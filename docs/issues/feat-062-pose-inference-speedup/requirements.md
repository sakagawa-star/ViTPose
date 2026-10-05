# feat-062 要求仕様書: 2 パス推論構成のままポーズ推定を高速化（backbone fp16 + CUDA Graph）

## 1.1 プロジェクト概要

- **何を作るのか**: `scripts/run_halpe26_pipeline_yolo11.py` の WholeBody / AIC の 2 つの
  ViTPose-H モデルについて、(1) backbone を fp16 で実行し、(2) backbone の forward を
  CUDA Graph でキャプチャ・再生する高速化機構を追加する。両機構は既定で有効とし、
  `--no-pose-fp16` / `--no-cuda-graph` で個別に無効化できる。両方無効時は改修前と同一の
  推論経路で処理し、出力は座標・bbox が一致する（confidence は GPU 推論の実行間の揺れの範囲で一致）。高速化ロジックは新規モジュール `scripts/pose_accel.py` に置き、
  パイプラインから import する。
- **なぜ作るのか**: 調査（README「調査結果」節）で、パイプライン時間の 86% が WholeBody / AIC
  推論、その 95% が ViT-H backbone forward（fp32、1 回 30.6 ms、1 BB あたり flip test 込み
  4 回）であると判明した。backbone を fp16 化すると 1 回 14.8 ms（出力は fp32 と同等）、
  さらに CUDA Graph を併用すると 8.4 ms になり、推論のみの条件で 105.7 ms/frame → 42.2 ms/frame
  （2.50 倍）を確認した。CUDA Graph が必要な理由は、fp16 では GPU の計算時間（9.3 ms）に対して
  CPU 側のカーネル発行時間（4.2 ms）の余裕が小さく、CPU が省電力状態のとき発行が GPU を律速
  してしまうため（連続実行 9.1 ms が パイプライン内では 14.8 ms に悪化）。CUDA Graph は forward
  全体を 1 回の発行で再生するため、CPU 側の速度に影響されない。
- **誰が使うのか**: 本プロジェクト開発者（パイプライン実行担当）。
- **どこで使うのか**: プロジェクトルートから
  `uv run python scripts/run_halpe26_pipeline_yolo11.py --video <動画>` で実行する。
  CUDA GPU（RTX 5060 Ti 16 GB で検証）の Linux 環境。CPU 実行時は両機構を自動で無効化する。

## 1.2 用語定義

| 用語 | 定義 |
|------|------|
| backbone | ViTPose-H モデルの画像特徴抽出部（`model.backbone`、`mmpose/models/backbones/vit.py` の `ViT`）。入力 `(N, 3, 256, 192)` float32、出力 `(N, 1280, 16, 12)` float32 |
| head | backbone の出力をヒートマップ `(N, K, 64, 48)` に変換する部分（`model.keypoint_head`）。K は WholeBody 133 / AIC 14 |
| decode | ヒートマップから座標・confidence を求める CPU 後処理（`keypoint_head.decode`） |
| flip test | 元画像と左右反転画像の両方を推論し平均する MMPose の設定（`test_cfg.flip_test=True`）。本案件では変更しない。1 BB あたり backbone は 2 回呼ばれる |
| fp16 | 16 ビット浮動小数点（`torch.float16`）。本案件では backbone の重みと入力のみ fp16 とし、head と decode は fp32（`torch.float32`）のまま |
| eager 実行 | CUDA Graph を使わず、PyTorch が演算ごとにカーネルを発行する通常の実行 |
| CUDA Graph | 一連の GPU カーネル発行を 1 回記録（キャプチャ）し、以後は記録を 1 回の発行で再実行（再生）する CUDA の仕組み。PyTorch では `torch.cuda.CUDAGraph` / `torch.cuda.graph` |
| キャプチャ | CUDA Graph の記録。入力形状ごとに 1 回必要。固定アドレスの入力・出力テンソル（静的バッファ）を伴う |
| 再生 | キャプチャ済み CUDA Graph の実行。静的入力バッファに入力をコピー → `graph.replay()` → 静的出力バッファから結果をコピーして返す |
| 入力形状 | backbone 入力テンソルの shape `(N, 3, H, W)`。N はそのフレームの BB 数、H×W は設定の `image_size`（256×192）で固定。したがって形状の違いは N の違いのみ |
| max_batch | CUDA Graph を使う BB 数 N の上限（既定 8）。N がこれを超える呼び出しは eager 実行 |
| ベースライン出力 | 改修前コード（または `--no-pose-fp16 --no-cuda-graph`）で得た JSON / 動画 |
| 確信点 | ベースライン出力で confidence > 0.3 のキーポイント。出力差分の評価母集団 |

機能設計書・コード内でも本表の用語を用いる。

## 1.3 機能要求一覧

### FR-001: backbone の fp16 実行（Must）

- **機能名**: backbone fp16 化（`--pose-fp16` / `--no-pose-fp16`）
- **概要**: WholeBody・AIC 両モデルの backbone の重みを fp16 に変換し、backbone 入力を
  fp32 → fp16 に変換して forward し、出力を fp16 → fp32 に変換して head に渡す。head・decode・
  flip test・前処理は無変更。CLI `--pose-fp16`（`argparse.BooleanOptionalAction`、既定 True）。
  `--device cpu` のときは指定にかかわらず無効（INFO ログ 1 行）。
- **入力**: `--pose-fp16` / `--no-pose-fp16`、解決済みデバイス（`cuda:0` または `cpu`）
- **出力**: backbone 出力 `(N, 1280, 16, 12)` float32（内部）。起動ログに有効/無効を表示（FR-004）
- **受け入れ基準**:
  - AC-001-1: `--pose-fp16 --no-cuda-graph --mode json` で camSony1_S（900 フレーム）を処理した
    JSON を、ベースライン出力と比較し、確信点のうち座標差（ユークリッド距離）が 2 px を超える
    点の割合が 2% 以下、確信点の confidence の符号付き平均差の絶対値が 0.001 以下、全点の
    confidence の最大絶対差が 0.05 以下である（調査実測: 0.6% / 0.2%、平均差 −2e-5、最大差 0.0092）。
    比較はフレームごとに people を出現順で対応付け、people 数がベースラインと異なるフレームは
    比較から除外して件数を報告する。除外フレームは 900 フレーム中 9 フレーム（1%）以下であること
  - AC-001-2: camSony1_S 900 フレーム `--mode both --profile` で、WholeBody と AIC の Avg(ms) の和が
    65 ms/frame 以下である（ベースライン実測 2026-10-02: WholeBody 50.8 + AIC 49.7 = 100.5 ms/frame の 65%。
    調査の推論のみ計測では fp16 で 46.3 / 91.6 = 51%）
  - AC-001-3: `--device cpu --pose-fp16` で起動したとき、fp16 は適用されず
    `[INFO] Pose accel disabled on CPU device` が出力され、推論は fp32 で完走する

### FR-002: backbone の CUDA Graph 再生（Must）

- **機能名**: CUDA Graph 化（`--cuda-graph` / `--no-cuda-graph`、`--cuda-graph-max-batch`）
- **概要**: backbone の forward を入力形状ごとにキャプチャし、以後の同形状の呼び出しは再生で
  処理する。起動時（モデル初期化直後）に N=1 の形状を事前キャプチャする。N=2 以上の形状は
  その形状が初めて現れた呼び出しでキャプチャする（遅延キャプチャ）。N が `--cuda-graph-max-batch`
  （int、1 以上、既定 8）を超える呼び出しはキャプチャせず eager 実行する。キャプチャが
  例外（`torch.cuda.OutOfMemoryError` を含む `RuntimeError`）で失敗した場合は致命エラーとし、
  `[ERROR] Pose accel (<name>): CUDA Graph capture failed for shape (...): <例外>. Use --no-cuda-graph`
  を出力して exit 1 する（キャプチャ失敗後は PyTorch のストリーム状態が保証されないため、
  eager へのフォールバックは行わない）。CLI `--cuda-graph`（`BooleanOptionalAction`、既定 True）。
  `--device cpu` のときは無効（FR-001 と同じ INFO ログ）。fp16 の有無に依存せず単独でも動作する。
- **入力**: `--cuda-graph` / `--no-cuda-graph`、`--cuda-graph-max-batch N`、backbone 入力テンソル
- **出力**: backbone 出力（eager 実行と同じ型・形状。静的出力バッファのコピーを返す）
- **受け入れ基準**:
  - AC-002-1: `--pose-fp16 --cuda-graph --mode json` の JSON と `--pose-fp16 --no-cuda-graph`
    の JSON を camSony1_S 900 フレームで比較し、全 person・全 26 点の座標の最大絶対差が 0.01 px 以下、
    confidence の最大絶対差が 0.001 以下である（調査実測: 座標最大差 2e-5 px）。people 数の対応付けと
    除外規則は AC-001-1 と同じ（除外は 9 フレーム以下）
  - AC-002-2: camSony1_S 900 フレーム `--mode both --profile`（既定設定）で、WholeBody と AIC の
    Avg(ms) の和が 45 ms/frame 以下である（ベースライン 100.5 ms/frame の 45%。調査の推論のみ計測では
    28.2 / 91.6 = 31%）
  - AC-002-3: 起動ログに `wb` / `aic` それぞれの N=1 事前キャプチャが 1 行ずつ出力される
  - AC-002-4: 複数人が映る動画（`testdata/pexels_4441000.mp4` または `cam05520125.mp4`）で、
    N=2 以上の形状が初出したフレームで遅延キャプチャのログが出力され、処理が完走する
  - AC-002-5: `--cuda-graph-max-batch 1` で AC-002-4 と同じ動画を処理したとき、N=2 以上の呼び出しは
    eager 実行され（当該形状のキャプチャログが出ない）、`batch N > max_batch 1, eager` のログが
    形状ごとに 1 回だけ出力され、完走する
  - AC-002-6: `--cuda-graph-max-batch 0` は argparse エラー（exit 2）で起動前に弾かれる

### FR-003: 後方互換モード（Must）

- **機能名**: 両機構無効時の出力一致（改修前と同一の推論経路）
- **概要**: `--no-pose-fp16 --no-cuda-graph` を指定したとき、モデルオブジェクトに一切の変更を
  加えず（`model.backbone` の差し替えを行わず）、改修前と同一の推論経路で処理する。
- **入力**: `--no-pose-fp16 --no-cuda-graph`
- **出力**: 改修前と同一経路の JSON / 動画（座標・bbox・bbox_score は一致。confidence は fp32 GPU 推論の
  実行間の非決定性により最下位桁が揺れるため、最大絶対差 1e-4 以下を許容する）
- **受け入れ基準**:
  - AC-003-1: `--no-pose-fp16 --no-cuda-graph` で camSony1_S を処理した JSON を、改修前コード
    （`git stash` で退避して実行）の出力と比較し、全 person の座標・bbox・bbox_score が全点一致、
    かつ confidence の最大絶対差が 1e-4 以下である（people 数が異なるフレームは 0 件であること）。
    `diff -r` のバイト一致は要求しない（改修前コード同士の 2 回実行でも 900 ファイル中 28 ファイルの
    confidence が最大 5.2e-5 異なるため。README「AC-003-1 について」参照）
  - AC-003-2: 同条件で `--profile` の区分名（Read / Detection / WholeBody / AIC / Merge / Dedup /
    Draw / JSON）と出力形式が改修前と同一である

### FR-004: 起動ログとキャプチャログ（Should）

- **機能名**: 高速化設定の可視化
- **概要**: モデル初期化後に有効な設定を 1 行で表示する。キャプチャ成功・失敗・max_batch 超過を
  それぞれ 1 行ログする（超過は形状ごとに初回のみ）。
- **入力**: 解決済み設定値、キャプチャ結果
- **出力**: 標準出力。書式は設計書 1.8 で定義
- **受け入れ基準**:
  - AC-004-1: 既定起動で `Pose accel: fp16=True, cuda_graph=True, max_batch=8` が 1 行出力される
  - AC-004-2: `--no-pose-fp16 --no-cuda-graph` で `Pose accel: fp16=False, cuda_graph=False, max_batch=8`
    が出力される（モデルは無変更、FR-003）

### FR-005: 高速化ロジックの共通モジュール化（Should）

- **機能名**: `scripts/pose_accel.py`
- **概要**: fp16 化と CUDA Graph 化を、MMPose の `TopDown` モデルを受け取って `model.backbone` を
  ラッパーモジュールに差し替える関数 `accelerate_pose_model` として実装し、
  `run_halpe26_pipeline_yolo11.py` から import する。MMPose 本体（`mmpose/`）は変更しない。
  他スクリプト（`diagnose_pose.py` / `analyze_clothing_color.py` / `run_halpe26_pipeline.py` /
  `run_halpe26_pipeline_yolox.py`）は本案件では変更しない。
- **入力**: `TopDown` モデル、fp16 / cuda_graph / max_batch / name
- **出力**: 差し替え済みモデル（破壊的更新）、戻り値は適用有無の bool
- **受け入れ基準**:
  - AC-005-1: `uv run python -c "from scripts.pose_accel import accelerate_pose_model"` 相当で
    import でき、`mmpose/` 配下に変更がない（`git diff --stat mmpose/` が空）

## 1.4 非機能要求

- **パフォーマンス（測定条件）**: 動画 `testdata/camSony1_S.mp4`（900 フレーム）、
  `--mode both --profile`、同一マシン（RTX 5060 Ti）、他の GPU ジョブなし、各条件 1 回実行、
  `--profile` 表の値で比較する。ベースライン（改修前コード、2026-10-02 実測）: 合計 105.7 s、8.5 fps、
  WholeBody 50.8 ms/frame、AIC 49.7 ms/frame、Detection 14.5 ms/frame、Draw 1.8 ms/frame、
  JSON 0.2 ms/frame、Read 0.4 ms/frame。
  - Must: 既定設定で WholeBody + AIC の Avg(ms) の和が 45 ms/frame 以下（AC-002-2）。
  - Should: 既定設定で全体 fps が 17.0 以上（ベースライン 8.5 fps の 2.0 倍。Detection 14.5 ms と
    Draw/JSON/Read 2.4 ms は変わらないため、WB+AIC が 30 ms なら合計約 47 ms/frame = 21 fps の見込み）。
- **GPU メモリ**: 既定設定（max_batch 8）で WB/AIC の N=1〜8 全 16 形状をキャプチャした状態でも、
  `nvidia-smi` の `memory.used` が 5.0 GB 以下であること。実測（2026-10-02、fp16 backbone、
  16 グラフを順次キャプチャ）: PyTorch reserved 3.92 GB（モデル読み込み直後 2.87 GB から +1.05 GB、
  allocated は +0.21 GB）、`nvidia-smi` 4.59 GB。ベースライン（fp32、2 モデル読み込み直後）は
  PyTorch reserved 5.00 GB / `nvidia-smi` 5.42 GB であり、改修後はこれを下回る。CUDA Graph のプールは解放されず
  単調増加するため、処理終了直前の `nvidia-smi` 値がグラフ由来メモリのピークになる。
- **対応環境**: Linux、Python 3.10.16、torch 2.11.0+cu128、CUDA GPU。CPU 実行は両機構を自動無効化
  して従来通り動作する。
- **信頼性**: キャプチャ失敗（OOM を含む）は `[ERROR]` + exit 1 で早期に終了し、利用者は
  `--no-cuda-graph` で回避する（feat-060/061 と同じ致命エラー規約）。出力 JSON の形式・フィールドは無変更。
- **後方互換**: `--no-pose-fp16 --no-cuda-graph` で改修前と同一の推論経路。座標・bbox は一致し、confidence は
  最大絶対差 1e-4 以下（FR-003、AC-003-1）。

## 1.5 制約条件

- **改修対象**: 新規 `scripts/pose_accel.py`、改修 `scripts/run_halpe26_pipeline_yolo11.py`、
  文書 `scripts/README.md` / `CLAUDE.md`。`mmpose/` と `configs/` は変更しない（flip test 設定・
  `post_process` 設定も変更しない）。
- **使用必須**: `torch.cuda.CUDAGraph` と `torch.cuda.graph`（torch 2.11 標準 API）。
  `torch.compile` は使わない（コンパイル時間と mmcv 1.7.2 との互換リスクのため）。
- **新規ライブラリ**: なし。
- **モデル差し替えの範囲**: `model.backbone` のみ。`model.keypoint_head`、`model.test_cfg`、
  `model.cfg` は触らない。
- **ドメイン前提**: 1 フレームの BB 数は通常 1、最大でも数個。max_batch 既定 8 はこの前提による。

## 1.6 優先順位

- **Must**: FR-001（fp16）、FR-002（CUDA Graph）、FR-003（後方互換）。この 3 つが MVP。
- **Should**: FR-004（ログ）、FR-005（共通モジュール化）。
- **Won't（今回やらない）**: flip test の無効化（利用者判断で不採用、調査結果 §5）、
  複数フレームのバッチ化、head の fp16 化、YOLO11x の高速化、他パイプライン・他スクリプトへの
  適用、CPU ガバナ等の環境設定変更、`torch.compile`。

MVP 範囲: FR-001 + FR-002 + FR-003。FR-004 + FR-005 を加えて完成形とする。

## 変更履歴

- 2026-10-05: AC-003-1 を「`diff -r` 差分 0」から「座標・bbox・bbox_score が全点一致、かつ confidence の最大絶対差が 1e-4 以下」に改定（利用者承認）。
  fp32 の GPU 推論に実行間の非決定性があり、改修前コード同士でもバイト一致が成立しないため。
  関連して 1.1 概要・FR-003 の機能名と出力・1.4 後方互換の記述を現行基準に合わせて更新。
