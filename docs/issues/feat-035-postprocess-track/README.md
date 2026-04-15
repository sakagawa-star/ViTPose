# feat-035: postprocess_track.py 実装（Deep OC-SORT 単独、track_id 付与）

## ステータス

Planned（feat-034 ロードマップの子案件、要求仕様書着手前）

## 概要

`scripts/postprocess_track.py`（新規）を実装する。既存の HALPE 26 OpenPose JSON ディレクトリと元動画を入力として、各人物 BB に Deep OC-SORT が付与した **生の `track_id`** を書き込む。`custom_reid.py` / `stable_id` / Re-ID ロジックは**一切使わない**。

feat-034 ロードマップの Stage 2 に対応する。

## 親ロードマップ

- feat-034: pink_id + Deep OC-SORT による新トラッキング方式（ロードマップ）

## 目的

- Deep OC-SORT を単独で動かし、生 `track_id` を JSON に記録する純粋なトラッキングポストプロセスを作る
- 本スクリプトの出力は、後段の `postprocess_pink_track_id.py`（feat-036）で `pink_id` と結合するための入力となる
- 既存 `postprocess_reid.py` から `custom_reid.py` 依存部分を取り除いたシンプル版として位置づける

## 期待される入出力

### 入力

- `--video`: 動画ファイルパス（MP4）
- `--json-dir`: HALPE 26 JSON ディレクトリ（`run_halpe26_pipeline_yolo11.py` の出力）
- `--out-dir`: 出力 JSON ディレクトリ（`--json-dir` と異なるパス）

### 出力

- 出力ディレクトリに同じ命名規約（`{video_stem}_{frame_idx:06d}.json`）で JSON を書き出す
- 各 `people[*]` に `track_id: int` フィールドを追加
- 既存フィールド（`bbox`, `bbox_score`, `pose_keypoints_2d`, `stable_id` 等）は変更しない
- `track_id = -1` は検出されたが track に紐付かない場合（理論上は発生しないが保険）

## 設計指針（要求仕様書作成時の前提）

- **流儀元**: `scripts/postprocess_reid.py`（feat-028）の CLI 構造、JSON I/O、ログ形式、終了コードを流用
- **相違点**: `from custom_reid import CustomReID` を削除し、`CustomReID.update()` 呼び出しも削除。Deep OC-SORT の出力 track_id を直接 JSON に書き込む
- **track 付与ロジック**: BoxMOT の `DeepOcSort` インスタンスに各フレームの BB + 画像を渡し、返却された track リストを JSON の `people` 配列と IoU マッチングで対応付ける（`postprocess_reid.py` の `match_track_to_json` 相当を流用）
- **出力フィールド名**: `track_id`（int）

## スコープ外

- `custom_reid.py` を使った Re-ID 処理
- `stable_id` の付与・更新
- `pink_id` の計算（feat-033 で実装済み、Stage 3 で別スクリプトが担当）
- `pink_track_id` の算出（feat-036 で実装）
- Deep OC-SORT のパラメータチューニング（既存 `postprocess_reid.py` の設定を踏襲）

## 前提

- 入力動画と HALPE 26 JSON は既存の `run_halpe26_pipeline_yolo11.py` 出力
- BoxMOT / Deep OC-SORT 環境は feat-020 で構築済み

## 次のステップ

1. 要求仕様書 `requirements.md` の作成
2. 機能設計書 `design.md` の作成
3. サブエージェントレビュー + ユーザーレビュー
4. 実装
5. 手動テスト（camSony1_S → camSony1_L の順で検証）

## 関連ファイル

- `scripts/postprocess_reid.py` — 流儀元（CLI, JSON I/O, Deep OC-SORT 初期化）
- `scripts/postprocess_pink_id.py` — Stage 3（feat-033、既存実装）
- `scripts/run_halpe26_pipeline_yolo11.py` — Stage 1（入力 JSON 生成元）
- 参考: feat-034 README（ロードマップ全体像）

## 関連案件

- 親: feat-034（ロードマップ）
- 後続: feat-036（本案件の出力を入力として pink_track_id を算出）
- 参照: feat-028（`postprocess_reid.py` の実装パターン）、feat-033（`postprocess_pink_id.py` の生 dict 保持設計）
