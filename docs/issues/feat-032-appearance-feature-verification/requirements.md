# feat-032: ポーズ誘導外観特徴量の独立検証 — 要求仕様書

## 1. プロジェクト概要

### 1.1 何を作るのか
`scripts/custom_reid.py` 内に埋め込まれているポーズ誘導外観特徴量（キーポイントで頭部・胴体ROIを切り出し HSV 色ヒストグラムを計算する処理）を独立モジュール `scripts/appearance_feature.py` として切り出す。その上で、既存動画と既存トラッキング結果 JSON を入力とし、各 track_id のポーズ誘導外観特徴量を時系列で計算・記録・可視化する独立検証スクリプト `scripts/verify_appearance_feature.py` を作成する。

### 1.2 なぜ作るのか
feat-026「見切れ再同定の検証」で、Deep OC-SORT の ID スイッチ発生時（camSony1_L の frame 6377 付近）にポーズ誘導外観特徴量の EMA 更新が無条件で実行され、別人の外見で EMA が汚染されて stable_id=1 の追跡が 42 分間途切れる問題が判明した。Re-ID 修正方針（EMA 更新スキップの判定基準）を詰めるには、汚染が実データで何フレームかけてどう進行するかを観測する必要がある。Re-ID・Deep OC-SORT・特徴量計算が `custom_reid.py` 内で密結合しているため、特徴量計算ロジックのみを切り出して独立観測できる環境を作る。

### 1.3 誰が使うのか
本プロジェクトの開発者。生成された CSV と時系列グラフを分析し、Re-ID 修正方針の判断根拠とする。

### 1.4 どこで使うのか
Linux 開発マシン（本プロジェクトの既存 ViTPose uv 環境）。コマンドラインから実行する。ViTPose 推論は不要で、既存動画と既存 JSON があれば動作する。

## 2. 用語定義

本ドキュメント、機能設計書、実装コード内で同じ用語を用いる。

| 用語 | 定義 |
|------|------|
| ポーズ誘導外観特徴量 | HALPE 26 キーポイントから頭部・胴体の ROI を局所化し、各領域の HSV 色ヒストグラム（H 36bin + S 32bin = 68 次元）を結合した値。`PersonFeature` データクラスで表現される |
| 頭部 ROI | HALPE 26 の Nose / LEye / REye / LEar / REar / Head / Neck（index `[0, 1, 2, 3, 4, 17, 18]`）のうち、confidence > 0.3 の点の外接矩形を 20px 拡張した領域 |
| 胴体 ROI | HALPE 26 の LShoulder / RShoulder / LHip / RHip（index `[5, 6, 11, 12]`）のうち、confidence > 0.3 の点の外接矩形 |
| HSV ヒストグラム | OpenCV の `cv2.calcHist` で計算される H チャンネル 36bin と S チャンネル 32bin を結合して正規化した 68 次元のベクトル |
| EMA | 指数移動平均（Exponential Moving Average）。`ema_new = α * new + (1 - α) * ema_prev`、α = 0.1 |
| 生特徴量 | 今フレームの観測から直接計算した `PersonFeature`（EMA を通していない値） |
| 時間連続類似度 | 前フレームの生特徴量と今フレームの生特徴量のヒストグラム交差類似度 |
| EMA 類似度 | 前フレームの EMA 特徴量と今フレームの生特徴量のヒストグラム交差類似度 |
| ヒストグラム交差類似度 | `sim(a, b) = Σ min(a_i, b_i)`。正規化済みヒストグラム同士なら値域は [0, 1] |
| track_id | Deep OC-SORT が付与する人物識別子。ID スイッチで乗っ取られうる |
| stable_id | カスタム Re-ID が track_id に割り当てる安定識別子（本案件では参照のみで変更しない） |

## 3. 機能要求一覧

### FR-001: ポーズ誘導外観特徴量モジュールの切り出し

- **概要**: `scripts/custom_reid.py` に埋め込まれているポーズ誘導外観特徴量の計算ロジックを、純粋な関数・データクラスとして `scripts/appearance_feature.py`（新規）に切り出す。`custom_reid.py` は切り出し先からの import に置き換える
- **切り出し対象**:
  - データクラス: `PersonFeature`
  - 定数: `HEAD_INDICES = [0, 1, 2, 3, 4, 17, 18]`、`TORSO_INDICES = [5, 6, 11, 12]`
  - 関数: `extract_head_region`、`extract_torso_region`、`compute_hsv_histogram`、`build_feature`、`ema_update_feature`、`ema_update_histogram`、`compute_similarity`
  - デフォルト値: `alpha = 0.1`、`kpt_conf_thr = 0.3`、`head_expand_px = 20`
- **入力**: 既存 `scripts/custom_reid.py` の該当ロジック
- **出力**:
  - `scripts/appearance_feature.py`（新規作成）
  - `scripts/custom_reid.py`（切り出し対象を削除し、`appearance_feature` から import する形に変更）
- **受け入れ基準**:
  - AC-001-1: `scripts/appearance_feature.py` が作成され、上記の関数・データクラス・定数が定義されている
  - AC-001-2: `scripts/custom_reid.py` から切り出し対象の実装が削除され、`from appearance_feature import ...` の形に置き換わっている
  - AC-001-3: `custom_reid.py` の公開 API（`CustomReID` クラスのメソッドシグネチャと戻り値）は切り出し前後で変化しない
  - AC-001-4: 既存の `scripts/run_halpe26_pipeline_yolo11.py` を `testdata/camSony1.mp4` に対して実行したとき、切り出し前後で出力 JSON（stable_id 列、bbox 座標、keypoints）が完全一致する

### FR-002: 独立検証スクリプトの実装（処理本体）

- **概要**: `scripts/verify_appearance_feature.py`（新規）を作成する。既存動画と既存トラッキング結果 JSON を入力として、各 track_id のポーズ誘導外観特徴量を時系列で計算し、時間連続類似度と EMA 類似度を観測する
- **入力**:
  - 動画ファイル（MP4）
  - 既存トラッキング結果 JSON のディレクトリ（`experiments/results/camSony1_L_reid_json/` 形式。フレームごとに bbox、keypoints、track_id、stable_id を含む）
  - フレーム範囲（任意）
- **処理内容**:
  1. JSON ディレクトリから全フレームのデータを昇順で読み込む
  2. 動画から各フレーム画像を順次取得する
  3. 各フレームで、動画に存在する全 track_id について `build_feature()` で生 `PersonFeature` を計算する
  4. 各 track_id について、前フレームの生特徴量と前フレームの EMA 特徴量を内部バッファに保持する
  5. 各 track_id について、以下 2 種類の類似度を計算する:
     - 時間連続類似度: `compute_similarity(prev_raw_feature, current_raw_feature)`
     - EMA 類似度: `compute_similarity(prev_ema_feature, current_raw_feature)`
  6. EMA 特徴量を `ema_update_feature()` で更新する（無条件更新、現 `custom_reid.py` の挙動と同一）
  7. 前フレーム生特徴量・前フレーム EMA 特徴量バッファを更新する
- **出力**: 本 FR の処理結果は FR-003 / FR-004 の出力生成に用いられる
- **受け入れ基準**:
  - AC-002-1: 指定した動画と JSON ディレクトリに対してエラーなく処理を完了する
  - AC-002-2: 動画全体または指定フレーム範囲の全フレームが処理される
  - AC-002-3: 新規 track_id の初回出現フレームでは、前フレームバッファが存在しないため、時間連続類似度と EMA 類似度は NaN として扱われる
  - AC-002-4: 消失した track_id の内部バッファは破棄され、同じ track_id が再出現した場合は新規扱いとなる

### FR-003: CSV ローデータ出力

- **概要**: FR-002 で計算した特徴量メタ情報と類似度を CSV 形式で出力する
- **入力**: FR-002 の処理結果
- **出力**: CSV ファイル `{out-dir}/appearance_features.csv`
- **カラム定義**:

  | カラム名 | 型 | 意味 |
  |---------|-----|------|
  | `frame_idx` | int | フレーム番号（JSON ファイル名から抽出、0 始まり） |
  | `track_id` | int | Deep OC-SORT のトラック ID |
  | `stable_id` | int | JSON に記録された stable_id（参照のみ） |
  | `bbox_x1`, `bbox_y1`, `bbox_x2`, `bbox_y2` | float | JSON に記録された BB 座標 |
  | `head_hist_valid` | bool | 頭部 HSV ヒストグラムが有効か（None でないか） |
  | `torso_hist_valid` | bool | 胴体 HSV ヒストグラムが有効か |
  | `sim_raw_prev` | float または NaN | 時間連続類似度 |
  | `sim_ema_prev` | float または NaN | EMA 類似度 |

- **受け入れ基準**:
  - AC-003-1: CSV ファイルが `{out-dir}/appearance_features.csv` に生成される
  - AC-003-2: 処理対象フレームに存在する全 track_id の全行が記録される
  - AC-003-3: `sim_raw_prev` と `sim_ema_prev` は track_id 初回出現フレームで NaN となる
  - AC-003-4: 類似度カラムは小数点 4 桁で記録される

### FR-004: 時系列グラフ出力

- **概要**: FR-002 の処理結果を track_id 別の時系列グラフとして PNG 画像に出力する
- **入力**: FR-002 の処理結果
- **出力**: PNG ファイル群 `{out-dir}/similarity_timeseries_tid_{XXXX}.png`（track_id ごとに 1 枚、ゼロ埋め 4 桁）
- **グラフ仕様**:
  - X 軸: `frame_idx`
  - Y 軸: 類似度（0.0 〜 1.0 で固定）
  - 2 本のライン:
    - 時間連続類似度（青、ラベル `sim(raw_prev, raw)`）
    - EMA 類似度（橙、ラベル `sim(ema_prev, raw)`）
  - タイトル: `track_id = {XXXX}`
  - グリッド表示あり
  - 凡例表示あり
- **受け入れ基準**:
  - AC-004-1: 対象フレーム範囲で出現する全 track_id に対し、それぞれ 1 枚の PNG ファイルが生成される
  - AC-004-2: NaN 区間（初回出現フレーム、一時消失後の再出現時）はプロットされない
  - AC-004-3: Y 軸範囲は常に [0.0, 1.0] 固定で、track_id 間で比較可能

### FR-005: CLI インタフェース

- **概要**: FR-002 〜 FR-004 を実行するコマンドラインインタフェースを提供する
- **コマンド**: `uv run python scripts/verify_appearance_feature.py [引数]`
- **引数**:

  | 引数 | 必須 | 型 | デフォルト | 意味 |
  |-----|------|---|-----------|------|
  | `--video` | 必須 | パス | - | 入力動画ファイル |
  | `--json-dir` | 必須 | パス | - | 既存トラッキング結果 JSON のディレクトリ |
  | `--out-dir` | 必須 | パス | - | 出力先ディレクトリ |
  | `--start-frame` | 任意 | int | 0 | 処理開始フレーム（この値を含む） |
  | `--end-frame` | 任意 | int | 最終フレーム | 処理終了フレーム（この値を含む） |

- **受け入れ基準**:
  - AC-005-1: 必須引数が未指定の場合、argparse のエラーメッセージを表示して終了する
  - AC-005-2: 出力先ディレクトリが存在しない場合、自動作成する
  - AC-005-3: `--start-frame` / `--end-frame` で指定した範囲のみが処理される
  - AC-005-4: `--end-frame` が動画の最終フレーム番号を超える場合、最終フレームまでで終了する

## 4. 非機能要求

### NFR-001: パフォーマンス
- 処理は CPU のみで動作し、GPU を使用しない
- 検証目的のため厳密な処理時間目標は設けない。ただし camSony1_L（約 321K フレーム）の全区間を数時間以内に処理できること

### NFR-002: 対応環境
- OS: Linux（本プロジェクトの開発環境）
- Python: 3.10.16
- パッケージ管理: uv
- GPU: 不要（OpenCV の HSV ヒストグラム計算のみ）

### NFR-003: 信頼性
- 検証用スクリプトのため、ロバスト性より観測可能性を優先する
- JSON ファイルが存在しないフレーム番号は警告ログを出力してスキップする
- 動画フレームの読み込みに失敗した場合は警告ログを出力して当該フレームをスキップする

## 5. 制約条件

### 5.1 使用必須のライブラリ
- OpenCV（動画読み込み、HSV 変換、ヒストグラム計算）
- numpy（配列・ヒストグラム演算）
- matplotlib（時系列グラフ生成）

### 5.2 既存環境への追加検討
- CSV 出力は標準ライブラリ `csv` で実装する。`pandas` は追加しない
- `matplotlib` が既存 uv 環境にあるかは機能設計書で確認する

### 5.3 変更禁止
- `scripts/custom_reid.py` の Re-ID ロジック（`CustomReID.update` 本体、`_match`、`_pending`、`_disappeared` の管理、stable_id 発番）
- `scripts/run_halpe26_pipeline_yolo11.py` の本体処理（`custom_reid` の import 先変更を除く）
- Deep OC-SORT の設定・置き換え

### 5.4 データ制約
- 入力 JSON フォーマットは既存 `scripts/postprocess_reid.py` の出力形式に準拠する（フレームごとに people 配列を持ち、各 person が `track_id`、`stable_id`、`bbox`、`pose_keypoints_2d` を含む）
- 入力動画のフレームレート・解像度に追加制約は設けない

## 6. 優先順位

### 6.1 MoSCoW

| ID | 機能 | 優先度 |
|----|------|--------|
| FR-001 | モジュール切り出し | Must |
| FR-002 | 検証スクリプト本体 | Must |
| FR-003 | CSV ローデータ出力 | Must |
| FR-004 | 時系列グラフ出力 | Should |
| FR-005 | CLI インタフェース | Must |

Won't（本案件のスコープ外）:
- Re-ID ロジックの変更（feat-026 の次フェーズで検討）
- Deep OC-SORT の変更・代替
- 特徴量汚染を防ぐ EMA 更新制御の実装（本案件の観測結果を踏まえて別案件で検討）

### 6.2 MVP
- FR-001 + FR-002 + FR-003 + FR-005 が動作し、CSV が取得できる状態を最小実行可能プロダクトとする
- FR-004（時系列グラフ）は Should。CSV から外部ツールで後処理可能だが、本案件では一括実装して目視確認を容易にする
