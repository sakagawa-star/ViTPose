# bug-004: postprocess_pink_id.py の確認動画がデフォルトで出力されない

## ステータス

Open

## 概要

`scripts/postprocess_pink_id.py` は、確認動画（pink_id オーバーレイ MP4）の出力に `--visualize` フラグの明示指定が必須（feat-056）。
通常実行では JSON しか出力されず確認動画が出ない。これは feat-056 の要求仕様段階での漏れであり、本来は実行時にデフォルトで確認動画も出力されるべき。

## 再現手順

```bash
uv run python scripts/postprocess_pink_id.py \
  --video testdata/camSony1_S.mp4 \
  --json-dir experiments/results/camSony1_S_json/ \
  --out-dir experiments/results/camSony1_S_pink_json/
```

- **現状**: 出力 JSON のみ生成され、確認動画 MP4 は生成されない（`--visualize` 未指定のため）
- **期待**: JSON に加えて確認動画 MP4 も `output/` に生成される。動画が不要なときは `--no-visualize` で抑制する

## 関連

- 原因元: feat-056（確認動画統合、`--visualize` をオプトイン設計にした）
- 影響: feat-057（`--out-dir` 自動導出）の手動テストが、動画出力前提のため本バグ解消まで完了できない
- 修正対象コード: `scripts/postprocess_pink_id.py`
- 整合が必要なドキュメント: feat-056 の requirements.md / design.md、`scripts/README.md`、`CLAUDE.md`
