"""不一致フレーム可視化ツール (feat-047 FR-005〜FR-007).

compare_roi_modes.py が出力した disagreement.csv と元動画を入力に、
不一致フレームを目視確認するための PNG 静止画を出力する。

- bb モード選択 BB: 赤枠 (BGR=(0,0,255))
- keypoint-rect モード選択 BB: 青枠 (BGR=(255,0,0))
- 画像上部に frame_idx / disagreement_type / 各モードの bb_index, pink_ratio を表示
"""
from __future__ import annotations

import argparse
import ast
import csv
import os
import sys

import cv2


def _positive_int(s: str) -> int:
    v = int(s)
    if v < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {v}")
    return v


def _parse_bbox(s: str, label: str, fr_idx: int):
    if not s:
        return None
    try:
        v = ast.literal_eval(s)
        if not isinstance(v, list) or len(v) != 4:
            raise ValueError(f"expected list of 4, got {v!r}")
        return v
    except (ValueError, SyntaxError) as e:
        print(f"WARNING: failed to parse {label} bbox at frame {fr_idx}: {e}",
              file=sys.stderr)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, help="元動画ファイル")
    parser.add_argument("--csv", required=True, help="disagreement.csv パス")
    parser.add_argument("--out-dir", required=True, help="PNG 出力先ディレクトリ")
    parser.add_argument("--max-samples", type=_positive_int, default=50,
                        help="サンプル数上限 (>=1)。--all 時は無視")
    parser.add_argument("--all", action="store_true",
                        help="全件出力 (--max-samples を無視)")
    args = parser.parse_args()

    if not os.path.isfile(args.csv):
        print(f"ERROR: CSV not found: {args.csv}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(args.video):
        print(f"ERROR: video not found: {args.video}", file=sys.stderr)
        sys.exit(1)
    os.makedirs(args.out_dir, exist_ok=True)

    rows: list[dict] = []
    with open(args.csv) as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    original_row_count = len(rows)
    if not args.all and len(rows) > args.max_samples:
        step = len(rows) / args.max_samples
        indices = [int(i * step) for i in range(args.max_samples)]
        rows = [rows[i] for i in indices]

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"ERROR: failed to open video: {args.video}", file=sys.stderr)
        sys.exit(1)

    success_count = 0
    seek_fail_count = 0
    total = len(rows)

    for n, r in enumerate(rows):
        fr_idx = int(r["frame_idx"])
        cap.set(cv2.CAP_PROP_POS_FRAMES, fr_idx)
        ret, frame = cap.read()
        if not ret:
            seek_fail_count += 1
            print(f"WARNING: failed to seek frame {fr_idx}", file=sys.stderr)
            continue

        bb_bbox = _parse_bbox(r["bb_bbox"], "bb", fr_idx)
        kp_bbox = _parse_bbox(r["kp_bbox"], "kp", fr_idx)
        bb_bbox_i = tuple(int(round(v)) for v in bb_bbox) if bb_bbox is not None else None
        kp_bbox_i = tuple(int(round(v)) for v in kp_bbox) if kp_bbox is not None else None

        dtype = r["disagreement_type"]
        if dtype in ("both_selected_different", "only_bb") and bb_bbox_i is not None:
            cv2.rectangle(frame, (bb_bbox_i[0], bb_bbox_i[1]),
                          (bb_bbox_i[2], bb_bbox_i[3]), (0, 0, 255), 2)  # 赤 = bb
        if dtype in ("both_selected_different", "only_kp") and kp_bbox_i is not None:
            cv2.rectangle(frame, (kp_bbox_i[0], kp_bbox_i[1]),
                          (kp_bbox_i[2], kp_bbox_i[3]), (255, 0, 0), 2)  # 青 = kp

        lines = [f"Frame: {fr_idx:06d} | Type: {dtype}"]
        if r["bb_selected_bb_index"]:
            lines.append(
                f"BB: idx={r['bb_selected_bb_index']} ratio={r['bb_pink_ratio']}"
            )
        if r["kp_selected_bb_index"]:
            lines.append(
                f"KP: idx={r['kp_selected_bb_index']} ratio={r['kp_pink_ratio']}"
            )
        for i, line in enumerate(lines):
            org = (10, 25 + 25 * i)
            cv2.putText(frame, line, org, cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (0, 0, 0), 3)
            cv2.putText(frame, line, org, cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (255, 255, 255), 1)

        out_path = os.path.join(args.out_dir, f"frame_{fr_idx:06d}_disagree.png")
        cv2.imwrite(out_path, frame)
        success_count += 1

        if (n + 1) % 10 == 0:
            print(f"Processing frame {n + 1}/{total}")

    cap.release()

    print(f"Total disagreement frames in CSV: {original_row_count}")
    print(f"Samples to process: {total}")
    print(f"PNGs successfully saved: {success_count}")
    print(f"Seek failures: {seek_fail_count}")
    print(f"Output: {args.out_dir}/")


if __name__ == "__main__":
    main()
