# feat-020: BoxMOT環境構築

## ステータス: Closed (2026-03-30)

## 結果

- boxmot 16.0.11 インストール成功（既存パッケージへの影響なし）
- `from boxmot import DeepOcSort` インポート確認済み
- トラッカー初期化確認済み（Re-IDモデル OSNet 自動DL済み）
- 実APIのクラス名は `DeepOcSort`（Web情報の `DeepOCSORT` ではない）
- コンストラクタ引数: `reid_weights` / `half`（`model_weights` / `fp16` ではない）

## 概要

BoxMOTパッケージを現環境にインストールし、Deep OC-SORTが利用可能な状態にする。

## 依存

- feat-019（人物トラッキング調査・ロードマップ）
