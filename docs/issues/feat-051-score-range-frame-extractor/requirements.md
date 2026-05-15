# feat-051 要求仕様書: selection_score 範囲によるフレーム抽出 PNG ツール

## 1. プロジェクト概要

### 1.1 何を作るのか

`scripts/extract_score_range_frames.py`（仮）を新規作成。kp モード JSON ディレクトリと動画を入力に、各フレームの最大 `s = selection_score` が指定範囲内にあるフレームを抽出し PNG 出力する。

### 1.2 なぜ作るのか

`--min-pink-ratio`（feat-050）の閾値設定検討のため、`s` 帯域別に「何が選ばれているか」を目視確認したい。

### 1.3 誰が使うのか

本プロジェクトの開発者。

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| `s` / selection_score | `pink_ratio + 0.05 × iou_with_prev`。JSON フィールド `selection_score`。feat-041 設計で `iou_with_prev=None` のとき `s=None` |
| 有効 s | 本ツール内での計算値: JSON の `selection_score` が非 None ならその値、None なら `pink_ratio` を代替値として使う（**フォールバック規約**） |
| フレーム max s | 当該フレームの全 person について計算した「有効 s」の最大値 |
| 抽出対象人物 | フレーム max s を持つ person（同値が複数あればインデックス小を採用） |

## 3. 機能要求一覧

### FR-001: CLI 引数と入力検証

- **概要**: 必要な入力を受け取りバリデート
- **入力**:
  - `--json-dir` (str, 必須): kp モード JSON ディレクトリ
  - `--video` (str, 必須): 元動画
  - `--out-dir` (str, 必須): PNG 出力先
  - `--score-min` (float, 必須, 値域 `[0.0, 1.05]`): 抽出対象の有効 s 下限（**含む**）
  - `--score-max` (float, 必須, 値域 `[0.0, 1.05]`): 抽出対象の有効 s 上限（**含む**）。両端含む `[score-min, score-max]` で抽出。理論最大 1.05 のフレームも抽出可能
  - `--kpt-conf-min` (float, デフォルト 0.3, 値域 `[0.0, 1.0]`): ROI 状態再計算用
  - `--min-roi-area` (int, デフォルト 200, 値域 `>=1`): 同上
  - `--show-kpt-conf` (BooleanOptionalAction, デフォルト True): キーポイント信頼度テキスト表示。`--no-show-kpt-conf` で OFF（feat-048 と同方式）
- **処理内容**:
  1. ディレクトリ / 動画存在チェック
  2. `--score-min <= --score-max` の検証（等号許容）
- **受け入れ基準**:
  - AC-001-1: `--json-dir` / `--video` が存在しない場合、`ERROR: ...` + exit code 1
  - AC-001-2: `--score-min > --score-max` で exit code 2（単一値抽出のため `--score-min == --score-max` は許容）
  - AC-001-3: 値域外引数で exit code 2

注: `s` 値域は理論上 `[0.0, 1.05]`（pink_ratio max=1.0 + 0.05 × IoU max=1.0）のため上限を 1.05 とする。

### FR-002: 有効 s の計算（フォールバック規約）

- **概要**: 各 person の「有効 s」を計算
- **入力**: person dict
- **処理内容**:
  ```
  if person["selection_score"] is not None:
      s = person["selection_score"]
  elif person["pink_ratio"] is not None:
      s = person["pink_ratio"]   # フォールバック: iou_with_prev=None 時
  else:
      s = None  # bbox 欠損等、計算不能
  ```
- **受け入れ基準**:
  - AC-002-1: `selection_score` 非 None のとき JSON 値を使う
  - AC-002-2: `selection_score` が None で `pink_ratio` が非 None のとき `pink_ratio` を代替値とする
  - AC-002-3: 両方 None の person は max 計算から除外

### FR-003: フレーム max s の計算と抽出

- **概要**: 各フレームの全 person 中の有効 s 最大値を求め、範囲内なら抽出
- **入力**: JSON dict + 範囲 `[score-min, score-max]`（両端含む）
- **処理内容**:
  1. 各 person の有効 s を計算（FR-002）
  2. 有効 s の最大値を求める。同値時はインデックス小の person を選ぶ
  3. `score-min <= max_s <= score-max` なら当該フレームを抽出
  4. 抽出対象 person を保持
- **受け入れ基準**:
  - AC-003-1: 全 person で有効 s が None のフレームは抽出されない
  - AC-003-2: 範囲外（`max_s < score-min` または `max_s > score-max`）のフレームは抽出されない。境界値 `max_s == score-min` または `max_s == score-max` は抽出対象

### FR-004: PNG 描画内容

- **概要**: 抽出フレームの動画イメージに以下を描画して PNG 保存
- **入力**: 動画フレーム + 抽出対象人物の JSON データ
- **出力**: `frame_{NNNNNN}_s{0.XXX}.png` 形式（フレーム番号 6 桁ゼロ埋め、s 値 3 桁）
- **処理内容**:
  1. **人物 BB**: 青枠（BGR=(255,0,0)、線幅 2）
  2. **BB ラベル**:
     - BB 上部ラベル（`pink_id:` / `score:`）は**描画しない**（BB 内部診断ラベルと近接して可読性が落ちるため、本案件では省略）。`pink_id` は BB 内部診断ラベルの `pid={N}` で参照可能。`bbox_score` は本案件では描画しない（必要なら元 JSON を参照）
     - BB 内部に診断ラベル `idx={N} pid={N} r={0.XXX} iou={0.XXX or null} s={0.XXX or null}`。キー欠損 ⇒ 当該要素を省略。キー存在かつ値 None ⇒ `null` 文字列で描画
  3. **keypoint-rect ROI 矩形**: `build_attempted_roi` 経由で取得、状態別色分け（ok=黄、fail_area=オレンジ、fail_kpt=描画なし、feat-048 と同色）
  4. **HALPE26 胴体 4 点**: 暗青、高信頼=塗りつぶし円、低信頼=× マーク、LS/RS/LH/RH ラベル + 信頼度テキスト（feat-048 描画スタイル）
  5. **上部ラベル（黒帯バナー方式）**:
     - 元動画フレームの**上に黒色バナー領域を追加**（背景 BGR=(0,0,0)、高さ 60 px）。元動画ピクセルは一切覆わない
     - 出力 PNG のサイズ = `元動画解像度の高さ + 60 px`、幅は元のまま
     - バナー内に**白文字**で 2 行描画:
       - 1 行目: `Frame: {NNNNNN}  effective_s: {0.XXX} (range: [{score-min}, {score-max}])`
       - 2 行目: `kp-rect ROI: {ok / fail_area / fail_kpt}`（フォールバック発動時は `(s fallback: r used as s)` 注記を付ける）
     - 黒縁取りは不要（背景が黒なので白文字単独で可読）
- **受け入れ基準**:
  - AC-004-1: BB / idx / pid / r / iou / s の各値が描画される
  - AC-004-2: ROI 矩形が状態別色で描画される
  - AC-004-3: 胴体 4 点が描画される（LS/RS/LH/RH ラベル付き）
  - AC-004-4: 出力 PNG 上部の黒帯バナー内に Frame 番号と有効 s 値が表示される
  - AC-004-5: 上部バナーは元動画フレームピクセルを一切覆わない（バナーは元フレームの**上**に追加された別領域として存在し、出力 PNG 高さは元動画高さ + 60 px となる）
  - AC-004-6: BB 上部ラベル（`pink_id:` / `score:`）は描画されない（feat-051 v2 で省略）

### FR-005: 出力ファイル命名規約

- **概要**: PNG ファイル名にフレーム番号と s 値を含める
- **処理内容**: `frame_{frame_idx:06d}_s{s:.3f}.png`（例: `frame_217337_s0.115.png`）
- **受け入れ基準**:
  - AC-005-1: 命名規約通り出力される

### FR-006: サマリ統計の標準出力

- **概要**: 処理結果サマリを表示
- **出力**: 標準出力
- **処理内容**:
  1. 入力 JSON 総フレーム数
  2. 範囲内に該当したフレーム数
  3. s フォールバック発動フレーム数: **抽出された各フレームの「max s person」がフォールバック（`selection_score=None` → `pink_ratio` で代替）だった件数**。他 person のフォールバックは計上しない（フレーム単位カウント）
  4. 成功 PNG 数
  5. シーク失敗数（0 件のときも常に表示する。抑制オプションなし）
  6. 出力先ディレクトリパス
- **受け入れ基準**:
  - AC-006-1: 上記 6 項目が表示される
  - AC-006-2: シーク失敗数は 0 件のときも常に表示される（行が省略されない）

## 4. 非機能要求

### NFR-001: パフォーマンス

- camSony1_L 321K フレームで **5 分以内**に範囲フィルタ + PNG 出力完了（範囲によって PNG 数が大きく変わるため、PNG 描画コストは PNG 数依存）

### NFR-002: 対応環境

- 既存と同一

### NFR-003: 既存スクリプト整合性

- `compare_roi_modes.py` / `visualize_disagreement_frames.py` / `postprocess_pink_id.py` を変更しない
- 描画ヘルパは feat-048 から import 推奨

## 5. 制約条件

### 5.1 使用ライブラリ

- 既存依存のみ

### 5.2 追加禁止

- 動画ファイル出力（PNG のみ）
- JSON 形式の変更（feat-041 の null 規約は保持）

## 6. 優先順位

| ID | 機能 | 優先度 |
|----|------|--------|
| FR-001 | CLI と検証 | Must |
| FR-002 | 有効 s 計算 | Must |
| FR-003 | フレーム max s 抽出 | Must |
| FR-004 | PNG 描画 | Must |
| FR-005 | 命名規約 | Should |
| FR-006 | サマリ統計 | Should |
