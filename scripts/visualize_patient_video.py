"""pink_track_id / pink_id / track_id 動画可視化 (feat-038)

元動画に BB・ID テキスト・キーポイント・スケルトンをオーバーレイした MP4 を出力する。
--id-type で描画に使用する ID 種別を選択、--mode で描画モードを切替できる。
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
from merge_halpe26 import HALPE26_SKELETON  # noqa: E402


# ---------------- Constants ----------------
PROGRESS_INTERVAL_FRAMES: int = 3000
COLOR_GRAY: tuple[int, int, int] = (128, 128, 128)
COLOR_FILTER: tuple[int, int, int] = (0, 255, 0)
ID_TYPE_SHORT: dict[str, str] = {
    "pink_track_id": "ptid",
    "pink_id": "pid",
    "track_id": "tid",
}


# ---------------- Color palette ----------------
def _generate_palette(n: int = 20) -> list[tuple[int, int, int]]:
    palette = []
    for i in range(n):
        h = int(180 * i / n)
        hsv = np.array([[[h, 255, 255]]], dtype=np.uint8)
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        palette.append(tuple(int(c) for c in bgr[0, 0]))
    return palette


COLOR_PALETTE: list[tuple[int, int, int]] = _generate_palette(20)


def get_color_for_mode(
    id_value: int, mode: str
) -> tuple[int, int, int]:
    if mode == "filter":
        return COLOR_FILTER
    if not isinstance(id_value, int) or id_value < 0:
        return COLOR_GRAY
    return COLOR_PALETTE[id_value % len(COLOR_PALETTE)]


# ---------------- JSON helpers ----------------
def detect_json_stem(json_dir: str) -> str:
    json_path = Path(json_dir)
    pattern = re.compile(r"^(.+)_\d{6}\.json$")
    for f in sorted(json_path.glob("*.json")):
        m = pattern.match(f.name)
        if m:
            return m.group(1)
    print(f"ERROR: No valid JSON files found in {json_dir}")
    sys.exit(1)


def load_frame_json(json_path: str) -> list[dict]:
    if not os.path.exists(json_path):
        return []
    try:
        with open(json_path) as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print(f"WARNING: Failed to parse {json_path}")
        return []
    return data.get("people", [])


# ---------------- Filtering ----------------
def filter_people(
    people: list[dict],
    id_type: str,
    mode: str,
    filter_values: list[int],
) -> list[dict]:
    if mode == "all":
        return people
    result = []
    for person in people:
        id_val = person.get(id_type)
        if id_val is None:
            continue
        if id_val in filter_values:
            result.append(person)
    return result


# ---------------- Drawing ----------------
def draw_skeleton(
    img: np.ndarray,
    person: dict,
    color: tuple[int, int, int],
    kpt_thr: float,
) -> None:
    kpts_flat = person.get("pose_keypoints_2d", [])
    if len(kpts_flat) < 26 * 3:
        return
    kpts = np.array(kpts_flat).reshape(26, 3)

    for i, j in HALPE26_SKELETON:
        if kpts[i, 2] > kpt_thr and kpts[j, 2] > kpt_thr:
            pt1 = (int(kpts[i, 0]), int(kpts[i, 1]))
            pt2 = (int(kpts[j, 0]), int(kpts[j, 1]))
            cv2.line(img, pt1, pt2, color, 2)

    for idx in range(26):
        if kpts[idx, 2] > kpt_thr:
            x, y = int(kpts[idx, 0]), int(kpts[idx, 1])
            cv2.circle(img, (x, y), 4, color, -1)


def build_debug_label(person: dict, debug_flags: dict[str, bool]) -> str:
    parts: list[str] = []

    if debug_flags["bb_index"] and "bb_index" in person:
        v = person["bb_index"]
        parts.append("idx=null" if v is None else f"idx={int(v)}")

    if debug_flags["pink_id"] and "pink_id" in person:
        v = person["pink_id"]
        parts.append("pid=null" if v is None else f"pid={int(v)}")

    if debug_flags["pink_ratio"] and "pink_ratio" in person:
        v = person["pink_ratio"]
        parts.append("r=null" if v is None else f"r={v:.3f}")

    if debug_flags["iou_with_prev"] and "iou_with_prev" in person:
        v = person["iou_with_prev"]
        parts.append("iou=null" if v is None else f"iou={v:.3f}")

    if debug_flags["selection_score"] and "selection_score" in person:
        v = person["selection_score"]
        parts.append("s=null" if v is None else f"s={v:.3f}")

    return " ".join(parts)


def draw_person(
    img: np.ndarray,
    person: dict,
    color: tuple[int, int, int],
    id_type: str,
    kpt_thr: float,
    debug_flags: dict[str, bool],
) -> None:
    bbox = person.get("bbox")
    if bbox is None or len(bbox) != 4:
        return
    x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

    id_value = person.get(id_type, "?")
    score = person.get("bbox_score", 0)
    short = ID_TYPE_SHORT.get(id_type, id_type)
    label = f"{short}:{id_value} {score:.2f}"
    text_y = y1 - 8 if y1 - 8 > 0 else y1 + 20
    cv2.putText(img, label, (x1, text_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    debug_label = build_debug_label(person, debug_flags)
    if debug_label:
        cv2.putText(img, debug_label, (x1 + 4, y1 + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

    draw_skeleton(img, person, color, kpt_thr)


def draw_frame_number(img: np.ndarray, frame_idx: int) -> None:
    cv2.putText(img, f"Frame: {frame_idx}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)


# ---------------- Main ----------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visualize BB/skeleton on video with pink_track_id/pink_id/track_id"
    )
    parser.add_argument("--video", required=True, help="Input video file")
    parser.add_argument("--json-dir", required=True, help="Input JSON directory")
    parser.add_argument("--out-dir", default="output", help="Output directory")
    parser.add_argument(
        "--id-type", default="pink_track_id",
        choices=["pink_track_id", "pink_id", "track_id"],
        help="ID type to visualize",
    )
    parser.add_argument(
        "--mode", default="all", choices=["filter", "all"],
        help="Drawing mode: filter (show only matching BBs) or all (color-code all)",
    )
    parser.add_argument(
        "--filter-values", type=int, nargs="+", default=[1],
        help="ID values to draw in filter mode",
    )
    parser.add_argument("--draw-start", type=int, default=0, help="Draw start frame")
    parser.add_argument("--draw-end", type=int, default=-1, help="Draw end frame (-1=end)")
    parser.add_argument("--kpt-thr", type=float, default=0.3, help="Keypoint threshold")
    parser.add_argument(
        "--show-bb-index",
        action=argparse.BooleanOptionalAction, default=True,
        help="Show bb_index in debug label (BB interior)",
    )
    parser.add_argument(
        "--show-pink-id",
        action=argparse.BooleanOptionalAction, default=True,
        help="Show pink_id in debug label",
    )
    parser.add_argument(
        "--show-pink-ratio",
        action=argparse.BooleanOptionalAction, default=True,
        help="Show pink_ratio in debug label",
    )
    parser.add_argument(
        "--show-iou-with-prev",
        action=argparse.BooleanOptionalAction, default=True,
        help="Show iou_with_prev in debug label",
    )
    parser.add_argument(
        "--show-selection-score",
        action=argparse.BooleanOptionalAction, default=True,
        help="Show selection_score in debug label",
    )
    args = parser.parse_args()

    debug_flags = {
        "bb_index": args.show_bb_index,
        "pink_id": args.show_pink_id,
        "pink_ratio": args.show_pink_ratio,
        "iou_with_prev": args.show_iou_with_prev,
        "selection_score": args.show_selection_score,
    }

    if not os.path.isdir(args.json_dir):
        print(f"ERROR: JSON directory not found: {args.json_dir}")
        sys.exit(1)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"ERROR: Failed to open video: {args.video}")
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    os.makedirs(args.out_dir, exist_ok=True)
    video_stem = Path(args.video).stem
    out_name = f"vis_{args.id_type}_{args.mode}_{video_stem}.mp4"
    out_path = os.path.join(args.out_dir, out_name)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

    json_stem = detect_json_stem(args.json_dir)
    draw_end = args.draw_end

    print(f"Video: {args.video} ({total_frames} frames, {fps} fps)")
    print(f"JSON: {args.json_dir}")
    print(f"ID type: {args.id_type}, Mode: {args.mode}")
    if args.mode == "filter":
        print(f"Filter values: {args.filter_values}")
    print(f"Draw range: {args.draw_start} - {'end' if draw_end == -1 else draw_end}")
    print(f"Output: {out_path}")

    if args.draw_start > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, args.draw_start)

    frame_idx = args.draw_start
    start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if draw_end != -1 and frame_idx > draw_end:
            break

        draw_frame_number(frame, frame_idx)

        json_path = os.path.join(
            args.json_dir, f"{json_stem}_{frame_idx:06d}.json"
        )
        people = load_frame_json(json_path)
        visible_people = filter_people(
            people, args.id_type, args.mode, args.filter_values
        )
        for person in visible_people:
            id_value = person.get(args.id_type, -1)
            color = get_color_for_mode(id_value, args.mode)
            draw_person(frame, person, color, args.id_type, args.kpt_thr, debug_flags)

        writer.write(frame)

        if frame_idx % PROGRESS_INTERVAL_FRAMES == 0:
            if total_frames > 0:
                pct = frame_idx / total_frames * 100
                print(f"Processing frame {frame_idx:06d}/{total_frames} ({pct:.1f}%)")
            else:
                print(f"Processing frame {frame_idx:06d}/?")

        frame_idx += 1

    cap.release()
    writer.release()

    elapsed = time.time() - start_time
    fps_actual = frame_idx / elapsed if elapsed > 0 else 0.0
    print()
    print(f"Total frames: {frame_idx}")
    print(f"Processing time: {elapsed:.1f} sec ({fps_actual:.1f} fps)")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()
