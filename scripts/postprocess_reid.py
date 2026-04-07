"""Re-ID ポストプロセス: 既存 HALPE 26 JSON に stable_id を付与する (feat-028)

既存の動画ファイルと HALPE 26 JSON を入力とし、Deep OC-SORT + カスタム Re-ID を
実行して、各人物に stable_id を付与した新しい JSON ファイルを出力する。
ViTPose/MMPose によるキーポイント推定は行わない。
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


def init_tracker(device: str) -> DeepOcSort:
    """Deep OC-SORT トラッカーを初期化する。"""
    reid_path = Path(__file__).resolve().parent.parent / "osnet_x0_25_msmt17.pt"
    try:
        return DeepOcSort(
            reid_weights=reid_path,
            device=device,
            half="cuda" in device,
            max_age=30,
            w_association_emb=0.0,
        )
    except TypeError:
        print("WARNING: w_association_emb not supported, falling back without it")
        return DeepOcSort(
            reid_weights=reid_path,
            device=device,
            half="cuda" in device,
            max_age=30,
        )


def build_dets(json_people: list[dict]) -> np.ndarray:
    """JSON 人物リストから Deep OC-SORT 入力用の dets 配列を構築する。"""
    if len(json_people) > 0:
        return np.array(
            [
                [
                    p["bbox"][0], p["bbox"][1], p["bbox"][2], p["bbox"][3],
                    p["bbox_score"], 0,
                ]
                for p in json_people
            ],
            dtype=np.float32,
        )
    return np.empty((0, 6), dtype=np.float32)


def parse_tracks(tracks: np.ndarray) -> dict[int, list[float]]:
    """Deep OC-SORT 出力を tracked_bboxes 辞書に変換する。"""
    if len(tracks) > 0:
        return {int(t[4]): t[:4].tolist() for t in tracks}
    return {}


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


def match_track_to_json(
    tracked_bboxes: dict[int, list[float]],
    json_people: list[dict],
    iou_threshold: float = 0.5,
) -> dict[int, np.ndarray | None]:
    """track_id → キーポイントのマッチング（Re-ID 用）。"""
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


def assign_stable_ids(
    json_people: list[dict],
    tracked_bboxes: dict[int, list[float]],
    stable_ids: dict[int, int],
    iou_threshold: float = 0.5,
) -> list[int]:
    """各 JSON 人物に stable_id を割り当てる。

    JSON 人物 → track_id 方向の貪欲マッチング。
    IoU 最大値が同率の場合は track_id 最小を優先する。
    """
    result: list[int] = []

    if len(tracked_bboxes) == 0:
        return [-1] * len(json_people)

    for person in json_people:
        best_iou = 0.0
        best_tid = None
        for tid, bbox in tracked_bboxes.items():
            iou = compute_iou(person["bbox"], bbox)
            if iou > best_iou or (
                iou == best_iou
                and best_tid is not None
                and tid < best_tid
            ):
                best_iou = iou
                best_tid = tid
        if best_iou >= iou_threshold and best_tid is not None:
            result.append(stable_ids.get(best_tid, -1))
        else:
            result.append(-1)

    return result


def build_output_json(
    json_dir: str,
    video_stem: str,
    frame_idx: int,
    json_people: list[dict],
    person_stable_ids: list[int],
) -> dict:
    """入力 JSON を読み込み、stable_id を追加した出力 JSON を構築する。"""
    json_path = os.path.join(json_dir, f"{video_stem}_{frame_idx:06d}.json")

    if os.path.exists(json_path):
        with open(json_path) as f:
            data = json.load(f)
        for i, person in enumerate(data.get("people", [])):
            if i < len(person_stable_ids):
                person["stable_id"] = person_stable_ids[i]
            else:
                person["stable_id"] = -1
    else:
        data = {"version": 1.3, "people": []}

    return data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add stable_id to HALPE 26 JSON via Re-ID"
    )
    parser.add_argument("--video", required=True, help="Video file path")
    parser.add_argument(
        "--json-dir", required=True, help="Input HALPE 26 JSON directory"
    )
    parser.add_argument(
        "--out-dir", required=True,
        help="Output JSON directory (must differ from --json-dir)",
    )
    parser.add_argument("--device", default="cuda:0", help="BoxMOT device")
    args = parser.parse_args()

    # 上書き防止チェック
    if os.path.realpath(args.json_dir) == os.path.realpath(args.out_dir):
        print("ERROR: --out-dir must differ from --json-dir to prevent overwriting")
        sys.exit(1)

    # 出力ディレクトリ作成
    os.makedirs(args.out_dir, exist_ok=True)

    # JSON データ読み込み
    json_data = load_data(args.json_dir)
    print(f"Loaded {len(json_data)} frames from JSON")

    # 動画オープン
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"ERROR: Cannot open video {args.video}")
        sys.exit(1)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Deep OC-SORT 初期化
    tracker = init_tracker(args.device)

    # カスタム Re-ID 初期化
    reid = CustomReID(delay_frames=180)

    # 動画ファイル名のステム
    video_stem = os.path.splitext(os.path.basename(args.video))[0]

    # stable_id 集計
    all_stable_ids: set[int] = set()

    frame_idx = 0
    start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        json_people = json_data.get(frame_idx, [])

        # 1. Deep OC-SORT でトラッキング
        dets = build_dets(json_people)
        tracks = tracker.update(dets, frame)
        tracked_bboxes = parse_tracks(tracks)
        track_ids = list(tracked_bboxes.keys())

        # 2. IoU マッチング: track_id → キーポイント（Re-ID 用）
        keypoints_map = match_track_to_json(tracked_bboxes, json_people)

        # 3. カスタム Re-ID 更新
        stable_ids = reid.update(frame, track_ids, keypoints_map, frame_idx)

        # 4. JSON 人物 → stable_id の割り当て
        person_stable_ids = assign_stable_ids(
            json_people, tracked_bboxes, stable_ids
        )

        # 5. JSON 出力
        output_json = build_output_json(
            args.json_dir, video_stem, frame_idx, json_people, person_stable_ids
        )
        json_path = os.path.join(
            args.out_dir, f"{video_stem}_{frame_idx:06d}.json"
        )
        with open(json_path, "w") as f:
            json.dump(output_json, f)

        # stable_id 集計
        for sid in person_stable_ids:
            if sid >= 1:
                all_stable_ids.add(sid)

        # 進捗表示
        if frame_idx % 3000 == 0:
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

    # サマリー出力
    print()
    print(f"Total frames: {frame_idx}")
    print(f"Unique stable IDs: {len(all_stable_ids)}")
    if elapsed > 0:
        print(f"Processing time: {elapsed:.1f} sec ({frame_idx / elapsed:.1f} fps)")
    else:
        print(f"Processing time: {elapsed:.1f} sec")
    print(f"Output directory: {args.out_dir}")


if __name__ == "__main__":
    main()
