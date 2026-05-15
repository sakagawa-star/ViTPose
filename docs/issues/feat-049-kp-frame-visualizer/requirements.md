# feat-049 要求仕様書: keypoint-rect モード単体・全フレーム可視化ツール

## 1. プロジェクト概要

### 1.1 何を作るのか

`postprocess_pink_id.py --roi-mode keypoint-rect` 出力 JSON ディレクトリと元動画を入力に、**全フレームを 1 フレーム 1 枚ずつ PNG として描画**する新規スクリプト `scripts/visualize_kp_frames.py` を作成する。

各 PNG には kp モードの挙動を判定するために必要な情報を描画する:
- pink_id=1 に選ばれた人物の人物 BB（青枠）
- pink_id=1 の人物の keypoint-rect ROI 矩形（状態別に色分け：ok=黄、fail_area=オレンジ、fail_kpt=描画なし）
- pink_id=1 の人物の HALPE26 胴体 4 点（高信頼=塗りつぶし円、低信頼=× マーク、LS/RS/LH/RH ラベル付き）
- 上部診断ラベル（フレーム番号、pink_id 選択有無、idx、pink_ratio、ROI 状態）

### 1.2 なぜ作るのか

feat-048 は不一致フレームのみが対象で kp モード単体の挙動検証には使えない。集計グラフ（feat-040）は個別フレーム信頼性が確立してから意味を持つ。現段階では「全 900 フレームを 1 枚ずつ目視する」運用が必要。

### 1.3 誰が使うのか

本プロジェクトの開発者（kp モード信頼性検証、bug-004 改修必要性の裏付け収集）。

### 1.4 どこで使うのか

既存スクリプトと同一の実行環境（uv 環境、CPU + OpenCV）。

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| kp モード JSON | `postprocess_pink_id.py --roi-mode keypoint-rect` の出力 JSON ディレクトリ |
| pink_id=1 person | 当該フレームで `pink_id == 1` を持つ person（kp モードで選ばれた患者候補。フレームに存在しないこともある） |
| 試行 ROI | feat-048 で定義した「area チェック省略版」の keypoint-rect ROI。`fail_area` でも矩形を返す |
| 描画対象人物 | pink_id=1 person のみ。pink_id=-1 の他 person は描画しない（kp モード選択結果のみに集中） |
| HALPE26 胴体 4 点 | LShoulder (idx=5), RShoulder (idx=6), LHip (idx=11), RHip (idx=12) |
| 高信頼キーポイント | conf >= `--kpt-conf-min`（デフォルト 0.3）の点 |
| 低信頼キーポイント | conf < `--kpt-conf-min` の点 |

## 3. 機能要求一覧

### FR-001: JSON ディレクトリと動画の読み込み

- **概要**: kp モード JSON ディレクトリと元動画を入力に、全フレームを処理対象とする
- **入力**:
  - `--json-dir` (str, 必須): kp モード JSON ディレクトリ
  - `--video` (str, 必須): 元動画
  - `--out-dir` (str, 必須): PNG 出力先
  - `--kpt-conf-min` (float, デフォルト 0.3, 値域 [0.0, 1.0]): ROI 状態再計算用閾値（JSON 生成時と同値）
  - `--min-roi-area` (int, デフォルト 200, 値域 >=1): ROI 状態再計算用最低面積（JSON 生成時と同値）
- **処理内容**:
  1. JSON ディレクトリの全ファイルをフレーム番号で読み込み
  2. 動画の全フレームを順次デコード
  3. JSON が存在しないフレームは PNG にフレーム番号のみ描画し WARNING 出力
- **受け入れ基準**:
  - AC-001-1: `--json-dir` が存在しない場合、`ERROR: JSON directory not found: <path>` を標準エラーに出力し exit code 1
  - AC-001-2: `--video` が存在しない場合、同様に exit code 1
  - AC-001-3: 値域外引数（`--kpt-conf-min 1.5` 等）で argparse がエラー（exit code 2）

### FR-002: フレーム範囲とサンプリング

- **概要**: 描画対象を指定範囲・サンプリングで絞り込み
- **入力**:
  - `--frame-start` (int, デフォルト 0): 開始フレーム番号
  - `--frame-end` (int, デフォルト -1, -1 = 動画末尾): 終了フレーム番号
  - `--step` (int, デフォルト 1, 値域 >=1): N フレームごとに 1 枚出力
- **処理内容**:
  1. 動画フレームを `frame-start` から `frame-end` まで `step` 刻みで描画
  2. JSON が存在しないフレームはスキップせず、空ラベルで PNG 出力（フレーム範囲内なら必ず PNG が出る）
- **受け入れ基準**:
  - AC-002-1: 引数なしで実行すると動画全フレーム（step=1）が PNG 化される
  - AC-002-2: `--step 5` で 5 フレーム刻みで PNG 出力
  - AC-002-3: `--frame-start 100 --frame-end 200` で 101 枚の PNG が出力される

### FR-003: 人物 BB の描画

- **概要**: pink_id=1 person の人物 BB を青枠で描画
- **入力**: `pink_id=1` person の `bbox`
- **出力**: PNG（青枠、線幅 2）
- **処理内容**:
  1. pink_id=1 person が存在する場合のみ描画
  2. 線幅 2、色 = BGR(255, 0, 0)
- **受け入れ基準**:
  - AC-003-1: pink_id=1 person が存在するフレームで青枠が描画される
  - AC-003-2: pink_id=1 person が存在しないフレームでは BB は描画されない

### FR-004: idx ラベル

- **概要**: pink_id=1 person の BB 右上角外側に `idx=N` を青色で描画
- **入力**: pink_id=1 person の `bb_index`
- **出力**: PNG（idx ラベル）
- **処理内容**: feat-048 と同じロジックで青色描画
- **受け入れ基準**:
  - AC-004-1: pink_id=1 person が存在する場合、`idx=N` が青色で描画される

### FR-005: keypoint-rect ROI 矩形の描画

- **概要**: pink_id=1 person の試行 ROI（feat-048 と同じ `build_attempted_roi`）を状態別に色分けで描画
- **入力**: pink_id=1 person の `pose_keypoints_2d`、`--kpt-conf-min`、`--min-roi-area`
- **出力**: PNG（ROI 矩形）
- **処理内容**:
  1. `build_attempted_roi` を呼び出して矩形と状態を取得
  2. `ok` = 黄色 (BGR=(0,255,255))、`fail_area` = オレンジ (BGR=(0,165,255))、`fail_kpt` = 描画なし
  3. 線幅 2
- **受け入れ基準**:
  - AC-005-1: `ok` 状態の ROI は黄色で描画される
  - AC-005-2: `fail_area` 状態の ROI はオレンジ色で描画される
  - AC-005-3: `fail_kpt` 状態は矩形描画なし、上部ラベルで状態を示す
  - AC-005-4: pink_id=1 person が存在しないフレームでは ROI は描画されない

### FR-006: HALPE26 胴体 4 点の描画

- **概要**: pink_id=1 person の胴体 4 点を描画
- **入力**: pink_id=1 person の `pose_keypoints_2d`
- **出力**: PNG（最大 4 点）
- **処理内容**:
  1. 4 点を暗青色（BGR=(200,100,0)）で描画
  2. 高信頼（conf >= `--kpt-conf-min`）= 塗りつぶし円（半径 6）、低信頼 = × マーク
  3. 各点に 2 文字ラベル（LS / RS / LH / RH）を併記
  4. 信頼度テキスト `0.XX` を併記（`--show-kpt-conf` で ON/OFF、デフォルト ON）
- **受け入れ基準**:
  - AC-006-1: 4 点が暗青色で描画される
  - AC-006-2: 高信頼点と低信頼点が形状で判別できる
  - AC-006-3: 部位ラベル LS/RS/LH/RH が併記される
  - AC-006-4: `--show-kpt-conf` で信頼度テキストの ON/OFF 切替

### FR-007: 上部診断ラベル

- **概要**: フレーム情報を上部に表示
- **入力**: フレーム番号、pink_id=1 person の有無、idx、pink_ratio、ROI 状態
- **出力**: PNG（黒縁取り + 白文字）
- **処理内容**:
  1. 1 行目: `Frame: NNNNNN`
  2. 2 行目: pink_id=1 が存在する場合 `kp: idx=N ratio=0.XXX  kp-rect ROI: <status> <bbox or "->">`、存在しない場合 `kp: no pink_id=1 person in this frame`
  3. JSON 自体が欠落する場合 `(no JSON for this frame)` を表示
- **受け入れ基準**:
  - AC-007-1: 1 行目は必ず表示
  - AC-007-2: pink_id=1 の有無に応じて 2 行目が分岐
  - AC-007-3: ROI 状態（ok / fail_kpt / fail_area）が表示される

### FR-008: サマリ統計の標準出力

- **概要**: 処理結果を標準出力
- **出力**:
  - 処理フレーム数
  - pink_id=1 ありフレーム数
  - pink_id=1 なしフレーム数
  - JSON 欠落フレーム数
  - 成功 PNG 数
- **受け入れ基準**: AC-008-1: 上記 5 値が表示される

## 4. 非機能要求

### NFR-001: パフォーマンス

- camSony1_S 全 900 フレーム PNG 出力で **60 秒以内**

### NFR-002: 対応環境

- 既存スクリプトと同一（Python 3.10.16、uv 環境、CPU、OpenCV）

### NFR-003: feat-048 との整合性

- 描画スタイル（色、フォントサイズ、線幅、マーカー形状、ラベル位置）は feat-048 と統一
- `build_attempted_roi` は feat-048 と同じものを使用（visualize_disagreement_frames.py から import するか、共通モジュール化するかは design で確定）

## 5. 制約条件

### 5.1 使用ライブラリ

- 既存依存のみ（OpenCV、json、argparse、os、sys、re）

### 5.2 追加禁止

- 動画ファイル出力（PNG のみ）
- bb モードとの比較（kp モード単体専用）
- pink_id != 1 の他 person 描画（pink_id=1 person のみに集中）

## 6. 優先順位

| ID | 機能 | 優先度 |
|----|------|--------|
| FR-001 | JSON / 動画読み込み | Must |
| FR-002 | フレーム範囲・サンプリング | Must |
| FR-003 | 人物 BB 描画 | Must |
| FR-004 | idx ラベル | Must |
| FR-005 | ROI 矩形描画 | Must |
| FR-006 | 胴体 4 点描画 | Must |
| FR-007 | 上部診断ラベル | Must |
| FR-008 | サマリ統計 | Should |

MVP = FR-001〜FR-007。
