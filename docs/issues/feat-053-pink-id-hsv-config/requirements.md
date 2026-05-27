# feat-053 要求仕様書: postprocess_pink_id.py の HSV 設定ファイル読み込み対応

## 1. プロジェクト概要

### 1.1 何を作るのか

`scripts/postprocess_pink_id.py` に CLI 引数 `--hsv-config <path>` を追加し、JSON 設定ファイルから `fixed_hsv_ranges`（ピンク判定の HSV レンジ集合）と `min_pink_ratio`（pink_id=1 候補の最低 pink_ratio）を読み込めるようにする。これによりハードコードされた定数 `FIXED_HSV_RANGES` を、ソースコードを編集せずに患者ごとへ差し替え可能にする。

### 1.2 なぜ作るのか

feat-052 の調査で、本番患者の淡いピンク服が、テスト動画由来でハードコードされた `FIXED_HSV_RANGES` とズレており pink_ratio が取りこぼされる（実例 `E0014-01.png` で current pink_ratio=0.0099、推奨レンジでは 0.6046）ことが判明した。患者ごとに最適な HSV レンジと閾値を、ソース編集なしで差し替えられるようにする必要がある。

### 1.3 誰が使うのか

本プロジェクトの開発者（患者ごとの色レンジ調整・pink_id 付与担当）。

### 1.4 どこで使うのか

既存スクリプトと同一環境（uv 環境、Python 3.10.16）。

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| `FIXED_HSV_RANGES` | 既存グローバル定数。ピンク画素マスクを作る HSV レンジのリスト。各要素は `(lo, hi)` で `lo`/`hi` は `(H, S, V)` |
| `min_pink_ratio` | pink_id=1 候補とする `pink_ratio` の最低値。既存定数 `MIN_PINK_RATIO=0.03`、feat-050 で `--min-pink-ratio` 化済み |
| HSV 設定ファイル（hsv-config） | 本案件で追加する JSON ファイル。キー `fixed_hsv_ranges` と `min_pink_ratio` を持つ「患者プロファイル」 |
| `fixed_hsv_ranges`（キー） | 設定ファイルのキー。JSON 配列 `[[[H,S,V],[H,S,V]], ...]`。各要素が 1 レンジ `[lo, hi]` |
| `min_pink_ratio`（キー） | 設定ファイルのキー。数値、値域 `[0.0, 1.0]` |
| 明示指定 | CLI で `--min-pink-ratio` が実際に渡されたこと。argparse のデフォルト値が使われた状態と区別する |

機能設計書・コード内でも本表の用語を用いる。

## 3. 機能要求一覧

### FR-001: CLI 引数 `--hsv-config` の追加

- **概要**: `postprocess_pink_id.py` に `--hsv-config` を追加する。省略可能（デフォルト None）
- **入力**: `--hsv-config <path>`（str、JSON ファイルパス）
- **処理内容**:
  1. 指定時、ファイルを読み JSON パースする
  2. スキーマ検証する（FR-002）
  3. `fixed_hsv_ranges` を pink_ratio 計算に、`min_pink_ratio` を候補選択に使う（後者は FR-003 の優先順位に従う）
  4. 未指定時、従来通りグローバル `FIXED_HSV_RANGES` と既定 `min_pink_ratio` を使う
- **出力**: 設定ファイルのレンジ・閾値が反映された pink_id 付与済み JSON
- **受け入れ基準**:
  - AC-001-1: `--hsv-config` 未指定かつ `--min-pink-ratio` 未指定時の出力は改修前と完全一致。検証手順: 改修前コード（`git stash` で退避）と改修後コードでそれぞれ `experiments/results/camSony1_S_pink_json_before/` / `_after/` を生成し `diff -r before/ after/` で差分 0 行を確認
  - AC-001-2: サンプル設定ファイル（`example_hsv_config.json`。`fixed_hsv_ranges` は現状 `FIXED_HSV_RANGES` と同値、`min_pink_ratio` は `MIN_PINK_RATIO`=0.03 と同値）を `--hsv-config` で指定した出力は、`--hsv-config` 未指定の出力と完全一致（`diff -r` で差分 0 行）。`min_pink_ratio` を 0.03 とするのは FR-003 で config 値が CLI デフォルトより優先されるため（0.03 以外だと差分が出る）

### FR-002: 設定ファイルのスキーマ検証

- **概要**: 設定ファイルの構造・値域を厳密に検証し、不正なら明確なエラーメッセージで終了する
- **入力**: パース済み JSON
- **処理内容**: 以下をすべて検証し、1 つでも満たさなければ標準エラーにメッセージを出して exit code 1:
  1. トップレベルが JSON オブジェクト（dict）であること
  2. キー `fixed_hsv_ranges` と `min_pink_ratio` が**両方存在**すること（B-1: 両キー必須）
  3. `fixed_hsv_ranges`: 空でない配列。各要素 `r` は長さ 2 の配列 `[lo, hi]`。`lo`/`hi` はそれぞれ長さ 3 の `[H,S,V]`。各値は整数（bool・float は不可。`153.0` のような小数表記もエラー。HSV は整数表記に統一する）。`H ∈ [0,179]`、`S ∈ [0,255]`、`V ∈ [0,255]`。各成分で `lo[i] <= hi[i]`
  4. `min_pink_ratio`: 数値（int/float、bool 不可）、値域 `[0.0, 1.0]`
- **出力**: 検証 OK なら `(ranges, min_pink_ratio)` を返す。NG なら exit code 1
- **受け入れ基準**:
  - AC-002-1: ファイルが存在しない → exit 1、メッセージにパスを表示
  - AC-002-2: JSON パース不能 → exit 1
  - AC-002-3: キー欠如（`fixed_hsv_ranges` のみ / `min_pink_ratio` のみ）→ exit 1、欠けたキー名を表示
  - AC-002-4: 構造不正（要素長さ違い、`H=200`、`H=153.0`（小数）、`lo>hi` 等）→ exit 1、該当箇所を示すメッセージ
  - AC-002-5: `min_pink_ratio` が値域外（`-0.1` / `1.5`）→ exit 1

### FR-003: `min_pink_ratio` の優先順位

- **概要**: 設定ファイルと CLI `--min-pink-ratio` の両方が `min_pink_ratio` を指定しうる。優先順位を **CLI明示 > 設定ファイル > デフォルト** とする（A-1）
- **入力**: CLI の `--min-pink-ratio`、設定ファイルの `min_pink_ratio`、定数 `MIN_PINK_RATIO`
- **処理内容**:
  1. `--min-pink-ratio` が明示指定された場合 → その値
  2. それ以外で `--hsv-config` 指定があれば → 設定ファイルの `min_pink_ratio`
  3. どちらもなければ → `MIN_PINK_RATIO`（0.03）
- **受け入れ基準**:
  - AC-003-1: 設定ファイル `min_pink_ratio=0.05`、CLI 未指定 → 0.05 が使われる（サマリ表示で確認）
  - AC-003-2: 設定ファイル `min_pink_ratio=0.05`、CLI `--min-pink-ratio 0.1` → 0.1 が使われる（CLI 勝ち）
  - AC-003-3: 両方未指定（`--hsv-config` なし、`--min-pink-ratio` なし）→ 0.03

### FR-004: `compute_pink_ratio` の引数化

- **概要**: `compute_pink_ratio` がレンジを引数で受け取れるようにする。後方互換のため `ranges=None` デフォルトで従来のグローバル参照を維持する
- **入力**: シグネチャ `compute_pink_ratio(roi_bgr, ranges=None)`
- **処理内容**: `ranges` が `None` なら `FIXED_HSV_RANGES` を使う。それ以外は渡されたレンジを使う
- **受け入れ基準**:
  - AC-004-1: `compute_pink_ratio(roi)`（引数なし）の結果が改修前と一致する（`analyze_clothing_color.py` 後方互換）
  - AC-004-2: `compute_pink_ratio(roi, ranges=R)` で渡したレンジが使われる
  - AC-004-3: main 側から設定ファイル or グローバルのレンジが渡される

### FR-005: サマリ出力に設定情報を表示

- **概要**: 実行時に使った設定ファイルパス・有効レンジ・`min_pink_ratio` をサマリに表示し、再現性を高める
- **出力**: 標準出力のサマリブロックに追加
- **処理内容**: 以下 3 行を出す（`min_pink_ratio` 行は既存を流用）:
  - `HSV config: <path>` または `HSV config: default (built-in FIXED_HSV_RANGES)`
  - `Active HSV ranges: [...]`
  - `Min pink ratio threshold: 0.XXX`（値は FR-003 の解決結果）
- **受け入れ基準**:
  - AC-005-1: 設定ファイル指定時、そのパスと有効レンジが表示される
  - AC-005-2: 未指定時、`HSV config: default (built-in FIXED_HSV_RANGES)` と表示される

## 4. 非機能要求

### NFR-001: パフォーマンス

追加コストは起動時の設定ファイル読み込み 1 回のみ。フレームループ内の計算量は改修前と不変。

### NFR-002: 対応環境

既存と同一（Python 3.10.16、uv 環境）。

### NFR-003: 後方互換性

- `--hsv-config` 未指定かつ `--min-pink-ratio` 未指定時の出力は改修前と**完全一致**（JSON diff 0）
- `FIXED_HSV_RANGES` / `MIN_PINK_RATIO` 定数は残し、import している `analyze_clothing_color.py`（`compute_pink_ratio`・`FIXED_HSV_RANGES`）と `plot_pink_ratio_timeline.py`（`MIN_PINK_RATIO`）は**無変更で動作**する
- 出力 JSON 形式は変更なし。下流スクリプト（feat-035 / 036 / 037 / 038 / 039 / 040 / 041 / 042 / 048 / 049）は変更不要

## 5. 制約条件

### 5.1 使用ライブラリ

既存依存のみ。`json` は標準ライブラリ。追加ライブラリなし。

### 5.2 追加禁止

- CLI への数値 HSV レンジ引数の追加（レンジは設定ファイル経由のみ）
- 設定ファイルへの version フィールド
- 出力 JSON フィールドの追加（有効レンジ・閾値を JSON に保存しない。標準出力ログから確認）
- 他定数（`IOU_CONT_WEIGHT` 等）の外部化（本案件のスコープ外）

## 6. 優先順位

| ID | 機能 | 優先度 |
|----|------|--------|
| FR-001 | `--hsv-config` 追加 | Must |
| FR-002 | スキーマ検証 | Must |
| FR-003 | `min_pink_ratio` 優先順位 | Must |
| FR-004 | `compute_pink_ratio` 引数化 | Must |
| FR-005 | サマリ表示 | Should |

MVP: FR-001〜FR-004。
