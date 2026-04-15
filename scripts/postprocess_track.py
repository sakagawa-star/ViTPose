"""track_id ポストプロセス: 既存 HALPE 26 JSON に track_id を付与する (feat-035)

feat-034 ロードマップの Stage 2 に対応。Deep OC-SORT を単独で実行し、
生 track_id を各人物エントリに付与する。custom_reid.py / stable_id 関連の
ロジックは一切使用しない。

入力:
  - 動画ファイル (MP4)
  - HALPE 26 OpenPose JSON ディレクトリ（run_halpe26_pipeline_yolo11.py の出力）

出力:
  指定した出力ディレクトリに、入力と同じ命名規約で JSON を書き出す。
  各 people エントリに track_id: int を追加（既存フィールドは変更しない生 dict 保持設計）。
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


# ---------------- Constants ----------------
IOU_THRESHOLD: float = 0.5
TRACK_ID_UNMATCHED: int = -1
PROGRESS_INTERVAL_FRAMES: int = 3000
DEEP_OC_SORT_MAX_AGE: int = 30


# ---------------- 純関数 ----------------
def _is_valid_bbox(bbox) -> bool:
    """bbox が 4 要素の数値リスト/タプルか判定する。bool は除外する。"""
    if bbox is None:
        return False
    if not isinstance(bbox, (list, tuple)):
        return False
    if len(bbox) != 4:
        return False
    return all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in bbox
    )


def _is_number(v) -> bool:
    """数値判定。bool は int のサブクラスだが除外する。"""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def compute_iou(a: list[float], b: list[float]) -> float:
    """xyxy 形式の bbox の IoU を計算する。"""
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def build_dets(
    people: list[dict],
    frame_idx: int,
) -> tuple[np.ndarray, list[int]]:
    """有効人物のみから Deep OC-SORT 入力用の dets 配列を構築する (FR-003)。

    Returns:
        (dets: shape=(M, 6) dtype=float32, valid_indices: list[int])
    """
    if len(people) == 0:
        return np.empty((0, 6), dtype=np.float32), []

    rows: list[list[float]] = []
    valid_indices: list[int] = []
    for i, person in enumerate(people):
        bbox = person.get("bbox")
        score = person.get("bbox_score")
        if not _is_valid_bbox(bbox) or not _is_number(score):
            print(
                f"WARNING: Invalid bbox/bbox_score in frame {frame_idx} "
                f"person {i}, excluding from tracking"
            )
            continue
        rows.append([bbox[0], bbox[1], bbox[2], bbox[3], float(score), 0.0])
        valid_indices.append(i)

    if len(rows) == 0:
        return np.empty((0, 6), dtype=np.float32), []
    return np.array(rows, dtype=np.float32), valid_indices


def parse_tracks(tracks: np.ndarray) -> dict[int, list[float]]:
    """Deep OC-SORT の戻り値を {track_id: [x1, y1, x2, y2]} に変換する。"""
    if len(tracks) == 0:
        return {}
    return {int(t[4]): t[:4].tolist() for t in tracks}


def assign_track_ids(
    people: list[dict],
    valid_indices: list[int],
    tracked_bboxes: dict[int, list[float]],
    iou_threshold: float = IOU_THRESHOLD,
) -> list[int]:
    """各 JSON 人物に track_id を割り当てる (FR-004)。

    無効人物・IoU 閾値未満・IoU=0・マッチなしはすべて TRACK_ID_UNMATCHED。
    同値タイブレークでは最小 track_id を優先する。
    """
    result: list[int] = [TRACK_ID_UNMATCHED] * len(people)
    if not tracked_bboxes:
        return result

    for i in valid_indices:
        person_bbox = people[i]["bbox"]
        best_iou = 0.0
        best_tid: int | None = None
        for tid, trk_bbox in tracked_bboxes.items():
            iou = compute_iou(person_bbox, trk_bbox)
            if iou > best_iou:
                best_iou = iou
                best_tid = tid
            elif iou == best_iou and best_tid is not None and tid < best_tid:
                best_tid = tid
        if best_iou >= iou_threshold and best_tid is not None:
            result[i] = best_tid
    return result


# ---------------- I/O ----------------
def load_json_frames(json_dir: str) -> dict[int, tuple[str, dict]]:
    """JSON ディレクトリから全フレームの生 dict を読み込む (FR-001)。

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


def init_tracker(device: str) -> DeepOcSort:
    """Deep OC-SORT トラッカーを初期化する (FR-002)。"""
    reid_path = Path(__file__).resolve().parent.parent / "osnet_x0_25_msmt17.pt"
    try:
        return DeepOcSort(
            reid_weights=reid_path,
            device=device,
            half="cuda" in device,
            max_age=DEEP_OC_SORT_MAX_AGE,
            w_association_emb=0.0,
        )
    except TypeError:
        print("WARNING: w_association_emb not supported, falling back without it")
        return DeepOcSort(
            reid_weights=reid_path,
            device=device,
            half="cuda" in device,
            max_age=DEEP_OC_SORT_MAX_AGE,
        )


def print_summary(
    total_frames_processed: int,
    all_track_ids: set[int],
    elapsed: float,
    out_dir: str,
) -> None:
    fps = total_frames_processed / elapsed if elapsed > 0 else 0.0
    print()
    print(f"Total frames: {total_frames_processed}")
    print(f"Unique track IDs: {len(all_track_ids)}")
    print(f"Processing time: {elapsed:.1f} sec ({fps:.1f} fps)")
    print(f"Output directory: {out_dir}")


# ---------------- Main ----------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add track_id to HALPE 26 JSON via Deep OC-SORT"
    )
    parser.add_argument("--video", required=True, help="Video file path")
    parser.add_argument(
        "--json-dir", required=True, help="Input HALPE 26 JSON directory"
    )
    parser.add_argument(
        "--out-dir", required=True,
        help="Output JSON directory (must differ from --json-dir)",
    )
    parser.add_argument(
        "--device", default="cuda:0", help="BoxMOT device (e.g., cuda:0, cpu)"
    )
    args = parser.parse_args()

    # 上書き防止
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
    tracker = init_tracker(args.device)

    all_track_ids: set[int] = set()
    frame_idx = 0
    start_time = time.time()

    while True:
        ret, frame_bgr = cap.read()
        if not ret:
            break

        entry = frame_to_json.get(frame_idx)

        if entry is None:
            # 入力 JSON がない: tracker の時間同期のみ、JSON 出力なし (ADR-004)
            tracker.update(np.empty((0, 6), dtype=np.float32), frame_bgr)
        else:
            filename, content_dict = entry
            people = content_dict.get("people", [])

            dets, valid_indices = build_dets(people, frame_idx)
            tracks = tracker.update(dets, frame_bgr)
            tracked_bboxes = parse_tracks(tracks)
            assigned = assign_track_ids(people, valid_indices, tracked_bboxes)

            for i, person in enumerate(people):
                person["track_id"] = assigned[i]

            for tid in assigned:
                if tid >= 1:
                    all_track_ids.add(tid)

            out_path = os.path.join(args.out_dir, filename)
            write_json_frame(out_path, content_dict)

        if frame_idx % PROGRESS_INTERVAL_FRAMES == 0:
            if total_frames > 0:
                pct = frame_idx / total_frames * 100
                print(f"Processing frame {frame_idx:06d}/{total_frames} ({pct:.1f}%)")
            else:
                print(f"Processing frame {frame_idx:06d}/?")

        frame_idx += 1

    cap.release()
    elapsed = time.time() - start_time
    print_summary(frame_idx, all_track_ids, elapsed, args.out_dir)


if __name__ == "__main__":
    main()
