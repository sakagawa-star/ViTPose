"""selection_score 範囲によるフレーム抽出 PNG ツール (feat-051).

kp モード JSON ディレクトリと動画を入力に、各フレームの最大 selection_score
(`s = pink_ratio + 0.05 * iou_with_prev`) が指定範囲 [score-min, score-max]
（両端含む）にあるフレームを抽出し、対象 person の BB / ROI / 胴体 4 点 /
診断ラベルを描画した PNG を出力する。--min-pink-ratio 閾値検討用。

特記事項:
- feat-041 設計で selection_score が None になるケース（連続性切れ復帰直後）が
  存在。本ツールでは「s=None なら pink_ratio で代替」というローカルフォール
  バック規約を採用（JSON 形式は変更しない）
- 描画ヘルパは feat-048 (visualize_disagreement_frames) から import
- 1 フレーム 1 person（最大有効 s の person のみ）を描画
"""
from __future__ import annotations

import argparse
import os
import sys

import cv2
import numpy as np

from visualize_disagreement_frames import (
    load_all_json,
    build_attempted_roi,
    extract_torso_kpts,
    draw_person_bbox,
    draw_roi,
    draw_torso_kpts,
    _check_conf,
    _check_area,
    BLUE,
    BLUE_DARK,
)


BANNER_HEIGHT = 60


# ---------------- バリデータ ----------------
def _check_score(s: str) -> float:
    fv = float(s)
    if not (0.0 <= fv <= 1.05):
        raise argparse.ArgumentTypeError(
            f"score must be in [0.0, 1.05], got {fv}"
        )
    return fv


# ---------------- 有効 s 計算 ----------------
def compute_effective_s(person: dict) -> tuple[float | None, bool]:
    """有効 s 値とフォールバック発動フラグを返す (FR-002)。

    Returns:
        (effective_s, used_fallback):
            effective_s: float または None
            used_fallback: selection_score が None で pink_ratio で代替したとき True
    """
    s = person.get("selection_score")
    if s is not None:
        return float(s), False
    r = person.get("pink_ratio")
    if r is not None:
        return float(r), True
    return None, False


def find_max_s_person(
    people: list[dict],
) -> tuple[dict | None, float | None, bool]:
    """全 person 中の有効 s 最大の person を返す (FR-003)。同値時はインデックス小を採用。"""
    best = None
    best_s = None
    best_fallback = False
    for p in people:
        s, fb = compute_effective_s(p)
        if s is None:
            continue
        if best_s is None or s > best_s:
            best = p
            best_s = s
            best_fallback = fb
    return best, best_s, best_fallback


# ---------------- 描画ヘルパ ----------------
def build_diag_label(p: dict) -> str:
    """BB 内部診断ラベル。キー欠損 ⇒ 省略、値 None ⇒ null 文字列。"""
    parts = []
    if "bb_index" in p:
        v = p["bb_index"]
        parts.append("idx=null" if v is None else f"idx={int(v)}")
    if "pink_id" in p:
        v = p["pink_id"]
        parts.append("pid=null" if v is None else f"pid={int(v)}")
    if "pink_ratio" in p:
        v = p["pink_ratio"]
        parts.append("r=null" if v is None else f"r={v:.3f}")
    if "iou_with_prev" in p:
        v = p["iou_with_prev"]
        parts.append("iou=null" if v is None else f"iou={v:.3f}")
    if "selection_score" in p:
        v = p["selection_score"]
        parts.append("s=null" if v is None else f"s={v:.3f}")
    return " ".join(parts)


def draw_diag_label(frame, bbox_i, text: str, color) -> None:
    if not text:
        return
    org = (bbox_i[0] + 4, bbox_i[1] + 16)
    cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (0, 0, 0), 2)
    cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                color, 1)


# ---------------- Main ----------------
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-dir", required=True,
                        help="kp モード JSON ディレクトリ")
    parser.add_argument("--video", required=True, help="元動画")
    parser.add_argument("--out-dir", required=True, help="PNG 出力先")
    parser.add_argument("--score-min", type=_check_score, required=True,
                        help="有効 s 下限（[0.0, 1.05]、含む）")
    parser.add_argument("--score-max", type=_check_score, required=True,
                        help="有効 s 上限（[0.0, 1.05]、含む）")
    parser.add_argument("--kpt-conf-min", type=_check_conf, default=0.3,
                        help="ROI 状態再計算用閾値（JSON 生成時と同値）")
    parser.add_argument("--min-roi-area", type=_check_area, default=200,
                        help="ROI 状態再計算用最低面積（JSON 生成時と同値）")
    parser.add_argument("--show-kpt-conf",
                        action=argparse.BooleanOptionalAction, default=True,
                        help="胴体 4 点の信頼度テキスト表示")
    args = parser.parse_args()

    if args.score_min > args.score_max:
        print(
            f"ERROR: --score-min ({args.score_min}) must be <= "
            f"--score-max ({args.score_max})",
            file=sys.stderr,
        )
        sys.exit(2)

    # AC-001-1: ディレクトリ・動画存在チェック
    if not os.path.isdir(args.json_dir):
        print(f"ERROR: JSON directory not found: {args.json_dir}",
              file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(args.video):
        print(f"ERROR: video not found: {args.video}", file=sys.stderr)
        sys.exit(1)
    os.makedirs(args.out_dir, exist_ok=True)

    json_data = load_all_json(args.json_dir)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"ERROR: failed to open video: {args.video}", file=sys.stderr)
        sys.exit(1)

    extracted = 0
    fallback_count = 0
    success_count = 0
    seek_fail_count = 0

    sorted_frames = sorted(json_data.keys())
    total = len(sorted_frames)
    for n, fr_idx in enumerate(sorted_frames):
        content = json_data[fr_idx]
        target, max_s, used_fallback = find_max_s_person(
            content.get("people", [])
        )
        if max_s is None:
            continue
        if not (args.score_min <= max_s <= args.score_max):
            continue
        extracted += 1
        if used_fallback:
            fallback_count += 1

        cap.set(cv2.CAP_PROP_POS_FRAMES, fr_idx)
        ret, frame = cap.read()
        if not ret:
            seek_fail_count += 1
            print(f"WARNING: failed to seek frame {fr_idx}", file=sys.stderr)
            continue

        img_h, img_w = frame.shape[:2]
        bbox = target.get("bbox")
        if bbox is None or len(bbox) != 4:
            continue
        bbox_i = tuple(int(round(v)) for v in bbox)

        # z-order:
        # 1) 人物 BB
        draw_person_bbox(frame, bbox, BLUE)

        # 2) ROI 矩形
        roi_bbox, roi_status = build_attempted_roi(
            target.get("pose_keypoints_2d", []),
            img_w, img_h, args.kpt_conf_min, args.min_roi_area,
        )
        if roi_bbox is not None:
            draw_roi(frame, roi_bbox, roi_status)

        # 3) 胴体 4 点
        kpts = extract_torso_kpts(target)
        if kpts is not None:
            draw_torso_kpts(frame, kpts, BLUE_DARK, args.show_kpt_conf,
                            args.kpt_conf_min)

        # 4) BB 内部診断ラベル
        draw_diag_label(frame, bbox_i, build_diag_label(target), BLUE)

        # （feat-051 v2: BB 上部ラベル pink_id:/score: は描画しない、AC-004-6）

        # 5) 黒帯バナーを元フレームの上に積層（段階 B、AC-004-5）
        banner = np.zeros((BANNER_HEIGHT, img_w, 3), dtype=np.uint8)
        top_lines = [
            f"Frame: {fr_idx:06d}  effective_s: {max_s:.3f} "
            f"(range: [{args.score_min}, {args.score_max}])",
            f"kp-rect ROI: {roi_status}"
            + ("  (s fallback: r used as s)" if used_fallback else ""),
        ]
        for i, line in enumerate(top_lines):
            org = (10, 22 + 24 * i)
            cv2.putText(banner, line, org, cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (255, 255, 255), 1, cv2.LINE_AA)
        output_img = np.vstack([banner, frame])

        out_path = os.path.join(
            args.out_dir, f"frame_{fr_idx:06d}_s{max_s:.3f}.png"
        )
        cv2.imwrite(out_path, output_img)
        success_count += 1

        if (n + 1) % 1000 == 0:
            print(f"Scanning frame {n + 1}/{total}")

    cap.release()

    scanned = len(json_data)  # 入力 JSON 総フレーム数（FR-006-1）
    print(f"Total JSON frames scanned: {scanned}")
    print(f"Frames in range [{args.score_min}, {args.score_max}]: {extracted}")
    print(f"Fallback used (s=None -> r): {fallback_count}")
    print(f"PNGs successfully saved: {success_count}")
    print(f"Seek failures: {seek_fail_count}")
    print(f"Output: {args.out_dir}/")


if __name__ == "__main__":
    main()
