# feat-061 要求仕様書: YOLO 検出ゼロ時の固定 ROI フォールバック

## 1.1 プロジェクト概要

- **何を作るのか**: `scripts/run_halpe26_pipeline_yolo11.py` に、YOLO11x が
  `bbox_thr` 以上の person BB を 1 件も返さなかったフレームに限り、CLI で指定した固定座標
  ROI を 1 個の BB として ViTPose（WB+AIC）に流すフォールバック機構を追加する。
  既定無効、`--fallback-roi` 指定時のみ有効。
- **なぜ作るのか**: 臥位・遮蔽（シーツで肩から上のみ可視）の姿勢で YOLO11x（COCO 学習）が
  person を検出できず、トップダウン方式のため当該フレームの ViTPose 推論ごとスキップされる。
  `diagnose_pose.py`（feat-060）で原因は YOLO 検出失敗（`--bbox-thr 0.01` でも検出ゼロ）と
  確定済み。検出器差し替え・再学習は時間的制約で不可のため、1 人前提のドメイン特性を活かし
  固定 ROI を ViTPose に流して当該フレームのポーズ出力を回復する。
- **誰が使うのか**: 本プロジェクト開発者（パイプライン実行担当）。
- **どこで使うのか**: プロジェクトルートから
  `uv run python scripts/run_halpe26_pipeline_yolo11.py --video <動画> --fallback-roi x1 y1 x2 y2`
  で実行する。GPU（CUDA）または CPU の Linux 環境。

## 1.2 用語定義

| 用語 | 定義 |
|------|------|
| 検出ゼロフレーム | YOLO11x の person BB を、Ultralytics 既定 `conf`（0.25）適用後さらに `bbox_thr` で前段フィルタした結果、残った BB が 0 件のフレーム。本案件では YOLO 呼び出しの `conf` を変更せず既存挙動（既定 0.25）のまま用いる |
| フォールバック ROI | `--fallback-roi x1 y1 x2 y2` で与える固定矩形（整数 4 値、画像座標、`x1<x2` かつ `y1<y2`） |
| フォールバック注入 | 検出ゼロフレームで、フォールバック ROI を score 付き BB 1 個として `person_results` に与えること |
| フォールバック score | フォールバック注入 BB の信頼度（`bbox_score`）。検出由来ではなく `--fallback-score`（既定 1.0）で与える固定値 |

機能設計書・コード内でも本表の用語を用いる。

## 1.3 機能要求一覧

### FR-001: フォールバック ROI の CLI 指定（Must）

- **機能名**: `--fallback-roi` / `--fallback-score` 引数の追加
- **概要**: フォールバック ROI を `--fallback-roi x1 y1 x2 y2`（整数 4 値、`nargs=4`）で
  受け取る。未指定（既定 `None`）のときフォールバック機構は完全に無効。
  フォールバック注入 BB の score は `--fallback-score`（float, [0.0, 1.0], 既定 1.0）で与える。
- **入力**: `--fallback-roi`（int×4, 既定 None）、`--fallback-score`（float, 既定 1.0）
- **出力**: パース結果（内部）。指定時は起動ログに ROI と score を 1 行出力する。
- **受け入れ基準**:
  - AC-001-1: `--fallback-roi` 未指定時、検出・推論・出力が改修前と完全一致する
    （既存動画で出力 JSON / 動画が `diff` 差分 0）
  - AC-001-2: `--fallback-roi 100 50 400 300` 指定時、起動ログに
    `Fallback ROI: [100, 50, 400, 300], score: 1.0` 相当が 1 行出力される

### FR-002: フォールバック ROI 座標の検証（Must）

- **機能名**: ROI 座標の妥当性チェック
- **概要**: 検証は 2 段で行う。**(1) 基本検証（モデルロード前）**: `--fallback-roi` 指定時、
  4 値が `x1 < x2` かつ `y1 < y2` かつ全値 `>= 0` を満たすか検証する。違反時は `[ERROR]` を
  ログして exit 1 する。重いモデルロード・GPU 初期化より前に実行し、ROI エラーが
  モデル読み込み失敗や CUDA OOM に隠されないようにする。**(2) クリップ検証（動画サイズ確定後）**:
  ROI が `[0, 0, W, H]` をはみ出す場合は各辺を画像内にクリップし、`[WARN]` を 1 行出力する
  （クリップ後に `x1 < x2` かつ `y1 < y2` が崩れる場合は `[ERROR]` exit 1）。
- **入力**: `--fallback-roi`（FR-001）、動画フレーム幅 W・高さ H
- **出力**: 正常時はクリップ済み ROI（内部）。違反時は `[ERROR]` メッセージと exit 1。
  クリップ発生時は `[WARN]` メッセージ。
- **受け入れ基準**:
  - AC-002-1: `x1 >= x2` または `y1 >= y2` または負値を含む ROI で exit 1 する
  - AC-002-2: 画像範囲をはみ出す ROI が `[0,0,W,H]` にクリップされ `[WARN]` が出力される
  - AC-002-3: クリップ後に幅または高さが 0 以下になる ROI で exit 1 する
  - AC-002-4: 不正 ROI 指定時、基本検証（非負・大小違反）もクリップ後縮退も、いずれも
    モデル初期化より前に検出され、モデル初期化に到達せず（GPU 初期化ログより前に）exit 1 する

### FR-003: 検出ゼロフレームへのフォールバック注入（Must）

- **機能名**: 検出ゼロフレームでの固定 ROI 注入
- **概要**: 各フレームで YOLO 検出 + `bbox_thr` フィルタ後に `person_results` が空の場合、
  かつ `--fallback-roi` 指定時に限り、フォールバック ROI を
  `[x1, y1, x2, y2, fallback_score]` の BB 1 個として `person_results` に設定する。
  以降の WholeBody 推論・AIC 推論・HALPE26 結合・BB 重複除去・描画・JSON 出力は既存処理を
  そのまま通す（注入 BB は 1 個のため重複除去は `n_persons >= 2` 条件に非該当で素通り）。
  検出ゼロでないフレーム、および `--fallback-roi` 未指定時は注入しない。
- **入力**: フレーム画像、`bbox_thr` フィルタ後の `person_results`、検証済みフォールバック ROI、
  フォールバック score
- **出力**: 当該フレームの HALPE26 推論結果・描画・JSON（注入 BB 由来の 1 人分）
- **受け入れ基準**:
  - AC-003-1: 検出ゼロフレームで、フォールバック ROI 由来の人物 1 人分の HALPE26 が
    JSON に出力される（`people` が 1 件、`bbox_score` がフォールバック score 値）
  - AC-003-2: YOLO が（既定 conf 適用後）`bbox_thr` フィルタ後に 1 件以上残ったフレームでは
    注入されず、検出 BB のみで処理される
  - AC-003-3: `--fallback-roi` 未指定時はどのフレームでも注入されない（AC-001-1 と整合）

### FR-004: フォールバック発動の集計ログ（Should）

- **機能名**: フォールバック発動フレーム数のサマリ出力
- **概要**: 処理全体でフォールバック注入が発動したフレーム数をカウントし、処理終了時に
  標準出力へ 1 行サマリする。
- **入力**: 各フレームの注入有無（内部カウンタ）
- **出力**: `Fallback applied to N / total_frames frames` 相当の 1 行（`--fallback-roi`
  指定時のみ出力。未指定時は出力しない）。
- **受け入れ基準**:
  - AC-004-1: `--fallback-roi` 指定時、終了ログに発動フレーム数が出力される
  - AC-004-2: `--fallback-roi` 未指定時はサマリ行を出力しない

### FR-005: フォールバック由来 person への `fallback` フィールド付与（Must）

- **機能名**: 注入 BB 由来 person への判別フラグ追加
- **概要**: フォールバック注入が発動したフレームの JSON では、注入 ROI 由来の person に
  `"fallback": true` フィールドを付与する。通常検出（YOLO 由来）の person、および
  `--fallback-roi` 未指定時の全 person には `fallback` フィールドを一切付けない
  （キーの有無で判別可能にする）。下流（Pose2Sim・`postprocess_*`）がフォールバック
  フレームを明示判別できるようにする。
- **入力**: 当該フレームがフォールバック注入フレームか否か（内部フラグ）
- **出力**: 注入フレームの `people[*]` に `"fallback": true`。非注入フレームは当該キーなし。
- **受け入れ基準**:
  - AC-005-1: フォールバック注入フレームの JSON で、person に `"fallback": true` が含まれる
  - AC-005-2: YOLO 検出 BB 由来の person、および `--fallback-roi` 未指定時の全 person に
    `fallback` キーが存在しない（AC-001-1 のバイト一致と整合）
  - AC-005-3: `fallback` フィールドは既存フィールド（`bbox` / `bbox_score` 等）に追加される
    のみで、それらの値・有無を変えない

## 1.4 非機能要求

- **パフォーマンス**: フォールバック未指定時のオーバーヘッドは実質ゼロ（フレームごとに
  `person_results` の空判定 1 回のみ追加）。指定時も追加コストは検出ゼロフレームでの
  ROI 注入 1 個分のみで、処理 fps の有意な低下を生じない。
- **対応環境**: Linux、Python 3.10.16、CUDA GPU または CPU。既存パイプラインと同一。
- **信頼性**: ROI 座標の不正・クリップ後縮退は exit 1 で早期に弾く（FR-002）。注入処理は
  検出ループ内の局所追加であり、既存の WB/AIC/dedup/draw 経路は変更しない。JSON 経路は
  `fallback_flags` の任意引数追加（FR-005）のみ行い、`--fallback-roi` 未指定時の出力は
  改修前とバイト一致する。
- **後方互換**: `--fallback-roi` 未指定時、改修前と出力がバイト一致すること（AC-001-1）。

## 1.5 制約条件

- **改修対象**: `scripts/run_halpe26_pipeline_yolo11.py`（本体）と
  `scripts/halpe26_to_openpose.py`（`halpe26_to_openpose_json` に後方互換の任意引数
  `fallback_flags` を 1 つ追加、既存 `stable_ids` 引数と同パターン）。`merge_halpe26.py`・
  `compare_dedup_methods.py`・他パイプライン（`run_halpe26_pipeline.py` /
  `run_halpe26_pipeline_yolox.py`）は変更しない。
- **使用必須**: 既存の `inference_top_down_pose_model`（`bbox_thr=None`, `format='xyxy'`）
  経路をそのまま使う。注入 BB は既存検出 BB と同じ `{'bbox': np.array([x1,y1,x2,y2,score],
  float32)}` 形式とする。
- **発動条件の限定**: フォールバックは「`bbox_thr` 以上の person BB が 0 件」のフレームに
  限る。1 件以上検出されたフレームには一切介入しない（FR-003）。
- **ドメイン前提**: 対象は 1 人前提。フォールバック ROI は 1 個のみ（複数 ROI は対象外）。

## 1.6 優先順位

- **Must**: FR-001（CLI 指定）、FR-002（座標検証）、FR-003（注入本体）、
  FR-005（`fallback` フィールド付与）。この 4 つが MVP。
- **Should**: FR-004（集計ログ）。
- **Won't（今回やらない）**: 複数フォールバック ROI、キーポイントや前フレーム BB からの
  ROI 自動推定、フォールバック BB の特別な可視化色分け（JSON フラグのみ対応、可視化は対象外）、
  他検出器版パイプラインへの展開。

MVP 範囲: FR-001 + FR-002 + FR-003 + FR-005。FR-004 を加えて完成形とする。
