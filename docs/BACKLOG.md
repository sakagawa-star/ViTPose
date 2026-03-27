# Backlog

## ロードマップ

ViTPose++ MoEモデルを使い、HALPE 26相当のキーポイントをOpenPose JSON形式で出力することが最終目標。
段階的に各データセットの推論を単独で動作確認し、最後に結合する。

### Phase 0: 環境準備

| ID | Title | 概要 | 依存 |
|----|-------|------|------|
| feat-001 | MMPose環境構築・動作確認 | MMPose + mmcv + MMDetection の環境構築。既存デモスクリプトで動作確認 | - |
| feat-002 | MoEチェックポイントDL・分割 | ViTPose++ Huge MoEモデルをOneDriveからDLし、model_split.pyで6データセット分に分割 | feat-001 |

### Phase 1: COCO 17キーポイント推定

| ID | Title | 概要 | 依存 |
|----|-------|------|------|
| feat-003 | COCO 17 静止画推定 | 分割済みcoco.pth + COCO設定で静止画1枚のポーズ推定・可視化 | feat-002 |
| feat-004 | COCO 17 動画推定 | COCO 17で病室動画のポーズ推定・可視化動画出力 | feat-003 |

### Phase 2: COCO-WholeBody 133キーポイント推定

| ID | Title | 概要 | 依存 |
|----|-------|------|------|
| feat-005 | WholeBody 静止画推定 | 分割済みwholebody.pth + WholeBody設定で静止画1枚のポーズ推定・可視化 | feat-002 |
| feat-006 | WholeBody 動画推定 | WholeBody 133で動画推定。足6点(BigToe/SmallToe/Heel)が正しく出力されるか確認 | feat-005 |

### Phase 3: AIC 14キーポイント推定

| ID | Title | 概要 | 依存 |
|----|-------|------|------|
| feat-007 | AIC 静止画推定 | 分割済みaic.pth + AIC設定で静止画1枚のポーズ推定・可視化 | feat-002 |
| feat-008 | AIC 動画推定 | AIC 14で動画推定。Head/Neckが正しく出力されるか確認 | feat-007 |

### Phase 4: HALPE 26結合出力

| ID | Title | 概要 | 依存 |
|----|-------|------|------|
| feat-009 | WholeBody + AIC結合ロジック | WholeBody(23点)とAIC(Head/Neck)のマッピング + Hip center計算 | feat-006, feat-008 |
| feat-010 | OpenPose JSON出力 | Pose2Sim互換のOpenPose JSONフォーマットで26キーポイントを出力 | feat-009 |
| feat-011 | 結合結果の可視化・検証 | HALPE 26の可視化動画作成。キーポイント位置・左右の正しさを目視確認 | feat-010 |

## Open

| ID | Type | Title | Status |
|----|------|-------|--------|
| feat-001 | feat | MMPose環境構築・動作確認 | Not Started |
| feat-002 | feat | MoEチェックポイントDL・分割 | Not Started |
| feat-003 | feat | COCO 17 静止画推定 | Not Started |
| feat-004 | feat | COCO 17 動画推定 | Not Started |
| feat-005 | feat | WholeBody 静止画推定 | Not Started |
| feat-006 | feat | WholeBody 動画推定 | Not Started |
| feat-007 | feat | AIC 静止画推定 | Not Started |
| feat-008 | feat | AIC 動画推定 | Not Started |
| feat-009 | feat | WholeBody + AIC結合ロジック | Not Started |
| feat-010 | feat | OpenPose JSON出力 | Not Started |
| feat-011 | feat | 結合結果の可視化・検証 | Not Started |

## Closed

| ID | Type | Title | Resolved |
|----|------|-------|----------|
