# feat-021: 既存JSON+動画でBoxMOT動作検証

## ステータス: Closed (2026-03-30)

## 結果

- 1244フレーム全てエラーなく処理完了（Skipped: 0）
- メインの人物にID 1が1006フレーム付与（全体の81%）
- 処理時間: 14.5秒（85.7 fps）
- 322フレーム（26%）でMMDet誤検出による2人目の低スコアbboxあり（bbox_thr=0.3が低いため）。パイプライン統合時に対処予定

## 概要

パイプライン出力済みのOpenPose JSON（bbox + bbox_score）と元動画を使い、ViTPose推論なしでDeep OC-SORTの動作を確認する。

## 依存

- feat-020（BoxMOT環境構築）
