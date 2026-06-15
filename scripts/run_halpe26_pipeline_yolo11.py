"""HALPE 26 unified pipeline with YOLO11x detector: video visualization + OpenPose JSON output."""
import argparse
import json
import os
import sys
import time


def _resolve_device(argv: list) -> str:
    """--device を先読みし、CUDA_VISIBLE_DEVICES を1枚に絞って内部デバイス名を返す。

    重い import（torch/ultralytics/mmpose）前に呼ぶこと。内部デバイスは常に cuda:0 に
    固定し、物理GPU選択は CUDA_VISIBLE_DEVICES へ委ねる（bug-005）。--device cuda:N の N は
    「現在見えている GPU リストの N 番目」として解決する。
    """
    raw = 'cuda:0'
    for i, a in enumerate(argv):
        if a == '--device' and i + 1 < len(argv):
            raw = argv[i + 1]
        elif a.startswith('--device='):
            raw = a.split('=', 1)[1]
    if raw == 'cpu':
        return 'cpu'
    if raw == 'cuda' or raw.startswith('cuda:'):
        suffix = raw.split(':', 1)[1] if ':' in raw else '0'
        if not suffix.isdigit():   # 負号・非数字を弾く（cuda:-1 / cuda:foo を排除）
            raise SystemExit(
                f"--device の値が不正です: {raw!r}。cpu / cuda / cuda:N (N>=0) を指定してください")
        idx = int(suffix)
        present = 'CUDA_VISIBLE_DEVICES' in os.environ
        visible = os.environ.get('CUDA_VISIBLE_DEVICES', '')
        if present and visible == '':
            raise SystemExit(
                "CUDA_VISIBLE_DEVICES='' (GPU 不可視) が指定されています。"
                "GPU を使うなら CUDA_VISIBLE_DEVICES を外すか、--device cpu を指定してください")
        if not present:
            # 外部マスクなし: 物理 index = N
            os.environ['CUDA_VISIBLE_DEVICES'] = str(idx)
        else:
            # 外部マスクあり: 見えるリストの N 番目を選ぶ
            devices = [d for d in visible.split(',') if d != '']
            if idx >= len(devices):
                raise SystemExit(
                    f"--device cuda:{idx} は CUDA_VISIBLE_DEVICES={visible!r} の範囲外です "
                    f"(見える GPU 数 = {len(devices)})")
            os.environ['CUDA_VISIBLE_DEVICES'] = devices[idx]
        return 'cuda:0'
    raise SystemExit(
        f"--device の値が不正です: {raw!r}。cpu / cuda / cuda:N (N>=0) を指定してください")


# 重い import より前に CUDA_VISIBLE_DEVICES を確定する（bug-005）。
INTERNAL_DEVICE = _resolve_device(sys.argv)

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


# ---------------------------------------------------------------------------
# BB dedup constants and functions (from compare_dedup_methods.py)
# ---------------------------------------------------------------------------

CONF_THR = 0.3

HALPE26_SIGMAS = np.array([
    0.026, 0.025, 0.025, 0.035, 0.035,      # Nose,LEye,REye,LEar,REar
    0.079, 0.079, 0.072, 0.072, 0.062, 0.062,  # shoulders,elbows,wrists
    0.107, 0.107, 0.087, 0.087, 0.089, 0.089,  # hips,knees,ankles
    0.10, 0.10, 0.10,                        # Head,Neck,Hip(center)
    0.089, 0.089, 0.089, 0.089, 0.089, 0.089,  # toes,heels
])


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


# ---------------------------------------------------------------------------
# YOLO11x detection
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """CLI引数をパースする。"""
    parser = argparse.ArgumentParser(
        description='HALPE 26 pipeline with YOLO11x detector')
    parser.add_argument('--video', type=str, required=True,
                        help='Input video path')
    parser.add_argument('--out-dir', type=str, default='output',
                        help='Output base directory')
    parser.add_argument('--device', type=str, default='cuda:0',
                        help='Inference device (cpu / cuda / cuda:N)。cuda:N は '
                             'CUDA_VISIBLE_DEVICES の見えるGPUリストのN番目を選び、内部は'
                             '常に cuda:0 で実行する（bug-005）')
    parser.add_argument('--mode', type=str, default='both',
                        choices=['both', 'video', 'json'],
                        help='Output mode: both, video, json')
    parser.add_argument('--bbox-thr', type=float, default=0.3,
                        help='Bounding box score threshold for person detection (default: 0.3)')
    parser.add_argument('--oks-thr', type=float, default=0.5,
                        help='OKS threshold for BB dedup detection (default: 0.5)')
    parser.add_argument('--kpt-thr', type=float, default=0.3,
                        help='Keypoint confidence threshold for drawing (0.0-1.0, default: 0.3)')
    parser.add_argument('--profile', action='store_true',
                        help='Enable per-step profiling')
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """統合パイプラインのメイン処理。"""
    args = parse_args()

    # Mode flags
    do_video = args.mode in ('both', 'video')
    do_json = args.mode in ('both', 'json')
    print(f'Output mode: {args.mode}')
    print(f'Detector: YOLO11x')
    print(f'Bbox threshold: {args.bbox_thr}, OKS dedup threshold: {args.oks_thr}')

    # 1. Initialize models
    print('Initializing models...')
    det_model = YOLO('checkpoints/yolo11x.pt')
    wb_model = init_pose_model(WB_CONFIG, WB_CHECKPOINT, device=INTERNAL_DEVICE)
    aic_model = init_pose_model(AIC_CONFIG, AIC_CHECKPOINT, device=INTERNAL_DEVICE)

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
            'merge': 0.0, 'dedup': 0.0, 'draw': 0.0, 'json': 0.0,
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

        # 5a. Person detection (YOLO11x) + bbox_thr pre-filter
        if args.profile:
            t = time.time()
        yolo_results = det_model(frame, device=INTERNAL_DEVICE, verbose=False)
        person_results = process_yolo11_results(yolo_results[0])
        person_results = [p for p in person_results if p['bbox'][4] >= args.bbox_thr]
        if args.profile:
            profile['det'] += time.time() - t

        # 5b. WholeBody estimation (bbox_thr=None, pre-filtered)
        if args.profile:
            t = time.time()
        wb_results, _ = inference_top_down_pose_model(
            wb_model, frame, person_results, bbox_thr=None,
            format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)
        if args.profile:
            profile['wb'] += time.time() - t

        # 5c. AIC estimation (bbox_thr=None, pre-filtered)
        if args.profile:
            t = time.time()
        aic_results, _ = inference_top_down_pose_model(
            aic_model, frame, person_results, bbox_thr=None,
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

        # 5d2. BB dedup (Plan A)
        if args.profile:
            t = time.time()
        all_bboxes = [wb_results[i]['bbox'] for i in range(len(all_halpe26))]
        n_persons = len(all_halpe26)

        if n_persons >= 2:
            oks_matrix = np.zeros((n_persons, n_persons))
            for i in range(n_persons):
                for j in range(i + 1, n_persons):
                    area_i = float((all_bboxes[i][2] - all_bboxes[i][0])
                                   * (all_bboxes[i][3] - all_bboxes[i][1]))
                    area_j = float((all_bboxes[j][2] - all_bboxes[j][0])
                                   * (all_bboxes[j][3] - all_bboxes[j][1]))
                    area = max(area_i, area_j)
                    oks_val = compute_oks_mutual(all_halpe26[i], all_halpe26[j], area)
                    oks_matrix[i, j] = oks_val
                    oks_matrix[j, i] = oks_val

            groups = build_dedup_groups(n_persons, oks_matrix, args.oks_thr)

            if groups:
                in_group = set()
                for g in groups:
                    in_group.update(g)

                new_halpe26 = []
                new_bboxes = []
                for i in range(n_persons):
                    if i not in in_group:
                        new_halpe26.append(all_halpe26[i])
                        new_bboxes.append(all_bboxes[i])

                for g in groups:
                    group_bboxes = [all_bboxes[i] for i in g]
                    kps_a, bbox_a = method_a(
                        frame, group_bboxes, wb_model, aic_model,
                        wb_dataset, wb_dataset_info,
                        aic_dataset, aic_dataset_info,
                        height, width)
                    new_halpe26.append(kps_a)
                    new_bboxes.append(bbox_a)

                all_halpe26 = new_halpe26
                all_bboxes = new_bboxes

        if args.profile:
            profile['dedup'] += time.time() - t

        # 5e. Video output
        if do_video:
            if args.profile:
                t = time.time()
            vis_frame = frame.copy()
            for i in range(len(all_halpe26)):
                vis_frame = draw_bbox(vis_frame, all_bboxes[i])
            for kps in all_halpe26:
                vis_frame = draw_halpe26(vis_frame, kps, kpt_thr=args.kpt_thr)
            writer.write(vis_frame)
            if args.profile:
                profile['draw'] += time.time() - t

        # 5f. JSON output
        if do_json:
            if args.profile:
                t = time.time()
            bbox_scores = [float(all_bboxes[i][4])
                          for i in range(len(all_halpe26))]
            bboxes = [all_bboxes[i][:4].tolist()
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
                           ('dedup', 'Dedup'),
                           ('draw', 'Draw'),
                           ('json', 'JSON')]:
            total_s = profile[key]
            avg_ms = (total_s / frame_idx * 1000) if frame_idx > 0 else 0
            ratio = (total_s / total_elapsed * 100) if total_elapsed > 0 else 0
            print(f'{label:<12} {total_s:>10.2f} {avg_ms:>10.1f} {ratio:>7.1f}%')


if __name__ == '__main__':
    main()
