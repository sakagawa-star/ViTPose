"""カスタム Re-ID オフライン検証スクリプト (feat-022 イテレーション2)

既存の動画ファイルと HALPE 26 JSON を使い、カスタム Re-ID の動作をオフラインで検証する。
ViTPose/MMPose によるキーポイント推定は行わない。
"""

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from boxmot import DeepOcSort

from custom_reid import CustomReID


def load_data(json_dir: str) -> dict[int, list[dict]]:
    """JSON ディレクトリから全フレームの人物データを読み込む。

    Returns:
        {frame_idx: list[dict]}
        各 dict は bbox, bbox_score, kpts を持つ。
        欠番フレームはキーに含まれない。
    """
    json_path = Path(json_dir)
    json_files = sorted(json_path.glob("*.json"))

    if len(json_files) == 0:
        print(f"ERROR: No JSON files found in {json_dir}")
        sys.exit(1)

    pattern = re.compile(r"_(\d{6})\.json$")
    data: dict[int, list[dict]] = {}

    for jf in json_files:
        m = pattern.search(jf.name)
        if m is None:
            continue
        frame_idx = int(m.group(1))

        try:
            with open(jf) as f:
                content = json.load(f)
        except json.JSONDecodeError:
            print(f"WARNING: Failed to parse {jf.name}, treating as 0 people")
            data[frame_idx] = []
            continue

        people = []
        for person in content.get("people", []):
            kpts_flat = person.get("pose_keypoints_2d", [])
            if len(kpts_flat) != 78:
                print(
                    f"WARNING: Invalid keypoints length in {jf.name}, skipping person"
                )
                continue
            if "bbox" not in person:
                print(f"WARNING: Missing bbox in {jf.name}, skipping person")
                continue
            if "bbox_score" not in person:
                print(f"WARNING: Missing bbox_score in {jf.name}, skipping person")
                continue

            people.append(
                {
                    "bbox": person["bbox"],
                    "bbox_score": person["bbox_score"],
                    "kpts": np.array(kpts_flat, dtype=np.float32).reshape(26, 3),
                }
            )
        data[frame_idx] = people

    return data


def compute_iou(bbox1: list[float], bbox2: list[float]) -> float:
    """xyxy 形式の bbox の IoU を計算する。"""
    ix1 = max(bbox1[0], bbox2[0])
    iy1 = max(bbox1[1], bbox2[1])
    ix2 = min(bbox1[2], bbox2[2])
    iy2 = min(bbox1[3], bbox2[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
    area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
    union = area1 + area2 - inter
    return inter / union if union > 0 else 0.0


def match_by_iou(
    tracked_bboxes: dict[int, list[float]],
    json_people: list[dict],
    iou_threshold: float = 0.5,
) -> dict[int, np.ndarray | None]:
    """トラッカー出力 bbox と JSON 人物のキーポイントを IoU でマッチング。"""
    keypoints_map: dict[int, np.ndarray | None] = {}

    if len(json_people) == 0:
        return {tid: None for tid in tracked_bboxes}

    for track_id, bbox in tracked_bboxes.items():
        best_iou, best_kpts = 0.0, None
        for person in json_people:
            iou = compute_iou(bbox, person["bbox"])
            if iou > best_iou:
                best_iou = iou
                best_kpts = person["kpts"]
        keypoints_map[track_id] = best_kpts if best_iou >= iou_threshold else None

    return keypoints_map


def main() -> None:
    parser = argparse.ArgumentParser(description="Custom Re-ID offline verification")
    parser.add_argument("--video", required=True, help="Video file path")
    parser.add_argument("--json-dir", required=True, help="HALPE 26 JSON directory")
    parser.add_argument("--device", default="cuda:0", help="BoxMOT device")
    args = parser.parse_args()

    # JSON データ読み込み
    json_data = load_data(args.json_dir)
    print(f"Loaded {len(json_data)} frames from JSON")

    # 動画オープン
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"ERROR: Cannot open video {args.video}")
        sys.exit(1)

    # Deep OC-SORT 初期化
    reid_path = Path(__file__).resolve().parent.parent / "osnet_x0_25_msmt17.pt"
    try:
        tracker = DeepOcSort(
            reid_weights=reid_path,
            device=args.device,
            half="cuda" in args.device,
            max_age=30,
            w_association_emb=0.0,
        )
    except TypeError:
        print("WARNING: w_association_emb not supported, falling back without it")
        tracker = DeepOcSort(
            reid_weights=reid_path,
            device=args.device,
            half="cuda" in args.device,
            max_age=30,
        )

    # カスタム Re-ID 初期化
    reid = CustomReID()

    # stable_id ごとのフレーム数カウント
    stable_id_counts: dict[int, int] = defaultdict(int)

    frame_idx = 0
    start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        json_people = json_data.get(frame_idx, [])

        # dets 構築
        if len(json_people) > 0:
            dets = np.array(
                [
                    [
                        p["bbox"][0],
                        p["bbox"][1],
                        p["bbox"][2],
                        p["bbox"][3],
                        p["bbox_score"],
                        0,
                    ]
                    for p in json_people
                ],
                dtype=np.float32,
            )
        else:
            dets = np.empty((0, 6), dtype=np.float32)

        # トラッカー更新
        tracks = tracker.update(dets, frame)

        # tracks → tracked_bboxes 変換
        if len(tracks) > 0:
            tracked_bboxes = {int(t[4]): t[:4].tolist() for t in tracks}
        else:
            tracked_bboxes = {}
        track_ids = list(tracked_bboxes.keys())

        # IoU マッチング
        keypoints_map = match_by_iou(tracked_bboxes, json_people)

        # WARNING: IoU < 閾値でキーポイント取得不可（0人検出時は出力しない）
        if len(json_people) > 0:
            for tid, kpts in keypoints_map.items():
                if kpts is None:
                    print(
                        f"WARNING: no keypoints for track_id={tid} at frame {frame_idx}"
                    )

        # カスタム Re-ID 更新
        stable_ids = reid.update(frame, track_ids, keypoints_map)

        # stable_id カウント
        for sid in stable_ids.values():
            stable_id_counts[sid] += 1

        # 10 フレームごとに出力
        if frame_idx % 10 == 0:
            print(
                f"Processing frame {frame_idx:04d}: "
                f"track_ids={track_ids}, stable_ids={stable_ids}"
            )

        frame_idx += 1

    cap.release()
    elapsed = time.time() - start_time

    # 最終サマリー
    print()
    print("=== Re-ID Summary ===")
    print(f"Total frames: {frame_idx}")
    print(f"Stable ID counts: {dict(stable_id_counts)}")
    print(f"Unique stable IDs: {len(stable_id_counts)}")
    if elapsed > 0:
        print(f"Processing time: {elapsed:.1f} sec ({frame_idx / elapsed:.1f} fps)")
    else:
        print(f"Processing time: {elapsed:.1f} sec")


if __name__ == "__main__":
    main()
