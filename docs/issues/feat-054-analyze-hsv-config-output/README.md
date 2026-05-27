# feat-054: analyze_clothing_color.py の HSV 設定ファイル（JSON）出力対応

## 概要

`scripts/analyze_clothing_color.py` に、推奨 HSV レンジを feat-053 互換の JSON 設定ファイル
（`fixed_hsv_ranges` + `min_pink_ratio`）として直接書き出す機能を追加する。これにより、
現状 stdout に出力される `proposed FIXED_HSV_RANGES` を人手で `postprocess_pink_id.py --hsv-config`
用の JSON へ写経する作業（feat-053 で発生）をなくす。

feat-052/053 で確定した「案C（JSON 設定ファイル経由）」の **機能②**。機能①（postprocess 側の
読み込み）は feat-053 で完了済み。

## ステータス

- Status: Closed（2026-05-27 完了）
- 親案件: feat-052（分析ツール本体）, feat-053（設定ファイル読み込み・スキーマ定義）

## 背景

- feat-053 では `analyze_clothing_color.py` が提案したレンジを、ユーザーが手で
  `scripts/conf/E0014.json` 等へ転記していた。手写経はミスの温床。
- 本案件で analyze 側が同一スキーマの JSON を直接吐けば、
  `analyze_clothing_color.py <画像>` → `postprocess_pink_id.py --hsv-config <出力JSON>`
  がコピペなしでつながる。

## 決定事項（ユーザー確認済み）

- `min_pink_ratio` は固定値 0.03（`postprocess_pink_id.MIN_PINK_RATIO` を流用、単一の真実源）。
  静止画では動画 BB 比率としての適切値を決められないため暫定固定とし、実運用での再調整は
  `postprocess_pink_id.py --min-pink-ratio` 側で行う。
- JSON 出力は**常時**（PNG と並んでデフォルトパスに書く。`--json-out` でパス上書き可）。
- 推奨レンジが空（`proposed=[]`、有彩色画素なし）の場合は **JSON を書かず `[WARN]`**。
  PNG 出力は従来通り継続する（`fixed_hsv_ranges` 空は load_hsv_config で exit 1 になる不正設定のため）。
