# feat-050 要求仕様書: postprocess_pink_id.py に `--min-pink-ratio` CLI 引数を追加

## 1. プロジェクト概要

### 1.1 何を作るのか

`scripts/postprocess_pink_id.py` に CLI 引数 `--min-pink-ratio` を追加し、ハードコードされていた定数 `MIN_PINK_RATIO = 0.03` を実行時に変更可能にする。

### 1.2 なぜ作るのか

keypoint-rect モード（feat-046）の挙動検証で閾値を 0.03 から 0.1 等へ変えて比較したいケースが発生。現状は定数のためソース編集が必要で煩雑。

### 1.3 誰が使うのか

本プロジェクトの開発者（閾値チューニング・挙動検証担当）。

### 1.4 どこで使うのか

既存スクリプトと同一環境（uv 環境）。

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| `MIN_PINK_RATIO` | 既存定数。pink_id=1 候補とする `pink_ratio` の最低値。デフォルト 0.03 |
| `--min-pink-ratio` | 本案件で追加する CLI 引数。`MIN_PINK_RATIO` 定数の代わりに使う値を実行時指定 |

## 3. 機能要求一覧

### FR-001: CLI 引数 `--min-pink-ratio` の追加

- **概要**: `postprocess_pink_id.py` に `--min-pink-ratio` を追加
- **入力**:
  - `--min-pink-ratio` (float, デフォルト 0.03, 値域 `[0.0, 1.0]`)
- **処理内容**:
  1. argparse バリデータで値域を検証
  2. 既存の `MIN_PINK_RATIO` 定数参照箇所すべてを `args.min_pink_ratio` 経由に置き換え
  3. 定数 `MIN_PINK_RATIO = 0.03` は **デフォルト値の出所として残す**（互換性と可読性のため）
- **受け入れ基準**:
  - AC-001-1: `--min-pink-ratio` 未指定時の挙動は改修前と完全一致。検証手順: 改修前コード（`git stash` 等で退避した状態）と改修後コードでそれぞれ `experiments/results/camSony1_S_pink_json_kp_before/` / `_after/` を生成し、`diff -r before/ after/` で差分 0 行を確認
  - AC-001-2: `--min-pink-ratio 0.1` 指定で `pink_ratio < 0.1` の人物は pink_id=1 候補から除外される
  - AC-001-3: 値域外（`--min-pink-ratio -0.1` / `--min-pink-ratio 1.5` / `--min-pink-ratio abc`）で exit code 2

### FR-002: サマリ出力に閾値表示

- **概要**: 実行時の `min-pink-ratio` 値をサマリ標準出力に表示し、再現性を高める
- **出力**: 標準出力末尾に 1 行追加
- **処理内容**: `Min pink ratio threshold: 0.XXX` 形式で表示
- **受け入れ基準**:
  - AC-002-1: サマリ最終行付近に閾値値が表示される

### FR-003: select_pink_bbox 関数の引数化

- **概要**: 既存 `select_pink_bbox` 関数内で `MIN_PINK_RATIO` を参照している部分を引数化
- **入力**: `select_pink_bbox` のシグネチャに `min_pink_ratio` 引数追加
- **処理内容**:
  - シグネチャ: `select_pink_bbox(bboxes, ratios, prev_selected_bbox, min_pink_ratio)`
  - 関数内 `candidates = [i for i, r in enumerate(ratios) if r >= MIN_PINK_RATIO]` を `>= min_pink_ratio` に変更
- **受け入れ基準**:
  - AC-003-1: 関数が引数経由で閾値を受け取る
  - AC-003-2: main 側から `args.min_pink_ratio` が渡される

## 4. 非機能要求

### NFR-001: パフォーマンス

- 改修前と同等。閾値比較演算は既存と同じく O(1)、追加コストなし

### NFR-002: 対応環境

- 既存と同一（Python 3.10.16、uv）

### NFR-003: 後方互換性

- `--min-pink-ratio` 未指定時の挙動は改修前と**完全一致**（JSON ファイル diff 0）
- 既存 JSON 出力形式は変更なし
- 下流スクリプト（feat-035 / 036 / 037 / 038 / 039 / 040 / 041 / 042 / 048 / 049）は変更不要

## 5. 制約条件

### 5.1 使用ライブラリ

- 既存依存のみ（追加なし）

### 5.2 追加禁止

- 出力 JSON フィールドの追加（閾値値を JSON に保存しない、本案件のスコープ外）
- 他の定数（`IOU_CONT_WEIGHT` 等）の CLI 化（本案件のスコープ外）

## 6. 優先順位

| ID | 機能 | 優先度 |
|----|------|--------|
| FR-001 | CLI 引数追加 | Must |
| FR-002 | サマリ閾値表示 | Should |
| FR-003 | select_pink_bbox 引数化 | Must |
