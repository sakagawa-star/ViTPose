# bug-005: run_halpe26_pipeline_yolo11.py で --device に cuda:0 以外を指定すると IndexError で異常終了する

## ステータス
- Open（修正計画レビュー中）

## 概要
`scripts/run_halpe26_pipeline_yolo11.py` に `--device cuda:1` など「cuda:0 以外」の GPU を
指定すると、ポーズ推論の冒頭フレームで `IndexError: list index out of range`
（`torch/nn/parallel/_functions.py` の `_get_stream` 内）が発生して落ちる。
`--device cuda:0`（デフォルト）のときだけ正常動作し、cuda:1 / cuda:6 など 0 以外の
インデックスはすべて失敗する。マルチGPUマシンで GPU0 以外を使えない。

## 環境
- ホスト: マルチGPU環境（`torch.cuda.device_count() = 7`）
- Python 3.10 / torch 2.11.0+cu128 / mmcv-full 1.7.2 / mmpose 0.24.0 / ultralytics 8.4.33
- 対象スクリプト: `scripts/run_halpe26_pipeline_yolo11.py`（YOLO11x検出器版）

## 再現手順
GPU0 以外を `--device` に指定して実行する（例: cuda:1）。

```bash
uv run python scripts/run_halpe26_pipeline_yolo11.py \
    --video   <任意の動画>.mp4 \
    --out-dir <出力先>/ \
    --bbox-thr 0.3 --oks-thr 0.5 \
    --device cuda:1
```

モデルのロード〜"Models initialized" / "Processing video" までは正常に進み、
最初のフレームのポーズ推論で異常終了する。

## 期待する動作
`--device cuda:1` を指定したら物理GPU1で推論が走り、最後まで完走する。

## 暫定回避策（利用者側）
物理GPUは `CUDA_VISIBLE_DEVICES` で選び、`--device` は cuda:0（デフォルト）のまま使う。

```bash
CUDA_VISIBLE_DEVICES=1 uv run python scripts/run_halpe26_pipeline_yolo11.py \
    --video <動画>.mp4 --out-dir <出力先>/ \
    --bbox-thr 0.3 --oks-thr 0.5 --device cuda:0
```
