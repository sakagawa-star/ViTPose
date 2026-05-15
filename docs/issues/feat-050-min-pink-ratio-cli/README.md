# feat-050: postprocess_pink_id.py に `--min-pink-ratio` CLI 引数を追加

## ステータス
Closed

## 概要

`scripts/postprocess_pink_id.py` 内でハードコードされている定数 `MIN_PINK_RATIO = 0.03` を CLI 引数 `--min-pink-ratio`（デフォルト 0.03、後方互換）で外部から指定可能にする。

## 背景

`MIN_PINK_RATIO` は「pink_id=1 候補とする pink_ratio の最低値」で、現状 0.03（3%）にハードコード。値を変更するにはソースコード編集が必要で、複数値を試行する作業が煩雑。

ユーザーは keypoint-rect モード（feat-046）の挙動検証中に閾値を 0.1 等に変えて挙動を比較したいケースが発生したため、CLI 化が必要。

## 関連案件

- 親: feat-033（pink_id 付与ポストプロセス、MIN_PINK_RATIO 導入）
- 兄: feat-046（keypoint-rect ROI 対応、本案件と独立）

## 影響範囲

- `scripts/postprocess_pink_id.py`: CLI 引数追加と定数参照の置き換え
- `scripts/README.md`: postprocess_pink_id.py セクション更新
- 出力 JSON 形式は変更しない（既存フィールドそのまま、threshold 値は CLI でのみ表現）
- 下流スクリプト（feat-035 / 036 / 037 / 038 / 039 / 040 / 041 / 042 / 048 / 049）は変更不要
