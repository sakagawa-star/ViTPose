# feat-023: YOLOX-l検出器検証 — 機能設計書

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|--------------|
| FR-001 | 2. チェックポイントダウンロード |
| FR-002 | 3. 検証用パイプラインスクリプト |
| FR-003 | 4. 検証実行手順 |

## 2. チェックポイントダウンロード（FR-001）

### ダウンロード方法

```bash
uv run mim download mmdet --config yolox_l_8x8_300e_coco --dest checkpoints/
```

もし`mim download`が失敗する場合は、以下のURLから直接ダウンロードする:

```
https://download.openmmlab.com/mmdetection/v2.0/yolox/yolox_l_8x8_300e_coco/yolox_l_8x8_300e_coco_20211126_140236-d3bd2b23.pth
```

### 配置先

- 設定ファイル: MMDetパッケージ内の既存設定を使用（`mmdet.__file__`から動的にパスを解決）
- チェックポイント: `checkpoints/yolox_l_8x8_300e_coco_20211126_140236-d3bd2b23.pth`

### 動作確認

```python
import os
import mmdet
from mmdet.apis import init_detector

mmdet_dir = os.path.dirname(os.path.abspath(mmdet.__file__))
config = os.path.join(mmdet_dir, '.mim/configs/yolox/yolox_l_8x8_300e_coco.py')
model = init_detector(
    config,
    'checkpoints/yolox_l_8x8_300e_coco_20211126_140236-d3bd2b23.pth',
    device='cuda:0'
)
```

エラーなく初期化できれば成功。

## 2.5 技術スタック

| 項目 | 値 |
|------|-----|
| 言語 | Python 3.10.16 |
| パッケージ管理 | uv |
| 検出器 | YOLOX-l（COCO val2017 mAP 49.4、入力サイズ640x640、80クラス） |
| 検出フレームワーク | MMDetection 2.28.2（YOLOXモデル・設定ファイル同梱済み） |
| ポーズ推定 | ViTPose++ MoE（WholeBody + AIC）— 既存パイプラインと同一 |

MMDet 2.28.2にYOLOX設定（`configs/yolox/`）とモデル定義（`mmdet/models/detectors/yolox.py`）が含まれているため、追加のライブラリインストールは不要。

## 3. 検証用パイプラインスクリプト（FR-002）

### 3.1 システム構成

```
scripts/
├── run_halpe26_pipeline.py           # 既存パイプライン（変更しない）
├── run_halpe26_pipeline_yolox.py     # 検証用パイプライン（新規作成）
├── merge_halpe26.py                  # 結合ロジック（変更しない）
└── halpe26_to_openpose.py            # JSON変換（変更しない）
```

### 3.2 変更方針

`scripts/run_halpe26_pipeline.py` をコピーして `scripts/run_halpe26_pipeline_yolox.py` を作成する。変更箇所は**検出器の設定とチェックポイントのパス、および`--bbox-thr`引数の追加**のみ。

### 3.3 変更箇所の詳細

#### 3.3.1 検出器設定の変更

`merge_halpe26.py` から `DET_CONFIG` / `DET_CHECKPOINT` をインポートせず、スクリプト内で直接定義する。

```python
# 既存（Faster R-CNN）
from merge_halpe26 import (merge_to_halpe26, draw_halpe26, draw_bbox,
                            DET_CONFIG, DET_CHECKPOINT,
                            WB_CONFIG, WB_CHECKPOINT,
                            AIC_CONFIG, AIC_CHECKPOINT)

# 変更後（YOLOX-l）
from merge_halpe26 import (merge_to_halpe26, draw_halpe26, draw_bbox,
                            WB_CONFIG, WB_CHECKPOINT,
                            AIC_CONFIG, AIC_CHECKPOINT)

import mmdet
MMDET_DIR = os.path.dirname(os.path.abspath(mmdet.__file__))
DET_CONFIG = os.path.join(
    MMDET_DIR, '.mim/configs/yolox/yolox_l_8x8_300e_coco.py')
DET_CHECKPOINT = 'checkpoints/yolox_l_8x8_300e_coco_20211126_140236-d3bd2b23.pth'
```

この相対パスは`merge_halpe26.py`の`DET_CHECKPOINT`と同じ方式であり、相対パスはカレントディレクトリ（プロジェクトルート）基準で解決される。

#### 3.3.2 `--bbox-thr`引数の追加

```python
parser.add_argument('--bbox-thr', type=float, default=0.3,
                    help='Bounding box score threshold for person detection (default: 0.3)')
```

既存パイプラインではbbox_thrがハードコード（0.3）されている。YOLOX-lはNMSスコア閾値が0.01（設定ファイル内のtest_cfg.score_thr）であり、低スコアのBBが多く出力される可能性がある。`--bbox-thr`で検出閾値を調整可能にする。

#### 3.3.3 bbox_thrの適用

`inference_top_down_pose_model`の`bbox_thr`引数に`args.bbox_thr`を渡す:

```python
# 既存
wb_results, _ = inference_top_down_pose_model(
    wb_model, frame, person_results, bbox_thr=0.3, ...)

# 変更後
wb_results, _ = inference_top_down_pose_model(
    wb_model, frame, person_results, bbox_thr=args.bbox_thr, ...)
```

AIC推定も同様に`args.bbox_thr`を使用する。

### 3.4 データフロー

YOLOX-lの出力フォーマットはMMDetの標準フォーマット（クラスごとのbbox配列のリスト）に従う。`process_mmdet_results`は`mmdet_results[cat_id - 1]`で人物クラスのBBを取得するため、YOLOX（80クラス、人物はクラス0=cat_id 1）でも互換性がある。

```
YOLOX-l推論
  ↓ inference_detector() → list[ndarray] (80クラス分)
process_mmdet_results(cat_id=1)
  ↓ → list[dict] (各dictに'bbox': ndarray(5,))
inference_top_down_pose_model(bbox_thr=args.bbox_thr)
  ↓ → 低スコアBBをフィルタリング
ポーズ推定（WholeBody / AIC）
  ↓
merge_to_halpe26() → HALPE 26
```

### 3.5 インターフェース定義

`parse_args()` の戻り値に以下のフィールドが追加される（既存パイプラインとの差分のみ記載）:

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|----------|------|
| `bbox_thr` | float | 0.3 | 人物検出のスコア閾値 |

その他の引数（`--video`, `--out-dir`, `--device`, `--mode`, `--kpt-thr`, `--profile`）は既存パイプラインと同一。`--out-dir`のデフォルト値は既存と同じ`output`。デフォルトの`output`で実行した場合、既存パイプラインの出力ファイルと同名のファイルが上書きされるため、検証時は`--out-dir experiments/results_yolox`を明示指定して既存パイプラインの出力と分離する。

`main()`のシグネチャは既存パイプラインと同一。

### 3.6 前提条件・境界条件

**前提条件**: プロジェクトルートディレクトリ（`ViTPose/`）から実行すること。チェックポイントのパスが相対パス（`checkpoints/...`）のため、別ディレクトリから実行するとFileNotFoundErrorになる。これは既存パイプライン（`merge_halpe26.py`）と同一の制約である。

| 条件 | 振る舞い |
|------|---------|
| 0人検出（person_results が空） | 既存パイプラインと同一。空のキーポイントリストで処理続行 |
| 大量BB検出 | `bbox_thr`によるフィルタリングに任せる。追加処理なし |
| チェックポイントファイルが存在しない | MMDetの`init_detector`がFileNotFoundErrorを出力して終了 |
| YOLOX-lの入力解像度 | 640x640固定（Faster R-CNNの短辺800とは異なる）。テスト時の前処理はMMDetの設定ファイルが制御するため、スクリプト側での対応は不要 |

### 3.7 ログ・デバッグ設計

起動時に以下を標準出力に表示する:

- `Detector: YOLOX-l` — 使用中の検出器名
- `Bbox threshold: {args.bbox_thr}` — 検出スコア閾値
- 既存パイプラインと同等のプログレス表示（100フレームごと）は変更なし

### 3.8 エラーハンドリング

既存パイプラインと同一。追加のエラーハンドリングは不要（検証用スクリプトのため）。

### 3.9 設計判断

| 判断 | 採用案 | 却下案 | 理由 |
|------|--------|--------|------|
| スクリプト作成方法 | `run_halpe26_pipeline.py`のコピーを作成 | 既存スクリプトに`--detector`引数を追加 | 既存パイプラインを壊すリスクを避ける。検証用なので、検証後に不要になれば削除できる |
| 設定ファイルの配置 | MMDetパッケージ内の既存設定をそのまま使用 | `checkpoints/`にコピー | YOLOX-l設定はbase設定（yolox_s）を参照しており、コピーするとbase解決に失敗する |
| `--bbox-thr`引数 | 追加する | ハードコード0.3のまま | YOLOXはFaster R-CNNより低スコアBBを多く出力する可能性があり、閾値調整が検証に必要 |

## 4. 検証実行手順（FR-003）

### 4.1 実行コマンド

```bash
# デフォルト閾値（0.3）
uv run python scripts/run_halpe26_pipeline_yolox.py \
  --video testdata/camSony1.mp4 \
  --out-dir experiments/results_yolox \
  --mode video \
  --profile

# 閾値を上げて比較（0.5）
uv run python scripts/run_halpe26_pipeline_yolox.py \
  --video testdata/camSony1.mp4 \
  --out-dir experiments/results_yolox_bbox05 \
  --mode video \
  --bbox-thr 0.5
```

### 4.2 比較確認

出力動画 `experiments/results_yolox/vis_halpe26_camSony1.mp4` を目視で確認し、以下を評価する:

1. BB重複問題が改善しているか（臥位の人物に1つのBBが付くか）
2. 検出の安定性（フレーム間でBBがちらつかないか）
3. 未検出フレームの頻度

既存パイプライン（Faster R-CNN）の出力と比較する場合は、既存パイプラインでも同じ動画を処理して出力を並べて確認する。
