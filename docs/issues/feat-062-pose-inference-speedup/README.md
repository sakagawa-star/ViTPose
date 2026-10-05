# feat-062: 2 パス推論構成のままポーズ推定を高速化

## 概要

`run_halpe26_pipeline_yolo11.py` の WholeBody + AIC の 2 パス ViTPose-H 推論を、
モデル構成（2 モデル・2 パス）を変えずに高速化する。候補施策は flip test OFF、
fp16 推論、複数フレームのクロップをまとめたバッチ推論、CPU 側後処理の見直し。
どの施策をどの順で入れるかは、本案件の調査フェーズで行う
「前処理 / forward / 後処理」の分割プロファイルの結果に基づいて決める。

## 背景

- feat-014 の実測（旧パイプライン `run_halpe26_pipeline.py`、Faster R-CNN 検出器、
  camSony1_S = 30 秒・900 フレーム）: 約 180 s、5.1 fps。
  Detection 26.7%、WholeBody 68.6 ms/frame（35.0%）、AIC 67.5 ms/frame（34.3%）。
  ポーズ推定 2 パスで約 136 ms/frame、全体の約 7 割を占める
  （出典: feat-015 requirements.md、2026-03-28 引き継ぎノート。
  feat-014 design.md の出力例の表は推定値であり根拠にしない）。
  検出器は feat-024 で YOLO11x に置換済みのため Detection の数値は現行と異なるが、
  WholeBody / AIC 各約 68 ms/frame は検出器に依存しない。
- ViT-H（embed_dim=1280、depth=32、約 630M パラメータ）の 256x192 入力は 192 トークンで、
  1 forward の演算量は概算 0.24 TFLOP。RTX 5060 Ti の fp32 ピーク（約 24 TFLOPS）では
  10 ms 強、fp16 Tensor Core なら数 ms が下限。現状は `flip_test=True`（設定既定、
  反転画像でもう 1 回推論）かつ fp32 なので forward だけで 20 ms 超が下限。
  実測 68 ms との差は、flip test、fp32 実行、CPU 側の前処理（affine 変換・正規化）と
  後処理（ヒートマップの argmax・座標変換）の
  いずれかに起因すると推測しているが、内訳は未計測。
- 2 パスの統合（バックボーン共有）は MoE 構造上できない。expert が全 32 ブロックの MLP に
  あり、各ブロック出力が共有部と expert 部の連結で次ブロックの attention に入るため、
  1 ブロック目以降の特徴がデータセットごとに分岐する（`mmpose/models/backbones/vit_moe.py`）。
  実運用で使う分割済みチェックポイントは `tools/model_split.py` が expert 重みを `fc2` に
  連結した各データセット専用の通常 ViT（`type='ViT'`）であり、2 つは別モデルである。
  1 パス化（HALPE 26 ヘッドの学習）は別案件で検討する。
- feat-015（WholeBody / AIC のスレッド並列）は効果なしだった（逐次 177.2 s vs 並列 177.0 s、
  推論結果は完全一致）。Python の GIL により CPU 側処理が直列化されたためと考えられ、
  当時の「GPU 飽和」という結論の裏付けにはならない可能性がある（→ 調査結果 §4 で再解釈）。

## 目標

- 推論結果（キーポイント座標・confidence）を許容誤差内に保ちつつ、ポーズ推定部分の
  処理時間を短縮する。数値目標はプロファイル結果を見て要求仕様で設定する。
- 出力 JSON 形式・下流スクリプト（postprocess_*.py 等）は無変更。

## 調査結果（2026-10-02）

計測条件: camSony1_S（960x540、30 fps）の先頭 300 フレーム（warmup 10 フレーム除外、290 フレーム集計）、
YOLO11x 検出（`bbox_thr=0.3`）→ WholeBody → AIC の推論のみ（描画・JSON 出力なし）。
検出人物は 206 BB / 290 フレーム（0.71 人/フレーム、84 フレームは検出ゼロでポーズ推論なし）。
計測スクリプトは作業用ディレクトリに置き、`torch.cuda.synchronize()` 付きで
backbone / head / decode をモンキーパッチして区間計測した。計装の有無で合計時間は変わらない
（105.7 vs 105.5 ms/frame）。§4 のバッチサイズ別計測・sleep / busy-wait 実験・CUDA Graph 単体計測・GPU クロックサンプリングと
§2 の YOLO fp16 は作業用スクリプトの単発実行結果（出力はテキストで保存、プロジェクト外）。

### 1. 時間内訳（ベースライン: flip test ON、fp32）

| 区間 | ms/frame | 比率 | 備考 |
|---|---|---|---|
| det (YOLO11x) | 13.7 | 12.9% | |
| wb.api | 46.3 | 43.8% | うち pre 0.8 / backbone 43.5 / head 0.6 / 転送+flip_back 0.7 / decode 0.4 / その他 0.3 |
| aic.api | 45.3 | 42.8% | うち backbone 43.5 / decode 0.1 / 他は wb と同程度 |
| 合計 | 105.7 | 100% | 9.5 fps |

- backbone forward が各モデル 412 回（206 BB × flip 2 回）で 1 回あたり **30.6 ms**。ポーズ推定時間の約 95% を占める。
- CPU 側の前処理（affine・正規化）と後処理（decode）は合計 1 ms 台で無視できる。
  両 config は `post_process='default'` なのでガウシアンブラーは実行されていない
  （`modulate_kernel=11` は config に残るが未使用。README 背景節の記述を訂正済み）。
- feat-014 の 5.1 fps と本計測の 9.5 fps の差は、検出器の違い（Faster R-CNN → YOLO11x）、
  描画・JSON 出力なし、検出ゼロフレームが 29% あることによる。WB/AIC 各約 45 ms/frame は
  feat-014 の各約 68 ms/frame と、人物あり率（0.71）を考慮すればおおむね整合する。

### 2. 施策別の効果（同一 290 フレーム）

| 変種 | ms/frame | fps | wb.api | aic.api | backbone ms/call | 対ベース |
|---|---|---|---|---|---|---|
| ベース（flip ON、fp32） | 105.7 | 9.5 | 46.3 | 45.3 | 30.6 | 1.00 |
| flip OFF | 60.8 | 16.4 | 23.6 | 23.1 | 30.7 | 1.74 |
| fp16 autocast | 64.7 | 15.5 | 25.9 | 24.9 | 16.4 | 1.63 |
| fp16 `model.half()` | 59.7 | 16.7 | 23.5 | 22.3 | 14.8 | 1.77 |
| flip OFF + `model.half()` | 38.6 | 25.9 | 12.5 | 11.9 | 15.3 | 2.74 |
| fp16 backbone のみ（head/decode は fp32） | 60.1 | 16.6 | 23.8 | 22.5 | 14.8 | 1.76 |
| fp16 backbone のみ + CUDA Graph | 42.2 | 23.7 | 14.6 | 13.6 | 8.4 | 2.50 |
| fp32 + CUDA Graph | 102.5 | 9.8 | 44.7 | 43.8 | 29.6 | 1.03 |

- fp16 は `model.half()` 方式が autocast より速い（autocast は forward ごとに重みキャストが入る）。
- YOLO11x の `half=True` は効果なし（13.1 → 13.1 ms/frame）。
- CUDA Graph は backbone の forward 全体（数百カーネル、未計測）を 1 回キャプチャし、以後は 1 回の発行で
  再生する仕組み。入力形状ごとにキャプチャが必要。本計測では全フレームが 1 BB だったため
  (1,3,256,192) のみ出現したが、複数人フレームでは BB 数ごとに別キャプチャ（warmup と静的バッファ）が
  必要になる（設計で扱う）。fp32 では効果が 3% しかなく、fp16 と組み合わせたときのみ効く（理由は §4）。

### 3. 出力差分（ベース比）

母集団は先頭 300 フレーム全体（warmup 含む）の 211 BB のうち、ベースの conf > 0.3 のキーポイント。
HALPE 26 に使う WB 0〜22 と AIC 全 14 点を対象とする。

| 変種 | モデル | 点数 | 中央値 | p95 | p99 | >2 px | conf 平均差 |
|---|---|---|---|---|---|---|---|
| fp16 half | wb | 2175 | 0.00 | 0.00 | 2.37 | 1.1% | −0.0001 |
| fp16 half | aic | 1624 | 0.00 | 0.00 | 0.00 | 0.4% | −0.0000 |
| fp16 backbone のみ | wb | 2175 | 0.00 | 0.00 | 0.00 | 0.6% | −0.0000 |
| fp16 backbone のみ | aic | 1624 | 0.00 | 0.00 | 0.00 | 0.2% | +0.0000 |
| flip OFF | wb | 2175 | 5.18 | 11.62 | 18.80 | 61.7% | +0.0128 |
| flip OFF | aic | 1624 | 5.19 | 11.61 | 19.51 | 64.7% | +0.0141 |

- **fp16 は出力同等**とみなせる（99% のキーポイントが 2.4 px 以内、conf 差なし）。
- backbone のみ fp16 にして head と decode を fp32 のまま残す方式は、`model.half()` より出力がベースに
  近い（2 px 超が wb 1.1% → 0.6%、p99 2.37 → 0.00）。速度は同じ（60.1 vs 59.7 ms/frame）。
  CUDA Graph を加えても出力は eager 実行と実質同一（最大差 2e-5 px）。fp32 + CUDA Graph もベースと
  実質同一（最大差 4e-5 px）。
- fp16 backbone のみの confidence 差（全点、211 BB）: 最大絶対差 wb 0.0092 / aic 0.0060、符号付き平均差
  wb +0.00018 / aic +0.00020（確信点のみでは −2e-5 / +2e-5）。
- **flip OFF は出力が変わる**。x/y 各軸の差は約 5.18 px の整数倍に量子化されている（点の 86〜91%）。
  これは `post_process='default'` が argmax に ±0.25 ヒートマップ画素のオフセットを加えるため、
  flip 有無でオフセットの符号が反転すると 0.5 画素、argmax が隣に移ると 1.0 画素の差になり、
  本動画の BB サイズでは 0.5 ヒートマップ画素が約 5.2 px に相当するため。表の距離 p95 ≈ √5 × 5.18 は
  x 2 量子・y 1 量子の組み合わせ。確信度の高い点の 62〜65% が 1 量子以上動く。
  x 方向の差は平均 −2.1〜−2.7 px と負に偏る（flip test の `shift_heatmap=True` に由来する系統差と
  考えられる）。どちらが正しいかは正解データなしには判定できない。

### 4. GPU の飽和と、CPU 側のカーネル発行遅延

- バックボーン単体のバッチサイズ別計測（ランダム入力、同一形状）: fp32 は bs=1 で 30.5 ms/枚、
  bs≥4 で 25.2 ms/枚（−17%）。fp16 は bs=1 で 9.1 ms/枚、bs≥4 で 7.3 ms/枚（−20%）。
  ViT-H はバッチ 1 でほぼ GPU を飽和させており、複数フレームをまとめるバッチ化の効果は 2 割以下。
  feat-015 の「GPU 飽和」という観察は、この意味では正しかった。
- 一方、パイプライン内の fp16 backbone は 14.8 ms/call で、連続実行時の 9.1 ms より 6 割遅い。
  原因を切り分けた結果は次の通り。
  - forward 間に 30〜50 ms の `time.sleep` を挟むと 16.6〜18.5 ms に悪化するが、同じ長さの
    busy-wait（CPU を回し続ける）では 9.1〜9.3 ms のまま。GPU のアイドル時間は両者で同じなので、
    原因は GPU 側ではなく CPU 側にある。
  - 実行中の GPU SM クロックを 100 ms 間隔でサンプリングしたところ、パイプライン実行中も中央値
    2.6 GHz（最大 3.09 GHz）で高止まりしており、GPU クロック低下は起きていない。
  - fp32 の forward は合計 30.5 ms（うち CPU の発行 4.4 ms）なので、発行が多少遅れても GPU が
    追いつかれない。fp16 では合計 9.3 ms に対し発行 4.2 ms と余裕が小さく、CPU が遅いときは
    発行が GPU を律速する。これが fp16 のときだけパイプライン内で遅くなる理由。
  - CPU が遅くなる要因として最も有力なのは CPU の省電力制御（周波数ガバナが `powersave`、
    アイドル時は最大 5.4 GHz の 19%）による周波数低下だが、実行中の CPU 周波数は未計測であり、
    パイプライン内で何が CPU を低速状態にしているか（GPU 待ち、動画読み込み、YOLO の CPU 処理）は
    特定していない。
- CUDA Graph で backbone を 1 回の発行にまとめると、連続実行で 8.6 ms/call、50 ms の sleep を
  挟んでも 8.7 ms/call で、CPU 側の発行速度に影響されなくなる。パイプライン内でも 8.4 ms/call を
  確認した。採用判断はこの実測で支えられており、CPU 低速化の機序の特定は不要。
- CUDA Graph のメモリ（fp16 backbone、WB/AIC 各 N=1〜8 の 16 グラフを私有プールで順次キャプチャ）:
  PyTorch reserved 2.87 GB → 3.92 GB（+1.05 GB）、allocated +0.21 GB、`nvidia-smi` 4.59 GB。
  fp32 で 2 モデルを読み込んだ直後は reserved 5.00 GB / `nvidia-smi` 5.42 GB（fp16 化で重みが半減するため
  改修後のほうが小さい）。ログは作業用ディレクトリ `bench_graph_mem.log` / `bench_fp32_mem.log`。
- CPU ガバナを `performance` に変える方法もあるが root 権限を要する環境設定であり、コード側で
  CUDA Graph を使えば環境に依らず解決できるため、こちらを採用する。

### 5. 施策の採否（要求仕様への入力）

| 施策 | 判断 | 根拠 |
|---|---|---|
| fp16（backbone のみ `half()`、head/decode は fp32） | **採用** | 1.76 倍、出力はベースと同等（2 px 超 0.6%）。`model.half()` より出力が近く速度は同じ |
| CUDA Graph（backbone、fp16 と併用） | **採用** | 併用で 2.50 倍。出力は fp16 eager と実質同一（最大差 2e-5 px）。CPU 側の発行遅延の影響を受けない |
| flip test OFF | **不採用**（利用者判断、2026-10-02） | さらに約 1.5 倍だが出力が変わる。精度が下がる可能性のある高速化は目的に反するため採用しない |
| 複数フレームのバッチ化 | 不採用 | GPU はバッチ 1 で飽和、効果 2 割以下。CUDA Graph で CPU 発行遅延も解消済み。コード変更が大きい割に見合わない |
| CPU 後処理の見直し | 不採用 | 前後処理は合計 1 ms 台 |
| YOLO11x の fp16 | 不採用 | 効果なし（13.1 → 13.1 ms/frame） |

採用 2 施策で、本計測条件（推論のみ）の 105.7 ms/frame → 42.2 ms/frame（9.5 → 23.7 fps）。
残りは YOLO11x 検出 13.6 ms/frame（32%）と backbone（BB あたり 4 回 × 8.4 ms、0.71 BB/frame で
約 24 ms/frame、57%）。

## 実装・検証結果（2026-10-02）

### 実装

- 新規 `scripts/pose_accel.py`: `AcceleratedBackbone`（backbone ラッパー、fp16 変換 + 入力形状ごとの
  CUDA Graph 再生）と `accelerate_pose_model`（`model.backbone` の差し替え。両機構 OFF なら no-op）。
- 改修 `scripts/run_halpe26_pipeline_yolo11.py`: CLI `--pose-fp16` / `--cuda-graph`（いずれも
  `BooleanOptionalAction`、既定 ON）、`--cuda-graph-max-batch`（既定 8）を追加。モデル初期化直後に
  `accelerate_pose_model` を WB / AIC に適用し `Pose accel: ...` を 1 行表示。`--device cpu` では両機構を
  自動無効化。`mmpose/` は無変更。
- 実装コードは Write 前に Subagent レビュー（高中ゼロ、低 4 件中 3 件反映）。

### 受け入れ基準の検証（camSony1_S 900 フレーム、`--mode both --profile`、同一マシン）

| AC | 内容 | 結果 | 実測 |
|---|---|---|---|
| AC-001-1 | fp16 eager の出力差（確信点 2 px 超 ≤ 2%、conf 平均差 ≤ 0.001、conf 最大差 ≤ 0.05、除外 ≤ 9） | PASS | 0.50% / −7e-6 / 0.0054 / 除外 0 |
| AC-001-2 | fp16 eager の WB+AIC ≤ 65 ms/frame | PASS | 24.9 + 23.6 = 48.5 ms/frame（15.4 fps） |
| AC-001-3 | `--device cpu` で両機構無効 | PASS | `[INFO] Pose accel disabled on CPU device` を確認、fp32 で 300 フレームまで処理を確認後に中断（設計手順 6） |
| AC-002-1 | fp16 eager と fp16+Graph の差（座標 ≤ 0.01 px、conf ≤ 0.001） | PASS | 座標 0.000 px / conf 2e-6 |
| AC-002-2 | 既定設定の WB+AIC ≤ 45 ms/frame | PASS | 15.9 + 14.7 = 30.6 ms/frame |
| AC-002-3 | 起動時 N=1 キャプチャログ（wb / aic） | PASS | 各 1 行 |
| AC-002-4 | 複数人動画で N≥2 の遅延キャプチャ・完走 | PASS | pexels_4441000（1244 フレーム）で N=2 を wb / aic 各 1 回キャプチャ |
| AC-002-5 | `--cuda-graph-max-batch 1` で N=2 は eager、ログは形状ごと 1 回 | PASS | `batch 2 > max_batch 1, eager` が wb / aic 各 1 行。既定設定と JSON 座標一致 |
| AC-002-6 | `--cuda-graph-max-batch 0` は exit 2 | PASS | argparse エラー |
| AC-003-1 | `--no-pose-fp16 --no-cuda-graph` でベースラインと座標・bbox・bbox_score 一致、confidence 最大差 ≤ 1e-4（2026-10-05 改定） | PASS | 座標・bbox・bbox_score 全点一致、confidence 最大差 1.9e-5。改定前基準（`diff -r` 差分 0）では不成立、下記参照 |
| AC-003-2 | `--profile` 区分・書式が改修前と同一 | PASS | 8 区分同一、合計 105.7 s / 8.5 fps（改修前と同値） |
| AC-004-1/2 | `Pose accel: fp16=..., cuda_graph=..., max_batch=8` 表示 | PASS | 既定 / 両 OFF とも表示 |
| AC-005-1 | `pose_accel` を import 可、`git diff --stat mmpose/` が空 | PASS | |
| 非機能 fps（Should） | 既定設定で 17.0 fps 以上 | PASS | 21.3 fps（改修前 8.5 fps、2.5 倍） |
| 非機能 GPU メモリ | N=1〜8 全 16 形状キャプチャで `nvidia-smi` ≤ 5.0 GB | PASS | 4711 MiB = 4.60 GiB（PyTorch reserved 4.04 GiB） |

### AC-003-1 について（バイト一致が成立しない原因と基準改定）

`--no-pose-fp16 --no-cuda-graph` の JSON はベースライン（改修前コードの出力）と 900 ファイル中 24 ファイルで
異なった。差分は confidence の下位桁（最大絶対差 1.9e-5）のみで、座標・bbox・bbox_score は全点一致。
原因切り分けのため、(a) 後方互換モードを 2 回実行して比較: 28 ファイルが異なる（confidence 最大絶対差
1.4e-5、座標一致）。(b) 改修前コード（`git stash` で改修を退避）を 2 回実行して比較: 28 ファイルが異なる
（confidence 最大絶対差 5.2e-5、座標一致）。すなわち改修の有無によらず、fp32 の GPU 推論自体に実行間の
非決定性があり、confidence のバイト一致は成立しない。機序は cuBLAS / cudnn のアルゴリズム選択や縮約順序に
よる最下位ビットの揺れと考えられる（未検証）。座標は本計測では全点一致した（ヒートマップの argmax +
1/4 画素オフセットで量子化されるため揺れが現れにくい）。

基準改定（2026-10-05、利用者承認）: AC-003-1 を「座標・bbox・bbox_score が全点一致、かつ confidence の
最大絶対差が 1e-4 以下」に改定した。改修後の後方互換モードはこの基準を満たす。

### 手動テスト（2026-10-05、利用者実施）

- 本番相当の長尺動画 camSony1_L（321,239 フレーム）を既定設定（`--mode both --profile`）で処理し完走。
  合計 15309.5 s（4 時間 15 分）、21.0 fps。WholeBody 16.5 + AIC 15.3 = 31.8 ms/frame、Detection 13.6 ms/frame。
  起動時の N=1 事前キャプチャと、最初の 100 フレーム以内での N=2 遅延キャプチャを確認。
- 出力 JSON を下流 3 ステージ（Stage2 track_id 付与 → Stage3 pink_id 付与 → Stage4 pink_track_id 算出）に
  通し、いずれも 321,239 ファイルを出力して完走。最終 JSON の読み込みエラーなし、全フィールド付与を確認。


## 進め方

1. 調査: 前処理 / forward（`torch.cuda.synchronize` 込み）/ 後処理に分割したプロファイルを
   camSony1_S の先頭 300 フレーム程度で取得し、結果を本 README に記録する。
   計測スクリプトはプロジェクトに入れない。
2. 要求仕様・設計: 計測結果に基づき施策と順序を決定する。
3. Codex レビュー → 実装 → 検証（改修前後の JSON 差分、処理時間）。

## ステータス

- 完了（2026-10-05）。受け入れ基準は全 PASS（AC-003-1 は 2026-10-05 改定後の基準）、手動テスト合格

## 関連

- feat-014: パイプライン処理速度プロファイリング（本案件の出発点となる計測値）
- feat-015: WholeBody/AIC 並列推論（効果なしで戻し。本案件で再解釈）
- feat-024: YOLO11x 検出器検証（現行パイプラインの検出器）
- feat-061: YOLO 検出ゼロ時の固定 ROI フォールバック（現行パイプラインの最新変更）
