"""pink → blue 動画変換ツール (feat-044)

入力動画のピンク領域を HSV 空間で青に置換した合成動画を出力する。
NDA により本物の青対象動画が入手不可のため、青色対応パイプライン (feat-045+) の検証用。
L2 変換: H -> target_h、S -> min(S * s_scale, s_max)、V 不変。
"""

import argparse
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np


# ---------------- Constants ----------------
# postprocess_pink_id.py の FIXED_HSV_RANGES と同期させる
DEFAULT_HSV_RANGES: list[tuple[tuple[int, int, int], tuple[int, int, int]]] = [
    ((0, 60, 80), (10, 255, 255)),
    ((140, 60, 80), (159, 255, 255)),
    ((160, 60, 80), (179, 255, 255)),
]
PROGRESS_INTERVAL_FRAMES: int = 3000


# ---------------- argparse type checkers ----------------
def _check_h(v: str) -> int:
    iv = int(v)
    if not (0 <= iv <= 179):
        raise argparse.ArgumentTypeError(f"target-h must be in [0, 179], got {iv}")
    return iv


def _check_scale(v: str) -> float:
    fv = float(v)
    if not (0.0 <= fv <= 1.0):
        raise argparse.ArgumentTypeError(f"s-scale must be in [0.0, 1.0], got {fv}")
    return fv


def _check_smax(v: str) -> int:
    iv = int(v)
    if not (0 <= iv <= 255):
        raise argparse.ArgumentTypeError(f"s-max must be in [0, 255], got {iv}")
    return iv


# ---------------- Pure functions ----------------
def build_pink_mask(
    hsv: np.ndarray,
    hsv_ranges: list[tuple[tuple[int, int, int], tuple[int, int, int]]],
) -> np.ndarray:
    mask_total = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lo, hi in hsv_ranges:
        m = cv2.inRange(hsv, np.array(lo, dtype=np.uint8), np.array(hi, dtype=np.uint8))
        mask_total = cv2.bitwise_or(mask_total, m)
    return mask_total > 0


def apply_blue_transform(
    hsv: np.ndarray,
    mask: np.ndarray,
    target_h: int,
    s_scale: float,
    s_max: int,
) -> np.ndarray:
    if not mask.any():
        return hsv
    hsv[mask, 0] = target_h
    s_orig = hsv[mask, 1].astype(np.int32)
    s_new = np.clip(s_orig * s_scale, 0, s_max).astype(np.uint8)
    hsv[mask, 1] = s_new
    return hsv


# ---------------- Main ----------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert pink regions in a video to blue (HSV-based)"
    )
    parser.add_argument("--input", required=True, type=str, help="Input video file")
    parser.add_argument("--out-dir", default="output", type=str, help="Output directory")
    parser.add_argument(
        "--target-h", type=_check_h, default=110,
        help="Target H value (0-179) after replacement (default: 110, blue center)",
    )
    parser.add_argument(
        "--s-scale", type=_check_scale, default=0.35,
        help="S compression factor (0.0-1.0). New S = min(S*s_scale, s_max) (default: 0.35)",
    )
    parser.add_argument(
        "--s-max", type=_check_smax, default=80,
        help="Maximum S after compression (0-255). (default: 80)",
    )
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.input)
    if not cap.isOpened():
        print(f"ERROR: Failed to open video: {args.input}", file=sys.stderr)
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if fps <= 0 or width <= 0 or height <= 0:
        print(
            f"ERROR: invalid video metadata (fps={fps}, size={width}x{height})",
            file=sys.stderr,
        )
        sys.exit(1)

    os.makedirs(args.out_dir, exist_ok=True)
    out_name = f"{Path(args.input).stem}_blue.mp4"
    out_path = os.path.join(args.out_dir, out_name)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

    print(f"Video: {args.input} ({total_frames} frames, {fps} fps, {width}x{height})")
    print(
        f"HSV transform: H -> {args.target_h}, S *= {args.s_scale} (max {args.s_max}), V kept"
    )
    print(f"Output: {out_path}")

    frame_idx = 0
    total_pink_pixels = 0
    total_pixels = 0
    start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = build_pink_mask(hsv, DEFAULT_HSV_RANGES)
        apply_blue_transform(hsv, mask, args.target_h, args.s_scale, args.s_max)
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        writer.write(bgr)

        total_pink_pixels += int(mask.sum())
        total_pixels += mask.size

        if frame_idx % PROGRESS_INTERVAL_FRAMES == 0:
            pct = frame_idx / total_frames * 100 if total_frames > 0 else 0.0
            print(f"Processing frame {frame_idx:06d}/{total_frames} ({pct:.1f}%)")

        frame_idx += 1

    cap.release()
    writer.release()

    elapsed = time.time() - start_time
    fps_actual = frame_idx / elapsed if elapsed > 0 else 0.0
    avg_ratio = total_pink_pixels / total_pixels if total_pixels > 0 else 0.0
    print()
    print(f"Total frames: {frame_idx}")
    print(f"Processing time: {elapsed:.1f} sec ({fps_actual:.1f} fps)")
    print(f"Average pink ratio: {avg_ratio*100:.2f}%")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()
