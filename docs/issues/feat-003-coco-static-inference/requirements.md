# 要求仕様書: feat-003 COCO 17 静止画推定

## 1. プロジェクト概要

- **何を作るか**: 分割済み ViTPose++ Huge（COCO）チェックポイントを使って、静止画1枚に対してCOCO 17キーポイントのポーズ推定を行い、結果を可視化する
- **なぜ作るか**: feat-002で分割したチェックポイントが正しく動作することを確認する。後続の動画推定（feat-004）やマルチデータセット結合（feat-009〜011）の基盤となる
- **誰が使うか**: 開発者（自分自身）
- **どこで使うか**: ローカルGPU環境（RTX 5060 Ti, CUDA 12.8）

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| COCO 17 | COCO Keypoints Dataset の17キーポイント定義（nose, left_eye, right_eye, left_ear, right_ear, left_shoulder, right_shoulder, left_elbow, right_elbow, left_wrist, right_wrist, left_hip, right_hip, left_knee, right_knee, left_ankle, right_ankle） |
| top-down推定 | まず人物検出（bounding box）を行い、各検出領域ごとにポーズ推定を行う方式 |
| strict=False | PyTorchのチェックポイントロード時に、モデル定義に存在しないキーを無視するオプション。mmcvの `load_checkpoint` のデフォルト値 |

## 3. 機能要求一覧

### FR-001: テスト画像の準備

- **機能名**: テスト用静止画の準備
- **概要**: テスト用動画の1フレーム目を静止画として抽出する
- **入力**: テスト用動画 `/home/sakagawa/git/ViTPose_HuggingFace/input/cam05520129.mp4`
- **出力**: `output/feat-003/test_frame.jpg`
- **受け入れ基準**:
  - `output/feat-003/test_frame.jpg` が存在する
  - 画像ファイルとして開くことができる（0バイトでない）
- **備考**: feat-001で `output/feat-001/test_frame.jpg` として同じ抽出を行っているが、feat-003用に別ディレクトリに出力する

### FR-002: ViTPose++ Huge（COCO）による静止画ポーズ推定

- **機能名**: COCO 17キーポイントの静止画推定と可視化
- **概要**: Faster R-CNN で人物検出を行い、ViTPose++ Huge（COCO分割チェックポイント）で COCO 17キーポイントを推定し、結果を可視化画像として出力する
- **入力**:
  - テスト画像: `output/feat-003/test_frame.jpg`（FR-001の出力）
  - 人物検出モデル: Faster R-CNN（R-50-FPN）— feat-001でDL済み
  - ポーズ推定モデル: ViTPose++ Huge COCO — `checkpoints/coco.pth`（feat-002で分割済み）
  - ポーズ推定設定: `configs/body/2d_kpt_sview_rgb_img/topdown_heatmap/coco/ViTPose_huge_coco_256x192.py`
- **出力**: `output/feat-003/vis_test_frame.jpg`（キーポイントとスケルトンが描画された画像）
- **受け入れ基準**:
  - `output/feat-003/vis_test_frame.jpg` が存在する
  - 出力画像を目視で確認し、少なくとも1人分のキーポイント（色付きの点）とスケルトン（キーポイント間の色付き接続線）が描画されていること
  - デモスクリプトがエラーなく完了する

## 4. 非機能要求

- **処理時間**: 静止画1枚の推定（人物検出 + ポーズ推定 + 可視化）が60秒以内に完了する
- **GPU使用**: CUDA対応GPUで推論する（デモスクリプトのデフォルト: `cuda:0`）
- **信頼性**: 出力ファイルは再実行により再生成可能。データ消失の許容範囲に制約なし

## 5. 制約条件

- 既存のデモスクリプト `demo/top_down_img_demo_with_mmdet.py` をそのまま使用する（コード変更しない）
- 人物検出モデルはfeat-001でDL済みの Faster R-CNN（R-50-FPN）を再利用する
- ポーズ推定設定ファイルは既存の `ViTPose_huge_coco_256x192.py` を使用する（backbone type=`ViT` であり、MoE分割後のチェックポイントと適合することを確認済み）
- チェックポイントのロードは `mmcv.runner.load_checkpoint` のデフォルト（`strict=False`）で行われるため、分割後のstate_dictに不要キー（`associate_keypoint_heads.*`, `mlp.experts.*`）が含まれていてもエラーにはならない
- ネットワーク接続は不要（チェックポイント・モデルはすべてローカルにDL済み）
- VRAM使用量: ViTPose++ Huge + Faster R-CNN の合計で8GB以下（RTX 5060 Ti 16GBで動作可能）

## 6. 優先順位

| ID | 優先度 | 備考 |
|----|--------|------|
| FR-001 | Must | FR-002の前提 |
| FR-002 | Must | 本案件の主目的 |

MVP: FR-001〜FR-002すべて
