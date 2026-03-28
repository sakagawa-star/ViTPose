# 要求仕様書: feat-009 WholeBody + AIC結合ロジック

## 1. プロジェクト概要

- **何を作るか**: WholeBody 133キーポイントとAIC 14キーポイントの推定結果を結合し、HALPE 26キーポイントを生成するPythonスクリプトを作成する。静止画1枚に対して動作確認を行う
- **なぜ作るか**: HALPE 26にはHead/Neck（AICから取得）、足6点（WholeBodyから取得）、Hip center（計算で生成）が必要であり、単一データセットの推定では取得できない。2つのデータセットの推定結果を結合することで、HALPE 26相当のキーポイントを得る
- **誰が使うか**: 開発者（自分自身）。後続のfeat-010（OpenPose JSON出力）、feat-011（可視化・検証）の基盤
- **どこで使うか**: ローカルGPU環境（RTX 5060 Ti, CUDA 12.8）

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| HALPE 26 | 26キーポイント定義。COCO 17 + Head + Neck + Hip center + 足6点。本プロジェクトのターゲット出力 |
| WholeBody 133 | COCO-WholeBody Datasetの133キーポイント。先頭23点（body 17 + foot 6）からHALPE 0-16, 20-25を取得する |
| AIC 14 | AI Challenger Datasetの14キーポイント。index 12（head_top）とindex 13（neck）からHALPE 17, 18を取得する |
| Hip center | HALPE 19。LHip（HALPE 11）とRHip（HALPE 12）の座標の中点として計算する |
| キーポイント配列 | numpy配列 shape=(K, 3)。各行は [x, y, confidence] |

## 3. 機能要求一覧

### FR-001: 結合スクリプトの作成

- **機能名**: WholeBody + AIC → HALPE 26 結合スクリプト
- **概要**: 入力画像に対してWholeBody推定とAIC推定を行い、結果を結合してHALPE 26キーポイントを出力するPythonスクリプトを作成する
- **入力**:
  - テスト画像: `output/feat-009/test_frame.jpg`（動画1フレーム目）
  - 人物検出モデル: Faster R-CNN（R-50-FPN）
  - WholeBodyモデル: `checkpoints/wholebody.pth` + `ViTPose_huge_wholebody_256x192.py`
  - AICモデル: `checkpoints/aic.pth` + `ViTPose_huge_aic_256x192.py`
- **出力**:
  - コンソールに各人物のHALPE 26キーポイント（26行、各行: index, name, x, y, confidence）を表示
  - `output/feat-009/halpe26_keypoints.npy` に結合結果をnumpy配列として保存（shape: (num_persons, 26, 3)）
- **受け入れ基準**:
  - スクリプト `scripts/merge_halpe26.py` が存在する
  - スクリプトがエラーなく実行完了する
  - コンソール出力に26キーポイント（index 0〜25）が表示される
  - 各キーポイントのconfidenceが0.0より大きい（人物が検出された場合）
  - `output/feat-009/halpe26_keypoints.npy` が存在し、shape が (N, 26, 3) である（Nは検出人数、1以上）

### FR-002: マッピングの正しさの検証

- **機能名**: キーポイントマッピングの正しさの確認
- **概要**: 結合結果のHALPE 26キーポイントが正しい位置にマッピングされていることを検証する
- **入力**: FR-001の出力（`halpe26_keypoints.npy`）とテスト画像
- **出力**: `output/feat-009/vis_halpe26.jpg`（HALPE 26キーポイントを描画した画像）
- **受け入れ基準**:
  - `output/feat-009/vis_halpe26.jpg` が存在する
  - 目視で以下を確認:
    - HALPE 0-16（COCO 17相当）が正しい位置にある
    - HALPE 17（Head）が頭頂付近にある
    - HALPE 18（Neck）が首の付け根付近にある
    - HALPE 19（Hip center）が左右Hip の中間にある
    - HALPE 20-25（足6点）の左右が正しい

## 4. 非機能要求

- **処理時間**: 静止画1枚の推定（WholeBody + AIC 2回推定 + 結合 + 可視化）が120秒以内に完了する
- **GPU使用**: CUDA対応GPUで推論する
- **信頼性**: 出力ファイルは再実行により再生成可能

## 5. 制約条件

- MMPoseの推論API（`inference_top_down_pose_model`, `init_pose_model`, `process_mmdet_results`）を使用する
- 人物検出は1回のみ行い、WholeBodyとAICの2回の推定で共有する
- 結合ロジックのスクリプトは `scripts/merge_halpe26.py` に配置する
- 可視化はOpenCVで行う（MMPoseの`vis_pose_result`はHALPE 26に対応していないため、独自に描画する）

## 6. 優先順位

| ID | 優先度 | 備考 |
|----|--------|------|
| FR-001 | Must | 結合ロジックの核心 |
| FR-002 | Must | マッピングの正しさ確認は必須 |

MVP: FR-001〜FR-002すべて
