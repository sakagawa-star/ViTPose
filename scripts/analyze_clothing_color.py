"""服パッチ静止画からの服色特徴量分析・HSVレンジ提案ツール (feat-052)。

対象の服が写った静止画1枚から ViTPose（画像全体を1BBとして推論）で胴体ROIを
切り出し、ROI内の HSV 色特徴量を測定（出力a）し、postprocess_pink_id.py 用の
推奨 FIXED_HSV_RANGES / MIN_PINK_RATIO を提案（出力b）する CLI 診断ツール。

既存の merge_halpe26.py / postprocess_pink_id.py は変更せず再利用する。

実行例（プロジェクトルートから）:
    uv run python scripts/analyze_clothing_color.py testdata/E0014-01.png
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from mmpose.apis import inference_top_down_pose_model, init_pose_model
from mmpose.datasets import DatasetInfo

from merge_halpe26 import (WB_CONFIG, WB_CHECKPOINT, AIC_CONFIG, AIC_CHECKPOINT,
                           merge_to_halpe26)
from postprocess_pink_id import (build_keypoint_rect_roi, compute_pink_ratio,
                                 FIXED_HSV_RANGES, MIN_PINK_RATIO)


# ---------------- CLI 引数チェッカ (ADR-6: 本スクリプトに新規定義) ----------------
def _check_conf(v: str) -> float:
    fv = float(v)
    if not (0.0 <= fv <= 1.0):
        raise argparse.ArgumentTypeError(f"kpt-conf-min must be in [0.0, 1.0], got {fv}")
    return fv


def _check_area(v: str) -> int:
    iv = int(v)
    if iv < 1:
        raise argparse.ArgumentTypeError(f"min-roi-area must be >= 1, got {iv}")
    return iv


def _check_percentile(v: str) -> float:
    fv = float(v)
    if not (0.0 <= fv <= 50.0):
        raise argparse.ArgumentTypeError(f"percentile must be in [0.0, 50.0], got {fv}")
    return fv


def _check_uint8(v: str) -> int:
    iv = int(v)
    if not (0 <= iv <= 255):
        raise argparse.ArgumentTypeError(f"value must be in [0, 255], got {iv}")
    return iv


def _check_ratio(v: str) -> float:
    fv = float(v)
    if not (0.0 <= fv <= 1.0):
        raise argparse.ArgumentTypeError(f"threshold must be in [0.0, 1.0], got {fv}")
    return fv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Analyze clothing color from one or more still images and '
                    'propose HSV ranges for postprocess_pink_id.py')
    parser.add_argument('images', type=str, nargs='+', help='Input still image path(s)')
    parser.add_argument('--out', type=str, default=None,
                        help='Output PNG path (single-image mode only; '
                             'default: <image_stem>_color_analysis.png). Ignored in multi-image mode')
    parser.add_argument('--json-out', type=str, default=None,
                        help='Output HSV config JSON path (single-image default: '
                             '<image_stem>_hsv_config.json; multi-image default: '
                             '<first_image_stem>_pooled_hsv_config.json)')
    parser.add_argument('--device', type=str, default='cuda:0',
                        help='Inference device (default: cuda:0)')
    parser.add_argument('--kpt-conf-min', type=_check_conf, default=0.3,
                        help='Min torso keypoint confidence ([0.0,1.0], default 0.3)')
    parser.add_argument('--min-roi-area', type=_check_area, default=200,
                        help='Min torso ROI area (>=1, default 200)')
    parser.add_argument('--percentile', type=_check_percentile, default=5.0,
                        help='Percentile width for range proposal ([0.0,50.0], default 5.0)')
    parser.add_argument('--sat-min', type=_check_uint8, default=20,
                        help='Saturation lower bound for chroma mask ([0,255], default 20)')
    parser.add_argument('--val-min', type=_check_uint8, default=60,
                        help='Value lower bound for chroma mask ([0,255], default 60)')
    parser.add_argument('--threshold', type=_check_ratio, default=MIN_PINK_RATIO,
                        help='Per-image pink_ratio PASS threshold for multi-image mode '
                             '([0.0,1.0], default 0.03)')
    parser.add_argument('--chroma-regime-min', type=_check_ratio, default=0.4,
                        help='chroma_ratio がこの値以上なら chromatic、未満なら '
                             'achromatic としてレンジを提案する ([0.0,1.0], default 0.4)。'
                             'default 0.4 は --sat-min=20 / --val-min=60 前提。'
                             'sat/val を変えたらこの値も再調整すること')
    return parser.parse_args()


# ---------------- モデル・推論 (FR-001) ----------------
def load_models(device: str) -> tuple:
    wb_model = init_pose_model(WB_CONFIG, WB_CHECKPOINT, device=device)
    aic_model = init_pose_model(AIC_CONFIG, AIC_CHECKPOINT, device=device)
    wb_dataset = wb_model.cfg.data['test']['type']
    wb_dataset_info = DatasetInfo(wb_model.cfg.data['test']['dataset_info'])
    aic_dataset = aic_model.cfg.data['test']['type']
    aic_dataset_info = DatasetInfo(aic_model.cfg.data['test']['dataset_info'])
    return (wb_model, aic_model, wb_dataset, wb_dataset_info,
            aic_dataset, aic_dataset_info)


def estimate_halpe26_fullframe(
    wb_model, aic_model, frame: np.ndarray,
    wb_dataset: str, wb_dataset_info,
    aic_dataset: str, aic_dataset_info,
) -> np.ndarray:
    """画像全体を1BBとして WB+AIC 推論し HALPE26 (26,3) を返す。"""
    h, w = frame.shape[:2]
    person = [{'bbox': np.array([0, 0, w, h, 1.0], dtype=np.float32)}]
    wb_results, _ = inference_top_down_pose_model(
        wb_model, frame, person, bbox_thr=None,
        format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)
    aic_results, _ = inference_top_down_pose_model(
        aic_model, frame, person, bbox_thr=None,
        format='xyxy', dataset=aic_dataset, dataset_info=aic_dataset_info)
    if len(wb_results) == 0 or len(aic_results) == 0:
        print('[ERROR] 推論結果が空です（人物BBに対するキーポイントが得られませんでした）')
        sys.exit(1)
    return merge_to_halpe26(wb_results[0]['keypoints'], aic_results[0]['keypoints'])


# ---------------- ROI構築 (FR-002 / FR-007) ----------------
def build_torso_roi(
    halpe26: np.ndarray, width: int, height: int,
    conf_min: float, area_min: int,
) -> tuple:
    """胴体4点で ROI を構築。失敗時は画像全体へフォールバック。"""
    kpts_flat = halpe26.flatten().tolist()
    box, status = build_keypoint_rect_roi(kpts_flat, width, height, conf_min, area_min)
    if status == 'ok':
        return box, 'torso'
    print(f'[WARN] 胴体ROI構築失敗 (status={status})。画像全体をROIとして測定します')
    return (0, 0, width, height), 'fullframe'


# ---------------- 色測定 (FR-003) ----------------
def extract_chroma_hsv(roi_bgr: np.ndarray, sat_min: int, val_min: int) -> tuple:
    """無彩色除外後の有彩色画素 Hc, Sc, Vc と chroma_ratio を返す (M-4 共用ヘルパ)。"""
    if roi_bgr.size == 0:
        empty = np.array([], dtype=np.uint8)
        return empty, empty, empty, 0.0
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    H = hsv[:, :, 0].ravel()
    S = hsv[:, :, 1].ravel()
    V = hsv[:, :, 2].ravel()
    mask = (S >= sat_min) & (V >= val_min)
    total = H.size
    chroma_ratio = float(np.count_nonzero(mask)) / total if total > 0 else 0.0
    return H[mask], S[mask], V[mask], chroma_ratio


def extract_all_hsv(roi_bgr: np.ndarray) -> tuple:
    """ROIの全画素 H,S,V を1次元配列で返す（マスクなし、feat-059）。空ROIなら空配列3つ。"""
    if roi_bgr.size == 0:
        empty = np.array([], dtype=np.uint8)
        return empty, empty, empty
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    return hsv[:, :, 0].ravel(), hsv[:, :, 1].ravel(), hsv[:, :, 2].ravel()


def decide_color_regime(chroma_ratio: float, chroma_regime_min: float) -> str:
    """chroma_ratio を閾値判定して 'chromatic' / 'achromatic' を返す (feat-059)。

    閾値判定のみで例外分岐は持たない（chroma_ratio==0.0 を特別扱いしない）。
    """
    return 'chromatic' if chroma_ratio >= chroma_regime_min else 'achromatic'


def propose_achromatic_ranges(
    H_all: np.ndarray, S_all: np.ndarray, V_all: np.ndarray, percentile: float,
) -> tuple:
    """全画素 S/V の percentile で H全域・S/V上下限を囲む achromatic レンジを返す (feat-059)。

    色相 H はノイズ的で意味が薄いため全域 [0,179] に開き、S・V を上下限とも
    データ駆動（白＝低S高V・黒＝低S低V が分布に追従）。
    戻り値: (proposed_ranges, s_lo, s_hi, v_lo, v_hi)。空配列なら ([], 0, 0, 0, 0)。
    """
    if len(S_all) == 0:
        return [], 0, 0, 0, 0
    p_lo, p_hi = percentile, 100.0 - percentile
    s_lo = int(round(float(np.percentile(S_all, p_lo))))
    s_hi = int(round(float(np.percentile(S_all, p_hi))))
    v_lo = int(round(float(np.percentile(V_all, p_lo))))
    v_hi = int(round(float(np.percentile(V_all, p_hi))))
    proposed = [((0, s_lo, v_lo), (179, s_hi, v_hi))]
    return proposed, s_lo, s_hi, v_lo, v_hi


def compute_hsv_stats(
    roi_bgr: np.ndarray, sat_min: int, val_min: int, percentile: float,
) -> dict:
    """H/S/V パーセンタイル・chroma_ratio に加え、可視化用に有彩色画素 Hc/Sc/Vc も返す。

    n_chroma==0 のとき H/S/V の 9 キーは None、chroma_ratio は 0.0、Hc/Sc/Vc は空配列。
    """
    Hc, Sc, Vc, chroma_ratio = extract_chroma_hsv(roi_bgr, sat_min, val_min)
    stats = {'chroma_ratio': chroma_ratio, 'Hc': Hc, 'Sc': Sc, 'Vc': Vc}
    keys = ['H_lo', 'H_med', 'H_hi', 'S_lo', 'S_med', 'S_hi', 'V_lo', 'V_med', 'V_hi']
    if len(Hc) == 0:
        stats.update({k: None for k in keys})
        return stats
    p_low, p_high = percentile, 100.0 - percentile

    def trio(arr):
        return (int(round(float(np.percentile(arr, p_low)))),
                int(round(float(np.percentile(arr, 50.0)))),
                int(round(float(np.percentile(arr, p_high)))))

    stats['H_lo'], stats['H_med'], stats['H_hi'] = trio(Hc)
    stats['S_lo'], stats['S_med'], stats['S_hi'] = trio(Sc)
    stats['V_lo'], stats['V_med'], stats['V_hi'] = trio(Vc)
    return stats


# ---------------- レンジ・マスク (FR-005) ----------------
def build_mask_for_ranges(roi_bgr: np.ndarray, ranges: list) -> np.ndarray:
    """各レンジで cv2.inRange → OR 合成した2値マスク (uint8) を返す。ranges 空なら全0。"""
    h, w = roi_bgr.shape[:2]
    mask_total = np.zeros((h, w), dtype=np.uint8)
    if not ranges or roi_bgr.size == 0:
        return mask_total
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    for lo, hi in ranges:
        lo_np = np.array(lo, dtype=np.uint8)
        hi_np = np.array(hi, dtype=np.uint8)
        mask_total = cv2.bitwise_or(mask_total, cv2.inRange(hsv, lo_np, hi_np))
    return mask_total


def compute_ratio_for_ranges(roi_bgr: np.ndarray, ranges: list) -> float:
    """compute_pink_ratio の一般化版（任意レンジ）。ranges 空なら 0.0。"""
    if not ranges or roi_bgr.size == 0:
        return 0.0
    mask = build_mask_for_ranges(roi_bgr, ranges)
    total = roi_bgr.shape[0] * roi_bgr.shape[1]
    return int(np.count_nonzero(mask)) / total if total > 0 else 0.0


def propose_ranges_from_chroma(
    Hc: np.ndarray, Sc: np.ndarray, Vc: np.ndarray, percentile: float,
) -> tuple:
    """クロマ画素配列(Hc/Sc/Vc)から循環統計で推奨 FIXED_HSV_RANGES を算出する (feat-055)。

    複数画像のクロマ画素を結合した配列にも適用できる（BGR往復変換不要）。
    戻り値: (proposed_ranges, s_lo, v_lo)。有彩色画素なし(len(Hc)==0)なら ([], 0, 0)。
    """
    if len(Hc) == 0:
        return [], 0, 0
    # H は色相環（OpenCV H:[0,179] が 0-360° = 実角度 H×2°）。循環平均を中心に相対化する。
    theta = Hc.astype(float) * 2.0 * np.pi / 180.0
    H_center = (np.arctan2(np.sin(theta).mean(), np.cos(theta).mean())
                * 180.0 / (2.0 * np.pi)) % 180.0
    if H_center >= 180.0:  # 浮動小数点誤差で % が 180.0 を返す稀なケースを 0 へ正規化
        H_center = 0.0
    rel = ((Hc.astype(float) - H_center + 90.0) % 180.0) - 90.0
    rel_lo = float(np.percentile(rel, percentile))
    rel_hi = float(np.percentile(rel, 100.0 - percentile))
    H_lo_i = int(round(H_center + rel_lo))
    H_hi_i = int(round(H_center + rel_hi))
    s_lo = int(round(float(np.percentile(Sc, percentile))))  # S下限のみデータ駆動 (ADR-4)
    v_lo = int(round(float(np.percentile(Vc, percentile))))  # V下限のみデータ駆動 (ADR-4)
    if 0 <= H_lo_i and H_hi_i <= 179:
        proposed = [((H_lo_i, s_lo, v_lo), (H_hi_i, 255, 255))]
    elif H_lo_i < 0:  # 下端が179側へ回り込む（赤・ピンク）
        proposed = [((0, s_lo, v_lo), (H_hi_i, 255, 255)),
                    ((180 + H_lo_i, s_lo, v_lo), (179, 255, 255))]
    else:  # H_hi_i > 179: 上端が0側へ回り込む
        proposed = [((H_lo_i, s_lo, v_lo), (179, 255, 255)),
                    ((0, s_lo, v_lo), (H_hi_i - 180, 255, 255))]
    proposed = [r for r in proposed if r[0][0] <= r[1][0]]  # 反転タプル(lo>hi)を破棄
    return proposed, s_lo, v_lo


def propose_hsv_ranges(
    roi_bgr: np.ndarray, sat_min: int, val_min: int, percentile: float,
) -> tuple:
    """循環統計で色相環またぎに対応した推奨 FIXED_HSV_RANGES を算出する（単一ROI版ラッパ）。

    戻り値: (proposed_ranges, s_lo, v_lo, proposed_ratio)。有彩色画素なしなら ([], 0, 0, 0.0)。
    """
    Hc, Sc, Vc, _ = extract_chroma_hsv(roi_bgr, sat_min, val_min)
    proposed, s_lo, v_lo = propose_ranges_from_chroma(Hc, Sc, Vc, percentile)
    proposed_ratio = compute_ratio_for_ranges(roi_bgr, proposed)
    return proposed, s_lo, v_lo, proposed_ratio


# ---------------- HSV 設定ファイル出力 (feat-054) ----------------
def build_hsv_config_dict(proposed_ranges: list, min_pink_ratio: float) -> dict:
    """proposed_ranges を feat-053 互換の設定 dict へ変換する。tuple → list、値は int 維持。"""
    return {
        'fixed_hsv_ranges': [[list(lo), list(hi)] for lo, hi in proposed_ranges],
        'min_pink_ratio': float(min_pink_ratio),
    }


def write_hsv_config(path: str, proposed_ranges: list, min_pink_ratio: float) -> None:
    """設定 dict を postprocess_pink_id.py --hsv-config 互換の JSON ファイルへ書き出す。

    scripts/conf/*.json と同じ compact 整形（1 レンジ = 1 行）で書く。
    """
    config = build_hsv_config_dict(proposed_ranges, min_pink_ratio)
    range_lines = ',\n'.join('    ' + json.dumps(r) for r in config['fixed_hsv_ranges'])
    text = (
        '{\n'
        '  "fixed_hsv_ranges": [\n'
        f'{range_lines}\n'
        '  ],\n'
        f'  "min_pink_ratio": {json.dumps(config["min_pink_ratio"])}\n'
        '}\n'
    )
    with open(path, 'w') as f:
        f.write(text)


# ---------------- 可視化 (FR-004) ----------------
def render_analysis_png(
    frame: np.ndarray, roi_box: tuple, stats: dict,
    proposed_ranges: list, current_ratio: float, proposed_ratio: float,
    out_path: str, regime: str = 'chromatic', all_hsv: tuple = None,
) -> None:
    """元画像+ROI枠・現状/推奨マスク・H/S/Vヒストグラムを1枚のPNGに合成して保存する。

    regime=='achromatic' のとき下段は全画素 H/S/V を表示し、S/V 境界線は
    proposed_ranges[0] から取得する（feat-059）。all_hsv=(H_all,S_all,V_all)。
    """
    x1, y1, x2, y2 = roi_box
    roi_bgr = frame[y1:y2, x1:x2]
    cur_mask = build_mask_for_ranges(roi_bgr, FIXED_HSV_RANGES)
    prop_mask = build_mask_for_ranges(roi_bgr, proposed_ranges)
    has_chroma = stats.get('H_lo') is not None
    Hc, Sc, Vc = stats.get('Hc'), stats.get('Sc'), stats.get('Vc')

    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    axes[0, 0].imshow(rgb)
    axes[0, 0].add_patch(Rectangle((x1, y1), x2 - x1, y2 - y1,
                                   edgecolor='lime', facecolor='none', linewidth=2))
    axes[0, 0].set_title('input + ROI')
    axes[0, 0].axis('off')

    axes[0, 1].imshow(cur_mask, cmap='gray')
    axes[0, 1].set_title(f'current mask (ratio={current_ratio:.4f})')
    axes[0, 1].axis('off')

    axes[0, 2].imshow(prop_mask, cmap='gray')
    axes[0, 2].set_title(
        f'proposed mask (ratio={proposed_ratio:.4f})' if proposed_ranges
        else 'proposed: N/A')
    axes[0, 2].axis('off')

    if regime == 'achromatic':
        # 全画素 H/S/V を表示。S/V 境界線は proposed_ranges[0] から取得（feat-059）。
        H_all, S_all, V_all = all_hsv if all_hsv is not None else (
            np.array([]), np.array([]), np.array([]))
        axes[1, 0].hist(H_all, bins=180, range=(0, 180), color='red')
        axes[1, 0].set_title('H (all px, full range)')
        axes[1, 1].hist(S_all, bins=256, range=(0, 256), color='green')
        axes[1, 1].set_title('S (all px)')
        axes[1, 2].hist(V_all, bins=256, range=(0, 256), color='blue')
        axes[1, 2].set_title('V (all px)')
        if proposed_ranges:
            s_lo, s_hi = proposed_ranges[0][0][1], proposed_ranges[0][1][1]
            v_lo, v_hi = proposed_ranges[0][0][2], proposed_ranges[0][1][2]
            for x in (s_lo, s_hi):
                axes[1, 1].axvline(x, color='k', linestyle='--', linewidth=0.8)
            for x in (v_lo, v_hi):
                axes[1, 2].axvline(x, color='k', linestyle='--', linewidth=0.8)
    elif has_chroma:
        axes[1, 0].hist(Hc, bins=180, range=(0, 180), color='red')
        axes[1, 0].set_title('H (chroma px)')
        for lo, hi in proposed_ranges:
            axes[1, 0].axvline(lo[0], color='k', linestyle='--', linewidth=0.8)
            axes[1, 0].axvline(hi[0], color='k', linestyle='--', linewidth=0.8)
        axes[1, 1].hist(Sc, bins=256, range=(0, 256), color='green')
        axes[1, 1].set_title('S (chroma px)')
        axes[1, 2].hist(Vc, bins=256, range=(0, 256), color='blue')
        axes[1, 2].set_title('V (chroma px)')
        if proposed_ranges:
            axes[1, 1].axvline(proposed_ranges[0][0][1], color='k', linestyle='--', linewidth=0.8)
            axes[1, 2].axvline(proposed_ranges[0][0][2], color='k', linestyle='--', linewidth=0.8)
    else:
        for j in range(3):
            axes[1, j].text(0.5, 0.5, 'no chroma pixels', ha='center', va='center')
            axes[1, j].axis('off')

    fig.suptitle(f'proposed FIXED_HSV_RANGES = {proposed_ranges}', fontsize=10)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches='tight')
    plt.close(fig)


def run_single_image(image: str, args: argparse.Namespace, models: tuple) -> None:
    """単一画像モード（feat-054 相当）。モデルは呼び出し側でロード済みのものを受け取る。"""
    (wb_model, aic_model, wb_dataset, wb_dataset_info,
     aic_dataset, aic_dataset_info) = models
    if args.out is None:
        out_path = os.path.splitext(image)[0] + '_color_analysis.png'
    else:
        out_path = args.out
    if args.json_out is None:
        json_out_path = os.path.splitext(image)[0] + '_hsv_config.json'
    else:
        json_out_path = args.json_out

    frame = cv2.imread(image)
    if frame is None:
        print(f'[ERROR] 画像を読み込めません: {image}')
        sys.exit(1)
    h, w = frame.shape[:2]
    print(f'[INFO] 入力画像: {image} ({w}x{h})')

    halpe26 = estimate_halpe26_fullframe(
        wb_model, aic_model, frame, wb_dataset, wb_dataset_info,
        aic_dataset, aic_dataset_info)

    roi_box, roi_source = build_torso_roi(
        halpe26, w, h, args.kpt_conf_min, args.min_roi_area)
    print(f'[INFO] ROI source={roi_source}, roi_box={roi_box}')
    x1, y1, x2, y2 = roi_box
    roi_bgr = frame[y1:y2, x1:x2]

    stats = compute_hsv_stats(roi_bgr, args.sat_min, args.val_min, args.percentile)
    current_ratio = compute_pink_ratio(roi_bgr)

    print(f'[INFO] chroma_ratio = {stats["chroma_ratio"]:.3f}')
    p_lo, p_hi = args.percentile, 100.0 - args.percentile
    if stats['H_lo'] is not None:
        print(f'[INFO] H  p{p_lo:.0f}/med/p{p_hi:.0f} = {stats["H_lo"]}/{stats["H_med"]}/{stats["H_hi"]}')
        print(f'[INFO] S  p{p_lo:.0f}/med/p{p_hi:.0f} = {stats["S_lo"]}/{stats["S_med"]}/{stats["S_hi"]}')
        print(f'[INFO] V  p{p_lo:.0f}/med/p{p_hi:.0f} = {stats["V_lo"]}/{stats["V_med"]}/{stats["V_hi"]}')
    else:
        print('[WARN] 有彩色画素なし')
    print(f'[INFO] current pink_ratio (FIXED_HSV_RANGES) = {current_ratio:.4f}')

    regime = decide_color_regime(stats['chroma_ratio'], args.chroma_regime_min)
    print(f'[INFO] regime = {regime} '
          f'(chroma_ratio={stats["chroma_ratio"]:.3f}, thr={args.chroma_regime_min:.2f})')

    all_hsv = None
    if regime == 'chromatic':
        proposed, s_lo, v_lo, proposed_ratio = propose_hsv_ranges(
            roi_bgr, args.sat_min, args.val_min, args.percentile)
        if proposed:
            print('[INFO] === 推奨 (出力b) ===')
            print(f'[INFO] proposed FIXED_HSV_RANGES = {proposed}')
            print(f'[INFO] proposed S_low={s_lo}, V_low={v_lo}')
            print(f'[INFO] pink_ratio: current={current_ratio:.4f} -> proposed={proposed_ratio:.4f}')
            print('[NOTE] MIN_PINK_RATIO: 本ROIは服が大部分を占めるため proposed_ratio は'
                  ' 動画BB内比率の上限です。実動画では肌・背景が混じり値は低下します。')
        else:
            print('[WARN] 推奨レンジ算出不可（有彩色画素なし）')
    else:  # achromatic (feat-059)
        H_all, S_all, V_all = extract_all_hsv(roi_bgr)
        all_hsv = (H_all, S_all, V_all)
        proposed, s_lo, s_hi, v_lo, v_hi = propose_achromatic_ranges(
            H_all, S_all, V_all, args.percentile)
        proposed_ratio = compute_ratio_for_ranges(roi_bgr, proposed)
        if proposed:
            print('[INFO] === 推奨 (出力b, achromatic) ===')
            print(f'[INFO] proposed FIXED_HSV_RANGES = {proposed}')
            print(f'[INFO] proposed S=[{s_lo},{s_hi}], V=[{v_lo},{v_hi}]')
            print(f'[INFO] pink_ratio: current={current_ratio:.4f} -> proposed={proposed_ratio:.4f}')
            print('[NOTE] MIN_PINK_RATIO: 本ROIは服が大部分を占めるため proposed_ratio は'
                  ' 動画BB内比率の上限です。実動画では肌・背景が混じり値は低下します。')
        else:
            print('[WARN] 推奨レンジ算出不可（ROI画素なし）')

    try:
        render_analysis_png(frame, roi_box, stats, proposed,
                            current_ratio, proposed_ratio, out_path,
                            regime=regime, all_hsv=all_hsv)
    except Exception as e:
        if os.path.exists(out_path):
            os.remove(out_path)
        print(f'[ERROR] PNG保存失敗: {e}')
        sys.exit(1)
    print(f'[INFO] 可視化PNGを保存: {out_path}')

    # --- feat-054: HSV 設定ファイル出力（PNG 保存後）---
    if proposed:
        try:
            write_hsv_config(json_out_path, proposed, MIN_PINK_RATIO)
        except Exception as e:
            print(f'[ERROR] 設定ファイル保存失敗: {e}')
            sys.exit(1)
        print(f'[INFO] HSV 設定ファイルを保存: {json_out_path} (min_pink_ratio={MIN_PINK_RATIO})')
    else:
        print('[WARN] 推奨レンジが空のため HSV 設定ファイルは出力しません')


def run_multi_image(images: list, args: argparse.Namespace, models: tuple) -> None:
    """複数画像モード (feat-055)。全画像のROIクロマ画素をプールして単一レンジを提案する。

    フェーズ順序: 1)全画像 imread→推論→ROI→stats 収集 2)プール提案 3)閾値検証
    4)画像ごとPNG 5)統合JSON。PNG/JSON 出力(フェーズ4以降)は提案後に置き、
    読込/推論失敗(フェーズ1)時は出力ファイルを一切作らない。
    """
    (wb_model, aic_model, wb_dataset, wb_dataset_info,
     aic_dataset, aic_dataset_info) = models
    if args.out is not None:
        print('[WARN] 複数画像モードでは --out は無視され、画像ごとの名前が使われます')

    # --- フェーズ1: 全画像を逐次 imread→推論→ROI→stats 収集 ---
    per_image = []  # 各要素 dict{name, frame, roi_box, stats, all_hsv}
    pooled_H, pooled_S, pooled_V = [], [], []         # クロマ画素プール（chromatic 用）
    pooled_all_H, pooled_all_S, pooled_all_V = [], [], []  # 全画素プール（achromatic 用、feat-059）
    total_px, chroma_px = 0, 0                         # プール chroma_ratio 算出用
    n = len(images)
    for k, img in enumerate(images, 1):
        frame = cv2.imread(img)
        if frame is None:
            print(f'[ERROR] 画像を読み込めません: {img}')
            sys.exit(1)
        h, w = frame.shape[:2]
        print(f'[INFO] [{k}/{n}] 入力画像: {img} ({w}x{h})')
        halpe26 = estimate_halpe26_fullframe(
            wb_model, aic_model, frame, wb_dataset, wb_dataset_info,
            aic_dataset, aic_dataset_info)
        roi_box, roi_source = build_torso_roi(
            halpe26, w, h, args.kpt_conf_min, args.min_roi_area)
        print(f'[INFO]   ROI source={roi_source}, roi_box={roi_box}')
        roi_bgr = roi_bgr_from(frame, roi_box)
        stats = compute_hsv_stats(roi_bgr, args.sat_min, args.val_min, args.percentile)
        Ha, Sa, Va = extract_all_hsv(roi_bgr)
        per_image.append({'name': img, 'frame': frame, 'roi_box': roi_box,
                          'stats': stats, 'all_hsv': (Ha, Sa, Va)})
        pooled_H.append(stats['Hc'])
        pooled_S.append(stats['Sc'])
        pooled_V.append(stats['Vc'])
        pooled_all_H.append(Ha)
        pooled_all_S.append(Sa)
        pooled_all_V.append(Va)
        total_px += int(Ha.size)
        chroma_px += int(len(stats['Hc']))

    # --- フェーズ2: レジーム判定＋プール提案（配列直結合、BGR往復なし）---
    pooled_ratio = chroma_px / total_px if total_px > 0 else 0.0
    regime = decide_color_regime(pooled_ratio, args.chroma_regime_min)
    print(f'[INFO] pooled regime = {regime} '
          f'(chroma_ratio={pooled_ratio:.3f}, thr={args.chroma_regime_min:.2f})')
    if regime == 'chromatic':
        allH = np.concatenate(pooled_H)
        allS = np.concatenate(pooled_S)
        allV = np.concatenate(pooled_V)
        proposed, s_lo, v_lo = propose_ranges_from_chroma(allH, allS, allV, args.percentile)
        if proposed:
            print('[INFO] === 推奨 (プール) ===')
            print(f'[INFO] proposed FIXED_HSV_RANGES = {proposed}')
            print(f'[INFO] proposed S_low={s_lo}, V_low={v_lo}')
            print('[NOTE] 静止画ROIの比率は動画BB内比率の上限です。'
                  '実動画では肌・背景が混じり値は低下します。')
        else:
            print('[WARN] 推奨レンジ算出不可（全画像で有彩色画素なし）')
    else:  # achromatic (feat-059)
        allH = np.concatenate(pooled_all_H)
        allS = np.concatenate(pooled_all_S)
        allV = np.concatenate(pooled_all_V)
        proposed, s_lo, s_hi, v_lo, v_hi = propose_achromatic_ranges(
            allH, allS, allV, args.percentile)
        if proposed:
            print('[INFO] === 推奨 (プール, achromatic) ===')
            print(f'[INFO] proposed FIXED_HSV_RANGES = {proposed}')
            print(f'[INFO] proposed S=[{s_lo},{s_hi}], V=[{v_lo},{v_hi}]')
            print('[NOTE] 静止画ROIの比率は動画BB内比率の上限です。'
                  '実動画では肌・背景が混じり値は低下します。')
        else:
            print('[WARN] 推奨レンジ算出不可（全画像でROI画素なし）')

    # --- フェーズ3: 閾値検証レポート（表示のみ、exit 0）---
    print(f'[INFO] === 閾値検証 (threshold={args.threshold:.4f}) ===')
    min_ratio = 1.0
    for d in per_image:
        r = compute_ratio_for_ranges(roi_bgr_from(d['frame'], d['roi_box']), proposed)
        d['proposed_ratio'] = r
        min_ratio = min(min_ratio, r)
        flag = 'OK' if r > args.threshold else 'NG'
        print(f'[INFO]   {os.path.basename(d["name"])}: ratio={r:.4f} [{flag}]')
    verdict = 'ALL PASS' if min_ratio > args.threshold else 'SOME FAIL'
    print(f'[INFO] min ratio = {min_ratio:.4f} ({verdict})')
    if min_ratio <= args.threshold:
        print('[WARN] 閾値を下回る画像があります。--percentile を下げてレンジを広げるか、'
              '入力画像の選定を見直してください')

    # --- フェーズ4: 画像ごと PNG（提案後。フェーズ1失敗時はここに到達しない）---
    for d in per_image:
        roi_bgr = roi_bgr_from(d['frame'], d['roi_box'])
        current_ratio = compute_pink_ratio(roi_bgr)  # FIXED_HSV_RANGES 基準
        out_path = os.path.splitext(d['name'])[0] + '_color_analysis.png'
        png_all_hsv = d['all_hsv'] if regime == 'achromatic' else None
        try:
            render_analysis_png(d['frame'], d['roi_box'], d['stats'], proposed,
                                current_ratio, d['proposed_ratio'], out_path,
                                regime=regime, all_hsv=png_all_hsv)
        except Exception as e:
            if os.path.exists(out_path):
                os.remove(out_path)
            print(f'[ERROR] PNG保存失敗: {e}')
            sys.exit(1)
        print(f'[INFO] 可視化PNGを保存: {out_path}')

    # --- フェーズ5: 統合 JSON（1個）---
    if proposed:
        if args.json_out is None:
            json_out_path = os.path.splitext(images[0])[0] + '_pooled_hsv_config.json'
        else:
            json_out_path = args.json_out
        try:
            write_hsv_config(json_out_path, proposed, MIN_PINK_RATIO)
        except Exception as e:
            print(f'[ERROR] 設定ファイル保存失敗: {e}')
            sys.exit(1)
        print(f'[INFO] HSV 設定ファイルを保存: {json_out_path} (min_pink_ratio={MIN_PINK_RATIO})')
    else:
        print('[WARN] 推奨レンジが空のため HSV 設定ファイルは出力しません')


def roi_bgr_from(frame: np.ndarray, roi_box: tuple) -> np.ndarray:
    """frame と roi_box=(x1,y1,x2,y2) から ROI のビューを返す（複数画像モードのスライス共通化）。"""
    x1, y1, x2, y2 = roi_box
    return frame[y1:y2, x1:x2]


def main() -> None:
    args = parse_args()
    print('[INFO] モデルをロード中...')
    try:
        models = load_models(args.device)
    except Exception as e:
        print(f'[ERROR] モデルロード失敗: {e}')
        sys.exit(1)
    print('[INFO] モデルロード完了')

    if len(args.images) == 1:
        run_single_image(args.images[0], args, models)
    else:
        run_multi_image(args.images, args, models)


if __name__ == '__main__':
    main()
