# feat-060 要求仕様書: 静止画1枚のポーズ推定診断ツール

## 1.1 プロジェクト概要

- **何を作るのか**: 1枚の静止画を入力とし、(A) YOLO11x による person 検出の成否と、
  (B) 画像全体を1つの BB として ViTPose（WholeBody + AIC）に流したときの HALPE26
  キーポイント推定の成否を、テキストと可視化 PNG で並べて出力する CLI 診断ツール
  `scripts/diagnose_pose.py`。
- **なぜ作るのか**: モノクロ・遮蔽の多い静止画でパイプラインがキーポイントを出力しない
  事象が報告された。原因が「YOLO の検出失敗」か「ViTPose 自体の推定失敗」かを切り分ける
  手段が現状ない。本ツールは検出経路と検出非依存経路を同時に観測し原因を一意化する。
- **誰が使うのか**: 本プロジェクト開発者（パイプラインのデバッグ・原因切り分け担当）。
- **どこで使うのか**: プロジェクトルートから `uv run python scripts/diagnose_pose.py <画像>`
  で実行する。GPU（CUDA）またはCPUで動作する Linux 環境。

## 1.2 用語定義

| 用語 | 定義 |
|------|------|
| YOLO検出経路 | YOLO11x（`checkpoints/yolo11x.pt`）で入力画像から person クラスの BB を検出する処理 |
| 全画像1BB経路 | 入力画像全体 `[0, 0, W, H]` を1つの BB として ViTPose（WB+AIC）に与え HALPE26 を推定する処理。YOLO検出に依存しない |
| HALPE26 | 本プロジェクトのターゲット 26 キーポイント定義（CLAUDE.md 参照） |
| キーポイント confidence | HALPE26 各点の3列目スコア（float, [0.0, 1.0]） |
| 検出成功 | YOLO検出経路で person BB が1個以上、かつ `bbox_thr` 以上の score で得られること |

機能設計書・コード内でも本表の用語を用いる。

## 1.3 機能要求一覧

### FR-001: YOLO検出経路の実行と結果出力（Must）

- **機能名**: YOLO11x による person 検出と検出結果のテキスト出力
- **概要**: 入力画像を YOLO11x に通し、person クラスの BB を検出する。
  `bbox_thr`（既定 0.3）以上の score を持つ BB の個数と、各 BB の
  `[x1, y1, x2, y2, score]` を標準出力に列挙する。閾値未満の BB も「閾値未満で除外」
  として個数のみ報告する。
- **入力**: 画像ファイルパス（位置引数）、`--bbox-thr`（float, [0.0, 1.0], 既定 0.3）、
  `--device`（既定 `cuda:0`）
- **出力**: 標準出力に以下を出力する:
  - 検出 person BB 総数（閾値適用前）
  - `bbox_thr` 以上の BB 個数と各 BB の `[x1, y1, x2, y2, score]`（score 降順）
  - 閾値未満で除外した個数
  - 結論行: `[RESULT] YOLO detection: SUCCESS (N boxes)` または
    `[RESULT] YOLO detection: FAILED (0 boxes >= thr)`
- **受け入れ基準**:
  - AC-001-1: person を含む画像で SUCCESS と検出 BB 一覧が出力される
  - AC-001-2: person を含まない（または検出されない）画像で FAILED が出力され、
    プロセスは異常終了せず後続の FR-002 へ進む
  - AC-001-3: 検出が0個でも例外を投げずに正常終了（exit 0）する

### FR-002: 全画像1BB経路の実行と結果出力（Must）

- **機能名**: 画像全体1BB での ViTPose 推論と HALPE26 confidence 出力
- **概要**: 入力画像全体 `[0, 0, W, H, 1.0]` を1つの BB として WB モデル・AIC モデルに
  与え、`merge_to_halpe26` で HALPE26 (26, 3) を得る。各点の confidence と、
  `--kpt-thr`（既定 0.3）を超える有効点数を出力する。
- **入力**: 画像ファイルパス（FR-001 と共通）、`--kpt-thr`（float, [0.0, 1.0], 既定 0.3）、
  `--device`
- **出力**: 標準出力に以下を出力する:
  - HALPE26 全26点の `index: name = (x, y, conf)`（小数3桁）
  - `--kpt-thr` を超える（`conf > kpt_thr`）有効点数 `M/26`（既存 `draw_halpe26` の
    描画判定 `>` と統一する。境界値 `conf == kpt_thr` は有効点に含めない）
  - 結論行: `[RESULT] ViTPose fullframe: SUCCESS (M/26 kpts > thr)` または
    `[RESULT] ViTPose fullframe: FAILED (推論結果が空 or 有効点0 or 推論例外)`
- **受け入れ基準**:
  - AC-002-1: 人物が写る画像で HALPE26 26点と有効点数が出力される
  - AC-002-2: ViTPose の推論結果が空（WB または AIC が0件）の場合、`sys.exit(1)` せず
    FAILED を出力して正常終了する（FR-001 既存実装の `estimate_halpe26_fullframe` は
    空時に exit するため、本ツールでは流用せず診断向けに分離実装する）
  - AC-002-3: 全点が `kpt-thr` 以下でも例外を投げず FAILED を出力して exit 0 する

### FR-003: 可視化 PNG 出力（Should）

- **機能名**: 検出経路・推論経路の可視化合成 PNG 保存
- **概要**: 1枚の PNG に2パネルを並べて保存する:
  - 左: 入力画像 + YOLO 検出 BB（`bbox_thr` 以上を緑枠、score を枠脇に表示）
  - 右: 入力画像 + 全画像1BB 枠（シアン）+ HALPE26 スケルトン（`kpt-thr` を超える点・骨）
- **入力**: `--out`（PNG出力パス, 既定 `<image_stem>_pose_diagnostic.png`）
- **出力**: PNG ファイル1個。保存パスを標準出力にログする。
- **受け入れ基準**:
  - AC-003-1: 既定パスまたは `--out` 指定パスに PNG が1個生成される
  - AC-003-2: YOLO 検出0個でも右パネル（全画像1BB推論）は描画され PNG が生成される
  - AC-003-3: PNG 保存に失敗した場合、書きかけファイルを残さず（存在すれば削除）
    `[ERROR]` をログして exit 1 する

### FR-004: 総合判定の出力（Should）

- **機能名**: 切り分け結論の出力
- **概要**: FR-001 と FR-002 の結果を踏まえ、原因の切り分け結論を1〜2行で出力する。
- **入力**: FR-001 / FR-002 の結果（内部）
- **出力**: 標準出力に以下のいずれかを出力する:
  - YOLO=FAILED かつ ViTPose=SUCCESS → `[VERDICT] 原因は YOLO 検出失敗の可能性が高い（ViTPose は全画像1BBで推定成功）`
  - YOLO=SUCCESS かつ ViTPose=SUCCESS → `[VERDICT] 両経路とも成功。パイプライン側の閾値/連携を確認のこと`
  - ViTPose=FAILED → `[VERDICT] ViTPose 自体が当該画像で推定失敗（YOLO の成否によらずポーズが出ない）`
- **受け入れ基準**:
  - AC-004-1: 上記3分岐がそれぞれの条件で正しく出力される

## 1.4 非機能要求

- **パフォーマンス**: 画像1枚（960x520 程度）の処理がモデルロード込みで GPU 上 60 秒以内
  に完了する。応答時間の厳密な保証は不要（診断用途・対話実行）。
- **対応環境**: Linux、Python 3.10.16、CUDA GPU または CPU。`--device cpu` で CPU 実行可。
- **信頼性**: エラーは2分類で扱う。
  - **致命エラー（exit 1）**: 入力画像が読めない・モデルチェックポイント不在やロード失敗・
    PNG保存失敗・CUDA OOM（`torch.cuda.OutOfMemoryError`）・`--device` 不正。`[ERROR]` を
    ログして exit 1 する。
  - **推論失敗（exit 0、FAILED記録）**: WB/AIC 推論が空、または推論中に上記以外の例外が発生
    した場合は、その経路を FAILED として記録し、ツール自体はクラッシュさせず exit 0 で
    続行・総合判定まで出す（FR-002 AC-002-2、切り分け結論を必ず出すため）。
- **セキュリティ**: 対象外。

## 1.5 制約条件

- **使用必須**: 既存の `merge_halpe26.py`（WB/AIC設定・`merge_to_halpe26`・`draw_halpe26`・
  `draw_bbox`）、`ultralytics`（YOLO11x）、MMPose（`inference_top_down_pose_model`）を
  再利用する。
- **既存ファイル変更禁止**: `merge_halpe26.py`、`analyze_clothing_color.py`、
  `run_halpe26_pipeline_yolo11.py`、`postprocess_pink_id.py` は変更しない。新規ファイル
  `scripts/diagnose_pose.py` のみ追加する。
- **モデルチェックポイント**: `checkpoints/yolo11x.pt`、WB/AIC チェックポイント（`merge_halpe26`
  が定義済み）が存在する前提。
- **オフライン**: ネットワーク不要（ローカルチェックポイントのみ）。
- **入力色空間**: OpenCV `imread` は BGR 3ch で読み込む。モノクロ画像（1ch保存）でも
  `imread` は既定で 3ch（BGR、全ch同値）として読み込むため、3ch化の明示処理は本案件の
  対象外とする（備考: 入力が 3ch でない異常時は機能設計書のエラーハンドリングで扱う）。

## 1.6 優先順位

- **Must**: FR-001（YOLO検出成否）、FR-002（全画像1BB推論成否）。この2つが MVP であり、
  原因切り分けの核。
- **Should**: FR-003（可視化PNG）、FR-004（総合判定）。
- **Won't（今回やらない）**: 複数画像の一括処理、動画入力、YOLO 検出 BB を使った
  トップダウン推論の精度評価、HSVレンジ提案（feat-052 系の責務）。

MVP 範囲: FR-001 + FR-002（テキスト出力のみ）。FR-003 / FR-004 を加えて完成形とする。
