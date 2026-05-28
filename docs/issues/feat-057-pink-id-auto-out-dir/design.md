# feat-057 機能設計書: postprocess_pink_id.py の --out-dir 自動導出（任意化）

## 1.1 対応要求マッピング

| 要求ID | 設計セクション |
|--------|----------------|
| FR-001 --out-dir 任意化 | 1.4.1 引数定義の変更 |
| FR-002 自動導出 | 1.4.2 自動導出ロジック |
| FR-003 上書き防止チェック維持 | 1.4.3 既存チェックとの関係 |

## 1.2 システム構成

- 改修対象は `scripts/postprocess_pink_id.py` の `main()` 内、引数定義と引数解決部分のみ。
- 関数の新規追加なし。`compute_pink_ratio` / `select_pink_bbox` などのコアロジックは無変更。
- 依存モジュール: 標準ライブラリ `os`（既に import 済み）。

## 1.3 技術スタック

- Python 3.10.16 / uv（既存環境、変更なし）
- 追加ライブラリなし。

## 1.4 各機能の詳細設計

### 1.4.1 引数定義の変更（FR-001）

現状（`scripts/postprocess_pink_id.py:339-343`）:

```python
parser.add_argument(
    "--out-dir",
    required=True,
    help="Output JSON directory (must differ from --json-dir)",
)
```

変更後:

```python
parser.add_argument(
    "--out-dir",
    default=None,
    help=(
        "Output JSON directory (must differ from --json-dir). "
        "If omitted, derived as '<json-dir>_pink_id'."
    ),
)
```

- `required=True` を削除し `default=None` を明示。
- help を更新し、省略時の自動導出規則を明記。

### 1.4.2 自動導出ロジック（FR-002）

**データフロー**:
- 入力: `args.json_dir`（str, ディレクトリパス）、`args.out_dir`（str | None）
- 出力: `args.out_dir`（str, 必ず非 None になる）

**処理ロジック**（引数パース直後、上書き防止チェックの前に挿入）:

```python
if args.out_dir is None:
    args.out_dir = os.path.normpath(args.json_dir) + "_pink_id"
```

- `os.path.normpath` により末尾スラッシュ・冗長な区切りを正規化してから接尾辞を付与する。
  - 例: `output/cam_json` → `output/cam_json_pink_id`（AC-002-1）
  - 例: `output/cam_json/` → normpath → `output/cam_json` → `output/cam_json_pink_id`（AC-002-2）
- 挿入位置は `args = parser.parse_args()`（425行）の後、既存の上書き防止チェック（435-438行）の **前**。
  - 理由: 導出後の `args.out_dir` に対して上書き防止チェックと `os.makedirs` が正しく適用される。
- 実際に実装するコードは INFO ログ付きの 1.8 節のブロックを採用する（上記は導出規則の説明用。print 文を含む最終形は 1.8 を参照）。

### 1.4.3 既存チェックとの関係（FR-003）

既存の上書き防止チェック（`scripts/postprocess_pink_id.py:435-438`）は無変更で維持する:

```python
if os.path.realpath(args.json_dir) == os.path.realpath(args.out_dir):
    print("ERROR: --out-dir must differ from --json-dir to prevent overwriting")
    sys.exit(1)
```

- 自動導出値は接尾辞 `_pink_id` が付くため `json_dir` と実体パスが一致することはなく、自動導出時にこのチェックへ抵触しない。
- ユーザーが `--json-dir` と同一パスを明示指定した場合は従来どおり exit 1（AC-003-1）。

### エラーハンドリング

- 本改修で新規に発生するエラーはない。
- `json_dir` が存在しない／空文字の場合の挙動は既存ロジック（`load_json_frames` 等）に委ねる（本改修の対象外）。

### 境界条件

- `--json-dir .`（カレント）指定で `--out-dir` 省略時: `os.path.normpath(".")` は `"."` を返すため、導出結果は `._pink_id`。実運用で `.` を json-dir に指定する想定はない。上書き防止チェックには抵触しない（`.` ≠ `._pink_id`）。問題があれば `--out-dir` 明示指定で回避可能。
- `--out-dir ""`（空文字明示）: argparse は空文字を「指定あり」として扱うため自動導出されず、空文字のまま makedirs で失敗する。これは明示指定の誤用であり本案件の対象外（従来も同様）。

## 1.6 ファイル・ディレクトリ設計

- 出力ディレクトリ命名規則:
  - `--out-dir` 明示時: 指定値そのまま。
  - `--out-dir` 省略時: `os.path.normpath(<json-dir>) + "_pink_id"`。
- 出力ファイル名規則は既存どおり（`591行: os.path.join(args.out_dir, filename)`）、変更なし。

## 1.7 インターフェース定義

- 関数シグネチャの変更なし。`main()` 内の引数定義と1ブロックの追加のみ。
- 公開関数（`compute_pink_ratio`, `select_pink_bbox`, `load_hsv_config` 等）は無変更。

## 1.8 ログ・デバッグ設計

- 既存のサマリ出力（`654行: Output directory: {args.out_dir}`）により、自動導出された出力先がユーザーに表示される。
- 自動導出時、導出先が一目で分かるよう INFO 相当の標準出力を1行追加する:

```python
if args.out_dir is None:
    args.out_dir = os.path.normpath(args.json_dir) + "_pink_id"
    print(f"[INFO] --out-dir not specified, using derived path: {args.out_dir}")
```

- 既存の `print` ベースのログ出力スタイルに合わせる（logging モジュールは未導入のため踏襲）。

## 設計判断の記録（ADR 簡易版）

- **採用案: `os.path.normpath(json_dir) + "_pink_id"`**
  - 理由: 入力名から一意・予測可能に導出でき、接尾辞により上書き防止チェックに自然に適合する。実装が1ブロックで済む。
- **却下案1: 固定デフォルト値（例 `default="output_pink_id"`）**
  - 理由: 入力が変わっても出力先が固定になり、複数動画を処理すると上書き衝突が起きる。
- **却下案2: 親ディレクトリ配下のサブフォルダ（例 `<json-dir>/../pink_id`）**
  - 理由: 入力名との対応が分かりにくく、複数入力で衝突する。
- **接尾辞を `_pink_id` とした理由**: 本スクリプトが付与するフィールド名 `pink_id` と一致し、出力内容が自明になる。
