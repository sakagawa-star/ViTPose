# feat-058: postprocess_pink_id.py の確認動画保存先デフォルトを out-dir の親に変更

## ステータス

Open

## 概要

`scripts/postprocess_pink_id.py` の確認動画出力先 `--vis-out-dir` のデフォルトは現在 `output` 固定。
`output/` はテスト用出力の場所であり、本番ポストプロセスの確認動画が混ざるため不適切。
`--vis-out-dir` 未指定時のデフォルトを、出力 JSON ディレクトリ（`--out-dir`）の親ディレクトリに変更する。

## 動機

- 確認動画がテスト用 `output/` に出るのを避け、出力 JSON の近く（親ディレクトリ）にまとめたい（ユーザー要望）
- feat-056 で `--vis-out-dir` のデフォルトを `output` 固定にした選定が、運用上不適切と判明

## 関連

- 原因元: feat-056（`--vis-out-dir` デフォルト `output` 固定）
- 依存: feat-057（`--out-dir` 自動導出）。`--out-dir` 省略時は `<json-dir>_pink_id` が out-dir となり、その親に動画が出る
- 改修対象: `scripts/postprocess_pink_id.py`
