# feat-039: postprocess_pink_id.py に pink_ratio フィールド追加（デバッグ用）

## ステータス

Open（requirements.md / design.md 未作成）

## 概要

`scripts/postprocess_pink_id.py` が出力する JSON の各 `people[i]` に、当該 BB の HSV ピンク画素比率（`pink_ratio`: float、値域 [0.0, 1.0]）を追加する。

現在のスクリプトは各 BB のピンク比率を内部で計算しているが、選択結果である `pink_id`（1 / -1）しか JSON に残していない。デバッグ・閾値チューニング時に「なぜこの BB が選ばれた／選ばれなかったのか」を後追いで調べられるよう、比率そのものを保存する。

## 目的

- feat-037 の時系列グラフで検出された `pink_id` 誤検出（患者不在区間での `pink_id=1` 検出）の原因解析を容易にする
- `MIN_PINK_RATIO = 0.03` 閾値の妥当性を後段で再評価可能にする
- デバッグ専用フィールド。下流スクリプト（feat-035 / 036 / 037 / 038）の挙動は変えない

## スコープ

- `scripts/postprocess_pink_id.py` のみ修正
- 出力 JSON の `people[i]` に `pink_ratio` フィールドを追加
- bbox 欠損 person（`bb is None`）の扱いをドキュメントで明記

## スコープ外

- 閾値の変更・可変化
- 下流スクリプトでの `pink_ratio` 活用（別案件）
- 可視化（`plot_pink_track_timeline.py` 等への組み込み）

## 参考

- 参照スクリプト: `scripts/postprocess_pink_id.py`
- 親案件: feat-033（服装の色による患者同定）
