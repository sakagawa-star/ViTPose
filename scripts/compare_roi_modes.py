"""ROI モード比較ツール (feat-047 FR-001〜FR-004).

postprocess_pink_id.py を --roi-mode bb と --roi-mode keypoint-rect の
2 種類で実行した結果 JSON ディレクトリを比較し、

- alpha1_scatter.png: pink_id=1 人物の pink_ratio 散布図 (bb vs keypoint-rect)
- disagreement.csv:    pink_id=1 選択が不一致なフレームの一覧

を出力する。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


PATTERN = re.compile(r"_(\d{6})\.json$")


def load_pink_id_results(json_dir: str) -> dict[int, dict]:
    """JSON ディレクトリから {frame_idx: {bb_index, pink_ratio, bbox}} を返す。

    pink_id == 1 の人物が存在すればその値、なければ全フィールド None。
    """
    result: dict[int, dict] = {}
    for fname in os.listdir(json_dir):
        m = PATTERN.search(fname)
        if not m:
            continue
        frame_idx = int(m.group(1))
        with open(os.path.join(json_dir, fname)) as f:
            data = json.load(f)
        pink_person = next(
            (p for p in data.get("people", []) if p.get("pink_id") == 1),
            None,
        )
        if pink_person is None:
            result[frame_idx] = {"bb_index": None, "pink_ratio": None, "bbox": None}
        else:
            result[frame_idx] = {
                "bb_index": pink_person.get("bb_index"),
                "pink_ratio": pink_person.get("pink_ratio"),
                "bbox": pink_person.get("bbox"),
            }
    return result


def classify_disagreement(bb_idx, kp_idx) -> Optional[str]:
    """不一致タイプ分類。一致 / both_none は None を返す。"""
    if bb_idx is None and kp_idx is None:
        return None  # both_none, CSV に含めない
    if bb_idx is None:
        return "only_kp"
    if kp_idx is None:
        return "only_bb"
    if bb_idx != kp_idx:
        return "both_selected_different"
    return None  # 同じ bb_index = 一致


def _bbox_str(bbox) -> str:
    if bbox is None:
        return ""
    return "[" + ", ".join(f"{round(v, 2)}" for v in bbox) + "]"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bb-json-dir", required=True,
                        help="bb モード JSON ディレクトリ")
    parser.add_argument("--kp-json-dir", required=True,
                        help="keypoint-rect モード JSON ディレクトリ")
    parser.add_argument("--out-dir", required=True,
                        help="alpha1_scatter.png / disagreement.csv の出力先")
    args = parser.parse_args()

    for d in [args.bb_json_dir, args.kp_json_dir]:
        if not os.path.isdir(d):
            print(f"ERROR: JSON directory not found: {d}", file=sys.stderr)
            sys.exit(1)
    os.makedirs(args.out_dir, exist_ok=True)

    bb_results = load_pink_id_results(args.bb_json_dir)
    kp_results = load_pink_id_results(args.kp_json_dir)

    common_frames = sorted(set(bb_results) & set(kp_results))
    only_bb_frames = set(bb_results) - set(kp_results)
    only_kp_frames = set(kp_results) - set(bb_results)
    if only_bb_frames or only_kp_frames:
        print(
            f"WARNING: bb-only frames={len(only_bb_frames)}, "
            f"kp-only frames={len(only_kp_frames)}"
        )

    # FR-002: α-1 散布図
    xs: list[float] = []
    ys: list[float] = []
    both_none_excluded = 0
    for f in common_frames:
        bb_r = bb_results[f]["pink_ratio"]
        kp_r = kp_results[f]["pink_ratio"]
        if bb_r is None and kp_r is None:
            both_none_excluded += 1
            continue
        xs.append(bb_r if bb_r is not None else 0.0)
        ys.append(kp_r if kp_r is not None else 0.0)

    fig, ax = plt.subplots(figsize=(10, 10), dpi=80)
    ax.scatter(xs, ys, s=4, alpha=0.3, color="navy")
    ax.plot([0, 1], [0, 1], "k--", linewidth=1, label="y=x")
    ax.set_xlim(0, 1.0)
    ax.set_ylim(0, 1.0)
    ax.set_xlabel("bb mode pink_ratio")
    ax.set_ylabel("keypoint-rect mode pink_ratio")
    ax.set_title(
        f"alpha-1 scatter: bb vs keypoint-rect "
        f"(plotted={len(xs)}, excluded both_none={both_none_excluded})"
    )
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    scatter_path = os.path.join(args.out_dir, "alpha1_scatter.png")
    plt.savefig(scatter_path)
    plt.close(fig)

    # FR-003: 不一致 CSV
    counts = {"both_selected_different": 0, "only_bb": 0,
              "only_kp": 0, "both_none": 0}
    csv_path = os.path.join(args.out_dir, "disagreement.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "frame_idx", "disagreement_type",
            "bb_selected_bb_index", "bb_pink_ratio", "bb_bbox",
            "kp_selected_bb_index", "kp_pink_ratio", "kp_bbox",
        ])
        for fr_idx in common_frames:
            bb = bb_results[fr_idx]
            kp = kp_results[fr_idx]
            bb_idx = bb["bb_index"]
            kp_idx = kp["bb_index"]
            if bb_idx is None and kp_idx is None:
                counts["both_none"] += 1
                continue
            if bb_idx is None:
                counts["only_kp"] += 1
            elif kp_idx is None:
                counts["only_bb"] += 1
            elif bb_idx != kp_idx:
                counts["both_selected_different"] += 1
            else:
                continue  # 一致
            dtype = classify_disagreement(bb_idx, kp_idx)
            assert dtype is not None
            writer.writerow([
                fr_idx, dtype,
                bb_idx if bb_idx is not None else "",
                f"{bb['pink_ratio']:.4f}" if bb["pink_ratio"] is not None else "",
                _bbox_str(bb["bbox"]),
                kp_idx if kp_idx is not None else "",
                f"{kp['pink_ratio']:.4f}" if kp["pink_ratio"] is not None else "",
                _bbox_str(kp["bbox"]),
            ])

    # FR-004: サマリ
    print(f"Total frames processed: {len(common_frames)}")
    print("Disagreement counts: " +
          ", ".join(f"{k}={v}" for k, v in counts.items()))
    print(f"Output: {scatter_path}")
    print(f"Output: {csv_path}")


if __name__ == "__main__":
    main()
