# feat-053: postprocess_pink_id.py の HSV 設定ファイル読み込み対応

## 概要

`scripts/postprocess_pink_id.py` に CLI 引数 `--hsv-config <path>` を追加し、ハードコードされた `FIXED_HSV_RANGES`（ピンク判定の HSV レンジ集合）と `min_pink_ratio`（pink_id=1 候補の最低 pink_ratio）を JSON 設定ファイルから差し替え可能にする。

## ステータス

Open（要求仕様・設計レビュー中）

## 背景

feat-052（服色特徴量分析ツール）の調査で、本番対象の淡いピンク服が、テスト動画由来でハードコードされた `FIXED_HSV_RANGES` とズレており pink_ratio が取りこぼされる（実例 `E0014-01.png` で current pink_ratio=0.0099、推奨レンジでは 0.6046）ことが判明した。推奨レンジの算出ツールはできたが、それを `postprocess_pink_id.py` に反映する手段がソースコードのハードコード編集しかなく、対象ごとの差し替えができない。

## 位置づけ（案C / 機能①）

色特徴量を `postprocess_pink_id.py` へ渡す方式として **案C（設定ファイル経由 + 分析ツール側の JSON 出力連携）** を採用。本案件はそのうち以下に分割した 2 機能の **機能①（コア）**:

- **機能①（本案件 feat-053）**: `postprocess_pink_id.py` が設定ファイルから `fixed_hsv_ranges` + `min_pink_ratio` を読む。`compute_pink_ratio` を引数化。未指定時は従来定数（後方互換）
- **機能②（後続案件）**: `analyze_clothing_color.py` が本案件と同一スキーマの JSON を出力し、手写経をなくす

## スコープ

- **IN**: `--hsv-config` の追加、設定ファイルのスキーマ検証、`min_pink_ratio` の優先順位解決、`compute_pink_ratio` 引数化、サマリ表示
- **OUT**: `analyze_clothing_color.py` の JSON 出力（機能②、別案件）／ デフォルトレンジそのものの変更 ／ CLI への数値レンジ引数追加 ／ 出力 JSON フィールド追加

## 主要な設計決定（議論で確定）

- 渡し方: **案C**（設定ファイル経由）
- 設定ファイルの項目: **`fixed_hsv_ranges` + `min_pink_ratio` の2項目**（`sat_min/val_min` は postprocess に概念がないため含めない）
- スキーマのキーは **両方必須**（B-1）
- `min_pink_ratio` の優先順位: **CLI明示 > 設定ファイル > デフォルト0.03**（A-1）
- `compute_pink_ratio(roi, ranges=None)` で None 時はグローバル `FIXED_HSV_RANGES` 参照（`analyze_clothing_color.py` 後方互換）
- `FIXED_HSV_RANGES` / `MIN_PINK_RATIO` 定数は残す（import 元の互換維持）
- 設定ファイルに version フィールドは設けない（YAGNI）

## ドキュメント

- `requirements.md` — 要求仕様書（REQUIREMENTS_STANDARD.md 準拠）
- `design.md` — 機能設計書（DESIGN_STANDARD.md 準拠）
