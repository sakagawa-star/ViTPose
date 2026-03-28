"""HALPE 26 unified pipeline: video visualization + OpenPose JSON output."""
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
from merge_halpe26 import (merge_to_halpe26, draw_halpe26, draw_bbox,
                            DET_CONFIG, DET_CHECKPOINT,
                            WB_CONFIG, WB_CHECKPOINT,
                            AIC_CONFIG, AIC_CHECKPOINT)
from halpe26_to_openpose import halpe26_to_openpose_json


def parse_args() -> argparse.Namespace:
    """CLI引数をパースする。"""
    parser = argparse.ArgumentParser(
        description='HALPE 26 unified pipeline: visualization + OpenPose JSON')
    parser.add_argument('--video', type=str, required=True,
                        help='Input video path')
    parser.add_argument('--out-dir', type=str, default='output',
                        help='Output base directory')
    parser.add_argument('--device', type=str, default='cuda:0',
                        help='Inference device')
    parser.add_argument('--mode', type=str, default='both',
                        choices=['both', 'video', 'json'],
                        help='Output mode: both, video, json')
    return parser.parse_args()


def main() -> None:
    """統合パイプラインのメイン処理。"""
    args = parse_args()

    # Mode flags
    do_video = args.mode in ('both', 'video')
    do_json = args.mode in ('both', 'json')
    print(f'Output mode: {args.mode}')

    # 1. Initialize models
    print('Initializing models...')
    det_model = init_detector(DET_CONFIG, DET_CHECKPOINT, device=args.device)
    wb_model = init_pose_model(WB_CONFIG, WB_CHECKPOINT, device=args.device)
    aic_model = init_pose_model(AIC_CONFIG, AIC_CHECKPOINT, device=args.device)

    wb_dataset = wb_model.cfg.data['test']['type']
    wb_dataset_info = DatasetInfo(wb_model.cfg.data['test']['dataset_info'])
    aic_dataset = aic_model.cfg.data['test']['type']
    aic_dataset_info = DatasetInfo(aic_model.cfg.data['test']['dataset_info'])
    print('Models initialized.')

    # 2. Output directory
    os.makedirs(args.out_dir, exist_ok=True)
    video_stem = os.path.splitext(os.path.basename(args.video))[0]

    # 3. Open video
    cap = cv2.VideoCapture(args.video)
    assert cap.isOpened(), f'Failed to open video: {args.video}'
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f'Processing video: {args.video} ({total_frames} frames, {fps} fps)')

    # 4. Create output targets
    writer = None
    json_dir = None
    if do_video:
        out_name = f'vis_halpe26_{os.path.basename(args.video)}'
        out_path = os.path.join(args.out_dir, out_name)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))
    if do_json:
        json_dir = os.path.join(args.out_dir, f'{video_stem}_json')
        os.makedirs(json_dir, exist_ok=True)

    # 5. Frame loop
    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # 5a. Person detection
        mmdet_results = inference_detector(det_model, frame)
        person_results = process_mmdet_results(mmdet_results, cat_id=1)

        # 5b. WholeBody estimation
        wb_results, _ = inference_top_down_pose_model(
            wb_model, frame, person_results, bbox_thr=0.3,
            format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)

        # 5c. AIC estimation
        aic_results, _ = inference_top_down_pose_model(
            aic_model, frame, person_results, bbox_thr=0.3,
            format='xyxy', dataset=aic_dataset, dataset_info=aic_dataset_info)

        # 5d. Merge to HALPE 26
        if len(wb_results) != len(aic_results):
            print(f'Warning: frame {frame_idx} result count mismatch '
                  f'(wb={len(wb_results)}, aic={len(aic_results)}), '
                  f'skipping keypoints')
            all_halpe26 = []
        else:
            all_halpe26 = [merge_to_halpe26(wb_results[i]['keypoints'],
                                             aic_results[i]['keypoints'])
                           for i in range(len(wb_results))]

        # 5e. Video output
        if do_video:
            vis_frame = frame.copy()
            # BB描画（キーポイントの下に描画するため、先にBBを描画）
            for i in range(len(wb_results)):
                vis_frame = draw_bbox(vis_frame, wb_results[i]['bbox'])
            # キーポイント・スケルトン描画
            for kps in all_halpe26:
                vis_frame = draw_halpe26(vis_frame, kps)
            writer.write(vis_frame)

        # 5f. JSON output
        if do_json:
            openpose_dict = halpe26_to_openpose_json(all_halpe26)
            json_path = os.path.join(json_dir, f'{video_stem}_{frame_idx:06d}.json')
            with open(json_path, 'w') as f:
                json.dump(openpose_dict, f)

        if frame_idx % 100 == 0:
            print(f'Processing frame {frame_idx}/{total_frames}...')
        frame_idx += 1

    # 6. Release
    cap.release()
    if writer is not None:
        writer.release()

    if do_video:
        print(f'Saved: {out_path} ({frame_idx} frames)')
    if do_json:
        print(f'Saved {frame_idx} JSON files to {json_dir}')


if __name__ == '__main__':
    main()
