# feat-048 要求仕様書: 不一致フレーム可視化の情報再設計

## 1. プロジェクト概要

### 1.1 何を作るのか

`scripts/visualize_disagreement_frames.py` を全面的に再設計する。bb モード / keypoint-rect モードの JSON ディレクトリを直接読み、不一致フレームについて両モードの選択結果と keypoint-rect ROI 情報を 1 枚の PNG に描画して、δ（不一致目視判定）検証を成立させる。

`compare_roi_modes.py` は変更しない（CSV / 散布図出力を残置）。

### 1.2 なぜ作るのか

feat-047 / feat-048 初版（CSV 経路）では:
- `only_bb` ケース（不一致 139 件中 131 件、94%）で kp 側情報が CSV に含まれず描画不能
- 可読性問題（idx ラベル重なり、キーポイント識別不能、ROI 視認困難、ROI 未構築理由不明）

により δ 判定が成立しなかった。本案件で根本再設計する。

### 1.3 誰が使うのか

本プロジェクトの開発者（feat-046 keypoint-rect モード効果検証、bug-004 / feat-049 の判定材料収集）。

### 1.4 どこで使うのか

既存スクリプトと同一の実行環境（uv 環境、CPU + OpenCV）。

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| bb モード JSON | `postprocess_pink_id.py --roi-mode bb` の出力 JSON ディレクトリ |
| keypoint-rect モード JSON | 同 `--roi-mode keypoint-rect` の出力 JSON ディレクトリ |
| disagreement_type | 既存定義: `both_selected_different` / `only_bb` / `only_kp` / `both_none`。本案件でも継続使用 |
| bb 選択人物 | bb モード JSON の `pink_id=1` の person |
| kp 選択人物 | keypoint-rect モード JSON の `pink_id=1` の person |
| bb 選択人物の kp-rect ROI | bb 選択人物に対応する keypoint-rect モード JSON 内の person（**同一 `bb_index` フィールド値を持つ person を線形検索で取得**。配列インデックス直参照ではなく `bb_index` フィールド一致で引く。bb モードと kp モードで人物検出順序が同一でない可能性に備える） |
| HALPE26 胴体 4 点 | LShoulder (idx=5), RShoulder (idx=6), LHip (idx=11), RHip (idx=12) |
| 高信頼キーポイント | conf >= `--kpt-conf-min`（デフォルト 0.3）の点。値域 [0.0, 1.0]。kp モード JSON 生成時の `postprocess_pink_id.py --kpt-conf-min` と同値を渡すべき（食い違うと ROI 状態再計算結果が JSON 生成時と乖離する） |
| 低信頼キーポイント | conf < `--kpt-conf-min` の点 |
| ROI 未構築 | keypoint-rect モード JSON で当該 person の `roi_bbox` が null。原因は `fail_kpt`（信頼点 2 個未満）または `fail_area`（面積 < `--min-roi-area`）。判別は visualize 内で `build_keypoint_rect_roi` を再呼び出しして取得 |
| 試行 ROI | visualize 内で **area チェックを省略した版**の ROI 構築ロジックで得られる矩形。信頼点 2 個以上で構築可能な場合に得られる。feat-046 の `fail_area` 状態でもこの矩形は存在し、本案件では描画対象とする |

## 3. 機能要求一覧

### FR-001: JSON ディレクトリ直読み

- **概要**: bb / kp 両モード JSON ディレクトリを入力に、フレーム単位で両 JSON の対応を取り、不一致フレームを抽出する
- **入力**:
  - `--bb-json-dir` (str, 必須): bb モード JSON ディレクトリ
  - `--kp-json-dir` (str, 必須): keypoint-rect モード JSON ディレクトリ
  - `--video` (str, 必須): 元動画
  - `--out-dir` (str, 必須): PNG 出力先
  - `--kpt-conf-min` (float, デフォルト 0.3, 値域 [0.0, 1.0]): ROI 状態再計算用のキーポイント信頼度閾値。**kp モード JSON 生成時に使った値と同値を渡すこと**
  - `--min-roi-area` (int, デフォルト 200, 値域 >=1): ROI 状態再計算用の最低面積。同上
- **出力**: 内部データ構造（disagreement フレームリスト）
- **処理内容**:
  1. 両ディレクトリの全 JSON をフレーム番号で対応付け
  2. 両 JSON で共通するフレームのみ処理対象
  3. 各フレームで bb 側 / kp 側の `pink_id=1` person を取得
  4. `disagreement_type` を判定（既存 `classify_disagreement` ロジック相当）
  5. `both_none` 以外のフレームのみ後続処理
- **受け入れ基準**:
  - AC-001-1: いずれかのディレクトリが存在しない場合、`ERROR: JSON directory not found: <path>` を標準エラーに出力し exit code 1
  - AC-001-2: 共通フレームのみ処理対象。片方のみのフレームは standard error に WARNING 出力（既存 `compare_roi_modes.py` と同様）
  - AC-001-3: ファイル名パターン `_(\d{6})\.json$` に一致しないファイルは無視

### FR-002: サンプリング（既存挙動維持）

- **概要**: 不一致フレーム数が多い場合に均等間隔でサンプリング
- **入力**:
  - `--max-samples` (int, デフォルト 50, 値域 >=1)
  - `--all` (flag, デフォルト False)
- **処理内容**: 既存 feat-047 と同じ均等サンプリングロジック
- **受け入れ基準**:
  - AC-002-1: `--all` 指定時は不一致全件処理
  - AC-002-2: `--all` 未指定時は `min(不一致件数, max-samples)` 件を均等抽出
  - AC-002-3: `--max-samples 0` または負値で argparse がエラー（exit code 2）

### FR-003: 人物 BB の描画

- **概要**: bb 選択人物と kp 選択人物の人物 BB（YOLO11x 出力）を画像に描画
- **入力**: bb 選択人物の `bbox`、kp 選択人物の `bbox`
- **出力**: PNG（人物 BB 矩形）
- **処理内容**:
  1. bb 選択人物の `bbox` を**赤枠** (BGR=(0,0,255))、線幅 2 で描画
  2. kp 選択人物の `bbox` を**青枠** (BGR=(255,0,0))、線幅 2 で描画
  3. `only_bb` フレームは赤枠のみ、`only_kp` フレームは青枠のみ
- **受け入れ基準**:
  - AC-003-1: 該当する選択がある場合のみ枠が描画される
  - AC-003-2: 線幅 2 で描画される

### FR-004: idx ラベルの描画

- **概要**: 各人物 BB に `idx=N` ラベルを描画（キーポイント領域と重ならない位置）
- **入力**: bb 選択人物の `bb_index`、kp 選択人物の `bb_index`
- **出力**: PNG（idx ラベル）
- **処理内容**:
  1. 赤枠の **右上角の外側**（x2 + 数 px, y1 + 数 px）に赤色 `idx=N`
  2. 青枠の **右上角の外側**（x2 + 数 px, y1 + 数 px）に青色 `idx=N`
  3. ラベルが画像外にはみ出す場合は内側に折り返し（具体位置は design で確定）
  4. 黒縁取り + 色本体の 2 重 putText で可読性確保
- **受け入れ基準**:
  - AC-004-1: idx ラベルがキーポイント描画と重ならない
  - AC-004-2: BB と同色（赤/青）で描画され、対応が一目で判る

### FR-005: keypoint-rect ROI 矩形の描画（構築失敗時も含めて常に描く）

- **概要**: bb 選択人物・kp 選択人物の双方について、**keypoint-rect ROI の算出結果を可能な限り常に描画する**。JSON に保存された `roi_bbox` が `null`（feat-046 で `fail_area` または `fail_kpt` 扱い）の場合でも、visualize 内で同じロジックを再計算し、矩形が形成可能なら描画する。
- **入力**:
  - 対象人物の `pose_keypoints_2d`
  - `--kpt-conf-min` / `--min-roi-area`（JSON 生成時と同値）
- **出力**: PNG（ROI 矩形 + 状態テキスト）
- **処理内容**:
  1. 対象人物（bb 選択人物の kp 側対応 person、kp 選択人物）について、**area チェックを行わない版**の ROI 構築ロジックを visualize 内で実行する
  2. 信頼点 2 個未満 → 矩形を描画できない（後述 AC-005-4）
  3. 信頼点 2 個以上 → 矩形を構築し、`min_roi_area` を満たすか否かに関わらず描画
  4. 描画色を状態で分ける:
     - `ok`（feat-046 と同じ判定で構築成功）= **黄色** (BGR=(0,255,255))
     - `fail_area`（矩形は構築できたが面積 < `min_roi_area`）= **オレンジ** (BGR=(0,165,255))
     - `fail_kpt`（信頼点 2 個未満）= 描画なし
  5. 線幅は両状態とも 2
  6. bb 選択 ROI と kp 選択 ROI が同一座標になる場合は dedup（1 つだけ描画。色は描画順で先勝ち）
- **受け入れ基準**:
  - AC-005-1: `ok` 状態の ROI は黄色で描画される
  - AC-005-2: `fail_area` 状態の ROI もオレンジ色で描画される（feat-048 初版では描画されなかった）
  - AC-005-3: `only_bb` ケースでも bb 選択人物の kp-rect ROI が（状態に応じて色を変えて）描画される。ただし `fail_kpt` / `not_present` の場合は AC-005-4 に従い矩形は描画されず、上部診断ラベル（FR-007）で状態が示される
  - AC-005-4: `fail_kpt` 状態（信頼点 2 個未満で矩形構築不能）の場合のみ ROI 矩形は描画されない。理由は上部診断ラベル（FR-007）で示される
  - AC-005-5: 矩形の色は人物 BB（赤/青）と区別可能（黄/オレンジは独立色域）

### FR-006: HALPE26 胴体 4 点の描画

- **概要**: bb 選択人物・kp 選択人物の胴体 4 点を描画
- **入力**:
  - bb 選択人物の `pose_keypoints_2d` (bb モード JSON)
  - kp 選択人物の `pose_keypoints_2d` (kp モード JSON)
- **出力**: PNG（最大 8 点）
- **処理内容**:
  1. bb 選択 4 点を**暗赤色** (例: (0,0,200))、kp 選択 4 点を**暗青色** (例: (200,100,0)) で描画
  2. 高信頼点（conf >= 0.3）= **塗りつぶし円**、低信頼点（conf < 0.3）= **× マーク**（線が交差で明確に判別可能）
  3. 円・× のサイズは判別容易な大きさ（半径 6 以上、具体値は design で確定）
  4. 各点の近傍に **2 文字ラベル** (`LS`, `RS`, `LH`, `RH`) を併記（BB 色と同系）
  5. 信頼度テキスト `c=0.XX` は併記（`--show-kpt-conf` フラグで ON/OFF、デフォルト ON）
- **受け入れ基準**:
  - AC-006-1: 高信頼点と低信頼点が形状で明確に判別できる
  - AC-006-2: 各点がどの胴体部位か（LS/RS/LH/RH）ラベルで判別できる
  - AC-006-3: bb 選択 4 点と kp 選択 4 点が色（暗赤/暗青）で判別できる
  - 注記: 安全装置として「bb_index 一致時の重複描画スキップ」を design 側に実装する（理論上 disagreement 定義により発動しないが、データ異常時の防護）
  - AC-006-4: `--show-kpt-conf` フラグで信頼度テキストの ON/OFF 切替可能

### FR-007: 上部診断ラベルの描画

- **概要**: 画像上部に診断情報をテキストで表示
- **入力**: 内部状態（フレーム番号、disagreement_type、各モードの選択情報、ROI 状態）
- **出力**: PNG（黒縁取り + 白文字の複数行テキスト）
- **処理内容**:
  1. 1 行目: `Frame: NNNNNN | Type: <disagreement_type>`
  2. 2 行目: `bb: idx=N ratio=0.XXX  kp-rect ROI: <status> <bbox or "->">`（bb 選択あり時）
  3. 3 行目: `kp: idx=N ratio=0.XXX  kp-rect ROI: <status> <bbox or "->">`（kp 選択あり時）
  4. `<status>` は `ok` / `fail_kpt` / `fail_area` / `not_present` の文字列
     - `not_present`: bb 選択人物の `bb_index` を kp 側 JSON で線形検索しても一致 person が見つからない異常系（通常は発生しないが、bb/kp で people 配列が異なるパイプラインを通った場合や後処理の影響で発生し得る。発生時は標準エラーに WARNING 出力）
  5. ROI 未構築理由は visualize 内で `build_keypoint_rect_roi` 相当のロジックを呼んで再計算（同関数を import するか相当のロジックを内包）
- **受け入れ基準**:
  - AC-007-1: 1 行目の Frame / Type は必ず表示される
  - AC-007-2: bb 選択あり時は 2 行目に bb 情報が表示される
  - AC-007-3: kp 選択あり時は 3 行目に kp 情報が表示される
  - AC-007-4: ROI 未構築の理由が `fail_kpt` / `fail_area` / `not_present` で表示される

### FR-008: シーク失敗時のフォールバック（既存挙動維持）

- 既存 feat-047 と同じ。`cap.set` + `cap.read()` 失敗時に WARNING 出力 + skip + 後続継続

### FR-009: サマリ統計の標準出力

- 不一致フレーム数（disagreement_type ごと）、サンプリング後の処理対象数、成功 PNG 数、シーク失敗数を表示
- 既存 feat-047 の visualize サマリに加え、disagreement_type ごとのカウントも出す

## 4. 非機能要求

### NFR-001: パフォーマンス

- camSony1_S 全 900 フレーム + 不一致 139 件 PNG 出力で **30 秒以内**（必達）
- camSony1_L 321K フレームの不一致サンプル 50 件 PNG 出力: **ベストエフォート**。JSON 全読みがネックになり 60 秒を超える可能性があるが、本案件 MVP では性能最適化を行わない。性能問題が顕在化した場合は別案件として「pink_id=1 を持つフレームのみ列挙する 1 パス先行 → 対象フレームのみ再読み込み」等の最適化を検討する

### NFR-002: 対応環境

- 既存スクリプトと同一（Python 3.10.16、uv 環境、CPU、OpenCV + numpy）

### NFR-003: 既存スクリプトとの整合性

- `compare_roi_modes.py` は変更しない
- `postprocess_pink_id.py` の JSON 出力形式は変更しない（feat-046 で定義済み）
- `scripts/README.md`:
  - `compare_roi_modes.py` セクションは変更しない
  - `visualize_disagreement_frames.py` セクションは**全面改訂する**（CLI 引数変更、入力源変更、描画内容変更に追従）

## 5. 制約条件

### 5.1 使用ライブラリ

- 既存依存のみ（OpenCV、numpy、json、argparse、os、sys、pathlib、re）
- 新規ライブラリ追加なし

### 5.2 追加禁止

- CSV を入力に取らない（CSV 経路は完全廃止）
- 出力 PNG を複数枚に分割しない（1 フレーム 1 枚を維持）
- 解像度のリサイズはしない（元動画解像度のままで描画。本案件では描画要素の改良で可読性確保）

### 5.3 既存実装からの破壊的変更

- `visualize_disagreement_frames.py` の CLI 引数: `--csv` を削除、`--bb-json-dir` / `--kp-json-dir` を追加（後方互換性の維持はしない）
- feat-047 / feat-048 初版で生成された disagreement.csv ベースの動作は本案件で廃止

## 6. 優先順位

| ID | 機能 | 優先度 |
|----|------|--------|
| FR-001 | JSON ディレクトリ直読み | Must |
| FR-002 | サンプリング | Must |
| FR-003 | 人物 BB 描画 | Must |
| FR-004 | idx ラベル | Must |
| FR-005 | ROI 矩形描画 | Must |
| FR-006 | 胴体 4 点描画 | Must |
| FR-007 | 上部診断ラベル | Must |
| FR-008 | シーク失敗フォールバック | Should |
| FR-009 | サマリ統計 | Should |

MVP = FR-001〜FR-007。
