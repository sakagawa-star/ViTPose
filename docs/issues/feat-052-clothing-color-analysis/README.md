# feat-052: 服パッチ静止画からの服色特徴量分析・HSVレンジ提案ツール

## ステータス

Open（要求仕様書・機能設計書 作成中）

## 概要

対象の服パッチ静止画1枚を入力に、ViTPose（画像全体を1BBとして推論）で胴体ROIを切り出し、その領域のHSV色特徴量を測定（出力a）し、`postprocess_pink_id.py` 用の推奨 `FIXED_HSV_RANGES` / `MIN_PINK_RATIO` を提案（出力b）するCLI診断ツール。

新規スクリプト: `scripts/analyze_clothing_color.py`

## 背景

本番対象動画にピンク対象追跡（feat-033 `postprocess_pink_id.py`）を適用したが、HSVピンク判定の色特徴量（`FIXED_HSV_RANGES` / `MIN_PINK_RATIO`）がテスト動画（`pink_tracker_jhub.py`）由来のまま流用されており、本番対象の服色とズレている。

本番対象の服パッチ静止画 `testdata/E0014-01.png`（顔・全身なし、プライバシー保護済み）を入手。このフレームは本番処理で `pink_id=1` と判定されなかった取りこぼし実例。

事前実測（中央矩形ROIでの粗検証。ViTPose導入前の手動確認）:

- 現状レンジでの pink_ratio = 0.0273（閾値 0.03 を下回る＝取りこぼしと整合）
- S（彩度）中央値 26、`S>=60` を満たす画素はわずか 4.2% → 淡いピンクが現状レンジで拾えない主因
- H（色相）が p5=1 / p95=177 と両端に割れる＝赤/ピンクの色相環またぎ
- おすすめ方式（色相環対応＋S/V下限データ駆動＋無彩色除去）の試作レンジで pink_ratio = 0.53 に改善（約19倍）

## 成果物

- `scripts/analyze_clothing_color.py`（新規）
- `requirements.md` — 要求仕様書（REQUIREMENTS_STANDARD.md 準拠）
- `design.md` — 機能設計書（DESIGN_STANDARD.md 準拠）

## 関連案件

- feat-033: 服装の色による対象同定（`postprocess_pink_id.py`、`FIXED_HSV_RANGES` / `MIN_PINK_RATIO` の出自）
- feat-046: keypoint-rect ROI 対応（`build_keypoint_rect_roi` を再利用）
- feat-050: `--min-pink-ratio` CLI 引数化
- feat-051: selection_score 範囲フレーム抽出ツール（ピンク服 vs 灰色服の pink_ratio 同水準問題＝HSV限界の構造問題を提起）
