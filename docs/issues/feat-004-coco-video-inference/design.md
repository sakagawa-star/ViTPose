# 機能設計書: feat-004 COCO 17 動画推定

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001 | 4.1 ポーズ推定動画の生成 |

## 2. システム構成

新規ファイルの作成・既存ファイルの変更はなし。既存のデモスクリプト `demo/top_down_video_demo_with_mmdet.py` をCLIから実行する。

### ディレクトリ構成（変更後）

```
output/
└── feat-004/
    └── vis_cam05520129.mp4    # ポーズ推定結果の可視化動画
```

## 3. 技術スタック

既存の技術スタックのみ使用。追加ライブラリなし。

- Python 3.10.16
- MMPose 0.24.0（`demo/top_down_video_demo_with_mmdet.py`）
- MMDetection 2.28.2（Faster R-CNN による人物検出）
- PyTorch 2.11.0+cu128（GPU推論）
- OpenCV（動画の読み込み・書き出し）

## 4. 各機能の詳細設計

### 4.1 ポーズ推定動画の生成 (FR-001)

#### データフロー

- **入力**:
  - テスト動画: `/home/sakagawa/git/ViTPose_HuggingFace/input/cam05520129.mp4`（1920x1080, 30fps, 902フレーム）
  - 人物検出モデル設定: `checkpoints/faster_rcnn_r50_fpn_1x_coco.py`
  - 人物検出モデル重み: `checkpoints/faster_rcnn_r50_fpn_1x_coco_20200130-047c8118.pth`
  - ポーズ推定モデル設定: `configs/body/2d_kpt_sview_rgb_img/topdown_heatmap/coco/ViTPose_huge_coco_256x192.py`
  - ポーズ推定モデル重み: `checkpoints/coco.pth`（feat-002で分割済み）
- **出力**: `output/feat-004/vis_cam05520129.mp4`（mp4v コーデック、1920x1080, 30fps）

#### 処理ロジック

カレントディレクトリは `/home/sakagawa/git/ViTPose` で実行すること。

```bash
mkdir -p output/feat-004
uv run python demo/top_down_video_demo_with_mmdet.py \
    checkpoints/faster_rcnn_r50_fpn_1x_coco.py \
    checkpoints/faster_rcnn_r50_fpn_1x_coco_20200130-047c8118.pth \
    configs/body/2d_kpt_sview_rgb_img/topdown_heatmap/coco/ViTPose_huge_coco_256x192.py \
    checkpoints/coco.pth \
    --video-path /home/sakagawa/git/ViTPose_HuggingFace/input/cam05520129.mp4 \
    --out-video-root output/feat-004/
```

デモスクリプト内部の処理フロー（`demo/top_down_video_demo_with_mmdet.py`）:
1. `init_detector()` で Faster R-CNN を初期化（GPU上）
2. `init_pose_model()` で ViTPose++ Huge COCO を初期化（GPU上）
3. `cv2.VideoCapture` で入力動画を開く
4. `cv2.VideoWriter` で出力動画を作成（コーデック: mp4v、入力と同じfps・解像度）
5. 各フレームに対してループ:
   a. `inference_detector()` で人物bounding boxを検出
   b. `process_mmdet_results()` で person カテゴリ（cat_id=1）のみ抽出
   c. `inference_top_down_pose_model()` でポーズ推定（17キーポイント）
   d. `vis_pose_result()` でフレームにキーポイント＋スケルトンを描画
   e. `videoWriter.write()` で描画済みフレームを出力動画に書き込む
6. `cap.release()` / `videoWriter.release()` でリソース解放

出力ファイル名は `vis_{入力動画のbasename}`（105行目: `f'vis_{os.path.basename(args.video_path)}'`）で自動生成される。入力が `cam05520129.mp4` のため、出力は `vis_cam05520129.mp4` となる。

以下のパラメータはデモスクリプトのデフォルト値を使用するため、コマンドラインで明示的に指定しない:
- `--device cuda:0`（GPU推論）
- `--det-cat-id 1`（COCOのpersonカテゴリ）
- `--bbox-thr 0.3`（検出スコア閾値）
- `--kpt-thr 0.3`（キーポイントスコア閾値）
- `--radius 4`（キーポイント描画半径）
- `--thickness 1`（スケルトン線の太さ）

#### 検証コマンド

出力動画の解像度・フレーム数を確認する:

```bash
uv run python -c "
import cv2
cap = cv2.VideoCapture('output/feat-004/vis_cam05520129.mp4')
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)
cap.release()
print(f'Size={w}x{h}, Frames={total}, FPS={fps}')
"
```

期待値: `Size=1920x1080, Frames=902, FPS=30.0`

#### エラーハンドリング

- CUDA out of memory: 静止画1枚ずつの推論であるため、feat-003と同じVRAM使用量（8GB以下）。OOMが発生する可能性は低い。万一発生した場合はfeat-003設計書のOOM対処手順に従う
- 動画ファイルが開けない場合: `cv2.VideoCapture` の `isOpened()` が False となりassertで停止。動画パスを確認する
- 途中でフレーム読み込みが失敗した場合: `flag` が False になりループが正常終了。出力動画は読み込み成功分のフレームのみ含む

#### 境界条件

- 特定フレームで人物が検出されない場合: キーポイントなしのフレームが出力される（デモスクリプトはエラーにならない）
- 複数人物が検出された場合: 全員分のポーズが描画される

## 5. インターフェース定義

該当なし（新規コード作成なし。既存デモスクリプトをCLIから実行するのみ）

## 6. ファイル・ディレクトリ設計

セクション2のディレクトリ構成を参照。設定ファイルの新規作成はない。`output/` は `.gitignore` に含まれている。

## 7. ログ・デバッグ設計

該当なし（新規コード作成なし）

## 8. 設計判断

### デモスクリプトの選択: top_down_video_demo_with_mmdet.py

- **採用案**: `demo/top_down_video_demo_with_mmdet.py`
- **却下案**: `demo/top_down_pose_tracking_demo_with_mmdet.py`（トラッキング付き。本案件ではフレームごとの独立推定で十分）
- **理由**: 人物検出 + ポーズ推定のtop-downパイプラインを動画で実行できるデモスクリプト。トラッキングは不要
