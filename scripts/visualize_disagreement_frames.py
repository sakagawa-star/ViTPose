"""不一致フレーム可視化ツール (feat-048 v2).

bb モード JSON ディレクトリと keypoint-rect モード JSON ディレクトリを直接読み込み、
不一致フレームについて両モードの選択結果と keypoint-rect ROI 情報を 1 枚の PNG に
描画する。

描画内容:
- 人物 BB: bb 選択 = 赤枠、kp 選択 = 青枠（線幅 2）
- idx ラベル: 各 BB の右上角外側に BB と同色で
- keypoint-rect ROI 矩形: bb 選択人物の kp-rect ROI と kp 選択人物の kp-rect ROI を
  黄色 (線幅 2) で描画。同一 ROI は 1 つに dedup
- HALPE26 胴体 4 点 (LS/RS/LH/RH): bb 選択 = 暗赤、kp 選択 = 暗青。
  高信頼 (conf >= --kpt-conf-min) = 塗りつぶし円、低信頼 = × マーク。
  各点に 2 文字ラベル併記、信頼度テキストは --show-kpt-conf で ON/OFF
- 上部診断ラベル: Frame / Type / 各モードの idx・ratio・ROI 状態
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import cv2

from postprocess_pink_id import clip_bbox


PATTERN = re.compile(r"_(\d{6})\.json$")

# HALPE26 胴体 4 点 (feat-046 と同値)
TORSO_KEYPOINT_INDICES = (5, 6, 11, 12)
TORSO_KPT_LABELS = ("LS", "RS", "LH", "RH")

# 色 (BGR)
RED = (0, 0, 255)
BLUE = (255, 0, 0)
RED_DARK = (0, 0, 200)
BLUE_DARK = (200, 100, 0)
ROI_COLOR_OK = (0, 255, 255)        # ROI ok: 黄色
ROI_COLOR_FAIL_AREA = (0, 165, 255)  # ROI fail_area: オレンジ（試行矩形）
LABEL_BLACK = (0, 0, 0)
LABEL_WHITE = (255, 255, 255)

# 描画サイズ
BB_LINE_WIDTH = 2
ROI_LINE_WIDTH = 2
KPT_RADIUS = 6
KPT_CROSS_HALF = 6
TOP_LABEL_FONT_SCALE = 0.6
IDX_LABEL_FONT_SCALE = 0.55
KPT_LABEL_FONT_SCALE = 0.4


# ---------------- argparse validators ----------------
def _positive_int(s: str) -> int:
    v = int(s)
    if v < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {v}")
    return v


def _check_conf(s: str) -> float:
    fv = float(s)
    if not (0.0 <= fv <= 1.0):
        raise argparse.ArgumentTypeError(
            f"kpt-conf-min must be in [0.0, 1.0], got {fv}"
        )
    return fv


def _check_area(s: str) -> int:
    iv = int(s)
    if iv < 1:
        raise argparse.ArgumentTypeError(f"min-roi-area must be >= 1, got {iv}")
    return iv


# ---------------- JSON helpers ----------------
def load_all_json(json_dir: str) -> dict[int, dict]:
    """JSON ディレクトリから {frame_idx: content} を返す。"""
    result: dict[int, dict] = {}
    for fname in os.listdir(json_dir):
        m = PATTERN.search(fname)
        if not m:
            continue
        with open(os.path.join(json_dir, fname)) as f:
            result[int(m.group(1))] = json.load(f)
    return result


def find_pink_person(content: dict) -> dict | None:
    """pink_id == 1 の person を返す。"""
    for p in content.get("people", []):
        if p.get("pink_id") == 1:
            return p
    return None


def find_person_by_bb_index(content: dict, bb_idx) -> dict | None:
    """bb_index フィールド一致 person を線形検索。配列順序非依存。"""
    if bb_idx is None:
        return None
    for p in content.get("people", []):
        if p.get("bb_index") == bb_idx:
            return p
    return None


def classify(bb_idx, kp_idx) -> str | None:
    if bb_idx is None and kp_idx is None:
        return None
    if bb_idx is None:
        return "only_kp"
    if kp_idx is None:
        return "only_bb"
    if bb_idx != kp_idx:
        return "both_selected_different"
    return None


def build_attempted_roi(
    kpts_flat, width: int, height: int,
    conf_min: float, area_min: int,
) -> tuple[tuple[int, int, int, int] | None, str]:
    """ROI 構築を試みた結果を返す。area チェックは判定のみで矩形は破棄しない。

    feat-046 の build_keypoint_rect_roi との差分:
        本関数は fail_area でも矩形を返す（pink_ratio 計算には使わず、可視化
        目的で「試行された矩形」を画面に残すため）。

    Returns:
        (roi_bbox, status):
            roi_bbox = (x1, y1, x2, y2) int タプル または None
            status ∈ {"ok", "fail_kpt", "fail_area"}
            - ok / fail_area: roi_bbox は非 None（dedup の set 比較用に int 化）
            - fail_kpt: roi_bbox は None（信頼点 2 個未満で矩形不能）
    """
    if kpts_flat is None or len(kpts_flat) < 78:
        return None, "fail_kpt"
    candidates = []
    for idx in TORSO_KEYPOINT_INDICES:
        base = idx * 3
        x, y, c = kpts_flat[base], kpts_flat[base + 1], kpts_flat[base + 2]
        if c >= conf_min:
            candidates.append((x, y))
    if len(candidates) < 2:
        return None, "fail_kpt"
    xs = [p[0] for p in candidates]
    ys = [p[1] for p in candidates]
    x1, y1, x2, y2 = clip_bbox(
        (min(xs), min(ys), max(xs), max(ys)), width, height,
    )
    if x2 <= x1 or y2 <= y1:
        return None, "fail_kpt"
    area = (x2 - x1) * (y2 - y1)
    rect = (int(x1), int(y1), int(x2), int(y2))
    if area < area_min:
        return rect, "fail_area"
    return rect, "ok"


def get_attempted_roi_for_person(
    person: dict | None, img_w: int, img_h: int,
    kpt_conf_min: float, min_roi_area: int,
) -> tuple[tuple[int, int, int, int] | None, str]:
    """person が None の場合は ('not_present')、それ以外は build_attempted_roi。"""
    if person is None:
        return None, "not_present"
    return build_attempted_roi(
        person.get("pose_keypoints_2d", []),
        img_w, img_h, kpt_conf_min, min_roi_area,
    )


def extract_torso_kpts(person: dict | None):
    if person is None:
        return None
    kpts = person.get("pose_keypoints_2d", [])
    if len(kpts) < 78:
        return None
    return [
        (kpts[i * 3], kpts[i * 3 + 1], kpts[i * 3 + 2])
        for i in TORSO_KEYPOINT_INDICES
    ]


# ---------------- Drawing ----------------
def draw_person_bbox(frame, bbox, color):
    if bbox is None or len(bbox) != 4:
        return
    x1, y1, x2, y2 = (int(round(v)) for v in bbox)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, BB_LINE_WIDTH)


def draw_idx_label(frame, bbox, idx_str: str, color, img_w: int):
    if bbox is None or len(bbox) != 4:
        return
    x1, y1, x2, y2 = (int(round(v)) for v in bbox)
    label_w_estimate = 50
    if x2 + label_w_estimate < img_w:
        org = (x2 + 4, y1 + 14)
    else:
        org = (max(x2 - label_w_estimate, 0), y1 + 14)
    cv2.putText(frame, idx_str, org, cv2.FONT_HERSHEY_SIMPLEX,
                IDX_LABEL_FONT_SCALE, LABEL_BLACK, 3)
    cv2.putText(frame, idx_str, org, cv2.FONT_HERSHEY_SIMPLEX,
                IDX_LABEL_FONT_SCALE, color, 1)


def draw_roi(frame, roi_bbox_i, status: str):
    """状態に応じた色で ROI 矩形を描画。

    status="ok"        → 黄色
    status="fail_area" → オレンジ（試行矩形、feat-046 上は無効だが可視化目的で残す）
    呼び出し側で fail_kpt / not_present（roi_bbox_i is None）は除外済み。
    """
    if roi_bbox_i is None:
        return
    color = ROI_COLOR_OK if status == "ok" else ROI_COLOR_FAIL_AREA
    cv2.rectangle(
        frame,
        (roi_bbox_i[0], roi_bbox_i[1]),
        (roi_bbox_i[2], roi_bbox_i[3]),
        color, ROI_LINE_WIDTH,
    )


def draw_kpt_marker(frame, x, y, conf, color, kpt_conf_min: float):
    cx, cy = int(round(x)), int(round(y))
    if conf >= kpt_conf_min:
        cv2.circle(frame, (cx, cy), KPT_RADIUS, color, -1)
    else:
        h = KPT_CROSS_HALF
        cv2.line(frame, (cx - h, cy - h), (cx + h, cy + h), color, 2)
        cv2.line(frame, (cx + h, cy - h), (cx - h, cy + h), color, 2)


def draw_torso_kpts(frame, kpts, color, show_conf: bool,
                    kpt_conf_min: float) -> None:
    if kpts is None:
        return
    for (x, y, c), label in zip(kpts, TORSO_KPT_LABELS):
        draw_kpt_marker(frame, x, y, c, color, kpt_conf_min)
        cx, cy = int(round(x)), int(round(y))
        cv2.putText(frame, label, (cx + 8, cy - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, KPT_LABEL_FONT_SCALE,
                    LABEL_BLACK, 2)
        cv2.putText(frame, label, (cx + 8, cy - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, KPT_LABEL_FONT_SCALE,
                    color, 1)
        if show_conf:
            cv2.putText(frame, f"{c:.2f}", (cx + 8, cy + 10),
                        cv2.FONT_HERSHEY_SIMPLEX, KPT_LABEL_FONT_SCALE,
                        LABEL_BLACK, 2)
            cv2.putText(frame, f"{c:.2f}", (cx + 8, cy + 10),
                        cv2.FONT_HERSHEY_SIMPLEX, KPT_LABEL_FONT_SCALE,
                        color, 1)


def build_top_labels(fr_idx, dtype, bb_person, kp_person, kp_content,
                     img_w, img_h, kpt_conf_min, min_roi_area) -> list[str]:
    """上部診断ラベルを構築。

    bb 選択人物の kp 側対応 person が見つからない場合 (not_present) のみ、
    本関数内で WARNING を一本化して出力する（§4.5.1 側では出さない）。
    """
    lines = [f"Frame: {fr_idx:06d} | Type: {dtype}"]
    # bb 行
    if bb_person is not None:
        bb_idx = bb_person["bb_index"]
        kp_side_person = find_person_by_bb_index(kp_content, bb_idx)
        if kp_side_person is None:
            print(
                f"WARNING: frame {fr_idx} bb_index={bb_idx} "
                f"not found in kp JSON",
                file=sys.stderr,
            )
        roi_bbox, roi_status = get_attempted_roi_for_person(
            kp_side_person, img_w, img_h, kpt_conf_min, min_roi_area
        )
        roi_str = str(list(roi_bbox)) if roi_bbox else "->"
        lines.append(
            f"bb: idx={bb_idx} ratio={bb_person.get('pink_ratio', 0):.3f}  "
            f"kp-rect ROI: {roi_status} {roi_str}"
        )
    # kp 行: kp_person 直参照（pink_id=1 で取得済み）
    if kp_person is not None:
        kp_idx = kp_person["bb_index"]
        roi_bbox, roi_status = build_attempted_roi(
            kp_person.get("pose_keypoints_2d", []),
            img_w, img_h, kpt_conf_min, min_roi_area,
        )
        roi_str = str(list(roi_bbox)) if roi_bbox else "->"
        lines.append(
            f"kp: idx={kp_idx} ratio={kp_person.get('pink_ratio', 0):.3f}  "
            f"kp-rect ROI: {roi_status} {roi_str}"
        )
    return lines


def draw_top_labels(frame, lines):
    for i, line in enumerate(lines):
        org = (10, 25 + 25 * i)
        cv2.putText(frame, line, org, cv2.FONT_HERSHEY_SIMPLEX,
                    TOP_LABEL_FONT_SCALE, LABEL_BLACK, 3)
        cv2.putText(frame, line, org, cv2.FONT_HERSHEY_SIMPLEX,
                    TOP_LABEL_FONT_SCALE, LABEL_WHITE, 1)


# ---------------- Main ----------------
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bb-json-dir", required=True,
                        help="bb モード JSON ディレクトリ")
    parser.add_argument("--kp-json-dir", required=True,
                        help="keypoint-rect モード JSON ディレクトリ")
    parser.add_argument("--video", required=True, help="元動画ファイル")
    parser.add_argument("--out-dir", required=True, help="PNG 出力先ディレクトリ")
    parser.add_argument("--max-samples", type=_positive_int, default=50,
                        help="サンプル数上限 (>=1)。--all 時は無視")
    parser.add_argument("--all", action="store_true",
                        help="全件出力 (--max-samples を無視)")
    parser.add_argument("--show-kpt-conf",
                        action=argparse.BooleanOptionalAction, default=True,
                        help="胴体 4 点の信頼度テキストを表示 (デフォルト: True)")
    parser.add_argument("--kpt-conf-min", type=_check_conf, default=0.3,
                        help="ROI 状態再計算のキーポイント信頼度閾値 "
                             "(kp モード JSON 生成時と同値を渡すこと)")
    parser.add_argument("--min-roi-area", type=_check_area, default=200,
                        help="ROI 状態再計算の最低面積 "
                             "(kp モード JSON 生成時と同値を渡すこと)")
    args = parser.parse_args()

    for d in [args.bb_json_dir, args.kp_json_dir]:
        if not os.path.isdir(d):
            print(f"ERROR: JSON directory not found: {d}", file=sys.stderr)
            sys.exit(1)
    if not os.path.isfile(args.video):
        print(f"ERROR: video not found: {args.video}", file=sys.stderr)
        sys.exit(1)
    os.makedirs(args.out_dir, exist_ok=True)

    bb_data = load_all_json(args.bb_json_dir)
    kp_data = load_all_json(args.kp_json_dir)

    common_frames = sorted(set(bb_data) & set(kp_data))
    only_bb_files = set(bb_data) - set(kp_data)
    only_kp_files = set(kp_data) - set(bb_data)
    if only_bb_files or only_kp_files:
        print(
            f"WARNING: bb-only frames={len(only_bb_files)}, "
            f"kp-only frames={len(only_kp_files)}",
            file=sys.stderr,
        )

    disagreement_frames: list[tuple[int, str]] = []
    counts = {"both_selected_different": 0, "only_bb": 0, "only_kp": 0}
    for f in common_frames:
        bb_p = find_pink_person(bb_data[f])
        kp_p = find_pink_person(kp_data[f])
        bb_idx = bb_p["bb_index"] if bb_p else None
        kp_idx = kp_p["bb_index"] if kp_p else None
        dtype = classify(bb_idx, kp_idx)
        if dtype is None:
            continue
        disagreement_frames.append((f, dtype))
        counts[dtype] += 1

    original_count = len(disagreement_frames)
    if not args.all and original_count > args.max_samples:
        step = original_count / args.max_samples
        indices = [int(i * step) for i in range(args.max_samples)]
        disagreement_frames = [disagreement_frames[i] for i in indices]

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"ERROR: failed to open video: {args.video}", file=sys.stderr)
        sys.exit(1)

    success_count = 0
    seek_fail_count = 0
    total = len(disagreement_frames)

    for n, (fr_idx, dtype) in enumerate(disagreement_frames):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fr_idx)
        ret, frame = cap.read()
        if not ret:
            seek_fail_count += 1
            print(f"WARNING: failed to seek frame {fr_idx}", file=sys.stderr)
            continue

        img_h, img_w = frame.shape[:2]
        bb_content = bb_data[fr_idx]
        kp_content = kp_data[fr_idx]
        bb_person = find_pink_person(bb_content)
        kp_person = find_pink_person(kp_content)

        # 1) 人物 BB
        if dtype in ("both_selected_different", "only_bb") and bb_person is not None:
            draw_person_bbox(frame, bb_person.get("bbox"), RED)
        if dtype in ("both_selected_different", "only_kp") and kp_person is not None:
            draw_person_bbox(frame, kp_person.get("bbox"), BLUE)

        # 2) ROI 矩形 (試行 ROI を含めて常に描画。状態で色分け、dedup)
        bb_idx_val = bb_person["bb_index"] if bb_person else None
        kp_idx_val = kp_person["bb_index"] if kp_person else None
        bb_owner_person = (
            find_person_by_bb_index(kp_content, bb_idx_val)
            if bb_idx_val is not None else None
        )
        bb_owner_roi, bb_owner_status = get_attempted_roi_for_person(
            bb_owner_person, img_w, img_h,
            args.kpt_conf_min, args.min_roi_area,
        )
        kp_owner_roi, kp_owner_status = get_attempted_roi_for_person(
            kp_person, img_w, img_h,
            args.kpt_conf_min, args.min_roi_area,
        )
        drawn_roi_keys: set = set()
        for roi, status in (
            (bb_owner_roi, bb_owner_status),
            (kp_owner_roi, kp_owner_status),
        ):
            if roi is None or roi in drawn_roi_keys:
                continue
            draw_roi(frame, roi, status)
            drawn_roi_keys.add(roi)

        # 3) idx ラベル
        if dtype in ("both_selected_different", "only_bb") and bb_person is not None:
            draw_idx_label(frame, bb_person.get("bbox"),
                           f"idx={bb_idx_val}", RED, img_w)
        if dtype in ("both_selected_different", "only_kp") and kp_person is not None:
            draw_idx_label(frame, kp_person.get("bbox"),
                           f"idx={kp_idx_val}", BLUE, img_w)

        # 4) 胴体 4 点
        bb_kpts = extract_torso_kpts(bb_person)
        kp_kpts = extract_torso_kpts(kp_person)
        same_person = (
            bb_idx_val is not None and kp_idx_val is not None
            and bb_idx_val == kp_idx_val
        )
        if bb_kpts is not None:
            draw_torso_kpts(frame, bb_kpts, RED_DARK, args.show_kpt_conf,
                            args.kpt_conf_min)
        if kp_kpts is not None and not same_person:
            draw_torso_kpts(frame, kp_kpts, BLUE_DARK, args.show_kpt_conf,
                            args.kpt_conf_min)

        # 5) 上部ラベル
        lines = build_top_labels(
            fr_idx, dtype, bb_person, kp_person, kp_content,
            img_w, img_h, args.kpt_conf_min, args.min_roi_area,
        )
        draw_top_labels(frame, lines)

        out_path = os.path.join(args.out_dir, f"frame_{fr_idx:06d}_disagree.png")
        cv2.imwrite(out_path, frame)
        success_count += 1

        if (n + 1) % 10 == 0:
            print(f"Processing frame {n + 1}/{total}")

    cap.release()

    print(f"Total disagreement frames: {original_count}")
    print(f"  both_selected_different={counts['both_selected_different']}")
    print(f"  only_bb={counts['only_bb']}")
    print(f"  only_kp={counts['only_kp']}")
    print(f"Samples to process: {total}")
    print(f"PNGs successfully saved: {success_count}")
    print(f"Seek failures: {seek_fail_count}")
    print(f"Output: {args.out_dir}/")


if __name__ == "__main__":
    main()
