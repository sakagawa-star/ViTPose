# feat-024: YOLO11x検出器検証 — 機能設計書

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|--------------|
| FR-001 | 2. インストール |
| FR-002 | 3. 検証用パイプラインスクリプト |
| FR-003 | 4. 検証実行手順 |

## 2. インストール（FR-001）

### インストール方法

```bash
uv pip install ultralytics==8.4.33
```

### 動作確認

```bash
uv run python -c "from ultralytics import YOLO; print('OK')"
```

### 既存環境への影響確認

ultralyticsは多くの依存関係（torchvision、pillow等）を持つ。インストール後、既存パイプラインが正常動作することを確認する:

```bash
uv run python scripts/run_halpe26_pipeline.py --video testdata/camSony1_S.mp4 --out-dir /tmp/test_env --mode video
```

エラーなく動画が出力されれば、既存環境への副作用はない。

### TECH_STACK.md更新

`docs/TECH_STACK.md`にultralytics 8.4.33を追記する（用途: YOLO11x人物検出、選定理由: COCO mAP 54.7で最高精度クラス）。

### チェックポイント

YOLO11xのモデル（`yolo11x.pt`、109.3MB）は初回推論時にultralyticsが自動ダウンロードする。手動ダウンロードは不要。

## 2.5 技術スタック

| 項目 | 値 |
|------|-----|
| 言語 | Python 3.10.16 |
| パッケージ管理 | uv |
| 検出器 | YOLO11x（COCO val2017 mAP 54.7、56.9Mパラメータ、80クラス） |
| 検出フレームワーク | ultralytics 8.4.33 |
| ポーズ推定 | ViTPose++ MoE（WholeBody + AIC）— 既存パイプラインと同一 |

## 3. 検証用パイプラインスクリプト（FR-002）

### 3.1 システム構成

```
scripts/
├── run_halpe26_pipeline.py           # 既存パイプライン（変更しない）
├── run_halpe26_pipeline_yolox.py     # YOLOX-l版（変更しない）
├── run_halpe26_pipeline_yolo11.py    # YOLO11x版（新規作成）
├── merge_halpe26.py                  # 結合ロジック（変更しない）
└── halpe26_to_openpose.py            # JSON変換（変更しない）
```

### 3.2 変更方針

`scripts/run_halpe26_pipeline_yolox.py` をベースに `scripts/run_halpe26_pipeline_yolo11.py` を作成する。変更箇所は以下の3点:

1. **検出器の初期化**: MMDetの`init_detector`をultralyticsの`YOLO`に置き換える
2. **検出処理**: MMDetの`inference_detector` + `process_mmdet_results`を、YOLO11xの推論 + 変換関数`process_yolo11_results`に置き換える
3. **MMDetのインポート削除**: `mmdet.apis`のインポートを削除し、`ultralytics`をインポートする

ポーズ推定（WholeBody / AIC）、結合、描画、JSON出力のロジックは一切変更しない。

### 3.3 変更箇所の詳細

#### 3.3.1 インポートの変更

```python
# 削除
import mmdet
from mmdet.apis import inference_detector, init_detector
from mmpose.apis import process_mmdet_results

# 追加
from ultralytics import YOLO
```

`process_mmdet_results`は使用しない。代わりにスクリプト内に`process_yolo11_results`関数を定義する。

#### 3.3.2 検出器の初期化

```python
# YOLOX-l版（削除）
MMDET_DIR = os.path.dirname(os.path.abspath(mmdet.__file__))
DET_CONFIG = os.path.join(MMDET_DIR, '.mim/configs/yolox/yolox_l_8x8_300e_coco.py')
DET_CHECKPOINT = 'checkpoints/yolox_l_8x8_300e_coco_20211126_140236-d3bd2b23.pth'
...
det_model = init_detector(DET_CONFIG, DET_CHECKPOINT, device=args.device)

# YOLO11x版（追加）
det_model = YOLO('yolo11x.pt')
```

`YOLO('yolo11x.pt')` は初回実行時に自動ダウンロードされる。デバイスは推論時に `args.device` を明示指定する（セクション3.3.4参照）。

#### 3.3.3 process_yolo11_results関数

YOLO11xの出力をMMPoseの`inference_top_down_pose_model`が受け取れるperson_results形式に変換する関数。スクリプト内にトップレベル関数として定義する。

```python
def process_yolo11_results(
    results,
    person_cls: int = 0,
) -> list[dict]:
    """YOLO11x結果をMMPose互換のperson_results形式に変換する。

    Args:
        results: ultralytics.engine.results.Results — 1画像分の推論結果。
            results.boxes.xyxy: Tensor shape (N, 4) — [x1, y1, x2, y2]
            results.boxes.conf: Tensor shape (N,) — 信頼度スコア
            results.boxes.cls: Tensor shape (N,) — クラスID (float)
        person_cls: 人物クラスID（COCOでは0）

    Returns:
        list[dict]: 各要素は {'bbox': ndarray([x1, y1, x2, y2, score])}
    """
    person_results = []
    boxes = results.boxes
    for i in range(len(boxes)):
        if int(boxes.cls[i]) == person_cls:
            x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy()
            score = float(boxes.conf[i].cpu())
            person_results.append({
                'bbox': np.array([x1, y1, x2, y2, score], dtype=np.float32)
            })
    return person_results
```

この関数の出力形式は`process_mmdet_results`と同一（`list[dict]`、各dictに`'bbox': ndarray(5,)`）であり、後続の`inference_top_down_pose_model`にそのまま渡せる。

#### 3.3.4 フレームループ内の検出処理

```python
# YOLOX-l版（削除）
mmdet_results = inference_detector(det_model, frame)
person_results = process_mmdet_results(mmdet_results, cat_id=1)

# YOLO11x版（追加）
yolo_results = det_model(frame, device=args.device, verbose=False)
person_results = process_yolo11_results(yolo_results[0])
```

- `frame`はBGR numpy配列。ultralyticsは内部でBGR→RGB変換を行うため、前処理は不要
- `verbose=False`で推論ごとのログ出力を抑制する
- `yolo_results[0]`で1画像目の結果を取得する（バッチサイズ1）
- ultralyticsのデフォルトNMSパラメータ: `conf=0.25`（信頼度閾値）、`iou=0.7`（IoU閾値）、`imgsz=640`（入力画像サイズ）。本検証ではこれらのデフォルト値を使用する
- 推論時の`device=args.device`指定により、初回呼び出し時にモデルが指定デバイスに自動移動する。2回目以降はキャッシュされるためオーバーヘッドはない

#### 3.3.5 bbox_thrの適用

YOLOX-l版と同一。`inference_top_down_pose_model`の`bbox_thr`引数に`args.bbox_thr`を渡す。YOLO11xの`process_yolo11_results`では全スコアのBBを返し、フィルタリングは`inference_top_down_pose_model`に任せる。

### 3.4 データフロー

```
YOLO11x推論
  ↓ det_model(frame, verbose=False) → list[Results]
  ↓ yolo_results[0].boxes.xyxy (N,4), .conf (N,), .cls (N,)
process_yolo11_results(person_cls=0)
  ↓ → list[dict] (各dictに'bbox': ndarray(5,))  ※cls==0のみ抽出
inference_top_down_pose_model(bbox_thr=args.bbox_thr)
  ↓ → 低スコアBBをフィルタリング
ポーズ推定（WholeBody / AIC）
  ↓
merge_to_halpe26() → HALPE 26
```

### 3.5 インターフェース定義

`parse_args()`の引数はYOLOX-l版（feat-023）と同一:

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|----------|------|
| `video` | str | （必須） | 入力動画パス |
| `out_dir` | str | `output` | 出力ディレクトリ |
| `device` | str | `cuda:0` | 推論デバイス |
| `mode` | str | `both` | 出力モード（both/video/json） |
| `bbox_thr` | float | 0.3 | 人物検出のスコア閾値 |
| `kpt_thr` | float | 0.3 | キーポイント描画閾値 |
| `profile` | bool | False | プロファイリング有効化 |

`--out-dir`のデフォルト値は`output`。デフォルトで実行した場合、既存パイプラインの出力ファイルと同名のファイルが上書きされるため、検証時は`--out-dir experiments/results_yolo11`を明示指定して既存出力と分離する。

`process_yolo11_results`のシグネチャ:

```python
def process_yolo11_results(results, person_cls: int = 0) -> list[dict]:
```

### 3.6 前提条件・境界条件

**前提条件**: プロジェクトルートディレクトリ（`ViTPose/`）から実行すること。ポーズ推定モデルのチェックポイントが相対パス（`checkpoints/...`）のため。YOLO11xのモデルはultralyticsのデフォルトディレクトリに保存されるため、実行ディレクトリに依存しない。

| 条件 | 振る舞い |
|------|---------|
| 0人検出（person_resultsが空） | 既存パイプラインと同一。空のキーポイントリストで処理続行 |
| 大量BB検出 | `bbox_thr`によるフィルタリングに任せる。追加処理なし |
| YOLO11xモデル未ダウンロード | 初回推論時にultralyticsのデフォルトディレクトリに自動ダウンロード（約109MB） |
| ultralyticsパッケージ未インストール | ImportErrorで即時終了 |
| YOLO11xの入力解像度 | ultralyticsのデフォルト値（imgsz=640）を使用する。スクリプト側での対応は不要 |

### 3.7 ログ・デバッグ設計

起動時に以下を標準出力に表示する:

- `Detector: YOLO11x` — 使用中の検出器名
- `Bbox threshold: {args.bbox_thr}` — 検出スコア閾値
- 既存パイプラインと同等のプログレス表示（100フレームごと）は変更なし

### 3.8 エラーハンドリング

既存パイプラインと同一。追加のエラーハンドリングは不要（検証用スクリプトのため）。

### 3.9 設計判断

| 判断 | 採用案 | 却下案 | 理由 |
|------|--------|--------|------|
| ベーススクリプト | `run_halpe26_pipeline_yolox.py`をベースにコピー | `run_halpe26_pipeline.py`をベースにコピー | YOLOX-l版に`--bbox-thr`引数が既にあり、差分が小さい |
| YOLO11xの推論結果変換 | スクリプト内に`process_yolo11_results`関数を定義 | `merge_halpe26.py`に変換関数を追加 | 検証用スクリプトなので`merge_halpe26.py`を変更しない |
| フィルタリングの配置 | `process_yolo11_results`ではフィルタリングせず、`inference_top_down_pose_model`のbbox_thrに任せる | `process_yolo11_results`内でbbox_thrフィルタリング | 既存パイプラインと同じフィルタリング方式を維持する |
| YOLO11xのデバイス指定 | `model(frame, device=args.device)` で明示的にデバイスを指定 | ultralyticsの自動検出に任せる | マルチGPU環境で意図しないGPUが選ばれるのを防ぐ。`--device`引数をポーズ推定とYOLO11x両方に統一的に適用する |
| `--out-dir`のデフォルト値 | `output`を維持する（feat-023と同一方針） | `experiments/results_yolo11`に変更 | 検証時は`--out-dir`を明示指定する運用とする。デフォルト値を変えると他のスクリプトと挙動が異なり混乱する |

## 4. 検証実行手順（FR-003）

### 4.1 実行コマンド

```bash
# デフォルト閾値（0.3）
uv run python scripts/run_halpe26_pipeline_yolo11.py \
  --video testdata/cam05520129.mp4 \
  --out-dir experiments/results_yolo11 \
  --mode video \
  --profile

# 閾値を上げて比較（0.5）
uv run python scripts/run_halpe26_pipeline_yolo11.py \
  --video testdata/cam05520129.mp4 \
  --out-dir experiments/results_yolo11_bbox05 \
  --mode video \
  --bbox-thr 0.5
```

### 4.2 比較確認

出力動画 `experiments/results_yolo11/vis_halpe26_cam05520129.mp4` を目視で確認し、以下を評価する:

1. BB重複問題が改善しているか（臥位の人物に1つのBBが付くか）
2. 検出の安定性（フレーム間でBBがちらつかないか）
3. 未検出フレームの頻度

YOLOX-l版（feat-023）の出力と比較する場合は、YOLOX-l版でも同じ動画を処理して出力を並べて確認する。
