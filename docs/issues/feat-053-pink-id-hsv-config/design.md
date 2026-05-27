# feat-053 機能設計書: postprocess_pink_id.py の HSV 設定ファイル読み込み対応

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001（`--hsv-config` 追加） | §4.1 |
| FR-002（スキーマ検証） | §4.2 |
| FR-003（`min_pink_ratio` 優先順位） | §4.3 |
| FR-004（`compute_pink_ratio` 引数化） | §4.4 |
| FR-005（サマリ表示） | §4.5 |
| NFR-003（後方互換性） | §4.4 / §9 |

## 2. システム構成

### 2.1 モジュール構成

```
scripts/postprocess_pink_id.py                                  # 単一ファイル修正
docs/issues/feat-053-pink-id-hsv-config/example_hsv_config.json # サンプル設定ファイル（新規、git 管理）
```

### 2.2 依存関係

`json`（標準ライブラリ）の import を追加するのみ。外部ライブラリ追加なし。

### 2.3 既存定数の扱い

`FIXED_HSV_RANGES` と `MIN_PINK_RATIO` は**削除せず残す**。

- `FIXED_HSV_RANGES`: `--hsv-config` 未指定時の有効レンジ、かつ `compute_pink_ratio(ranges=None)` のフォールバック。`analyze_clothing_color.py` が import している
- `MIN_PINK_RATIO`: `min_pink_ratio` 解決のデフォルト値の出所。`plot_pink_ratio_timeline.py` が import している

## 3. 技術スタック

既存と同一（Python 3.10.16、OpenCV、NumPy）。`json` 標準ライブラリを追加 import。

## 4. 各機能の詳細設計

### 4.1 FR-001: CLI 引数 `--hsv-config` の追加

既存の `--min-pink-ratio` の直後に追加する。

```python
parser.add_argument(
    "--hsv-config", default=None,
    help=(
        "Path to JSON config with keys 'fixed_hsv_ranges' and "
        "'min_pink_ratio'. If omitted, built-in FIXED_HSV_RANGES is used."
    ),
)
```

main 冒頭（既存の上書き防止チェックの後、フレームループ開始前）で設定を解決する:

```python
# HSV 設定の解決
if args.hsv_config is not None:
    active_ranges, config_min_pink_ratio = load_hsv_config(args.hsv_config)
else:
    active_ranges = FIXED_HSV_RANGES
    config_min_pink_ratio = None

# min_pink_ratio の優先順位（FR-003）
min_pink_ratio = resolve_min_pink_ratio(
    args.min_pink_ratio, config_min_pink_ratio
)
```

- **データフロー**: `active_ranges` は `list[tuple[tuple[int,int,int], tuple[int,int,int]]]`、`min_pink_ratio` は `float`
- フレームループ内では `args.min_pink_ratio` ではなく解決済みローカル変数 `min_pink_ratio` を使う

### 4.2 FR-002: スキーマ検証

`load_hsv_config` と検証ヘルパを新規追加する。`_validate_ranges` は検証後、`FIXED_HSV_RANGES` と同じ tuple-of-tuples 構造（`list[tuple[tuple[int,int,int], tuple[int,int,int]]]`）に正規化して返す。エラー時は標準エラーへメッセージを出し `sys.exit(1)`。

```python
def _config_error(msg: str) -> None:
    print(f"ERROR: invalid HSV config: {msg}", file=sys.stderr)
    sys.exit(1)


def _validate_hsv_triple(t, ri: int, which: str) -> tuple[int, int, int]:
    """[H,S,V] を検証。H:[0,179] S/V:[0,255]、整数(bool不可)。"""
    if not isinstance(t, (list, tuple)) or len(t) != 3:
        _config_error(f"range[{ri}].{which} must be a 3-element [H,S,V]")
    bounds = ((0, 179), (0, 255), (0, 255))
    out = []
    for ci, (v, (lo_b, hi_b)) in enumerate(zip(t, bounds)):
        if isinstance(v, bool) or not isinstance(v, int):
            _config_error(f"range[{ri}].{which}[{ci}] must be an integer")
        if not (lo_b <= v <= hi_b):
            _config_error(
                f"range[{ri}].{which}[{ci}]={v} out of [{lo_b},{hi_b}]"
            )
        out.append(v)
    return tuple(out)


def _validate_ranges(raw) -> list:
    if not isinstance(raw, list) or len(raw) == 0:
        _config_error("fixed_hsv_ranges must be a non-empty array")
    result = []
    for ri, r in enumerate(raw):
        if not isinstance(r, (list, tuple)) or len(r) != 2:
            _config_error(f"range[{ri}] must be [lo, hi]")
        lo = _validate_hsv_triple(r[0], ri, "lo")
        hi = _validate_hsv_triple(r[1], ri, "hi")
        for ci in range(3):
            if lo[ci] > hi[ci]:
                _config_error(f"range[{ri}] lo[{ci}]={lo[ci]} > hi[{ci}]={hi[ci]}")
        result.append((lo, hi))
    return result


def _validate_min_pink_ratio(v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        _config_error("min_pink_ratio must be a number")
    if not (0.0 <= v <= 1.0):
        _config_error(f"min_pink_ratio={v} out of [0.0, 1.0]")
    return float(v)


def load_hsv_config(path: str) -> tuple[list, float]:
    """HSV 設定ファイルを読み検証する。失敗時は sys.exit(1)。"""
    if not os.path.isfile(path):
        print(f"ERROR: HSV config file not found: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        with open(path) as f:
            cfg = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: failed to parse HSV config JSON: {e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(cfg, dict):
        _config_error("root must be a JSON object")
    for key in ("fixed_hsv_ranges", "min_pink_ratio"):
        if key not in cfg:
            _config_error(f"missing required key: {key}")
    ranges = _validate_ranges(cfg["fixed_hsv_ranges"])
    mpr = _validate_min_pink_ratio(cfg["min_pink_ratio"])
    return ranges, mpr
```

- **境界条件**: 空配列 `fixed_hsv_ranges: []` はエラー。`H=180` 以上はエラー（OpenCV H は 0-179）。`lo>hi` はエラー。bool 値（JSON `true`/`false`）は整数として扱わずエラー。**float（例 `153.0`）も `isinstance(v, int)` を満たさないためエラー**（HSV は整数表記に統一する方針。`analyze` 出力は `int(round(...))` 済み）。両キーが共に欠けている場合は検証ループ先頭の `fixed_hsv_ranges` のみ報告して exit（先勝ち、1 メッセージ）
- **エラーハンドリング**: ファイル不在・JSON パース不能・型/値域違反すべて exit code 1。メッセージで該当箇所を示す
- **検証の二重定義について**: `min_pink_ratio` の値域 `[0.0, 1.0]` は CLI 経路（既存 `_check_ratio`、`argparse.ArgumentTypeError`）と config 経路（新規 `_validate_min_pink_ratio`、`sys.exit(1)`）で独立に検証する。値域は要求で固定（変更予定なし）のため、定数共有はせず 2 系統の独立検証を意図的に許容する

### 4.3 FR-003: `min_pink_ratio` の優先順位

`--min-pink-ratio` のデフォルトを **`None` に変更**して「明示指定の有無」を判定可能にする。

```python
# 既存（feat-050）: default=MIN_PINK_RATIO → 変更後
parser.add_argument(
    "--min-pink-ratio", type=_check_ratio, default=None,
    help=(
        f"Minimum pink_ratio to be a pink_id=1 candidate "
        f"([0.0, 1.0]). Overrides config; default if both unset: "
        f"{MIN_PINK_RATIO}"
    ),
)
```

解決関数:

```python
def resolve_min_pink_ratio(
    cli_value: float | None, config_value: float | None
) -> float:
    """CLI明示 > 設定ファイル > デフォルト の順で min_pink_ratio を決める。"""
    if cli_value is not None:
        return cli_value          # CLI 明示（argparse が _check_ratio 検証済み）
    if config_value is not None:
        return config_value       # 設定ファイル（load_hsv_config 検証済み）
    return MIN_PINK_RATIO         # デフォルト 0.03
```

- **後方互換の根拠**: `default=None` に変えても、未指定時の最終値は `MIN_PINK_RATIO`（0.03）で改修前と同一。`_check_ratio` は明示指定時のみ argparse が適用するため、`None` がバリデータに渡ることはない
- フレームループ内の `select_pink_bbox(..., args.min_pink_ratio)` 呼び出し（既存 368 行）を、解決済みローカル変数 `min_pink_ratio` 渡しに変更する

### 4.4 FR-004: `compute_pink_ratio` の引数化

```python
def compute_pink_ratio(roi_bgr: np.ndarray, ranges: list | None = None) -> float:
    """BGR ROI の HSV ピンク画素比率を返す。

    ranges=None のときは従来どおりグローバル FIXED_HSV_RANGES を使う
    （後方互換: 引数なし呼び出しの analyze_clothing_color.py を壊さない）。
    """
    if roi_bgr.size == 0:
        return 0.0
    use_ranges = FIXED_HSV_RANGES if ranges is None else ranges
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    mask_total = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lo, hi in use_ranges:
        lo_np = np.array(lo, dtype=np.uint8)
        hi_np = np.array(hi, dtype=np.uint8)
        mask = cv2.inRange(hsv, lo_np, hi_np)
        mask_total = cv2.bitwise_or(mask_total, mask)
    pink_pixels = int(np.count_nonzero(mask_total))
    total_pixels = roi_bgr.shape[0] * roi_bgr.shape[1]
    return pink_pixels / total_pixels if total_pixels > 0 else 0.0
```

main 内の 2 つの呼び出し（既存 349 行・364 行）を `compute_pink_ratio(roi, ranges=active_ranges)` に変更する。`--hsv-config` 未指定時は `active_ranges == FIXED_HSV_RANGES` のため結果は引数なし呼び出しと同一（後方互換）。

### 4.5 FR-005: サマリ表示

既存サマリの `Output directory: ...`（438 行）の直後、feat-046 の keypoint-rect 統計ブロックの直前に固定配置する。既存の `Min pink ratio threshold` 行（439 行）はこのブロックに統合する:

```python
print(f"Output directory: {args.out_dir}")
if args.hsv_config is not None:
    print(f"HSV config: {args.hsv_config}")
else:
    print("HSV config: default (built-in FIXED_HSV_RANGES)")
print(f"Active HSV ranges: {active_ranges}")
print(f"Min pink ratio threshold: {min_pink_ratio:.3f}")  # 解決後の値
# 以降に feat-046 の keypoint-rect 統計ブロックが続く
```

## 5. ファイル・ディレクトリ設計

### 5.1 設定ファイルのスキーマ（JSON）

```json
{
  "fixed_hsv_ranges": [
    [[0, 60, 80], [10, 255, 255]],
    [[140, 60, 80], [159, 255, 255]],
    [[160, 60, 80], [179, 255, 255]]
  ],
  "min_pink_ratio": 0.03
}
```

| キー | 型 | 値域 | 必須 |
|------|------|------|------|
| `fixed_hsv_ranges` | array of `[lo, hi]`、`lo`/`hi` = `[H,S,V]` | H:[0,179] S/V:[0,255]、各成分 lo<=hi、空配列不可 | Yes |
| `min_pink_ratio` | number | [0.0, 1.0] | Yes |

上の例は現行の `FIXED_HSV_RANGES` と同値であり（`min_pink_ratio` も `MIN_PINK_RATIO`=0.03 と同値）、これを `example_hsv_config.json` として案件フォルダに配置する（AC-001-2 / AC-005 の検証に使用。`--hsv-config` 指定時と未指定時で出力が一致することを確認できる）。`min_pink_ratio` を 0.03 とするのは FR-003 で config 値が CLI デフォルトより優先されるため（0.03 以外だと未指定時と差分が出て AC-001-2 が不成立になる）。

### 5.2 設定ファイルの置き場所規約

- `--hsv-config` は任意パスを受け取る。デフォルトパスは設けない
- git 管理するサンプル（匿名・テスト動画由来値）は `docs/issues/feat-053-pink-id-hsv-config/example_hsv_config.json`
- 実患者用の設定ファイル（患者 ID をファイル名に含む等センシティブになりうるもの）は `experiments/`（`.gitignore` 対象）配下にユーザーが作成する

### 5.3 推奨実行コマンド

```bash
# デフォルト（--hsv-config なし、改修前と完全互換）
uv run python scripts/postprocess_pink_id.py \
  --video testdata/camSony1_S.mp4 \
  --json-dir experiments/results/camSony1_S_json \
  --out-dir experiments/results/camSony1_S_pink_json_default \
  --roi-mode keypoint-rect

# 設定ファイル指定
uv run python scripts/postprocess_pink_id.py \
  --video testdata/camSony1_S.mp4 \
  --json-dir experiments/results/camSony1_S_json \
  --out-dir experiments/results/camSony1_S_pink_json_cfg \
  --roi-mode keypoint-rect \
  --hsv-config experiments/hsv_configs/E0014.json
```

## 6. パフォーマンス影響

起動時の設定ファイル読み込み・検証 1 回のみ。フレームループ内の演算は改修前と同一。

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
| `--min-pink-ratio` | float | **None（変更）** | `[0.0, 1.0]`（明示指定時） |
| `--hsv-config` | str | None | 既存 JSON ファイルパス（**新規**） |

### 7.2 公開関数（新規・変更）

| 関数 | シグネチャ | 変更 |
|------|-----------|------|
| `compute_pink_ratio` | `(np.ndarray, list \| None = None) -> float` | `ranges` 引数追加（デフォルト None） |
| `load_hsv_config` | `(str) -> tuple[list[tuple[tuple[int,int,int],tuple[int,int,int]]], float]` | 新規 |
| `resolve_min_pink_ratio` | `(float \| None, float \| None) -> float` | 新規 |
| `_validate_ranges` | `(object) -> list` | 新規 |
| `_validate_hsv_triple` | `(object, int, str) -> tuple[int,int,int]` | 新規 |
| `_validate_min_pink_ratio` | `(object) -> float` | 新規 |
| `_config_error` | `(str) -> None` | 新規 |

`select_pink_bbox`（feat-050 で引数化済み）はシグネチャ変更なし。呼び出し時に渡す値を `args.min_pink_ratio` から解決済み `min_pink_ratio` に変えるのみ。

## 8. ログ・デバッグ設計

- 設定ファイルの検証エラーは `file=sys.stderr` に `ERROR: ...` 形式で出力し exit code 1
- 正常時はサマリ（§4.5）に HSV config パス・有効レンジ・閾値を表示。既存のログ方針を踏襲

## 9. 設計判断の記録（ADR）

- **ADR-1 案C（設定ファイル経由）**: HSV レンジは「複数の (lo,hi) 3 要素タプル」という構造データで、CLI のフラットな数値列（案A）は手入力ミスを誘発する。設定ファイルが素直で、患者プロファイルとして git/ファイル管理でき再現性も高い。analyze 側の出力連携（機能②）への発展性もある
- **ADR-2 2 項目スキーマ（`fixed_hsv_ranges` + `min_pink_ratio`）**: `postprocess_pink_id.py` が実際に使う色パラメータはこの 2 つのみ。`sat_min/val_min` は analyze 側の測定専用パラメータで postprocess には概念がない（S/V 下限はレンジ各タプルの下限値に内包）ため含めない
- **ADR-3 両キー必須（B-1）**: 設定ファイルを「患者プロファイル」という完結した単位として扱い、設定漏れによる意図しない挙動を防ぐ。部分指定（B-2）は採らない
- **ADR-4 優先順位 CLI明示 > 設定ファイル > デフォルト（A-1）**: 患者プロファイルを基準にしつつ、検証時に `--min-pink-ratio` でその場の微調整を許す方が直感的。実装は `--min-pink-ratio` のデフォルトを `None` にして明示指定の有無を判定する。設定ファイルが常に勝つ案（A-2）は CLI の即時上書きができず却下
- **ADR-5 `compute_pink_ratio` は `ranges=None` デフォルト**: 必須引数化すると `analyze_clothing_color.py:321` の引数なし呼び出しが壊れる。`None` でグローバル `FIXED_HSV_RANGES` フォールバックすることで後方互換を保つ
- **ADR-6 定数 `FIXED_HSV_RANGES` / `MIN_PINK_RATIO` を残す**: それぞれ `analyze_clothing_color.py` / `plot_pink_ratio_timeline.py` が import している。削除すると import エラーになる。デフォルト値・フォールバックの出所としても保持
- **ADR-7 CLI に数値レンジ引数を作らない**: レンジは構造データであり CLI には不向き。設定ファイル経由に一本化
- **ADR-8 version フィールドなし（YAGNI）**: 現時点でスキーマ進化の予定がなく、不要な複雑さを避ける
- **ADR-9 H 上限を 179 で検証**: OpenCV の HSV は H ∈ [0,179]（実角度 H×2°）。180 以上はソフトに丸めず明示エラーとし、設定ミスを早期検出する
- **ADR-10 出力 JSON に設定情報を保存しない**: 出力 JSON 互換性を最優先。有効レンジ・閾値の実行時値は標準出力ログから確認する運用

## 10. 実装完了後のチェックリスト

- [ ] `import json` 追加
- [ ] `compute_pink_ratio` に `ranges=None` 引数追加、`use_ranges` 分岐
- [ ] `_config_error` / `_validate_hsv_triple` / `_validate_ranges` / `_validate_min_pink_ratio` / `load_hsv_config` 追加
- [ ] `resolve_min_pink_ratio` 追加
- [ ] `--hsv-config` CLI 引数追加
- [ ] `--min-pink-ratio` のデフォルトを `None` に変更、help 文更新
- [ ] main で `active_ranges` / `config_min_pink_ratio` / `min_pink_ratio` を解決
- [ ] `compute_pink_ratio` 呼び出し 2 箇所を `ranges=active_ranges` 渡しに変更
- [ ] `select_pink_bbox` 呼び出しを解決済み `min_pink_ratio` 渡しに変更
- [ ] サマリに HSV config / Active HSV ranges / Min pink ratio threshold の 3 行
- [ ] `example_hsv_config.json`（`fixed_hsv_ranges` は現行 FIXED_HSV_RANGES と同値、`min_pink_ratio` は 0.03）を案件フォルダに作成
- [ ] AC-001-1（後方互換）: `git stash` で改修前退避 → `--hsv-config` 未指定で before/after 生成 → `diff -r` 差分 0
- [ ] AC-001-2: `example_hsv_config.json` 指定の出力が未指定時と `diff -r` 差分 0
- [ ] AC-002-1〜5: 不正設定ファイル各ケース（ファイル不在 / パース不能 / キー欠如 / 構造不正（`H=200`・float `153.0`・`lo>hi` 等）/ `min_pink_ratio` 値域外）で exit code 1
- [ ] NFR-003 import 互換: `uv run python -c "from postprocess_pink_id import compute_pink_ratio, FIXED_HSV_RANGES, MIN_PINK_RATIO, select_pink_bbox, clip_bbox, build_keypoint_rect_roi"` が成功（import 元 analyze_clothing_color.py / plot_pink_ratio_timeline.py / visualize_disagreement_frames.py の互換確認）
- [ ] AC-003-1〜3: 優先順位の 3 ケースをサマリ表示で確認
- [ ] AC-005-1/2: サマリ表示の指定時/未指定時
- [ ] `scripts/README.md` の postprocess_pink_id.py セクションに `--hsv-config` と設定ファイル形式を追記
- [ ] CLAUDE.md / `docs/BACKLOG.md` 更新
