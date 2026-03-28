# 機能設計書: feat-011 結合結果の可視化・検証

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001 | 4.1 動画可視化スクリプト |
| FR-002 | 4.2 Pexelsテスト動画での実行 |
| FR-003 | 4.3 病室テスト動画での実行 |

## 2. システム構成

### モジュール構成

```
scripts/
├── merge_halpe26.py               # feat-009で作成済み（変更なし）
└── visualize_halpe26_video.py     # 動画可視化スクリプト（新規作成）
```

`visualize_halpe26_video.py` は `merge_halpe26.py` から `merge_to_halpe26()` と `draw_halpe26()` をインポートして使用する。

### ディレクトリ構成（変更後）

```
output/
└── feat-011/
    ├── vis_halpe26_pexels_4441000.mp4  # Pexels動画の可視化結果
    └── vis_halpe26_cam05520129.mp4    # 病室動画の可視化結果
```

## 3. 技術スタック

既存の技術スタックのみ使用。追加ライブラリなし。

- Python 3.10.16
- MMPose 0.24.0（推論API）
- MMDetection 2.28.2（Faster R-CNN）
- PyTorch 2.11.0+cu128
- NumPy, OpenCV

## 4. 各機能の詳細設計

### 4.1 動画可視化スクリプト (FR-001)

#### データフロー

- **入力**: 動画ファイルパス（コマンドライン引数）
- **出力**: 可視化動画（`--out-dir` に保存、ファイル名は `vis_halpe26_{入力basename}`）

#### コマンドライン引数

```
usage: visualize_halpe26_video.py [-h] --video VIDEO [--out-dir OUT_DIR] [--device DEVICE]
```

| 引数 | 型 | デフォルト | 説明 |
|------|-----|-----------|------|
| `--video` | str | 必須 | 入力動画パス |
| `--out-dir` | str | `output/feat-011` | 出力ディレクトリ |
| `--device` | str | `cuda:0` | 推論デバイス |

#### 処理ロジック

```python
# scripts/visualize_halpe26_video.py の擬似コード（意図の伝達が目的）

import os
import sys
import cv2
import numpy as np

from mmpose.apis import (inference_top_down_pose_model, init_pose_model,
                         process_mmdet_results)
from mmpose.datasets import DatasetInfo
from mmdet.apis import inference_detector, init_detector

sys.path.insert(0, os.path.dirname(__file__))
from merge_halpe26 import (merge_to_halpe26, draw_halpe26,
                            DET_CONFIG, DET_CHECKPOINT,
                            WB_CONFIG, WB_CHECKPOINT,
                            AIC_CONFIG, AIC_CHECKPOINT)

# 1. モデル初期化（1回のみ）
det_model = init_detector(DET_CONFIG, DET_CHECKPOINT, device=args.device)
wb_model = init_pose_model(WB_CONFIG, WB_CHECKPOINT, device=args.device)
aic_model = init_pose_model(AIC_CONFIG, AIC_CHECKPOINT, device=args.device)

wb_dataset = wb_model.cfg.data['test']['type']
wb_dataset_info = DatasetInfo(wb_model.cfg.data['test']['dataset_info'])
aic_dataset = aic_model.cfg.data['test']['type']
aic_dataset_info = DatasetInfo(aic_model.cfg.data['test']['dataset_info'])

# 2. 動画入力のオープン
cap = cv2.VideoCapture(args.video)
assert cap.isOpened(), f'Failed to open video: {args.video}'
fps = cap.get(cv2.CAP_PROP_FPS)
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

# 3. 出力ディレクトリ作成＋動画出力の作成
os.makedirs(args.out_dir, exist_ok=True)
out_name = f'vis_halpe26_{os.path.basename(args.video)}'
out_path = os.path.join(args.out_dir, out_name)
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

# 4. フレームループ
frame_idx = 0
while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    # 4a. 人物検出
    mmdet_results = inference_detector(det_model, frame)
    person_results = process_mmdet_results(mmdet_results, cat_id=1)

    # 4b. WholeBody推定
    wb_results, _ = inference_top_down_pose_model(
        wb_model, frame, person_results, bbox_thr=0.3,
        format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)

    # 4c. AIC推定
    aic_results, _ = inference_top_down_pose_model(
        aic_model, frame, person_results, bbox_thr=0.3,
        format='xyxy', dataset=aic_dataset, dataset_info=aic_dataset_info)

    # 4d. 結合＋描画（結果数不一致フレームはスキップしキーポイントなしで書き込む）
    vis_frame = frame.copy()
    if len(wb_results) == len(aic_results):
        for i in range(len(wb_results)):
            halpe26 = merge_to_halpe26(
                wb_results[i]['keypoints'], aic_results[i]['keypoints'])
            vis_frame = draw_halpe26(vis_frame, halpe26)
    else:
        print(f'Warning: frame {frame_idx} result count mismatch '
              f'(wb={len(wb_results)}, aic={len(aic_results)}), skipping keypoints')

    writer.write(vis_frame)

    if frame_idx % 100 == 0:
        print(f'Processing frame {frame_idx}...')
    frame_idx += 1

# 5. リソース解放
cap.release()
writer.release()
```

出力ファイル名のルール: `vis_halpe26_{入力動画のbasename}`。例:
- 入力 `pexels_4441000.mp4` → 出力 `vis_halpe26_pexels_4441000.mp4`
- 入力 `cam05520129.mp4` → 出力 `vis_halpe26_cam05520129.mp4`

#### インポート方法

`scripts/merge_halpe26.py` からのインポートは、同一ディレクトリにあるため `from merge_halpe26 import ...` で行う。実行時のカレントディレクトリは `/home/sakagawa/git/ViTPose` であるため、`PYTHONPATH` に `scripts/` を追加するか、`sys.path` に追加する。スクリプト冒頭で以下を行う:

```python
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from merge_halpe26 import (merge_to_halpe26, draw_halpe26,
                            DET_CONFIG, DET_CHECKPOINT,
                            WB_CONFIG, WB_CHECKPOINT,
                            AIC_CONFIG, AIC_CHECKPOINT)
```

#### エラーハンドリング

- 動画ファイルが開けない場合: `cap.isOpened()` が False。`assert cap.isOpened(), f'Failed to open video: {args.video}'` で停止する
- WholeBodyとAICの結果数不一致: 動画処理では1フレームの不一致でスクリプト全体を停止させず、該当フレームをキーポイントなしで書き込み、警告メッセージをコンソールに表示する（擬似コード4dを参照）
- 特定フレームで人物が検出されない場合: キーポイントなしのフレームをそのまま書き込む

#### 境界条件

- 全フレームで人物が検出されない場合: キーポイントなしの動画が出力される
- 複数人物が検出された場合: 全員分のHALPE 26を描画する

### 4.2 Pexelsテスト動画での実行 (FR-002)

カレントディレクトリは `/home/sakagawa/git/ViTPose` で実行すること。

```bash
mkdir -p output/feat-011
uv run python scripts/visualize_halpe26_video.py \
    --video output/feat-009/pexels_4441000.mp4 \
    --out-dir output/feat-011
```

出力: `output/feat-011/vis_halpe26_pexels_4441000.mp4`

#### 検証コマンド

```bash
uv run python -c "
import cv2
cap = cv2.VideoCapture('output/feat-011/vis_halpe26_pexels_4441000.mp4')
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)
cap.release()
print(f'Size={w}x{h}, Frames={total}, FPS={fps}')
"
```

期待値: `Size=1920x1080, Frames=1244, FPS=25.0`

### 4.3 病室テスト動画での実行 (FR-003)

```bash
uv run python scripts/visualize_halpe26_video.py \
    --video /home/sakagawa/git/ViTPose_HuggingFace/input/cam05520129.mp4 \
    --out-dir output/feat-011
```

出力: `output/feat-011/vis_halpe26_cam05520129.mp4`

#### 検証コマンド

```bash
uv run python -c "
import cv2
cap = cv2.VideoCapture('output/feat-011/vis_halpe26_cam05520129.mp4')
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)
cap.release()
print(f'Size={w}x{h}, Frames={total}, FPS={fps}')
"
```

期待値: `Size=1920x1080, Frames=902, FPS=30.0`

## 5. インターフェース定義

`visualize_halpe26_video.py` は新規関数を定義せず、`merge_halpe26.py` の関数を再利用する。スクリプトレベルの処理のみ。

## 6. ファイル・ディレクトリ設計

セクション2のディレクトリ構成を参照。`scripts/` はgit管理対象。`output/` は `.gitignore` に含まれている。

## 7. ログ・デバッグ設計

- `print` でコンソールに進捗を表示する:
  - `Initializing models...`
  - `Processing video: {path} ({total_frames} frames, {fps} fps)`
  - `Processing frame {n}...`（100フレームごと）
  - `Saved: {out_path}`

## 8. 設計判断

### スクリプト分割: 動画版を別ファイルにする vs merge_halpe26.pyに動画機能を追加

- **採用案**: `visualize_halpe26_video.py` として別ファイルで作成
- **却下案**: `merge_halpe26.py` に `--video` オプションを追加
- **理由**: merge_halpe26.py は静止画の結合ロジックとして単一責務を保つ。動画処理はフレームループ・VideoWriter管理が加わるため、別スクリプトが適切

### 関数の再利用: import vs コピー

- **採用案**: `from merge_halpe26 import ...` でインポート
- **却下案**: merge_halpe26.py の関数をコピーして貼り付ける
- **理由**: コードの重複を避け、結合ロジックの変更が1箇所で済むようにする
