# bug-002: --mode json時にout_pathが未定義で参照されるリスク

## 概要

`run_halpe26_pipeline.py` 185行目で `out_path` を参照しているが、この変数は `do_video=True` の場合（79-81行目）のみ定義される。`--mode json`（`do_video=False`）の場合、185行目の `if do_video:` ガードにより参照されないため現時点では問題ないが、条件分岐のガードに依存した安全性であり、リファクタリング時にNameErrorが発生するリスクがある。

## 再現手順

1. `--mode json` で実行 → 現時点では正常動作（`if do_video:` で保護されている）
2. 将来的に185行目付近の条件分岐が変更された場合、`out_path` が未定義で `NameError` になる可能性がある

## ステータス

Closed (2026-03-29)
