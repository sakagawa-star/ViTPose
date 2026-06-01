# feat-046 要求仕様書: postprocess_pink_id.py のキーポイントベース ROI 対応

## 1. プロジェクト概要

### 1.1 何を作るのか

`scripts/postprocess_pink_id.py` の pink_ratio 計算 ROI を CLI `--roi-mode` で切替可能にする拡張。新モード `keypoint-rect` は HALPE26 の 4 キーポイント（LShoulder=5, RShoulder=6, LHip=11, RHip=12）の min/max 軸並行矩形を ROI とし、背景・四肢・顔・髪を HSV 比率計算から除外する。

### 1.2 なぜ作るのか

- 現状の BB 全体 ROI では対象識別の S/N 比が低い（背景・他部位の混入）
- feat-044 で確定したように、ピクセル単位での色分離は不可能だが、領域を絞れば色比率のコントラストは改善できる可能性が高い
- ピンク対象で効果が確認できれば、青対象への拡張（feat-045 以降の検出側）でも同じ ROI 切り出し戦略が流用可能

### 1.3 誰が使うのか

本プロジェクトの開発者（ピンク対象検出精度を改善し、後段の青対象対応に備える者）。

### 1.4 どこで使うのか

既存スクリプトと同一の実行環境（uv 環境、CPU + OpenCV）。実行 CLI は既存引数を維持し、新規 3 引数のみ追加。

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| bb モード | 既存挙動。BB 全体（`bbox = (x1,y1,x2,y2)`）を clip_bbox 後そのまま ROI として使用 |
| keypoint-rect モード | 新規挙動。HALPE26 の 4 キーポイント（LShoulder, RShoulder, LHip, RHip）のうち conf≥`kpt_conf_min` を満たす点のみを使い、それらの (x, y) の min/max で軸並行矩形を作成し ROI とする |
| 信頼できるキーポイント | conf >= `kpt_conf_min`（CLI、デフォルト 0.3）の点 |
| K-2 方式 | 信頼できる点の座標のみで min/max 矩形を構築する方式。信頼度が低い点の座標は使用しない |
| F2 厳しめフォールバック | ROI 構築条件を満たさないとき、当該人物の `pink_ratio = 0` とし、`pink_id = 1` への選択候補から外す。bb モードへの自動フォールバックは行わない |
| ROI 構築条件 | (1) 信頼できる点が 2 個以上、かつ (2) min/max 矩形の面積が `min_roi_area`（CLI、デフォルト 200 px）以上、かつ (3) clip 後の矩形面積が 0 より大きい |
| HALPE26 キーポイント番号 | 0=Nose, 1=LEye, 2=REye, 3=LEar, 4=REar, 5=LShoulder, 6=RShoulder, 7=LElbow, 8=RElbow, 9=LWrist, 10=RWrist, 11=LHip, 12=RHip, 13=LKnee, 14=RKnee, 15=LAnkle, 16=RAnkle, 17=Head, 18=Neck, 19=Hip中心, 20-25=足部 |

## 3. 機能要求一覧

### FR-001: --roi-mode CLI 引数の追加

- **概要**: `--roi-mode {bb,keypoint-rect}` を CLI に追加。デフォルト `bb`
- **入力**: コマンドライン引数
- **出力**: パース済み `args.roi_mode`
- **処理内容**:
  1. argparse で choices=['bb', 'keypoint-rect'] を追加
  2. デフォルト 'bb' で、未指定時の挙動は既存と完全に一致
- **受け入れ基準**:
  - AC-001-1: `--help` で `--roi-mode` が選択肢付きで表示される
  - AC-001-2: 未指定時のデフォルトは `bb`
  - AC-001-3: 不正値（例: `--roi-mode polygon`）は argparse の標準エラー + exit code 2

### FR-002: --kpt-conf-min / --min-roi-area CLI 引数の追加

- **概要**: keypoint-rect モード用のパラメータを CLI で調整可能にする
- **入力**:
  - `--kpt-conf-min` (float、デフォルト 0.3、値域 [0.0, 1.0])
  - `--min-roi-area` (int、デフォルト 200、値域 [1, ∞))
- **出力**: パース済み `args.kpt_conf_min` / `args.min_roi_area`
- **処理内容**:
  1. argparse で type と値域チェックを行う custom type 関数を用意
  2. 値域外は標準エラー + exit code 2
- **受け入れ基準**:
  - AC-002-1: `--help` で両引数が表示される
  - AC-002-2: 値域外（`--kpt-conf-min 1.5`, `--kpt-conf-min -0.1`, `--min-roi-area 0`, `--min-roi-area -1`）で exit code 2
  - AC-002-3: bb モード使用時はこれらの値は使用されない（指定しても影響なし）

### FR-003: bb モードの挙動完全維持

- **概要**: `--roi-mode bb` または未指定時、既存の `postprocess_pink_id.py` と完全に同一の挙動を行う
- **入力**: 既存と同じ（動画、JSON ディレクトリ、出力ディレクトリ）
- **出力**: 既存と同じ JSON（`pink_id`, `pink_ratio`, `bb_index`, `iou_with_prev`, `selection_score` を含む）
- **処理内容**:
  1. ROI 計算は既存通り BB 全体（clip_bbox 後）
  2. それ以外の処理（select_pink_bbox の選択ロジック、IoU 連続性ボーナス、フィールド書き込み）はすべて変更なし
- **受け入れ基準**:
  - AC-003-1: 同一入力に対し、改修前のスクリプトと出力 JSON が完全一致する（`pink_id`, `pink_ratio`, `bb_index`, `iou_with_prev`, `selection_score` のすべて）。検証手順: 改修前バイナリで生成した `out_dir_before/` と改修後 `--roi-mode bb`（デフォルト省略でも可）で生成した `out_dir_after/` に対し `diff -r out_dir_before/ out_dir_after/` を実行し差分 0 を確認する
  - AC-003-2: サマリ出力（フレーム数、選択フレーム数、平均 pink_ratio 等）も改修前と完全一致

### FR-004: keypoint-rect モードの ROI 構築

- **概要**: `--roi-mode keypoint-rect` 指定時、各人物の HALPE26 キーポイント 4 点（5, 6, 11, 12）から軸並行矩形 ROI を計算する
- **入力**: `person['pose_keypoints_2d']`（list of 78 float, [x0, y0, c0, x1, y1, c1, ..., x25, y25, c25]）
- **出力**: ROI 矩形 `(x1, y1, x2, y2)` または「ROI 構築不能」
- **処理内容**:
  1. キーポイント 5, 6, 11, 12 の (x, y, conf) を抽出
  2. conf >= `kpt_conf_min` の点のみを「信頼できる点」として保持
  3. 信頼できる点が 2 個未満 ⇒ ROI 構築不能
  4. 信頼できる点の x 座標の min/max、y 座標の min/max で矩形を作成
  5. 矩形を画像境界で clip
  6. clip 後の面積（(x2-x1) × (y2-y1)）が `min_roi_area` 未満 ⇒ ROI 構築不能
  7. それ以外 ⇒ ROI 構築成功、矩形を返す
- **受け入れ基準**:
  - AC-004-1: 4 点すべて conf>=0.3 のフレームで、min/max 矩形が画像境界内かつ面積>=200 なら ROI 構築成功
  - AC-004-2: 信頼できる点が 0 個または 1 個のフレームで「ROI 構築不能」となる
  - AC-004-3: clip 後の min/max 矩形で `x2 <= x1` または `y2 <= y1`（信頼できる点の x 座標すべて同一、y 座標すべて同一、または画像境界クランプ後に線分縮退する場合）の場合は構築不能（`fail_area`）
  - AC-004-4: 信頼できる点が 3 個で三角形が縦に細い場合、min/max 矩形が `min_roi_area` 未満なら構築不能
  - AC-004-5: 信頼度が低い点の座標は min/max 計算に使用されない（K-2 方式）

### FR-005: keypoint-rect モードの pink_ratio 計算

- **概要**: ROI 構築成功時は ROI に対し既存 `compute_pink_ratio` を適用、ROI 構築不能時は pink_ratio = 0
- **入力**: ROI 矩形（または構築不能フラグ）、フレーム画像
- **出力**: 当該人物の `pink_ratio` (float, [0.0, 1.0])
- **処理内容**:
  1. ROI 構築不能 ⇒ pink_ratio = 0
  2. ROI 構築成功 ⇒ `frame[y1:y2, x1:x2]` を切り出し、`compute_pink_ratio` を適用
- **受け入れ基準**:
  - AC-005-1: ROI 構築不能フレームの pink_ratio は 0.0
  - AC-005-2: ROI 構築成功フレームの pink_ratio は `compute_pink_ratio(frame[y1:y2, x1:x2])` の値
  - AC-005-3: pink_id 選択ロジック（`select_pink_bbox`）は pink_ratio が `MIN_PINK_RATIO` (=0.03) 未満の人物を候補から除外するため、ROI 構築不能で pink_ratio = 0 となった人物は pink_id = 1 にならない（F2 厳しめ動作）

### FR-006: 既存出力フィールドの追加情報

- **概要**: keypoint-rect モード使用時、診断用に追加 2 フィールドを JSON に保存する
- **入力**: 既存と同じ
- **出力**: 各 `people[i]` に以下を追加（keypoint-rect モード時のみ）:
  - `roi_mode` (str, "keypoint-rect")
  - `roi_bbox` (list of 4 int [x1, y1, x2, y2] または null) — ROI 構築不能時は null
- **処理内容**:
  1. bb モード時はこれらのフィールドを書き込まない（後方互換性、JSON 容量削減）
  2. keypoint-rect モード時は両フィールドを書き込む
- **受け入れ基準**:
  - AC-006-1: bb モードで実行した JSON に `roi_mode` / `roi_bbox` キーが存在しない
  - AC-006-2: keypoint-rect モードで実行した JSON で、各 people に `roi_mode = "keypoint-rect"` が存在
  - AC-006-3: ROI 構築成功時 `roi_bbox = [x1, y1, x2, y2]`、構築不能時 `roi_bbox = null`
  - AC-006-4: `roi_bbox` の値は (x1, y1) = ROI 左上、(x2, y2) = ROI 右下、画像境界 clip 後

### FR-007: サマリ出力

- **概要**: keypoint-rect モード使用時、サマリに ROI 構築統計を追加する
- **入力**: なし（内部統計）
- **出力**: 標準出力
- **処理内容**:
  1. keypoint-rect モード時、サマリ末尾に以下を追加:
     - ROI 構築成功人物数 / 総人物数
     - ROI 構築不能（信頼できる点不足）人物数
     - ROI 構築不能（面積不足）人物数
  2. bb モード時はこれらを出力しない
- **受け入れ基準**:
  - AC-007-1: bb モードのサマリは既存と完全一致
  - AC-007-2: keypoint-rect モードで上記 3 統計が出力される

## 4. 非機能要求

### NFR-001: パフォーマンス

- 既存実装（bb モード）に対し、keypoint-rect モードでの処理時間増加は **20% 以内**
- 根拠: 各人物につき 4 キーポイント取得 + min/max 計算 + 面積判定の追加のみ。numpy 演算ではなく Python の単純な数値処理で完結

### NFR-002: 対応環境

- 既存 `postprocess_pink_id.py` と同一（Python 3.10.16、uv 環境、CPU 実行）

### NFR-003: 互換性

- bb モード時の出力 JSON は既存と完全一致（既存下流スクリプト feat-035 / 036 / 037 / 038 / 039 / 040 / 041 / 042 への影響なし）
- keypoint-rect モード時の出力 JSON は既存フィールドを変更せず、新規フィールド `roi_mode` / `roi_bbox` のみ追加（生 dict 保持設計、下流スクリプトは未知フィールドを無視）

## 5. 制約条件

### 5.1 使用必須のライブラリ

- 既存依存のみ（OpenCV、numpy、json 標準ライブラリ）。新規ライブラリ導入なし

### 5.2 追加禁止

- 多角形 ROI（I 方式）・回転矩形 ROI（II-b 方式）の実装
- F1（bb モード自動フォールバック）の実装 — 比較のため F2 厳しめのみ
- 別スクリプトファイルへの分離 — 既存 `postprocess_pink_id.py` 内で完結
- pink_id 選択ロジック（`select_pink_bbox`）の変更
- `FIXED_HSV_RANGES` の変更
- 4 キーポイント番号の変更（5, 6, 11, 12 で固定）

### 5.3 デフォルト値

- `--roi-mode`: `bb`（後方互換）
- `--kpt-conf-min`: 0.3（CLAUDE.md feat-035/036 で採用されている標準値）
- `--min-roi-area`: 200 px

## 6. 優先順位

| ID | 機能 | 優先度 |
|----|------|--------|
| FR-001 | --roi-mode CLI 引数 | Must |
| FR-002 | --kpt-conf-min / --min-roi-area CLI 引数 | Must |
| FR-003 | bb モード挙動完全維持 | Must |
| FR-004 | keypoint-rect モード ROI 構築 | Must |
| FR-005 | keypoint-rect モード pink_ratio 計算 | Must |
| FR-006 | roi_mode / roi_bbox フィールド追加 | Should |
| FR-007 | サマリ統計追加 | Should |
| NFR-001 | パフォーマンス 20% 以内 | Should |

MVP = FR-001 + FR-002 + FR-003 + FR-004 + FR-005。FR-006 / FR-007 / NFR-001 は実装後確認項目。
