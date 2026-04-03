"""HALPE 26 unified pipeline with YOLOX-l detector: video visualization + OpenPose JSON output."""
import argparse
import json
import os
import sys
import time

import cv2
import numpy as np

import mmdet
from mmpose.apis import (inference_top_down_pose_model, init_pose_model,
                         process_mmdet_results)
from mmpose.datasets import DatasetInfo
from mmdet.apis import inference_detector, init_detector

sys.path.insert(0, os.path.dirname(__file__))
from merge_halpe26 import (merge_to_halpe26, draw_halpe26, draw_bbox,
                            WB_CONFIG, WB_CHECKPOINT,
                            AIC_CONFIG, AIC_CHECKPOINT)
from halpe26_to_openpose import halpe26_to_openpose_json

# YOLOX-l detector paths
MMDET_DIR = os.path.dirname(os.path.abspath(mmdet.__file__))
DET_CONFIG = os.path.join(
    MMDET_DIR, '.mim/configs/yolox/yolox_l_8x8_300e_coco.py')
DET_CHECKPOINT = 'checkpoints/yolox_l_8x8_300e_coco_20211126_140236-d3bd2b23.pth'


def parse_args() -> argparse.Namespace:
    """CLI引数をパースする。"""
    parser = argparse.ArgumentParser(
        description='HALPE 26 pipeline with YOLOX-l detector')
    parser.add_argument('--video', type=str, required=True,
                        help='Input video path')
    parser.add_argument('--out-dir', type=str, default='output',
                        help='Output base directory')
    parser.add_argument('--device', type=str, default='cuda:0',
                        help='Inference device')
    parser.add_argument('--mode', type=str, default='both',
                        choices=['both', 'video', 'json'],
                        help='Output mode: both, video, json')
    parser.add_argument('--bbox-thr', type=float, default=0.3,
                        help='Bounding box score threshold for person detection (default: 0.3)')
    parser.add_argument('--kpt-thr', type=float, default=0.3,
                        help='Keypoint confidence threshold for drawing (0.0-1.0, default: 0.3)')
    parser.add_argument('--profile', action='store_true',
                        help='Enable per-step profiling')
    return parser.parse_args()


def main() -> None:
    """統合パイプラインのメイン処理。"""
    args = parse_args()

    # Mode flags
    do_video = args.mode in ('both', 'video')
    do_json = args.mode in ('both', 'json')
    print(f'Output mode: {args.mode}')
    print(f'Detector: YOLOX-l')
    print(f'Bbox threshold: {args.bbox_thr}')

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
    out_path = None
    if do_video:
        out_name = f'vis_halpe26_{os.path.basename(args.video)}'
        out_path = os.path.join(args.out_dir, out_name)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))
    if do_json:
        json_dir = os.path.join(args.out_dir, f'{video_stem}_json')
        os.makedirs(json_dir, exist_ok=True)

    # 5. Frame loop
    if args.profile:
        profile = {
            'read': 0.0, 'det': 0.0, 'wb': 0.0, 'aic': 0.0,
            'merge': 0.0, 'draw': 0.0, 'json': 0.0,
        }
        total_start = time.time()

    frame_idx = 0
    while cap.isOpened():
        if args.profile:
            t = time.time()
        ret, frame = cap.read()
        if not ret:
            break
        if args.profile:
            profile['read'] += time.time() - t

        # 5a. Person detection
        if args.profile:
            t = time.time()
        mmdet_results = inference_detector(det_model, frame)
        person_results = process_mmdet_results(mmdet_results, cat_id=1)
        if args.profile:
            profile['det'] += time.time() - t

        # 5b. WholeBody estimation
        if args.profile:
            t = time.time()
        wb_results, _ = inference_top_down_pose_model(
            wb_model, frame, person_results, bbox_thr=args.bbox_thr,
            format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)
        if args.profile:
            profile['wb'] += time.time() - t

        # 5c. AIC estimation
        if args.profile:
            t = time.time()
        aic_results, _ = inference_top_down_pose_model(
            aic_model, frame, person_results, bbox_thr=args.bbox_thr,
            format='xyxy', dataset=aic_dataset, dataset_info=aic_dataset_info)
        if args.profile:
            profile['aic'] += time.time() - t

        # 5d. Merge to HALPE 26
        if args.profile:
            t = time.time()
        if len(wb_results) != len(aic_results):
            print(f'Warning: frame {frame_idx} result count mismatch '
                  f'(wb={len(wb_results)}, aic={len(aic_results)}), '
                  f'skipping keypoints')
            all_halpe26 = []
        else:
            all_halpe26 = [merge_to_halpe26(wb_results[i]['keypoints'],
                                             aic_results[i]['keypoints'])
                           for i in range(len(wb_results))]
        if args.profile:
            profile['merge'] += time.time() - t

        # 5e. Video output
        if do_video:
            if args.profile:
                t = time.time()
            vis_frame = frame.copy()
            # BB描画（キーポイントの下に描画するため、先にBBを描画）
            for i in range(len(wb_results)):
                vis_frame = draw_bbox(vis_frame, wb_results[i]['bbox'])
            # キーポイント・スケルトン描画
            for kps in all_halpe26:
                vis_frame = draw_halpe26(vis_frame, kps, kpt_thr=args.kpt_thr)
            writer.write(vis_frame)
            if args.profile:
                profile['draw'] += time.time() - t

        # 5f. JSON output
        if do_json:
            if args.profile:
                t = time.time()
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
            if args.profile:
                profile['json'] += time.time() - t

        if frame_idx % 100 == 0:
            print(f'Processing frame {frame_idx}/{total_frames}...')
        frame_idx += 1

    if args.profile:
        total_elapsed = time.time() - total_start

    # 6. Release
    cap.release()
    if writer is not None:
        writer.release()

    if do_video:
        print(f'Saved: {out_path} ({frame_idx} frames)')
    if do_json:
        print(f'Saved {frame_idx} JSON files to {json_dir}')

    if args.profile:
        processing_fps = frame_idx / total_elapsed if total_elapsed > 0 else 0.0
        print(f'\n--- Profile ({frame_idx} frames, {total_elapsed:.1f}s, '
              f'{processing_fps:.1f} fps) ---')
        print(f'{"Step":<12} {"Total(s)":>10} {"Avg(ms)":>10} {"Ratio":>8}')
        for key, label in [('read', 'Read'),
                           ('det', 'Detection'),
                           ('wb', 'WholeBody'),
                           ('aic', 'AIC'),
                           ('merge', 'Merge'),
                           ('draw', 'Draw'),
                           ('json', 'JSON')]:
            total_s = profile[key]
            avg_ms = (total_s / frame_idx * 1000) if frame_idx > 0 else 0
            ratio = (total_s / total_elapsed * 100) if total_elapsed > 0 else 0
            print(f'{label:<12} {total_s:>10.2f} {avg_ms:>10.1f} {ratio:>7.1f}%')


if __name__ == '__main__':
    main()
