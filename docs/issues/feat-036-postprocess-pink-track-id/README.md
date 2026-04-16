# feat-036: postprocess_patient_id.py 実装（pink_id + track_id ハイブリッド患者追跡）

## ステータス

**Closed**（2026-04-16 完了）

## 完了結果サマリ

| テスト | Total frames | patient track_ids | pink_track_id=1 | pink_track_id=-2 | 処理時間 |
|--------|-------------|-------------------|-----------------|------------------|---------|
| camSony1_S | 900 | 4 | 726 | 9 | 0.1 秒 / 7924 fps |
| camSony1_L | 321,239 | 641 | 248,752 | 17,296 | 58.5 秒 / 5489 fps |

- 要求 A（種による直接判定）: pink_id=1 で患者を直接判定 → 動作確認済み
- 要求 B（track_id 拡張）: pink_id 非観測フレームで track_id 経由の伝播 → camSony1_S で +4 フレーム、camSony1_L で +13,456 フレームの患者追加を確認
- 要求 E（デデュプ）: 同一フレーム内の複数 pink_track_id=1 を bbox_score 最大のみ維持 → camSony1_S 9 フレーム、camSony1_L 17,296 フレームで発火
- OOM / クラッシュ: なし

## 注記

- **案件フォルダ名**: `feat-036-postprocess-pink-track-id`（案件開始時の当初案に合わせて命名）
- **スクリプト名**: `scripts/postprocess_patient_id.py`（ヒアリング後に命名変更。フォルダ名は CLAUDE.md「案件フォルダは完了後も削除・移動しない」ルールに従い維持）
- **JSON フィールド名**: `pink_track_id`（feat-034 ロードマップから変更なし）

## 概要

`scripts/postprocess_patient_id.py`（新規）を実装する。feat-035 出力（`track_id` 付き）と feat-033 出力（`pink_id` 付き）が両方適用された HALPE 26 JSON を入力として、各人物 BB に `pink_track_id: int` フィールドを付与する。

feat-034 ロードマップの Stage 4 に対応する。本案件は Stage 2（feat-035）と Stage 3（feat-033）が両方完了していることを前提とする。

## 親ロードマップ

- feat-034: pink_id + Deep OC-SORT による新トラッキング方式（ロードマップ）

## 基本方針

`pink_track_id` は `pink_id` を**種（主）**、`track_id` を**拡張手段（従）**とする階層構造で決定する。

- **種（pink_id=1）**: 色ベースで患者を直接判定する情報源。これ自体が患者シグナル
- **拡張（track_id）**: 種が観測できないフレームに患者ラベルを時間方向へ伝播させる道具。単独では患者を決定できない

動画全体を 2 パスで走査する。

**パス 1: patient track_id 集合の構築**

- 全フレームを走査し、各フレームで `pink_id=1` の BB を収集する
- 1 フレーム内で `pink_id=1` が複数ある場合（重複 BB 問題）、`bbox_score` が最大の BB を「有効な pink_id=1」として採用する
- 有効 BB 以外の同フレーム `pink_id=1` BB は「重複 BB」としてマークする
- 有効 BB の `track_id` を `patient_track_ids` 集合に追加する

**パス 2: pink_track_id の付与（階層順に判定）**

各フレームの各 BB について、以下の順で判定する:

1. パス 1 で「重複 BB」とマークされた → `pink_track_id = -2`（重複除外）
2. その BB 自身が有効 `pink_id=1` BB である → `pink_track_id = 1`（**種**: 直接判定）
3. その BB の `track_id` が `patient_track_ids` に含まれる → `pink_track_id = 1`（**拡張**: 種が付いた track_id を時間方向へ伝播）
4. 上記いずれにも該当しない → `pink_track_id = -1`（非患者）

判定 2（種）と判定 3（拡張）の順序は重要である。`pink_id=1` は色ベースの直接シグナルなので、`track_id` の状態に関わらず常に患者と判定される。`track_id` は種が付いた後に他フレームへ患者ラベルを伝播させる手段として働く。

**後処理デデュプ**: 判定 1〜4 の後、同一フレーム内で `pink_track_id=1` が 2 つ以上になった場合（例: 種と拡張が異なる BB に付いた場合）、`bbox_score` 最大の BB のみ `1` を維持し、他は `-2` に降格する。これにより各フレームで `pink_track_id=1` は最大 1 つに保証される。

これにより、`track_id` が全区間で一度でも有効な `pink_id=1` と紐づいていれば、その `track_id` を持つ全フレームの BB が遡って `pink_track_id=1` となり、pink が観測できない前後のフレームでも患者追跡が継続する。

## 期待される入出力

### 入力

- `--json-dir`: 入力 JSON ディレクトリ。`track_id`（feat-035 付与）と `pink_id`（feat-033 付与）の**両方**を含むこと
- `--out-dir`: 出力 JSON ディレクトリ（`--json-dir` と異なるパス）

動画ファイルは本案件では不要（`pink_id` / `track_id` / `bbox_score` は既に JSON に含まれており、パス 1/2 とも画素参照は発生しない）。

### 出力

- 出力ディレクトリに同じ命名規約で JSON を書き出す
- 各 `people[*]` に `pink_track_id: int` フィールドを追加
- 既存フィールド（`bbox`, `bbox_score`, `pose_keypoints_2d`, `track_id`, `pink_id`, `stable_id` 等）は一切変更しない

## 値域

| 値 | 意味 |
|----|------|
| `1` | 患者 |
| `-1` | 非患者 |
| `-2` | 重複 BB（bbox_score 最大でない pink_id=1 の BB、トラッキング対象外） |

## 前提

- 個室のため患者は 1 名のみ（複数患者は非対応）
- feat-035 が完了し、`postprocess_track.py` が `track_id` を JSON に付与できる状態
- feat-033 の `postprocess_pink_id.py` が `pink_id` を JSON に付与できる状態（修正不要）
- パイプライン実行順は Stage 1 → Stage 2 (feat-035) → Stage 3 (feat-033) → Stage 4 (本案件)

## スコープ外

- Stage 2 の `postprocess_track.py` 実装（feat-035 で完了済み）
- Stage 3 の `postprocess_pink_id.py` 修正（feat-033、修正不要）
- Deep OC-SORT のパラメータチューニング
- 可視化スクリプトの作成・修正
- 複数患者の同時追跡
- `run_halpe26_pipeline_yolo11.py` の変更

## 論点（解決済み）

要求仕様書作成前のヒアリングで以下の論点が全て解決した。

- **論点1（patient track_id の初期化・更新規則）**: 2 パス方式により解決。リアルタイムの継続判断を行わず、全フレーム走査後に patient_track_ids 集合を確定してから付与する
- **論点2（消失時の猶予フレーム数）**: 2 パス方式により解決。全区間走査なので猶予概念が不要
- **論点3（複数 pink_id=1）**: `bbox_score` 最大の BB を採用し、他は重複 BB として `-2` 付与
- **論点4（初回 pink_id=1 観測前のフレーム）**: その BB の `track_id` が動画のどこかで `pink_id=1` と観測されれば遡って `1` を付与、そうでなければ `-1`
- **論点5（出力 pink_track_id の値域）**: `{1, -1, -2}` に確定

## 成果物

- `scripts/postprocess_patient_id.py` — 新規作成（本案件本体）
- `docs/issues/feat-036-postprocess-pink-track-id/requirements.md` — 要求仕様書
- `docs/issues/feat-036-postprocess-pink-track-id/design.md` — 機能設計書
- `scripts/README.md` — postprocess_patient_id.py エントリ追記

## 関連ファイル

- `scripts/postprocess_pink_id.py` — Stage 3（feat-033、既存）
- `scripts/postprocess_track.py` — Stage 2（feat-035、既存）
- `scripts/postprocess_reid.py` — 流儀元（CLI, JSON I/O）
- 参考: feat-034 README（ロードマップ全体像）

## 関連案件

- 親: feat-034（ロードマップ）
- 前提: feat-035（Stage 2 実装、本案件の入力を生成）
- 前提: feat-033（Stage 3 実装、本案件の入力を生成）
- 参照: feat-028（`postprocess_reid.py` の実装パターン）
