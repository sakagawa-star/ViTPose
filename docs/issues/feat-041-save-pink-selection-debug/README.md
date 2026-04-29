# feat-041: postprocess_pink_id.py に選択スコア診断フィールド追加

## ステータス

Open（requirements.md / design.md 未作成）

## 概要

`scripts/postprocess_pink_id.py` の出力 JSON の各 `people[i]` に、`pink_id` 選択スコアの内訳を診断するための 3 フィールドを追加する。feat-039 の `pink_ratio` 追加と同じ「生 dict 保持設計」に従い、選択ロジック・CLI・サマリ出力は変更しない。

追加フィールド:

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `iou_with_prev` | `float \| null` | 前フレーム選択 BB との IoU。値域 [0.0, 1.0]。前フレーム選択 BB が無い（連続性切れ直後）の場合は `null` |
| `selection_score` | `float \| null` | 当該 BB の選択スコア = `pink_ratio + IOU_CONT_WEIGHT × iou_with_prev`。`iou_with_prev` が `null` のときは `null` |
| `bb_index` | `int` | 同フレームの `people` リスト内連番（0, 1, 2, …）。JSON 上の BB と動画上の BB を一意に対応付ける |

## なぜ作るのか

現行の `pink_id` 選択ロジック `score = pink_ratio + 0.05 × IoU(prev, current)` の計算過程が JSON に残っていないため、誤選択（典型例: ピンク患者の前を別人が通り過ぎてからずっとその別人に `pink_id=1` が付き続ける）の原因が IoU 連続性ボーナスによる逆転かどうか判別できない。本案件で内訳を保存することで:

- 連続性ボーナスが選択を反転させたフレームを定量的に特定可能
- ピンク患者復帰時に誤選択がロックインする現象を時系列で観察可能（feat-040 のグラフ拡張で活用）
- `bb_index` により「同フレームの何番目の BB か」が JSON だけで確定し、可視化動画と JSON の対応が容易になる

## スコープ

- `scripts/postprocess_pink_id.py` のみ修正
- 出力 JSON の `people[i]` に上記 3 フィールドを追加
- 連続性切れ時の値規約: 案 B（`iou_with_prev` / `selection_score` を `null` で事実保存）

## スコープ外

- `pink_id` 選択ロジックの変更
- 連続性ボーナス重み `IOU_CONT_WEIGHT = 0.05` の調整・廃止
- 動画への描画拡張（feat-042 で対応予定）
- `bb_index` を上流（`run_halpe26_pipeline_yolo11.py`）で付与する案

## 親案件・関連案件

- 親: feat-033（`postprocess_pink_id.py` 本体）
- 兄弟: feat-039（`pink_ratio` 追加、本案件と同じ「診断フィールド追加」設計パターン）
- 後続: feat-042（動画描画拡張、本案件のフィールドを活用）
- 利用先: feat-040（時系列グラフ、本案件のフィールドを活用したパネル拡張は将来案件で）
