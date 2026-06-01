# feat-009: WholeBody + AIC結合ロジック

## ステータス: Closed (2026-03-28)

## 概要

WholeBody 133キーポイントとAIC 14キーポイントの推定結果を結合し、HALPE 26キーポイントを生成するスクリプト `scripts/merge_halpe26.py` を作成した。

## マッピング

- HALPE 0-16: WholeBody 0-16（COCO 17相当）
- HALPE 17 (Head): AIC 12 (head_top)
- HALPE 18 (Neck): AIC 13 (neck)
- HALPE 19 (Hip center): (LHip + RHip) / 2
- HALPE 20-25 (足6点): WholeBody 17-22

## 確認結果

- 静止画での結合が正常動作（26キーポイントすべて出力）
- 目視確認はfeat-011で実施（Pexels全身動画 + 室内動画）
