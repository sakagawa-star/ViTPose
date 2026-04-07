"""カスタム Re-ID オフライン検証スクリプト (feat-022 iter2 + feat-026)

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

from custom_reid import CustomReID, PersonFeature


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


def print_reid_report(
    reid_events: list[dict],
    reid: CustomReID,
    last_stable_ids: dict[int, int],
) -> None:
    """Re-IDイベントログと統計情報を出力する（FR-003）。"""
    # (1) Re-ID Event Log
    type_order = {"disappear": 0, "appear": 1, "delayed_match": 2, "delayed_timeout": 3}
    sorted_events = sorted(
        reid_events, key=lambda e: (e["frame_idx"], type_order.get(e["type"], 99))
    )

    print()
    print("=== Re-ID Event Log ===")
    for e in sorted_events:
        etype = e["type"]
        fidx = e["frame_idx"]
        if etype == "disappear":
            print(
                f"[{'disappear':<9}] frame={fidx:06d} "
                f"track_id={e['track_id']} stable_id={e['stable_id']}"
            )
        elif etype == "appear":
            mt = e["match_type"]
            if mt == "instant":
                detail = f"(instant match from sid={e['from_sid']})"
            elif mt == "new":
                detail = "(new)"
            else:
                detail = "(pending)"
            print(
                f"[{'appear':<9}] frame={fidx:06d} "
                f"track_id={e['track_id']} stable_id={e['stable_id']} {detail}"
            )
        elif etype == "delayed_match":
            print(
                f"[{'delayed':<9}] frame={fidx:06d} "
                f"track_id={e['track_id']} old_sid={e['old_stable_id']} "
                f"new_sid={e['new_stable_id']} (offset={e['offset']})"
            )
        elif etype == "delayed_timeout":
            print(
                f"[{'timeout':<9}] frame={fidx:06d} "
                f"track_id={e['track_id']} stable_id={e['stable_id']} (confirmed)"
            )

    # (2) Re-ID Statistics
    appear_events = [e for e in reid_events if e["type"] == "appear"]
    disappear_events = [e for e in reid_events if e["type"] == "disappear"]
    delayed_matches = [e for e in reid_events if e["type"] == "delayed_match"]
    delayed_timeouts = [e for e in reid_events if e["type"] == "delayed_timeout"]

    instant_count = sum(1 for e in appear_events if e["match_type"] == "instant")
    new_count = sum(1 for e in appear_events if e["match_type"] == "new")

    delayed_success = len(delayed_matches)
    delayed_timeout_count = len(delayed_timeouts)

    # 保留中消失: pending appear のうち delayed/timeout が発生しなかったもの
    delayed_match_tids = {e["track_id"] for e in delayed_matches}
    delayed_timeout_tids = {e["track_id"] for e in delayed_timeouts}
    pending_tids = {e["track_id"] for e in appear_events if e["match_type"] == "pending"}
    pending_disappeared = len(pending_tids - delayed_match_tids - delayed_timeout_tids)

    delayed_total = delayed_success + delayed_timeout_count
    if delayed_total > 0:
        delayed_rate = (
            f"{delayed_success}/{delayed_total} "
            f"({delayed_success / delayed_total * 100:.1f}%)"
        )
    else:
        delayed_rate = "0/0 (N/A)"

    # Unique stable IDs (final)
    final_active_sids = set(last_stable_ids.values())
    final_disappeared_sids = set(reid.disappeared.keys())
    final_unique = final_active_sids | final_disappeared_sids

    # Active stable IDs at last frame
    active_at_last = {sid: tid for tid, sid in last_stable_ids.items()}

    print()
    print("=== Re-ID Statistics ===")
    print(f"Total appear events: {len(appear_events)}")
    print(f"  Instant match: {instant_count}")
    print(f"  New (no disappeared): {new_count}")
    print(f"  New (pending \u2192 delayed match): {delayed_success}")
    print(f"  New (pending \u2192 timeout): {delayed_timeout_count}")
    print(f"  New (pending \u2192 disappeared): {pending_disappeared}")
    print(f"Total disappear events: {len(disappear_events)}")
    print(f"Delayed match success rate: {delayed_rate}")
    print(f"Unique stable IDs (final): {len(final_unique)}")
    if len(active_at_last) > 0:
        print(f"Active stable IDs at last frame: {active_at_last}")
    else:
        print("Active stable IDs at last frame: (no active tracks at last frame)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Custom Re-ID offline verification")
    parser.add_argument("--video", required=True, help="Video file path")
    parser.add_argument("--json-dir", required=True, help="HALPE 26 JSON directory")
    parser.add_argument("--device", default="cuda:0", help="BoxMOT device")
    parser.add_argument(
        "--print-interval", type=int, default=10,
        help="Progress log interval in frames (default: 10)",
    )
    parser.add_argument(
        "--no-sim-log", action="store_true",
        help="Suppress Re-ID similarity log output",
    )
    args = parser.parse_args()

    # JSON データ読み込み
    json_data = load_data(args.json_dir)
    print(f"Loaded {len(json_data)} frames from JSON")

    # 動画オープン
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"ERROR: Cannot open video {args.video}")
        sys.exit(1)

    # 総フレーム数（0以下の場合は取得失敗）
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

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
    reid = CustomReID(delay_frames=180)

    # stable_id ごとのフレーム数カウント
    stable_id_counts: dict[int, int] = defaultdict(int)

    # FR-008: 遅延マッチ実験用の状態管理（--no-sim-log 時は不使用）
    recently_appeared: dict[int, int] = {}  # {track_id: 出現フレーム番号}
    snapshot_disappeared: dict[int, PersonFeature] = {}

    # FR-002: Re-IDイベント収集
    reid_events: list[dict] = []
    prev_track_set: set[int] = set()
    prev_stable_map: dict[int, int] = {}

    frame_idx = 0
    stable_ids: dict[int, int] = {}
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

        # FR-008: --no-sim-log 未指定時のみスナップショット取得
        if not args.no_sim_log:
            snapshot_disappeared = dict(reid.disappeared)

        # カスタム Re-ID 更新
        stable_ids = reid.update(frame, track_ids, keypoints_map, frame_idx)

        # FR-002: イベント収集
        # last_events から出現イベントの match_type マッピングを構築
        appear_info: dict[int, tuple[str, int | None]] = {}
        for event in reid.last_events:
            if event["type"] == "instant_match":
                appear_info[event["track_id"]] = ("instant", event["from_disappeared_sid"])
            elif event["type"] == "new_id":
                appear_info[event["track_id"]] = ("new", None)
            elif event["type"] == "pending":
                appear_info[event["track_id"]] = ("pending", None)

        # 消失検出
        curr_track_set = set(track_ids)
        lost_tids = prev_track_set - curr_track_set
        for tid in sorted(lost_tids):
            sid = prev_stable_map[tid]
            reid_events.append({
                "type": "disappear", "frame_idx": frame_idx,
                "track_id": tid, "stable_id": sid,
            })

        # 出現検出
        for tid in sorted(appear_info.keys()):
            assigned_sid = stable_ids[tid]
            match_type, from_sid = appear_info[tid]
            if match_type == "instant":
                reid_events.append({
                    "type": "appear", "frame_idx": frame_idx,
                    "track_id": tid, "stable_id": assigned_sid,
                    "match_type": "instant", "from_sid": from_sid,
                })
            elif match_type == "new":
                reid_events.append({
                    "type": "appear", "frame_idx": frame_idx,
                    "track_id": tid, "stable_id": assigned_sid,
                    "match_type": "new",
                })
            elif match_type == "pending":
                reid_events.append({
                    "type": "appear", "frame_idx": frame_idx,
                    "track_id": tid, "stable_id": assigned_sid,
                    "match_type": "pending",
                })

        # 遅延マッチ・タイムアウトイベントの取得
        for event in reid.last_events:
            if event["type"] == "delayed_match":
                reid_events.append({
                    "type": "delayed_match",
                    "frame_idx": event["frame_idx"],
                    "track_id": event["track_id"],
                    "old_stable_id": event["old_stable_id"],
                    "new_stable_id": event["new_stable_id"],
                    "offset": event["offset"],
                })
            elif event["type"] == "delayed_timeout":
                reid_events.append({
                    "type": "delayed_timeout",
                    "frame_idx": event["frame_idx"],
                    "track_id": event["track_id"],
                    "stable_id": event["stable_id"],
                })

        # FR-008: --no-sim-log 未指定時のみ類似度ログ出力
        if not args.no_sim_log:
            # 新規出現 track_id を記録
            for tid in track_ids:
                if tid not in recently_appeared:
                    recently_appeared[tid] = frame_idx

            # 消失した track_id を recently_appeared から除去
            disappeared_tids = set(recently_appeared.keys()) - set(track_ids)
            for tid in disappeared_tids:
                del recently_appeared[tid]

            # 類似度ログ出力
            for tid, appear_frame in recently_appeared.items():
                offset = frame_idx - appear_frame
                current_feat = reid.active_features.get(tid)
                if current_feat is None:
                    continue
                for sid, dis_feat in snapshot_disappeared.items():
                    if stable_ids.get(tid) == sid:
                        continue
                    sim = reid._compute_similarity(current_feat, dis_feat)
                    print(
                        f"Re-ID sim: frame={frame_idx:04d} offset={offset:02d} "
                        f"track_id={tid} disappeared_sid={sid} sim={sim:.3f}"
                    )

        # stable_id カウント
        for sid in stable_ids.values():
            stable_id_counts[sid] += 1

        # FR-001: 進捗ログ
        if frame_idx % args.print_interval == 0:
            if total_frames > 0:
                pct = frame_idx / total_frames * 100
                print(
                    f"Processing frame {frame_idx:06d}/{total_frames} ({pct:.1f}%): "
                    f"track_ids={track_ids}, stable_ids={stable_ids}"
                )
            else:
                print(
                    f"Processing frame {frame_idx:06d}/?: "
                    f"track_ids={track_ids}, stable_ids={stable_ids}"
                )

        # ループ末尾で更新
        prev_track_set = curr_track_set
        prev_stable_map = dict(stable_ids)

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

    # FR-003: Re-IDサマリーレポート
    print_reid_report(reid_events, reid, stable_ids)


if __name__ == "__main__":
    main()
