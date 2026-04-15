# feat-036: postprocess_pink_track_id.py 実装（pink_id + track_id ハイブリッド患者追跡）

## ステータス

Planned（feat-034 ロードマップの子案件、要求仕様書着手前）

## 概要

`scripts/postprocess_pink_track_id.py`（新規）を実装する。feat-035 出力（`track_id` 付き）と feat-033 出力（`pink_id` 付き）が両方適用された HALPE 26 JSON を入力として、`pink_id` を「患者同定シグナル」、`track_id` を「継続性シグナル」として組み合わせ、各人物 BB に `pink_track_id: int`（1 = 患者、-1 = 非患者または未割り当て）を付与する。

feat-034 ロードマップの Stage 4 に対応する。本案件は Stage 2（feat-035）と Stage 3（feat-033）が両方完了していることを前提とする。

## 親ロードマップ

- feat-034: pink_id + Deep OC-SORT による新トラッキング方式（ロードマップ）

## 目的

- `pink_id=1` が観測されたフレームで、その BB の `track_id` を「現在の患者 track_id」として記憶する
- 服が見えない（`pink_id=1` が観測できない）後続フレームでも、記憶した `track_id` を持つ BB を「患者」として `pink_track_id=1` を付与し、患者追跡を延長する
- Deep OC-SORT 上で patient track が消失したら、次に `pink_id=1` が観測されるまで `pink_track_id=-1` にフォールバックする
- 新しい `pink_id=1` が観測されたら、その BB の `track_id` に patient track_id を更新する

## 期待される入出力

### 入力

- `--video`: 動画ファイルパス（MP4、描画やデバッグ用途がある場合に使用）
- `--json-dir`: 入力 JSON ディレクトリ。`track_id`（feat-035 付与）と `pink_id`（feat-033 付与）の**両方**を含むこと
- `--out-dir`: 出力 JSON ディレクトリ（`--json-dir` と異なるパス）

### 出力

- 出力ディレクトリに同じ命名規約で JSON を書き出す
- 各 `people[*]` に `pink_track_id: int` フィールドを追加
- 既存フィールド（`bbox`, `bbox_score`, `pose_keypoints_2d`, `track_id`, `pink_id`, `stable_id` 等）は変更しない

## 設計上の論点（要求仕様書作成時のヒアリング対象）

本案件の核となる「patient track_id の継続ロジック」には複数の設計判断があり、要求仕様書作成前にヒアリング・壁打ちが必要。現時点の論点:

### 論点1: patient track_id の初期化・更新規則

- 初期状態: `patient_track_id = None`
- 更新トリガー: `pink_id=1` が観測されたフレームで、その BB の `track_id` を patient_track_id に設定
- 連続する `pink_id=1` で `track_id` が変わった場合: 即座に patient_track_id を更新? それとも一定フレーム安定してから更新?

### 論点2: patient track が消失した場合の猶予（max_age 相当）

- patient_track_id が現フレームの track リストに存在しない場合、即座に「患者不在」とするか、一定フレーム間は「一時消失」とみなして patient_track_id を保持するか
- feat-022 / feat-026 の要件: 「5〜10秒（30fps で 150〜300 フレーム）の見切れ後に ID 維持が必須」
- Deep OC-SORT 自体が `max_age` で track を保持しているため、本スクリプト側は薄く扱うか、独自に猶予を持つか

### 論点3: 複数の pink_id=1 BB が同時に異なる track_id にマッピングされた場合

- 理論上 `pink_id=1` は1フレーム最大1人（feat-033 の仕様）だが、フレームをまたいで次々と別 track_id に切り替わる場合の扱い
- 基本方針: その時点での pink_id=1 BB の track_id をそのまま採用（乗り換え）

### 論点4: 初回 pink_id=1 観測前のフレーム

- 動画の最初で pink_id=1 がまだ観測されていない区間の `pink_track_id` は全員 -1
- 最初の観測以降から追跡開始

### 論点5: 出力される pink_track_id の値域

- 最小: `{1, -1}` のバイナリ（患者 or 非患者）
- 拡張案1: `{patient_track_id, -1}`（患者の track_id をそのまま出力し、デバッグ用途に流す）
- 拡張案2: マルチ患者対応のために増やす（今回はスコープ外）

## スコープ外

- Stage 2 の `postprocess_track.py` 実装（feat-035）
- Stage 3 の `postprocess_pink_id.py` 修正（feat-033、修正不要）
- Deep OC-SORT のパラメータチューニング
- 可視化スクリプトの作成・修正
- 複数患者の同時追跡

## 前提

- feat-035 が完了し、`postprocess_track.py` が生 `track_id` を JSON に付与できる状態
- feat-033 の `postprocess_pink_id.py` が再利用可能（修正不要）
- パイプライン実行順は Stage 1 → Stage 2 (feat-035) → Stage 3 (feat-033) → Stage 4 (本案件)

## 依存

本案件は feat-035 の完了を待ってから実装を開始する。

## 次のステップ

1. **ヒアリング・壁打ち**（論点1〜5 の決定）
2. 要求仕様書 `requirements.md` の作成
3. 機能設計書 `design.md` の作成
4. サブエージェントレビュー + ユーザーレビュー
5. 実装
6. 手動テスト（camSony1_S で期待動作を検証 → camSony1_L で実運用検証）

## 関連ファイル

- `scripts/postprocess_pink_id.py` — Stage 3（feat-033、既存）
- `scripts/postprocess_track.py` — Stage 2（feat-035、未実装）
- `scripts/postprocess_reid.py` — 流儀元（CLI, JSON I/O）
- 参考: feat-034 README（ロードマップ全体像）

## 関連案件

- 親: feat-034（ロードマップ）
- 前提: feat-035（Stage 2 実装、本案件の入力を生成）
- 前提: feat-033（Stage 3 実装、本案件の入力を生成）
- 参照: feat-028（`postprocess_reid.py` の実装パターン）
