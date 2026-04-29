# feat-041 要求仕様書: postprocess_pink_id.py に選択スコア診断フィールド追加

## 1. プロジェクト概要

### 1.1 何を作るのか

`scripts/postprocess_pink_id.py` の出力 JSON の各 `people[i]` に、`pink_id` 選択スコアの内訳を診断するための 3 フィールド `iou_with_prev`、`selection_score`、`bb_index` を追加する改修。

### 1.2 なぜ作るのか

現行の `pink_id` 選択ロジックは `score = pink_ratio + IOU_CONT_WEIGHT × IoU(prev_selected_bbox, current_bbox)` で BB を選ぶが、計算過程の中間値（IoU・最終スコア）が JSON に残らない。そのため:

- 「ピンク患者の前を別人が通り過ぎてからずっと別人に `pink_id=1` が付き続ける」現象が、IoU 連続性ボーナスによる逆転かどうかを後追いで判別できない
- 連続性ボーナスがロックインを起こすフレーム区間を定量的に特定できない
- 同一フレームに複数 BB がある場合、JSON 上の人物エントリと動画上の BB を一意に対応付ける手段がない（`bb_index` の不在）

本案件で内訳を保存することで、ポストプロセス再実行なしで誤選択の原因解析と BB 同定が可能になる。

### 1.3 誰が使うのか

本プロジェクトの開発者（`pink_id` の誤選択区間を解析する者、可視化動画と JSON を突合する者）。

### 1.4 どこで使うのか

既存 `scripts/postprocess_pink_id.py` と同一の実行環境（uv 環境、CPU + OpenCV）。実行 CLI・引数・入出力ディレクトリ規約は変更しない。

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| 前フレーム選択 BB | `postprocess_pink_id.py` が前フレームで `pink_id=1` と判定した BB の座標タプル `(x1, y1, x2, y2)`。**`clip_bbox` 適用後の整数座標タプル**（既存実装で `prev_selected_bbox` に格納される値はこの形式）。コード上の変数名は `prev_selected_bbox` |
| 連続性切れ | `prev_selected_bbox = None` の状態。1 フレーム目、前フレームで候補 0 個だった次のフレーム、JSON 欠損フレームの次のフレームで発生 |
| iou_with_prev | 当該 BB と前フレーム選択 BB との IoU。値域 [0.0, 1.0]。連続性切れフレームでは null |
| selection_score | 当該 BB の選択スコア = `pink_ratio + IOU_CONT_WEIGHT × iou_with_prev`。`iou_with_prev` が null のときは null |
| bb_index | 同フレームの `people` リスト内の 0 始まりの連番。整数 |
| IOU_CONT_WEIGHT | 既存定数。値は 0.05。`postprocess_pink_id.py` の選択ロジックで連続性ボーナスの重みとして使われる |
| 生 dict 保持設計 | feat-033 / 035 / 036 / 039 共通の設計方針。入力 JSON の既存フィールドを変更せず、新規フィールドのみ追加して書き出す |

注記: 本案件では JSON 拡張のみ行い、可視化動画への描画は対象外（feat-042 で扱う）。

## 3. 機能要求一覧

### FR-001: bb_index フィールドの付与

- **概要**: 各 `people[i]` に、同フレームの `people` リスト内の 0 始まり連番を `bb_index: int` として保存する
- **入力**: 既存の入力（動画ファイル、HALPE 26 JSON ディレクトリ、出力ディレクトリ）に変更なし
- **出力**: 出力 JSON の各 `people[i]` に `bb_index` キーが存在する
- **処理内容**:
  1. 既存の pink_id 付与ループ内で、`enumerate(people)` の `i` をそのまま `person["bb_index"] = i` として保存
  2. `bb_index` の値は同フレーム内で重複せず、0 から `len(people) − 1` まで連続する
- **受け入れ基準**:
  - AC-001-1: 全フレームの全 `people[i]` に `bb_index` キーが存在する
  - AC-001-2: 同一フレーム内で `bb_index` の値は重複せず、0 始まりで連続する
  - AC-001-3: `bbox` 欠損 person（既存実装で WARNING ログを出すケース）にも `bb_index` が付与される

### FR-002: iou_with_prev フィールドの付与

- **概要**: 各 `people[i]` の `bbox` と前フレーム選択 BB との IoU を計算し、`iou_with_prev: float | null` として保存する
- **入力**: 既存と同じ。前フレーム選択 BB は `select_pink_bbox` 呼び出し時点の `prev_selected_bbox` を流用
- **出力**: 出力 JSON の各 `people[i]` に `iou_with_prev` キーが存在する
- **処理内容**:
  1. 当該フレームの選択判定に使った `prev_selected_bbox` 値を退避
  2. `prev_selected_bbox` が `None`（連続性切れ）の場合、全 `people[i]` の `iou_with_prev = null`
  3. `prev_selected_bbox` が値ありの場合、各 `people[i]` の clipped bbox と前フレーム選択 BB との `compute_iou` を計算した結果を保存
  4. `bbox` 欠損 person の `iou_with_prev = null`（IoU 計算不能）
- **受け入れ基準**:
  - AC-002-1: 連続性切れフレームでは全 `people[i]` の `iou_with_prev` が JSON 上で `null` になる
  - AC-002-2: 連続性切れでないフレームでは、`bbox` 有効な全 `people[i]` の `iou_with_prev` が `[0.0, 1.0]` の float
  - AC-002-3: `bbox` 欠損 person の `iou_with_prev` は `null`
  - AC-002-4: 前フレーム選択 BB と同一座標の BB（理論上ありえないが境界値として）は `iou_with_prev = 1.0`

### FR-003: selection_score フィールドの付与

- **概要**: 各 `people[i]` の選択スコアを `selection_score: float | null` として保存する
- **入力**: 既存と同じ。`pink_ratio` と `iou_with_prev` を流用
- **出力**: 出力 JSON の各 `people[i]` に `selection_score` キーが存在する
- **処理内容**:
  1. `iou_with_prev` が `null`（連続性切れ・bbox 欠損）の場合、`selection_score = null`
  2. それ以外の場合、`selection_score = pink_ratio + IOU_CONT_WEIGHT × iou_with_prev`（IOU_CONT_WEIGHT = 0.05）
- **受け入れ基準**:
  - AC-003-1: 連続性切れフレームでは全 `people[i]` の `selection_score` が JSON 上で `null`
  - AC-003-2: `bbox` 欠損 person の `selection_score` は `null`
  - AC-003-3: それ以外では `selection_score == pink_ratio + 0.05 × iou_with_prev` の等式が成立（浮動小数点誤差を除く）
  - AC-003-4: `pink_id == 1` の人物の `selection_score` は同フレームの全 BB の中で最大値である（既存選択ロジックとの整合確認）

### FR-004: 既存フィールド・ロジックの非変更

- **概要**: `pink_id` 選択ロジック、CLI 引数、入出力ディレクトリ規約、サマリ出力、既存フィールド (`pink_id` / `pink_ratio` / `bbox` / `pose_keypoints_2d` 等) を変更しない
- **入力**: 既存と同じ
- **出力**: 既存フィールドの値・順序は変更されない
- **受け入れ基準**:
  - AC-004-1: `pink_id == 1` になる BB の集合は改修前と完全一致する（同一入力・同一乱数条件）
  - AC-004-2: `pink_ratio` の値は改修前と完全一致する
  - AC-004-3: CLI 引数 `--video` / `--json-dir` / `--out-dir` は変更されない
  - AC-004-4: サマリ出力の項目名・出力順は改修前と完全一致する（feat-039 の AC-003-3 で列挙した 7 項目）

## 4. 非機能要求

### NFR-001: パフォーマンス

- 既存実装に対し、同一入力（camSony1_L.mp4、約 321K フレーム）で処理時間の増加が **20% 以内** に収まる
  - 根拠: BB ごとに `compute_iou` を 1 回追加で呼ぶのみ（既存の `select_pink_bbox` 内 IoU 計算と数式は同一）。Python の dict 代入 3 件追加。BGR→HSV 変換等の重処理は増えない

### NFR-002: 下流互換性

- 以下の下流スクリプトが改修後の JSON を既存と同じ挙動で処理できる:
  - feat-035 `postprocess_track.py`
  - feat-036 `postprocess_patient_id.py`
  - feat-037 `plot_pink_track_timeline.py`
  - feat-038 `visualize_patient_video.py`
  - feat-040 `plot_pink_ratio_timeline.py`
- 根拠: いずれも生 dict 保持設計で未知フィールドを無視する

### NFR-003: 対応環境

- 既存 `postprocess_pink_id.py` と同一（Python 3.10.16、uv 環境、CPU 実行、OpenCV + numpy）

## 5. 制約条件

### 5.1 使用必須のライブラリ

- 既存依存のみ（OpenCV、numpy、json 標準ライブラリ）。追加ライブラリの導入は行わない

### 5.2 追加禁止

- 閾値 `MIN_PINK_RATIO` / `IOU_CONT_WEIGHT` / `FIXED_HSV_RANGES` の変更は本案件のスコープ外
- `select_pink_bbox` 関数の選択ロジック自体の変更は本案件のスコープ外
- CLI 引数の追加（例: `--write-debug-fields` のような ON/OFF フラグ）は行わない。デバッグ目的ではあるが、計算コストは小さく常時書き込みとする
- `bb_index` の上流付与（`run_halpe26_pipeline_yolo11.py` での付与）は行わない。本案件では `postprocess_pink_id.py` で付与する

### 5.3 値規約（連続性切れ時）

採用案: **案 B（null で事実保存）**

- `iou_with_prev = null`、`selection_score = null` で「連続性切れ」を JSON 上で明示する
- 案 A（`iou_with_prev = 0.0`、`selection_score = pink_ratio` で代用）は採用しない。理由: 「前 BB あり & IoU=0」と「前 BB なし」が JSON 上で区別不能になるため、後段の解析（誤選択区間の連続性切れ起因か否かの判別）が不可能になる

### 5.4 フィールド名

- 新規フィールド名は `iou_with_prev`、`selection_score`、`bb_index` に固定する。他候補（`prev_iou`、`score`、`bb_id` 等）は採用しない

## 6. 優先順位

| ID | 機能 | 優先度 |
|----|------|--------|
| FR-001 | bb_index フィールドの付与 | Must |
| FR-002 | iou_with_prev フィールドの付与 | Must |
| FR-003 | selection_score フィールドの付与 | Must |
| FR-004 | 既存フィールド・ロジックの非変更 | Must |

MVP = FR-001 + FR-002 + FR-003 + FR-004。本案件はすべて Must であり、Should / Could / Won't はなし。
