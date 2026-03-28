"""WholeBody 133 + AIC 14 -> HALPE 26 keypoint merge script."""
import argparse
import os
import warnings

import cv2
import numpy as np

from mmpose.apis import (inference_top_down_pose_model, init_pose_model,
                         process_mmdet_results)
from mmpose.datasets import DatasetInfo

try:
    from mmdet.apis import inference_detector, init_detector
except (ImportError, ModuleNotFoundError):
    raise ImportError('mmdet is required for person detection.')

# Model paths (hardcoded)
DET_CONFIG = 'checkpoints/faster_rcnn_r50_fpn_1x_coco.py'
DET_CHECKPOINT = 'checkpoints/faster_rcnn_r50_fpn_1x_coco_20200130-047c8118.pth'
WB_CONFIG = ('configs/wholebody/2d_kpt_sview_rgb_img/topdown_heatmap/'
             'coco-wholebody/ViTPose_huge_wholebody_256x192.py')
WB_CHECKPOINT = 'checkpoints/wholebody.pth'
AIC_CONFIG = ('configs/body/2d_kpt_sview_rgb_img/topdown_heatmap/'
              'aic/ViTPose_huge_aic_256x192.py')
AIC_CHECKPOINT = 'checkpoints/aic.pth'

# HALPE 26 keypoint names
HALPE26_NAMES = [
    'Nose', 'LEye', 'REye', 'LEar', 'REar',
    'LShoulder', 'RShoulder', 'LElbow', 'RElbow', 'LWrist', 'RWrist',
    'LHip', 'RHip', 'LKnee', 'RKnee', 'LAnkle', 'RAnkle',
    'Head', 'Neck', 'Hip',
    'LBigToe', 'RBigToe', 'LSmallToe', 'RSmallToe', 'LHeel', 'RHeel',
]

# HALPE 26 skeleton (pairs of keypoint indices)
HALPE26_SKELETON = [
    (0, 1), (0, 2), (1, 3), (2, 4),
    (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 6), (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
    (17, 18), (18, 5), (18, 6),
    (15, 20), (15, 22), (15, 24),
    (16, 21), (16, 23), (16, 25),
    (11, 19), (12, 19),
]

# HALPE 26 keypoint colors (BGR for OpenCV)
HALPE26_COLORS = {
    0: (51, 153, 255), 17: (51, 153, 255), 18: (51, 153, 255), 19: (51, 153, 255),
    1: (0, 255, 0), 3: (0, 255, 0), 5: (0, 255, 0), 7: (0, 255, 0),
    9: (0, 255, 0), 11: (0, 255, 0), 13: (0, 255, 0), 15: (0, 255, 0),
    20: (0, 255, 0), 22: (0, 255, 0), 24: (0, 255, 0),
    2: (255, 128, 0), 4: (255, 128, 0), 6: (255, 128, 0), 8: (255, 128, 0),
    10: (255, 128, 0), 12: (255, 128, 0), 14: (255, 128, 0), 16: (255, 128, 0),
    21: (255, 128, 0), 23: (255, 128, 0), 25: (255, 128, 0),
}


def merge_to_halpe26(
    wb_keypoints: np.ndarray,
    aic_keypoints: np.ndarray,
) -> np.ndarray:
    """WholeBody 133 + AIC 14 -> HALPE 26.

    Args:
        wb_keypoints: shape=(133, 3), [x, y, confidence]
        aic_keypoints: shape=(14, 3), [x, y, confidence]

    Returns:
        shape=(26, 3), HALPE 26 keypoints
    """
    halpe26 = np.zeros((26, 3), dtype=np.float32)

    # WholeBody -> HALPE (body 17 points)
    halpe26[0:17] = wb_keypoints[0:17]

    # WholeBody -> HALPE (foot 6 points)
    halpe26[20] = wb_keypoints[17]   # LBigToe
    halpe26[22] = wb_keypoints[18]   # LSmallToe
    halpe26[24] = wb_keypoints[19]   # LHeel
    halpe26[21] = wb_keypoints[20]   # RBigToe
    halpe26[23] = wb_keypoints[21]   # RSmallToe
    halpe26[25] = wb_keypoints[22]   # RHeel

    # AIC -> HALPE (Head, Neck)
    halpe26[17] = aic_keypoints[12]  # Head (head_top)
    halpe26[18] = aic_keypoints[13]  # Neck

    # Hip center (computed)
    halpe26[19, :2] = (halpe26[11, :2] + halpe26[12, :2]) / 2
    halpe26[19, 2] = min(halpe26[11, 2], halpe26[12, 2])

    return halpe26


def draw_bbox(
    img: np.ndarray,
    bbox: np.ndarray,
    color: tuple = (0, 255, 255),
    thickness: int = 2,
) -> np.ndarray:
    """Draw bounding box on image.

    Args:
        img: BGR image
        bbox: [x1, y1, x2, y2, score]
        color: BGR color tuple (default: yellow)
        thickness: line thickness

    Returns:
        BGR image with bounding box drawn
    """
    img = img.copy()
    x1, y1, x2, y2, score = bbox[:5]
    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)
    label = f'{score:.2f}'
    cv2.putText(img, label, (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    return img


def draw_halpe26(
    img: np.ndarray,
    keypoints: np.ndarray,
    kpt_thr: float = 0.3,
) -> np.ndarray:
    """Draw HALPE 26 keypoints on image.

    Args:
        img: BGR image
        keypoints: shape=(26, 3), [x, y, confidence]
        kpt_thr: confidence threshold for drawing

    Returns:
        BGR image with keypoints drawn
    """
    img = img.copy()

    # Draw skeleton
    for i, j in HALPE26_SKELETON:
        if keypoints[i, 2] > kpt_thr and keypoints[j, 2] > kpt_thr:
            pt1 = (int(keypoints[i, 0]), int(keypoints[i, 1]))
            pt2 = (int(keypoints[j, 0]), int(keypoints[j, 1]))
            color = HALPE26_COLORS.get(i, (200, 200, 200))
            cv2.line(img, pt1, pt2, color, 2)

    # Draw keypoints
    for idx in range(26):
        if keypoints[idx, 2] > kpt_thr:
            x, y = int(keypoints[idx, 0]), int(keypoints[idx, 1])
            color = HALPE26_COLORS.get(idx, (200, 200, 200))
            cv2.circle(img, (x, y), 4, color, -1)
            cv2.putText(img, str(idx), (x + 5, y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

    return img


def parse_args():
    parser = argparse.ArgumentParser(
        description='Merge WholeBody + AIC to HALPE 26 keypoints')
    parser.add_argument('--img', type=str, required=True,
                        help='Input image path')
    parser.add_argument('--out-dir', type=str, default='output/feat-009',
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

    # 2. Person detection (once)
    print('Detecting persons...')
    mmdet_results = inference_detector(det_model, args.img)
    person_results = process_mmdet_results(mmdet_results, cat_id=1)
    print(f'Running WholeBody estimation... ({len(person_results)} persons)')

    # 3. WholeBody estimation
    wb_results, _ = inference_top_down_pose_model(
        wb_model, args.img, person_results, bbox_thr=0.3,
        format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)

    # 4. AIC estimation
    print(f'Running AIC estimation... ({len(person_results)} persons)')
    aic_results, _ = inference_top_down_pose_model(
        aic_model, args.img, person_results, bbox_thr=0.3,
        format='xyxy', dataset=aic_dataset, dataset_info=aic_dataset_info)

    # Verify result count
    if len(wb_results) != len(aic_results):
        raise RuntimeError(
            f'WholeBody results ({len(wb_results)}) and '
            f'AIC results ({len(aic_results)}) count mismatch')

    # 5. Merge to HALPE 26
    print('Merging to HALPE 26...')
    num_persons = len(wb_results)

    if num_persons == 0:
        print('No person detected.')
        all_halpe26 = np.zeros((0, 26, 3), dtype=np.float32)
    else:
        all_halpe26 = np.zeros((num_persons, 26, 3), dtype=np.float32)
        for i in range(num_persons):
            all_halpe26[i] = merge_to_halpe26(
                wb_results[i]['keypoints'],
                aic_results[i]['keypoints'])

    # 6. Save numpy array
    npy_path = os.path.join(args.out_dir, 'halpe26_keypoints.npy')
    np.save(npy_path, all_halpe26)
    print(f'Saved: {npy_path} (shape={all_halpe26.shape})')

    # 7. Print keypoints table
    for person_idx in range(num_persons):
        print(f'\n--- Person {person_idx} ---')
        print(f'{"idx":>3}  {"name":<12}  {"x":>8}  {"y":>8}  {"conf":>6}')
        for kp_idx in range(26):
            x, y, c = all_halpe26[person_idx, kp_idx]
            print(f'{kp_idx:>3}  {HALPE26_NAMES[kp_idx]:<12}  '
                  f'{x:>8.1f}  {y:>8.1f}  {c:>6.3f}')

    # 8. Visualize
    img = cv2.imread(args.img)
    for person_idx in range(num_persons):
        img = draw_halpe26(img, all_halpe26[person_idx])
    vis_path = os.path.join(args.out_dir, 'vis_halpe26.jpg')
    cv2.imwrite(vis_path, img)
    print(f'Saved: {vis_path}')


if __name__ == '__main__':
    main()
