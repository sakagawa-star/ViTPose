"""Compare BB dedup methods: Plan A (union re-estimate) vs Plan E (best score).

Outputs visualization videos, OpenPose JSON, and OKS statistics for both methods.
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

from ultralytics import YOLO
from mmpose.apis import inference_top_down_pose_model, init_pose_model
from mmpose.datasets import DatasetInfo

sys.path.insert(0, os.path.dirname(__file__))
from merge_halpe26 import (merge_to_halpe26, draw_halpe26, draw_bbox,
                            WB_CONFIG, WB_CHECKPOINT,
                            AIC_CONFIG, AIC_CHECKPOINT)
from halpe26_to_openpose import halpe26_to_openpose_json

CONF_THR = 0.3

HALPE26_SIGMAS = np.array([
    0.026, 0.025, 0.025, 0.035, 0.035,      # Nose,LEye,REye,LEar,REar
    0.079, 0.079, 0.072, 0.072, 0.062, 0.062,  # shoulders,elbows,wrists
    0.107, 0.107, 0.087, 0.087, 0.089, 0.089,  # hips,knees,ankles
    0.10, 0.10, 0.10,                        # Head,Neck,Hip(center)
    0.089, 0.089, 0.089, 0.089, 0.089, 0.089,  # toes,heels
])


def process_yolo11_results(
    results,
    person_cls: int = 0,
) -> list[dict]:
    """YOLO11x結果をMMPose互換のperson_results形式に変換する。"""
    person_results = []
    boxes = results.boxes
    for i in range(len(boxes)):
        if int(boxes.cls[i]) == person_cls:
            x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy()
            score = float(boxes.conf[i].cpu())
            person_results.append({
                'bbox': np.array([x1, y1, x2, y2, score], dtype=np.float32)
            })
    return person_results


def compute_oks_mutual(kps1: np.ndarray, kps2: np.ndarray, area: float) -> float:
    """両者のconfidence > CONF_THRの共通キーポイントでOKSを計算する（重複判定用）。"""
    valid = (kps1[:, 2] > CONF_THR) & (kps2[:, 2] > CONF_THR)
    if valid.sum() == 0:
        return 0.0
    dx = kps1[valid, 0] - kps2[valid, 0]
    dy = kps1[valid, 1] - kps2[valid, 1]
    dist_sq = dx**2 + dy**2
    sigma = HALPE26_SIGMAS[valid]
    e = dist_sq / (2 * area * sigma**2 + 1e-6)
    return float(np.mean(np.exp(-e)))


def compute_oks(kps_ref: np.ndarray, kps_target: np.ndarray, area: float) -> float:
    """案A基準のOKSを計算する（案A vs 案E比較用）。"""
    valid = kps_ref[:, 2] > CONF_THR
    if valid.sum() == 0:
        return 0.0
    dx = kps_ref[valid, 0] - kps_target[valid, 0]
    dy = kps_ref[valid, 1] - kps_target[valid, 1]
    dist_sq = dx**2 + dy**2
    sigma = HALPE26_SIGMAS[valid]
    e = dist_sq / (2 * area * sigma**2 + 1e-6)
    return float(np.mean(np.exp(-e)))


def build_dedup_groups(
    n_persons: int, oks_matrix: np.ndarray, oks_thr: float,
) -> list[list[int]]:
    """OKS行列から重複グループを構築する（簡易Union-Find）。"""
    parent = list(range(n_persons))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n_persons):
        for j in range(i + 1, n_persons):
            if oks_matrix[i, j] > oks_thr:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n_persons):
        r = find(i)
        groups.setdefault(r, []).append(i)

    return [g for g in groups.values() if len(g) >= 2]


def method_a(
    frame: np.ndarray,
    group_bboxes: list[np.ndarray],
    wb_model, aic_model,
    wb_dataset: str, wb_dataset_info,
    aic_dataset: str, aic_dataset_info,
    img_h: int, img_w: int,
) -> tuple[np.ndarray, np.ndarray]:
    """重複BBの外接矩形で再推定する。"""
    all_bboxes = np.array(group_bboxes)
    x1 = float(np.clip(all_bboxes[:, 0].min(), 0, img_w))
    y1 = float(np.clip(all_bboxes[:, 1].min(), 0, img_h))
    x2 = float(np.clip(all_bboxes[:, 2].max(), 0, img_w))
    y2 = float(np.clip(all_bboxes[:, 3].max(), 0, img_h))
    max_score = float(all_bboxes[:, 4].max())
    union_bbox = np.array([x1, y1, x2, y2, max_score], dtype=np.float32)

    union_person = [{'bbox': union_bbox}]
    wb_results, _ = inference_top_down_pose_model(
        wb_model, frame, union_person, bbox_thr=None,
        format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)
    aic_results, _ = inference_top_down_pose_model(
        aic_model, frame, union_person, bbox_thr=None,
        format='xyxy', dataset=aic_dataset, dataset_info=aic_dataset_info)

    kps = merge_to_halpe26(wb_results[0]['keypoints'], aic_results[0]['keypoints'])
    return kps, union_bbox


def method_e(
    group_indices: list[int],
    all_halpe26: list[np.ndarray],
    all_bboxes: list[np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    """重複グループ内でbbox scoreが最大のキーポイントとBBを返す。"""
    scores = [all_bboxes[i][4] for i in group_indices]
    best_idx = group_indices[int(np.argmax(scores))]
    return all_halpe26[best_idx], all_bboxes[best_idx]


def write_frame(writer: cv2.VideoWriter, frame: np.ndarray,
                results: list[dict], kpt_thr: float) -> None:
    """可視化フレームを描画して書き込む。"""
    vis = frame.copy()
    for r in results:
        vis = draw_bbox(vis, r['bbox'])
    for r in results:
        vis = draw_halpe26(vis, r['keypoints'], kpt_thr=kpt_thr)
    writer.write(vis)


def write_json(json_dir: str, stem: str, frame_idx: int,
               results: list[dict]) -> None:
    """OpenPose JSONを書き出す。"""
    all_kps = [r['keypoints'] for r in results]
    bbox_scores = [float(r['bbox'][4]) for r in results]
    bboxes = [r['bbox'][:4].tolist() for r in results]
    openpose_dict = halpe26_to_openpose_json(
        all_kps, bbox_scores=bbox_scores, bboxes=bboxes)
    path = os.path.join(json_dir, f'{stem}_{frame_idx:06d}.json')
    with open(path, 'w') as f:
        json.dump(openpose_dict, f)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Compare BB dedup methods: Plan A vs Plan E')
    parser.add_argument('--video', type=str, required=True,
                        help='Input video path')
    parser.add_argument('--out-dir', type=str, default='output',
                        help='Output directory')
    parser.add_argument('--device', type=str, default='cuda:0',
                        help='Inference device')
    parser.add_argument('--bbox-thr', type=float, default=0.3,
                        help='Detection score threshold (default: 0.3)')
    parser.add_argument('--oks-thr', type=float, default=0.5,
                        help='OKS threshold for dedup detection (default: 0.5)')
    parser.add_argument('--kpt-thr', type=float, default=0.3,
                        help='Keypoint draw threshold (default: 0.3)')
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print('=== BB Dedup Method Comparison ===')
    print(f'Video: {args.video}')
    print(f'Bbox threshold: {args.bbox_thr}, OKS dedup threshold: {args.oks_thr}')
    print()

    # 1. Initialize models
    print('Initializing models...')
    det_model = YOLO('yolo11x.pt')
    wb_model = init_pose_model(WB_CONFIG, WB_CHECKPOINT, device=args.device)
    aic_model = init_pose_model(AIC_CONFIG, AIC_CHECKPOINT, device=args.device)

    wb_dataset = wb_model.cfg.data['test']['type']
    wb_dataset_info = DatasetInfo(wb_model.cfg.data['test']['dataset_info'])
    aic_dataset = aic_model.cfg.data['test']['type']
    aic_dataset_info = DatasetInfo(aic_model.cfg.data['test']['dataset_info'])
    print('Models initialized.')

    # 2. Open video & create output targets
    cap = cv2.VideoCapture(args.video)
    assert cap.isOpened(), f'Failed to open video: {args.video}'
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    img_h, img_w = height, width
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    video_basename = os.path.basename(args.video)
    video_stem = os.path.splitext(video_basename)[0]
    os.makedirs(args.out_dir, exist_ok=True)

    out_path_a = os.path.join(args.out_dir, f'vis_dedup_a_{video_basename}')
    out_path_e = os.path.join(args.out_dir, f'vis_dedup_e_{video_basename}')
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer_a = cv2.VideoWriter(out_path_a, fourcc, fps, (width, height))
    writer_e = cv2.VideoWriter(out_path_e, fourcc, fps, (width, height))

    json_dir_a = os.path.join(args.out_dir, f'{video_stem}_dedup_a_json')
    json_dir_e = os.path.join(args.out_dir, f'{video_stem}_dedup_e_json')
    os.makedirs(json_dir_a, exist_ok=True)
    os.makedirs(json_dir_e, exist_ok=True)

    # 3. Frame loop
    frames_with_detection = 0
    frames_with_multi = 0
    frames_with_dedup = 0
    oks_samples: list[float] = []

    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # 3a. Person detection + filter
        yolo_results = det_model(frame, device=args.device, verbose=False)
        person_results = process_yolo11_results(yolo_results[0])
        person_results = [p for p in person_results if p['bbox'][4] >= args.bbox_thr]
        n_persons = len(person_results)

        if n_persons > 0:
            frames_with_detection += 1

        # 3b. 0 persons: empty frame
        if n_persons == 0:
            writer_a.write(frame)
            writer_e.write(frame)
            write_json(json_dir_a, video_stem, frame_idx, [])
            write_json(json_dir_e, video_stem, frame_idx, [])
            if frame_idx % 100 == 0:
                print(f'Processing frame {frame_idx}/{total_frames}...')
            frame_idx += 1
            continue

        # 3c-d. Pose estimation for all persons
        all_bboxes = [p['bbox'] for p in person_results]
        wb_results, _ = inference_top_down_pose_model(
            wb_model, frame, person_results, bbox_thr=None,
            format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)
        aic_results, _ = inference_top_down_pose_model(
            aic_model, frame, person_results, bbox_thr=None,
            format='xyxy', dataset=aic_dataset, dataset_info=aic_dataset_info)

        all_halpe26 = [merge_to_halpe26(wb_results[i]['keypoints'],
                                         aic_results[i]['keypoints'])
                       for i in range(n_persons)]

        # Build normal results (used when no dedup needed)
        normal_results = [{'keypoints': all_halpe26[i], 'bbox': all_bboxes[i]}
                          for i in range(n_persons)]

        # 3c. 1 person: output normally
        if n_persons == 1:
            write_frame(writer_a, frame, normal_results, args.kpt_thr)
            write_frame(writer_e, frame, normal_results, args.kpt_thr)
            write_json(json_dir_a, video_stem, frame_idx, normal_results)
            write_json(json_dir_e, video_stem, frame_idx, normal_results)
            if frame_idx % 100 == 0:
                print(f'Processing frame {frame_idx}/{total_frames}...')
            frame_idx += 1
            continue

        frames_with_multi += 1

        # 3e. Compute pairwise OKS for dedup detection
        oks_matrix = np.zeros((n_persons, n_persons))
        for i in range(n_persons):
            for j in range(i + 1, n_persons):
                area_i = (all_bboxes[i][2] - all_bboxes[i][0]) * (all_bboxes[i][3] - all_bboxes[i][1])
                area_j = (all_bboxes[j][2] - all_bboxes[j][0]) * (all_bboxes[j][3] - all_bboxes[j][1])
                area = max(float(area_i), float(area_j))
                oks_val = compute_oks_mutual(all_halpe26[i], all_halpe26[j], area)
                oks_matrix[i, j] = oks_val
                oks_matrix[j, i] = oks_val

        # 3f. Build dedup groups
        groups = build_dedup_groups(n_persons, oks_matrix, args.oks_thr)

        # 3g. No dedup groups: output normally
        if not groups:
            write_frame(writer_a, frame, normal_results, args.kpt_thr)
            write_frame(writer_e, frame, normal_results, args.kpt_thr)
            write_json(json_dir_a, video_stem, frame_idx, normal_results)
            write_json(json_dir_e, video_stem, frame_idx, normal_results)
            if frame_idx % 100 == 0:
                print(f'Processing frame {frame_idx}/{total_frames}...')
            frame_idx += 1
            continue

        frames_with_dedup += 1

        # 3h. Build Plan A / Plan E results
        in_group = set()
        for g in groups:
            in_group.update(g)

        result_a: list[dict] = []
        result_e: list[dict] = []

        # Non-overlapping persons
        for i in range(n_persons):
            if i not in in_group:
                result_a.append({'keypoints': all_halpe26[i], 'bbox': all_bboxes[i]})
                result_e.append({'keypoints': all_halpe26[i], 'bbox': all_bboxes[i]})

        # Dedup groups
        for g in groups:
            group_bboxes = [all_bboxes[i] for i in g]

            kps_a, bbox_a = method_a(
                frame, group_bboxes, wb_model, aic_model,
                wb_dataset, wb_dataset_info,
                aic_dataset, aic_dataset_info,
                img_h, img_w)
            result_a.append({'keypoints': kps_a, 'bbox': bbox_a})

            kps_e, bbox_e = method_e(g, all_halpe26, all_bboxes)
            result_e.append({'keypoints': kps_e, 'bbox': bbox_e})

            # 3k. OKS comparison
            union_area = float((bbox_a[2] - bbox_a[0]) * (bbox_a[3] - bbox_a[1]))
            oks_val = compute_oks(kps_a, kps_e, union_area)
            oks_samples.append(oks_val)

        # 3i-j. Write outputs
        write_frame(writer_a, frame, result_a, args.kpt_thr)
        write_frame(writer_e, frame, result_e, args.kpt_thr)
        write_json(json_dir_a, video_stem, frame_idx, result_a)
        write_json(json_dir_e, video_stem, frame_idx, result_e)

        if frame_idx % 100 == 0:
            print(f'Processing frame {frame_idx}/{total_frames}...')
        frame_idx += 1

    # 4. Release
    cap.release()
    writer_a.release()
    writer_e.release()

    # 5. Statistics output
    print()
    print(f'Total frames: {total_frames}')
    print(f'Frames with detection: {frames_with_detection}')
    print(f'Frames with multi-person: {frames_with_multi} '
          f'({100 * frames_with_multi / total_frames:.1f}%)')
    print(f'Frames with dedup (OKS > {args.oks_thr}): {frames_with_dedup} '
          f'({100 * frames_with_dedup / total_frames:.1f}%)')
    print(f'Dedup groups (total): {len(oks_samples)} '
          f'(= OKS sample count, across all frames)')

    if not oks_samples:
        print('\nNo dedup groups found. Nothing to compare.')
    else:
        oks_arr = np.array(oks_samples)
        print(f'\n--- Plan A vs Plan E: OKS ---')
        print(f'Mean:   {oks_arr.mean():.3f}')
        print(f'Median: {np.median(oks_arr):.3f}')
        print(f'Min:    {oks_arr.min():.3f}')
        print(f'Max:    {oks_arr.max():.3f}')
        for thr in [0.50, 0.75, 0.90, 0.95]:
            count = int((oks_arr > thr).sum())
            print(f'>{thr:.2f}:  {count} / {len(oks_arr)} '
                  f'({100 * count / len(oks_arr):.1f}%)')

    print(f'\nSaved: {out_path_a}')
    print(f'Saved: {out_path_e}')
    print(f'Saved {frame_idx} JSON files to {json_dir_a}')
    print(f'Saved {frame_idx} JSON files to {json_dir_e}')


if __name__ == '__main__':
    main()
