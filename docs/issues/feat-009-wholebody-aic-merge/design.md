# 機能設計書: feat-009 WholeBody + AIC結合ロジック

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001 | 4.1 結合スクリプト |
| FR-002 | 4.2 可視化 |

## 2. システム構成

### モジュール構成

```
scripts/
└── merge_halpe26.py    # 結合スクリプト（新規作成）
```

`merge_halpe26.py` は単一ファイルのスクリプトとして実装する。以下の処理をすべて含む:
- 人物検出（Faster R-CNN）
- WholeBody推定
- AIC推定
- HALPE 26への結合
- 結果の保存と可視化

### ディレクトリ構成（変更後）

```
scripts/
└── merge_halpe26.py           # 結合スクリプト（新規作成）
output/
└── feat-009/
    ├── test_frame.jpg         # テスト用静止画
    ├── halpe26_keypoints.npy  # 結合結果（numpy配列）
    └── vis_halpe26.jpg        # 可視化画像
```

## 3. 技術スタック

既存の技術スタックのみ使用。追加ライブラリなし。

- Python 3.10.16
- MMPose 0.24.0（推論API）
- MMDetection 2.28.2（Faster R-CNN）
- PyTorch 2.11.0+cu128
- NumPy（キーポイント配列操作）
- OpenCV（画像読み込み・可視化・保存）

## 4. 各機能の詳細設計

### 4.1 結合スクリプト (FR-001)

#### データフロー

- **入力**:
  - 画像パス（コマンドライン引数）
  - 人物検出モデル設定/重み（ハードコード）
  - WholeBodyモデル設定/重み（ハードコード）
  - AICモデル設定/重み（ハードコード）
- **中間データ**:
  - WholeBody推定結果: list[dict]、各dictに `keypoints` (133, 3) を含む
  - AIC推定結果: list[dict]、各dictに `keypoints` (14, 3) を含む
- **出力**:
  - numpy配列 shape=(N, 26, 3)、N=検出人数
  - コンソール出力

#### 処理ロジック

```python
# scripts/merge_halpe26.py の擬似コード（意図の伝達が目的、そのままコピーして使うものではない）

# 1. モデル初期化
det_model = init_detector(det_config, det_checkpoint, device)
wb_model = init_pose_model(wb_config, wb_checkpoint, device)
aic_model = init_pose_model(aic_config, aic_checkpoint, device)

# 2. 人物検出（1回のみ）
mmdet_results = inference_detector(det_model, img)
person_results = process_mmdet_results(mmdet_results, cat_id=1)

# 3. WholeBody推定
wb_results, _ = inference_top_down_pose_model(
    wb_model, img, person_results, bbox_thr=0.3, format='xyxy',
    dataset=wb_dataset, dataset_info=wb_dataset_info)

# 4. AIC推定（同じperson_resultsを使用）
aic_results, _ = inference_top_down_pose_model(
    aic_model, img, person_results, bbox_thr=0.3, format='xyxy',
    dataset=aic_dataset, dataset_info=aic_dataset_info)

# 5. 結合
for person_idx in range(len(wb_results)):
    halpe26 = np.zeros((26, 3), dtype=np.float32)
    wb_kps = wb_results[person_idx]['keypoints']   # (133, 3)
    aic_kps = aic_results[person_idx]['keypoints']  # (14, 3)

    # WholeBody → HALPE マッピング
    halpe26[0:17] = wb_kps[0:17]     # HALPE 0-16 ← WholeBody 0-16
    halpe26[20] = wb_kps[17]          # HALPE 20 (LBigToe) ← WholeBody 17
    halpe26[22] = wb_kps[18]          # HALPE 22 (LSmallToe) ← WholeBody 18
    halpe26[24] = wb_kps[19]          # HALPE 24 (LHeel) ← WholeBody 19
    halpe26[21] = wb_kps[20]          # HALPE 21 (RBigToe) ← WholeBody 20
    halpe26[23] = wb_kps[21]          # HALPE 23 (RSmallToe) ← WholeBody 21
    halpe26[25] = wb_kps[22]          # HALPE 25 (RHeel) ← WholeBody 22

    # AIC → HALPE マッピング
    halpe26[17] = aic_kps[12]         # HALPE 17 (Head) ← AIC 12 (head_top)
    halpe26[18] = aic_kps[13]         # HALPE 18 (Neck) ← AIC 13 (neck)

    # Hip center 計算
    halpe26[19, :2] = (halpe26[11, :2] + halpe26[12, :2]) / 2  # 座標は中点
    halpe26[19, 2] = min(halpe26[11, 2], halpe26[12, 2])        # confidenceはmin
```

#### マッピング定義（完全な対応表）

| HALPE index | HALPE name | ソース | ソースindex | ソース名 |
|-------------|------------|--------|-------------|----------|
| 0 | Nose | WholeBody | 0 | nose |
| 1 | LEye | WholeBody | 1 | left_eye |
| 2 | REye | WholeBody | 2 | right_eye |
| 3 | LEar | WholeBody | 3 | left_ear |
| 4 | REar | WholeBody | 4 | right_ear |
| 5 | LShoulder | WholeBody | 5 | left_shoulder |
| 6 | RShoulder | WholeBody | 6 | right_shoulder |
| 7 | LElbow | WholeBody | 7 | left_elbow |
| 8 | RElbow | WholeBody | 8 | right_elbow |
| 9 | LWrist | WholeBody | 9 | left_wrist |
| 10 | RWrist | WholeBody | 10 | right_wrist |
| 11 | LHip | WholeBody | 11 | left_hip |
| 12 | RHip | WholeBody | 12 | right_hip |
| 13 | LKnee | WholeBody | 13 | left_knee |
| 14 | RKnee | WholeBody | 14 | right_knee |
| 15 | LAnkle | WholeBody | 15 | left_ankle |
| 16 | RAnkle | WholeBody | 16 | right_ankle |
| 17 | Head | AIC | 12 | head_top |
| 18 | Neck | AIC | 13 | neck |
| 19 | Hip | 計算 | - | (LHip + RHip) / 2 |
| 20 | LBigToe | WholeBody | 17 | left_big_toe |
| 21 | RBigToe | WholeBody | 20 | right_big_toe |
| 22 | LSmallToe | WholeBody | 18 | left_small_toe |
| 23 | RSmallToe | WholeBody | 21 | right_small_toe |
| 24 | LHeel | WholeBody | 19 | left_heel |
| 25 | RHeel | WholeBody | 22 | right_heel |

#### コマンドライン引数

```
usage: merge_halpe26.py [-h] --img IMG [--out-dir OUT_DIR] [--device DEVICE]
```

| 引数 | 型 | デフォルト | 説明 |
|------|-----|-----------|------|
| `--img` | str | 必須 | 入力画像パス |
| `--out-dir` | str | `output/feat-009` | 出力ディレクトリ |
| `--device` | str | `cuda:0` | 推論デバイス |

#### モデルパス（スクリプト内ハードコード）

```python
DET_CONFIG = 'checkpoints/faster_rcnn_r50_fpn_1x_coco.py'
DET_CHECKPOINT = 'checkpoints/faster_rcnn_r50_fpn_1x_coco_20200130-047c8118.pth'
WB_CONFIG = 'configs/wholebody/2d_kpt_sview_rgb_img/topdown_heatmap/coco-wholebody/ViTPose_huge_wholebody_256x192.py'
WB_CHECKPOINT = 'checkpoints/wholebody.pth'
AIC_CONFIG = 'configs/body/2d_kpt_sview_rgb_img/topdown_heatmap/aic/ViTPose_huge_aic_256x192.py'
AIC_CHECKPOINT = 'checkpoints/aic.pth'
```

#### 実行コマンド

カレントディレクトリは `/home/sakagawa/git/ViTPose` で実行すること。

```bash
mkdir -p output/feat-009
uv run python -c "
import cv2
cap = cv2.VideoCapture('/home/sakagawa/git/ViTPose_HuggingFace/input/cam05520129.mp4')
ret, frame = cap.read()
cv2.imwrite('output/feat-009/test_frame.jpg', frame)
cap.release()
"
uv run python scripts/merge_halpe26.py --img output/feat-009/test_frame.jpg --out-dir output/feat-009
```

#### WholeBodyとAICの人物対応

人物検出を1回のみ行い、同じ `person_results` を同じ `bbox_thr=0.3` でWholeBodyとAICの両方に渡す。`inference_top_down_pose_model` 内の `bbox_thr` フィルタリング（inference.py 380-384行目）は入力の `person_results` に対して行われるため、同一の入力・同一の閾値で同じフィルタリング結果となる。また、結果の順序は `person_results` の順序を保持する（inference.py 415行目の `zip`）。これにより、`wb_results[i]` と `aic_results[i]` が同じ人物に対応することが保証される。

#### エラーハンドリング

- 人物が検出されない場合: `person_results` が空リスト。空の結果を保存し、コンソールに「No person detected」と表示する
- WholeBodyとAICの結果数が一致しない場合: 同じ `person_results` を使うため原理的に発生しない。万一発生した場合は `raise RuntimeError(f'WholeBody results ({len(wb_results)}) and AIC results ({len(aic_results)}) count mismatch')` で停止する

#### 境界条件

- 画像内に人物がいない場合: halpe26_keypoints.npy の shape は (0, 26, 3) で保存
- 複数人物が検出された場合: 全員分の結合結果を配列に格納

### 4.2 可視化 (FR-002)

#### データフロー

- **入力**: テスト画像、HALPE 26キーポイント配列
- **出力**: `output/feat-009/vis_halpe26.jpg`

#### 処理ロジック

可視化は `merge_halpe26.py` 内に含める（別スクリプトにしない）。

描画仕様:
- 各キーポイントを円で描画（半径4、confidence > 0.3 のもののみ）
- キーポイントの色: 左側を緑 (0, 255, 0)、右側をオレンジ (255, 128, 0)、中央を青 (51, 153, 255)
- HALPE 26のスケルトン接続を線で描画（太さ2）
- 各キーポイントの横にindex番号を表示（デバッグ用）

HALPE 26 スケルトン定義（接続ペア）:

```python
HALPE26_SKELETON = [
    (0, 1), (0, 2), (1, 3), (2, 4),          # 顔
    (5, 7), (7, 9), (6, 8), (8, 10),          # 腕
    (5, 6), (5, 11), (6, 12), (11, 12),        # 胴体
    (11, 13), (13, 15), (12, 14), (14, 16),    # 脚
    (17, 18), (18, 5), (18, 6),                # Head-Neck-Shoulder
    (15, 20), (15, 22), (15, 24),              # 左足
    (16, 21), (16, 23), (16, 25),              # 右足
    (11, 19), (12, 19),                        # Hip center
]
```

キーポイントの色分け:

```python
HALPE26_COLORS = {
    # 中央（青）
    0: (51, 153, 255),   # Nose
    17: (51, 153, 255),  # Head
    18: (51, 153, 255),  # Neck
    19: (51, 153, 255),  # Hip
    # 左（緑）
    1: (0, 255, 0), 3: (0, 255, 0), 5: (0, 255, 0), 7: (0, 255, 0),
    9: (0, 255, 0), 11: (0, 255, 0), 13: (0, 255, 0), 15: (0, 255, 0),
    20: (0, 255, 0), 22: (0, 255, 0), 24: (0, 255, 0),
    # 右（オレンジ）
    2: (255, 128, 0), 4: (255, 128, 0), 6: (255, 128, 0), 8: (255, 128, 0),
    10: (255, 128, 0), 12: (255, 128, 0), 14: (255, 128, 0), 16: (255, 128, 0),
    21: (255, 128, 0), 23: (255, 128, 0), 25: (255, 128, 0),
}
```

#### エラーハンドリング

- 人物が検出されなかった場合: キーポイントなしの元画像をそのまま保存する

## 5. インターフェース定義

### merge_halpe26.py

```python
def merge_to_halpe26(
    wb_keypoints: np.ndarray,   # shape=(133, 3)
    aic_keypoints: np.ndarray,  # shape=(14, 3)
) -> np.ndarray:                # shape=(26, 3)
    """WholeBody 133とAIC 14のキーポイントをHALPE 26に結合する。"""

def draw_halpe26(
    img: np.ndarray,            # BGR画像
    keypoints: np.ndarray,      # shape=(26, 3)
    kpt_thr: float = 0.3,      # confidence閾値
) -> np.ndarray:                # 描画済みBGR画像
    """HALPE 26キーポイントを画像に描画する。"""
```

## 6. ファイル・ディレクトリ設計

セクション2のディレクトリ構成を参照。`scripts/` ディレクトリはgit管理対象。`output/` は `.gitignore` に含まれている。

## 7. ログ・デバッグ設計

- コンソールにINFOレベルの進捗メッセージを表示:
  - `Detecting persons...`
  - `Running WholeBody estimation... (N persons)`
  - `Running AIC estimation... (N persons)`
  - `Merging to HALPE 26...`
  - `Saved: {npy_path}`
  - `Saved: {vis_path}`
- 各人物のHALPE 26キーポイントをテーブル形式でコンソール出力

## 8. 設計判断

### 人物検出の共有

- **採用案**: 人物検出を1回のみ行い、WholeBodyとAICで共有する
- **却下案**: WholeBodyとAICで別々に人物検出する
- **理由**: 同じbounding boxを使うことで、結果の人物対応が保証される。別々に検出すると人物の対応付けが必要になり複雑化する

### スクリプト構成: 単一ファイル vs モジュール分割

- **採用案**: `scripts/merge_halpe26.py` の単一ファイル
- **却下案**: `scripts/` 内をモジュール分割（merge.py, visualize.py, config.py）
- **理由**: 現時点では機能がシンプルであり、単一ファイルで十分。feat-010でOpenPose JSON出力を追加する際に、必要に応じてリファクタリングする

### 可視化方法: OpenCV直接描画 vs MMPose vis_pose_result

- **採用案**: OpenCVで直接描画
- **却下案**: MMPoseの `vis_pose_result` を使用
- **理由**: `vis_pose_result` はdataset_infoに基づいて描画するため、HALPE 26に対応したdataset_infoが必要になる。HALPE 26のdataset_infoを新たに定義するよりも、OpenCVで直接描画する方がシンプル
