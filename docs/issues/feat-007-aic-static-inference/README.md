# feat-007: AIC 静止画推定

## ステータス: Closed (2026-03-28)

## 概要

分割済み ViTPose++ Huge（AIC）チェックポイントを使い、病室動画の1フレーム目に対してAIC 14キーポイントのポーズ推定と可視化を実行した。Head/Neckキーポイントの描画を確認。

## 実行コマンド

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

## 確認結果

- デモスクリプトがエラーなく完了
- `aic.pth` のロード時に `mlp.experts.*` の unexpected key 警告が出るが正常動作
- 出力画像 `output/feat-007/vis_test_frame.jpg` にAIC 14キーポイント（Head/Neck含む）とスケルトンが正しく描画されていることを目視確認済み
