# 要求仕様書: feat-008 AIC 動画推定

## 1. プロジェクト概要

- **何を作るか**: ViTPose++ Huge（AIC分割チェックポイント）を使って、室内動画に対してAIC 14キーポイントのポーズ推定を行い、結果を可視化動画として出力する
- **なぜ作るか**: feat-007で静止画推定を確認した。本案件では動画全フレームに対する推定が安定して動作することを確認する。特にHead/Neckが全フレームで正しく出力されるかを確認し、後続のHALPE 26結合（feat-009〜011）の基盤とする
- **誰が使うか**: 開発者（自分自身）
- **どこで使うか**: ローカルGPU環境（RTX 5060 Ti, CUDA 12.8）

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| AIC 14 | AI Challenger Datasetの14キーポイント定義（RShoulder, RElbow, RWrist, LShoulder, LElbow, LWrist, RHip, RKnee, RAnkle, LHip, LKnee, LAnkle, Head, Neck） |
| Head/Neck | AIC固有のキーポイント。HALPE 26のHead(17)/Neck(18)に対応する |

## 3. 機能要求一覧

### FR-001: 室内動画に対するAIC 14ポーズ推定動画の生成

- **機能名**: AIC 14キーポイントの動画推定と可視化
- **概要**: Faster R-CNN で各フレームの人物検出を行い、ViTPose++ Huge（AIC）でAIC 14キーポイントを推定し、全フレームの結果を可視化動画として出力する
- **入力**:
  - テスト動画: `/home/sakagawa/git/ViTPose_HuggingFace/input/cam05520129.mp4`（1920x1080, 30fps, 902フレーム, 30.1秒）
  - 人物検出モデル: Faster R-CNN（R-50-FPN）— feat-001でDL済み
  - ポーズ推定モデル: ViTPose++ Huge AIC — `checkpoints/aic.pth`（feat-002で分割済み）
  - ポーズ推定設定: `configs/body/2d_kpt_sview_rgb_img/topdown_heatmap/aic/ViTPose_huge_aic_256x192.py`
- **出力**: `output/feat-008/vis_cam05520129.mp4`（キーポイントとスケルトンが描画された動画）
- **受け入れ基準**:
  - `output/feat-008/vis_cam05520129.mp4` が存在する
  - 出力動画が再生可能である
  - 出力動画の解像度が入力動画と同一（1920x1080）である
  - 出力動画のフレーム数が入力動画と同一（902フレーム）である
  - デモスクリプトがエラーなく完了する
  - 出力動画を目視で確認し、少なくとも1人分のキーポイント（色付きの点）とスケルトン（色付き接続線）が描画されていること
  - Head/Neckのキーポイントが描画されていること

## 4. 非機能要求

- **処理時間**: 902フレームの推定が30分以内に完了する
- **GPU使用**: CUDA対応GPUで推論する（デモスクリプトのデフォルト: `cuda:0`）
- **信頼性**: 出力ファイルは再実行により再生成可能。データ消失の許容範囲に制約なし

## 5. 制約条件

- 既存のデモスクリプト `demo/top_down_video_demo_with_mmdet.py` をそのまま使用する（コード変更しない）
- 人物検出モデルはfeat-001でDL済みの Faster R-CNN（R-50-FPN）を再利用する
- ポーズ推定設定ファイルは既存の `ViTPose_huge_aic_256x192.py` を使用する（backbone type=`ViT`、MoE分割後のチェックポイントと適合）
- チェックポイントのロードは `mmcv.runner.load_checkpoint` のデフォルト（`strict=False`）で行われるため、不要キーが含まれていてもエラーにはならない
- ネットワーク接続は不要

## 6. 優先順位

| ID | 優先度 | 備考 |
|----|--------|------|
| FR-001 | Must | 本案件の主目的 |

MVP: FR-001
