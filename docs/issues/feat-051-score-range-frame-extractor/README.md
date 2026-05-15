# feat-051: selection_score 範囲によるフレーム抽出 PNG ツール

## ステータス
Closed

## 概要

`postprocess_pink_id.py --roi-mode keypoint-rect` 出力 JSON ディレクトリと動画を入力に、**各フレームの最大 selection_score (`s = pink_ratio + 0.05 × iou_with_prev`) が指定範囲内にあるフレーム**を抽出し、PNG として出力する新規スクリプトを作成する。

## 背景

`--min-pink-ratio`（feat-050）の閾値設定に向けて、特定 `s` 帯域（例: `0.10 < s < 0.12`）に該当するフレームを目視確認したい。閾値境界付近で何が誤判定 / 正判定されているかを把握することが目的。

`visualize_disagreement_frames.py`（feat-048）は disagreement フレーム限定、`visualize_patient_video.py`（feat-038/042）は動画形式、どちらも本要求を満たさない。

## 用途

- camSony1_L 321K フレームから `s` 帯域別のサンプルを取得
- bug-004（ROI 品質ガード）/ HSV レンジ調整など下流案件の判断材料
