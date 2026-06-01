# feat-056: postprocess_pink_id.py に確認動画同時出力（--visualize）を統合

## ステータス

Closed（2026-05-28 完了。camSony1_S 900 フレームで全 AC PASS、手動テスト目視 OK）

## 概要

`scripts/postprocess_pink_id.py` に `--visualize` オプションを追加し、pink_id を付与した
JSON の書き出しと**同時に**、確認用の MP4（BB・スケルトン・pink_id ラベルをオーバーレイ）
を出力できるようにする。

描画ロジックは新規に書かず、`scripts/visualize_patient_video.py` の描画関数を import して
再利用する。`visualize_patient_video.py` 自体は無変更。

## 背景・動機

- 現状、対象同定結果を目視確認するには次の 2 コマンドを毎回手動で順に実行している:
  1. `postprocess_pink_id.py`（pink_id 付与 JSON 出力）
  2. `visualize_patient_video.py --id-type pink_id --mode filter`（確認 MP4 出力）
- この 2 連続実行が手間。さらに**動画フルスキャンが 2 回**走り非効率（pink_id 計算で 1 回、
  描画で 1 回）。
- 調査の結果、`postprocess_pink_id.py` のフレームループは描画に必要なもの（フレーム BGR
  画像・pink_id 付与済み person dict）をその場ですべて保持しているため、ループ末尾に描画
  ブロックを足すだけで MP4 を同時生成でき、動画読み込みを 1 回に削減できると判明した。

## スコープ

- 対象 ID は `pink_id` のみ（postprocess_pink_id.py 直後に存在する ID 種別）。
- 描画モードは `filter`（特定 pink_id 値のみ描画）をデフォルトとし、`all`（全 BB 色分け）も選択可。
- `track_id` / `pink_track_id` の可視化、付与済み JSON の再描画は従来どおり
  `visualize_patient_video.py` を使う（本統合の対象外）。

## 関連案件・ファイル

- feat-033: postprocess_pink_id.py 本体（pink_id 付与）
- feat-038: visualize_patient_video.py（描画関数の提供元）
- feat-050: `--min-pink-ratio` CLI 化
- feat-053: `--hsv-config` 読み込み
- `scripts/postprocess_pink_id.py` — 本案件で改修
- `scripts/visualize_patient_video.py` — 描画関数の import 元（無変更）
