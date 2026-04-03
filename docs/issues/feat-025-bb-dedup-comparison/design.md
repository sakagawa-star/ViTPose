# feat-025: BB重複除去方式の比較（案A vs 案E） — 機能設計書

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|--------------|
| FR-001 | 3. 比較スクリプト |

## 2. 技術スタック

| 項目 | 値 |
|------|-----|
| 言語 | Python 3.10.16 |
| パッケージ管理 | uv |
| 検出器 | YOLO11x（ultralytics 8.4.33） |
| ポーズ推定 | ViTPose++ MoE（WholeBody + AIC） |
| OKS計算 | numpy（スクリプト内に実装） |

## 3. 比較スクリプト（FR-001）

### 3.1 システム構成

```
scripts/
├── compare_dedup_methods.py          # 新規作成（本案件）
├── run_halpe26_pipeline.py           # 変更しない
├── run_halpe26_pipeline_yolox.py     # 変更しない
├── run_halpe26_pipeline_yolo11.py    # 変更しない
├── merge_halpe26.py                  # 変更しない
└── halpe26_to_openpose.py            # 変更しない
```

### 3.1.1 インポート文

```python
import argparse
import json
import os
import sys
import time

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
```

`process_yolo11_results`はスクリプト内に定義する（`run_halpe26_pipeline_yolo11.py`のトップレベル関数であり、モジュールとしてインポートするとmain()が実行されるリスクがあるため。`run_halpe26_pipeline_yolo11.py`の同名関数をそのままコピーする）。

### 3.2 処理フロー

```
1. モデル初期化:
      - YOLO11x: YOLO('yolo11x.pt')
      - WholeBody: init_pose_model(WB_CONFIG, WB_CHECKPOINT, device=args.device)
      - AIC: init_pose_model(AIC_CONFIG, AIC_CHECKPOINT, device=args.device)
      - dataset/dataset_info取得:
        wb_dataset = wb_model.cfg.data['test']['type']
        wb_dataset_info = DatasetInfo(wb_model.cfg.data['test']['dataset_info'])
        aic_dataset = aic_model.cfg.data['test']['type']
        aic_dataset_info = DatasetInfo(aic_model.cfg.data['test']['dataset_info'])
      ※ WB_CONFIG等はmerge_halpe26.pyからインポート。既存パイプラインと同一
2. 出力ターゲット作成（案A/E各動画ライター、JSONディレクトリ）
3. フレームループ:
   a. YOLO11x検出 → person_results
      フィルタ: person_results = [p for p in person_results if p['bbox'][4] >= args.bbox_thr]
   b. 人数が0なら空フレームを出力して次へ
   c. 人数が1なら通常結果を案A/E両方に出力して次へ
   d. 全BBでWholeBody + AIC推定 → 全員のHALPE 26キーポイント
   e. 全ペアのOKSを計算（compute_oks_mutual使用、CONF_THR=0.3固定）
   f. 重複グループを構築（Union-Find）
   g. 重複グループなし → 通常結果を案A/E両方に出力して次へ
   h. 重複グループあり:
      - 案A: 各グループの外接矩形で再推定。非重複人物はそのまま
      - 案E: 各グループのスコア最大BBを採用。非重複人物はそのまま
   i. 案A/E各結果で可視化フレーム描画・動画書き込み
   j. 案A/E各結果でOpenPose JSON書き出し
   k. 各重複グループに対して、案Aの結果と案Eの結果のペアでOKSを計算し、1グループにつき1つのOKSサンプルとして記録:
      area = (bbox_a[2]-bbox_a[0]) * (bbox_a[3]-bbox_a[1])  # 案Aの外接矩形面積
      oks_val = compute_oks(kps_a, kps_e, area)
4. 統計出力
```

### 3.3 重複グループの構築

Union-Findで重複ペアを連結してグループ化する。1つの重複グループにつき1つのOKSサンプルを生成する。

```python
def build_dedup_groups(n_persons: int, oks_matrix: np.ndarray, oks_thr: float) -> list[list[int]]:
    """OKS行列から重複グループを構築する（簡易Union-Find）。

    Returns:
        list[list[int]]: 2人以上の重複グループのリスト。単独の人物は含まない
    """
    parent = list(range(n_persons))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n_persons):
        for j in range(i + 1, n_persons):
            if oks_matrix[i, j] > oks_thr:
                union(i, j)

    groups = {}
    for i in range(n_persons):
        r = find(i)
        groups.setdefault(r, []).append(i)

    return [g for g in groups.values() if len(g) >= 2]
```

### 3.4 案Aの実装詳細（外接矩形再推定）

```python
def method_a(frame, group_bboxes, wb_model, aic_model,
             wb_dataset, wb_dataset_info, aic_dataset, aic_dataset_info,
             img_h, img_w):
    """重複BBの外接矩形で再推定する。

    Returns:
        tuple: (halpe26_kps: ndarray(26,3), union_bbox: ndarray(5,))
    """
    all_bboxes = np.array(group_bboxes)
    x1 = np.clip(all_bboxes[:, 0].min(), 0, img_w)
    y1 = np.clip(all_bboxes[:, 1].min(), 0, img_h)
    x2 = np.clip(all_bboxes[:, 2].max(), 0, img_w)
    y2 = np.clip(all_bboxes[:, 3].max(), 0, img_h)
    max_score = all_bboxes[:, 4].max()
    union_bbox = np.array([x1, y1, x2, y2, max_score], dtype=np.float32)

    union_person = [{'bbox': union_bbox}]
    wb_results, _ = inference_top_down_pose_model(
        wb_model, frame, union_person, bbox_thr=None,
        format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)
    aic_results, _ = inference_top_down_pose_model(
        aic_model, frame, union_person, bbox_thr=None,
        format='xyxy', dataset=aic_dataset, dataset_info=aic_dataset_info)

    # wb_results[0]['keypoints']: ndarray shape (133, 3)
    # aic_results[0]['keypoints']: ndarray shape (14, 3)
    kps = merge_to_halpe26(wb_results[0]['keypoints'], aic_results[0]['keypoints'])
    return kps, union_bbox
```

`bbox_thr=None`を指定して`inference_top_down_pose_model`内のフィルタリングをスキップする。`bbox_thr=None`のため必ず1要素のリストを返す。

戻り値にunion_bboxを含める。可視化でBBを描画するため、およびJSON出力でbbox_scoreとbbox座標を記録するため。

### 3.5 案Eの実装詳細（スコア最大BB選択）

```python
def method_e(group_indices, all_halpe26, all_bboxes):
    """重複グループ内でbbox scoreが最大のキーポイントとBBを返す。

    Returns:
        tuple: (halpe26_kps: ndarray(26,3), bbox: ndarray(5,))
    """
    scores = [all_bboxes[i][4] for i in group_indices]
    best_idx = group_indices[int(np.argmax(scores))]
    return all_halpe26[best_idx], all_bboxes[best_idx]
```

### 3.6 フレーム結果の構築

各フレームで案A/案Eの最終結果を構築する。重複グループは案A/Eで処理し、非重複人物はそのまま含める。

```python
def build_frame_results(n_persons, groups, all_halpe26, all_bboxes,
                        frame, wb_model, aic_model,
                        wb_dataset, wb_dataset_info,
                        aic_dataset, aic_dataset_info,
                        img_h, img_w):
    """フレームの案A/案E結果を構築する。

    Returns:
        tuple: (result_a, result_e)
            各resultは list[dict] で、各dictに 'keypoints'(ndarray(26,3)) と 'bbox'(ndarray(5,)) を持つ
    """
    # 重複グループに属する人物のインデックスを集める
    in_group = set()
    for g in groups:
        in_group.update(g)

    result_a = []
    result_e = []

    # 非重複人物はそのまま両方に追加（コピーして共有参照を避ける）
    for i in range(n_persons):
        if i not in in_group:
            result_a.append({'keypoints': all_halpe26[i], 'bbox': all_bboxes[i]})
            result_e.append({'keypoints': all_halpe26[i], 'bbox': all_bboxes[i]})

    # 重複グループは案A/Eで処理
    for g in groups:
        group_bboxes = [all_bboxes[i] for i in g]
        kps_a, bbox_a = method_a(frame, group_bboxes, wb_model, aic_model,
                                 wb_dataset, wb_dataset_info,
                                 aic_dataset, aic_dataset_info, img_h, img_w)
        result_a.append({'keypoints': kps_a, 'bbox': bbox_a})

        kps_e, bbox_e = method_e(g, all_halpe26, all_bboxes)
        result_e.append({'keypoints': kps_e, 'bbox': bbox_e})

    return result_a, result_e
```

### 3.7 可視化・JSON出力

案A/案Eの各結果に対して、既存パイプラインと同じ方式で出力する。

**可視化**: 入力動画と同じfps・フレームサイズ、コーデック`mp4v`でVideoWriterを初期化する。各フレームで`draw_bbox` + `draw_halpe26`で描画し書き込む。

```python
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
writer_a = cv2.VideoWriter(out_path_a, fourcc, fps, (width, height))
writer_e = cv2.VideoWriter(out_path_e, fourcc, fps, (width, height))
```

**JSON**: `halpe26_to_openpose_json`でOpenPose形式に変換し、フレームごとにJSONファイルに書き出す。

```python
# result_a / result_e は list[dict] で各dictに 'keypoints'(26,3) と 'bbox'(5,) を持つ
all_kps = [r['keypoints'] for r in result_a]
bbox_scores = [float(r['bbox'][4]) for r in result_a]
bboxes = [r['bbox'][:4].tolist() for r in result_a]
openpose_dict = halpe26_to_openpose_json(all_kps, bbox_scores=bbox_scores, bboxes=bboxes)
```

### 3.8 OKS計算

```python
CONF_THR = 0.3

HALPE26_SIGMAS = np.array([
    0.026, 0.025, 0.025, 0.035, 0.035,
    0.079, 0.079, 0.072, 0.072, 0.062, 0.062,
    0.107, 0.107, 0.087, 0.087, 0.089, 0.089,
    0.10, 0.10, 0.10,
    0.089, 0.089, 0.089, 0.089, 0.089, 0.089,
])

def compute_oks_mutual(kps1, kps2, area):
    """両者のconfidence > CONF_THRの共通キーポイントでOKSを計算する（重複判定用）。
    共通有効キーポイントが0個の場合はOKS=0.0を返し、重複なしと判定する。
    """
    valid = (kps1[:, 2] > CONF_THR) & (kps2[:, 2] > CONF_THR)
    if valid.sum() == 0:
        return 0.0
    dx = kps1[valid, 0] - kps2[valid, 0]
    dy = kps1[valid, 1] - kps2[valid, 1]
    dist_sq = dx**2 + dy**2
    sigma = HALPE26_SIGMAS[valid]
    # COCO OKS: e_i = d_i^2 / (2 * s^2 * k_i^2) where s^2 = area, k_i = sigma
    e = dist_sq / (2 * area * sigma**2 + 1e-6)
    return float(np.mean(np.exp(-e)))

def compute_oks(kps_ref, kps_target, area):
    """案A基準のOKSを計算する（案A vs 案E比較用）。
    kps_refのconfidence > CONF_THRのキーポイントを基準とし、
    kps_target側はconfidenceに関係なく使用する。
    案Aの有効キーポイントが0個の場合はOKS=0.0を返す。
    """
    valid = kps_ref[:, 2] > CONF_THR
    if valid.sum() == 0:
        return 0.0
    dx = kps_ref[valid, 0] - kps_target[valid, 0]
    dy = kps_ref[valid, 1] - kps_target[valid, 1]
    dist_sq = dx**2 + dy**2
    sigma = HALPE26_SIGMAS[valid]
    e = dist_sq / (2 * area * sigma**2 + 1e-6)
    return float(np.mean(np.exp(-e)))
```

**OKS計算の使い分け**:
- **重複判定時**（ステップe）: `compute_oks_mutual`。areaは各ペアのBBのうち面積が大きい方の`(x2-x1)*(y2-y1)`
- **案A vs 案E比較時**（ステップk）: `compute_oks`。areaは案Aの外接矩形の`(x2-x1)*(y2-y1)`

### 3.9 インターフェース定義

```python
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Compare BB dedup methods: Plan A vs Plan E')
    parser.add_argument('--video', type=str, required=True, help='Input video path')
    parser.add_argument('--out-dir', type=str, default='output', help='Output directory')
    parser.add_argument('--device', type=str, default='cuda:0', help='Inference device')
    parser.add_argument('--bbox-thr', type=float, default=0.3, help='Detection score threshold')
    parser.add_argument('--oks-thr', type=float, default=0.5, help='OKS threshold for dedup')
    parser.add_argument('--kpt-thr', type=float, default=0.3, help='Keypoint draw threshold')
    return parser.parse_args()
```

`--out-dir`のデフォルト値は`output`。検証時は`--out-dir experiments/results_dedup`を明示指定して既存出力と分離する。

### 3.10 出力ファイル構成

```
{out-dir}/
├── vis_dedup_a_{動画名}.mp4           # 案Aの可視化動画
├── vis_dedup_e_{動画名}.mp4           # 案Eの可視化動画
├── {動画stem}_dedup_a_json/           # 案AのOpenPose JSON
│   ├── {stem}_000000.json
│   ├── {stem}_000001.json
│   └── ...
└── {動画stem}_dedup_e_json/           # 案EのOpenPose JSON
    ├── {stem}_000000.json
    ├── {stem}_000001.json
    └── ...
```

### 3.11 標準出力フォーマット

```
=== BB Dedup Method Comparison ===
Video: testdata/cam05520125.mp4
Bbox threshold: 0.3, OKS dedup threshold: 0.5

Total frames: 300
Frames with detection: 280
Frames with multi-person: 129 (46.1%)
Frames with dedup (OKS > 0.5): 125 (44.6%)
Dedup groups (total): 125 (= OKS sample count, across all frames)

--- Plan A vs Plan E: OKS ---
Mean:   0.XXX
Median: 0.XXX
Min:    0.XXX
Max:    0.XXX
>0.50:  XXX / XXX (XX.X%)
>0.75:  XXX / XXX (XX.X%)
>0.90:  XXX / XXX (XX.X%)
>0.95:  XXX / XXX (XX.X%)

Saved: {out-dir}/vis_dedup_a_{動画名}.mp4
Saved: {out-dir}/vis_dedup_e_{動画名}.mp4
Saved: XXX JSON files to {out-dir}/{stem}_dedup_a_json/
Saved: XXX JSON files to {out-dir}/{stem}_dedup_e_json/
```

### 3.12 前提条件・境界条件

**前提条件**: プロジェクトルートディレクトリから実行すること。

| 条件 | 振る舞い |
|------|---------|
| 0人検出フレーム | 案A/E両方に元フレーム（描画なし）を出力。JSONは空のpeopleリスト |
| 1人検出フレーム | 通常結果を案A/E両方に同じ内容で出力 |
| 2人以上検出だがOKS <= oks_thrの全ペア | 通常結果を案A/E両方に同じ内容で出力（本当の複数人） |
| 重複検出フレームが0の動画 | 「重複なし」と表示。可視化動画・JSONは出力される（案A/Eが同一内容） |
| 3人以上の重複グループ | Union-Findでグループ化し、グループ単位で案A/Eを適用 |
| 非重複人物 | 案A/E両方にそのまま含める。OKS比較の対象外 |
| 外接矩形が画像境界を超える場合 | `np.clip`で画像サイズ内にクリッピングする |

### 3.13 ログ・デバッグ設計

起動時に動画パス、bbox_thr、oks_thrを表示。100フレームごとにプログレス表示。

### 3.14 エラーハンドリング

既存パイプラインと同一。調査用スクリプトのため追加のエラーハンドリングは不要。

### 3.15 設計判断

| 判断 | 採用案 | 却下案 | 理由 |
|------|--------|--------|------|
| OKSのarea基準（比較時） | 案Aの外接矩形の面積 | 各BBの面積 | 案Aと案Eを同じスケールで比較するため |
| 重複グループの構築 | Union-Find | ペアごとに独立処理 | 3人以上のBBが重複する場合に正しくグループ化できる |
| 案Aのbbox_thr | Noneを指定 | args.bbox_thrを使用 | 外接矩形は明示的に構築したBBであり、スコアフィルタリングは不要 |
| 案Aのconfidence | 重複BBの最大スコアを採用 | 平均値、固定値 | 最もシンプルで既存パイプラインとの互換性が高い |
| 3人以上の重複グループの案A | 全BBの外接矩形1つで再推定 | グループ内の最大BBで再推定 | 全BBを包含する外接矩形が最も安全 |
| HALPE26_SIGMASの出典 | インデックス0-16: COCO公式sigmaをHALPE 26の対応インデックスにマッピング。17-19(Head/Neck/Hip): 公式値なし、保守的に0.10を採用。20-25(足6点): ankle相当の0.089を採用 | 全キーポイントに独自sigma算出 | 調査用スクリプトであり相対比較が目的。厳密なsigma不要 |
| conf_thr | 0.3固定（CONF_THR定数）、CLI引数にしない | CLI引数として公開 | bbox_thrと同値であり、調査用スクリプトでは変更の必要性が低い |
| YOLO11xモデルパス | `yolo11x.pt`（ultralyticsが自動解決） | checkpoints/に配置 | 既存の`run_halpe26_pipeline_yolo11.py`と同一方式 |
| 非重複フレームの出力 | 案A/E両方に同一内容を出力 | 出力しない | 動画として連続して確認できるようにする |
| OKS関数 | 重複判定用（compute_oks_mutual）と比較用（compute_oks）を別関数で定義 | 1つの関数にフラグ追加 | 用途ごとに関数を分けた方がコードの意図が明確 |
