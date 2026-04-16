# feat-038: pink_track_id / pink_id / track_id 動画可視化

## ステータス

**Closed**（2026-04-17 完了）

## 完了結果サマリ

- camSony1_S（900 フレーム）/ camSony1_L（321,239 フレーム）ともに MP4 出力を確認
- filter モード（pink_track_id=1 のみ描画）/ all モード（全 BB 色分け）ともに動作確認済み

## 概要

`scripts/visualize_patient_video.py`（新規）を作成する。feat-036 出力の JSON と元動画を入力として、選択した ID（`pink_track_id` / `pink_id` / `track_id`）に基づいて BB・ID テキスト・キーポイント・スケルトンを元動画にオーバーレイした MP4 を出力する。

## 親案件

- feat-036: postprocess_patient_id.py（入力 JSON の生成元）
- feat-037: pink_track_id 時系列可視化グラフ（グラフ版の可視化、本案件は動画版）

## 主要機能

- **ID 選択**: `--id-type` で `pink_track_id` / `pink_id` / `track_id` を選択
- **描画モード**: `--mode filter`（指定 ID 値の BB のみ描画）/ `--mode all`（全 BB を色分け描画）
- **描画要素**: BB、ID 値テキスト、bbox_score、キーポイント、HALPE 26 スケルトン
- **フレーム指定**: `--draw-start` / `--draw-end` で描画フレーム範囲を指定。範囲外は素通し（動画全体は出力）

## スコープ外

- pink_id / track_id / pink_track_id の計算・再計算
- グラフ出力（feat-037 で対応済み）

## 関連案件

- feat-036: postprocess_patient_id.py
- feat-037: plot_pink_track_timeline.py
- feat-029: visualize_tracking.py（既存、`stable_id` ベース。流儀参考）
