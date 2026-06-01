# feat-047: ROI モード比較・可視化ツール

## ステータス
Closed

## 概要

feat-046 で導入される `--roi-mode {bb, keypoint-rect}` の効果を定量・定性的に検証するための比較ツール群を新規作成する:

- `scripts/compare_roi_modes.py`: 2 つのモードで生成された JSON ディレクトリを比較し、α-1（同一フレームの pink_ratio 直接比較）と不一致フレームリストを出力
- `scripts/visualize_disagreement_frames.py`: 不一致フレームリストと動画を入力に、不一致フレームの目視確認用 PNG を出力

## なぜ作るのか

- feat-046 のクローズ判定（「認識率が上がるかどうか」）には、bb モードと keypoint-rect モードの並走比較が必須
- 「擬似正解の循環参照」を避けるため、両モードで `pink_id=1` の選択結果が一致しない（=不一致）フレームを抽出し、人間が目視判定する運用にする
- 判定指標は 2 つ:
  - **α-1**: 同一フレームの bb pink_ratio vs keypoint-rect pink_ratio 散布図
  - **δ（不一致目視）**: bb モードと keypoint-rect モードで pink_id=1 を付けた人物が異なるフレームを抽出 → 目視で「どちらが正しい」を判定
- camSony1_S は単一人物のため α 検証用、camSony1_L は複数人物のため δ 検証用

## スコープ

- `scripts/compare_roi_modes.py` を新規作成: 比較 CSV + α-1 散布図 PNG
- `scripts/visualize_disagreement_frames.py` を新規作成: 不一致フレーム PNG 群（V-2 案）
- サンプリング機能（不一致が多すぎる場合の目視負荷軽減）

## スコープ外

- pink_id 検出ロジックの変更（feat-046 で実施済み）
- 自動的な「正解判定」アルゴリズム（目視判定が前提）
- 動画形式での比較出力（V-1 / V-3 は不採用、静止画 V-2 のみ）
- 青対象検証（別案件で）

## 親案件・関連案件

- 親: feat-046（本案件の検証対象）
- 関連: feat-038（`visualize_patient_video.py`、描画パターンの参考）
