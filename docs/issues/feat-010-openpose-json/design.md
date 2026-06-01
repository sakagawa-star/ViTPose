# 機能設計書: feat-010 OpenPose JSON出力

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001 | 4.1 JSON出力スクリプト |
| FR-002 | 4.2 室内動画での実行 |

## 2. システム構成

### モジュール構成

```
scripts/
├── merge_halpe26.py               # feat-009で作成済み（変更なし）
├── visualize_halpe26_video.py     # feat-011で作成済み（変更なし）
└── halpe26_to_openpose.py         # OpenPose JSON出力スクリプト（新規作成）
```

### ディレクトリ構成（変更後）

```
output/
└── feat-010/
    └── cam05520129_json/              # Pose2Sim互換ディレクトリ
        ├── cam05520129_000000.json
        ├── cam05520129_000001.json
        ├── ...
        └── cam05520129_000901.json
```

## 3. 技術スタック

既存の技術スタックのみ使用。追加ライブラリなし。

- Python 3.10.16
- MMPose 0.24.0（推論API）
- MMDetection 2.28.2（Faster R-CNN）
- PyTorch 2.11.0+cu128
- NumPy, OpenCV, json（標準ライブラリ）

## 4. 各機能の詳細設計

### 4.1 JSON出力スクリプト (FR-001)

#### データフロー

- **入力**: 動画ファイルパス（コマンドライン引数）
- **出力**: `{out-dir}/{video_stem}_json/{video_stem}_{frame:06d}.json`

#### コマンドライン引数

```
usage: halpe26_to_openpose.py [-h] --video VIDEO [--out-dir OUT_DIR] [--device DEVICE]
```

| 引数 | 型 | デフォルト | 説明 |
|------|-----|-----------|------|
| `--video` | str | 必須 | 入力動画パス |
| `--out-dir` | str | `output/feat-010` | 出力ベースディレクトリ |
| `--device` | str | `cuda:0` | 推論デバイス |

#### JSON出力フォーマット

各フレームにつき1つのJSONファイルを出力する。フォーマット:

```json
{
  "version": 1.3,
  "people": [
    {
      "person_id": [-1],
      "pose_keypoints_2d": [x0, y0, c0, x1, y1, c1, ..., x25, y25, c25],
      "face_keypoints_2d": [],
      "hand_left_keypoints_2d": [],
      "hand_right_keypoints_2d": [],
      "pose_keypoints_3d": [],
      "face_keypoints_3d": [],
      "hand_left_keypoints_3d": [],
      "hand_right_keypoints_3d": []
    }
  ]
}
```

- `version`: 1.3（Pose2SimのposeEstimation.py 239行目に合わせる）
- `pose_keypoints_2d`: HALPE 26キーポイントの [x, y, confidence] を平坦化したリスト（78要素）。値はfloat型
- `person_id`: [-1]（OpenPose互換、人物IDなし）
- 人物が検出されなかったフレーム: `"people": []`（空リスト）

#### ファイル命名規則

Pose2Simの `personAssociation.py` がファイル名から正規表現 `r'(\d+)'` で最後から2番目の数字部分をフレーム番号として抽出する。以下の命名規則に従う:

- ディレクトリ名: `{video_stem}_json`（`video_stem` は動画ファイル名から拡張子を除いた部分）
- ファイル名: `{video_stem}_{frame:06d}.json`（フレーム番号は0始まり、6桁ゼロパディング）
- 例: 動画 `cam05520129.mp4` → ディレクトリ `cam05520129_json/`、ファイル `cam05520129_000000.json`

#### 処理ロジック

```python
# scripts/halpe26_to_openpose.py の擬似コード（意図の伝達が目的）

import os
import sys
import json
import cv2
import numpy as np

from mmpose.apis import (inference_top_down_pose_model, init_pose_model,
                         process_mmdet_results)
from mmpose.datasets import DatasetInfo
from mmdet.apis import inference_detector, init_detector

sys.path.insert(0, os.path.dirname(__file__))
from merge_halpe26 import (merge_to_halpe26,
                            DET_CONFIG, DET_CHECKPOINT,
                            WB_CONFIG, WB_CHECKPOINT,
                            AIC_CONFIG, AIC_CHECKPOINT)


def halpe26_to_openpose_json(all_halpe26: list[np.ndarray]) -> dict:
    """Convert HALPE 26 keypoints to OpenPose JSON format.

    Args:
        all_halpe26: list of ndarray, each shape=(26, 3)

    Returns:
        OpenPose JSON dict
    """
    people = []
    for kps in all_halpe26:
        person = {
            'person_id': [-1],
            'pose_keypoints_2d': kps.flatten().tolist(),
            'face_keypoints_2d': [],
            'hand_left_keypoints_2d': [],
            'hand_right_keypoints_2d': [],
            'pose_keypoints_3d': [],
            'face_keypoints_3d': [],
            'hand_left_keypoints_3d': [],
            'hand_right_keypoints_3d': [],
        }
        people.append(person)
    return {'version': 1.3, 'people': people}


# main処理:
# 1. モデル初期化
det_model = init_detector(DET_CONFIG, DET_CHECKPOINT, device=args.device)
wb_model = init_pose_model(WB_CONFIG, WB_CHECKPOINT, device=args.device)
aic_model = init_pose_model(AIC_CONFIG, AIC_CHECKPOINT, device=args.device)

wb_dataset = wb_model.cfg.data['test']['type']
wb_dataset_info = DatasetInfo(wb_model.cfg.data['test']['dataset_info'])
aic_dataset = aic_model.cfg.data['test']['type']
aic_dataset_info = DatasetInfo(aic_model.cfg.data['test']['dataset_info'])

# 2. 動画オープン
cap = cv2.VideoCapture(args.video)
assert cap.isOpened(), f'Failed to open video: {args.video}'

video_stem = os.path.splitext(os.path.basename(args.video))[0]
json_dir = os.path.join(args.out_dir, f'{video_stem}_json')
os.makedirs(json_dir, exist_ok=True)

# 3. フレームループ
frame_idx = 0
while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    # 3a. 人物検出 + WholeBody + AIC推定
    mmdet_results = inference_detector(det_model, frame)
    person_results = process_mmdet_results(mmdet_results, cat_id=1)

    wb_results, _ = inference_top_down_pose_model(
        wb_model, frame, person_results, bbox_thr=0.3,
        format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)
    aic_results, _ = inference_top_down_pose_model(
        aic_model, frame, person_results, bbox_thr=0.3,
        format='xyxy', dataset=aic_dataset, dataset_info=aic_dataset_info)

    # 3b. 結合
    all_halpe26 = []
    if len(wb_results) == len(aic_results):
        for i in range(len(wb_results)):
            halpe26 = merge_to_halpe26(
                wb_results[i]['keypoints'], aic_results[i]['keypoints'])
            all_halpe26.append(halpe26)
    else:
        print(f'Warning: frame {frame_idx} result count mismatch, writing empty people')

    # 3c. JSON書き出し
    openpose_dict = halpe26_to_openpose_json(all_halpe26)
    json_path = os.path.join(json_dir, f'{video_stem}_{frame_idx:06d}.json')
    with open(json_path, 'w') as f:
        json.dump(openpose_dict, f)

    if frame_idx % 100 == 0:
        print(f'Processing frame {frame_idx}...')
    frame_idx += 1

cap.release()
```

#### エラーハンドリング

- 動画ファイルが開けない場合: assertで停止する
- WholeBodyとAICの結果数不一致: 該当フレームは `"people": []` として書き出し、警告をコンソール表示する
- ディスク容量不足: 各JSONファイルは数百バイト〜数KB。902フレーム × 数KB = 数MB程度のため問題にならない

#### 境界条件

- 人物が検出されなかったフレーム: `"people": []` のJSONを書き出す
- 複数人物が検出された場合: `"people"` リストに全員分を含める

### 4.2 室内動画での実行 (FR-002)

カレントディレクトリは `/home/sakagawa/git/ViTPose` で実行すること。

```bash
mkdir -p output/feat-010
uv run python scripts/halpe26_to_openpose.py \
    --video /home/sakagawa/git/ViTPose_HuggingFace/input/cam05520129.mp4 \
    --out-dir output/feat-010
```

出力: `output/feat-010/cam05520129_json/cam05520129_000000.json` 〜 `cam05520129_000901.json`

#### 検証コマンド

ファイル数の確認:
```bash
ls output/feat-010/cam05520129_json/*.json | wc -l
```
期待値: `902`

先頭ファイルのフォーマット確認:
```bash
uv run python -c "
import json
with open('output/feat-010/cam05520129_json/cam05520129_000000.json') as f:
    data = json.load(f)
print(f'version: {data[\"version\"]}')
print(f'people count: {len(data[\"people\"])}')
if data['people']:
    p = data['people'][0]
    print(f'person_id: {p[\"person_id\"]}')
    print(f'pose_keypoints_2d length: {len(p[\"pose_keypoints_2d\"])}')
    print(f'First 9 values (kp 0-2): {p[\"pose_keypoints_2d\"][:9]}')
"
```

## 5. インターフェース定義

### halpe26_to_openpose.py

```python
def halpe26_to_openpose_json(
    all_halpe26: list[np.ndarray],  # 各要素 shape=(26, 3)
) -> dict:
    """Convert HALPE 26 keypoints to OpenPose JSON dict."""
```

## 6. ファイル・ディレクトリ設計

セクション2のディレクトリ構成を参照。`output/` は `.gitignore` に含まれている。

## 7. ログ・デバッグ設計

`print` でコンソールに進捗を表示する:
- `Initializing models...`
- `Processing video: {path} ({total_frames} frames)`
- `Output directory: {json_dir}`
- `Processing frame {n}...`（100フレームごと）
- `Saved {frame_count} JSON files to {json_dir}`

## 8. 設計判断

### JSON version: 1.0 vs 1.3

- **採用案**: version 1.3
- **却下案**: version 1.0（halpe26_merge_spec.md記載の値）
- **理由**: Pose2Simの `poseEstimation.py` が出力するJSON（239行目）は version 1.3 を使用している。Pose2Sim互換を優先する

### 可視化機能の統合: する vs しない

- **採用案**: JSON出力のみ。可視化はfeat-011のスクリプトを使用する
- **却下案**: JSON出力と同時に可視化動画も出力する
- **理由**: 単一責務の原則。JSON出力と可視化は別のスクリプトで独立して実行可能にする
