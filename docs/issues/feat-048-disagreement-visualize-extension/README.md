# feat-048: 不一致フレーム可視化の情報再設計

## ステータス
Closed

## 概要

feat-047 で作成した `visualize_disagreement_frames.py` の出力 PNG では、`keypoint-rect` モードの効果を視覚的に判定できないことが手動テストで判明。本案件で以下を全面再設計する:

- **入力源を CSV → JSON ディレクトリ直読みに変更**
  - bb モード JSON ディレクトリ + keypoint-rect モード JSON ディレクトリの両方を直接受け取る
  - `compare_roi_modes.py` の CSV / 散布図出力には依存しない
- **`only_bb` ケースでも bb 選択人物の kp-rect ROI を描画**
  - kp モード JSON 内に全 person の `roi_bbox` が記録済み → bb 選択人物の `bb_index` で kp 側 JSON を引いて取得
- **可読性問題の一括是正**
  - idx ラベル位置（キーポイントと重ならない）
  - キーポイント識別（LS/RS/LH/RH 名前ラベル）
  - 高信頼／低信頼の判別性（円拡大）
  - ROI 矩形の視認性（色強化）
  - ROI 未構築時の理由テキスト表示

## 背景

### 初版設計（feat-047 + feat-048 初版）の不備

feat-047 design.md §9 ADR で `compare_roi_modes.py` の CSV 出力 → `visualize_disagreement_frames.py` の CSV 読み込みという 2 段構成を確定。その後 feat-048 初版で CSV 列を 8 → 11 に拡張し、visualize に idx ラベル / ROI 矩形 / 胴体 4 点描画を追加。

しかし手動テスト（camSony1_S, 不一致 139 件）で以下が判明:

1. CSV には「`pink_id=1` で選ばれた person」の情報しか含まれず、**`only_bb` ケース（131 件、94%）で kp 側情報が全て空欄**になり描画スキップ。kp モードがなぜその人物を選ばなかったかが画像から判定不能
2. ユーザーは CSV を実用上見ていない（PNG だけが δ 判定の根拠）
3. 可読性問題: idx ラベルとキーポイント円が重なる、塗りつぶし/中抜きが判別困難、キーポイント名不明、ROI 矩形が薄くて見えない、ROI 未構築理由不明

これらは個別 UI 修正の積み上げで解決せず、データ取得経路から再設計が必要と判断。

### feat-046 / 047 / 048 初版との関係

- feat-046（keypoint-rect ROI 実装）は変更なし。JSON フォーマットも変更しない
- feat-047 の `compare_roi_modes.py` は残置（CSV / 散布図出力は維持。ユーザーが将来別目的で使う可能性あり）
- feat-047 の `visualize_disagreement_frames.py` および feat-048 初版で追加した拡張部分は本案件で**全面書き直し**

## 関連案件

- 親: feat-047（ROI モード比較・可視化ツール）
- 兄: feat-046（keypoint-rect ROI 実装、本案件で JSON 形式変更なし）
- 後続: bug-004（feat-046 ROI 品質ガード強化）— 本案件の可視化を用いて検証
- 後続: feat-049（disagreement 分類精緻化、IoU subtype）

## 再現手順

feat-048 初版実装（コミット `??`、本ドキュメント執筆時点では未コミット）状態で `experiments/results/camSony1_S_roi_compare/disagreement_frames/frame_000011_disagree.png` を確認すると:

- bb 選択人物（赤枠）のキーポイントは描画されるが、kp 側情報（ROI 矩形・キーポイント）が完全に欠落
- 不一致 139 件中 131 件で同様の状態
