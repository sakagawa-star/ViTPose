# feat-055: analyze_clothing_color.py の複数画像入力・プール提案・閾値検証対応

## ステータス

Closed（2026-05-28 完了。`testdata/E0014/` 3枚で全AC PASS、手動テストOK）

## 概要

`scripts/analyze_clothing_color.py` を拡張し、**複数の服パッチ静止画**を一度に入力して、
全画像を覆う**単一の HSV 設定（`--hsv-config` 互換 JSON）**を提案できるようにする。

現状は静止画 1 枚専用で、患者ごとに複数枚（角度・照明違い）から共通の HSV レンジを作る
作業は使い捨てスクリプトでの手動プールに頼っていた（feat-055 着手の直接の動機）。
これを再現性のある正式ツールに昇格させる。

## 背景

- feat-052 で 1 枚→推奨レンジ、feat-054 で `--hsv-config` 互換 JSON 出力を実装済み。
- `testdata/E0014/` の 3 枚で「全画像 `pink_ratio > 0.03`」を満たす単一設定を求める調査を実施。
  - 現状の `FIXED_HSV_RANGES` では 3 枚中 2 枚が 0.03 未満（0.0099 / 0.0035）で失格。
  - 全 ROI のクロマ画素をプールして 1 セット提案すると、3 枚の ratio = 0.5928 / 0.7701 / 0.7049
    と全て大幅に 0.03 を超えることを確認（レンジ 2 本、min 0.5928）。
- この「プール提案」を正式機能として `analyze_clothing_color.py` に組み込む。

## 関連案件

- feat-052: 服色特徴量分析・HSVレンジ提案ツール（本ツールの基盤）
- feat-053: postprocess_pink_id.py の `--hsv-config` 読み込み（出力 JSON の消費先）
- feat-054: analyze_clothing_color.py の `--hsv-config` 互換 JSON 出力（単一画像版、本案件で複数画像へ拡張）
