# feat-037: pink_track_id 時系列可視化グラフ

## ステータス

**Closed**（2026-04-16 完了）

## 完了結果サマリ

- camSony1_S（900 フレーム）/ camSony1_L（321,239 フレーム）ともに 5 パネル PNG を正常出力
- camSony1_L のグラフ目視により、feat-033 `pink_id` の誤検出（動画終盤の患者不在区間で `pink_id=1` が検出される）を発見。本案件の「pink_track_id の正常性を目視で判断する」目的を達成

## 概要

feat-036 で付与した `pink_track_id` が正常に動作しているかを目視確認するため、時系列グラフを出力するスクリプトを作成する。動画上への描画は別案件とし、本案件はグラフ（PNG 画像）の出力のみをスコープとする。

## 親案件

- feat-036: postprocess_patient_id.py 実装（本案件の入力 JSON を生成）

## 可視化項目

1. **pink_track_id=1 の有無**（二値タイムライン）
2. **BB 数の内訳**（フレームごとの `pink_track_id=1` / `-1` / `-2` の個数）
3. **pink_track_id=1 BB の track_id 値の推移**（患者の track_id がいつ切り替わるか）
4. **pink_track_id=1 BB の bbox_score の推移**
5. **pink_id の情報**（pink_id=1 の有無タイムライン等）

## 入出力

### 入力

- `--json-dir`: feat-036 出力の JSON ディレクトリ（`pink_track_id` / `track_id` / `pink_id` / `bbox_score` 付き）

### 出力

- `--out-dir` または `--out-path` で指定した PNG 画像

## 対象動画

- camSony1_S（900 フレーム）で動作確認
- camSony1_L（321K フレーム）で本番検証

## スコープ外

- 動画上への BB / スケルトン描画（別案件）
- pink_track_id の修正・再計算
- OpenCV / 動画ファイルの参照

## 技術スタック

- matplotlib（グラフ描画）
- 標準ライブラリ（json, pathlib, argparse 等）

## 関連案件

- feat-036: postprocess_patient_id.py（入力 JSON の生成元）
- feat-029: visualize_tracking.py（既存の可視化スクリプト、参考）
