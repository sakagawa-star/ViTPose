# feat-025: BB重複除去方式の比較（案A vs 案E） — 機能設計書

## 1. 対応要求マッピング

| 要求ID | 設計セクション | 実装状態 |
|--------|--------------|----------|
| FR-001 | 3. 比較スクリプト | 実装済み |
| FR-002 | 4. YOLO11x + 案Aパイプライン | 未実装 |

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

注: 設計時は`build_frame_results`関数として定義したが、FR-001の実装（`compare_dedup_methods.py`）では`main()`内にインライン展開した。以下は設計意図を示す参考コードである。

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

---

## 4. YOLO11x + 案Aパイプライン（FR-002）

### 4.1 変更対象

`scripts/run_halpe26_pipeline_yolo11.py` のみ変更する。`compare_dedup_methods.py` は変更しない。

### 4.2 追加するインポート・定数

`compare_dedup_methods.py` から以下をスクリプト内にコピーする（`compare_dedup_methods.py` はモジュールとしてインポートするとmain()が実行されるリスクがあるため、FR-001と同じ理由でコピー方式を採用）。

```python
CONF_THR = 0.3

HALPE26_SIGMAS = np.array([
    0.026, 0.025, 0.025, 0.035, 0.035,
    0.079, 0.079, 0.072, 0.072, 0.062, 0.062,
    0.107, 0.107, 0.087, 0.087, 0.089, 0.089,
    0.10, 0.10, 0.10,
    0.089, 0.089, 0.089, 0.089, 0.089, 0.089,
])
```

### 4.3 追加する関数

`compare_dedup_methods.py` から以下の3関数をそのままコピーする。コードは同一。

1. `compute_oks_mutual(kps1, kps2, area)` — 重複判定用OKS（セクション3.8と同一）
2. `build_dedup_groups(n_persons, oks_matrix, oks_thr)` — Union-Findによるグループ構築（セクション3.3と同一）
3. `method_a(frame, group_bboxes, wb_model, aic_model, ...)` — 外接矩形再推定（セクション3.4と同一）

### 4.4 CLI引数の追加

```python
parser.add_argument('--oks-thr', type=float, default=0.5,
                    help='OKS threshold for BB dedup detection (default: 0.5)')
```

既存引数（`--video`, `--out-dir`, `--device`, `--mode`, `--bbox-thr`, `--kpt-thr`, `--profile`）は変更しない。

### 4.5 bbox_thrフィルタリング方式の変更

既存パイプラインでは`inference_top_down_pose_model`に`bbox_thr=args.bbox_thr`を渡し、関数内部でフィルタしている。この方式では`person_results`と`wb_results`のインデックスがずれる可能性がある（スコアが低いBBが除外されるため）。

FR-002では`compare_dedup_methods.py`と同じ**事前フィルタ方式**に変更する:

1. YOLO11x検出後に`person_results`を`bbox_thr`でフィルタする（`person_results = process_yolo11_results(yolo_results[0])` の直後に追加）
2. `inference_top_down_pose_model`には`bbox_thr=None`を渡す（フィルタ済みのため）

これにより`person_results`、`wb_results`、`aic_results`のインデックスが1対1で対応することが保証される。

**変更箇所（ステップ5a直後）:**

```python
        person_results = process_yolo11_results(yolo_results[0])
        # 事前フィルタ（compare_dedup_methods.pyと同一方式）
        person_results = [p for p in person_results if p['bbox'][4] >= args.bbox_thr]
```

**変更箇所（ステップ5b/5c）:**

```python
        # bbox_thr=None に変更（事前フィルタ済みのため）
        wb_results, _ = inference_top_down_pose_model(
            wb_model, frame, person_results, bbox_thr=None,
            format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)
        aic_results, _ = inference_top_down_pose_model(
            aic_model, frame, person_results, bbox_thr=None,
            format='xyxy', dataset=aic_dataset, dataset_info=aic_dataset_info)
```

### 4.6 フレームループの変更（重複除去ステップの挿入）

既存のステップ5d（Merge to HALPE 26）とステップ5e（Video output）の間に、重複除去ステップを挿入する。

#### 変更前（ステップ5d以降）

```
5d. Merge to HALPE 26 → all_halpe26
5e. Video output（wb_results[i]['bbox']でBB描画、len(wb_results)でループ）
5f. JSON output（wb_results[i]['bbox']でbbox_scores/bboxes取得）
```

#### 変更後

```
5d. Merge to HALPE 26 → all_halpe26
5d2. all_bboxes構築 + BB重複除去（案A）:
     - all_bboxes = [wb_results[i]['bbox'] for i in range(len(all_halpe26))]
     - 人数が2人以上の場合のみ重複除去を実行
     - compute_oks_mutual でペアワイズOKS計算
     - build_dedup_groups でグループ構築
     - グループがあれば method_a で再推定し、all_halpe26 と all_bboxes を更新
5e. Video output（all_bboxes[i]でBB描画、len(all_halpe26)でループ）
5f. JSON output（all_bboxes[i]でbbox_scores/bboxes取得）
```

注: 重複除去後は`wb_results`と`all_halpe26`の長さが異なる（重複グループが1つに統合されるため）。ステップ5e/5fでは`wb_results`ではなく`all_halpe26`と`all_bboxes`を参照する。

#### 擬似コード（ステップ5d2）

`all_bboxes`の構築も含めてdedupプロファイルとする。

```python
        # 5d2. BB dedup (Plan A)
        if args.profile:
            t = time.time()
        # wb_results[i]['bbox'] は inference_top_down_pose_model が入力BBをそのまま返すため、
        # person_results[i]['bbox'] と同一。bbox_thr=None で推論しているためインデックスも1対1対応。
        all_bboxes = [wb_results[i]['bbox'] for i in range(len(all_halpe26))]
        n_persons = len(all_halpe26)

        if n_persons >= 2:
            # OKSペアワイズ計算
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
                # 重複グループに属するインデックスを収集
                in_group = set()
                for g in groups:
                    in_group.update(g)

                # 非重複人物を保持
                new_halpe26 = []
                new_bboxes = []
                for i in range(n_persons):
                    if i not in in_group:
                        new_halpe26.append(all_halpe26[i])
                        new_bboxes.append(all_bboxes[i])

                # 重複グループに案Aを適用
                for g in groups:
                    group_bboxes = [all_bboxes[i] for i in g]
                    # height, width は既存コードの cap.get() で取得済みの変数
                    # method_a の仮引数 img_h, img_w に対応
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
```

### 4.7 ステップ5e/5fの変更

BB描画とJSON出力で使用するBBの参照元を `wb_results[i]['bbox']` から `all_bboxes[i]` に変更する。ループのイテレーション対象も `len(wb_results)` から `len(all_halpe26)` に変更する（重複除去後はwb_resultsとall_halpe26の長さが異なるため）。

**ステップ5e（Video output）— 変更後:**

```python
        if do_video:
            vis_frame = frame.copy()
            # len(wb_results) → len(all_halpe26) に変更
            for i in range(len(all_halpe26)):
                vis_frame = draw_bbox(vis_frame, all_bboxes[i])
            for kps in all_halpe26:
                vis_frame = draw_halpe26(vis_frame, kps, kpt_thr=args.kpt_thr)
            writer.write(vis_frame)
```

**ステップ5f（JSON output）— 変更後:**

```python
        if do_json:
            # wb_results[i]['bbox'] → all_bboxes[i] に変更
            bbox_scores = [float(all_bboxes[i][4])
                          for i in range(len(all_halpe26))]
            bboxes = [all_bboxes[i][:4].tolist()
                      for i in range(len(all_halpe26))]
            openpose_dict = halpe26_to_openpose_json(all_halpe26,
                                                     bbox_scores=bbox_scores,
                                                     bboxes=bboxes)
```

**件数不一致時（all_halpe26 = []）の振る舞い**: 既存のステップ5dで`wb_results`と`aic_results`の件数が不一致の場合、`all_halpe26 = []`となる。ステップ5d2で`n_persons = 0`のため重複除去はスキップされ、`all_bboxes = []`となる。ステップ5e/5fでも`len(all_halpe26) = 0`のためBB描画・JSON出力は空になる。

### 4.8 プロファイル項目の追加

`profile` 辞書に `'dedup'` キーを追加する。

```python
    if args.profile:
        profile = {
            'read': 0.0, 'det': 0.0, 'wb': 0.0, 'aic': 0.0,
            'merge': 0.0, 'dedup': 0.0, 'draw': 0.0, 'json': 0.0,
        }
```

プロファイル出力のラベルリストにも `('merge', 'Merge')` の直後に `('dedup', 'Dedup')` を挿入する:

```python
        for key, label in [('read', 'Read'),
                           ('det', 'Detection'),
                           ('wb', 'WholeBody'),
                           ('aic', 'AIC'),
                           ('merge', 'Merge'),
                           ('dedup', 'Dedup'),   # 追加
                           ('draw', 'Draw'),
                           ('json', 'JSON')]:
```

### 4.9 起動時メッセージの変更

```python
    print(f'Output mode: {args.mode}')
    print(f'Detector: YOLO11x')
    print(f'Bbox threshold: {args.bbox_thr}, OKS dedup threshold: {args.oks_thr}')
```

### 4.10 設計判断

| 判断 | 採用案 | 却下案 | 理由 |
|------|--------|--------|------|
| bbox_thrフィルタ方式 | 事前フィルタ（YOLO11x検出後にスコアフィルタ）+ `bbox_thr=None`で推論 | 既存の`bbox_thr=args.bbox_thr`で推論内フィルタ | `compare_dedup_methods.py`と同一方式に統一。person_resultsとwb_resultsのインデックス1対1対応を保証 |
| ロジックの共有方法 | `compare_dedup_methods.py` から関数をコピー | 共通モジュールに抽出 | 両スクリプトが独立実行可能であること優先。共通化は将来のリファクタリング対象 |
| 変更対象 | `run_halpe26_pipeline_yolo11.py` のみ | 新規スクリプト作成 | 既存パイプラインの拡張が自然。新規スクリプトは管理コスト増 |
| 重複除去の挿入位置 | ステップ5d（Merge）と5e（Video output）の間 | ステップ5a（Detection）の直後 | 重複判定にキーポイントのOKSが必要なため、ポーズ推定後でなければ判定できない |
| all_bboxesの導入 | ステップ5d2でall_bboxesリストを構築 | wb_results[i]['bbox']を直接更新 | wb_resultsのdictを破壊的に変更するより、独立したリストの方が安全 |
