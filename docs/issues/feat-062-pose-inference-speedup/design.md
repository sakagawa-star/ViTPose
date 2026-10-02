# feat-062 機能設計書: 2 パス推論構成のままポーズ推定を高速化（backbone fp16 + CUDA Graph）

## 1.1 対応要求マッピング

| 要求ID | 設計セクション |
|--------|----------------|
| FR-001（backbone fp16） | 1.4 §A、1.7 `AcceleratedBackbone` |
| FR-002（CUDA Graph） | 1.4 §B、1.7 `AcceleratedBackbone` |
| FR-003（後方互換） | 1.4 §C、1.7 `accelerate_pose_model` |
| FR-004（ログ） | 1.4 §D、1.8 |
| FR-005（共通モジュール化） | 1.2、1.7 |

## 1.2 システム構成

```
scripts/
├── pose_accel.py                   # 新規: AcceleratedBackbone / accelerate_pose_model
└── run_halpe26_pipeline_yolo11.py  # 改修: CLI 3 引数追加、モデル初期化直後に accelerate_pose_model を適用
```

- `pose_accel.py` は `torch`（と標準ライブラリ `sys`）のみに依存する（mmpose / ultralytics / cv2 を import しない）。
  `TopDown` モデルを duck typing で扱う（`model.backbone` と `model.cfg.data_cfg['image_size']` のみ参照）。
- `run_halpe26_pipeline_yolo11.py` は `from pose_accel import accelerate_pose_model` を追加する
  （既存の `sys.path.insert(0, os.path.dirname(__file__))` の後、`merge_halpe26` import と同じ位置）。
- 依存方向: `run_halpe26_pipeline_yolo11.py` → `pose_accel.py` → `torch`。逆方向・循環なし。
- MMPose 側の呼び出し経路（無変更）: `inference_top_down_pose_model` → `TopDown.forward`
  → `TopDown.forward_test` → `self.backbone(img)`（flip test で 2 回）→ `keypoint_head.inference_model`
  → `keypoint_head.decode`。本案件は `self.backbone` が指すモジュールを差し替えるだけで、
  この経路のコードには触れない。

## 1.3 技術スタック

- Python 3.10.16 / 実行は `uv run python`
- torch 2.11.0+cu128（`torch.cuda.CUDAGraph`、`torch.cuda.graph`、`torch.cuda.Stream`）、
  MMPose 0.24.0、mmcv-full 1.7.2、ultralytics、OpenCV、numpy（いずれも既存）
- 新規依存なし。`torch.compile` 不採用（ADR-3）。

## 1.4 各機能の詳細設計

### §A backbone fp16 化（FR-001）

#### データフロー
- 入力: `x` = backbone 入力 `torch.Tensor`、shape `(N, 3, 256, 192)`、dtype float32、device `cuda:0`、
  値域は MMPose の `NormalizeTensor` 後（平均 0・分散 1 付近）。N はフレーム内 BB 数（1 以上）。
- 変換: `x.half()` → fp16 → `inner(x)`（fp16 重みの `ViT`）→ 出力 fp16 `(N, 1280, 16, 12)`
  → `.float()` → float32。
- 出力: `(N, 1280, 16, 12)` float32。改修前の backbone 出力と同じ型・形状・device。
- 重み変換: `inner.half()` を `AcceleratedBackbone.__init__` で 1 回だけ実行（パラメータとバッファ
  の全てが fp16 になる。`pos_embed` を含む）。

#### 処理ロジック
```
# 意図の伝達用。そのままコピーして使うものではない
class AcceleratedBackbone(torch.nn.Module):
    def __init__(self, inner, fp16, cuda_graph, max_batch, name):
        super().__init__()
        self.inner = inner.half() if fp16 else inner
        ...
        self.eval()                    # inner は init_pose_model で eval 済み。ラッパー自身も eval に揃える
    def forward(self, x):
        if self.fp16:
            x = x.half()
        out = self._run(x)            # §B（CUDA Graph）または eager
        return out.float() if self.fp16 else out
```
- `out.float()` は fp16 → fp32 の新規テンソルを返す（コピー）。CUDA Graph 再生時の静的出力バッファ
  の別名参照を防ぐ役割も兼ねる（§B）。

#### エラーハンドリング
- fp16 の `inner.half()` 自体は失敗しない（全パラメータが浮動小数点のため）。
- fp16 演算での NaN/Inf 発生は実行時に検査しない（ADR-4）。調査で camSony1_S 300 フレームにおいて
  確信点の 2 px 超が 0.6% / 0.2%、確信点の confidence 符号付き平均差 −2e-5、全点の confidence
  最大絶対差 0.0092 であることを確認済み（README 調査結果 §3）。

#### 境界条件
- N=0 は到達しない（`inference_top_down_pose_model` が `person_results` 空のとき backbone を呼ばず
  早期 return する。`mmpose/apis/inference.py`）。
- `--device cpu`: §C で `fp16_on = graph_on = False` となり `accelerate_pose_model` は no-op
  （`model.backbone` を差し替えない）ため fp16 は適用されない。

### §B CUDA Graph 再生（FR-002）

#### データフロー
- 入力: §A 変換後の `x`（fp16 または fp32、shape `(N, 3, 256, 192)`、device cuda）。
- キャッシュ: `self._graphs: dict[tuple[int, ...], _GraphEntry]`。キーは `tuple(x.shape)`。
  値 `_GraphEntry(graph: torch.cuda.CUDAGraph, static_in: Tensor, static_out: Tensor)`。
  キャプチャ失敗は致命エラー（exit 1）なので「失敗済み形状」の状態は持たない。
- `self._over_max_logged: set[tuple[int, ...]]`: max_batch 超過を 1 回ログ済みの形状。
- 出力: `static_out` のコピー（fp16 なら `.float()` が §A でコピーを作る。fp32 なら `.clone()`）。

#### 処理ロジック
```
def _run(self, x):
    if not self.cuda_graph:
        return self.inner(x)
    shape = tuple(x.shape)
    if shape[0] > self.max_batch:
        if shape not in self._over_max_logged:
            print(f'[INFO] Pose accel ({self.name}): batch {shape[0]} > max_batch {self.max_batch}, eager')
            self._over_max_logged.add(shape)
        return self.inner(x)
    if shape not in self._graphs:
        self._graphs[shape] = self._capture(x)      # 失敗時は _capture 内で exit 1
    entry = self._graphs[shape]
    entry.static_in.copy_(x)
    entry.graph.replay()
    return entry.static_out if self.fp16 else entry.static_out.clone()
    # fp16 のときは呼び出し元 forward() の .float() がコピーを作るので clone 不要
```

```
def _capture(self, x):
    static_in = x.clone()                     # 固定アドレスの入力バッファ（x と同 dtype/device）
    try:
        with torch.no_grad():
            s = torch.cuda.Stream()
            s.wait_stream(torch.cuda.current_stream())
            with torch.cuda.stream(s):
                for _ in range(3):             # warmup 3 回（cuBLAS/cudnn の初期化をキャプチャ外で済ませる）
                    self.inner(static_in)
            torch.cuda.current_stream().wait_stream(s)
            graph = torch.cuda.CUDAGraph()
            with torch.cuda.graph(graph):      # pool 指定なし = グラフごとの私有プール（ADR-2）
                static_out = self.inner(static_in)
    except RuntimeError as e:                  # torch.cuda.OutOfMemoryError は RuntimeError のサブクラス
        print(f'[ERROR] Pose accel ({self.name}): CUDA Graph capture failed for shape '
              f'{tuple(static_in.shape)}: {e}. Use --no-cuda-graph')
        sys.exit(1)                            # 致命（ADR-8）
    print(f'[INFO] Pose accel ({self.name}): CUDA Graph captured for shape {tuple(static_in.shape)}')
    return _GraphEntry(graph, static_in, static_out)
```
- 事前キャプチャ（`precapture(shape)`）: `accelerate_pose_model` 内で、`cuda_graph=True` のとき
  `W, H = model.cfg.data_cfg['image_size']`（WB/AIC とも `[192, 256]`）を求め、
  `wrapper.precapture((1, 3, H, W))` を呼ぶ。`precapture` は
  `torch.zeros(shape, dtype=(torch.float16 if self.fp16 else torch.float32), device=self.device)` を
  作って `self._run(zeros)` を 1 回呼ぶ。`self.device` はラッパーが `__init__` で
  `next(self.inner.parameters()).device` として保持する（`cuda:0`）。これで N=1 の形状が起動時に
  キャプチャされ、フレームループ内の初回フレームにキャプチャの遅延（約 1 秒）が入らない。
- 遅延キャプチャ: N≥2 は初出の呼び出し内でキャプチャする。当該フレームの WholeBody / AIC ステップが
  約 1 秒長くなる（`--profile` の当該区分に含まれる）。1 動画で起こるのは形状の種類数回（通常 0〜2 回）。
- flip test との関係: `forward_test` は同じ形状で backbone を 2 回連続して呼ぶ（元画像・反転画像）。
  1 回目の出力は `.float()` / `.clone()` でコピー済みなので、2 回目の再生で `static_out` が上書き
  されても 1 回目の結果は壊れない。
- `static_in.copy_(x)`: `copy_` は任意のメモリレイアウトの `x` を受け付ける（`img.flip(3)` は
  連続な新規テンソルを返すので、実際には連続入力のみ到達する）。

#### エラーハンドリング
| 事象 | 検出 | 動作 | ログ |
|------|------|------|------|
| キャプチャ中の `RuntimeError`（`torch.cuda.OutOfMemoryError`、キャプチャ非対応の演算、ストリーム状態異常を含む） | except | `[ERROR]` を出力して `sys.exit(1)`。eager にフォールバックしない（ADR-8） | `[ERROR] Pose accel (name): CUDA Graph capture failed for shape (...): <例外>. Use --no-cuda-graph` |
| N > max_batch | 形状判定 | eager | `[INFO] ... batch N > max_batch M, eager`（形状ごと初回のみ） |
| 再生時の例外 | 捕捉しない | 伝播（調査で再生失敗は未観測。再生は発行のみで失敗要因が乏しい） | PyTorch の例外 |

#### 境界条件
- N=1: 起動時に事前キャプチャ済み。
- N=max_batch: キャプチャ対象（`>` 判定のため上限値は含む）。
- 同一 N の呼び出しが WB と AIC で発生: モデルごとに別の `AcceleratedBackbone` インスタンスと
  別の `_graphs` を持つ（WB と AIC は重みが違うので当然グラフも別）。
- fp16 なし・CUDA Graph あり（`--no-pose-fp16 --cuda-graph`）: fp32 のままキャプチャ。動作するが
  効果は 3%（調査結果 §2）。許容する（禁止しない）。
- GPU メモリ（実測 2026-10-02、fp16 backbone、WB/AIC 各 N=1〜8 の 16 グラフを私有プールで順次
  キャプチャ）: PyTorch reserved はモデル読み込み直後 2.87 GB → 16 グラフ後 3.92 GB（+1.05 GB、
  1 グラフあたり約 50〜110 MB、N に比例して増加）、allocated +0.21 GB、`nvidia-smi` 4.59 GB。
  グラフのプールはプロセス終了まで解放しない（形状数は max_batch 以下に有界）。これらは要求仕様
  1.4 の上限 5.0 GB の根拠である。

### §C 後方互換と適用判定（FR-003）

#### 処理ロジック（`run_halpe26_pipeline_yolo11.py` main、`init_pose_model` 2 行の直後・`Models initialized.` の前に挿入）
```
use_cuda = INTERNAL_DEVICE != 'cpu'
fp16_on = args.pose_fp16 and use_cuda
graph_on = args.cuda_graph and use_cuda
if (args.pose_fp16 or args.cuda_graph) and not use_cuda:
    print('[INFO] Pose accel disabled on CPU device')
for name, m in (('wb', wb_model), ('aic', aic_model)):
    accelerate_pose_model(m, fp16=fp16_on, cuda_graph=graph_on,
                          max_batch=args.cuda_graph_max_batch, name=name)
print(f'Pose accel: fp16={fp16_on}, cuda_graph={graph_on}, max_batch={args.cuda_graph_max_batch}')
```
- `accelerate_pose_model` は `fp16 == False and cuda_graph == False` のとき **何もせず False を返す**
  （`model.backbone` を差し替えない）。これにより FR-003 のバイト一致が成立する。
- 片方だけ True のときはラッパーを装着し、無効な側は素通し（fp16=False なら dtype 変換なし、
  cuda_graph=False なら常に `self.inner(x)`）。

#### CLI 引数（`parse_args`、`--fallback-score` の後に追加）
```
parser.add_argument('--pose-fp16', action=argparse.BooleanOptionalAction, default=True,
                    help='ViTPose backbone を fp16 で実行（既定 ON、--no-pose-fp16 で fp32。feat-062）')
parser.add_argument('--cuda-graph', action=argparse.BooleanOptionalAction, default=True,
                    help='ViTPose backbone を CUDA Graph で再生（既定 ON、--no-cuda-graph で eager。feat-062）')
parser.add_argument('--cuda-graph-max-batch', type=_check_positive_int, default=8,
                    help='CUDA Graph を使う 1 フレームの BB 数上限（1 以上、既定 8。超過は eager）')
```
- `_check_positive_int(s: str) -> int`: `int(s)` が 1 未満なら `argparse.ArgumentTypeError`
  （既存 `_check_thr` と同じパターンで本ファイルに定義）。

### §D ログ（FR-004）
- 1.8 を参照。

## 1.5 状態遷移
- 該当なし（ステートフルな GUI/処理はない）。`_graphs` のエントリは「未キャプチャ → キャプチャ済み
  | 失敗（None）」の一方向で、プロセス終了まで保持される。

## 1.6 ファイル・ディレクトリ設計
- 入出力ファイルのパス規約・命名規則・JSON 形式は無変更。
- 新規ファイル: `scripts/pose_accel.py`。
- 文書更新: `scripts/README.md` に `## run_halpe26_pipeline_yolo11.py` 節を新設し、既存
  `run_halpe26_pipeline.py` 節と同じ表形式で引数一覧（`--video` / `--out-dir` / `--device` / `--mode` /
  `--bbox-thr` / `--oks-thr` / `--kpt-thr` / `--profile` / `--fallback-roi` / `--fallback-score` /
  `--pose-fp16` / `--cuda-graph` / `--cuda-graph-max-batch`）を記載する。`CLAUDE.md` のディレクトリ
  構成に `pose_accel.py` を追加する。

## 1.7 インターフェース定義

```python
# scripts/pose_accel.py
class _GraphEntry(NamedTuple):
    graph: torch.cuda.CUDAGraph
    static_in: torch.Tensor
    static_out: torch.Tensor

class AcceleratedBackbone(torch.nn.Module):
    def __init__(self, inner: torch.nn.Module, fp16: bool, cuda_graph: bool,
                 max_batch: int, name: str) -> None: ...
    def forward(self, x: torch.Tensor) -> torch.Tensor: ...      # §A + §B
    def precapture(self, shape: tuple[int, int, int, int]) -> None: ...  # zeros で _run を 1 回呼ぶ
    # 内部: _run(x), _capture(x)。self.device は __init__ で next(inner.parameters()).device として保持

def accelerate_pose_model(model, fp16: bool, cuda_graph: bool,
                          max_batch: int = 8, name: str = 'pose') -> bool:
    """model.backbone を AcceleratedBackbone に差し替える。両方 False なら何もせず False を返す。
    cuda_graph=True のとき N=1 形状を事前キャプチャする。戻り値は差し替えたか否か。"""
```
- `accelerate_pose_model` の前提: `model` は `torch.nn.Module` で属性 `backbone`（nn.Module、
  cuda 上、eval 済み）と `cfg.data_cfg['image_size']`（`[W, H]`）を持つ。前提を満たさない場合は
  `AttributeError` / `KeyError` をそのまま送出する（本パイプラインでは `init_pose_model` の戻り値を
  渡すので常に満たす）。
- `model.backbone = AcceleratedBackbone(...)` の代入は `nn.Module.__setattr__` により `_modules['backbone']`
  を置き換える。`TopDown.forward_test` の `self.backbone(img)` は以後ラッパーを呼ぶ。
- 呼び出し方向: `run_halpe26_pipeline_yolo11.main` → `accelerate_pose_model` のみ。

## 1.8 ログ・デバッグ設計
- 既存パイプラインに合わせ `print` を使う。接頭辞は `[INFO]` / `[ERROR]`（設定表示行は接頭辞なしの
  既存書式 `Pose accel: ...` に合わせる）。
- 出力ポイントと書式:
  - CPU 時: `[INFO] Pose accel disabled on CPU device`（`--pose-fp16` または `--cuda-graph` が True
    で device が cpu のとき 1 回）
  - 設定表示: `Pose accel: fp16={bool}, cuda_graph={bool}, max_batch={int}`（常に 1 回、
    `Models initialized.` の直前）
  - キャプチャ成功: `[INFO] Pose accel ({name}): CUDA Graph captured for shape (N, 3, 256, 192)`
  - キャプチャ失敗: `[ERROR] Pose accel ({name}): CUDA Graph capture failed for shape (...): {例外}. Use --no-cuda-graph`（直後に exit 1）
  - max_batch 超過: `[INFO] Pose accel ({name}): batch N > max_batch M, eager`（形状ごと初回のみ）
- `--profile` の区分・書式は無変更。

## 設計判断の記録（ADR）

- **ADR-1: backbone のみ fp16、head は fp32**。採用理由: 速度は `model.half()` 全体と同じ
  （60.1 vs 59.7 ms/frame）で、出力がベースラインに近い（確信点の 2 px 超 1.1% → 0.6%、p99 2.37 → 0.00 px）。
  head は 0.6 ms/frame で高速化の余地がなく、fp32 のままにすることで flip_back・decode が
  改修前と同じ float32 numpy 経路を通る。却下案: `model.half()`（出力差がやや大きい）、
  `torch.autocast`（forward ごとの重みキャストで 64.7 ms/frame と遅い）。
- **ADR-2: CUDA Graph は入力形状ごとの私有メモリプール**。採用理由: `torch.cuda.graph` 既定。
  プール共有（`pool=`）は再生順序の制約があり、WB/AIC・N 違いのグラフが交互に再生される本用途では
  安全性の証明が必要になる。私有プールのコストは N=1 で数十 MB と小さい。却下案: プール共有。
- **ADR-3: `torch.compile(mode='reduce-overhead')` 不採用**。理由: 初回コンパイルに数分、
  動的形状の再コンパイル、mmcv 1.7.2 のカスタム op との互換が未検証。手動 CUDA Graph は
  調査で動作と効果を確認済み。
- **ADR-4: fp16 の NaN/Inf を実行時検査しない**。理由: 検査には GPU 同期が必要で、CUDA Graph で
  排除した CPU 待ちを再導入する。調査でキーポイント座標・confidence に異常値は出ていない
  （confidence 最大差 0.0092、座標差は量子化単位内）。将来必要になれば `--no-pose-fp16` で回避できる。
- **ADR-5: N=1 のみ事前キャプチャ、N≥2 は遅延キャプチャ**。理由: 本ドメインは 1 人前提で
  N=1 がほぼ全フレーム。全 N を起動時にキャプチャすると起動が max_batch 秒程度遅くなり、
  使われない形状のメモリを確保する。
- **ADR-6: 両機構とも既定 ON**。理由: 利用者が fp16 の出力差（確信点の 2 px 超 0.6%）を許容すると
  判断済み（2026-10-02）。bug-004 の方針（有用な既定を ON）に合わせる。ベースライン再現が必要な
  検証時のみ `--no-pose-fp16 --no-cuda-graph` を使う。
- **ADR-7: ラッパーモジュール方式（`model.backbone` の差し替え）**。理由: MMPose のコードを変更せず、
  `forward_test` の呼び出し経路をそのまま使える。両機構 OFF 時は装着しないためバイト一致が
  構造的に保証される。却下案: `backbone.forward` のインスタンス属性への代入（調査スクリプトで
  使った方法。動くが nn.Module の規約外で、`state_dict` や `repr` に現れず保守性が低い）。
- **ADR-8: キャプチャ失敗は致命エラー（exit 1）、eager フォールバックなし**。理由: torch 2.11 の
  `torch.cuda.graph.__exit__` は `capture_end()` → ストリームコンテキストの復帰の順で実行され、
  `capture_end()` が例外を投げると current stream がキャプチャ用サイドストリームのまま残り、以後の
  eager 実行の順序保証が崩れる。復旧（`torch.cuda.set_stream`）して続行する案は実機で検証できない
  （調査ではキャプチャ失敗が未観測）ため却下し、`[ERROR]` + exit 1 + `--no-cuda-graph` の案内に
  単純化する（feat-060/061 の致命エラー規約と一致）。

## 検証手順（手動テスト用、AC との対応）

共通条件: 動画 `testdata/camSony1_S.mp4`（900 フレーム）、`--mode both --profile`、同一マシン、他の GPU
ジョブなし、各条件 1 回実行。`--mode both` は JSON と動画の両方を出力するので、同じ実行結果を JSON 差分と
性能（`--profile` 表）の両方に使う。出力先は条件ごとに別ディレクトリ（`<base_dir>` / `<legacy_dir>` /
`<fp16_dir>` / `<default_dir>`）とし、JSON ディレクトリは `<dir>/camSony1_S_json`。

1. ベースライン生成（AC-003 / AC-001 / AC-002 の比較元）: 実装前に `git stash` した状態で
   `uv run python scripts/run_halpe26_pipeline_yolo11.py --video testdata/camSony1_S.mp4 --out-dir <base_dir> --mode both --profile`
   を実行し、JSON ディレクトリと `--profile` 表（合計秒・fps・各区分 Avg(ms)）を保存する。
   参考: 2026-10-02 の改修前実測は合計 105.7 s、8.5 fps、WholeBody 50.8 / AIC 49.7 ms/frame。
2. AC-003-1/2（後方互換）: 実装後、`--no-pose-fp16 --no-cuda-graph --out-dir <legacy_dir>`（他は共通条件）
   を実行し、`diff -r <base_dir>/camSony1_S_json <legacy_dir>/camSony1_S_json` が空であること、
   `--profile` の区分名と表形式が 1 と同一であること。
3. AC-001-1/2（fp16 eager）: `--pose-fp16 --no-cuda-graph --out-dir <fp16_dir>`（他は共通条件）を実行する。
   - AC-001-2: `--profile` 表の WholeBody + AIC の Avg(ms) の和が 65 ms/frame 以下。
   - AC-001-1: JSON 比較は作業用ディレクトリの一時スクリプトで行う（`<base_dir>` と `<fp16_dir>` の JSON を
     フレーム番号で対応付け、各フレームの people を出現順で対応付け、people 数が異なるフレームは除外して
     件数を表示する。`pose_keypoints_2d` の 26 点を `(x, y, c)` に分け、ベースラインの c > 0.3 の点について
     距離が 2 px を超える割合・c の符号付き平均差を、全点について c の最大絶対差を出す）。
4. AC-002-1/2/3（既定設定）: 引数追加なしで `--out-dir <default_dir>`（他は共通条件）を実行する。
   - AC-002-3: 起動ログに `wb` / `aic` の `CUDA Graph captured for shape (1, 3, 256, 192)` が各 1 行。
   - AC-002-2: `--profile` 表の WholeBody + AIC の Avg(ms) の和が 45 ms/frame 以下。
   - 非機能 Should: `--profile` の fps が 17.0 以上。
   - AC-002-1: 3 と同じ一時スクリプトで `<fp16_dir>` と `<default_dir>` を比較し、全点の座標最大絶対差が
     0.01 px 以下、c の最大絶対差が 0.001 以下。
5. AC-002-4/5（遅延キャプチャ・max_batch）: `--video testdata/pexels_4441000.mp4 --mode json` を
   既定設定と `--cuda-graph-max-batch 1` で実行する。前者で N≥2 の `captured for shape (N, 3, 256, 192)` が
   出ること、後者で当該形状のキャプチャログが出ず `batch N > max_batch 1, eager` が形状ごとに 1 回出ること、
   両方とも完走すること。
6. AC-001-3（CPU）: `--device cpu --mode json` を camSony1_S で起動し、`[INFO] Pose accel disabled on CPU device`
   と `Pose accel: fp16=False, cuda_graph=False, max_batch=8` を確認する（CPU は非常に遅いため、ログ確認後に
   `Ctrl-C` で中断してよい）。
7. AC-002-6: `--cuda-graph-max-batch 0` で argparse エラー（exit 2）になること。
8. 非機能（GPU メモリ、N=1〜8 全形状）: 実動画では全形状が現れないため、専用の一時スクリプト（作業用
   ディレクトリ、プロジェクトに入れない）で次を行い、要求仕様 1.4 の上限 5.0 GB を確認する。
   ```
   # 意図の伝達用。作業用ディレクトリに置く一時スクリプトの骨子
   import os, sys, torch
   os.chdir('<repo>'); sys.path.insert(0, 'scripts')
   from mmpose.apis import init_pose_model
   from merge_halpe26 import WB_CONFIG, WB_CHECKPOINT, AIC_CONFIG, AIC_CHECKPOINT
   from pose_accel import accelerate_pose_model
   models = [init_pose_model(c, k, device='cuda:0')
             for c, k in ((WB_CONFIG, WB_CHECKPOINT), (AIC_CONFIG, AIC_CHECKPOINT))]
   for name, m in zip(('wb', 'aic'), models):
       accelerate_pose_model(m, fp16=True, cuda_graph=True, max_batch=8, name=name)   # N=1 を事前キャプチャ
   for m in models:
       for n in range(2, 9):
           m.backbone.precapture((n, 3, 256, 192))                                     # N=2..8 をキャプチャ
   torch.cuda.synchronize()
   print('reserved GB', torch.cuda.memory_reserved() / 2**30)                          # 期待 約 3.9 GB
   os.system('nvidia-smi --query-gpu=memory.used --format=csv,noheader')              # 期待 約 4.6 GB、上限 5.0 GB
   ```
   期待値は調査実測（reserved 3.92 GB、`nvidia-smi` 4.59 GB）。ログに `captured for shape (N, 3, 256, 192)` が
   WB/AIC それぞれ N=1〜8 の 8 行ずつ出ること。
