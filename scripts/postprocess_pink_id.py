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

# ---------------- Constants (pink_tracker_jhub.py からの流用) ----------------
FIXED_HSV_RANGES: list[tuple[tuple[int, int, int], tuple[int, int, int]]] = [
    ((0, 60, 80), (10, 255, 255)),     # 赤系ピンク
    ((140, 60, 80), (159, 255, 255)),  # マゼンタ
    ((160, 60, 80), (179, 255, 255)),  # ピンク赤尾部
]
MIN_PINK_RATIO: float = 0.03
IOU_CONT_WEIGHT: float = 0.05


# ---------------- 純関数 ----------------
def compute_pink_ratio(roi_bgr: np.ndarray) -> float:
    """BGR ROI の HSV ピンク画素比率を返す (FR-001)。"""
    if roi_bgr.size == 0:
        return 0.0
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    mask_total = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lo, hi in FIXED_HSV_RANGES:
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


def select_pink_bbox(
    bboxes: list[tuple[int, int, int, int] | None],
    ratios: list[float],
    prev_selected_bbox: tuple[int, int, int, int] | None,
) -> int | None:
    """候補のうちスコア最大の BB インデックスを返す (FR-002)。

    None 要素（bbox 欠損）は ratio が 0.0 で閾値未満のため自動的に候補から除外される。
    同値時はインデックス小を優先する。
    """
    if not bboxes:
        return None
    candidates = [i for i, r in enumerate(ratios) if r >= MIN_PINK_RATIO]
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
        required=True,
        help="Output JSON directory (must differ from --json-dir)",
    )
    args = parser.parse_args()

    # 上書き防止チェック
    if os.path.realpath(args.json_dir) == os.path.realpath(args.out_dir):
        print("ERROR: --out-dir must differ from --json-dir to prevent overwriting")
        sys.exit(1)

    os.makedirs(args.out_dir, exist_ok=True)

    frame_to_json = load_json_frames(args.json_dir)
    print(f"Loaded {len(frame_to_json)} frames from JSON")

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"ERROR: Cannot open video {args.video}")
        sys.exit(1)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    progress_interval = max(1, total_frames // 10) if total_frames > 0 else 1

    # 集計
    summary_total = 0
    summary_selected = 0
    summary_no_candidate = 0
    summary_json_missing = 0
    summary_breaks = 0

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
        for i, person in enumerate(people):
            bb = person.get("bbox")
            if bb is None or len(bb) != 4:
                print(
                    f"WARNING: Missing/invalid bbox in frame {frame_idx} person {i}"
                )
                bboxes.append(None)
                ratios.append(0.0)
                continue
            clipped = clip_bbox(tuple(bb), W, H)
            cx1, cy1, cx2, cy2 = clipped
            if cx2 <= cx1 or cy2 <= cy1:
                roi = np.zeros((0, 0, 3), dtype=np.uint8)
            else:
                roi = frame_bgr[cy1:cy2, cx1:cx2]
            bboxes.append(clipped)
            ratios.append(compute_pink_ratio(roi))

        sel_idx = select_pink_bbox(bboxes, ratios, prev_selected_bbox)

        # pink_id 付与
        for i, person in enumerate(people):
            person["pink_id"] = 1 if i == sel_idx else -1

        # JSON 書き出し
        out_path = os.path.join(args.out_dir, filename)
        write_json_frame(out_path, content)

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


if __name__ == "__main__":
    main()
