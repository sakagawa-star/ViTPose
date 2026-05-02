"""feat-044 不具合調査用: ピンク服 vs 肌の HSV 分離可能性を判定する。

investigation.md §1.3.7-§1.3.10 に従い、
- 候補フレームから条件を満たすものを選定
- ROI-A (鼻パッチ=肌)、ROI-B (胴体内接矩形中央 50%=服) を抽出
- HSV 統計を集計、円環距離・重なり率を計算
- 仮説 A / B / GRAY を判定
- 散布図・H ヒストグラムを PNG 保存
"""

import argparse
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


# HALPE 26 keypoint index
NOSE = 0
LSHOULDER = 5
RSHOULDER = 6
LHIP = 11
RHIP = 12

KP_CONF_MIN = 0.3
BBOX_SCORE_MIN = 0.7
TORSO_AREA_MIN = 1000


def load_frame_json(json_dir: str, video_stem: str, frame_idx: int) -> dict | None:
    p = os.path.join(json_dir, f"{video_stem}_{frame_idx:06d}.json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def find_pink_person(people: list[dict]) -> dict | None:
    for p in people:
        if p.get("pink_id") == 1:
            return p
    return None


def get_kpts(person: dict) -> np.ndarray | None:
    kpts = person.get("pose_keypoints_2d", [])
    if len(kpts) < 26 * 3:
        return None
    return np.array(kpts).reshape(26, 3)


def select_sample_frames(
    video_path: str,
    json_dir: str,
    candidates: list[int],
    tolerance: int,
    min_samples: int,
    max_samples: int,
) -> list[int]:
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    video_stem = Path(video_path).stem
    selected: list[int] = []
    for c in candidates:
        for delta in range(0, tolerance + 1):
            for sign in (1, -1) if delta > 0 else (1,):
                fi = c + sign * delta
                if fi < 0 or fi >= total:
                    continue
                if fi in selected:
                    continue
                d = load_frame_json(json_dir, video_stem, fi)
                if d is None:
                    continue
                p = find_pink_person(d.get("people", []))
                if p is None:
                    continue
                if p.get("bbox_score", 0) < BBOX_SCORE_MIN:
                    continue
                kpts = get_kpts(p)
                if kpts is None:
                    continue
                conf_ok = all(
                    kpts[i, 2] >= KP_CONF_MIN
                    for i in (NOSE, LSHOULDER, RSHOULDER, LHIP, RHIP)
                )
                if not conf_ok:
                    continue
                xs = kpts[[LSHOULDER, RSHOULDER], 0]
                ys = kpts[[LSHOULDER, RSHOULDER, LHIP, RHIP], 1]
                w = float(xs.max() - xs.min())
                h = float(ys.max() - ys.min())
                if w * h < TORSO_AREA_MIN:
                    continue
                selected.append(fi)
                break
            else:
                continue
            break
        if len(selected) >= max_samples:
            break
    selected.sort()
    return selected[:max_samples]


def get_frame(video_path: str, frame_idx: int) -> np.ndarray | None:
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return None
    return frame


def extract_roi_a_skin(frame_bgr: np.ndarray, kpts: np.ndarray, patch: int) -> np.ndarray:
    nx, ny = int(kpts[NOSE, 0]), int(kpts[NOSE, 1])
    half = patch // 2
    H, W = frame_bgr.shape[:2]
    x1 = max(0, nx - half)
    y1 = max(0, ny - half)
    x2 = min(W, nx + half)
    y2 = min(H, ny + half)
    if x2 <= x1 or y2 <= y1:
        return np.empty((0, 3), dtype=np.uint8)
    patch_bgr = frame_bgr[y1:y2, x1:x2]
    return cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2HSV).reshape(-1, 3)


def extract_roi_b_torso_raw(
    frame_bgr: np.ndarray, kpts: np.ndarray, shrink: float
) -> np.ndarray:
    xs = kpts[[LSHOULDER, RSHOULDER], 0]
    ys = kpts[[LSHOULDER, RSHOULDER, LHIP, RHIP], 1]
    x_min0, x_max0 = float(xs.min()), float(xs.max())
    y_min0, y_max0 = float(ys.min()), float(ys.max())
    cx = (x_min0 + x_max0) / 2
    cy = (y_min0 + y_max0) / 2
    w = x_max0 - x_min0
    h = y_max0 - y_min0
    half_factor = shrink / 2
    x1 = int(round(cx - w * half_factor))
    y1 = int(round(cy - h * half_factor))
    x2 = int(round(cx + w * half_factor))
    y2 = int(round(cy + h * half_factor))
    H, W = frame_bgr.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(W, x2), min(H, y2)
    if x2 <= x1 or y2 <= y1:
        return np.empty((0, 3), dtype=np.uint8)
    bgr = frame_bgr[y1:y2, x1:x2]
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).reshape(-1, 3)


def in_h_band(h: np.ndarray, lo: int, hi: int) -> np.ndarray:
    """円環 H 帯への該当判定。lo > hi は H=179-0 をまたぐ区間として扱う。"""
    if lo <= hi:
        return (h >= lo) & (h <= hi)
    return (h >= lo) | (h <= hi)


def filter_skin_h_band(
    roi_b_raw: np.ndarray, h_skin_lo: int, h_skin_hi: int
) -> np.ndarray:
    if roi_b_raw.size == 0:
        return roi_b_raw
    skin_mask = in_h_band(roi_b_raw[:, 0], h_skin_lo, h_skin_hi)
    return roi_b_raw[~skin_mask]


def hue_circular_distance(h1: float, h2: float) -> float:
    d = abs(float(h1) - float(h2))
    return min(d, 180.0 - d)


def compute_h_overlap_ratio(
    roi_b_raw: np.ndarray, h_skin_lo: int, h_skin_hi: int
) -> float:
    if roi_b_raw.size == 0:
        return 0.0
    in_band = in_h_band(roi_b_raw[:, 0], h_skin_lo, h_skin_hi)
    return float(in_band.sum()) / float(len(roi_b_raw))


def compute_stats(hsv_pixels: np.ndarray) -> dict:
    if hsv_pixels.size == 0:
        return {k: 0.0 for k in ["H_med", "H_p25", "H_p75", "H_mean",
                                  "S_med", "S_p25", "S_p75", "S_mean",
                                  "V_med", "V_p25", "V_p75", "V_mean", "n"]}
    H, S, V = hsv_pixels[:, 0], hsv_pixels[:, 1], hsv_pixels[:, 2]
    return {
        "n": int(len(hsv_pixels)),
        "H_med": float(np.median(H)), "H_p25": float(np.percentile(H, 25)),
        "H_p75": float(np.percentile(H, 75)), "H_mean": float(H.mean()),
        "S_med": float(np.median(S)), "S_p25": float(np.percentile(S, 25)),
        "S_p75": float(np.percentile(S, 75)), "S_mean": float(S.mean()),
        "V_med": float(np.median(V)), "V_p25": float(np.percentile(V, 25)),
        "V_p75": float(np.percentile(V, 75)), "V_mean": float(V.mean()),
    }


def classify_hypothesis(
    h_diff: float, overlap: float,
    h_diff_a: float, h_diff_b: float,
    overlap_a: float, overlap_b: float,
) -> tuple[str, list[str]]:
    a_cond = (h_diff >= h_diff_a) and (overlap < overlap_a)
    b_cond = (h_diff < h_diff_b) or (overlap >= overlap_b)
    notes = []
    notes.append(f"A condition (h_diff>={h_diff_a} AND overlap<{overlap_a}): {a_cond}")
    notes.append(f"B condition (h_diff<{h_diff_b} OR overlap>={overlap_b}): {b_cond}")
    if a_cond and b_cond:
        return "GRAY", notes + ["A and B both satisfied (contradiction) -> GRAY"]
    if a_cond:
        return "A", notes
    if b_cond:
        return "B", notes
    return "GRAY", notes + ["neither A nor B satisfied -> GRAY"]


def plot_scatter(
    roi_a: np.ndarray, roi_b_raw: np.ndarray, out_path: str
) -> None:
    fig, ax = plt.subplots(figsize=(12, 8))
    if roi_b_raw.size:
        ax.scatter(roi_b_raw[:, 0], roi_b_raw[:, 1], s=2, c="blue",
                   alpha=0.3, label=f"ROI-B torso (n={len(roi_b_raw)})")
    if roi_a.size:
        ax.scatter(roi_a[:, 0], roi_a[:, 1], s=8, c="red",
                   alpha=0.6, label=f"ROI-A skin (n={len(roi_a)})")
    ax.set_xlabel("H (0-179)")
    ax.set_ylabel("S (0-255)")
    ax.set_xlim(0, 180)
    ax.set_ylim(0, 256)
    ax.set_title("Hue-Saturation scatter: ROI-A skin vs ROI-B torso (raw)")
    ax.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=80)
    plt.close()


def plot_h_histograms(
    roi_a: np.ndarray, roi_b_raw: np.ndarray, roi_b_filt: np.ndarray, out_path: str
) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    if roi_a.size:
        axes[0].hist(roi_a[:, 0], bins=18, range=(0, 180), color="red")
    axes[0].set_title(f"ROI-A skin H (n={len(roi_a)})")
    axes[0].set_ylabel("pixels")
    if roi_b_raw.size:
        axes[1].hist(roi_b_raw[:, 0], bins=18, range=(0, 180), color="blue")
    axes[1].set_title(f"ROI-B torso raw H (n={len(roi_b_raw)})")
    axes[1].set_ylabel("pixels")
    if roi_b_filt.size:
        axes[2].hist(roi_b_filt[:, 0], bins=18, range=(0, 180), color="cyan")
    axes[2].set_title(f"ROI-B torso filtered (skin H excluded) H (n={len(roi_b_filt)})")
    axes[2].set_xlabel("H (0-179)")
    axes[2].set_ylabel("pixels")
    plt.tight_layout()
    plt.savefig(out_path, dpi=80)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnose pink-vs-skin HSV separability for feat-044"
    )
    parser.add_argument("--video", required=True, type=str)
    parser.add_argument("--json-dir", required=True, type=str)
    parser.add_argument("--out-dir", required=True, type=str)
    parser.add_argument("--candidate-frames", type=int, nargs="+",
                        default=[200, 300, 400, 500, 600, 700, 800])
    parser.add_argument("--frame-tolerance", type=int, default=20)
    parser.add_argument("--min-samples", type=int, default=5)
    parser.add_argument("--max-samples", type=int, default=10)
    parser.add_argument("--skin-patch-size", type=int, default=8)
    parser.add_argument("--torso-shrink", type=float, default=0.5)
    parser.add_argument("--h-diff-a", type=float, default=30.0)
    parser.add_argument("--h-diff-b", type=float, default=15.0)
    parser.add_argument("--overlap-a", type=float, default=0.05)
    parser.add_argument("--overlap-b", type=float, default=0.15)
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    print("=== feat-044 pink/skin separation diagnosis ===")
    selected = select_sample_frames(
        args.video, args.json_dir, args.candidate_frames,
        args.frame_tolerance, args.min_samples, args.max_samples,
    )
    print(f"Selected frames: {selected}  ({len(selected)} samples)")
    if len(selected) < args.min_samples:
        print(
            f"ERROR: only {len(selected)} samples, below min {args.min_samples}. "
            "Sampling strategy needs redesign per investigation.md §1.3.3.",
            file=sys.stderr,
        )
        sys.exit(2)

    roi_a_chunks = []
    roi_b_raw_chunks = []
    for fi in selected:
        frame = get_frame(args.video, fi)
        if frame is None:
            continue
        d = load_frame_json(args.json_dir, Path(args.video).stem, fi)
        person = find_pink_person(d["people"])
        kpts = get_kpts(person)
        roi_a_chunks.append(extract_roi_a_skin(frame, kpts, args.skin_patch_size))
        roi_b_raw_chunks.append(
            extract_roi_b_torso_raw(frame, kpts, args.torso_shrink)
        )

    roi_a_all = (
        np.concatenate(roi_a_chunks, axis=0) if roi_a_chunks else np.empty((0, 3))
    )
    roi_b_raw_all = (
        np.concatenate(roi_b_raw_chunks, axis=0)
        if roi_b_raw_chunks else np.empty((0, 3))
    )

    stats_a = compute_stats(roi_a_all)
    a_p25, a_p75 = int(round(stats_a["H_p25"])), int(round(stats_a["H_p75"]))

    roi_b_filt_all = filter_skin_h_band(roi_b_raw_all, a_p25, a_p75)
    stats_b = compute_stats(roi_b_filt_all)

    h_diff = hue_circular_distance(stats_a["H_med"], stats_b["H_med"])
    overlap = compute_h_overlap_ratio(roi_b_raw_all, a_p25, a_p75)

    print()
    print(f"ROI-A (skin, nose patch {args.skin_patch_size}x{args.skin_patch_size}):")
    print(f"  total pixels: {stats_a['n']}")
    print(f"  H median={stats_a['H_med']:.0f}, P25={stats_a['H_p25']:.0f}, "
          f"P75={stats_a['H_p75']:.0f}, mean={stats_a['H_mean']:.1f}")
    print(f"  S median={stats_a['S_med']:.0f}, P25={stats_a['S_p25']:.0f}, "
          f"P75={stats_a['S_p75']:.0f}, mean={stats_a['S_mean']:.1f}")
    print(f"  V median={stats_a['V_med']:.0f}, P25={stats_a['V_p25']:.0f}, "
          f"P75={stats_a['V_p75']:.0f}, mean={stats_a['V_mean']:.1f}")

    print()
    print(f"ROI-B (gown, torso center {int(args.torso_shrink*100)}%, skin-H excluded):")
    print(f"  total pixels (raw): {len(roi_b_raw_all)}")
    print(f"  total pixels (skin-H excluded): {stats_b['n']}")
    print(f"  H median={stats_b['H_med']:.0f}, P25={stats_b['H_p25']:.0f}, "
          f"P75={stats_b['H_p75']:.0f}, mean={stats_b['H_mean']:.1f}")
    print(f"  S median={stats_b['S_med']:.0f}, P25={stats_b['S_p25']:.0f}, "
          f"P75={stats_b['S_p75']:.0f}, mean={stats_b['S_mean']:.1f}")
    print(f"  V median={stats_b['V_med']:.0f}, P25={stats_b['V_p25']:.0f}, "
          f"P75={stats_b['V_p75']:.0f}, mean={stats_b['V_mean']:.1f}")

    print()
    print(f"H circular distance (ROI-A median vs ROI-B median): {h_diff:.0f}")
    print(f"H overlap ratio (raw ROI-B in ROI-A P25-P75 band [{a_p25}-{a_p75}]): "
          f"{overlap*100:.1f}%")

    print()
    hyp, notes = classify_hypothesis(
        h_diff, overlap,
        args.h_diff_a, args.h_diff_b, args.overlap_a, args.overlap_b,
    )
    print("=== Hypothesis classification ===")
    for n in notes:
        print(f"  {n}")
    print(f"Final: HYPOTHESIS {hyp}")
    if hyp == "A":
        print("  -> HSV range adjustment can solve.")
    elif hyp == "B":
        print("  -> HSV alone cannot separate. Spatial constraints needed.")
    else:
        print("  -> GRAY zone. Re-examine sampling/ROI per investigation.md §1.3.6.")

    scatter_path = os.path.join(args.out_dir, "skin_vs_gown_scatter.png")
    hist_path = os.path.join(args.out_dir, "h_histograms.png")
    plot_scatter(roi_a_all, roi_b_raw_all, scatter_path)
    plot_h_histograms(roi_a_all, roi_b_raw_all, roi_b_filt_all, hist_path)
    print()
    print(f"Saved: {scatter_path}")
    print(f"Saved: {hist_path}")


if __name__ == "__main__":
    main()
