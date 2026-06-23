"""静止画1枚のポーズ推定診断ツール (feat-060)。

1枚の静止画に対し、以下2経路を実行して結果を並べて出力し、キーポイントが
出力されない原因（YOLO 検出失敗 / ViTPose 自体の推定失敗）を切り分ける CLI 診断ツール:

  A. YOLO検出経路    : YOLO11x で person を検出し、検出数・各 BB の score を出力 (FR-001)
  B. 全画像1BB経路   : 画像全体を1BBとして ViTPose(WB+AIC) に流し HALPE26 を推定 (FR-002)
  C. 可視化PNG       : 左=YOLO検出 / 右=全画像1BB推論 の2パネル PNG を保存 (FR-003)
  D. 総合判定        : A/B の結果から切り分け結論を出力 (FR-004)

既存の merge_halpe26.py / run_halpe26_pipeline_yolo11.py は変更せず再利用・参照する。

実行例（プロジェクトルートから）:
    uv run python scripts/diagnose_pose.py path/to/image.png
"""
import argparse
import os
import sys


def _resolve_device(argv: list) -> str:
    """--device を先読みし、CUDA_VISIBLE_DEVICES を1枚に絞って内部デバイス名を返す。

    run_halpe26_pipeline_yolo11.py の _resolve_device と同仕様（ADR-3: import せず自前定義）。
    重い import（torch/ultralytics/mmpose）前に呼ぶこと。内部デバイスは常に cuda:0 に
    固定し、物理GPU選択は CUDA_VISIBLE_DEVICES へ委ねる（bug-005 と同方針）。
    不正値は SystemExit を raise する（トップレベルで [ERROR] 形式へ整形して exit 1）。
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
        if not suffix.isdigit():
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
            os.environ['CUDA_VISIBLE_DEVICES'] = str(idx)
        else:
            devices = [d for d in visible.split(',') if d != '']
            if idx >= len(devices):
                raise SystemExit(
                    f"--device cuda:{idx} は CUDA_VISIBLE_DEVICES={visible!r} の範囲外です "
                    f"(見える GPU 数 = {len(devices)})")
            os.environ['CUDA_VISIBLE_DEVICES'] = devices[idx]
        return 'cuda:0'
    raise SystemExit(
        f"--device の値が不正です: {raw!r}。cpu / cuda / cuda:N (N>=0) を指定してください")


# 重い import より前に CUDA_VISIBLE_DEVICES を確定する（bug-005 と同方針）。
# --device 不正時は SystemExit を [ERROR] 形式へ整形して exit 1 する（要求 1.4 信頼性）。
try:
    INTERNAL_DEVICE = _resolve_device(sys.argv)
except SystemExit as e:
    print(f'[ERROR] {e}')
    sys.exit(1)

import cv2
import numpy as np
import torch
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ultralytics import YOLO
from mmpose.apis import inference_top_down_pose_model, init_pose_model
from mmpose.datasets import DatasetInfo

sys.path.insert(0, os.path.dirname(__file__))
from merge_halpe26 import (WB_CONFIG, WB_CHECKPOINT, AIC_CONFIG, AIC_CHECKPOINT,
                           HALPE26_NAMES, merge_to_halpe26, draw_halpe26, draw_bbox)

YOLO_CHECKPOINT = 'checkpoints/yolo11x.pt'
PERSON_CLS = 0  # YOLO COCO person クラス ID


# ---------------- CLI 引数チェッカ ----------------
def _check_thr(v: str) -> float:
    fv = float(v)
    if not (0.0 <= fv <= 1.0):
        raise argparse.ArgumentTypeError(f"threshold must be in [0.0, 1.0], got {fv}")
    return fv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Diagnose why pose estimation produced no keypoints for a single '
                    'still image: report YOLO person detection result and whole-image '
                    '1BB ViTPose result side by side.')
    parser.add_argument('image', type=str, help='Input still image path')
    parser.add_argument('--out', type=str, default=None,
                        help='Output PNG path (default: <image_stem>_pose_diagnostic.png)')
    parser.add_argument('--device', type=str, default='cuda:0',
                        help='Inference device (cpu / cuda / cuda:N)。cuda:N は '
                             'CUDA_VISIBLE_DEVICES の見えるGPUリストのN番目を選び、内部は'
                             '常に cuda:0 で実行する')
    parser.add_argument('--bbox-thr', type=_check_thr, default=0.3,
                        help='YOLO person BB score threshold ([0.0,1.0], default 0.3)')
    parser.add_argument('--kpt-thr', type=_check_thr, default=0.3,
                        help='Keypoint confidence threshold ([0.0,1.0], default 0.3)。'
                             '有効点は conf > kpt_thr（超過）で数える')
    return parser.parse_args()


# ---------------- モデルロード ----------------
def load_models(device: str) -> tuple:
    """WB/AIC ポーズモデルと dataset 情報をロードする（analyze_clothing_color.py と同構造）。"""
    wb_model = init_pose_model(WB_CONFIG, WB_CHECKPOINT, device=device)
    aic_model = init_pose_model(AIC_CONFIG, AIC_CHECKPOINT, device=device)
    wb_dataset = wb_model.cfg.data['test']['type']
    wb_dataset_info = DatasetInfo(wb_model.cfg.data['test']['dataset_info'])
    aic_dataset = aic_model.cfg.data['test']['type']
    aic_dataset_info = DatasetInfo(aic_model.cfg.data['test']['dataset_info'])
    return (wb_model, aic_model, wb_dataset, wb_dataset_info,
            aic_dataset, aic_dataset_info)


# ---------------- §A YOLO検出経路 (FR-001) ----------------
def run_yolo_detection(det_model, frame: np.ndarray, bbox_thr: float) -> tuple:
    """YOLO11x で person を検出する。

    戻り値: (person_boxes, n_total)
      person_boxes : bbox_thr 以上の BB（np.ndarray([x1,y1,x2,y2,score])）の score 降順 list
      n_total      : 閾値適用前の person BB 総数
    OOM 以外の推論例外は ([], 0) を返し YOLO detection を FAILED 扱いにする（exit しない）。
    """
    try:
        results = det_model(frame, device=INTERNAL_DEVICE, verbose=False)
        boxes = results[0].boxes
    except torch.cuda.OutOfMemoryError:
        raise  # 致命: main で [ERROR] exit 1
    except Exception as e:
        print(f'[WARN] YOLO 推論例外: {type(e).__name__}: {e}')
        return [], 0

    person_boxes_all = []
    for i in range(len(boxes)):
        if int(boxes.cls[i]) == PERSON_CLS:
            x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy()
            score = float(boxes.conf[i].cpu())
            person_boxes_all.append(
                np.array([x1, y1, x2, y2, score], dtype=np.float32))
    person_boxes = [b for b in person_boxes_all if b[4] >= bbox_thr]
    person_boxes.sort(key=lambda b: b[4], reverse=True)
    return person_boxes, len(person_boxes_all)


def report_yolo(person_boxes: list, n_total: int, bbox_thr: float) -> bool:
    """YOLO 検出結果を標準出力に報告し、成否（bool）を返す。"""
    n_kept = len(person_boxes)
    n_excluded = n_total - n_kept
    print(f'[INFO] YOLO person BB: total={n_total}, '
          f'>= thr({bbox_thr})={n_kept}, excluded={n_excluded}')
    for k, b in enumerate(person_boxes, 1):
        print(f'[INFO]   #{k}: [x1={b[0]:.1f}, y1={b[1]:.1f}, '
              f'x2={b[2]:.1f}, y2={b[3]:.1f}, score={b[4]:.3f}]')
    if n_excluded > 0:
        print(f'[WARN] {n_excluded} 個の person BB が bbox_thr 未満で除外されました')
    success = n_kept >= 1
    if success:
        print(f'[RESULT] YOLO detection: SUCCESS ({n_kept} boxes)')
    else:
        print('[RESULT] YOLO detection: FAILED (0 boxes >= thr)')
    return success


# ---------------- §B 全画像1BB経路 (FR-002) ----------------
def estimate_halpe26_fullframe_safe(
    wb_model, aic_model, frame: np.ndarray,
    wb_dataset: str, wb_dataset_info,
    aic_dataset: str, aic_dataset_info,
) -> "np.ndarray | None":
    """画像全体を1BBとして WB+AIC 推論し HALPE26 (26,3) を返す。

    推論結果が空、または OOM 以外の例外時は None を返す（analyze_clothing_color.py の
    estimate_halpe26_fullframe は空時に sys.exit(1) するため流用せず分離実装、ADR-1）。
    CUDA OOM だけは致命エラーとして再 raise する（要求 1.4 信頼性）。
    """
    h, w = frame.shape[:2]
    person = [{'bbox': np.array([0, 0, w, h, 1.0], dtype=np.float32)}]
    try:
        wb_results, _ = inference_top_down_pose_model(
            wb_model, frame, person, bbox_thr=None,
            format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)
        aic_results, _ = inference_top_down_pose_model(
            aic_model, frame, person, bbox_thr=None,
            format='xyxy', dataset=aic_dataset, dataset_info=aic_dataset_info)
    except torch.cuda.OutOfMemoryError:
        raise  # 致命: main で [ERROR] exit 1
    except Exception as e:
        print(f'[WARN] ViTPose 推論例外: {type(e).__name__}: {e}')
        return None
    if len(wb_results) == 0 or len(aic_results) == 0:
        return None
    return merge_to_halpe26(wb_results[0]['keypoints'], aic_results[0]['keypoints'])


def report_vitpose(halpe26: np.ndarray, kpt_thr: float) -> bool:
    """全画像1BB推論結果を標準出力に報告し、成否（bool）を返す。"""
    if halpe26 is None:
        print('[RESULT] ViTPose fullframe: FAILED (推論結果が空 or 推論例外)')
        return False
    print('[INFO] HALPE26 keypoints (index: name = (x, y, conf)):')
    for idx in range(26):
        x, y, conf = halpe26[idx]
        print(f'[INFO]   {idx:2d}: {HALPE26_NAMES[idx]:<10s} = '
              f'({x:.3f}, {y:.3f}, {conf:.3f})')
    m = int((halpe26[:, 2] > kpt_thr).sum())  # > で統一（draw_halpe26 と同判定）
    success = m >= 1
    if success:
        print(f'[RESULT] ViTPose fullframe: SUCCESS ({m}/26 kpts > thr)')
    else:
        print(f'[RESULT] ViTPose fullframe: FAILED (有効点0/26, > thr)')
    return success


# ---------------- §C 可視化PNG (FR-003) ----------------
def render_diagnostic_png(
    frame: np.ndarray, person_boxes: list, halpe26: np.ndarray,
    kpt_thr: float, out_path: str,
) -> None:
    """左=YOLO検出BB / 右=全画像1BB枠+スケルトン の2パネル PNG を保存する。

    halpe26 が None の場合、右パネルは全画像1BB枠のみ描画する。
    """
    h, w = frame.shape[:2]
    left = frame.copy()
    for b in person_boxes:
        left = draw_bbox(left, b, color=(0, 255, 0))  # 緑枠（score ラベル付き）

    right = frame.copy()
    # 全画像1BB枠は score 表示不要かつラベルが画像外になるため draw_bbox を使わず枠のみ。
    cv2.rectangle(right, (0, 0), (w - 1, h - 1), (255, 255, 0), 2)  # シアン(BGR)
    if halpe26 is not None:
        right = draw_halpe26(right, halpe26, kpt_thr=kpt_thr)

    n_kept = len(person_boxes)
    if halpe26 is None:
        right_title = 'fullframe 1BB: FAILED'
    else:
        m = int((halpe26[:, 2] > kpt_thr).sum())
        right_title = f'fullframe 1BB ({m}/26 kpts > thr)'

    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    axes[0].imshow(cv2.cvtColor(left, cv2.COLOR_BGR2RGB))
    axes[0].set_title(f'YOLO det ({n_kept} boxes)')
    axes[0].axis('off')
    axes[1].imshow(cv2.cvtColor(right, cv2.COLOR_BGR2RGB))
    axes[1].set_title(right_title)
    axes[1].axis('off')
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches='tight')
    plt.close(fig)


# ---------------- §D 総合判定 (FR-004) ----------------
def print_verdict(yolo_success: bool, vitpose_success: bool) -> None:
    """FR-001 / FR-002 の結果から切り分け結論を出力する。"""
    if not vitpose_success:
        print('[VERDICT] ViTPose 自体が当該画像で推定失敗'
              '（YOLO の成否によらずポーズが出ない）')
    elif not yolo_success:
        print('[VERDICT] 原因は YOLO 検出失敗の可能性が高い'
              '（ViTPose は全画像1BBで推定成功）')
    else:
        print('[VERDICT] 両経路とも成功。パイプライン側の閾値/連携を確認のこと')


# ---------------- main ----------------
def main() -> None:
    args = parse_args()

    out_path = (args.out if args.out is not None
                else os.path.splitext(args.image)[0] + '_pose_diagnostic.png')

    frame = cv2.imread(args.image)
    if frame is None:
        print(f'[ERROR] 画像を読み込めません: {args.image}')
        sys.exit(1)
    h, w = frame.shape[:2]
    print(f'[INFO] 入力画像: {args.image} ({w}x{h})')

    # モデルロード（致命エラーは [ERROR] exit 1）
    print('[INFO] モデルをロード中...')
    try:
        det_model = YOLO(YOLO_CHECKPOINT)
        (wb_model, aic_model, wb_dataset, wb_dataset_info,
         aic_dataset, aic_dataset_info) = load_models(INTERNAL_DEVICE)
    except Exception as e:
        print(f'[ERROR] モデルロード失敗: {type(e).__name__}: {e}')
        sys.exit(1)
    print('[INFO] モデルロード完了')

    # §A YOLO検出経路 / §B 全画像1BB経路（CUDA OOM のみ致命扱い）
    try:
        person_boxes, n_total = run_yolo_detection(det_model, frame, args.bbox_thr)
        yolo_success = report_yolo(person_boxes, n_total, args.bbox_thr)
        halpe26 = estimate_halpe26_fullframe_safe(
            wb_model, aic_model, frame, wb_dataset, wb_dataset_info,
            aic_dataset, aic_dataset_info)
        vitpose_success = report_vitpose(halpe26, args.kpt_thr)
    except torch.cuda.OutOfMemoryError as e:
        print(f'[ERROR] CUDA OOM: {e}')
        sys.exit(1)

    # §C 可視化PNG（保存失敗は致命扱い）
    try:
        render_diagnostic_png(frame, person_boxes, halpe26, args.kpt_thr, out_path)
    except Exception as e:
        if os.path.exists(out_path):
            os.remove(out_path)
        print(f'[ERROR] PNG保存失敗: {type(e).__name__}: {e}')
        sys.exit(1)
    print(f'[INFO] 診断PNGを保存: {out_path}')

    # §D 総合判定
    print_verdict(yolo_success, vitpose_success)


if __name__ == '__main__':
    main()
