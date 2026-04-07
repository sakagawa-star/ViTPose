# feat-028: JSONにトラッキングID記録

## ステータス: Closed (2026-04-07)

## 概要

Re-IDパイプライン実行時に、各フレームのOpenPose JSONに `stable_id`（カスタムRe-IDが維持する安定ID）を記録する。これにより、後続の可視化・分析がJSONデータから直接行えるようになる。

## 成果物

- `scripts/postprocess_reid.py` — Re-IDポストプロセススクリプト（新規）
- `scripts/halpe26_to_openpose.py` — `stable_ids` オプション引数追加（将来のパイプライン統合用）
- `experiments/results/camSony1_L_reid_json/` — camSony1_L の stable_id 付きJSON（321,239ファイル）

## テスト結果

- camSony1_L.mp4（321,239フレーム）: 処理時間 1,773.8秒（181.1 fps）、ユニーク stable_id 845

## 依存

- feat-022（カスタムRe-IDモジュール）— 完了済み
- feat-025（BB重複除去方式）— 完了済み
