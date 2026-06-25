"""HALPE 26 keypoints to OpenPose JSON output (Pose2Sim compatible)."""
import argparse
import json
import os
import sys

import cv2
import numpy as np

from mmpose.apis import (inference_top_down_pose_model, init_pose_model,
                         process_mmdet_results)
from mmpose.datasets import DatasetInfo
from mmdet.apis import inference_detector, init_detector

sys.path.insert(0, os.path.dirname(__file__))
from merge_halpe26 import (merge_to_halpe26,
                            DET_CONFIG, DET_CHECKPOINT,
                            WB_CONFIG, WB_CHECKPOINT,
                            AIC_CONFIG, AIC_CHECKPOINT)


def halpe26_to_openpose_json(
    all_halpe26: list,
    bbox_scores: list | None = None,
    bboxes: list | None = None,
    stable_ids: list[int] | None = None,
    fallback_flags: list[bool] | None = None,
) -> dict:
    """Convert HALPE 26 keypoints to OpenPose JSON dict.

    Args:
        all_halpe26: list of ndarray, each shape=(26, 3)
        bbox_scores: list of float, bounding box detection scores.
            Must have the same length as all_halpe26.
            If None, bbox_score field is not included in the output.
        bboxes: list of list[float], bounding box ROI coordinates [x1, y1, x2, y2].
            Must have the same length as all_halpe26.
            If None, bbox field is not included in the output.
        stable_ids: list of int, stable IDs from custom Re-ID.
            Must have the same length as all_halpe26.
            If None, stable_id field is not included in the output.
        fallback_flags: list of bool, fallback ROI injection flags (feat-061).
            Must have the same length as all_halpe26.
            For each person where the flag is True, a "fallback": true field is added.
            If None, or for elements that are False, the fallback field is not included.

    Returns:
        OpenPose JSON dict
    """
    people = []
    for i, kps in enumerate(all_halpe26):
        person = {
            'person_id': [-1],
            'pose_keypoints_2d': kps.flatten().tolist(),
            'face_keypoints_2d': [],
            'hand_left_keypoints_2d': [],
            'hand_right_keypoints_2d': [],
            'pose_keypoints_3d': [],
            'face_keypoints_3d': [],
            'hand_left_keypoints_3d': [],
            'hand_right_keypoints_3d': [],
        }
        if bbox_scores is not None:
            person['bbox_score'] = bbox_scores[i]
        if bboxes is not None:
            person['bbox'] = bboxes[i]
        if stable_ids is not None:
            person['stable_id'] = stable_ids[i]
        if fallback_flags is not None and fallback_flags[i]:
            person['fallback'] = True
        people.append(person)
    return {'version': 1.3, 'people': people}


def parse_args():
    parser = argparse.ArgumentParser(
        description='Output HALPE 26 keypoints as OpenPose JSON (Pose2Sim compatible)')
    parser.add_argument('--video', type=str, required=True,
                        help='Input video path')
    parser.add_argument('--out-dir', type=str, default='output/feat-010',
                        help='Output base directory')
    parser.add_argument('--device', type=str, default='cuda:0',
                        help='Inference device')
    return parser.parse_args()


def main():
    args = parse_args()

    # 1. Initialize models
    print('Initializing models...')
    det_model = init_detector(DET_CONFIG, DET_CHECKPOINT, device=args.device)
    wb_model = init_pose_model(WB_CONFIG, WB_CHECKPOINT, device=args.device)
    aic_model = init_pose_model(AIC_CONFIG, AIC_CHECKPOINT, device=args.device)

    wb_dataset = wb_model.cfg.data['test']['type']
    wb_dataset_info = DatasetInfo(wb_model.cfg.data['test']['dataset_info'])
    aic_dataset = aic_model.cfg.data['test']['type']
    aic_dataset_info = DatasetInfo(aic_model.cfg.data['test']['dataset_info'])

    # 2. Open video
    cap = cv2.VideoCapture(args.video)
    assert cap.isOpened(), f'Failed to open video: {args.video}'
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f'Processing video: {args.video} ({total_frames} frames)')

    # 3. Create output directory
    video_stem = os.path.splitext(os.path.basename(args.video))[0]
    json_dir = os.path.join(args.out_dir, f'{video_stem}_json')
    os.makedirs(json_dir, exist_ok=True)
    print(f'Output directory: {json_dir}')

    # 4. Frame loop
    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # 4a. Person detection + pose estimation
        mmdet_results = inference_detector(det_model, frame)
        person_results = process_mmdet_results(mmdet_results, cat_id=1)

        wb_results, _ = inference_top_down_pose_model(
            wb_model, frame, person_results, bbox_thr=0.3,
            format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)
        aic_results, _ = inference_top_down_pose_model(
            aic_model, frame, person_results, bbox_thr=0.3,
            format='xyxy', dataset=aic_dataset, dataset_info=aic_dataset_info)

        # 4b. Merge to HALPE 26
        all_halpe26 = []
        if len(wb_results) == len(aic_results):
            for i in range(len(wb_results)):
                halpe26 = merge_to_halpe26(
                    wb_results[i]['keypoints'], aic_results[i]['keypoints'])
                all_halpe26.append(halpe26)
        else:
            print(f'Warning: frame {frame_idx} result count mismatch '
                  f'(wb={len(wb_results)}, aic={len(aic_results)}), '
                  f'writing empty people')

        # 4c. Write JSON
        bbox_scores = [float(wb_results[i]['bbox'][4])
                       for i in range(len(all_halpe26))]
        bboxes = [wb_results[i]['bbox'][:4].tolist()
                  for i in range(len(all_halpe26))]
        openpose_dict = halpe26_to_openpose_json(all_halpe26,
                                                 bbox_scores=bbox_scores,
                                                 bboxes=bboxes)
        json_path = os.path.join(json_dir, f'{video_stem}_{frame_idx:06d}.json')
        with open(json_path, 'w') as f:
            json.dump(openpose_dict, f)

        if frame_idx % 100 == 0:
            print(f'Processing frame {frame_idx}/{total_frames}...')
        frame_idx += 1

    cap.release()
    print(f'Saved {frame_idx} JSON files to {json_dir}')


if __name__ == '__main__':
    main()
