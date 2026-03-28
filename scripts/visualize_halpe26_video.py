"""HALPE 26 keypoint visualization on video."""
import argparse
import os
import sys

import cv2
import numpy as np

from mmpose.apis import (inference_top_down_pose_model, init_pose_model,
                         process_mmdet_results)
from mmpose.datasets import DatasetInfo
from mmdet.apis import inference_detector, init_detector

sys.path.insert(0, os.path.dirname(__file__))
from merge_halpe26 import (merge_to_halpe26, draw_halpe26,
                            DET_CONFIG, DET_CHECKPOINT,
                            WB_CONFIG, WB_CHECKPOINT,
                            AIC_CONFIG, AIC_CHECKPOINT)


def parse_args():
    parser = argparse.ArgumentParser(
        description='Visualize HALPE 26 keypoints on video')
    parser.add_argument('--video', type=str, required=True,
                        help='Input video path')
    parser.add_argument('--out-dir', type=str, default='output/feat-011',
                        help='Output directory')
    parser.add_argument('--device', type=str, default='cuda:0',
                        help='Inference device')
    return parser.parse_args()


def main():
    args = parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

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
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f'Processing video: {args.video} ({total_frames} frames, {fps} fps)')

    # 3. Create video writer
    out_name = f'vis_halpe26_{os.path.basename(args.video)}'
    out_path = os.path.join(args.out_dir, out_name)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

    # 4. Frame loop
    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # 4a. Person detection
        mmdet_results = inference_detector(det_model, frame)
        person_results = process_mmdet_results(mmdet_results, cat_id=1)

        # 4b. WholeBody estimation
        wb_results, _ = inference_top_down_pose_model(
            wb_model, frame, person_results, bbox_thr=0.3,
            format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)

        # 4c. AIC estimation
        aic_results, _ = inference_top_down_pose_model(
            aic_model, frame, person_results, bbox_thr=0.3,
            format='xyxy', dataset=aic_dataset, dataset_info=aic_dataset_info)

        # 4d. Merge + draw (skip keypoints on result count mismatch)
        vis_frame = frame.copy()
        if len(wb_results) == len(aic_results):
            for i in range(len(wb_results)):
                halpe26 = merge_to_halpe26(
                    wb_results[i]['keypoints'], aic_results[i]['keypoints'])
                vis_frame = draw_halpe26(vis_frame, halpe26)
        else:
            print(f'Warning: frame {frame_idx} result count mismatch '
                  f'(wb={len(wb_results)}, aic={len(aic_results)}), '
                  f'skipping keypoints')

        writer.write(vis_frame)

        if frame_idx % 100 == 0:
            print(f'Processing frame {frame_idx}/{total_frames}...')
        frame_idx += 1

    # 5. Release
    cap.release()
    writer.release()
    print(f'Saved: {out_path} ({frame_idx} frames)')


if __name__ == '__main__':
    main()
