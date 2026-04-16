"""pink_track_id 時系列可視化グラフ (feat-037)

feat-036 postprocess_patient_id.py の出力 JSON を入力とし、
pink_track_id の時系列変化を 5 パネル構成の PNG グラフとして出力する。

パネル構成:
  1. pink_track_id=1 の有無（二値タイムライン）
  2. BB 数の内訳（pink_track_id 値別）
  3. pink_track_id=1 BB の track_id 推移
  4. pink_track_id=1 BB の bbox_score 推移
  5. pink_id=1 の有無（二値タイムライン、パネル1との比較用）
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ---------------- データ構造 ----------------
@dataclass
class TimelineData:
    frames: list[int] = field(default_factory=list)
    has_patient: list[int] = field(default_factory=list)
    has_pink_id: list[int] = field(default_factory=list)
    count_patient: list[int] = field(default_factory=list)
    count_not_patient: list[int] = field(default_factory=list)
    count_duplicate: list[int] = field(default_factory=list)
    patient_track_ids: list[int | None] = field(default_factory=list)
    patient_bbox_scores: list[float | None] = field(default_factory=list)


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
def collect_timeline_data(
    frame_to_json: dict[int, tuple[str, dict]],
) -> TimelineData:
    """全フレームから描画用のタイムラインデータを収集する (FR-001 後処理)。"""
    data = TimelineData()

    for frame_idx in sorted(frame_to_json.keys()):
        _, content_dict = frame_to_json[frame_idx]
        people = content_dict.get("people", [])

        data.frames.append(frame_idx)

        n_patient = 0
        n_not_patient = 0
        n_duplicate = 0
        p_track_id: int | None = None
        p_bbox_score: float | None = None
        found_pink_id = False

        for person in people:
            ptid = person.get("pink_track_id")
            # pink_track_id が未付与（None）の BB は non-patient として扱う
            if ptid == 1:
                n_patient += 1
                p_track_id = person.get("track_id")
                score = person.get("bbox_score")
                if isinstance(score, (int, float)) and not isinstance(score, bool):
                    p_bbox_score = float(score)
            elif ptid == -2:
                n_duplicate += 1
            else:
                n_not_patient += 1
            if person.get("pink_id") == 1:
                found_pink_id = True

        data.has_patient.append(1 if n_patient > 0 else 0)
        data.has_pink_id.append(1 if found_pink_id else 0)
        data.count_patient.append(n_patient)
        data.count_not_patient.append(n_not_patient)
        data.count_duplicate.append(n_duplicate)
        data.patient_track_ids.append(p_track_id)
        data.patient_bbox_scores.append(p_bbox_score)

    return data


# ---------------- 描画関数 ----------------
def plot_patient_presence(ax: plt.Axes, data: TimelineData) -> None:
    """パネル 1: pink_track_id=1 の有無 (FR-002)。"""
    ax.fill_between(data.frames, data.has_patient, step="mid", alpha=0.7, color="green")
    ax.set_ylabel("Patient\n(0/1)")
    ax.set_ylim(-0.1, 1.3)


def plot_bb_count_breakdown(ax: plt.Axes, data: TimelineData) -> None:
    """パネル 2: BB 数の内訳 (FR-003)。"""
    ax.plot(data.frames, data.count_patient, linewidth=0.5, color="green", label="=1 (patient)")
    ax.plot(data.frames, data.count_not_patient, linewidth=0.5, color="gray", label="=-1 (not patient)")
    ax.plot(data.frames, data.count_duplicate, linewidth=0.5, color="orange", label="=-2 (duplicate)")
    ax.set_ylabel("BB count")
    ax.legend(loc="upper right", fontsize="small")


def plot_patient_track_id(ax: plt.Axes, data: TimelineData) -> None:
    """パネル 3: pink_track_id=1 BB の track_id 推移 (FR-004)。"""
    xs = [f for f, t in zip(data.frames, data.patient_track_ids) if t is not None]
    ys = [t for t in data.patient_track_ids if t is not None]
    if xs:
        ax.scatter(xs, ys, s=1, color="blue", alpha=0.5)
    ax.set_ylabel("track_id\n(patient)")


def plot_patient_bbox_score(ax: plt.Axes, data: TimelineData) -> None:
    """パネル 4: pink_track_id=1 BB の bbox_score 推移 (FR-005)。"""
    xs = [f for f, s in zip(data.frames, data.patient_bbox_scores) if s is not None]
    ys = [s for s in data.patient_bbox_scores if s is not None]
    if xs:
        ax.scatter(xs, ys, s=1, color="purple", alpha=0.5)
    ax.set_ylabel("bbox_score\n(patient)")
    ax.set_ylim(0.0, 1.05)


def plot_pink_id_presence(ax: plt.Axes, data: TimelineData) -> None:
    """パネル 5: pink_id=1 の有無 (FR-006)。"""
    ax.fill_between(data.frames, data.has_pink_id, step="mid", alpha=0.7, color="hotpink")
    ax.set_ylabel("pink_id=1\n(0/1)")
    ax.set_ylim(-0.1, 1.3)
    ax.set_xlabel("Frame index")


# ---------------- Main ----------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot pink_track_id timeline from HALPE 26 JSON"
    )
    parser.add_argument(
        "--json-dir", required=True, help="Input JSON directory (pink_track_id assigned)"
    )
    parser.add_argument(
        "--out-path", required=True, help="Output PNG file path"
    )
    args = parser.parse_args()

    frame_to_json = load_json_frames(args.json_dir)
    print(f"Loaded {len(frame_to_json)} frames from JSON")

    data = collect_timeline_data(frame_to_json)
    print(f"Collected timeline data for {len(data.frames)} frames")

    fig, axes = plt.subplots(5, 1, figsize=(16, 12), sharex=True)

    plot_patient_presence(axes[0], data)
    plot_bb_count_breakdown(axes[1], data)
    plot_patient_track_id(axes[2], data)
    plot_patient_bbox_score(axes[3], data)
    plot_pink_id_presence(axes[4], data)

    dir_name = os.path.basename(os.path.normpath(args.json_dir))
    axes[0].set_title(
        f"pink_track_id timeline — {dir_name} ({len(data.frames)} frames)"
    )

    plt.tight_layout()
    out_dir = os.path.dirname(os.path.abspath(args.out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    fig.savefig(args.out_path, dpi=150)
    plt.close(fig)
    print(f"Saved: {args.out_path}")


if __name__ == "__main__":
    main()
