# 機能設計書: feat-007 AIC 静止画推定

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001 | 4.1 テスト画像の準備 |
| FR-002 | 4.2 ポーズ推定の実行 |

## 2. システム構成

新規ファイルの作成・既存ファイルの変更はなし。既存のデモスクリプト `demo/top_down_img_demo_with_mmdet.py` をCLIから実行する。

### ディレクトリ構成（変更後）

```
output/
└── feat-007/
    ├── test_frame.jpg         # テスト用静止画（動画1フレーム目）
    └── vis_test_frame.jpg     # ポーズ推定結果の可視化画像
```

## 3. 技術スタック

既存の技術スタックのみ使用。追加ライブラリなし。

- Python 3.10.16
- MMPose 0.24.0（`demo/top_down_img_demo_with_mmdet.py`）
- MMDetection 2.28.2（Faster R-CNN による人物検出）
- PyTorch 2.11.0+cu128（GPU推論）

## 4. 各機能の詳細設計

### 4.1 テスト画像の準備 (FR-001)

#### データフロー

- **入力**: `/home/sakagawa/git/ViTPose_HuggingFace/input/cam05520129.mp4`（動画ファイル）
- **出力**: `output/feat-007/test_frame.jpg`（JPEG画像、動画の1フレーム目）

#### 処理ロジック

カレントディレクトリは `/home/sakagawa/git/ViTPose` で実行すること。

```bash
mkdir -p output/feat-007
uv run python -c "
import cv2
cap = cv2.VideoCapture('/home/sakagawa/git/ViTPose_HuggingFace/input/cam05520129.mp4')
ret, frame = cap.read()
assert ret, 'Failed to read video frame'
cv2.imwrite('output/feat-007/test_frame.jpg', frame)
cap.release()
print('Saved: output/feat-007/test_frame.jpg')
"
```

#### エラーハンドリング

- 動画ファイルが存在しない場合: `ret` が False になる。動画パスを確認する

### 4.2 ポーズ推定の実行 (FR-002)

#### データフロー

- **入力**:
  - テスト画像: `output/feat-007/test_frame.jpg`（JPEG, BGR, 動画のフレーム解像度）
  - 人物検出モデル設定: `checkpoints/faster_rcnn_r50_fpn_1x_coco.py`
  - 人物検出モデル重み: `checkpoints/faster_rcnn_r50_fpn_1x_coco_20200130-047c8118.pth`
  - ポーズ推定モデル設定: `configs/body/2d_kpt_sview_rgb_img/topdown_heatmap/aic/ViTPose_huge_aic_256x192.py`
  - ポーズ推定モデル重み: `checkpoints/aic.pth`（feat-002で分割済み）
- **出力**: `output/feat-007/vis_test_frame.jpg`（キーポイント＋スケルトン描画済みJPEG画像）

#### 処理ロジック

カレントディレクトリは `/home/sakagawa/git/ViTPose` で実行すること。

```bash
uv run python demo/top_down_img_demo_with_mmdet.py \
    checkpoints/faster_rcnn_r50_fpn_1x_coco.py \
    checkpoints/faster_rcnn_r50_fpn_1x_coco_20200130-047c8118.pth \
    configs/body/2d_kpt_sview_rgb_img/topdown_heatmap/aic/ViTPose_huge_aic_256x192.py \
    checkpoints/aic.pth \
    --img-root output/feat-007/ \
    --img test_frame.jpg \
    --out-img-root output/feat-007/
```

デモスクリプト内部の処理フロー（feat-003/005と同一のスクリプト）:
1. `init_detector()` で Faster R-CNN を初期化（GPU上）
2. `init_pose_model()` で ViTPose++ Huge AIC を初期化（GPU上）
3. `inference_detector()` で画像から人物bounding boxを検出
4. `process_mmdet_results()` で person カテゴリ（cat_id=1）のみ抽出
5. `inference_top_down_pose_model()` で各bounding box内のポーズ推定（14キーポイント）
6. `vis_pose_result()` で結果を可視化し、`output/feat-007/vis_test_frame.jpg` に保存（121行目: `f'vis_{args.img}'`）

以下のパラメータはデモスクリプトのデフォルト値を使用するため、コマンドラインで明示的に指定しない:
- `--device cuda:0`（GPU推論）
- `--det-cat-id 1`（COCOのpersonカテゴリ）
- `--bbox-thr 0.3`（検出スコア閾値）
- `--kpt-thr 0.3`（キーポイントスコア閾値）
- `--radius 4`（キーポイント描画半径）
- `--thickness 1`（スケルトン線の太さ）

#### チェックポイントのロードに関する確認事項

`aic.pth` は `model_split.py` で分割されたもの（expert 1、associate_keypoint_heads.0）。`init_pose_model()` は `strict=False`（mmcvデフォルト）でロードするため、`mlp.experts.*` の余分なキーが含まれていてもエラーにはならない。`associate_keypoint_heads.*` は分割時に除去済み。

#### backbone type=ViT の適合確認

`ViTPose_huge_aic_256x192.py` のbackbone typeは `ViT`（33行目: `type='ViT'`）であり、MoE分割後のチェックポイントと適合する。

#### エラーハンドリング

- CUDA out of memory: 静止画1枚の推論であるため、OOMが発生する可能性は低い
- 人物が検出されない場合: `--bbox-thr` を下げる（0.1）

#### 境界条件

- 画像内に人物がいない場合: キーポイントなしの画像が出力される
- 複数人物が検出された場合: 全員分のポーズが描画される

## 5. インターフェース定義

該当なし（新規コード作成なし）

## 6. ファイル・ディレクトリ設計

セクション2のディレクトリ構成を参照。`output/` は `.gitignore` に含まれている。

## 7. ログ・デバッグ設計

該当なし（新規コード作成なし）

## 8. 設計判断

### デモスクリプトの選択

- **採用案**: `demo/top_down_img_demo_with_mmdet.py`（feat-003/005と同一）
- **理由**: AICもtop-downパイプラインで推定可能。dataset_infoを設定ファイルから読み取るため、同じスクリプトが使える
