# feat-040 要求仕様書: pink_ratio 時系列可視化グラフ

## 1. プロジェクト概要

### 1.1 何を作るのか

feat-039 改修済み `postprocess_pink_id.py` の出力 JSON ディレクトリを入力とし、各フレームの全 BB の `pink_ratio`（HSV ピンク画素比率、float、値域 [0.0, 1.0]）を時系列で 4 パネル構成の PNG グラフに描画するスタンドアロンスクリプト `scripts/plot_pink_ratio_timeline.py` を新規作成する。

### 1.2 なぜ作るのか

feat-039 で各 BB の `pink_ratio` を JSON に保存できるようになったが、`pink_id` の選択結果（1 / -1）と各 BB の比率を**時系列で並べて見る手段がない**。特に「ピンクの病院着を着ている患者ではない別人に `pink_id=1` が付いてしまった」場面で、(a) 選択 BB と次点 BB の比率がどれだけ拮抗していたか、(b) 同フレームに何個の候補が居たか、(c) 閾値 `MIN_PINK_RATIO=0.03` の妥当性を時系列で目視確認する手段が必要。本グラフはこれを満たすための診断ツールである。

### 1.3 誰が使うのか

本プロジェクトの開発者（`pink_id` の誤検出区間を解析・閾値チューニングを行う者）。

### 1.4 どこで使うのか

既存 `scripts/plot_pink_track_timeline.py` と同一の実行環境（uv 環境、CPU のみ、matplotlib + 標準ライブラリ）。GPU・動画ファイル読み込みは不要。

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| pink_ratio | feat-039 で各 `people[i]` に保存される HSV ピンク画素比率。float、値域 [0.0, 1.0] |
| pink_id | 既存フィールド。選択 BB は 1、それ以外は -1 |
| 候補 BB | `pink_ratio >= MIN_PINK_RATIO`（= 0.03）を満たす BB |
| 非候補 BB | `pink_ratio < MIN_PINK_RATIO`（= 0.03）の BB |
| 選択 BB | 当該フレームで `pink_id == 1` の BB。0 個または 1 個 |
| 次点 BB | 同フレーム全 BB のうち `pink_ratio` の値で **2 位** の BB（選択 BB を含めた全体ランキングでの 2 位）。BB が 0–1 個のフレームでは存在しない |
| 際どい差分 | `selected_ratio − runner_up_ratio < 0.05` を満たすフレーム（負値も含む。すなわち「選択 BB の `pink_ratio` 優位性が 0.05 未満、または選択 BB が ratio 上で 1 位ですらない」状態を指す）。`IOU_CONT_WEIGHT = 0.05`（連続性ボーナス重み）と整合させた値 |
| MIN_PINK_RATIO | `postprocess_pink_id.py` が候補判定に使う閾値。値は 0.03 |
| BB ゼロフレーム | `people` リストが空のフレーム |

注記: 本スクリプトは動画ファイルを読まず、`--json-dir` 配下に存在する JSON のみを対象とする。動画上のフレームと JSON ディレクトリの対応関係は検証しない（動画上の欠損は検知不可）。「JSON 欠損」という概念は本スクリプトの範囲外。

## 3. 機能要求一覧

### FR-001: タイムラインデータ収集

- **概要**: 入力 JSON ディレクトリ全体を読み込み、フレームごとに描画用の構造化データを構築する
- **入力**: `--json-dir` 引数で指定された JSON ディレクトリ。各 JSON は `{"version": ..., "people": [...]}` 形式で、各 `people[i]` に `bbox`, `pink_id`, `pink_ratio` を含む
- **出力**: メモリ上の構造化データ（フレーム数 × 各種系列）
- **処理内容**:
  1. ディレクトリ内の `*_{6 桁}.json` をソートし、フレーム番号を抽出
  2. JSON 解析失敗 / `people` キー欠損は WARNING ログ出力で空 people 扱い
  3. 各フレームについて以下を集計:
     - 全 BB の `(frame, pink_ratio, pink_id)` タプル列
     - 選択 BB の `pink_ratio`（無いフレームは None）
     - 次点 BB の `pink_ratio`（BB が 2 個以上のフレームのみ、無いフレームは None）
     - 候補 BB 数（pink_id=1）、候補 BB 数（pink_id=-1 かつ ratio≥0.03）、非候補 BB 数（pink_id=-1 かつ ratio<0.03）
- **受け入れ基準**:
  - AC-001-1: フレーム数 N の入力に対して、内部データの全系列が長さ N（または該当フレームのみ要素を持つ疎な構造）になる
  - AC-001-2: JSON 解析失敗フレームでは空 people として処理され、エラーで停止しない
  - AC-001-3: `pink_ratio` フィールドが欠落している `people[i]` に遭遇した場合は `pink_ratio = 0.0` として扱う（feat-039 改修以前の JSON との後方互換）

### FR-002: Panel 1 — 全 BB の pink_ratio 散布図

- **概要**: 横軸フレーム番号、縦軸 `pink_ratio` の散布図を描き、`pink_id` 値で色分けする。閾値ラインを重ねる
- **入力**: FR-001 の構造化データ
- **出力**: matplotlib の Axes に描画された Panel 1
- **処理内容**:
  1. `pink_id == 1` の BB をマゼンタ（`s=4`、`alpha=0.7`）で散布
  2. `pink_id == -1` かつ `pink_ratio >= 0.03` の BB を黒（`s=2`、`alpha=0.4`）で散布
  3. `pink_id == -1` かつ `pink_ratio < 0.03` の BB を灰（`s=1`、`alpha=0.2`）で散布
  4. `pink_ratio = MIN_PINK_RATIO`（= 0.03）の水平点線を赤で描画
  5. 縦軸範囲は [0.0, 1.05]
  6. 凡例を右上に表示（"selected"、"candidate"、"non-candidate"、"threshold=0.03"）
- **受け入れ基準**:
  - AC-002-1: 入力 JSON 上で `pink_id=1` のフレーム数だけマゼンタ点が描画される
  - AC-002-2: 閾値ライン（赤点線、y=0.03）が描画されている
  - AC-002-3: 縦軸の範囲が [0.0, 1.05] に固定される

### FR-003: Panel 2 — pink_id=1 の有無タイムライン

- **概要**: 各フレームで `pink_id=1` の BB が存在するかしないかを 0 / 1 のステップ塗りで描く
- **入力**: FR-001 の構造化データ（has_pink_id 系列）
- **出力**: matplotlib の Axes に描画された Panel 2
- **処理内容**:
  1. `fill_between(frames, has_pink_id, step="mid", color="hotpink", alpha=0.7)` で塗りつぶし
  2. 縦軸範囲 [-0.1, 1.3]、ラベル `"pink_id=1\n(0/1)"`
- **受け入れ基準**:
  - AC-003-1: `pink_id=1` のフレームで縦軸 = 1、それ以外で縦軸 = 0 となる
  - AC-003-2: feat-037 の同種パネルと視覚的に整合（色 hotpink、step="mid"、alpha=0.7）

### FR-004: Panel 3 — フレームごとの BB 数（3 系列）

- **概要**: フレームごとの BB 数を 3 系列の折れ線で描画する
- **入力**: FR-001 の構造化データ（count_selected / count_candidate_other / count_non_candidate）
- **出力**: matplotlib の Axes に描画された Panel 3
- **処理内容**:
  1. `pink_id=1` の数（マゼンタ、線幅 0.5）
  2. `pink_id=-1 かつ ratio>=0.03` の数（黒、線幅 0.5）
  3. `pink_id=-1 かつ ratio<0.03` の数（灰、線幅 0.5）
  4. 凡例を右上に表示
  5. 縦軸ラベル `"BB count"`、縦軸範囲は auto
- **受け入れ基準**:
  - AC-004-1: 任意のフレームで「選択数 + 候補数（その他）+ 非候補数」が当該フレームの `len(people)` と一致する
  - AC-004-2: 3 系列が凡例で区別できる

### FR-005: Panel 4 — 選択 BB と次点 BB の差分

- **概要**: 「選択 BB の `pink_ratio` − 次点 BB の `pink_ratio`」を散布点で描画し、際どい差分（< 0.05）のフレームを赤背景帯で強調する
- **入力**: FR-001 の構造化データ（selected_ratio / runner_up_ratio）
- **出力**: matplotlib の Axes に描画された Panel 4
- **処理内容**:
  1. 選択 BB と次点 BB の双方が存在するフレームについて差分 `selected_ratio − runner_up_ratio` を計算
  2. 差分を青の散布点（`s=2`、`alpha=0.5`）で描画
  3. `selected_ratio − runner_up_ratio < 0.05`（負値含む）のフレームを赤背景 `axvspan(alpha=0.15)` で強調
  4. y=0 の水平点線（黒、`alpha=0.5`）を補助線として描画
  5. 縦軸範囲 [-0.5, 1.05]（負値は「次点が選択より大きい = 連続性ボーナスで反転した」事象を含むため）
  6. 縦軸ラベル `"selected − runner-up\nratio"`
- **受け入れ基準**:
  - AC-005-1: BB が 2 個以上のフレームのみが描画される（0–1 個のフレームでは点なし）
  - AC-005-2: `selected_ratio − runner_up_ratio < 0.05`（負値含む）の連続区間が赤背景帯で塗られる
  - AC-005-3: 差分が負になり得る（`select_pink_bbox` の連続性ボーナスにより、選択 BB が ratio 1 位でないことがあり得るため）

### FR-006: 次点 BB の決定ロジック

- **概要**: 各フレームの「次点 BB」を定義する
- **入力**: 同フレームの全 `people[i]`
- **出力**: 次点 BB の `pink_ratio`（無い場合は None）
- **処理内容**:
  1. 当該フレームの全 BB を `pink_ratio` の降順でソート
  2. 2 位の BB の `pink_ratio` を返す（同値タイは安定ソートに任せ、選択 BB を含めた全体での 2 位とする＝ 案 a-2）
  3. BB が 0 個または 1 個のフレームは None を返す
- **受け入れ基準**:
  - AC-006-1: BB 数 ≥ 2 のフレームでは必ず None でない値が返る
  - AC-006-2: BB 数 < 2 のフレームでは None が返る
  - AC-006-3: 選択 BB が `pink_ratio` 1 位でないフレームでは、選択 BB を「次点」として扱わない（全体 2 位はあくまで全体のソート結果での 2 位）

### FR-007: CLI インタフェース

- **概要**: コマンドライン引数を受け取り、PNG ファイルを出力する
- **入力**: コマンドライン引数
- **出力**: 指定パスに 1 枚の PNG
- **処理内容**:
  1. 必須引数: `--json-dir`（入力ディレクトリ）、`--out-path`（出力 PNG パス）
  2. 任意引数（Should）: `--frame-start`（int、デフォルト 0）、`--frame-end`（int、デフォルト -1 = 最終フレーム）。指定範囲のフレームのみ描画。**値は JSON ファイル名末尾の 6 桁フレーム番号**（feat-039 出力規約：`{stem}_{6桁}.json`）であり、ソート後の連番インデックスではない
  3. 出力 PNG の親ディレクトリは存在しなければ自動作成
  4. グラフ全体のタイトル: `"pink_ratio timeline — {dir_name} ({n} frames drawn / {n_total} total)"`
  5. PNG 解像度 dpi=150、図サイズ `(16, 12)` インチ（feat-037 と同等）
- **受け入れ基準**:
  - AC-007-1: `--json-dir` が存在しないと ERROR で異常終了する
  - AC-007-2: `--out-path` の親ディレクトリが存在しなくても自動作成される
  - AC-007-3: `--frame-start` / `--frame-end` を指定すると、その範囲のフレームのみが横軸に描画される（範囲外のフレームは集計・描画ともに対象外）
  - AC-007-4: 出力 PNG が指定パスに作成される（サイズ > 0 バイト）

## 4. 非機能要求

### NFR-001: パフォーマンス

- camSony1_L（約 321K フレーム）を入力としたとき、処理時間が **120 秒以内** に完了する見込み
  - 根拠: feat-037 の `plot_pink_track_timeline.py`（同等の処理 + 5 パネル）が同等規模で実用時間内に動作している実績
- メモリ使用量: 全フレームの BB 情報をリストに保持しても、camSony1_L の最大想定（数百万 BB）でも数 GB 以下

### NFR-002: 対応環境

- Python 3.10.16、uv 環境、CPU 実行
- matplotlib（既存依存）、標準ライブラリのみ
- GPU 不要

### NFR-003: 出力品質

- PNG dpi=150、図サイズ `(16, 12)` インチ
- 全パネルが横軸（フレーム番号）を共有し `sharex=True`
- 各パネルは凡例 / 縦軸ラベル / 単位明記

## 5. 制約条件

### 5.1 使用必須のライブラリ

- matplotlib（描画）
- 標準ライブラリ: `argparse`, `json`, `os`, `re`, `sys`, `pathlib`, `dataclasses`

### 5.2 使用禁止のライブラリ

- pandas、seaborn 等の追加ライブラリは導入しない（既存依存のみで完結させる）
- 動画読み込み用 OpenCV は使わない（pink_ratio は JSON に保存済み、再計算しない）

### 5.3 定数の参照方法

- `MIN_PINK_RATIO` は `from postprocess_pink_id import MIN_PINK_RATIO` で import する。値のハードコード重複を避ける
  - 前例: `visualize_patient_video.py` が `from merge_halpe26 import HALPE26_SKELETON` で同様に import 済み
- `IOU_CONT_WEIGHT` の値（0.05）は際どい差分閾値の根拠としてコメントで記述するが、変数として import はしない（描画閾値はあくまで本スクリプトの判断値であり、実装上の連動はしない）

## 6. 優先順位

| ID | 機能 | 優先度 |
|----|------|--------|
| FR-001 | タイムラインデータ収集 | Must |
| FR-002 | Panel 1（散布図） | Must |
| FR-003 | Panel 2（pink_id=1 タイムライン） | Must |
| FR-004 | Panel 3（BB 数） | Must |
| FR-005 | Panel 4（差分） | Must |
| FR-006 | 次点 BB 決定ロジック | Must |
| FR-007 | CLI（必須引数 `--json-dir` / `--out-path`） | Must |
| FR-007 任意引数 `--frame-start` / `--frame-end` | フレーム範囲指定 | Should |

MVP = FR-001〜007 の Must 範囲。`--frame-start` / `--frame-end` は Should（あると誤検出ピンポイント解析時に有用、無くても全体描画で代替可能）。
