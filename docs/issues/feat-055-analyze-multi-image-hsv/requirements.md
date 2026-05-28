# feat-055 要求仕様書: analyze_clothing_color.py の複数画像入力・プール提案・閾値検証対応

## 1.1 プロジェクト概要

- **何を作るのか**: `scripts/analyze_clothing_color.py` を拡張し、複数の服パッチ静止画を
  一度に受け取り、全画像を覆う単一の HSV 設定（`postprocess_pink_id.py --hsv-config` 互換 JSON）を
  「プール方式」で提案する。各画像の `pink_ratio` を閾値と照合してレポートする。
- **なぜ作るのか**: 患者 1 人につき角度・照明の異なる複数枚から共通の HSV レンジを作る作業が、
  使い捨てスクリプトでの手動プールに依存しており再現性がなかった。これを正式ツール化する。
- **誰が使うのか**: 本プロジェクトの開発者（患者ごとの HSV 設定ファイルを準備する作業者）。
- **どこで使うのか**: ローカル開発環境（Linux, GPU あり, `uv run python` 経由）。プロジェクトルートから実行。

## 1.2 用語定義

- **クロマ画素**: ROI 内で `S >= sat_min` かつ `V >= val_min` を満たす有彩色画素（既存 `extract_chroma_hsv` の定義）。
- **プール方式**: 入力した全画像の胴体 ROI から抽出したクロマ画素を 1 つの配列に結合し、
  その結合配列に対して循環統計で 1 セットの HSV レンジを提案する方式。
- **胴体 ROI**: HALPE26 胴体 4 点（5/6/11/12）から構築する軸並行最小矩形（既存 `build_keypoint_rect_roi`）。
  構築失敗時は画像全体へフォールバック（既存 `build_torso_roi`）。
- **単一画像モード**: 入力画像が 1 枚のときの動作。feat-054 完了時点の挙動と完全一致させる。
- **複数画像モード**: 入力画像が 2 枚以上のときの動作。本案件で新規に追加する。
- **pink_ratio**: あるレンジ集合で ROI 内のマスク画素が ROI 全画素に占める比率（既存 `compute_ratio_for_ranges`）。
- **閾値**: 各画像の pooled pink_ratio が「満たした（PASS）」と判定する基準値。判定は厳密大なり
  `pink_ratio > 閾値` で行い、**閾値ちょうど（`==`）は FAIL** とする。CLI `--threshold`、デフォルト 0.03。
- **対象テストデータ**: `testdata/E0014/E0014_01.png` / `E0014_02.png` / `E0014_03.png` の 3 枚（本案件の検証に使う）。
- 本書の用語は機能設計書・コード内でも同じ語を使う。

## 1.3 機能要求一覧

### FR-001: 複数画像入力（後方互換）
- **概要**: positional 引数を 1 枚以上の画像パス（`nargs='+'`）に拡張する。1 枚指定時は
  単一画像モードとして feat-054 完了時点の挙動を完全に維持する。
- **入力**: 1 個以上の画像ファイルパス（コマンドライン positional）。
- **出力**: 画像枚数に応じて単一画像モード / 複数画像モードに分岐（FR-002〜FR-005）。
- **受け入れ基準**:
  - AC-001-1: 画像 1 枚を指定したときの PNG・JSON・stdout が、本改修前（feat-054）の出力と一致する
    （`git stash` で改修前バイナリと突き合わせ、`testdata/E0014/E0014_01.png` で PNG 以外は完全一致、
    JSON はバイト一致、stdout は推奨レンジ・ratio 行が一致）。
  - AC-001-2: 画像 2 枚以上を指定すると複数画像モードに入り、全画像が推論・ROI 抽出される。

### FR-002: プール方式による単一 HSV レンジ提案（複数画像モード）
- **概要**: 全入力画像の胴体 ROI からクロマ画素を抽出し、H/S/V を画像横断で結合した配列に対し、
  既存 feat-052 の循環統計（色相環またぎ対応）で 1 セットの推奨 `FIXED_HSV_RANGES` を提案する。
- **入力**: 各画像の胴体 ROI（BGR）。`--sat-min`/`--val-min`/`--percentile`/`--kpt-conf-min`/`--min-roi-area`。
- **出力**: 推奨レンジ（list of `((H_lo,S_lo,V_lo),(H_hi,255,255))`、1〜2 本）、S 下限、V 下限を stdout に表示。
- **受け入れ基準**:
  - AC-002-1: 対象テストデータ 3 枚（`E0014_01.png` / `E0014_02.png` / `E0014_03.png`）を入力すると、
    推奨レンジが算出され stdout に表示される。
  - AC-002-2: H の色相環またぎ（赤・ピンク）が 2 本レンジに分割されて提案される
    （既存 `propose_hsv_ranges` と同一のまたぎロジック）。
  - AC-002-3: 全画像でクロマ画素が 0 のときは推奨レンジを算出せず `[WARN]` を表示する。

### FR-003: 閾値検証レポート（複数画像モード）
- **概要**: 提案レンジを各画像の ROI に適用して pink_ratio を計算し、画像ごとに値と PASS/FAIL
  （`> 閾値` で PASS）を表示する。全画像中の最小 ratio を表示し、最小 ratio が閾値以下なら `[WARN]` と
  対処方針（`--percentile` を下げてレンジを広げる）を提示する。
- **入力**: FR-002 の推奨レンジ、各画像 ROI、`--threshold`（float, `[0.0, 1.0]`, デフォルト 0.03）。
- **出力**: 画像ごとの `ratio` と `[OK]`/`[NG]`、`min ratio`、判定（`ALL PASS`/`SOME FAIL`）を stdout に表示。
- **受け入れ基準**:
  - AC-003-1: 対象テストデータ 3 枚で各画像の ratio と最小 ratio が表示され、最小 ratio が `> 0.03` のとき
    `ALL PASS` と表示される。
  - AC-003-2: 閾値を `--threshold 0.7` のように上げて最小 ratio がそれ以下になるとき、`SOME FAIL` と
    `[WARN]`（`--percentile` を下げる旨）が表示される。プログラムは exit 0 で正常終了する（エラー終了しない）。
    判定は `pink_ratio > 閾値` の厳密大なりで、閾値ちょうどは FAIL とする。

### FR-004: 画像ごとの可視化 PNG 出力（複数画像モード）
- **概要**: 入力画像ごとに 1 枚、その画像の入力+ROI 枠・現状マスク・提案（プール）マスク・H/S/V
  ヒストグラムを描いた PNG を出力する。既存 `render_analysis_png` を再利用する。
- **入力**: 各画像、その ROI、共通の提案レンジ。
- **出力**: 画像ごとに `<image_stem>_color_analysis.png`（既存命名規則）。
- **受け入れ基準**:
  - AC-004-1: 入力 N 枚に対し PNG が N 枚出力され、各 PNG の proposed マスクは共通のプール提案レンジで描かれる。
  - AC-004-2: いずれかの PNG 保存に失敗した場合、当該 PNG の不完全ファイルは残さず `[ERROR]` で exit 1。

### FR-005: 単一の統合 HSV 設定 JSON 出力（複数画像モード）
- **概要**: プール提案レンジを feat-053 互換スキーマ（`fixed_hsv_ranges` + `min_pink_ratio`）の
  1 個の JSON ファイルに書き出す。整形は `scripts/conf/*.json` と同じ compact 形式（1 レンジ = 1 行）。
- **入力**: プール提案レンジ。`--json-out`（省略時 `<first_image_stem>_pooled_hsv_config.json`）。
- **出力**: 1 個の JSON ファイル。`min_pink_ratio` は `postprocess_pink_id.MIN_PINK_RATIO`（0.03）固定。
- **受け入れ基準**:
  - AC-005-1: 出力 JSON は `postprocess_pink_id.load_hsv_config()` でエラーなく読み込め、
    `fixed_hsv_ranges` と `min_pink_ratio` の 2 キーのみを持つ。
  - AC-005-2: 推奨レンジが空（全画像クロマ 0）のときは JSON を出力せず `[WARN]` を表示する。
  - AC-005-3: 対象テストデータ 3 枚から生成した JSON を `--hsv-config` に渡して `load_hsv_config()` で
    読み込んだレンジが、stdout に表示された推奨レンジと整数値まで一致する。

## 1.4 非機能要求

- **パフォーマンス**: モデルロードは 1 回のみ。推論は画像枚数に線形。`testdata/E0014/` 3 枚で
  GPU 実行時 60 秒以内（モデルロード含む）に完了する。
- **対応環境**: Linux、CUDA 対応 GPU（`--device cuda:0` デフォルト）。`uv run python` 経由で実行。
- **信頼性**: 入力画像が 1 枚でも読み込めない、または推論結果が空の場合は `[ERROR]` で exit 1（fail fast）。
  途中まで書いた PNG/JSON の不完全ファイルは残さない。
- **後方互換**: 単一画像モードの出力（PNG/JSON/stdout）は feat-054 完了時点と一致させる（FR-001 AC）。

## 1.5 制約条件

- **使用必須**: 既存 `mmpose` (0.24.0)・既存 ViTPose++ モデル（WB/AIC）・`merge_halpe26.py`・
  `postprocess_pink_id.py`。これらは無変更で再利用する。
- **新規ライブラリ追加禁止**: 既存依存（cv2, numpy, matplotlib）のみで実装する。
- **既存スクリプト無変更**: `merge_halpe26.py` / `postprocess_pink_id.py` は変更しない。
- **実行方法**: `uv run python scripts/analyze_clothing_color.py ...`（python/pip 直接実行禁止）。

## 1.6 優先順位（MoSCoW）

- **Must**: FR-001（後方互換）, FR-002（プール提案）, FR-005（統合 JSON 出力）
- **Should**: FR-003（閾値検証レポート）, FR-004（画像ごと PNG）
- **Could**: なし
- **Won't（本案件では実装しない）**:
  - union 方式の提案、`--method` 切替（プール方式に一本化）
  - 閾値未達時の percentile 自動拡幅（レポートのみ）
  - 複数画像を 1 枚に並べた統合 PNG
- **MVP 範囲**: FR-001 + FR-002 + FR-005（複数画像から単一 JSON を生成できること）。
