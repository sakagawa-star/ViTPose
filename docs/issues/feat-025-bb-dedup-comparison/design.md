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
├── merge_halpe26.py                  # 変更しない（関数をインポートして使用）
└── halpe26_to_openpose.py            # 変更しない
```

### 3.2 処理フロー

```
1. モデル初期化（YOLO11x、WholeBody、AIC）
2. フレームループ:
   a. YOLO11x検出 → person_results
   b. bbox_thr でフィルタリング後、人数が1以下なら次のフレームへ
   c. 全BBでWholeBody + AIC推定 → 全員のHALPE 26キーポイント
   d. 全ペアのOKSを計算
   e. OKS > oks_thr のペアがなければ次のフレームへ（本当の複数人）
   f. 重複検出と判定:
      - 案E: OKS > oks_thr のペアのうち、bbox scoreが高い方のキーポイントを採用
      - 案A: 重複BBの外接矩形を作成し、その1つのBBで再推定
   g. 案Aと案EのキーポイントのOKSを計算して記録
3. 統計出力
```

### 3.3 重複グループの構築

1フレームに3人以上検出され、うち複数がOKS > oks_thrで重複する場合がある。重複ペアを連結して**重複グループ**を構築する（Union-Find）。

例: person 0,1,2が検出され、OKS(0,1) > thr, OKS(1,2) > thr の場合 → {0,1,2}が1つの重複グループ。

各重複グループに対して案Aと案Eを適用する。

### 3.4 案Aの実装詳細（外接矩形再推定）

```python
def method_a(frame, group_bboxes, wb_model, aic_model, wb_dataset, wb_dataset_info, aic_dataset, aic_dataset_info, device):
    """重複BBの外接矩形で再推定する。

    Args:
        frame: BGR画像（numpy配列）
        group_bboxes: list[ndarray] — 重複グループのBB一覧。各要素は[x1,y1,x2,y2,score]
        wb_model, aic_model: ポーズ推定モデル
        その他: データセット情報
        device: 推論デバイス

    Returns:
        ndarray shape (26, 3): HALPE 26キーポイント
    """
    # 外接矩形を計算
    all_bboxes = np.array(group_bboxes)
    x1 = all_bboxes[:, 0].min()
    y1 = all_bboxes[:, 1].min()
    x2 = all_bboxes[:, 2].max()
    y2 = all_bboxes[:, 3].max()
    max_score = all_bboxes[:, 4].max()
    union_bbox = np.array([x1, y1, x2, y2, max_score], dtype=np.float32)

    # 外接矩形でポーズ推定
    union_person = [{'bbox': union_bbox}]
    wb_results, _ = inference_top_down_pose_model(
        wb_model, frame, union_person, bbox_thr=None,
        format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)
    aic_results, _ = inference_top_down_pose_model(
        aic_model, frame, union_person, bbox_thr=None,
        format='xyxy', dataset=aic_dataset, dataset_info=aic_dataset_info)

    return merge_to_halpe26(wb_results[0]['keypoints'], aic_results[0]['keypoints'])
```

`bbox_thr=None`を指定して、`inference_top_down_pose_model`内のフィルタリングをスキップする。外接矩形は明示的に作成したBBであり、フィルタリングは不要。`bbox_thr=None`のため`inference_top_down_pose_model`は必ず1要素のリストを返す。空リストにはならない。

### 3.5 案Eの実装詳細（スコア最大BB選択）

```python
def method_e(group_indices, all_halpe26, all_bboxes):
    """重複グループ内でbbox scoreが最大のキーポイントを返す。

    Args:
        group_indices: list[int] — 重複グループの人物インデックス
        all_halpe26: list[ndarray] — 全員のHALPE 26キーポイント
        all_bboxes: list[ndarray] — 全員のBB

    Returns:
        ndarray shape (26, 3): HALPE 26キーポイント
    """
    scores = [all_bboxes[i][4] for i in group_indices]
    best_idx = group_indices[np.argmax(scores)]
    return all_halpe26[best_idx]
```

### 3.6 OKS計算

```python
# HALPE 26用のsigma値
# COCO 17に対応するキーポイントはCOCO公式sigmaを使用
# Head, Neck, Hip(center), 足6点は0.1（公式値なし、保守的な値）
HALPE26_SIGMAS = np.array([
    0.026, 0.025, 0.025, 0.035, 0.035,  # Nose,LEye,REye,LEar,REar
    0.079, 0.079, 0.072, 0.072, 0.062, 0.062,  # shoulders,elbows,wrists
    0.107, 0.107, 0.087, 0.087, 0.089, 0.089,  # hips,knees,ankles
    0.10, 0.10, 0.10,   # Head,Neck,Hip(center)
    0.089, 0.089, 0.089, 0.089, 0.089, 0.089   # toes,heels
])

def compute_oks(kps1, kps2, area, conf_thr=0.3):
    """2つのキーポイントセット間のOKSを計算する。

    Args:
        kps1: ndarray shape (26, 3) — [x, y, confidence]
        kps2: ndarray shape (26, 3) — [x, y, confidence]
        area: float — BBの面積（正規化用）
        conf_thr: float — この閾値以上の共通キーポイントのみ使用

    Returns:
        float: OKS値（0〜1）。共通キーポイントがない場合は0.0
    """
    valid = (kps1[:, 2] > conf_thr) & (kps2[:, 2] > conf_thr)
    if valid.sum() == 0:
        return 0.0
    dx = kps1[valid, 0] - kps2[valid, 0]
    dy = kps1[valid, 1] - kps2[valid, 1]
    dist_sq = dx**2 + dy**2
    s = HALPE26_SIGMAS[valid]
    e = dist_sq / (2 * area * s**2 + 1e-6)
    return float(np.mean(np.exp(-e)))
```

**areaの定義**:
- **重複判定時**（処理フロー ステップd）: 各ペアのBBのうち面積が大きい方の`(x2-x1)*(y2-y1)`を使用する
- **案A vs 案E比較時**（処理フロー ステップg）: 案Aの外接矩形の`(x2-x1)*(y2-y1)`を使用する。案Aと案Eを同じスケールで比較するため

### 3.7 インターフェース定義

```python
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Compare BB dedup methods: Plan A (union re-estimate) vs Plan E (best score)')
    parser.add_argument('--video', type=str, required=True, help='Input video path')
    parser.add_argument('--device', type=str, default='cuda:0', help='Inference device')
    parser.add_argument('--bbox-thr', type=float, default=0.3, help='Detection score threshold')
    parser.add_argument('--oks-thr', type=float, default=0.5, help='OKS threshold for dedup detection')
    return parser.parse_args()
```

### 3.8 出力フォーマット

```
=== BB Dedup Method Comparison ===
Video: testdata/cam05520125.mp4
Bbox threshold: 0.3, OKS dedup threshold: 0.5

Total frames: 300
Frames with detection: 280
Frames with multi-person: 129 (46.1%)
Frames with dedup (OKS > 0.5): 125 (44.6%)
Dedup groups: 125

--- Plan A vs Plan E: OKS ---
Mean:   0.XXX
Median: 0.XXX
Min:    0.XXX
Max:    0.XXX
>0.50:  XXX / XXX (XX.X%)
>0.75:  XXX / XXX (XX.X%)
>0.90:  XXX / XXX (XX.X%)
>0.95:  XXX / XXX (XX.X%)
```

### 3.9 前提条件・境界条件

**前提条件**: プロジェクトルートディレクトリから実行すること。

| 条件 | 振る舞い |
|------|---------|
| 0人検出フレーム | スキップ |
| 1人検出フレーム | スキップ（重複なし） |
| 2人以上検出だがOKS <= oks_thrの全ペア | スキップ（本当の複数人） |
| 重複検出フレームが0の動画 | 「重複なし」と表示して正常終了 |
| 3人以上の重複グループ | Union-Findでグループ化し、グループ単位で案A/Eを適用 |
| 非重複人物 | OKS比較の対象外。統計には含めない |

### 3.10 ログ・デバッグ設計

起動時に以下を表示:
- 動画パス、bbox_thr、oks_thr
- 100フレームごとのプログレス表示

### 3.11 エラーハンドリング

既存パイプラインと同一。調査用スクリプトのため追加のエラーハンドリングは不要。

### 3.12 設計判断

| 判断 | 採用案 | 却下案 | 理由 |
|------|--------|--------|------|
| OKSのarea基準 | 案Aの外接矩形の面積 | 各BBの面積 | 案Aと案Eを同じスケールで比較するため |
| 重複グループの構築 | Union-Find | ペアごとに独立処理 | 3人以上のBBが重複する場合に正しくグループ化できる |
| 案Aのbbox_thr | Noneを指定 | args.bbox_thrを使用 | 外接矩形は明示的に構築したBBであり、スコアフィルタリングは不要 |
| 案Aのconfidence | 重複BBの最大スコアを採用 | 平均値、固定値 | 最もシンプルで既存パイプラインとの互換性が高い |
| 3人以上の重複グループの案A | 全BBの外接矩形1つで再推定 | グループ内の最大BBで再推定 | 全BBを包含する外接矩形が最も安全。体全体をカバーできる |
| 足6点のsigma値 | ankleと同値の0.089を使用 | COCO-WholeBody公式sigma（0.068程度） | 調査用スクリプトであり厳密なsigma不要。ankleに近い部位のため同値を採用。比較は相対的な精度差の確認が目的 |
