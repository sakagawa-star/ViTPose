# bug-003: visualize_patient_video.py の `--draw-start` / `--draw-end` が出力動画範囲を制限しない

## ステータス

Closed（2026-04-30）。コード修正・自動検証完了。テスト項目1（出力 1397 フレーム）/ 4（リグレッション、camSony1_S 全 900 フレーム）/ 5（`--draw-start 100` のみで 800 フレーム）すべて期待値通り。処理時間は camSony1_L 範囲指定で 30 分超 → 4.8 秒に短縮。

## 概要

`scripts/visualize_patient_video.py` で `--draw-start` / `--draw-end` を指定しても、出力 MP4 は入力動画の全フレームを含む。指定範囲外のフレームは「オーバーレイなしの素のフレーム」として出力に書き込まれてしまう。

ユーザーは「指定範囲のフレームのみが出力 MP4 に含まれる」挙動を期待していたため、不具合と判定。

## 再現手順

```bash
uv run python scripts/visualize_patient_video.py \
  --video experiments/input/camSony1_L.mp4 \
  --json-dir experiments/results/camSony1_L_pink_json \
  --out-dir experiments/results \
  --id-type pink_id --mode all \
  --draw-start 29519 --draw-end 30915
```

入力動画は 321239 フレーム。`--draw-start 29519 --draw-end 30915` は 1397 フレーム分の範囲を指定しているが、ターミナル表示は `Processing frame 000000/321239` から開始し、全フレーム（321239）が処理・書き出しされる。

```
Video: experiments/input/camSony1_L.mp4 (321239 frames, 30.0 fps)
...
Draw range: 29519 - 30915
...
Processing frame 000000/321239 (0.0%)
Processing frame 003000/321239 (0.9%)
...（全フレーム継続）
```

## 期待動作

`--draw-start` / `--draw-end` で指定した範囲のフレームのみが出力 MP4 に含まれる。指定範囲外のフレームはデコードもエンコードもされない。

## 関連

- 影響を受けたユーザーフロー: feat-042 の手動テスト（誤選択区間 29519–30915 の検証）
- 既存実装の出典: feat-038（`visualize_patient_video.py` 本体）
- 修正は `writer.write` をフレームループ内の `if in_draw_range:` 配下へ移すか、もしくは `cap.set(CAP_PROP_POS_FRAMES, draw_start)` でシークしてループ条件で `draw_end` 到達時に break する方式が候補（詳細は investigation.md §1.3 で確定）
