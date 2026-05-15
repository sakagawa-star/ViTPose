# feat-050 機能設計書: postprocess_pink_id.py に `--min-pink-ratio` CLI 引数を追加

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001（CLI 引数追加） | §4.1 |
| FR-002（サマリ閾値表示） | §4.2 |
| FR-003（select_pink_bbox 引数化） | §4.3 |
| NFR-003（後方互換性） | §4.1 / §5 |

## 2. システム構成

### 2.1 モジュール構成

```
scripts/postprocess_pink_id.py  # 単一ファイル修正
```

### 2.2 依存関係

追加なし。

### 2.3 既存定数の扱い

`MIN_PINK_RATIO = 0.03` 定数は **削除せず残す**。CLI 引数のデフォルト値として参照することで一箇所管理を保つ:

```python
MIN_PINK_RATIO: float = 0.03  # デフォルト値の出所

parser.add_argument(
    "--min-pink-ratio", type=_check_ratio, default=MIN_PINK_RATIO,
    help="..."
)
```

## 3. 技術スタック

既存と同一。

## 4. 各機能の詳細設計

### 4.1 FR-001: CLI 引数追加

#### 4.1.1 argparse バリデータ

```python
def _check_ratio(s: str) -> float:
    fv = float(s)
    if not (0.0 <= fv <= 1.0):
        raise argparse.ArgumentTypeError(
            f"min-pink-ratio must be in [0.0, 1.0], got {fv}"
        )
    return fv
```

#### 4.1.2 引数追加

既存の `--min-roi-area` の直後に追加:

```python
parser.add_argument(
    "--min-pink-ratio", type=_check_ratio, default=MIN_PINK_RATIO,
    help=(
        f"Minimum pink_ratio to be a pink_id=1 candidate "
        f"([0.0, 1.0], default: {MIN_PINK_RATIO})"
    ),
)
```

`MIN_PINK_RATIO` 定数を help 文字列にも展開して同期不要に。

### 4.2 FR-002: サマリ閾値表示

既存サマリの `Output directory: ...` 行の**直後**、`keypoint-rect` 専用統計ブロック（feat-046 が出す `ROI mode: keypoint-rect` 以降）の**直前**に固定して挿入する:

```python
print(f"Output directory: {args.out_dir}")
print(f"Min pink ratio threshold: {args.min_pink_ratio:.3f}")  # 新規（feat-050）
# 以降に feat-046 の keypoint-rect 統計ブロックが続く
if args.roi_mode == "keypoint-rect":
    ...
```

位置を一意に確定することで `keypoint-rect` 統計の有無に関わらず常に同じ行位置に表示される。

### 4.3 FR-003: select_pink_bbox 引数化

#### 4.3.1 シグネチャ変更

```python
def select_pink_bbox(
    bboxes: list[tuple[int, int, int, int] | None],
    ratios: list[float],
    prev_selected_bbox: tuple[int, int, int, int] | None,
    min_pink_ratio: float,
) -> int | None:
    ...
    candidates = [i for i, r in enumerate(ratios) if r >= min_pink_ratio]
    ...
```

関数内の `MIN_PINK_RATIO` 参照（1 箇所）を引数 `min_pink_ratio` に置き換え。

#### 4.3.2 呼び出し側の修正

main 関数内の `select_pink_bbox` 呼び出し:

```python
sel_idx = select_pink_bbox(
    bboxes, ratios, prev_selected_bbox, args.min_pink_ratio
)
```

`args.min_pink_ratio` を引数として渡す。

#### 4.3.3 関数 docstring 更新

既存 docstring の閾値説明部分を「引数 `min_pink_ratio` 以上の人物のみ候補」と改訂。

## 5. ファイル・ディレクトリ設計

### 5.1 入出力パス

既存と同じ。変更なし。

### 5.2 推奨実行コマンド

```bash
# デフォルト（0.03、改修前と完全互換）
uv run python scripts/postprocess_pink_id.py \
  --video testdata/camSony1_S.mp4 \
  --json-dir experiments/results/camSony1_S_json \
  --out-dir experiments/results/camSony1_S_pink_json_kp_default \
  --roi-mode keypoint-rect

# 閾値 0.1
uv run python scripts/postprocess_pink_id.py \
  --video testdata/camSony1_S.mp4 \
  --json-dir experiments/results/camSony1_S_json \
  --out-dir experiments/results/camSony1_S_pink_json_kp_th01 \
  --roi-mode keypoint-rect \
  --min-pink-ratio 0.1
```

## 6. パフォーマンス影響

なし。閾値比較演算は既存と同等の O(1)。

## 7. インターフェース定義

### 7.1 CLI 引数（既存 + 新規）

| 引数 | 型 | デフォルト | 値域 |
|------|------|----------|------|
| `--video` | str | 必須 | - |
| `--json-dir` | str | 必須 | - |
| `--out-dir` | str | 必須 | - |
| `--roi-mode` | str | `bb` | `{bb, keypoint-rect}` |
| `--kpt-conf-min` | float | 0.3 | `[0.0, 1.0]` |
| `--min-roi-area` | int | 200 | `>=1` |
| `--min-pink-ratio` | float | 0.03 | `[0.0, 1.0]`（**新規**） |

### 7.2 公開関数（変更）

| 関数 | シグネチャ | 変更 |
|------|-----------|------|
| `select_pink_bbox` | `(list, list, tuple\|None, float) -> int\|None` | 引数 `min_pink_ratio` 追加 |
| `_check_ratio` | `(str) -> float` | 新規 |

## 8. ログ・デバッグ設計

既存通り。サマリに 1 行追加するのみ。

## 9. 設計判断の記録（ADR）

- **`MIN_PINK_RATIO` 定数を残す**: CLI デフォルト値の出所として保持。help 文字列にも展開して値の一箇所管理。後方互換的に「定数を読む既存コードは引き続き機能」する
- **`select_pink_bbox` シグネチャ変更**: 関数内で定数を直接参照していたのを引数化する。シグネチャ拡張だが純関数として明確。**呼び出し元は main 内の 1 箇所のみ**（同ファイル内）で外部スクリプトからの呼び出しはなく、位置引数追加による破壊的変更を許容。キーワード専用引数化（`*, min_pink_ratio`）は採用せず、純関数として全引数を位置引数で揃える既存スタイルに合わせる
- **JSON に閾値値を保存しない**: 出力 JSON の互換性最優先。閾値の実行時値は標準出力ログから確認する運用
- **CLI 引数名は `--min-pink-ratio`**: 既存 `--min-roi-area` 命名と統一感のあるハイフン区切り
- **値域 `[0.0, 1.0]`**: 通常の閾値範囲。0.0 = 全人物候補化、1.0 = 候補なし。`pink_ratio` の値域と同じ範囲を許容

## 10. 実装完了後のチェックリスト

- [ ] `_check_ratio` バリデータ追加
- [ ] `--min-pink-ratio` CLI 引数追加（デフォルト `MIN_PINK_RATIO`）
- [ ] `select_pink_bbox` シグネチャ拡張、内部参照を `min_pink_ratio` に置換
- [ ] main 内呼び出しを `args.min_pink_ratio` 渡しに更新
- [ ] サマリに `Min pink ratio threshold: 0.XXX` 1 行追加
- [ ] AC-001-1（後方互換）: 改修前コードを `git stash push scripts/postprocess_pink_id.py -m "feat-050 impl"` で退避 → 改修前で `_pink_json_kp_before/` 生成 → `git stash pop` → 改修後で `--min-pink-ratio` 未指定実行で `_pink_json_kp_after/` 生成 → `diff -r _pink_json_kp_before/ _pink_json_kp_after/` で差分 0 行を確認
- [ ] AC-001-2: `--min-pink-ratio 0.1` 実行で挙動が変わることを確認
- [ ] AC-001-3: 値域外 3 ケース（-0.1 / 1.5 / abc）で exit code 2
- [ ] `scripts/README.md` の postprocess_pink_id.py セクションに新引数追加
- [ ] CLAUDE.md / `docs/BACKLOG.md` 更新
