# feat-058 機能設計書: 確認動画保存先デフォルトを out-dir の親に変更

## 1.1 対応要求マッピング

| 要求ID | 設計セクション |
|--------|----------------|
| FR-001 デフォルトを out-dir の親に | 1.4.1 引数定義の変更 / 1.4.2 デフォルト導出ロジック |
| FR-002 明示時の優先 | 1.4.2 デフォルト導出ロジック（None 判定） |
| FR-003 親なしフォールバック | 1.4.2 デフォルト導出ロジック（`or "."`） |

## 1.2 システム構成

- 改修対象は `scripts/postprocess_pink_id.py` の `main()` 内、`--vis-out-dir` 引数定義と引数解決部分のみ。
- 関数の新規追加なし。動画出力ブロック（`if args.visualize:` 内、`os.makedirs(args.vis_out_dir)` / `os.path.join(args.vis_out_dir, out_name)`）は無変更。
- 依存モジュール: 標準ライブラリ `os`（import 済み）。

## 1.3 技術スタック

- Python 3.10.16 / uv（既存環境、変更なし）。追加ライブラリなし。

## 1.4 各機能の詳細設計

### 1.4.1 引数定義の変更（FR-001 / FR-002）

現状（`scripts/postprocess_pink_id.py:387-389`）:

```python
parser.add_argument(
    "--vis-out-dir", default="output",
    help="Output directory for the visualization MP4 (default: output)",
)
```

変更後:

```python
parser.add_argument(
    "--vis-out-dir", default=None,
    help=(
        "Output directory for the visualization MP4. "
        "If omitted, the parent directory of --out-dir is used."
    ),
)
```

- `default="output"` → `default=None`。`None` を「未指定」の判定に使う（FR-002 の明示優先のため）。
- help を更新し、省略時の導出規則を明記。

### 1.4.2 デフォルト導出ロジック（FR-001 / FR-002 / FR-003）

**データフロー**:
- 入力: `args.out_dir`（str, feat-057 の自動導出ブロック後に確定済みの非 None 値）、`args.vis_out_dir`（str | None）
- 出力: `args.vis_out_dir`（str, 必ず非 None・非空になる）

**処理ロジック**（挿入位置 = `os.makedirs(args.out_dir, exist_ok=True)`（現状 450 行付近）の直後。feat-057 の `--out-dir` 自動導出ブロックの後で `args.out_dir` が確定済み、かつ動画出力ブロック（`if args.visualize:`）より前）:

```python
if args.vis_out_dir is None:
    args.vis_out_dir = os.path.dirname(os.path.normpath(args.out_dir)) or "."
```

- `args.out_dir` を `os.path.normpath` で正規化してから `os.path.dirname` で親を取る。
  - 例: `experiments/results/cam_pink_id` → 親 `experiments/results`（AC-001-1）
  - 例: `experiments/results/cam_pink_id/`（末尾スラッシュ）→ normpath → `experiments/results/cam_pink_id` → 親 `experiments/results`（AC-001-3）
  - 例: 自動導出 `experiments/results/cam_json_pink_id` → 親 `experiments/results`（AC-001-2）
- `os.path.dirname(...)` が空文字 `""` を返す場合（out_dir が区切りを含まない相対パス、例 `cam_pink_id`）は `or "."` でカレントディレクトリにフォールバック（FR-003、AC-003-1）。
- **順序の依存**: feat-057 で `args.out_dir` が `None` のとき自動導出される。本ロジックはその後に実行する必要がある（`args.out_dir` の確定値に依存）。

### エラーハンドリング

- 本改修で新規に発生するエラーはない。
- 導出された親ディレクトリは動画出力ブロックの既存 `os.makedirs(args.vis_out_dir, exist_ok=True)` で作成される（既存挙動）。

### 境界条件

- out_dir が絶対パス（例 `/data/cam_pink_id`）: 親 `/data`。問題なし。
- out_dir が区切りなし相対パス（例 `cam_pink_id`）: 親が空文字 → `.` フォールバック（FR-003）。
- `--no-visualize` 指定時: 動画出力ブロックに入らないため `args.vis_out_dir` は使われない。導出は実行されるが無害（未使用）。

## 1.6 ファイル・ディレクトリ設計

- 確認動画出力先:
  - `--vis-out-dir` 明示時: 指定値そのまま。
  - `--vis-out-dir` 省略時: `os.path.dirname(os.path.normpath(args.out_dir)) or "."`。
- MP4 ファイル名規約は既存どおり（`vis_pink_id_<vis-mode>_<stem>.mp4`）、変更なし。

## 1.7 インターフェース定義

- 関数シグネチャの変更なし。`main()` 内の引数定義変更と1ブロックの追加のみ。
- 公開関数は無変更。

## 1.8 ログ・デバッグ設計

- 既存の `Visualize: ON -> <vis_out_path>` ログ（動画出力ブロック内）により、最終的な動画出力先がユーザーに表示される。これで導出結果が確認できるため、導出時の追加ログは出さない。

## 設計判断の記録（ADR 簡易版）

- **採用案: `os.path.dirname(os.path.normpath(out_dir)) or "."`**
  - 理由: out-dir の親を一意・予測可能に導出でき、末尾スラッシュ（normpath）と親なしパス（`or "."`）の両境界を 1 行で処理できる。
- **却下案1: `os.path.dirname(out_dir)`（normpath なし）**
  - 理由: out-dir に末尾スラッシュがあると親が取れない（`a/b/` → `a/b`）。AC-001-3 を満たさない。
- **却下案2: json-dir の親を基準にする**
  - 理由: ユーザー選択は「out-dir の親」。out-dir 明示時に json-dir 基準だと出力 JSON と動画の位置がずれる。
- **却下案3: feat-056 のデフォルト `output` 固定を維持**
  - 理由: 本案件の動機（テスト用 `output/` に本番動画が混ざる）を解決できない。
- **追加ログを出さない理由**: 既存の `Visualize: ON -> ...` ログが最終出力先を示すため、導出専用ログは冗長。
