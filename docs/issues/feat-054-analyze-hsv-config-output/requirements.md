# feat-054 要求仕様書: analyze_clothing_color.py の HSV 設定ファイル（JSON）出力対応

## 1. プロジェクト概要

### 1.1 何を作るのか

`scripts/analyze_clothing_color.py` に、`propose_hsv_ranges()` が算出した推奨 HSV レンジを
feat-053 互換の JSON 設定ファイル（キー `fixed_hsv_ranges` + `min_pink_ratio`）として
ファイルへ書き出す機能を追加する。デフォルトで PNG と並んで常時出力し、`--json-out` で
出力パスを上書きできる。

### 1.2 なぜ作るのか

feat-053 で `postprocess_pink_id.py --hsv-config <JSON>` を実装したが、その JSON の中身は
`analyze_clothing_color.py` が stdout に出力する `proposed FIXED_HSV_RANGES` を**人手で写経**して
作っていた（実例: `scripts/conf/E0014.json`）。写経は転記ミスを招くため、analyze 側が
postprocess がそのまま読める JSON を直接吐くことでコピペ作業をなくす。

これは feat-052/053 で確定した「案C（JSON 設定ファイル経由）」の**機能②**にあたる。

### 1.3 誰が使うのか

本プロジェクトの開発者（対象ごとの色レンジ調整・pink_id 付与担当）。

### 1.4 どこで使うのか

既存スクリプトと同一環境（uv 環境、Python 3.10.16）。
`uv run python scripts/analyze_clothing_color.py <画像>` をプロジェクトルートから実行する。

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| 推奨レンジ（proposed_ranges） | `propose_hsv_ranges()` が返す `list[tuple[tuple[int,int,int], tuple[int,int,int]]]`。各要素は `(lo, hi)`、`lo`/`hi` は `(H, S, V)`。色相環またぎ時は 2 要素になる |
| HSV 設定ファイル | feat-053 で定義した JSON 形式。キー `fixed_hsv_ranges` と `min_pink_ratio` を持つ対象プロファイル |
| `fixed_hsv_ranges`（キー） | JSON 配列 `[[[H,S,V],[H,S,V]], ...]`。各要素が 1 レンジ `[lo, hi]` |
| `min_pink_ratio`（キー） | 数値、値域 `[0.0, 1.0]`。本案件では固定値 `MIN_PINK_RATIO`（=0.03）を出力する |
| 空レンジ | `propose_hsv_ranges()` が `[]` を返す状態（ROI に有彩色画素が 1 つもない場合） |

機能設計書・コード内でも本表の用語を用いる。feat-053 が定義した設定ファイルスキーマと完全に一致させる。

## 3. 機能要求一覧

### FR-001: 推奨レンジを feat-053 互換 JSON として書き出す

- **概要**: `propose_hsv_ranges()` の `proposed_ranges` を、`postprocess_pink_id.load_hsv_config()`
  がそのまま受理できる JSON 設定ファイルとして書き出す
- **入力**: 推奨レンジ `proposed_ranges`（`propose_hsv_ranges()` の戻り値）
- **処理内容**:
  1. 出力 dict を構築する:
     - `fixed_hsv_ranges`: `proposed_ranges` を `[[ [H,S,V], [H,S,V] ], ...]` の入れ子リストへ変換
       （tuple → list。各値は Python `int`）
     - `min_pink_ratio`: `MIN_PINK_RATIO`（=0.03、`postprocess_pink_id` から import 済みの定数）
  2. `scripts/conf/*.json` と同じ compact 形式（1 レンジ `[[H,S,V],[H,S,V]]` = 1 行）でファイルへ書き出す
- **出力**: JSON 設定ファイル（既存なら上書き）
- **受け入れ基準**:
  - AC-001-1: 出力 JSON のトップレベルキーは `fixed_hsv_ranges` と `min_pink_ratio` の 2 つだけ
  - AC-001-2: 出力 JSON を `postprocess_pink_id.load_hsv_config(<出力パス>)` に渡すと検証を通過し、
    `(ranges, 0.03)` を返す（exit せず正常に読める）
  - AC-001-3: `fixed_hsv_ranges` の各値は整数（小数表記 `153.0` ではなく `153`）。
    `min_pink_ratio` は `0.03`
  - AC-001-4: 出力 JSON の `fixed_hsv_ranges` を tuple 化したものが、その実行の
    `proposed_ranges` と一致する（stdout に出る `proposed FIXED_HSV_RANGES` と同一内容）

### FR-002: JSON 出力パスの決定（常時出力）

- **概要**: JSON は実行のたびに常時書き出す。出力パスはデフォルトで画像と同じ stem を使い、
  `--json-out` で上書きできる
- **入力**: CLI `--json-out <path>`（str、省略可、デフォルト None）
- **処理内容**:
  1. `--json-out` 指定時 → そのパス
  2. 未指定時 → `<画像 stem>_hsv_config.json`（例: `testdata/E0014-01.png` → `testdata/E0014-01_hsv_config.json`）。
     PNG のデフォルト（`<画像 stem>_color_analysis.png`）と同じ規約に揃える
- **出力**: 決定された出力パス
- **受け入れ基準**:
  - AC-002-1: `--json-out` 未指定時、`<画像 stem>_hsv_config.json` が生成される
  - AC-002-2: `--json-out path/to/x.json` 指定時、`path/to/x.json` が生成される
  - AC-002-3: JSON 出力パスが書き出された旨が stdout に `[INFO]` で表示される

### FR-003: 空レンジ時の振る舞い

- **概要**: 推奨レンジが空（`proposed_ranges == []`、有彩色画素なし）の場合、JSON は書き出さない
- **入力**: `proposed_ranges`（空配列）
- **処理内容**:
  1. `proposed_ranges` が空なら JSON ファイルを作らず、`[WARN]` で「推奨レンジが空のため
     設定ファイルを出力しない」旨を表示する
  2. PNG 出力（既存）は従来通り実行する。スクリプト全体の exit code は PNG 出力の成否で決まる
     （空レンジ自体は exit 1 の理由にしない）
- **出力**: JSON は生成されない。`[WARN]` ログのみ
- **受け入れ基準**:
  - AC-003-1: 空レンジ時、JSON ファイルが生成されない
  - AC-003-2: 空レンジ時でも PNG は従来通り出力され、exit code は 0（PNG 出力成功時）
- **方針の根拠（AC ではない）**: 空配列を `fixed_hsv_ranges` に入れた JSON は `load_hsv_config` の
  「非空配列」検証で exit 1 になる不正設定のため、空レンジ時は書き出さない（設計 ADR-3 参照）

## 4. 非機能要求

### NFR-001: パフォーマンス

追加コストは推論後の JSON 書き出し 1 回のみ。推論・ROI 構築・色測定・PNG 生成の処理量は改修前と不変。

### NFR-002: 対応環境

既存と同一（Python 3.10.16、uv 環境、CUDA GPU）。

### NFR-003: 後方互換性

- 既存の stdout ログ・PNG 出力（`render_analysis_png`）の内容・パス規約は**不変**
- `postprocess_pink_id.py` / `merge_halpe26.py` は**無変更**。import 関係も変えない
  （新たに `MIN_PINK_RATIO` を import するだけ。同モジュールに既存の定数）
- feat-053 が定義した設定ファイルスキーマと完全一致させ、`load_hsv_config` がそのまま読めること

## 5. 制約条件

### 5.1 使用ライブラリ

既存依存のみ。`json` は標準ライブラリ。追加ライブラリなし。

### 5.2 追加禁止

- `min_pink_ratio` を CLI 引数や設定で可変にする（本案件では固定 0.03。静止画では動画 BB 比率としての
  適切値を決められないため、実運用での調整は `postprocess_pink_id.py --min-pink-ratio` 側で行う）
- 設定ファイルへの version フィールドや追加キー（feat-053 スキーマと厳密一致を保つ）
- `postprocess_pink_id.py` / `merge_halpe26.py` の変更
- PNG 出力ロジック・既存 stdout ログの変更

## 6. 優先順位

| ID | 機能 | 優先度 |
|----|------|--------|
| FR-001 | 推奨レンジを feat-053 互換 JSON へ書き出す | Must |
| FR-002 | JSON 出力パスの決定（常時出力・`--json-out`） | Must |
| FR-003 | 空レンジ時の振る舞い | Must |

MVP: FR-001〜FR-003（全て Must）。
