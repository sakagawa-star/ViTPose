# feat-016: JSONにBBスコアを保存 — 機能設計書

## 1.1 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001 | 1.4 各機能の詳細設計 |

## 1.2 システム構成

変更対象ファイル:
- `scripts/halpe26_to_openpose.py` — `halpe26_to_openpose_json` 関数のインターフェース変更 + `main` 関数の対応
- `scripts/run_halpe26_pipeline.py` — `halpe26_to_openpose_json` 呼び出し時にBBスコアを渡す

変更しないファイル:
- `scripts/merge_halpe26.py` — BB情報は扱わないため変更不要

## 1.3 技術スタック

既存の技術スタックのみ使用。追加ライブラリなし。

## 1.4 各機能の詳細設計

### FR-001: BBスコアのJSON出力

#### データフロー

1. `wb_results[i]['bbox']` — numpy.ndarray, shape=(5,), dtype=float32, [x1, y1, x2, y2, score]
2. `score` — float, 0.0〜1.0, BBの検出信頼度
3. JSON出力: 各personオブジェクトに `"bbox_score": float` を追加

#### 処理ロジック

**`halpe26_to_openpose_json` の変更:**

現在のシグネチャ:
```python
def halpe26_to_openpose_json(all_halpe26: list) -> dict:
```

変更後のシグネチャ:
```python
def halpe26_to_openpose_json(all_halpe26: list, bbox_scores: list[float] | None = None) -> dict:
```

- `bbox_scores` が `None` の場合: 従来通り `bbox_score` フィールドを出力しない（後方互換性を維持）
- `bbox_scores` がリストの場合: `len(bbox_scores) == len(all_halpe26)` であること。各personに `"bbox_score": bbox_scores[i]` を追加する

personオブジェクトの構造（変更後）:
```python
person = {
    'person_id': [-1],
    'pose_keypoints_2d': kps.flatten().tolist(),
    'bbox_score': bbox_scores[i],  # 追加
    'face_keypoints_2d': [],
    'hand_left_keypoints_2d': [],
    'hand_right_keypoints_2d': [],
    'pose_keypoints_3d': [],
    'face_keypoints_3d': [],
    'hand_left_keypoints_3d': [],
    'hand_right_keypoints_3d': [],
}
```

**`run_halpe26_pipeline.py` の変更:**

JSON出力部分（現在の167行目付近）で、BBスコアを抽出して渡す:

```python
bbox_scores = [float(wb_results[i]['bbox'][4]) for i in range(len(all_halpe26))]
openpose_dict = halpe26_to_openpose_json(all_halpe26, bbox_scores=bbox_scores)
```

注意: `all_halpe26` が空リスト（WB/AIC件数不一致時）の場合、`bbox_scores` も空リストとなり問題なし。

**`halpe26_to_openpose.py` の `main` 関数の変更:**

117行目付近で同様にBBスコアを渡す:

```python
bbox_scores = [float(wb_results[i]['bbox'][4]) for i in range(len(all_halpe26))]
openpose_dict = halpe26_to_openpose_json(all_halpe26, bbox_scores=bbox_scores)
```

#### 前提条件

- `all_halpe26[i]` は `wb_results[i]` と `aic_results[i]` から生成される。`bbox_scores[i]` は `wb_results[i]['bbox'][4]` から取得する。この1対1対応はパイプラインの構造で保証される

#### エラーハンドリング

- `bbox_scores` の長さが `all_halpe26` の長さと一致しない場合: `halpe26_to_openpose_json` 関数のdocstringに「`bbox_scores` の長さは `all_halpe26` と一致すること」という事前条件を明記する。バリデーションコードは追加しない
- `wb_results` が空の場合: `bbox_scores` も空リストとなり、ループに入らないため問題なし

#### 境界条件

- 0人検出: `all_halpe26 = []`, `bbox_scores = []` → `people = []` で正常動作
- 1人検出: 通常動作
- 複数人検出: 通常動作

## 1.5 状態遷移

なし（ステートレス処理）

## 1.6 ファイル・ディレクトリ設計

出力JSONのファイルパス・命名規則は変更なし。JSON内のスキーマにのみ `bbox_score` フィールドが追加される。

## 1.7 インターフェース定義

```python
def halpe26_to_openpose_json(
    all_halpe26: list,
    bbox_scores: list[float] | None = None,
) -> dict:
```

- `all_halpe26`: list of numpy.ndarray, 各shape=(26, 3)
- `bbox_scores`: list of float（各人物のBB検出スコア）。Noneの場合はbbox_scoreフィールドを出力しない
- 戻り値: OpenPose JSON dict

## 1.8 ログ・デバッグ設計

追加のログ出力なし。既存のprint出力に変更なし。

## 設計判断の記録

### `bbox_scores` をNoneデフォルトにする理由

- **採用案**: `bbox_scores: list[float] | None = None` でオプショナルにする
- **却下案**: 必須引数にする → `halpe26_to_openpose.py` の単体スクリプトと `run_halpe26_pipeline.py` の両方で呼ばれるため、後方互換性を維持する方が安全
