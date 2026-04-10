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

### Phase 5: 人物トラッキング（BoxMOT + Deep OC-SORT）

| ID | Title | 概要 | 依存 |
|----|-------|------|------|
| feat-019 | 人物トラッキング調査・ロードマップ | トラッキング手法の調査と段階的実装計画の作成 | - |
| feat-020 | BoxMOT環境構築 | boxmotインストール | feat-019 |
| feat-021 | 既存JSON+動画でBoxMOT動作検証 | 出力済みJSON(bbox)と元動画でDeep OC-SORTの動作確認（ViTPose推論不要） | feat-020 |
| feat-022 | 病室動画トラッキング・Re-ID検証 | 病室動画でトラッキング精度を目視確認 | feat-021 |
| feat-023 | YOLOX-l検出器検証 | 臥位人物検出の改善検証（Faster R-CNN→YOLOX-l） | feat-022 |
| feat-024 | YOLO11x検出器検証 | YOLOX-lで不十分な動画に対しYOLO11xで検出精度を検証 | feat-023 |
| feat-025 | BB重複除去方式の比較（案A vs 案E） | 外接矩形再推定(A) vs スコア最大BB選択(E)の精度比較CLI | feat-024 |
| feat-028 | JSONにトラッキングID記録 | person_idにstable_idを記録 | feat-025 |
| feat-026 | 見切れ再同定の検証 | 見切れ場面でID維持されるか確認。JSONに保存されたstable_idを使い可視化で検証 | feat-028 |
| feat-029 | トラッキング付き動画可視化 | ID別色分け描画 | feat-028 |
| feat-027 | Deep OC-SORT + HALPE 26統合 | パイプラインにDeep OC-SORTを統合（凍結中: feat-026の結果次第でスキップの可能性あり） | feat-026 |
| feat-030 | 患者ID特定スクリプト | 最長出現IDを患者として特定 | feat-028 |
| feat-031 | 患者フィルタリング | 指定IDのキーポイントのみ抽出 | feat-030 |

## Open

| ID | Type | Title | Status |
|----|------|-------|--------|
| feat-029 | feat | トラッキング付き動画可視化 | Closed |
| feat-026 | feat | 見切れ再同定の検証 | Open |
| feat-025 | feat | BB重複除去方式の比較（案A vs 案E） | Closed |
| feat-024 | feat | YOLO11x検出器検証 | Closed |
| feat-023 | feat | YOLOX-l検出器検証 | Closed |
| feat-020 | feat | BoxMOT環境構築 | Closed |
| feat-021 | feat | 既存JSON+動画でBoxMOT動作検証 | Closed |
| feat-022 | feat | 病室動画トラッキング・Re-ID検証 | Closed |
| feat-001 | feat | MMPose環境構築・動作確認 | Closed |
| feat-002 | feat | MoEチェックポイントDL・分割 | Closed |
| feat-003 | feat | COCO 17 静止画推定 | Closed |
| feat-004 | feat | COCO 17 動画推定 | Closed |
| feat-005 | feat | WholeBody 静止画推定 | Closed |
| feat-006 | feat | WholeBody 動画推定 | Closed |
| feat-007 | feat | AIC 静止画推定 | Closed |
| feat-008 | feat | AIC 動画推定 | Closed |
| feat-009 | feat | WholeBody + AIC結合ロジック | Closed |
| feat-010 | feat | OpenPose JSON出力 | Closed |
| feat-011 | feat | 結合結果の可視化・検証 | Closed |
| feat-012 | feat | HALPE 26統合パイプライン | Closed |
| feat-013 | feat | バウンディングボックス描画 | Closed |
| feat-014 | feat | パイプライン処理速度プロファイリング | Closed |
| feat-015 | feat | WholeBody/AIC並列推論 | Closed (効果なし、コード戻し) |
| bug-001 | bug | プロファイル表示で変数fpsが動画FPSを上書き | Closed |
| bug-002 | bug | --mode json時にout_pathが未定義で参照されるリスク | Closed |
| feat-016 | feat | JSONにBBスコアを保存 | Closed |
| feat-017 | feat | キーポイント描画のconfidence閾値を引数指定可能にする | Closed |
| feat-018 | feat | JSONにBBのROI座標を保存 | Closed |

## Closed

| ID | Type | Title | Resolved |
|----|------|-------|----------|
| feat-001 | feat | MMPose環境構築・動作確認 | 2026-03-28 |
| feat-002 | feat | MoEチェックポイントDL・分割 | 2026-03-28 |
| feat-003 | feat | COCO 17 静止画推定 | 2026-03-28 |
| feat-004 | feat | COCO 17 動画推定 | 2026-03-28 |
| feat-005 | feat | WholeBody 静止画推定 | 2026-03-28 |
| feat-006 | feat | WholeBody 動画推定 | 2026-03-28 |
| feat-007 | feat | AIC 静止画推定 | 2026-03-28 |
| feat-008 | feat | AIC 動画推定 | 2026-03-28 |
| feat-009 | feat | WholeBody + AIC結合ロジック | 2026-03-28 |
| feat-010 | feat | OpenPose JSON出力 | 2026-03-28 |
| feat-011 | feat | 結合結果の可視化・検証 | 2026-03-28 |
| feat-012 | feat | HALPE 26統合パイプライン | 2026-03-28 |
| feat-013 | feat | バウンディングボックス描画 | 2026-03-28 |
| feat-014 | feat | パイプライン処理速度プロファイリング | 2026-03-28 |
| feat-015 | feat | WholeBody/AIC並列推論 | 2026-03-28 (効果なし、コード戻し) |
| bug-001 | bug | プロファイル表示で変数fpsが動画FPSを上書き | 2026-03-29 |
| bug-002 | bug | --mode json時にout_pathが未定義で参照されるリスク | 2026-03-29 |
| feat-016 | feat | JSONにBBスコアを保存 | 2026-03-29 |
| feat-017 | feat | キーポイント描画のconfidence閾値を引数指定可能にする | 2026-03-29 |
| feat-018 | feat | JSONにBBのROI座標を保存 | 2026-03-29 |
| feat-019 | feat | 人物トラッキング調査・ロードマップ | 2026-03-29 |
| feat-020 | feat | BoxMOT環境構築 | 2026-03-30 |
| feat-021 | feat | 既存JSON+動画でBoxMOT動作検証 | 2026-03-30 |
| feat-022 | feat | 病室動画トラッキング・Re-ID検証 | 2026-04-06 |
| feat-023 | feat | YOLOX-l検出器検証 | 2026-04-03 |
| feat-024 | feat | YOLO11x検出器検証 | 2026-04-03 |
| feat-025 | feat | BB重複除去方式の比較（案A vs 案E） | 2026-04-09 |
| feat-028 | feat | JSONにトラッキングID記録 | 2026-04-07 |
| feat-029 | feat | トラッキング付き動画可視化 | 2026-04-07 |
