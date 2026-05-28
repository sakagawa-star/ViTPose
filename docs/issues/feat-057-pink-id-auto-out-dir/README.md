# feat-057: postprocess_pink_id.py の --out-dir 自動導出（任意化）

## ステータス

Open

## 概要

`scripts/postprocess_pink_id.py` の `--out-dir` は現在 `required=True` で、実行のたびに手入力が必要。
これを任意化し、未指定時は `--json-dir` から自動導出（`<json-dir>_pink_id`）する。

## 動機

- 毎回 `--out-dir` を入力するのが面倒（ユーザー要望）
- 入力ディレクトリと固定の接尾辞で命名できれば省略可能になり、誤って同一ディレクトリを指定する事故も防げる

## 関連

- 改修対象: `scripts/postprocess_pink_id.py`
- 既存の上書き防止チェック（`--json-dir` と `--out-dir` の同一禁止）は維持する
