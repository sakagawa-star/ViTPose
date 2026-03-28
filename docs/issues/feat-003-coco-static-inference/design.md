# 機能設計書: feat-003 COCO 17 静止画推定

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
└── feat-003/
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
- **出力**: `output/feat-003/test_frame.jpg`（JPEG画像、動画の1フレーム目）

#### 処理ロジック

カレントディレクトリは `/home/sakagawa/git/ViTPose` で実行すること。

```bash
mkdir -p output/feat-003
uv run python -c "
import cv2
cap = cv2.VideoCapture('/home/sakagawa/git/ViTPose_HuggingFace/input/cam05520129.mp4')
ret, frame = cap.read()
assert ret, 'Failed to read video frame'
cv2.imwrite('output/feat-003/test_frame.jpg', frame)
cap.release()
print('Saved: output/feat-003/test_frame.jpg')
"
```

#### エラーハンドリング

- 動画ファイルが存在しない場合: `cv2.VideoCapture` がフレームを返せず `ret` が False になる。動画パスを確認する
- cv2がインストールされていない場合: feat-001で `opencv-python` はmmpose依存として既にインストール済みのため発生しない

### 4.2 ポーズ推定の実行 (FR-002)

#### データフロー

- **入力**:
  - テスト画像: `output/feat-003/test_frame.jpg`（JPEG, BGR, 動画のフレーム解像度）
  - 人物検出モデル設定: `checkpoints/faster_rcnn_r50_fpn_1x_coco.py`
  - 人物検出モデル重み: `checkpoints/faster_rcnn_r50_fpn_1x_coco_20200130-047c8118.pth`
  - ポーズ推定モデル設定: `configs/body/2d_kpt_sview_rgb_img/topdown_heatmap/coco/ViTPose_huge_coco_256x192.py`
  - ポーズ推定モデル重み: `checkpoints/coco.pth`（feat-002で分割済み）
- **出力**: `output/feat-003/vis_test_frame.jpg`（キーポイント＋スケルトン描画済みJPEG画像）

#### 処理ロジック

カレントディレクトリは `/home/sakagawa/git/ViTPose` で実行すること。

```bash
uv run python demo/top_down_img_demo_with_mmdet.py \
    checkpoints/faster_rcnn_r50_fpn_1x_coco.py \
    checkpoints/faster_rcnn_r50_fpn_1x_coco_20200130-047c8118.pth \
    configs/body/2d_kpt_sview_rgb_img/topdown_heatmap/coco/ViTPose_huge_coco_256x192.py \
    checkpoints/coco.pth \
    --img-root output/feat-003/ \
    --img test_frame.jpg \
    --out-img-root output/feat-003/
```

デモスクリプト内部の処理フロー（`demo/top_down_img_demo_with_mmdet.py`）:
1. `init_detector()` で Faster R-CNN を初期化（GPU上）
2. `init_pose_model()` で ViTPose++ Huge COCO を初期化（GPU上）
3. `inference_detector()` で画像から人物bounding boxを検出
4. `process_mmdet_results()` で person カテゴリ（cat_id=1）のみ抽出
5. `inference_top_down_pose_model()` で各bounding box内のポーズ推定（17キーポイント）
6. `vis_pose_result()` で結果を可視化し、`--out-img-root` と `vis_{--img}` を結合したパス（`output/feat-003/vis_test_frame.jpg`）に保存（121行目: `f'vis_{args.img}'`）

以下のパラメータはデモスクリプトのデフォルト値を使用するため、コマンドラインで明示的に指定しない:
- `--device cuda:0`（GPU推論）
- `--det-cat-id 1`（COCOのpersonカテゴリ）
- `--bbox-thr 0.3`（検出スコア閾値）
- `--kpt-thr 0.3`（キーポイントスコア閾値）
- `--radius 4`（キーポイント描画半径）
- `--thickness 1`（スケルトン線の太さ）

#### チェックポイントのロードに関する確認事項

`coco.pth` は `model_split.py` で分割されたもの。分割後のstate_dictには以下の特徴がある:
- `keypoint_head.final_layer` はCOCO 17チャネル（トリミング不要）
- `associate_keypoint_heads.*` キーが残存している（COCO分割のコードパス（model_split.py 34-43行目）には `associate_keypoint_heads` の削除処理が含まれていないため）
- `mlp.experts.*` キーが残存している（非COCOデータセットの分割でも、model_split.py 98行目のバグ `if 'expert' in keys:` が `if 'expert' in key:` の誤りのため削除されないが、COCO分割ではそもそもこの削除ループを通らない）

`init_pose_model()` は内部で `mmcv.runner.load_checkpoint(model, checkpoint, map_location='cpu')` を呼び出す（`mmpose/apis/inference.py` 42行目）。`mmcv.runner.load_checkpoint` のデフォルトは `strict=False` であるため、state_dictに `associate_keypoint_heads.*` や `mlp.experts.*` の余分なキーが含まれていてもエラーにはならない。不要キーは無視され、モデル定義に対応するキーのみがロードされる。

#### backbone type=ViT の適合確認

`ViTPose_huge_coco_256x192.py` のbackbone typeは `ViT`（47行目: `type='ViT'`）であり、`ViTMoE` ではない。MoE分割後のチェックポイント（expertをfc2に結合済みのViT構造）と適合する。

#### エラーハンドリング

- CUDA out of memory: 静止画1枚の推論であるため、OOMが発生する可能性は低い（ViTPose++ Huge + Faster R-CNNの合計でVRAM 8GB以下）。万一発生した場合は以下の手順で対処する:
  1. `cp configs/body/2d_kpt_sview_rgb_img/topdown_heatmap/coco/ViTPose_huge_coco_256x192.py configs/body/2d_kpt_sview_rgb_img/topdown_heatmap/coco/ViTPose_huge_coco_256x192_noflip.py`
  2. コピーしたファイルの `flip_test=True` を `flip_test=False` に変更
  3. デモスクリプトの pose_config 引数をコピーしたファイルに差し替えて再実行
- チェックポイントのキー不一致: 上記「チェックポイントのロードに関する注意」の対処方法に従う
- 人物が検出されない場合: `--bbox-thr` を下げる（0.1など）。ただし病室動画の1フレーム目は人が映っているため、通常は検出される

#### 境界条件

- 画像内に人物がいない場合: デモスクリプトはエラーにならず、キーポイントなしの画像が出力される
- 複数人物が検出された場合: 全員分のポーズが描画される

## 5. インターフェース定義

該当なし（新規コード作成なし。既存デモスクリプトをCLIから実行するのみ）

## 6. ファイル・ディレクトリ設計

セクション2のディレクトリ構成を参照。設定ファイルの新規作成はない。`output/` は `.gitignore` に含まれている。

## 7. ログ・デバッグ設計

該当なし（新規コード作成なし。デモスクリプトの標準出力でエラーを確認する）

## 8. 設計判断

### デモスクリプトの選択: top_down_img_demo_with_mmdet.py

- **採用案**: `demo/top_down_img_demo_with_mmdet.py`
- **却下案**: `demo/top_down_img_demo.py`（ground-truth bbox必要）、`demo/top_down_video_demo_with_mmdet.py`（動画用、feat-004のスコープ）
- **理由**: 人物検出 + ポーズ推定のtop-downパイプラインを静止画で実行できる唯一のデモスクリプト

### 人物検出モデル: Faster R-CNN の再利用

- **採用案**: feat-001でDL済みの Faster R-CNN（R-50-FPN）を再利用
- **却下案**: YOLOXなど他の検出モデルをDL
- **理由**: 既にcheckpointsに存在し、動作確認済み。本案件の目的はViTPose++の動作確認であり、検出モデルの精度は副次的
