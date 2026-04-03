"""BoxMOT Deep OC-SORT offline tracking test.

既存のOpenPose JSON（bbox + bbox_score）と元動画を使い、
ViTPose推論なしでDeep OC-SORTの動作を確認するテストスクリプト。

Usage:
    uv run python scripts/test_boxmot_offline.py \
        --video testdata/pexels_4441000.mp4 \
        --json-dir experiments/results/feat-018-test/pexels_4441000_json/
"""

import argparse
import glob
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from boxmot import DeepOcSort


def load_bboxes_from_json(json_dir: str) -> list[list[dict]]:
    """JSONディレクトリからフレームごとのbbox情報を読み込む。"""
    json_files = sorted(glob.glob(str(Path(json_dir) / "*.json")))

    if len(json_files) == 0:
        print(f"Error: No JSON files found in {json_dir}")
        sys.exit(1)

    all_bboxes = []
    for json_path in json_files:
        with open(json_path) as f:
            data = json.load(f)

        frame_bboxes = []
        for person in data.get("people", []):
            if "bbox" not in person or "bbox_score" not in person:
                print(f"Warning: bbox/bbox_score missing in {json_path}, skipping person")
                continue
            frame_bboxes.append({
                "bbox": person["bbox"],
                "bbox_score": person["bbox_score"],
            })
        all_bboxes.append(frame_bboxes)

    print(f"Loaded {len(all_bboxes)} frames from {json_dir}")
    return all_bboxes


def main() -> None:
    parser = argparse.ArgumentParser(description="BoxMOT Deep OC-SORT offline tracking test")
    parser.add_argument("--video", type=str, required=True, help="Input video path")
    parser.add_argument("--json-dir", type=str, required=True, help="OpenPose JSON directory")
    parser.add_argument("--device", type=str, default="cuda:0", help="Tracker device (cuda:N or cpu)")
    parser.add_argument("--max-age", type=int, default=30, help="Max frames to keep lost tracks (default: 30)")
    args = parser.parse_args()

    # FR-1: JSON読み込み
    all_bboxes = load_bboxes_from_json(args.json_dir)

    # FR-2: 動画を開く
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"Error: Cannot open video: {args.video}")
        sys.exit(1)

    video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    json_frames = len(all_bboxes)

    if video_frames != json_frames:
        print(f"Warning: Frame count mismatch - video: {video_frames}, JSON: {json_frames}")

    num_frames = min(video_frames, json_frames)
    print(f"Processing {num_frames} frames...")

    # FR-3: トラッカー初期化
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    reid_path = project_root / "osnet_x0_25_msmt17.pt"

    if not reid_path.exists():
        print(f"Error: Re-ID model not found: {reid_path}")
        print("feat-020のセットアップが完了しているか確認してください。")
        sys.exit(1)

    tracker = DeepOcSort(
        reid_weights=reid_path,
        device=args.device,
        half="cuda" in args.device,
        max_age=args.max_age,
    )
    print(f"Tracker max_age={args.max_age}")

    # FR-3: トラッキング実行
    track_id_counts: dict[int, int] = defaultdict(int)
    skipped = 0
    consecutive_errors = 0
    start_time = time.time()

    for frame_idx in range(num_frames):
        ret, frame = cap.read()
        if not ret:
            print(f"Warning: Failed to read frame {frame_idx}, skipping")
            skipped += 1
            continue

        people = all_bboxes[frame_idx]

        if len(people) == 0:
            dets = np.empty((0, 6), dtype=np.float32)
        else:
            dets = np.array(
                [[*p["bbox"], p["bbox_score"], 0] for p in people],
                dtype=np.float32,
            )

        try:
            tracks = tracker.update(dets, frame)
            consecutive_errors = 0
        except Exception as e:
            print(f"Error at frame {frame_idx}: {e}")
            skipped += 1
            consecutive_errors += 1
            if consecutive_errors >= 10 and frame_idx < 10:
                print("Error: First 10 frames all failed. Aborting.")
                sys.exit(1)
            continue

        # FR-4: フレームごとの出力（10フレームおき）
        if len(tracks) > 0:
            track_ids = tracks[:, 4].astype(int)
            for tid in track_ids:
                track_id_counts[int(tid)] += 1

            if frame_idx % 10 == 0 or frame_idx == num_frames - 1:
                ids_str = ", ".join(str(tid) for tid in track_ids)
                print(f"Frame {frame_idx:04d}: {len(tracks)} person(s) [track_id: {ids_str}]")
        else:
            if frame_idx % 10 == 0 or frame_idx == num_frames - 1:
                print(f"Frame {frame_idx:04d}: 0 person(s)")

    elapsed = time.time() - start_time
    cap.release()

    # FR-4: サマリー出力
    fps = num_frames / elapsed if elapsed > 0 else 0
    print("\n=== Tracking Summary ===")
    print(f"Total frames: {num_frames}")
    print(f"Skipped frames: {skipped}")
    print(f"Unique track IDs: {dict(sorted(track_id_counts.items()))}")
    for tid, count in sorted(track_id_counts.items()):
        print(f"  ID {tid}: {count} frames")
    print(f"Processing time: {elapsed:.1f} sec ({fps:.1f} fps)")


if __name__ == "__main__":
    main()
