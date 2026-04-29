"""pink_ratio 時系列可視化グラフ (feat-040)

feat-039 改修済み postprocess_pink_id.py の出力 JSON を入力とし、
各フレームの全 BB の pink_ratio を 4 パネル構成の PNG グラフとして出力する。

パネル構成:
  1. 全 BB の pink_ratio 散布図 + 閾値ライン (MIN_PINK_RATIO)
  2. pink_id=1 の有無（二値タイムライン）
  3. フレームごとの BB 数（pink_id=1 / -1 かつ候補 / -1 かつ非候補 の 3 系列）
  4. 「選択 BB ratio − 次点 BB ratio」差分（負値含む際どい差分は赤背景帯で強調）
"""

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from postprocess_pink_id import MIN_PINK_RATIO  # noqa: E402


CLOSE_MARGIN_THRESHOLD: float = 0.05


# ---------------- データ構造 ----------------
@dataclass
class TimelineData:
    frames: list[int] = field(default_factory=list)

    # Panel 1 用: 全 BB のフラットリスト
    scatter_frames_selected: list[int] = field(default_factory=list)
    scatter_ratios_selected: list[float] = field(default_factory=list)
    scatter_frames_candidate: list[int] = field(default_factory=list)
    scatter_ratios_candidate: list[float] = field(default_factory=list)
    scatter_frames_noncand: list[int] = field(default_factory=list)
    scatter_ratios_noncand: list[float] = field(default_factory=list)

    # Panel 2 用
    has_pink_id: list[int] = field(default_factory=list)

    # Panel 3 用
    count_selected: list[int] = field(default_factory=list)
    count_candidate_other: list[int] = field(default_factory=list)
    count_non_candidate: list[int] = field(default_factory=list)

    # Panel 4 用
    selected_ratios: list[float | None] = field(default_factory=list)
    runnerup_ratios: list[float | None] = field(default_factory=list)


# ---------------- I/O ----------------
def load_json_frames(json_dir: str) -> dict[int, tuple[str, dict]]:
    """JSON ディレクトリから全フレームの生 dict を読み込む (FR-001)。"""
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


# ---------------- データ収集 ----------------
def extract_runner_up_ratio(people: list[dict]) -> float | None:
    """全 BB の pink_ratio を降順ソートし、2 位の値を返す (FR-006、案 a-2)。

    BB が 0–1 個のフレームでは None を返す。
    pink_ratio キー欠落の BB は 0.0 として扱う（後方互換）。
    """
    if len(people) < 2:
        return None
    ratios = [p.get("pink_ratio", 0.0) for p in people]
    ratios_sorted = sorted(ratios, reverse=True)
    return ratios_sorted[1]


def collect_timeline_data(
    frame_to_json: dict[int, tuple[str, dict]],
    frame_start: int,
    frame_end: int,
) -> TimelineData:
    """全フレームから描画用のタイムラインデータを収集する (FR-001)。

    frame_end は -1 のときは max(frame_to_json.keys()) に解決済みとして渡す。
    """
    data = TimelineData()

    for frame_idx in sorted(frame_to_json.keys()):
        if frame_idx < frame_start or frame_idx > frame_end:
            continue

        _, content_dict = frame_to_json[frame_idx]
        people = content_dict.get("people", [])

        data.frames.append(frame_idx)

        n_selected = 0
        n_candidate_other = 0
        n_non_candidate = 0
        selected_ratio: float | None = None

        for person in people:
            ratio = person.get("pink_ratio", 0.0)
            pid = person.get("pink_id", -1)
            if pid == 1:
                n_selected += 1
                selected_ratio = ratio
                data.scatter_frames_selected.append(frame_idx)
                data.scatter_ratios_selected.append(ratio)
            elif ratio >= MIN_PINK_RATIO:
                n_candidate_other += 1
                data.scatter_frames_candidate.append(frame_idx)
                data.scatter_ratios_candidate.append(ratio)
            else:
                n_non_candidate += 1
                data.scatter_frames_noncand.append(frame_idx)
                data.scatter_ratios_noncand.append(ratio)

        data.has_pink_id.append(1 if n_selected > 0 else 0)
        data.count_selected.append(n_selected)
        data.count_candidate_other.append(n_candidate_other)
        data.count_non_candidate.append(n_non_candidate)
        data.selected_ratios.append(selected_ratio)
        data.runnerup_ratios.append(extract_runner_up_ratio(people))

    return data


def _group_consecutive(values: list[int]) -> list[tuple[int, int]]:
    """昇順整数リストを「差 1 で連結、差 2 以上で分割」した区間にまとめる。

    例: [5, 6, 7, 10, 11, 20] -> [(5,7), (10,11), (20,20)]
    単独要素は (v, v) として返す。
    """
    if not values:
        return []
    result: list[tuple[int, int]] = []
    start = values[0]
    prev = values[0]
    for v in values[1:]:
        if v - prev == 1:
            prev = v
        else:
            result.append((start, prev))
            start = v
            prev = v
    result.append((start, prev))
    return result


# ---------------- 描画関数 ----------------
def plot_ratio_scatter(ax: plt.Axes, data: TimelineData) -> None:
    """Panel 1: 全 BB の pink_ratio 散布図 + 閾値ライン (FR-002)。"""
    ax.scatter(data.scatter_frames_noncand, data.scatter_ratios_noncand,
               s=1, c="lightgray", alpha=0.2,
               label=f"non-candidate (<{MIN_PINK_RATIO})")
    ax.scatter(data.scatter_frames_candidate, data.scatter_ratios_candidate,
               s=2, c="black", alpha=0.4,
               label=f"candidate (>={MIN_PINK_RATIO}, pink_id=-1)")
    ax.scatter(data.scatter_frames_selected, data.scatter_ratios_selected,
               s=4, c="magenta", alpha=0.7,
               label="selected (pink_id=1)")
    ax.axhline(MIN_PINK_RATIO, color="red", linestyle="--",
               linewidth=0.7, label=f"threshold={MIN_PINK_RATIO}")
    ax.set_ylabel("pink_ratio")
    ax.set_ylim(0.0, 1.05)
    ax.legend(loc="upper right", fontsize="small")


def plot_pink_id_presence(ax: plt.Axes, data: TimelineData) -> None:
    """Panel 2: pink_id=1 の有無タイムライン (FR-003)。"""
    ax.fill_between(data.frames, data.has_pink_id,
                    step="mid", color="hotpink", alpha=0.7)
    ax.set_ylabel("pink_id=1\n(0/1)")
    ax.set_ylim(-0.1, 1.3)


def plot_bb_count_breakdown(ax: plt.Axes, data: TimelineData) -> None:
    """Panel 3: フレームごとの BB 数 (FR-004)。"""
    ax.plot(data.frames, data.count_selected,
            linewidth=0.5, color="magenta", label="pink_id=1")
    ax.plot(data.frames, data.count_candidate_other,
            linewidth=0.5, color="black",
            label=f"pink_id=-1, ratio>={MIN_PINK_RATIO}")
    ax.plot(data.frames, data.count_non_candidate,
            linewidth=0.5, color="gray",
            label=f"pink_id=-1, ratio<{MIN_PINK_RATIO}")
    ax.set_ylabel("BB count")
    ax.legend(loc="upper right", fontsize="small")


def plot_selected_minus_runnerup(ax: plt.Axes, data: TimelineData) -> int:
    """Panel 4: 選択 BB と次点 BB の差分 (FR-005)。

    Returns:
        際どい差分 (selected - runner_up < CLOSE_MARGIN_THRESHOLD) のフレーム数。
    """
    diffs_x: list[int] = []
    diffs_y: list[float] = []
    close_x: list[int] = []
    for f, s, r in zip(data.frames, data.selected_ratios, data.runnerup_ratios):
        if s is None or r is None:
            continue
        d = s - r
        diffs_x.append(f)
        diffs_y.append(d)
        if d < CLOSE_MARGIN_THRESHOLD:
            close_x.append(f)

    for x_start, x_end in _group_consecutive(close_x):
        ax.axvspan(x_start - 0.5, x_end + 0.5, color="red", alpha=0.15)

    ax.scatter(diffs_x, diffs_y, s=2, c="blue", alpha=0.5)
    ax.axhline(0.0, color="black", linestyle="--",
               linewidth=0.5, alpha=0.5)
    ax.set_ylabel("selected − runner-up\nratio")
    ax.set_ylim(-0.5, 1.05)
    ax.set_xlabel("Frame index")
    return len(close_x)


# ---------------- Main ----------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot pink_ratio timeline from HALPE 26 JSON (feat-040)"
    )
    parser.add_argument(
        "--json-dir", required=True,
        help="Input JSON directory (pink_id / pink_ratio assigned)",
    )
    parser.add_argument(
        "--out-path", required=True, help="Output PNG file path"
    )
    parser.add_argument(
        "--frame-start", type=int, default=0,
        help="Frame number (6-digit suffix in JSON filename) "
             "to start drawing. Default: 0",
    )
    parser.add_argument(
        "--frame-end", type=int, default=-1,
        help="Frame number (6-digit suffix in JSON filename) "
             "to end drawing. -1 = max frame in input. Default: -1",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.json_dir):
        print(f"ERROR: JSON directory not found: {args.json_dir}")
        sys.exit(1)

    if args.frame_end != -1 and args.frame_end < args.frame_start:
        print(
            f"ERROR: --frame-end ({args.frame_end}) < "
            f"--frame-start ({args.frame_start})"
        )
        sys.exit(1)

    start_time = time.time()
    frame_to_json = load_json_frames(args.json_dir)
    n_total = len(frame_to_json)
    print(f"Loaded {n_total} frames from JSON")

    frame_end_resolved = (
        max(frame_to_json.keys()) if args.frame_end == -1 else args.frame_end
    )
    print(
        f"Draw range: {args.frame_start} - {frame_end_resolved}"
    )

    data = collect_timeline_data(
        frame_to_json, args.frame_start, frame_end_resolved
    )
    n_drawn = len(data.frames)
    n_with_pink = sum(data.has_pink_id)
    print(f"Frames drawn: {n_drawn}")
    print(f"Frames with pink_id=1: {n_with_pink}")

    fig, axes = plt.subplots(4, 1, figsize=(16, 12), sharex=True)
    plot_ratio_scatter(axes[0], data)
    plot_pink_id_presence(axes[1], data)
    plot_bb_count_breakdown(axes[2], data)
    n_close = plot_selected_minus_runnerup(axes[3], data)
    print(
        f"Frames with close margin "
        f"(selected − runner-up < {CLOSE_MARGIN_THRESHOLD}): {n_close}"
    )

    dir_name = os.path.basename(os.path.normpath(args.json_dir))
    axes[0].set_title(
        f"pink_ratio timeline — {dir_name} "
        f"({n_drawn} frames drawn / {n_total} total)"
    )

    plt.tight_layout()
    out_dir = os.path.dirname(os.path.abspath(args.out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    fig.savefig(args.out_path, dpi=150)
    plt.close(fig)

    elapsed = time.time() - start_time
    print(f"Saved: {args.out_path}")
    print(f"Processing time: {elapsed:.1f} sec")


if __name__ == "__main__":
    main()
