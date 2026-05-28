# feat-058 要求仕様書: 確認動画保存先デフォルトを out-dir の親に変更

## 1.1 プロジェクト概要

- **何を作るのか**: `scripts/postprocess_pink_id.py` の `--vis-out-dir`（確認動画 MP4 の出力先）のデフォルト値を、固定の `output` から「出力 JSON ディレクトリ（`--out-dir`）の親ディレクトリ」に変更する。
- **なぜ作るのか**: 現状デフォルト `output/` はテスト用出力の場所であり、本番ポストプロセスの確認動画がそこに混ざる。出力 JSON の近く（親ディレクトリ）に動画を出したい。
- **誰が使うのか**: 本リポジトリで pink_id ポストプロセスを実行する開発者（ユーザー本人）。
- **どこで使うのか**: ローカル CLI 実行（`uv run python scripts/postprocess_pink_id.py ...`）。

## 1.2 用語定義

- **out-dir**: `--out-dir` で指定する出力 JSON ディレクトリ。未指定時は feat-057 により `<json-dir>_pink_id` に自動導出される。
- **vis-out-dir**: `--vis-out-dir` で指定する確認動画 MP4 の出力先ディレクトリ。
- **親ディレクトリ**: あるパスを `os.path.normpath` で正規化した後の `os.path.dirname`。

## 1.3 機能要求一覧

### FR-001: --vis-out-dir 未指定時のデフォルトを out-dir の親に変更

- **機能名**: 確認動画保存先デフォルトの変更
- **概要**: `--vis-out-dir` を明示指定しなかった場合、確認動画 MP4 を out-dir の親ディレクトリに出力する。
- **入力**: `--vis-out-dir` 未指定（`--out-dir` は省略・明示どちらでも可）
- **出力**: 確認動画 MP4 が `os.path.dirname(os.path.normpath(out_dir))` に出力される
- **受け入れ基準**:
  - AC-001-1: `--out-dir experiments/results/cam_pink_id` ＋ `--vis-out-dir` 未指定で、動画が `experiments/results/` に出力される。
  - AC-001-2: `--out-dir` 省略（自動導出 `<json-dir>_pink_id`）＋ `--vis-out-dir` 未指定で、動画が json-dir の親（= out-dir の親）に出力される。例: `--json-dir experiments/results/cam_json` → out-dir `experiments/results/cam_json_pink_id` → 動画 `experiments/results/`。
  - AC-001-3: out-dir に末尾スラッシュがあっても（例 `experiments/results/cam_pink_id/`）親は `experiments/results` になる（normpath で吸収）。

### FR-002: --vis-out-dir 明示時は従来どおり指定値を使う

- **機能名**: 明示指定の優先
- **概要**: `--vis-out-dir` を明示指定した場合、その値をそのまま出力先とする（デフォルト導出は行わない）。
- **入力**: `--vis-out-dir <path>`
- **出力**: 指定値が動画出力先になる（feat-056 と同一動作）
- **受け入れ基準**:
  - AC-002-1: `--vis-out-dir vis_check` のように out-dir の親以外の任意パスを明示すると、out-dir の親ではなく指定値 `vis_check/` に動画が出力される（明示優先が効いている）。

### FR-003: 親が空になる場合のフォールバック

- **機能名**: 親なしパスのフォールバック
- **概要**: out-dir が区切りを含まない相対パス（例 `cam_pink_id`）で親ディレクトリが空文字になる場合、カレントディレクトリ `.` を出力先とする。
- **入力**: `--out-dir cam_pink_id`（区切りなし）＋ `--vis-out-dir` 未指定
- **出力**: 動画がカレントディレクトリ直下に出力される
- **受け入れ基準**:
  - AC-003-1: `os.path.dirname(os.path.normpath("cam_pink_id"))` は `""` を返すが、出力先は `.` にフォールバックし、`os.makedirs`/書き込みがエラーにならない。

## 1.4 非機能要求

- **パフォーマンス**: 引数解決のみの変更で、推論・描画処理には影響しない。
- **対応環境**: 既存の実行環境（Python 3.10.16 / uv）。新規ライブラリ追加なし。
- **信頼性**: 親ディレクトリが既存でも `os.makedirs(..., exist_ok=True)`（既存挙動）で再利用する。

## 1.5 制約条件

- 新規ライブラリ追加禁止（標準ライブラリ `os` のみ使用）。
- 確認動画のデフォルトON/OFF（bug-004）、`--out-dir` 自動導出（feat-057）、pink_id 計算・描画ロジックは変更しない。
- MP4 ファイル名規約（`vis_pink_id_<vis-mode>_<stem>.mp4`）は変更しない。
- `visualize_patient_video.py` / `merge_halpe26.py` は無変更。
- 挙動変更に伴い `scripts/README.md`（`--vis-out-dir` のデフォルト記述、該当全箇所）と `CLAUDE.md`（feat-056/058 関連記述）を整合更新する。


## 1.6 優先順位

| 要求 | MoSCoW |
|------|--------|
| FR-001 デフォルトを out-dir の親に | Must |
| FR-002 明示時の優先 | Must |
| FR-003 親なしフォールバック | Must |

MVP: FR-001 〜 FR-003 すべて（小規模改修のため全体が MVP）。
