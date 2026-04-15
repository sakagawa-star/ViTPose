# feat-033: 服装の色による患者同定（ポストプロセス） — 要求仕様書

## 1. プロジェクト概要

### 1.1 何を作るのか

`scripts/postprocess_pink_id.py`（新規）を作成する。本スクリプトは、`run_halpe26_pipeline_yolo11.py` が出力したHALPE 26 OpenPose JSON ディレクトリと元動画を入力とし、各フレームの各人物BBのHSVピンクマスク比率を計算し、閾値超の候補の中から「比率 + 前フレームで選択したBBとのIoU連続性ボーナス」が最大のBBを「ピンク服の患者」として選択する。選択されたBBを持つ人物エントリに `pink_id=1`、それ以外に `pink_id=-1` を付与した新しいJSONディレクトリを出力する。

### 1.2 なぜ作るのか

feat-032（ポーズ誘導外観特徴量の独立検証）の前段として、より単純な外観特徴量（衣服色）に基づく患者同定方式がどの程度機能するかを定量的に確認する。参考とする `pink_tracker_jhub.py` はHSVレンジ・閾値を固定化している（「色の情報を固定化している」）が、本案件では初回検証として同じ固定値戦略を採用する。色ベース方式の結果を feat-028 の `stable_id` と並べて観察することで、feat-032 のポーズ誘導外観特徴量が解決すべき課題（色情報だけでは不十分となる場面）を具体化する。

### 1.3 誰が使うのか

本プロジェクトの開発者。生成された `pink_id` 付与JSONと `stable_id` を照合し、色ベース方式と既存Re-ID方式の差分を目視・定量評価して feat-032 の方針決定に用いる。

### 1.4 どこで使うのか

Linux 開発マシン（本プロジェクトの既存 ViTPose uv 環境）。コマンドラインから実行する。ViTPose 推論・トラッカー呼び出しは不要で、既存動画と既存JSONがあれば動作する。

## 2. 用語定義

本ドキュメント、機能設計書、実装コード内で同じ用語を用いる。

| 用語 | 定義 |
|------|------|
| HSVピンクマスク | BB内画素を BGR → HSV 変換した後、定義された3つのHSVレンジ（後述の FIXED_HSV_RANGES）のいずれかに属する画素を 1、それ以外を 0 とする二値マスク |
| ピンク比率 | BB内画素総数に対する HSV ピンクマスクで 1 となった画素数の比。値域 [0.0, 1.0] |
| 選択BB | あるフレームで「ピンク服の患者」として選択された BB。1フレームあたり 0 個または 1 個 |
| 連続性ボーナス | 前フレームの選択BBと今フレームの候補BBの IoU に固定重みを掛けた値。スコアに加算される |
| スコア | `pink_ratio + IOU_CONT_WEIGHT * iou(prev_selected_bbox, current_bbox)` |
| pink_id | 各人物エントリに付与する整数フィールド。選択BBなら 1、それ以外なら -1 |
| stable_id | feat-028 でJSONに記録済みの安定識別子。本案件では参照のみで変更しない（入力JSONに存在する場合のみ） |
| 連続性切れ | 前フレームまで選択BBがあったが今フレームでは候補がゼロとなり、前フレーム BB バッファをリセットする状態遷移 |
| FIXED_HSV_RANGES | `pink_tracker_jhub.py` から流用する3帯HSVレンジ定数。後述 5.3 に記載 |
| MIN_PINK_RATIO | ピンク比率の候補判定閾値。定数 0.03 |
| IOU_CONT_WEIGHT | 連続性ボーナスの重み係数。定数 0.05 |

## 3. 機能要求一覧

### FR-001: HSVピンクマスク / ピンク比率計算

- **概要**: BGR画像ROI（BB内の部分画像）を入力として、FIXED_HSV_RANGES に従ったHSVピンクマスクを生成し、ピンク比率を返す純関数を実装する
- **入力**:
  - `roi_bgr`: numpy.ndarray、shape = (h, w, 3)、dtype = uint8、BGR色空間
- **出力**:
  - `pink_ratio`: float、値域 [0.0, 1.0]
- **処理内容**:
  1. ROIサイズが 0（幅 0 または高さ 0）の場合は 0.0 を返す
  2. BGR → HSV 変換（OpenCV `cv2.cvtColor`）
  3. FIXED_HSV_RANGES の各 (lower, upper) ペアについて `cv2.inRange` でマスク生成
  4. 全マスクをビット OR で統合
  5. ピンク画素数 / ROI総画素数 を返す
- **受け入れ基準**:
  - AC-001-1: ROIが空（サイズ 0）のとき 0.0 を返す
  - AC-001-2: ROIがピンク成分を全く含まない単色画像（例: 全面 BGR=(0,0,0)）のとき 0.0 を返す
  - AC-001-3: ROIが FIXED_HSV_RANGES のいずれかに完全に含まれる単色画像（例: 全面 BGR=(180,105,255) = 鮮やかなピンク）のとき 1.0 を返す
  - AC-001-4: 戻り値は常に [0.0, 1.0] の範囲に収まる

### FR-002: 選択BBロジック

- **概要**: 1フレーム分のBBリストと前フレーム選択BBを入力として、「ピンク服の患者」に該当するBBのインデックスを返す純関数を実装する
- **入力**:
  - `bboxes`: list[tuple[int, int, int, int]]、各要素は `(x1, y1, x2, y2)` のピクセル整数座標
  - `ratios`: list[float]、各BBのピンク比率、`len(ratios) == len(bboxes)`
  - `prev_selected_bbox`: tuple[int, int, int, int] または None、前フレームで選択されたBB（連続性切れ後は None）
- **出力**:
  - `selected_idx`: int または None、選択されたBBのインデックス（該当なしなら None）
- **処理内容**:
  1. `ratios[i] >= MIN_PINK_RATIO` を満たすインデックス集合 `candidates` を作る
  2. `candidates` が空なら None を返す
  3. `prev_selected_bbox` が None のときは `candidates` の中で `ratios[i]` が最大のインデックスを返す（同値の場合はインデックス最小）
  4. `prev_selected_bbox` が None でないときは `candidates` の中で `ratios[i] + IOU_CONT_WEIGHT * iou(prev_selected_bbox, bboxes[i])` が最大のインデックスを返す（同値の場合はインデックス最小）
- **受け入れ基準**:
  - AC-002-1: `bboxes` が空リストのとき None を返す
  - AC-002-2: 全BBのピンク比率が `MIN_PINK_RATIO` 未満のとき None を返す
  - AC-002-3: `prev_selected_bbox = None` かつ候補BBが1個のとき、そのインデックスを返す
  - AC-002-4: `prev_selected_bbox = None` かつ候補BBが複数のとき、ピンク比率最大のインデックスを返す
  - AC-002-5: `prev_selected_bbox != None` かつ候補が複数あるとき、以下の具体例で B が選択される: BB_A の `(ratio, IoU(prev, A))` = (0.10, 0.0)、BB_B の `(ratio, IoU(prev, B))` = (0.08, 1.0) のとき、score_A = 0.10、score_B = 0.08 + 0.05 × 1.0 = 0.13 となり B（インデックス大小に関わらず）が選ばれる
  - AC-002-6: 2 つの候補のスコアが完全に同値の場合、インデックスの小さい方を返す（例: 候補 [2, 5] で両者のスコアが 0.12 なら 2 を返す）

### FR-003: ポストプロセス本体

- **概要**: 入力JSONディレクトリの全フレームを昇順に走査し、動画から各フレーム画像を取得して FR-001 / FR-002 を適用し、pink_id を付与した新JSONを出力する
- **入力**:
  - 入力動画ファイル（MP4）
  - 入力JSONディレクトリ（`{video_stem}_{frame_idx:06d}.json` 形式のファイル群）
- **処理内容**:
  1. JSONディレクトリから全JSONファイルを `load_data()` と同等の形式で読み込む（既存 `scripts/postprocess_reid.py` の `load_data` を参考）
  2. 動画を `cv2.VideoCapture` で開く
  3. `prev_selected_bbox = None` で初期化
  4. フレームを 0 から昇順に読み、各フレームで以下を実行:
     - JSONに対応フレームがなければ空の people リストとして扱い、`prev_selected_bbox = None` にリセットする
     - 各人物BBについて FR-001 でピンク比率を計算
     - FR-002 で選択インデックスを求める
     - 選択された人物の `pink_id = 1`、それ以外の `pink_id = -1` とする
     - 選択がある場合は `prev_selected_bbox` を選択BBで更新、ない場合は `None` にリセット
  5. 各フレームのJSONを出力ディレクトリに書き出す（命名は入力と同じ）
- **受け入れ基準**:
  - AC-003-1: 指定した動画と入力JSONディレクトリに対してエラーなく処理完了する
  - AC-003-2: 出力ディレクトリに生成されるJSONファイル数は、次式で定まる: `出力JSON数 = (動画フレーム数と対応する入力JSONフレーム数の積集合) の要素数`。具体的には「動画のフレーム `i` について、入力JSONディレクトリに `{video_stem}_{i:06d}.json` が存在するフレーム」の総数と一致する。動画フレームに対応JSONがないフレーム（`json_missing`）は出力されない。入力JSONに対応する動画フレームが存在しないJSONは無視される（動画終了でループ終了するため出力されない）
  - AC-003-3: 入力JSONの既存フィールド（`version`、`people[*].pose_keypoints_2d`、`bbox`、`bbox_score`、`stable_id` 等）は変更されない
  - AC-003-4: 出力JSONの各 `people` エントリに `pink_id` フィールドが追加されている
  - AC-003-5: 1フレーム内で `pink_id = 1` となる人物は最大 1 人
  - AC-003-6: 候補がゼロのフレームでは全人物の `pink_id = -1` となる
  - AC-003-7: 以下のいずれかが発生したフレームは「連続性切れ」として扱い、`prev_selected_bbox` を `None` にリセットする。次フレームでは「`prev_selected_bbox = None`」ルートで再選択される:
    1. 対応する入力JSONファイルが存在しない
    2. 入力JSONの `people` 配列が空
    3. 全人物の `bbox` フィールドが欠損または形式不正で有効なBBが 0 個
    4. 有効なBBが存在するが、全員のピンク比率が `MIN_PINK_RATIO` 未満（候補ゼロ）
  - AC-003-8: 入力JSONが `people` を持たない（または空配列）フレームでは、空の `people` がそのまま出力される

### FR-004: CLI インタフェース

- **概要**: FR-003 を実行するコマンドラインインタフェースを提供する
- **コマンド**: `uv run python scripts/postprocess_pink_id.py [引数]`
- **引数**:

  | 引数 | 必須 | 型 | デフォルト | 意味 |
  |------|------|----|-----------|------|
  | `--video` | 必須 | パス | - | 入力動画ファイル |
  | `--json-dir` | 必須 | パス | - | 入力 HALPE 26 JSON ディレクトリ |
  | `--out-dir` | 必須 | パス | - | 出力JSONディレクトリ（入力と同一パス禁止） |

- **受け入れ基準**:
  - AC-004-1: 必須引数が未指定の場合、argparse のエラーメッセージを表示して終了コード 2 で終了する
  - AC-004-2: `--out-dir` が `--json-dir` と同じパス（realpath 比較）の場合、ERROR ログを出力して終了コード 1 で終了する
  - AC-004-3: 出力ディレクトリが存在しない場合、自動作成する
  - AC-004-4: 入力動画が開けない場合、ERROR ログを出力して終了コード 1 で終了する
  - AC-004-5: 入力JSONディレクトリにJSONファイルが1つもない場合、ERROR ログを出力して終了コード 1 で終了する

### FR-005: サマリ出力

- **概要**: 処理完了時に、フレーム総数・選択成功フレーム数・連続性切れ対象フレーム数の内訳・連続性切れ回数・処理時間を標準出力に表示する
- **入力**: FR-003 の処理結果
- **出力**: 標準出力（行区切りテキスト）。以下を含む:
  - `Total frames: <int>`
  - `Frames with pink_id=1: <int>`
  - `Frames without candidate (no valid bbox candidate above threshold): <int>`
  - `Frames without json: <int>`
  - `Continuity breaks: <int>`
  - `Processing time: <float> sec (<float> fps)`
  - `Output directory: <str>`
- **受け入れ基準**:
  - AC-005-1: 上記7項目がすべて出力される
  - AC-005-2: 以下の等式が常に成り立つ:
    `selected + no_candidate + json_missing == total`
    ここで selected = `Frames with pink_id=1`、no_candidate = `Frames without candidate`、json_missing = `Frames without json`、total = `Total frames`
  - AC-005-3: `Continuity breaks` は「前フレームで `prev_selected_bbox != None` の状態から今フレームで `None` にリセットされた」遷移の回数。起因事象（JSONなし / people 空 / 候補ゼロ）は問わない

## 4. 非機能要求

### NFR-001: パフォーマンス

- GPUは使用しない（OpenCV の HSV 変換・マスク計算のみ）
- フェーズ1対象の `camSony1_S.mp4`（445フレーム、960×540）を 60 秒以内に処理完了する
- フェーズ2対象の `camSony1_L.mp4`（約321Kフレーム）は数時間以内に処理完了する見込みであれば可（目標値は設けない）

### NFR-002: 対応環境

- OS: Linux（本プロジェクトの開発環境）
- Python: 3.10.16
- パッケージ管理: uv（`uv run python` 経由で実行）
- GPU: 不要

### NFR-003: 信頼性

- 検証用スクリプトのため、ロバスト性より観測可能性を優先する
- JSON読み込みに失敗したフレームは WARNING ログを出力してスキップし、`prev_selected_bbox` をリセットする
- 動画フレーム読み込みに失敗した時点で処理を終了する（途中終了でも出力済みJSONは保持する）

## 5. 制約条件

### 5.1 使用必須のライブラリ

- OpenCV（動画読み込み、HSV 変換、マスク計算）
- numpy（配列演算）

### 5.2 追加禁止

- 色パラメータ可変化のための設定ファイル（TOML/YAML/JSON）
- `pandas`、`matplotlib` 等の追加ライブラリ

### 5.3 固定値定数

以下は `pink_tracker_jhub.py` の値を変更せず流用し、スクリプト内の定数として定義する。

```python
FIXED_HSV_RANGES = [
    ((  0,  60,  80), ( 10, 255, 255)),  # 赤系ピンク
    ((140,  60,  80), (159, 255, 255)),  # マゼンタ
    ((160,  60,  80), (179, 255, 255)),  # ピンク赤尾部
]
MIN_PINK_RATIO = 0.03
IOU_CONT_WEIGHT = 0.05
```

### 5.4 変更禁止

- `scripts/run_halpe26_pipeline_yolo11.py`
- `scripts/postprocess_reid.py`
- `scripts/custom_reid.py`
- `scripts/visualize_tracking.py`（本案件では `pink_id` 対応を行わない）
- 既存 JSON 出力フォーマット（`pink_id` フィールドを追加するのみ）

### 5.5 データ制約

- 入力JSONフォーマットは既存 `scripts/run_halpe26_pipeline_yolo11.py` / `scripts/postprocess_reid.py` の出力形式に準拠する
- 各人物は `bbox = [x1, y1, x2, y2]`（ピクセル、xyxy）を持つ
- 入力JSONに `stable_id` が含まれる場合はそのまま保持する（参照・変更なし）

## 6. 優先順位

### 6.1 MoSCoW

| ID | 機能 | 優先度 |
|----|------|--------|
| FR-001 | HSVピンクマスク / ピンク比率計算 | Must |
| FR-002 | 選択BBロジック | Must |
| FR-003 | ポストプロセス本体 | Must |
| FR-004 | CLI インタフェース | Must |
| FR-005 | サマリ出力 | Should |

Won't（本案件のスコープ外）:

- 色パラメータの可変化（設定ファイルまたはCLI引数）
- 可視化スクリプトの作成・修正
- L版（`camSony1_L.mp4`）での実行（本案件内での実施はしない）
- feat-028 の再実行や `stable_id` の上書き

### 6.2 MVP

- FR-001 + FR-002 + FR-003 + FR-004 が動作し、フェーズ1対象（camSony1_S）に対して `pink_id` 付与JSONが生成できる状態を最小実行可能プロダクトとする
- FR-005（サマリ出力）は Should。実装コストが低く、手動テスト時の確認を容易にするため本案件内で一括実装する
