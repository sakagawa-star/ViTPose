"""Visualize tracking results with stable_id color coding."""

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


# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

def _generate_palette(n: int = 20) -> list[tuple[int, int, int]]:
    """HSV色相均等分割でn色のBGRパレットを生成する。"""
    palette = []
    for i in range(n):
        h = int(180 * i / n)  # OpenCV HSVのHは0-179
        hsv = np.array([[[h, 255, 255]]], dtype=np.uint8)
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        palette.append(tuple(int(c) for c in bgr[0, 0]))
    return palette


COLOR_PALETTE: list[tuple[int, int, int]] = _generate_palette(20)
GRAY = (128, 128, 128)


def get_color(stable_id: int) -> tuple[int, int, int]:
    """stable_idからBGR色を返す。"""
    if stable_id < 0:
        return GRAY
    return COLOR_PALETTE[stable_id % len(COLOR_PALETTE)]


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def draw_bbox_colored(
    img: np.ndarray,
    bbox: list[float],
    color: tuple[int, int, int],
    stable_id: int,
    thickness: int = 2,
) -> np.ndarray:
    """BBとstable_idテキストを描画する。"""
    x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)
    label = f"ID:{stable_id}"
    text_y = y1 - 8 if y1 - 8 > 0 else y1 + 20
    cv2.putText(img, label, (x1, text_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return img


def draw_halpe26_colored(
    img: np.ndarray,
    keypoints: np.ndarray,
    color: tuple[int, int, int],
    kpt_thr: float = 0.3,
) -> np.ndarray:
    """HALPE 26スケルトンを指定色で描画する。"""
    for i, j in HALPE26_SKELETON:
        if keypoints[i, 2] > kpt_thr and keypoints[j, 2] > kpt_thr:
            pt1 = (int(keypoints[i, 0]), int(keypoints[i, 1]))
            pt2 = (int(keypoints[j, 0]), int(keypoints[j, 1]))
            cv2.line(img, pt1, pt2, color, 2)

    for idx in range(26):
        if keypoints[idx, 2] > kpt_thr:
            x, y = int(keypoints[idx, 0]), int(keypoints[idx, 1])
            cv2.circle(img, (x, y), 4, color, -1)

    return img


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def detect_json_stem(json_dir: str) -> str:
    """json-dir内の最初のJSONファイルからstemを検出する。"""
    json_path = Path(json_dir)
    pattern = re.compile(r"^(.+)_\d{6}\.json$")
    for f in sorted(json_path.glob("*.json")):
        m = pattern.match(f.name)
        if m:
            return m.group(1)
    print(f"ERROR: No valid JSON files found in {json_dir}")
    sys.exit(1)


def load_frame_json(json_path: str) -> list[dict]:
    """1フレーム分のJSONを読み込む。"""
    if not os.path.exists(json_path):
        return []
    try:
        with open(json_path) as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print(f"WARNING: Failed to parse {json_path}, treating as 0 people")
        return []
    return data.get("people", [])


def filter_people(
    people: list[dict], target_ids: list[int] | None,
) -> list[dict]:
    """描画対象の人物をフィルタする。"""
    result = []
    for person in people:
        sid = person.get("stable_id", -1)
        if target_ids is None:
            result.append(person)
        else:
            if sid != -1 and sid in target_ids:
                result.append(person)
    return result


# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------

def build_output_path(args: argparse.Namespace) -> str:
    """出力ファイルパスを構築する。"""
    video_stem = Path(args.video).stem
    if args.ids is not None:
        ids_str = "_".join(str(i) for i in args.ids)
        filename = f"vis_tracking_{video_stem}_ids_{ids_str}.mp4"
    else:
        filename = f"vis_tracking_{video_stem}_all.mp4"
    return os.path.join(args.out_dir, filename)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """CLI引数をパースする。"""
    parser = argparse.ArgumentParser(
        description="Visualize tracking results with stable_id color coding")
    parser.add_argument("--video", type=str, required=True,
                        help="Input video path")
    parser.add_argument("--json-dir", type=str, required=True,
                        help="Directory of stable_id-annotated JSON files")
    parser.add_argument("--ids", type=int, nargs="+", default=None,
                        help="stable_ids to draw (omit for all)")
    parser.add_argument("--out-dir", type=str, default="output",
                        help="Output directory")
    parser.add_argument("--kpt-thr", type=float, default=0.3,
                        help="Keypoint confidence threshold (0.0-1.0)")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """エントリポイント。"""
    args = parse_args()

    # json-dir 存在チェック
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

    # 出力ディレクトリ自動作成
    os.makedirs(args.out_dir, exist_ok=True)

    # 出力パスを構築
    out_path = build_output_path(args)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

    # JSONファイル名のstemを取得
    json_stem = detect_json_stem(args.json_dir)

    mode = "filter" if args.ids is not None else "all"
    print(f"Video: {args.video} ({total_frames} frames, {fps} fps)")
    print(f"JSON dir: {args.json_dir} (stem: {json_stem})")
    print(f"Mode: {mode}, IDs: {args.ids}, kpt_thr: {args.kpt_thr}")

    start_time = time.time()
    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # JSONを読み込む
        json_path = os.path.join(
            args.json_dir, f"{json_stem}_{frame_idx:06d}.json")
        people = load_frame_json(json_path)

        # 描画対象をフィルタ
        targets = filter_people(people, args.ids)

        # 描画
        vis_frame = frame.copy()
        for person in targets:
            sid = person.get("stable_id", -1)
            color = get_color(sid)
            bbox = person.get("bbox")
            kpts_flat = person.get("pose_keypoints_2d", [])

            if bbox is not None and len(bbox) >= 4:
                draw_bbox_colored(vis_frame, bbox, color, sid)

            if len(kpts_flat) == 78:
                kpts = np.array(kpts_flat, dtype=np.float32).reshape(26, 3)
                draw_halpe26_colored(vis_frame, kpts, color, args.kpt_thr)

        writer.write(vis_frame)

        if frame_idx % 1000 == 0:
            print(f"Processing frame {frame_idx}/{total_frames} ...")
        frame_idx += 1

    cap.release()
    writer.release()

    elapsed = time.time() - start_time
    print(f"Done: {out_path} ({elapsed:.1f}s)")


if __name__ == "__main__":
    main()
