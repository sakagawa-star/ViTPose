# feat-015: WholeBody/AIC並列推論

## 概要

WholeBody推定とAIC推定をThreadPoolExecutorで並列実行し、処理速度を改善する。効果が見込めない場合はコードを元に戻す実験的案件。

## ステータス

Closed (2026-03-28) — 効果なし、コード戻し。RTX 5060 TiではGPU飽和により並列化効果ゼロ（逐次177.2s vs 並列177.0s、誤差範囲）。推論結果は完全一致を確認済み。

## 依存

feat-012, feat-014
