# feat-039 要求仕様書: postprocess_pink_id.py に pink_ratio フィールド追加（デバッグ用）

## 1. プロジェクト概要

### 1.1 何を作るのか

`scripts/postprocess_pink_id.py` の出力 JSON の各 `people[i]` に、当該 BB の HSV ピンク画素比率を表す浮動小数点フィールド `pink_ratio` を追加する改修。

### 1.2 なぜ作るのか

現行実装は各 BB のピンク比率を内部で計算しているが、選択結果 `pink_id`（1 / -1）しか JSON に残さない。閾値 `MIN_PINK_RATIO = 0.03` の妥当性検証や、feat-037 の時系列グラフで検出された「対象不在区間での `pink_id=1` 誤検出」の原因解析時に、フレーム・BB 単位のピンク比率を後追いで取得できず、再実行が必要となっていた。本改修により 1 回のポストプロセス実行で比率まで保存し、後段の解析を容易にする。

### 1.3 誰が使うのか

本プロジェクトの開発者（`pink_id` の閾値チューニング・誤検出解析を行う者）。

### 1.4 どこで使うのか

既存 `scripts/postprocess_pink_id.py` と同一の実行環境（uv 環境、CPU のみ、OpenCV + numpy）。実行 CLI・引数・入出力ディレクトリ規約は変更しない。

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| pink_id | 既存フィールド。選択 BB は 1、非選択は -1。本案件では変更しない |
| pink_ratio | 本案件で新規追加する浮動小数点フィールド。値域 [0.0, 1.0]。当該 BB の HSV ピンクマスク画素数 / BB 総画素数 |
| BB 欠損 person | 入力 JSON の `people[i]` で `bbox` フィールドが欠落、または長さ 4 でない人物エントリ。既存実装では WARNING ログを出して `ratios[i] = 0.0` として扱われる |
| 生 dict 保持設計 | feat-033 / 035 / 036 共通の設計方針。入力 JSON の既存フィールドを変更せず、新規フィールドのみ追加して書き出す |

## 3. 機能要求一覧

### FR-001: pink_ratio フィールドの付与

- **概要**: `scripts/postprocess_pink_id.py` が出力する JSON の各 `people[i]` に、当該 BB に対する `compute_pink_ratio` の戻り値を `pink_ratio` として保存する
- **入力**: 既存と同じ（動画ファイル、HALPE 26 JSON ディレクトリ、出力ディレクトリ）
- **出力**: 既存の出力 JSON に `pink_ratio: float`（値域 [0.0, 1.0]）が各 `people[i]` に追加される
- **処理内容**:
  1. 各 BB について既存の `compute_pink_ratio` を呼び出す（既存処理をそのまま利用）
  2. `pink_id` を付与する既存ループ内で、同じ人物エントリに `person["pink_ratio"] = ratios[i]` を追加する
- **受け入れ基準**:
  - AC-001-1: 出力 JSON の全 `people[i]` に `pink_ratio` キーが存在する
  - AC-001-2: `pink_ratio` の値は常に [0.0, 1.0] の範囲に収まる
  - AC-001-3: `pink_ratio >= 0.03` かつ当該フレーム内で最大スコアの人物だけが `pink_id = 1` を持つ（既存挙動と整合）
  - AC-001-4: 同一 BB に対して 2 回実行しても `pink_ratio` の値は一致する（決定的処理）

### FR-002: BB 欠損 person の値規約

- **概要**: `bbox` が欠落または不正な `people[i]` に対する `pink_ratio` の値を定義する
- **入力**: `bbox` キーが存在しない、または値の長さが 4 でない人物エントリ
- **出力**: 当該 `people[i]` に `pink_ratio: 0.0` を付与する
- **処理内容**:
  1. 既存実装では `bboxes.append(None); ratios.append(0.0)` として扱われている
  2. 同じ `ratios[i]`（= 0.0）をそのまま `pink_ratio` として書き込む
- **受け入れ基準**:
  - AC-002-1: `bbox` 欠損 person の出力に `pink_ratio = 0.0` が書き込まれている
  - AC-002-2: 既存の WARNING ログ（`WARNING: Missing/invalid bbox in frame ...`）は変更せず残る

### FR-003: 既存フィールド・CLI の非変更

- **概要**: `pink_id` の選択ロジック、CLI 引数、入出力ディレクトリ規約、サマリ出力を変更しない
- **入力**: 既存と同じ
- **出力**: 既存と同じ（`pink_ratio` の追加以外に差分を生じない）
- **受け入れ基準**:
  - AC-003-1: `pink_id = 1` になる BB の集合は改修前と完全一致する（同一入力・同一乱数条件）
  - AC-003-2: CLI 引数 `--video` / `--json-dir` / `--out-dir` は変更されない
  - AC-003-3: サマリ出力の項目（以下 7 項目）・項目名・出力順が改修前と完全一致する
    1. `Total frames`
    2. `Frames with pink_id=1`
    3. `Frames without candidate (no valid bbox candidate above threshold)`
    4. `Frames without json`
    5. `Continuity breaks`
    6. `Processing time: {elapsed:.1f} sec ({fps:.1f} fps)`
    7. `Output directory`

## 4. 非機能要求

### NFR-001: パフォーマンス

- 既存実装に対し、同一入力（camSony1_L.mp4、約 321K フレーム）で処理時間の増加が 5% 以内に収まる
  - 根拠: `compute_pink_ratio` は既に全 BB に対して計算済みであり、本改修は Python dict への代入 1 行の追加のみ

### NFR-002: 下流互換性

- feat-035 `postprocess_track.py` / feat-036 `postprocess_patient_id.py` / feat-037 `plot_pink_track_timeline.py` / feat-038 `visualize_patient_video.py` が改修後の JSON を既存と同じ挙動で処理できる
  - 根拠: いずれも生 dict 保持設計で未知フィールドを無視する

### NFR-003: 対応環境

- 既存 `postprocess_pink_id.py` と同一（Python 3.10.16、uv 環境、CPU 実行、OpenCV + numpy）

## 5. 制約条件

### 5.1 使用必須のライブラリ

- 既存依存のみ（OpenCV、numpy、json 標準ライブラリ）。追加ライブラリの導入は行わない

### 5.2 追加禁止

- 閾値 `MIN_PINK_RATIO` / `IOU_CONT_WEIGHT` / `FIXED_HSV_RANGES` の変更は本案件のスコープ外
- `pink_id` 選択ロジックの変更は本案件のスコープ外
- CLI 引数の追加（例: `--write-pink-ratio` のような ON/OFF フラグ）は行わない。デバッグ目的ではあるが、計算コストがゼロに近いため常時書き込みとする

### 5.3 フィールド名

- 新規フィールド名は `pink_ratio` に固定する。他候補（`pink_score`, `hsv_pink_ratio` など）は採用しない
  - 理由: requirements.md / design.md の feat-033 で用語「ピンク比率」を `pink_ratio` と表記しており整合するため

## 6. 優先順位

| ID | 機能 | 優先度 |
|----|------|--------|
| FR-001 | pink_ratio フィールドの付与 | Must |
| FR-002 | BB 欠損 person の値規約 | Must |
| FR-003 | 既存フィールド・CLI の非変更 | Must |

MVP = FR-001 + FR-002 + FR-003。本案件はすべて Must であり、Should / Could / Won't はなし。
