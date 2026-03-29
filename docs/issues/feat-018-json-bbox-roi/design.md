# feat-018: JSONにBBのROI座標を保存 — 機能設計書

## 1.1 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001 | 1.4 各機能の詳細設計 |

## 1.2 システム構成

変更対象ファイル:
- `scripts/halpe26_to_openpose.py` — `halpe26_to_openpose_json` 関数に `bboxes` パラメータを追加 + `main` 関数の対応
- `scripts/run_halpe26_pipeline.py` — `halpe26_to_openpose_json` 呼び出し時にROI座標を渡す

変更しないファイル:
- `scripts/merge_halpe26.py` — BB情報は扱わないため変更不要

## 1.3 技術スタック

既存の技術スタックのみ使用。追加ライブラリなし。

## 1.4 各機能の詳細設計

### FR-001: BB ROI座標のJSON出力

#### 前提条件

- feat-016で `bbox_scores` パラメータは追加済み。同じパターンで `bboxes` パラメータを追加する
- `all_halpe26[i]` と `wb_results[i]` の1対1対応はパイプラインの構造で保証される（feat-016 設計書で記録済み）

#### データフロー

1. `wb_results[i]['bbox']` — numpy.ndarray, shape=(5,), dtype=float32, [x1, y1, x2, y2, score]
2. 先頭4要素 `[x1, y1, x2, y2]` を抽出してfloatリストに変換
3. JSON出力: 各personオブジェクトに `"bbox": [x1, y1, x2, y2]` を追加

#### 処理ロジック

**`halpe26_to_openpose_json` の変更（`scripts/halpe26_to_openpose.py`）:**

変更前のシグネチャ:
```python
def halpe26_to_openpose_json(
    all_halpe26: list,
    bbox_scores: list | None = None,
) -> dict:
```

変更後のシグネチャ:
```python
def halpe26_to_openpose_json(
    all_halpe26: list,
    bbox_scores: list | None = None,
    bboxes: list | None = None,
) -> dict:
```

- `bboxes` が `None` の場合: `bbox` フィールドを出力しない（後方互換性を維持）
- `bboxes` がリストの場合: `len(bboxes) == len(all_halpe26)` であること。各personに `"bbox": bboxes[i]` を追加する

docstringに事前条件を明記する: 「`bboxes` の長さは `all_halpe26` と一致すること」

personオブジェクトへの追加（`bbox_scores` の追加処理の直後）:
```python
if bboxes is not None:
    person['bbox'] = bboxes[i]
```

**`run_halpe26_pipeline.py` の変更（169-172行目付近のJSON出力部分）:**

変更前:
```python
            bbox_scores = [float(wb_results[i]['bbox'][4])
                          for i in range(len(all_halpe26))]
            openpose_dict = halpe26_to_openpose_json(all_halpe26,
                                                     bbox_scores=bbox_scores)
```

変更後:
```python
            bbox_scores = [float(wb_results[i]['bbox'][4])
                          for i in range(len(all_halpe26))]
            bboxes = [wb_results[i]['bbox'][:4].tolist()
                      for i in range(len(all_halpe26))]
            openpose_dict = halpe26_to_openpose_json(all_halpe26,
                                                     bbox_scores=bbox_scores,
                                                     bboxes=bboxes)
```

**`halpe26_to_openpose.py` の `main` 関数の変更（125-128行目付近）:**

変更前:
```python
        bbox_scores = [float(wb_results[i]['bbox'][4])
                       for i in range(len(all_halpe26))]
        openpose_dict = halpe26_to_openpose_json(all_halpe26,
                                                 bbox_scores=bbox_scores)
```

変更後:
```python
        bbox_scores = [float(wb_results[i]['bbox'][4])
                       for i in range(len(all_halpe26))]
        bboxes = [wb_results[i]['bbox'][:4].tolist()
                  for i in range(len(all_halpe26))]
        openpose_dict = halpe26_to_openpose_json(all_halpe26,
                                                 bbox_scores=bbox_scores,
                                                 bboxes=bboxes)
```

#### エラーハンドリング

- `bboxes` の長さが `all_halpe26` と一致しない場合: `bboxes` と `all_halpe26` は同一の `wb_results` から `range(len(all_halpe26))` で生成されるため、長さは構造的に一致する。docstringに事前条件を明記する。バリデーションコードは追加しない（feat-016と同方針）
- `wb_results` が空の場合: `bboxes` も空リストとなり、ループに入らないため問題なし

#### 境界条件

- 0人検出: `all_halpe26 = []`, `bboxes = []` → `people = []` で正常動作
- 1人検出: 通常動作
- 複数人検出: 通常動作

## 1.5 状態遷移

なし（ステートレス処理）

## 1.6 ファイル・ディレクトリ設計

変更なし。JSON内のスキーマにのみ `bbox` フィールドが追加される。

## 1.7 インターフェース定義

```python
def halpe26_to_openpose_json(
    all_halpe26: list,
    bbox_scores: list | None = None,
    bboxes: list | None = None,
) -> dict:
```

- `all_halpe26`: list of numpy.ndarray, 各shape=(26, 3)
- `bbox_scores`: list of float（各人物のBB検出スコア）。Noneの場合はbbox_scoreフィールドを出力しない
- `bboxes`: list of list[float]（各人物のBB ROI座標 [x1, y1, x2, y2]）。Noneの場合はbboxフィールドを出力しない
- 戻り値: OpenPose JSON dict

## 1.8 ログ・デバッグ設計

追加のログ出力なし。

## 設計判断の記録

### `bbox[:4].tolist()` で変換する理由

- **採用案**: `wb_results[i]['bbox'][:4].tolist()` でnumpy配列からPythonリストに変換して渡す
- **却下案**: numpy配列のまま渡して `halpe26_to_openpose_json` 内で変換する → 呼び出し側で変換する方がJSON serializableなデータを渡す原則と一致する
