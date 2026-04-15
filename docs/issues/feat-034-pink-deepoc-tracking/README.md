# feat-034: pink_id + Deep OC-SORT による新トラッキング方式

## ステータス

Planned（ヒアリング・壁打ちフェーズ）

## 概要

feat-033 の結果、`scripts/custom_reid.py` ベースの `stable_id` 方式は EMA 汚染により同一患者を多数のIDに断片化（camSony1_L では top9 累積 91.7%、全444個にまで分散）する一方、色ベースの `pink_id` は一貫して同じ患者を選択できることが確認された。

本案件では、`pink_id` による患者選択ロジックと Deep OC-SORT を組み合わせ、`stable_id` / `custom_reid.py` に代わる新トラッキング方式を構築する。既存のパイプライン（`run_halpe26_pipeline_yolo11.py`）は変更せず、`postprocess_reid.py` とは別の新規ポストプロセススクリプトとして実装する。

## 背景

- feat-028 で導入した `stable_id`（Deep OC-SORT + `custom_reid.py` のポーズ誘導HSVヒストグラム Re-ID）は、feat-026 で ID スイッチ時の EMA 汚染が原因で患者の追跡が42分間途切れる問題が観測された
- feat-032 でその汚染を独立観測する準備をしていたが、feat-033（色ベース方式）を前段検証として実施した結果、色ベース方式単体で camSony1_L の 73.2% のフレームをカバーしつつ同一患者を安定選択できることが確認された
- `custom_reid.py` ベースの Re-ID 修正を続ける動機が薄れ、色ベース選択と既存トラッカー（Deep OC-SORT）を組み合わせる方がシンプルかつ実用的という判断

## 目的

- `pink_id` による患者選択と Deep OC-SORT を組み合わせた新トラッキング方式を設計・実装する
- 既存JSONに `pink_track_id`（新規フィールド）を付与する新ポストプロセススクリプトを作成する
- `custom_reid.py` に依存しない、より単純で汚染耐性のあるトラッキングを実現する

## スコープ外（現時点の想定、ヒアリング後に確定）

- 既存の `run_halpe26_pipeline_yolo11.py`（キーポイント推定パイプライン）の変更
- `postprocess_reid.py` の削除・上書き（並存させる）
- `custom_reid.py` の削除（当面は履歴として残す）

## 未決事項（要ヒアリング・壁打ち）

本案件は要求仕様書着手前のヒアリング・壁打ちフェーズ。以下を決定する必要がある。

### 方式の核となるアプローチ

以下のいずれを採用するか、あるいは別案かを検討する必要がある。

- **案1: pink_id=1 のBBのみを Deep OC-SORT に入力して追跡**
  - 利点: 追跡対象が常に1人で単純
  - 欠点: pink_id=1 が途切れたフレームで追跡も途切れる
- **案2: 全BBを Deep OC-SORT に投入し、track のうち `pink_id=1` を最も多く獲得した track の ID を患者 ID とする**
  - 利点: 一時的に pink_id=1 が他BBに移っても track が継続
  - 欠点: 判定ロジックが必要、全track を保持するコスト
- **案3: 全BBを Deep OC-SORT に投入し、各フレームの pink_id=1 BB と最大IoU の track を患者IDとして採用**
  - 利点: 色ベース選択の独立性を保ちつつ track 情報を活用
  - 欠点: pink_id=1 がないフレームで判定できない
- **その他の案**: ヒアリング中に検討

### 出力フィールド仕様

- フィールド名: `pink_track_id`（確定）
- データ型: int（stable_id 相当）
- `-1` の意味: 未割り当て / 患者非該当

## 段取り

1. **ヒアリング・壁打ち**（本案件のステップ1.5、CLAUDE.md の機能追加フローには含まれないが必要）
   - 新トラッキング方式の核となるアプローチを決定する
   - 入出力・ID 空間・エッジケースの扱いを詰める
2. **要求仕様書作成**（`requirements.md`）
3. **機能設計書作成**（`design.md`）
4. **レビュー → 実装 → 手動テスト → クローズ**（通常フロー）

## 前提

- 入力動画・入力JSONは feat-033 と同じ系統（`testdata/camSony1_S.mp4`, `experiments/input/camSony1_L.mp4` とそれぞれに対応する HALPE 26 JSON）
- BoxMOT / Deep OC-SORT の環境は既存のまま流用（feat-020 で構築済み）
- 既存 `postprocess_pink_id.py`（feat-033）の実装・結果をベースラインとして活用

## 関連案件

- 前提: feat-033（服装の色による患者同定、色ベース選択ロジックの確立）
- 前提: feat-020（BoxMOT 環境構築）
- 凍結中（本案件への移行により再開予定なし）: feat-026, feat-027, feat-030, feat-031, feat-032

## 関連ファイル

- `scripts/run_halpe26_pipeline_yolo11.py` — 入力JSONを生成するパイプライン（変更しない）
- `scripts/postprocess_pink_id.py` — 色ベース選択の既存実装（feat-033、ロジック再利用元）
- `scripts/postprocess_reid.py` — 旧 Re-ID ポストプロセス（当面並存）
- `scripts/custom_reid.py` — 旧カスタム Re-ID（当面並存）
