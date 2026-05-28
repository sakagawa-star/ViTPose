# bug-004 調査・修正計画: 確認動画のデフォルト出力

## イテレーション1 (2026-05-28)

### 1.1 不具合の特定

- **現在の動作**:
  `scripts/postprocess_pink_id.py` は確認動画（pink_id オーバーレイ MP4）の出力に `--visualize` フラグの明示指定が必須。
  未指定だと出力 JSON のみ生成され、確認動画は生成されない。
  再現手順は README.md 参照。
- **期待する動作**:
  `postprocess_pink_id.py` を通常実行すると、JSON に加えて確認動画 MP4 もデフォルトで出力される。
  確認動画が不要なときは `--no-visualize` で抑制できる（`--visualize` フラグ自体は残す）。
- **エラーメッセージ**:
  なし。クラッシュではなく、要求仕様段階での仕様漏れ（feat-056 で確認動画をオプトイン設計とした）。

### 1.2 原因分析

- **原因箇所**: `scripts/postprocess_pink_id.py:381`

  ```python
  parser.add_argument(
      "--visualize", action="store_true",
      help="Also write an overlay MP4 (pink_id) while assigning pink_id",
  )
  ```

- **原因の説明**:
  `action="store_true"` のため `--visualize` のデフォルトは `False`。
  動画出力ブロック（同ファイル `if args.visualize:`、現状 473 行）はこのフラグでガードされており、
  未指定時は動画初期化・書き込みがスキップされる。
- **根本原因 or 表面的原因**:
  根本原因。feat-056 の要求仕様で「確認動画をデフォルトで出力する」要求が定義されず、
  オプトイン（明示指定時のみ出力）として設計・実装されたことに起因する。

### 1.3 修正内容

- **変更対象ファイル1**: `scripts/postprocess_pink_id.py`（381 行の引数定義）

  修正前:
  ```python
  parser.add_argument(
      "--visualize", action="store_true",
      help="Also write an overlay MP4 (pink_id) while assigning pink_id",
  )
  ```

  修正後:
  ```python
  parser.add_argument(
      "--visualize", action=argparse.BooleanOptionalAction, default=True,
      help=(
          "Also write an overlay MP4 (pink_id) while assigning pink_id "
          "(default: on; use --no-visualize to skip)"
      ),
  )
  ```

  - `argparse.BooleanOptionalAction` は同ファイルの `--show-*` 引数群で既に使用済み（`import argparse` 済み）。
  - これにより `--visualize`（True）/ `--no-visualize`（False）の両指定が可能になり、デフォルトは True。
  - 動画出力ブロック（`if args.visualize:`）および出力先（`--vis-out-dir`、既定 `output`）は変更しない。

- **変更対象ファイル2**: `docs/issues/feat-056-integrate-pink-id-visualize/requirements.md`
  - 「`--visualize` 指定時のみ出力」「未指定時は完全後方互換」等のオプトイン前提の記述を、
    「デフォルトで出力、`--no-visualize` で抑制」に本文更新。
  - 末尾に変更履歴を1行追記（例: `※ bug-004 (2026-05-28): 確認動画をデフォルトON化（--no-visualize で抑制）`）。

- **変更対象ファイル3**: `docs/issues/feat-056-integrate-pink-id-visualize/design.md`
  - 引数定義・データフロー・後方互換の記述を現行挙動に合わせ本文更新。
  - 末尾に同じ変更履歴を1行追記。

- **変更対象ファイル4**: `scripts/README.md`（`--visualize` に言及する該当全箇所を更新）
  - 冒頭サマリ文（feat-056 説明、現状 210 行付近）の `--visualize` 記述。
  - パラメータ表の `--visualize` 行（現状 231 行付近、「flag | off」）。
  - 「確認動画の同時出力」セクションの引数表（現状 269 行付近、「flag | off」＋「未指定時は MP4 を出さず…後方互換」）。
  - いずれも「既定 on、`--no-visualize` で抑制」に統一更新する。

- **変更対象ファイル5**: `CLAUDE.md`
  - feat-056 の完了済み案件サマリ内「`--visualize` 無指定時は完全後方互換」の記述を更新。

- **変更しないファイル / 項目**:
  - 出力先 `--vis-out-dir`（既定 `output`）: ユーザー判断により現状維持（本バグのスコープ外）。
  - `--out-dir` 自動導出（feat-057）: 別案件。動画出力先とは独立で触れない。
  - 動画出力ロジック本体（`draw_person` 等の再利用、MP4 ファイル名規約）: 変更不要。

### 1.4 影響範囲

- **他の機能への影響**:
  - `--visualize` を付けずに `postprocess_pink_id.py` を実行していた既存の使い方では、
    今後デフォルトで確認動画 MP4 が出力されるようになる（意図的な挙動変更）。
  - feat-057 の手動テスト: 動画がデフォルト出力されることで、`--out-dir` 省略時の出力確認が可能になる。
- **リグレッションリスク**:
  - デフォルトで全フレーム描画（`--draw-start 0` / `--draw-end -1`）になるため、
    大規模動画（例: camSony1_L 約321Kフレーム）では処理時間が大幅に増える。
    動画不要時・大規模処理時は `--no-visualize` で従来の JSON のみ高速処理に戻せる。
  - `--visualize` を明示していた既存コマンドは引き続き動画出力（挙動不変）。

### 1.5 確認方法

- **テスト項目**:
  1. デフォルトON: `--no-visualize` を付けずに実行 → `output/vis_pink_id_filter_<stem>.mp4` が生成される。
  2. 抑制: `--no-visualize` を付けて実行 → MP4 は生成されず、JSON のみ。
  3. 明示ON（後方互換）: `--visualize` を明示 → 従来どおり MP4 が生成される。
  4. JSON 内容不変: 上記いずれの場合も出力 JSON の内容は本修正前と同一。
- **テストコマンド**（camSony1_S、900フレーム）:

  ```bash
  # 1. デフォルトON
  uv run python scripts/postprocess_pink_id.py \
    --video testdata/camSony1_S.mp4 \
    --json-dir experiments/results/camSony1_S_json/ \
    --out-dir experiments/results/camSony1_S_pink_json/
  # 期待: output/vis_pink_id_filter_camSony1_S.mp4 が生成される

  # 2. 抑制
  uv run python scripts/postprocess_pink_id.py \
    --video testdata/camSony1_S.mp4 \
    --json-dir experiments/results/camSony1_S_json/ \
    --out-dir experiments/results/camSony1_S_pink_json/ \
    --no-visualize
  # 期待: MP4 が生成されない。JSON のみ
  ```
