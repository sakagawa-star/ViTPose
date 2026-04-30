# feat-042: visualize_patient_video.py に pink 選択診断フィールドを描画する拡張

## ステータス

Closed（2026-04-30）。実装・自動検証（`build_debug_label` 7 ケース全パス、CLI ヘルプ表示確認）完了。手動テストは bug-003 修正後の `/tmp/bug003_test/vis_pink_id_all_camSony1_L.mp4` 出力で 5 フィールドが BB に正しく描画されていることを確認。

## 概要

既存 `scripts/visualize_patient_video.py` を拡張し、feat-041 で JSON に追加された診断フィールド（`bb_index` / `pink_id` / `pink_ratio` / `iou_with_prev` / `selection_score`）を BB 内部に 1 行で描画する。フィールドごとに ON/OFF を切替可能な CLI フラグを追加し、デフォルトは全 ON。

これにより、誤選択区間（camSony1_L フレーム 29519–30915 など、ピンク患者の前を別人が通り過ぎた直後に `pink_id=1` が別人に固定される現象）で「どの BB がどの `selection_score` で選ばれたか」が動画上で直接確認できるようになる。

## なぜ作るのか

- 現状の BB ラベルは `pid:1 0.91`（id_type 値 + bbox_score）のみで情報量が不足し、`pink_id` の誤選択原因を動画上で特定できない
- feat-041 で診断フィールドが JSON に書かれたが、JSON だけでは「動画上のどの BB か」の対応付けが困難
- 同フレームに複数 BB がある場合、`bb_index` を表示すれば JSON との突合が即座に可能になる

## スコープ

- `scripts/visualize_patient_video.py` の BB ラベル生成部分を拡張
- フィールドごとの ON/OFF フラグ（5 個）を追加
- 全 `--id-type` × `--mode` 組合せで動作（既存の動作を維持）
- 表示位置: BB 内部、1 行
- 数値の桁数: 小数 3 桁

## スコープ外

- 新規可視化スクリプトの作成
- JSON 仕様の変更（feat-041 で確定済み）
- グラフ系スクリプト（feat-040 等）の拡張
- 連続性ボーナス重み 0.05 の妥当性検証（別案件候補）

## 親案件・関連案件

- 親: feat-038（`visualize_patient_video.py` 本体）
- 兄弟: feat-041（描画対象フィールドを JSON に追加）
- 後続: 誤選択区間（フレーム 29519–30915）の本格解析（別案件候補）
