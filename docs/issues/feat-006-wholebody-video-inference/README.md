# feat-006: WholeBody 動画推定

## ステータス: Closed (2026-03-28)

## 概要

ViTPose++ Huge（WholeBody分割チェックポイント）を使い、室内動画（30.1秒, 902フレーム）に対してCOCO-WholeBody 133キーポイントのポーズ推定と可視化動画出力を実行した。

## 実行コマンド

```bash
uv run python demo/top_down_video_demo_with_mmdet.py \
    checkpoints/faster_rcnn_r50_fpn_1x_coco.py \
    checkpoints/faster_rcnn_r50_fpn_1x_coco_20200130-047c8118.pth \
    configs/wholebody/2d_kpt_sview_rgb_img/topdown_heatmap/coco-wholebody/ViTPose_huge_wholebody_256x192.py \
    checkpoints/wholebody.pth \
    --video-path /home/sakagawa/git/ViTPose_HuggingFace/input/cam05520129.mp4 \
    --out-video-root output/feat-006/
```

## 確認結果

- デモスクリプトがエラーなく完了
- 出力動画: `output/feat-006/vis_cam05520129.mp4` (29MB, 1920x1080, 902フレーム, 30fps)
- 体・顔・手のキーポイントとスケルトンが正しく描画されていることを目視確認済み
