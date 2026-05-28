"""Pink-id ポストプロセス: 既存 HALPE 26 JSON に pink_id を付与する (feat-033)

参考: /home/sakagawa/Downloads/pink_tracker_jhub.py（別プロジェクトの原版）

入力:
  - 動画ファイル (MP4)
  - HALPE 26 OpenPose JSON ディレクトリ（run_halpe26_pipeline_yolo11.py の出力）

処理:
  各フレームの各人物 BB について HSV ピンクマスクの画素比率を計算し、閾値超の候補
  の中から "比率 + IOU_CONT_WEIGHT * iou(prev_selected_bbox, bbox)" が最大の BB を
  患者として選択する。選択された BB を持つ人物に pink_id=1、それ以外に pink_id=-1
  を付与した新しい JSON ディレクトリを出力する。

出力:
  指定した出力ディレクトリに、入力と同じ命名規約で JSON を書き出す。
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from visualize_patient_video import (  # noqa: E402
    draw_frame_number,
    draw_person,
    filter_people,
    get_color_for_mode,
)

# ---------------- Constants (pink_tracker_jhub.py からの流用) ----------------
FIXED_HSV_RANGES: list[tuple[tuple[int, int, int], tuple[int, int, int]]] = [
    ((0, 60, 80), (10, 255, 255)),     # 赤系ピンク
    ((140, 60, 80), (159, 255, 255)),  # マゼンタ
    ((160, 60, 80), (179, 255, 255)),  # ピンク赤尾部
]
MIN_PINK_RATIO: float = 0.03
IOU_CONT_WEIGHT: float = 0.05

# HALPE 26 の胴体キーポイント (LShoulder, RShoulder, LHip, RHip)
TORSO_KEYPOINT_INDICES: tuple[int, int, int, int] = (5, 6, 11, 12)


# ---------------- argparse type checkers ----------------
def _check_conf(v: str) -> float:
    fv = float(v)
    if not (0.0 <= fv <= 1.0):
        raise argparse.ArgumentTypeError(
            f"kpt-conf-min must be in [0.0, 1.0], got {fv}"
        )
    return fv


def _check_area(v: str) -> int:
    iv = int(v)
    if iv < 1:
        raise argparse.ArgumentTypeError(f"min-roi-area must be >= 1, got {iv}")
    return iv


def _check_ratio(v: str) -> float:
    fv = float(v)
    if not (0.0 <= fv <= 1.0):
        raise argparse.ArgumentTypeError(
            f"min-pink-ratio must be in [0.0, 1.0], got {fv}"
        )
    return fv


# ---------------- HSV 設定ファイル (feat-053) ----------------
def _config_error(msg: str) -> None:
    print(f"ERROR: invalid HSV config: {msg}", file=sys.stderr)
    sys.exit(1)


def _validate_hsv_triple(t, ri: int, which: str) -> tuple[int, int, int]:
    """[H,S,V] を検証する。H:[0,179] S/V:[0,255]、整数のみ (bool/float 不可)。"""
    if not isinstance(t, (list, tuple)) or len(t) != 3:
        _config_error(f"range[{ri}].{which} must be a 3-element [H,S,V]")
    bounds = ((0, 179), (0, 255), (0, 255))
    out: list[int] = []
    for ci, (v, (lo_b, hi_b)) in enumerate(zip(t, bounds)):
        if isinstance(v, bool) or not isinstance(v, int):
            _config_error(f"range[{ri}].{which}[{ci}] must be an integer")
        if not (lo_b <= v <= hi_b):
            _config_error(f"range[{ri}].{which}[{ci}]={v} out of [{lo_b}, {hi_b}]")
        out.append(v)
    return (out[0], out[1], out[2])


def _validate_ranges(
    raw,
) -> list[tuple[tuple[int, int, int], tuple[int, int, int]]]:
    """fixed_hsv_ranges を検証し FIXED_HSV_RANGES と同じ tuple 構造に正規化する。"""
    if not isinstance(raw, list) or len(raw) == 0:
        _config_error("fixed_hsv_ranges must be a non-empty array")
    result: list[tuple[tuple[int, int, int], tuple[int, int, int]]] = []
    for ri, r in enumerate(raw):
        if not isinstance(r, (list, tuple)) or len(r) != 2:
            _config_error(f"range[{ri}] must be [lo, hi]")
        lo = _validate_hsv_triple(r[0], ri, "lo")
        hi = _validate_hsv_triple(r[1], ri, "hi")
        for ci in range(3):
            if lo[ci] > hi[ci]:
                _config_error(f"range[{ri}] lo[{ci}]={lo[ci]} > hi[{ci}]={hi[ci]}")
        result.append((lo, hi))
    return result


def _validate_min_pink_ratio(v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        _config_error("min_pink_ratio must be a number")
    if not (0.0 <= v <= 1.0):
        _config_error(f"min_pink_ratio={v} out of [0.0, 1.0]")
    return float(v)


def load_hsv_config(
    path: str,
) -> tuple[list[tuple[tuple[int, int, int], tuple[int, int, int]]], float]:
    """HSV 設定ファイル (JSON) を読み検証する。失敗時は sys.exit(1)。

    必須キー: fixed_hsv_ranges, min_pink_ratio (両キー必須、B-1)。
    """
    if not os.path.isfile(path):
        print(f"ERROR: HSV config file not found: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        with open(path) as f:
            cfg = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: failed to parse HSV config JSON: {e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(cfg, dict):
        _config_error("root must be a JSON object")
    for key in ("fixed_hsv_ranges", "min_pink_ratio"):
        if key not in cfg:
            _config_error(f"missing required key: {key}")
    ranges = _validate_ranges(cfg["fixed_hsv_ranges"])
    mpr = _validate_min_pink_ratio(cfg["min_pink_ratio"])
    return ranges, mpr


def resolve_min_pink_ratio(
    cli_value: float | None, config_value: float | None
) -> float:
    """CLI明示 > 設定ファイル > デフォルト の順で min_pink_ratio を決める (FR-003)。"""
    if cli_value is not None:
        return cli_value
    if config_value is not None:
        return config_value
    return MIN_PINK_RATIO


# ---------------- 純関数 ----------------
def compute_pink_ratio(roi_bgr: np.ndarray, ranges: list | None = None) -> float:
    """BGR ROI の HSV ピンク画素比率を返す (FR-001)。

    ranges=None のときは従来どおりグローバル FIXED_HSV_RANGES を使う
    （後方互換: 引数なし呼び出しの analyze_clothing_color.py を壊さない）。
    """
    if roi_bgr.size == 0:
        return 0.0
    use_ranges = FIXED_HSV_RANGES if ranges is None else ranges
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    mask_total = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lo, hi in use_ranges:
        lo_np = np.array(lo, dtype=np.uint8)
        hi_np = np.array(hi, dtype=np.uint8)
        mask = cv2.inRange(hsv, lo_np, hi_np)
        mask_total = cv2.bitwise_or(mask_total, mask)
    pink_pixels = int(np.count_nonzero(mask_total))
    total_pixels = roi_bgr.shape[0] * roi_bgr.shape[1]
    return pink_pixels / total_pixels if total_pixels > 0 else 0.0


def compute_iou(
    a: tuple[int, int, int, int],
    b: tuple[int, int, int, int],
) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    ua = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    ub = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = ua + ub - inter
    return inter / union if union > 0 else 0.0


def clip_bbox(
    bbox: tuple[float, float, float, float],
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    bx1, by1, bx2, by2 = bbox
    x1 = max(0, min(width - 1, int(round(bx1))))
    y1 = max(0, min(height - 1, int(round(by1))))
    x2 = max(0, min(width - 1, int(round(bx2))))
    y2 = max(0, min(height - 1, int(round(by2))))
    return (x1, y1, x2, y2)


def build_keypoint_rect_roi(
    kpts_flat: list[float],
    width: int,
    height: int,
    conf_min: float,
    area_min: int,
) -> tuple[tuple[int, int, int, int] | None, str]:
    """HALPE 26 の胴体 4 点から軸並行最小矩形 ROI を構築する (feat-046 FR-004)。

    K-2 方式: 信頼できる点 (conf >= conf_min) の座標のみで min/max 矩形を取る。
    F2 厳しめ: ROI 構築不能なら (None, status) を返す（自動 BB フォールバックなし）。

    Returns:
        ((x1, y1, x2, y2), "ok") or (None, "fail_kpt"|"fail_area")
    """
    if kpts_flat is None or len(kpts_flat) < 78:
        return None, "fail_kpt"
    candidates: list[tuple[float, float]] = []
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
        return None, "fail_area"
    area = (x2 - x1) * (y2 - y1)
    if area < area_min:
        return None, "fail_area"
    return (x1, y1, x2, y2), "ok"


def select_pink_bbox(
    bboxes: list[tuple[int, int, int, int] | None],
    ratios: list[float],
    prev_selected_bbox: tuple[int, int, int, int] | None,
    min_pink_ratio: float,
) -> int | None:
    """候補のうちスコア最大の BB インデックスを返す (FR-002)。

    None 要素（bbox 欠損）は ratio が 0.0 で閾値未満のため自動的に候補から除外される。
    同値時はインデックス小を優先する。

    min_pink_ratio: pink_id=1 候補とする最低 pink_ratio（feat-050 で引数化、
    デフォルトは main 側で MIN_PINK_RATIO=0.03）。
    """
    if not bboxes:
        return None
    candidates = [i for i, r in enumerate(ratios) if r >= min_pink_ratio]
    if not candidates:
        return None
    if prev_selected_bbox is None:
        best_i = candidates[0]
        best_r = ratios[best_i]
        for i in candidates[1:]:
            if ratios[i] > best_r:
                best_i = i
                best_r = ratios[i]
        return best_i
    # with continuity bonus
    best_i = candidates[0]
    assert bboxes[best_i] is not None  # candidates に含まれる時点で ratio > 0
    best_score = ratios[best_i] + IOU_CONT_WEIGHT * compute_iou(
        prev_selected_bbox, bboxes[best_i]
    )
    for i in candidates[1:]:
        assert bboxes[i] is not None
        score = ratios[i] + IOU_CONT_WEIGHT * compute_iou(
            prev_selected_bbox, bboxes[i]
        )
        if score > best_score:
            best_i = i
            best_score = score
    return best_i


# ---------------- I/O ----------------
def load_json_frames(json_dir: str) -> dict[int, tuple[str, dict]]:
    """JSON ディレクトリから全フレームの生 dict を読み込む。

    Returns:
        {frame_idx: (original_filename, content_dict)}
    """
    json_path = Path(json_dir)
    json_files = sorted(json_path.glob("*.json"))
    if not json_files:
        print(f"ERROR: No JSON files found in {json_dir}")
        sys.exit(1)

    pattern = re.compile(r"_(\d{6})\.json$")
    out: dict[int, tuple[str, dict]] = {}
    for jf in json_files:
        m = pattern.search(jf.name)
        if m is None:
            continue
        fidx = int(m.group(1))
        try:
            with open(jf) as f:
                content = json.load(f)
        except json.JSONDecodeError:
            print(f"WARNING: Failed to parse {jf.name}, treating as empty")
            content = {"version": 1.3, "people": []}
        out[fidx] = (jf.name, content)
    return out


def write_json_frame(out_path: str, data: dict) -> None:
    with open(out_path, "w") as f:
        json.dump(data, f)


# ---------------- Main ----------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add pink_id (color-based patient ID) to HALPE 26 JSON files"
    )
    parser.add_argument("--video", required=True, help="Input video file path")
    parser.add_argument(
        "--json-dir", required=True, help="Input HALPE 26 JSON directory"
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help=(
            "Output JSON directory (must differ from --json-dir). "
            "If omitted, derived as '<json-dir>_pink_id'."
        ),
    )
    parser.add_argument(
        "--roi-mode", default="bb", choices=["bb", "keypoint-rect"],
        help=(
            "ROI for pink ratio. bb: existing BB; keypoint-rect: min/max "
            "axis-aligned rect of 4 torso keypoints (default: bb)"
        ),
    )
    parser.add_argument(
        "--kpt-conf-min", type=_check_conf, default=0.3,
        help=(
            "Minimum keypoint confidence to use for keypoint-rect ROI "
            "(0.0-1.0, default: 0.3)"
        ),
    )
    parser.add_argument(
        "--min-roi-area", type=_check_area, default=200,
        help="Minimum ROI area in pixels (>=1, default: 200)",
    )
    parser.add_argument(
        "--min-pink-ratio", type=_check_ratio, default=None,
        help=(
            f"Minimum pink_ratio to be a pink_id=1 candidate ([0.0, 1.0]). "
            f"Overrides --hsv-config value; default if both unset: {MIN_PINK_RATIO}"
        ),
    )
    parser.add_argument(
        "--hsv-config", default=None,
        help=(
            "Path to JSON config with keys 'fixed_hsv_ranges' and "
            "'min_pink_ratio'. If omitted, built-in FIXED_HSV_RANGES is used."
        ),
    )
    # ---- 確認動画同時出力 (feat-056) ----
    parser.add_argument(
        "--visualize", action=argparse.BooleanOptionalAction, default=True,
        help=(
            "Also write an overlay MP4 (pink_id) while assigning pink_id "
            "(default: on; use --no-visualize to skip)"
        ),
    )
    parser.add_argument(
        "--vis-out-dir", default=None,
        help=(
            "Output directory for the visualization MP4. "
            "If omitted, the parent directory of --out-dir is used."
        ),
    )
    parser.add_argument(
        "--vis-mode", default="filter", choices=["filter", "all"],
        help="Drawing mode: filter (only matching pink_id) or all (color-code all)",
    )
    parser.add_argument(
        "--vis-filter-values", type=int, nargs="+", default=[1],
        help="pink_id values to draw in filter mode (default: 1)",
    )
    parser.add_argument(
        "--vis-kpt-thr", type=float, default=0.3,
        help="Keypoint confidence threshold for skeleton drawing (default: 0.3)",
    )
    parser.add_argument(
        "--draw-start", type=int, default=0,
        help="First frame to draw into the MP4 (default: 0)",
    )
    parser.add_argument(
        "--draw-end", type=int, default=-1,
        help="Last frame to draw into the MP4, inclusive (-1=until end)",
    )
    parser.add_argument(
        "--show-bb-index", action=argparse.BooleanOptionalAction, default=True,
        help="Show bb_index in the debug label",
    )
    parser.add_argument(
        "--show-pink-id", action=argparse.BooleanOptionalAction, default=True,
        help="Show pink_id in the debug label",
    )
    parser.add_argument(
        "--show-pink-ratio", action=argparse.BooleanOptionalAction, default=True,
        help="Show pink_ratio in the debug label",
    )
    parser.add_argument(
        "--show-iou-with-prev", action=argparse.BooleanOptionalAction, default=True,
        help="Show iou_with_prev in the debug label",
    )
    parser.add_argument(
        "--show-selection-score", action=argparse.BooleanOptionalAction, default=True,
        help="Show selection_score in the debug label",
    )
    args = parser.parse_args()

    if args.out_dir is None:
        args.out_dir = os.path.normpath(args.json_dir) + "_pink_id"
        print(f"[INFO] --out-dir not specified, using derived path: {args.out_dir}")

    debug_flags = {
        "bb_index": args.show_bb_index,
        "pink_id": args.show_pink_id,
        "pink_ratio": args.show_pink_ratio,
        "iou_with_prev": args.show_iou_with_prev,
        "selection_score": args.show_selection_score,
    }

    # 上書き防止チェック
    if os.path.realpath(args.json_dir) == os.path.realpath(args.out_dir):
        print("ERROR: --out-dir must differ from --json-dir to prevent overwriting")
        sys.exit(1)

    os.makedirs(args.out_dir, exist_ok=True)

    if args.vis_out_dir is None:
        args.vis_out_dir = os.path.dirname(os.path.normpath(args.out_dir)) or "."

    # HSV 設定の解決 (feat-053)
    if args.hsv_config is not None:
        active_ranges, config_min_pink_ratio = load_hsv_config(args.hsv_config)
    else:
        active_ranges = FIXED_HSV_RANGES
        config_min_pink_ratio = None
    min_pink_ratio = resolve_min_pink_ratio(
        args.min_pink_ratio, config_min_pink_ratio
    )

    frame_to_json = load_json_frames(args.json_dir)
    print(f"Loaded {len(frame_to_json)} frames from JSON")

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"ERROR: Cannot open video {args.video}")
        sys.exit(1)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    progress_interval = max(1, total_frames // 10) if total_frames > 0 else 1

    # 確認動画出力の初期化 (feat-056)
    writer = None
    vis_out_path = None
    if args.visualize:
        os.makedirs(args.vis_out_dir, exist_ok=True)
        vis_fps = cap.get(cv2.CAP_PROP_FPS)
        vis_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        vis_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        video_stem = Path(args.video).stem
        out_name = f"vis_pink_id_{args.vis_mode}_{video_stem}.mp4"
        vis_out_path = os.path.join(args.vis_out_dir, out_name)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(vis_out_path, fourcc, vis_fps, (vis_w, vis_h))
        if not writer.isOpened():
            print(f"ERROR: Failed to open VideoWriter: {vis_out_path}")
            sys.exit(1)
        draw_end_disp = "end" if args.draw_end == -1 else args.draw_end
        print(f"Visualize: ON -> {vis_out_path}")
        print(
            f"  mode={args.vis_mode}, filter_values={args.vis_filter_values}, "
            f"draw_range={args.draw_start}-{draw_end_disp}"
        )

    # 集計
    summary_total = 0
    summary_selected = 0
    summary_no_candidate = 0
    summary_json_missing = 0
    summary_breaks = 0
    stats_kpt = {"ok": 0, "fail_kpt": 0, "fail_area": 0}

    prev_selected_bbox: tuple[int, int, int, int] | None = None

    frame_idx = 0
    start_time = time.time()

    while True:
        ret, frame_bgr = cap.read()
        if not ret:
            if frame_idx == 0:
                print("WARNING: Could not read any frame from video")
            break

        summary_total += 1
        H, W = frame_bgr.shape[:2]

        entry = frame_to_json.get(frame_idx)
        if entry is None:
            # JSONなしフレーム → 連続性切れ扱い
            summary_json_missing += 1
            if prev_selected_bbox is not None:
                summary_breaks += 1
            prev_selected_bbox = None
            frame_idx += 1
            continue

        filename, content = entry
        people = content.get("people", [])

        bboxes: list[tuple[int, int, int, int] | None] = []
        ratios: list[float] = []
        roi_bboxes: list[tuple[int, int, int, int] | None] = []
        for i, person in enumerate(people):
            bb = person.get("bbox")
            if bb is None or len(bb) != 4:
                print(
                    f"WARNING: Missing/invalid bbox in frame {frame_idx} person {i}"
                )
                bboxes.append(None)
                ratios.append(0.0)
                roi_bboxes.append(None)
                continue
            clipped = clip_bbox(tuple(bb), W, H)
            bboxes.append(clipped)

            if args.roi_mode == "bb":
                cx1, cy1, cx2, cy2 = clipped
                if cx2 <= cx1 or cy2 <= cy1:
                    roi = np.zeros((0, 0, 3), dtype=np.uint8)
                else:
                    roi = frame_bgr[cy1:cy2, cx1:cx2]
                ratios.append(compute_pink_ratio(roi, ranges=active_ranges))
                roi_bboxes.append(None)
            else:  # keypoint-rect
                kpts_flat = person.get("pose_keypoints_2d", [])
                roi_bbox, status = build_keypoint_rect_roi(
                    kpts_flat, W, H,
                    args.kpt_conf_min, args.min_roi_area,
                )
                stats_kpt[status] += 1
                if roi_bbox is None:
                    ratios.append(0.0)
                    roi_bboxes.append(None)
                else:
                    rx1, ry1, rx2, ry2 = roi_bbox
                    roi = frame_bgr[ry1:ry2, rx1:rx2]
                    ratios.append(compute_pink_ratio(roi, ranges=active_ranges))
                    roi_bboxes.append(roi_bbox)

        sel_idx = select_pink_bbox(
            bboxes, ratios, prev_selected_bbox, min_pink_ratio
        )

        # IoU 計算（現フレームのスコア計算で参照した prev_selected_bbox を使う）
        ious: list[float | None] = []
        for bb in bboxes:
            if bb is None or prev_selected_bbox is None:
                ious.append(None)
            else:
                ious.append(compute_iou(prev_selected_bbox, bb))

        # pink_id / pink_ratio / bb_index / iou_with_prev / selection_score 付与
        for i, person in enumerate(people):
            person["pink_id"] = 1 if i == sel_idx else -1
            person["pink_ratio"] = ratios[i]
            person["bb_index"] = i
            person["iou_with_prev"] = ious[i]
            person["selection_score"] = (
                None if ious[i] is None
                else ratios[i] + IOU_CONT_WEIGHT * ious[i]
            )
            if args.roi_mode == "keypoint-rect":
                person["roi_mode"] = "keypoint-rect"
                person["roi_bbox"] = (
                    list(roi_bboxes[i]) if roi_bboxes[i] is not None else None
                )

        # JSON 書き出し
        out_path = os.path.join(args.out_dir, filename)
        write_json_frame(out_path, content)

        # 確認動画への描画 (feat-056)
        if writer is not None:
            in_draw_range = frame_idx >= args.draw_start and (
                args.draw_end == -1 or frame_idx <= args.draw_end
            )
            if in_draw_range:
                draw_frame_number(frame_bgr, frame_idx)
                visible = filter_people(
                    people, "pink_id", args.vis_mode, args.vis_filter_values
                )
                for person in visible:
                    id_value = person.get("pink_id", -1)
                    color = get_color_for_mode(id_value, args.vis_mode)
                    draw_person(
                        frame_bgr, person, color, "pink_id",
                        args.vis_kpt_thr, debug_flags,
                    )
                writer.write(frame_bgr)

        # 統計・前フレーム状態更新
        if sel_idx is not None:
            summary_selected += 1
            selected_bbox = bboxes[sel_idx]
            assert selected_bbox is not None
            prev_selected_bbox = selected_bbox
        else:
            summary_no_candidate += 1
            if prev_selected_bbox is not None:
                summary_breaks += 1
            prev_selected_bbox = None

        # 進捗表示
        if frame_idx % progress_interval == 0:
            if total_frames > 0:
                pct = frame_idx / total_frames * 100
                print(
                    f"Processing frame {frame_idx:06d}/{total_frames} ({pct:.1f}%)"
                )
            else:
                print(f"Processing frame {frame_idx:06d}/?")

        frame_idx += 1

    cap.release()
    if writer is not None:
        writer.release()
    elapsed = time.time() - start_time
    fps = summary_total / elapsed if elapsed > 0 else 0.0

    # サマリ
    print()
    print(f"Total frames: {summary_total}")
    print(f"Frames with pink_id=1: {summary_selected}")
    print(
        f"Frames without candidate (no valid bbox candidate above threshold): "
        f"{summary_no_candidate}"
    )
    print(f"Frames without json: {summary_json_missing}")
    print(f"Continuity breaks: {summary_breaks}")
    print(f"Processing time: {elapsed:.1f} sec ({fps:.1f} fps)")
    print(f"Output directory: {args.out_dir}")
    if writer is not None:
        print(f"Visualization MP4: {vis_out_path}")
    if args.hsv_config is not None:
        print(f"HSV config: {args.hsv_config}")
    else:
        print("HSV config: default (built-in FIXED_HSV_RANGES)")
    print(f"Active HSV ranges: {active_ranges}")
    print(f"Min pink ratio threshold: {min_pink_ratio:.3f}")

    if args.roi_mode == "keypoint-rect":
        total_persons = (
            stats_kpt["ok"] + stats_kpt["fail_kpt"] + stats_kpt["fail_area"]
        )
        print(f"ROI mode: keypoint-rect")
        print(f"  ROI built (ok):       {stats_kpt['ok']:6d} / {total_persons:6d}")
        print(f"  ROI failed (kpt):     {stats_kpt['fail_kpt']:6d} / {total_persons:6d}")
        print(f"  ROI failed (area):    {stats_kpt['fail_area']:6d} / {total_persons:6d}")


if __name__ == "__main__":
    main()
