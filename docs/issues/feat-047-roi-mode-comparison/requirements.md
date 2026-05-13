# feat-047 要求仕様書: ROI モード比較・可視化ツール

## 1. プロジェクト概要

### 1.1 何を作るのか

feat-046 で導入される `--roi-mode` の 2 モード（bb / keypoint-rect）の効果を比較するためのツール 2 つ:

- `scripts/compare_roi_modes.py`: 2 つの pink_id JSON ディレクトリを入力に、α-1（同一フレームの pink_ratio 比較）と δ（不一致フレーム抽出）を実施し、CSV と散布図 PNG を出力
- `scripts/visualize_disagreement_frames.py`: 不一致フレーム CSV と元動画を入力に、不一致フレームの目視確認用 PNG を出力（V-2 方式）

### 1.2 なぜ作るのか

feat-046 のクローズ判定には、bb モードと keypoint-rect モードの効果比較が必須。比較指標は:

- **α-1**: 同一フレームの bb pink_ratio vs keypoint-rect pink_ratio を散布図で確認（背景画素減少により keypoint-rect が高くなる期待 / 逆転ケースの観察）
- **δ（不一致目視）**: 「BB モードで pink_id=1 になった人物」と「keypoint-rect モードで pink_id=1 になった人物」が異なるフレームを抽出し、目視で「どちらが正しい患者を選んでいるか」を判定

「擬似正解」を立てず、不一致フレームのみを人間が目視判定することで、循環参照を避けた信頼性のある評価ができる。

### 1.3 誰が使うのか

本プロジェクトの開発者（feat-046 の効果検証、ピンク患者 → 青患者拡張の判断材料を集める者）。

### 1.4 どこで使うのか

既存スクリプトと同一の実行環境（uv 環境、CPU + OpenCV）。

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| bb モード JSON | feat-046 改修済み `postprocess_pink_id.py` を `--roi-mode bb` で実行した出力 JSON ディレクトリ |
| keypoint-rect モード JSON | 同じく `--roi-mode keypoint-rect` で実行した出力 JSON ディレクトリ |
| α-1 散布図 | 横軸 = bb モードの `pink_ratio`、縦軸 = keypoint-rect モードの `pink_ratio`、点 = フレーム |
| 不一致フレーム | `pink_id == 1` を付与された人物（or 該当なし）が 2 モード間で異なるフレーム |
| 不一致タイプ | 不一致フレームの分類。下記 4 種類:<br>- `both_selected_different`: 両モードで `pink_id=1` 人物が存在するが異なる人物（bb_index が異なる）<br>- `only_bb`: bb モードのみで `pink_id=1` が選ばれている<br>- `only_kp`: keypoint-rect モードのみで `pink_id=1` が選ばれている<br>- `both_none`: 両モードとも `pink_id=1` 人物なし → **不一致リストには含めない**（実装上「一致」扱い） |
| サンプリング | 不一致フレーム数が多い場合に、目視可視化対象を一部に絞る機能 |

## 3. 機能要求一覧

### compare_roi_modes.py

#### FR-001: 2 つの JSON ディレクトリの読み込み

- **概要**: bb モード JSON ディレクトリと keypoint-rect モード JSON ディレクトリを入力に、フレームごとの pink_id 情報を読み込む
- **入力**:
  - `--bb-json-dir` (str, 必須): bb モード JSON ディレクトリ
  - `--kp-json-dir` (str, 必須): keypoint-rect モード JSON ディレクトリ
- **出力**: 内部データ構造（フレーム番号 → bb モード結果 / keypoint-rect モード結果）
- **処理内容**:
  1. 両ディレクトリのファイル名パターン `*_{NNNNNN}.json` でフレーム番号を抽出
  2. 両者に共通するフレーム番号の積集合（intersection）を処理対象とする
  3. 各 JSON を読み込み、`people` リストから `pink_id == 1` の人物の `bb_index` と `pink_ratio` を取得
- **受け入れ基準**:
  - AC-001-1: `--bb-json-dir` または `--kp-json-dir` のいずれか（一方または両方）が存在しないディレクトリパスを指している場合、標準エラーに `ERROR: JSON directory not found: <path>` を出力 + exit code 1 で終了する
  - AC-001-2: 片方のディレクトリにしか存在しないフレーム番号は処理対象から除外され、サマリで警告
  - AC-001-3: ファイル名パターンに一致しないファイルは無視

#### FR-002: α-1 散布図 PNG 出力

- **概要**: 全フレームの「pink_id=1 人物の pink_ratio」を 2 モードで比較する散布図 PNG を出力
- **入力**: FR-001 で読み込んだ内部データ
- **出力**: `--out-dir` 配下に `alpha1_scatter.png`
- **処理内容**:
  1. 各フレームごとに、bb モードの「pink_id=1 人物の pink_ratio」と keypoint-rect モードの「同上」を取得
  2. **両モードとも pink_id=1 人物が存在しないフレーム（both_none）は散布図から除外**（両ゼロ点が原点に集積して情報量を下げるのを避けるため）
  3. 片方のみ存在のフレーム（only_bb / only_kp）は、存在しない側の ratio を 0.0 として描画（軸端で「片方ゼロ」群として観察可能）
  4. matplotlib で散布図を描画（横軸 = bb ratio、縦軸 = kp ratio、対角線 y=x も描画）
  5. 図サイズ 1000×1000、dpi=80、点サイズ小（透明度 0.3）
  6. 軸ラベル、タイトル、対角線凡例を含む。タイトルには散布点数と除外 both_none 数を併記
- **受け入れ基準**:
  - AC-002-1: `alpha1_scatter.png` が指定ディレクトリに保存される
  - AC-002-2: 横軸・縦軸ともに値域 [0.0, 1.0]
  - AC-002-3: 対角線 y=x が点線で描画され、凡例に「y=x」と表示される
  - AC-002-4: `both_none` フレームは散布図プロット対象から除外される（タイトルに除外件数を表示）

#### FR-003: 不一致フレーム CSV 出力

- **概要**: 不一致フレーム（FR-002 の処理対象のうち、定義に該当するもの）を CSV 形式で出力
- **入力**: FR-001 で読み込んだ内部データ
- **出力**: `--out-dir` 配下に `disagreement.csv`
- **処理内容**:
  1. 各フレームの不一致タイプを判定（用語定義の 4 種、`both_none` は除外）
  2. CSV 列構成:
     - `frame_idx` (int)
     - `disagreement_type` (str)
     - `bb_selected_bb_index` (int または空欄)
     - `bb_pink_ratio` (float、bb モードで pink_id=1 がない場合は空欄)
     - `bb_bbox` (str、`[x1,y1,x2,y2]` の形式、ない場合は空欄)
     - `kp_selected_bb_index` (int または空欄)
     - `kp_pink_ratio` (float、ない場合は空欄)
     - `kp_bbox` (str、ない場合は空欄)
  3. ヘッダ行を含む
  4. `frame_idx` 昇順
- **受け入れ基準**:
  - AC-003-1: `disagreement.csv` が指定ディレクトリに保存される
  - AC-003-2: 不一致がない場合はヘッダのみ含まれる
  - AC-003-3: CSV ヘッダ列名は上記の 8 列に一致
  - AC-003-4: `both_none` のフレームは CSV に含まれない

#### FR-004: サマリ統計の標準出力

- **概要**: 処理サマリを標準出力する
- **入力**: 内部データ
- **出力**: 標準出力
- **処理内容**:
  1. 処理フレーム数（両ディレクトリ積集合）
  2. 不一致タイプごとのカウント
  3. α-1 散布図と CSV の保存先パス
- **受け入れ基準**:
  - AC-004-1: 「Total frames processed」「Disagreement counts: both_selected_different=N1, only_bb=N2, only_kp=N3, both_none=N4」「Output: ...」の 3 行以上が表示される
  - AC-004-2: 片側のみ存在フレーム数（bb-only、kp-only）が 0 でなければ警告行 `WARNING: bb-only frames=X, kp-only frames=Y` が出力される

### visualize_disagreement_frames.py

#### FR-005: 不一致フレーム PNG 出力

- **概要**: `disagreement.csv` と動画ファイルを入力に、各不一致フレームを目視確認用 PNG として出力（V-2 方式）
- **入力**:
  - `--video` (str, 必須): 元動画ファイル
  - `--csv` (str, 必須): `disagreement.csv` パス
  - `--out-dir` (str, 必須): PNG 出力先ディレクトリ
  - `--max-samples` (int, デフォルト 50): 出力する PNG 数の上限。**値域は `>= 1`**。`0` または負値は argparse でエラー（exit code 2）。`--all` 指定時は無視
  - `--all` (flag, デフォルト False): 全件出力（`--max-samples` を無視）
- **出力**: `{out-dir}/frame_{NNNNNN}_disagree.png` 形式のファイル群
- **処理内容**:
  1. CSV を読み込み、不一致フレームのリストを取得
  2. `--all` が True なら全件、False ならフレーム番号順に均等サンプリング `max-samples` 件
  3. 各フレームについて:
     - `cv2.VideoCapture` で当該フレームを取得（シーク）
     - bb モード選択 BB を**赤枠** (BGR=(0,0,255)) で描画
     - keypoint-rect モード選択 BB を**青枠** (BGR=(255,0,0)) で描画
     - 両モードが同じ BB を選んでいる場合は**紫枠** (BGR=(255,0,255)) で描画（理論上は不一致リストに含まれないが、保険）
     - 画像上部に以下のテキストオーバーレイ:
       - `Frame: NNNNNN | Type: <disagreement_type>`
       - `BB: idx=N ratio=0.XXX` (該当ある場合)
       - `KP: idx=N ratio=0.XXX` (該当ある場合)
     - PNG として `frame_{NNNNNN}_disagree.png` で保存
- **受け入れ基準**:
  - AC-005-1: PNG ファイル名が `frame_{NNNNNN}_disagree.png` 形式で、フレーム番号 6 桁ゼロ埋め
  - AC-005-2: `--all` 未指定時、処理対象（サンプリング後の）フレーム数 = min(不一致フレーム数, `max-samples`)。成功 PNG 数は処理対象数以下（シーク失敗があれば不足する可能性あり）
  - AC-005-3: `--all` 指定時、処理対象フレーム数 = 不一致フレーム総数。成功 PNG 数は処理対象数以下
  - AC-005-4: 各 PNG について、CSV で当該モードの bbox が存在する場合のみ当該色で描画される（`only_bb` フレームは赤枠のみ、`only_kp` フレームは青枠のみ、`both_selected_different` フレームは赤・青の両方）
  - AC-005-5: PNG 上部のテキストに frame_idx と disagreement_type が必ず含まれる
  - AC-005-6: `--max-samples 0` または負値の指定時、argparse が「invalid value」エラーで exit code 2 を返す

#### FR-006: シーク失敗時のフォールバック

- **概要**: 動画シークが失敗したフレームはスキップしてエラー出力
- **入力**: なし（内部処理）
- **出力**: 標準エラー
- **処理内容**:
  1. `cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)` 後 `cap.read()` が False を返した場合、当該フレームをスキップ
  2. 標準エラーに `WARNING: failed to seek frame {N}` を出力
  3. 残りのフレームは継続処理
- **受け入れ基準**:
  - AC-006-1: シーク失敗フレームは PNG が生成されない
  - AC-006-2: シーク失敗 → 警告出力 → 後続フレーム処理継続
  - AC-006-3: 全フレームシーク失敗でもクラッシュせず exit code 0 で終了（PNG ゼロ件）
  - AC-006-4: 入力 CSV が空（ヘッダ行のみで不一致 0 件）の場合、success_count=0、seek_fail_count=0、処理対象数=0 でサマリ出力後 exit code 0 で終了

#### FR-007: サマリ統計の標準出力

- **概要**: 処理結果のサマリを標準出力
- **入力**: 内部状態
- **出力**: 標準出力
- **処理内容**:
  1. 入力 CSV の不一致フレーム数
  2. サンプリング後の処理対象フレーム数
  3. 出力成功 PNG 数
  4. シーク失敗フレーム数
- **受け入れ基準**:
  - AC-007-1: 処理結果 4 種の数値が表示される

## 4. 非機能要求

### NFR-001: パフォーマンス

- `compare_roi_modes.py`: camSony1_L 全体（321K フレーム）で **2 分以内**
- `visualize_disagreement_frames.py`: 不一致フレーム 50 件のサンプリング処理が **30 秒以内**

### NFR-002: 対応環境

- 既存スクリプトと同一（Python 3.10.16、uv 環境、CPU 実行、OpenCV + numpy + matplotlib）

### NFR-003: 出力品質

- PNG は標準的なビューワで再生可能
- CSV は標準的な表計算ソフト（LibreOffice Calc、pandas 等）で読み込み可能

## 5. 制約条件

### 5.1 使用ライブラリ

- 既存依存: OpenCV、numpy、matplotlib、json、csv（標準）
- 新規ライブラリ追加なし

### 5.2 追加禁止

- 動画形式での比較出力（V-1 / V-3 は不採用）
- 自動的な「正解判定」アルゴリズム（目視判定が前提）
- 両モード以外（多角形 ROI、回転矩形 ROI 等）の比較
- 3 モード以上の同時比較（2 モードのみ）

### 5.3 サンプリング規約

- 均等サンプリング: 不一致フレーム全体から `max_samples` 件を均等間隔で抽出
- 例: 不一致 1000 件、max_samples 50 → step = 20 でインデックス 0, 20, 40, ..., 980 を抽出

## 6. 優先順位

| ID | 機能 | 優先度 |
|----|------|--------|
| FR-001 | JSON ディレクトリ読み込み | Must |
| FR-002 | α-1 散布図 PNG | Must |
| FR-003 | 不一致 CSV | Must |
| FR-004 | compare サマリ | Should |
| FR-005 | 不一致フレーム PNG 出力 | Must |
| FR-006 | シーク失敗フォールバック | Should |
| FR-007 | visualize サマリ | Should |

MVP = FR-001 + FR-002 + FR-003 + FR-005。
