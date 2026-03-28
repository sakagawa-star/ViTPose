# 要求仕様書: feat-007 AIC 静止画推定

## 1. プロジェクト概要

- **何を作るか**: 分割済み ViTPose++ Huge（AIC）チェックポイントを使って、静止画1枚に対してAIC 14キーポイントのポーズ推定を行い、結果を可視化する
- **なぜ作るか**: AIC 14キーポイントにはHead/Neckが含まれており、HALPE 26結合（feat-009〜011）で必要となる。feat-002で分割したAICチェックポイントが正しく動作することを確認する
- **誰が使うか**: 開発者（自分自身）
- **どこで使うか**: ローカルGPU環境（RTX 5060 Ti, CUDA 12.8）

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| AIC 14 | AI Challenger Datasetの14キーポイント定義（RShoulder, RElbow, RWrist, LShoulder, LElbow, LWrist, RHip, RKnee, RAnkle, LHip, LKnee, LAnkle, Head, Neck） |
| Head/Neck | AIC固有のキーポイント。COCO 17やWholeBody 133には含まれず、HALPE 26のHead(17)/Neck(18)に対応する |

## 3. 機能要求一覧

### FR-001: テスト画像の準備

- **機能名**: テスト用静止画の準備
- **概要**: テスト用動画の1フレーム目を静止画として抽出する
- **入力**: テスト用動画 `/home/sakagawa/git/ViTPose_HuggingFace/input/cam05520129.mp4`
- **出力**: `output/feat-007/test_frame.jpg`
- **受け入れ基準**:
  - `output/feat-007/test_frame.jpg` が存在する
  - 画像ファイルとして開くことができる（0バイトでない）

### FR-002: ViTPose++ Huge（AIC）による静止画ポーズ推定

- **機能名**: AIC 14キーポイントの静止画推定と可視化
- **概要**: Faster R-CNN で人物検出を行い、ViTPose++ Huge（AIC分割チェックポイント）でAIC 14キーポイントを推定し、結果を可視化画像として出力する
- **入力**:
  - テスト画像: `output/feat-007/test_frame.jpg`（FR-001の出力）
  - 人物検出モデル: Faster R-CNN（R-50-FPN）— feat-001でDL済み
  - ポーズ推定モデル: ViTPose++ Huge AIC — `checkpoints/aic.pth`（feat-002で分割済み）
  - ポーズ推定設定: `configs/body/2d_kpt_sview_rgb_img/topdown_heatmap/aic/ViTPose_huge_aic_256x192.py`
- **出力**: `output/feat-007/vis_test_frame.jpg`（キーポイントとスケルトンが描画された画像）
- **受け入れ基準**:
  - `output/feat-007/vis_test_frame.jpg` が存在する
  - 出力画像を目視で確認し、少なくとも1人分のキーポイント（色付きの点）とスケルトン（色付き接続線）が描画されていること
  - Head/Neckのキーポイントが描画されていること（AIC固有の確認）
  - デモスクリプトがエラーなく完了する

## 4. 非機能要求

- **処理時間**: 静止画1枚の推定（人物検出 + ポーズ推定 + 可視化）が60秒以内に完了する
- **GPU使用**: CUDA対応GPUで推論する（デモスクリプトのデフォルト: `cuda:0`）
- **信頼性**: 出力ファイルは再実行により再生成可能。データ消失の許容範囲に制約なし

## 5. 制約条件

- 既存のデモスクリプト `demo/top_down_img_demo_with_mmdet.py` をそのまま使用する（コード変更しない）
- 人物検出モデルはfeat-001でDL済みの Faster R-CNN（R-50-FPN）を再利用する
- ポーズ推定設定ファイルは既存の `ViTPose_huge_aic_256x192.py` を使用する（backbone type=`ViT`、MoE分割後のチェックポイントと適合）
- チェックポイントのロードは `mmcv.runner.load_checkpoint` のデフォルト（`strict=False`）で行われるため、分割後のstate_dictに不要キーが含まれていてもエラーにはならない（feat-003, feat-005で確認済み）
- ネットワーク接続は不要

## 6. 優先順位

| ID | 優先度 | 備考 |
|----|--------|------|
| FR-001 | Must | FR-002の前提 |
| FR-002 | Must | 本案件の主目的 |

MVP: FR-001〜FR-002すべて
