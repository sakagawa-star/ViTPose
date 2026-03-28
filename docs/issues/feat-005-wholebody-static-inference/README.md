# feat-005: WholeBody 静止画推定

## ステータス: Closed (2026-03-28)

## 概要

分割済み ViTPose++ Huge（WholeBody）チェックポイントを使い、病室動画の1フレーム目に対してCOCO-WholeBody 133キーポイントのポーズ推定と可視化を実行した。

## 実行コマンド

```bash
uv run python demo/top_down_img_demo_with_mmdet.py \
    checkpoints/faster_rcnn_r50_fpn_1x_coco.py \
    checkpoints/faster_rcnn_r50_fpn_1x_coco_20200130-047c8118.pth \
    configs/wholebody/2d_kpt_sview_rgb_img/topdown_heatmap/coco-wholebody/ViTPose_huge_wholebody_256x192.py \
    checkpoints/wholebody.pth \
    --img-root output/feat-005/ \
    --img test_frame.jpg \
    --out-img-root output/feat-005/
```

## 確認結果

- デモスクリプトがエラーなく完了
- `wholebody.pth` のロード時に `mlp.experts.*` の unexpected key 警告が出るが、`strict=False`（mmcvデフォルト）により正常動作（`associate_keypoint_heads.*` は分割時に除去済み）
- 出力画像 `output/feat-005/vis_test_frame.jpg` に体・顔・手のキーポイントとスケルトンが正しく描画されていることを目視確認済み
