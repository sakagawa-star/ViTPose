# feat-003: COCO 17 静止画推定

## ステータス: Closed (2026-03-28)

## 概要

分割済み ViTPose++ Huge（COCO）チェックポイントを使い、室内動画の1フレーム目に対してCOCO 17キーポイントのポーズ推定と可視化を実行した。

## 実行コマンド

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

## 確認結果

- デモスクリプトがエラーなく完了
- `coco.pth` のロード時に `associate_keypoint_heads.*` / `mlp.experts.*` の unexpected key 警告が出るが、`strict=False`（mmcvデフォルト）により正常動作
- 出力画像 `output/feat-003/vis_test_frame.jpg` にキーポイントとスケルトンが正しく描画されていることを目視確認済み
