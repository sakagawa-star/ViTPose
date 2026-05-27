# feat-054 機能設計書: analyze_clothing_color.py の HSV 設定ファイル（JSON）出力対応

## 1.1 対応要求マッピング

| 要求ID | 設計セクション |
|--------|----------------|
| FR-001 推奨レンジを feat-053 互換 JSON へ書き出す | 1.4.1 `build_hsv_config_dict` / `write_hsv_config` |
| FR-002 JSON 出力パスの決定（常時出力・`--json-out`） | 1.4.2 CLI 引数 / `main()` のパス決定 |
| FR-003 空レンジ時の振る舞い | 1.4.3 `main()` の分岐 |
| NFR-003 後方互換性 | 1.7 インターフェース定義 / 2.4 ADR |

## 1.2 システム構成

改修対象は `scripts/analyze_clothing_color.py` の 1 ファイルのみ。

```
analyze_clothing_color.py
├── parse_args()                ← 改修: --json-out を追加
├── propose_hsv_ranges()        ← 変更なし（既存。proposed_ranges を返す）
├── build_hsv_config_dict()     ← 新規: proposed_ranges → feat-053 互換 dict
├── write_hsv_config()          ← 新規: dict を JSON ファイルへ書き出す
└── main()                      ← 改修: JSON 出力パス決定 + 空レンジ分岐 + 書き出し呼び出し
```

依存関係（import）:

```
analyze_clothing_color.py
  ├── import json                          ← 追加（標準ライブラリ。既存の import 群に json は無い）
  └── from postprocess_pink_id import (build_keypoint_rect_roi, compute_pink_ratio,
                                       FIXED_HSV_RANGES, MIN_PINK_RATIO)  ← MIN_PINK_RATIO を追加 import
```

注: 既存 `analyze_clothing_color.py` は `argparse / os / sys / cv2 / numpy / matplotlib` を import
しているが **`json` は import していない**。`write_hsv_config` の `json.dump` 使用のため
`import json` をファイル冒頭の標準ライブラリ群へ追加する（追加しないと `NameError`）。

`postprocess_pink_id.MIN_PINK_RATIO`（=0.03）は feat-053 でも残置が確定している定数。これを
単一の真実源として import し、analyze 側でハードコードしない。

## 1.3 技術スタック

- 言語: Python 3.10.16
- ライブラリ: 既存依存のみ（`json` は標準ライブラリ、追加なし）
- パッケージ管理: uv

## 1.4 各機能の詳細設計

### 1.4.1 `build_hsv_config_dict` / `write_hsv_config`（FR-001）

#### データフロー

入力:
- `proposed_ranges`: `list[tuple[tuple[int,int,int], tuple[int,int,int]]]`
  （`propose_hsv_ranges()` の第 1 戻り値。各値は Python `int`）
- `min_pink_ratio`: `float`（呼び出し側から `MIN_PINK_RATIO` を渡す）

中間（dict）:
```python
{
    "fixed_hsv_ranges": [[[H_lo, S_lo, V_lo], [H_hi, S_hi, V_hi]], ...],
    "min_pink_ratio": 0.03,
}
```

出力: 上記 dict を `json.dump(d, f, indent=2, ensure_ascii=False)` でファイルへ書き出す。

#### 処理ロジック

```python
def build_hsv_config_dict(proposed_ranges: list, min_pink_ratio: float) -> dict:
    """proposed_ranges を feat-053 互換の設定 dict へ変換する。tuple → list、値は int 維持。"""
    return {
        "fixed_hsv_ranges": [[list(lo), list(hi)] for lo, hi in proposed_ranges],
        "min_pink_ratio": float(min_pink_ratio),
    }


def write_hsv_config(path: str, proposed_ranges: list, min_pink_ratio: float) -> None:
    """設定 dict を JSON ファイルへ書き出す（scripts/conf/*.json と同じ compact 整形）。"""
    config = build_hsv_config_dict(proposed_ranges, min_pink_ratio)
    # 1 レンジ = 1 行（[[H,S,V],[H,S,V]]）で並べる手組み整形。json.dump(indent=2) は
    # 整数 1 つずつ改行する縦長になり可読性が低いため採用しない（ADR-6）。
    range_lines = ",\n".join("    " + json.dumps(r) for r in config["fixed_hsv_ranges"])
    text = (
        "{\n"
        '  "fixed_hsv_ranges": [\n'
        f"{range_lines}\n"
        "  ],\n"
        f'  "min_pink_ratio": {json.dumps(config["min_pink_ratio"])}\n'
        "}\n"
    )
    with open(path, "w") as f:
        f.write(text)
```

- `proposed_ranges` の各値は `propose_hsv_ranges()` 内で `int(round(...))` 済みのため Python `int`。
  `json.dumps` は `int` を小数点なしの整数（`153`）で書く → `load_hsv_config` の `isinstance(v, int)`
  検証を通る（AC-001-3）。
- tuple は `list(...)` で配列化（`build_hsv_config_dict`）。`json.dumps(r)`（デフォルト separators
  `(", ", ": ")`）で 1 レンジが `[[153, 21, 125], [179, 255, 255]]` の 1 行になる。
- 整形は文字列読みやすさのみが目的で、`json.load` は改行・インデントに非依存のため
  `load_hsv_config` の受理（AC-001-2）には影響しない。

#### 出力 JSON が load_hsv_config を必ず通る根拠（不変条件）

`propose_hsv_ranges()` の出力は構造上、feat-053 の検証をすべて満たす:
- 各成分は `int`（`int(round(...))`）。bool/float ではない
- `H ∈ [0,179]`: `propose_hsv_ranges` の H 構築は 3 分岐すべてで [0,179] に収まる。
  - 非色相環分岐（`0 <= H_lo_i and H_hi_i <= 179`）: 採択条件そのものが H 下限 0 以上・H 上限 179 以下を保証。
    なお末尾の `proposed = [r for r in proposed if r[0][0] <= r[1][0]]` で `H_lo_i <= H_hi_i` も保証
  - 色相環分岐（`H_lo_i < 0` / `H_hi_i > 179`）: 生成タプルの H は `0` / `179` / `180+H_lo_i` / `H_hi_i-180`
    のいずれかで、いずれも [0,179] に収まる（reduce 後）
- `S_lo, V_lo ∈ [0,255]`: `Sc`/`Vc` は `extract_chroma_hsv` の `S>=sat_min` マスク後画素（値域 [0,255]）で、
  そのパーセンタイル → `s_lo,v_lo ∈ [0,255]`。上限は固定 255 のため `lo <= 255 = hi`
- `proposed_ranges` が非空のときのみ書き出す（FR-003）→ `fixed_hsv_ranges` は非空配列

したがって `load_hsv_config` を必ず通る。ただし本不変条件は補足であり、AC-001-2 は
**実際に `load_hsv_config(<出力パス>)` へ通して検証する実測 AC** とする（不変条件の主張に依存しない）。

#### エラーハンドリング

- ファイル書き込み失敗（権限・ディスク等）: 例外を `main()` 側で捕捉し、`[ERROR] 設定ファイル
  保存失敗: {e}` を表示して `sys.exit(1)`。JSON 書き込みは PNG 保存**後**に行うため（1.4.3 / ADR-5）、
  この時点で PNG は既に保存済み。診断 PNG は失われない（ADR-3 と一貫）

#### 境界条件

- `proposed_ranges` が 1 要素（色相環をまたがない）: `fixed_hsv_ranges` は要素 1 個の配列
- `proposed_ranges` が 2 要素（色相環をまたぐ。赤・ピンク）: `fixed_hsv_ranges` は要素 2 個の配列
- `proposed_ranges` が空: `write_hsv_config` を**呼ばない**（FR-003、`main()` で分岐）

### 1.4.2 CLI 引数とパス決定（FR-002）

#### CLI 追加

`parse_args()` に以下を追加:
```python
parser.add_argument('--json-out', type=str, default=None,
                    help='Output HSV config JSON path '
                         '(default: <image_stem>_hsv_config.json)')
```

#### パス決定ロジック（`main()` 内、既存の PNG パス決定の直後）

```python
if args.json_out is None:
    json_out_path = os.path.splitext(args.image)[0] + '_hsv_config.json'
else:
    json_out_path = args.json_out
```

- 既存の PNG パス決定（`<image_stem>_color_analysis.png`）と同じ `os.path.splitext` 規約。
- 拡張子は `_hsv_config.json`。`_color_analysis.png` と stem を揃え、同じ入力画像由来と分かる命名。

### 1.4.3 `main()` の改修（FR-001 / FR-002 / FR-003）

既存 `main()` の推奨レンジ算出・ログ出力ブロック（`if proposed: ... else: ...`）はそのまま残し、
JSON 出力は既存の `render_analysis_png` 呼び出し（＋ `[INFO] 可視化PNGを保存`）の**後**に追加する。
PNG を先に確定させることで、JSON 書き込み失敗時でも診断 PNG を失わない（ADR-3 / ADR-5）。

擬似コード（既存行は `# 既存` で示す）:
```python
# 既存: proposed, s_lo, v_lo, proposed_ratio = propose_hsv_ranges(...)
# 既存: if proposed:  推奨ログ出力（proposed FIXED_HSV_RANGES / S_low,V_low / pink_ratio / NOTE）
# 既存: else:        [WARN] 推奨レンジ算出不可（有彩色画素なし）

# 既存: render_analysis_png(...) と [INFO] 可視化PNGを保存（PNG 保存失敗時は exit 1）

# --- feat-054 追加: JSON 設定ファイル出力（PNG 保存後）---
if proposed:
    try:
        write_hsv_config(json_out_path, proposed, MIN_PINK_RATIO)
    except Exception as e:
        print(f'[ERROR] 設定ファイル保存失敗: {e}')
        sys.exit(1)
    print(f'[INFO] HSV 設定ファイルを保存: {json_out_path} (min_pink_ratio={MIN_PINK_RATIO})')
else:
    print('[WARN] 推奨レンジが空のため HSV 設定ファイルは出力しません')
```

- 既存の `if proposed:` / `else:` ログ分岐は無変更（stdout の既存ログ順を保つ）。
- JSON 出力判定は PNG 保存後に独立した `if proposed:` で行う。空レンジ（`else`）では JSON を書かず
  `[WARN]` を 1 行出す（FR-003）。
- PNG 出力（`render_analysis_png`）は JSON より前に常時実行 → 空レンジでも JSON 失敗でも PNG は出る
  （AC-003-2 / ADR-3 と一貫）。
- exit code: JSON 書き出し成功 → 0、書き込み例外 → 1（PNG は保存済み）。空レンジは exit 1 にしない。

#### 条件分岐（すべての分岐先）

| 条件 | PNG 出力 | JSON 出力 | exit code |
|------|----------|-----------|-----------|
| `proposed` 非空 & JSON 書き込み成功 | する | する | 0 |
| `proposed` 非空 & JSON 書き込み失敗 | する（先に保存済み） | 失敗 | 1 |
| `proposed` 空 | する | しない（`[WARN]`） | 0（PNG 成功時） |
| PNG 保存失敗（既存挙動） | 失敗（既存ロジックで exit） | しない | 1 |

## 1.5 状態遷移

ステートフル処理・GUI なし。該当なし。

## 1.6 ファイル・ディレクトリ設計

### 入出力

| 種別 | パス | 形式 |
|------|------|------|
| 入力 | `<image>`（CLI 必須引数） | 静止画（PNG/JPG 等、cv2.imread 可能な形式） |
| 出力（既存） | `<image_stem>_color_analysis.png` または `--out` | PNG |
| 出力（新規） | `<image_stem>_hsv_config.json` または `--json-out` | JSON（feat-053 スキーマ） |

### 出力 JSON スキーマ（feat-053 と厳密一致）

```json
{
  "fixed_hsv_ranges": [
    [[153, 21, 125], [179, 255, 255]],
    [[0, 21, 125], [12, 255, 255]]
  ],
  "min_pink_ratio": 0.03
}
```

- `fixed_hsv_ranges`: 非空配列。各要素 `[lo, hi]`、`lo`/`hi` は `[H, S, V]`（整数）。
  `H ∈ [0,179]`, `S,V ∈ [0,255]`, 各成分 `lo[i] <= hi[i]`
- `min_pink_ratio`: `0.03`（固定）

## 1.7 インターフェース定義

### 新規関数

```python
def build_hsv_config_dict(proposed_ranges: list, min_pink_ratio: float) -> dict
def write_hsv_config(path: str, proposed_ranges: list, min_pink_ratio: float) -> None
```

### 改修関数

```python
def parse_args() -> argparse.Namespace   # --json-out を追加
def main() -> None                        # JSON 出力パス決定 + 分岐 + 書き出し
```

### import 追加

```python
from postprocess_pink_id import (build_keypoint_rect_roi, compute_pink_ratio,
                                 FIXED_HSV_RANGES, MIN_PINK_RATIO)  # MIN_PINK_RATIO 追加
```

呼び出し方向: `analyze_clothing_color.py` → `postprocess_pink_id`（定数 import のみ。循環なし）。

## 1.8 ログ・デバッグ設計

既存の `[INFO]`/`[WARN]`/`[ERROR]` プレフィックス規約を踏襲する。追加するログ:

| レベル | 出力ポイント | 内容 |
|--------|--------------|------|
| INFO | JSON 書き出し成功後 | `[INFO] HSV 設定ファイルを保存: {path} (min_pink_ratio={MIN_PINK_RATIO})` |
| WARN | 空レンジ時 | `[WARN] 推奨レンジが空のため HSV 設定ファイルは出力しません` |
| ERROR | 書き込み例外時 | `[ERROR] 設定ファイル保存失敗: {e}`（直後 exit 1） |

## 2. 記述ルール

### 2.4 設計判断の記録（ADR）

- **ADR-1: JSON 出力は常時（デフォルト）。`--json-out` で上書き**
  - 採用: 機能②の目的は写経の撲滅。常時出力ならコピペ作業が必ず消える。PNG が常時出力なのと対称
  - 却下: opt-in（`--json-out` 指定時のみ出力）→ デフォルト挙動が変わらず、写経撲滅が「指定し忘れ」で
    達成されないリスク（ユーザー確認で常時出力を選択）

- **ADR-2: `min_pink_ratio` は固定 0.03（`MIN_PINK_RATIO` を import）**
  - 採用: 静止画 ROI は服がほぼ全面のため `proposed_ratio≈0.6` と高く、動画 BB 内比率（肌・背景混じり）
    とは別物。静止画から動画用の適切な閾値は決められない。固定値を出して実運用で
    `postprocess_pink_id.py --min-pink-ratio` 側で再調整する分業（ユーザー確認済み）
  - 却下: analyze 側で `proposed_ratio` を書く → 動画では過大な閾値になり pink_id を取りこぼす
  - 却下: `--min-pink-ratio` CLI を analyze に足す → スコープ拡大。固定で十分（ユーザー確認済み）
  - 単一の真実源: `postprocess_pink_id.MIN_PINK_RATIO` を import（analyze 側でハードコードしない）

- **ADR-3: 空レンジ時は JSON を書かず WARN、PNG は継続**
  - 採用: `fixed_hsv_ranges` が空配列の JSON は `load_hsv_config` で exit 1 になる不正設定。
    不正ファイルを生成しても害しかない。PNG は診断目的で出す価値があるため継続（ユーザー確認済み）
  - 却下: 空でも空配列 JSON を書く → 下流で exit 1 になる無意味なファイル
  - 却下: 空レンジで exit 1 → PNG も出ず、診断材料を失う

- **ADR-4: tuple を明示的に `list(...)` 変換**
  - 採用: `json.dump` は tuple も配列化するが、明示変換で「JSON 配列を作る」意図を可読化。
    `int` 性は維持される（`list((153,21,125))` の各要素は `int` のまま）

- **ADR-6: JSON 整形は `scripts/conf/*.json` と同じ compact 形式（1 レンジ = 1 行）**
  - 採用: 手書きの `scripts/conf/E0014.json` / `example_hsv_config.json` は `[[H,S,V],[H,S,V]]` を 1 行に
    まとめた compact 形式。機能②はこれら手写経ファイルの置き換えなので、整形も合わせると
    既存ファイルとの diff・目視が容易（ユーザー手動テストで縦長が見づらいとの指摘を反映）
  - 却下: `json.dump(indent=2)`（初版）→ 整数 1 つずつが改行され縦長で見づらい
  - 実装: `json.dumps(range)` で各レンジを 1 行化し、トップレベルのみ手組み整形する

- **ADR-5: JSON 出力は PNG 保存の後に行う**
  - 採用: JSON 書き込みは権限・ディスク等の環境要因で失敗しうる。先に PNG を保存しておけば、
    JSON 失敗時でも診断 PNG は残る（ADR-3「診断材料を失わない」と一貫）。レビュー中-3 を反映
  - 却下: JSON を PNG より前に書く（初版）→ JSON 書き込み失敗で `sys.exit(1)` すると PNG も出ず、
    ADR-3 の方針と矛盾する
  - 既存の推奨ログ分岐（`if proposed/else`）は無変更のまま PNG 前に残し、JSON 出力判定のみ
    PNG 後に独立した `if proposed:` で行う（stdout の既存ログ順を保つ）
