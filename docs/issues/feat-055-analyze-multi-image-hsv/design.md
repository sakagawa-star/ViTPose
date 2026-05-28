# feat-055 機能設計書: analyze_clothing_color.py の複数画像入力・プール提案・閾値検証対応

## 1.1 対応要求マッピング

| 要求 ID | 設計セクション |
|---------|----------------|
| FR-001（複数画像入力・後方互換） | 1.4.1 CLI 拡張 / 1.4.2 main 制御フロー / ADR-3 |
| FR-002（プール方式提案） | 1.4.3 プール提案 / 1.7 `propose_ranges_from_chroma` / ADR-1, ADR-3 |
| FR-003（閾値検証レポート） | 1.4.4 閾値検証 / ADR-2 |
| FR-004（画像ごと PNG） | 1.4.5 PNG 出力 / ADR-5 |
| FR-005（統合 JSON 出力） | 1.4.6 JSON 出力 / ADR-4, ADR-5 |

## 1.2 システム構成

- 変更対象は **`scripts/analyze_clothing_color.py` のみ**。
- 既存関数を最大限再利用し、新規追加は「複数画像対応の制御フロー」と「クロマ配列からの提案ヘルパ」のみ。

```
analyze_clothing_color.py
├── parse_args()                      [変更] positional を nargs='+' 化、--threshold 追加
├── load_models()                     [流用]
├── estimate_halpe26_fullframe()      [流用]
├── build_torso_roi()                 [流用]
├── extract_chroma_hsv()              [流用]
├── propose_ranges_from_chroma()      [新規] クロマ配列(Hc,Sc,Vc)→(proposed, s_lo, v_lo)。循環統計コア
├── propose_hsv_ranges()              [リファクタ] 上記ヘルパを呼ぶ薄いラッパに変更（出力不変）
├── compute_ratio_for_ranges()        [流用]
├── render_analysis_png()             [流用]
├── build_hsv_config_dict()           [流用]
├── write_hsv_config()                [流用]
├── run_single_image()                [新規] 単一画像モード（feat-054 相当の処理を関数化）
├── run_multi_image()                 [新規] 複数画像モード（FR-002〜005）
└── main()                            [変更] len(images) で run_single_image / run_multi_image に分岐
```

依存方向（循環なし）:
`main → run_single_image/run_multi_image → {load_models, estimate_halpe26_fullframe, build_torso_roi, extract_chroma_hsv, propose_*, compute_ratio_for_ranges, render_analysis_png, write_hsv_config}`

外部依存（無変更で import）:
- `merge_halpe26`: `WB_CONFIG, WB_CHECKPOINT, AIC_CONFIG, AIC_CHECKPOINT, merge_to_halpe26`
- `postprocess_pink_id`: `build_keypoint_rect_roi, compute_pink_ratio, FIXED_HSV_RANGES, MIN_PINK_RATIO`

## 1.3 技術スタック

- 言語: Python 3.10.16
- ライブラリ: OpenCV (cv2), NumPy, matplotlib（いずれも既存依存、新規追加なし）、MMPose 0.24.0
- パッケージ管理: uv（`uv run python` 経由で実行）
- 選定理由: 既存 `analyze_clothing_color.py` と同一スタック。プール処理は NumPy 配列結合のみで追加依存不要。

## 1.4 各機能の詳細設計

### 1.4.1 CLI 拡張（FR-001）

**データフロー**:
- `image`（既存 positional, 単一 str）→ `images`（positional, `nargs='+'`, list[str], 1 個以上）。
- 新規 `--threshold`: float, 値域 `[0.0, 1.0]`, デフォルト `MIN_PINK_RATIO`（=0.03）。チェッカは
  **新規定義する `_check_ratio`** を使う（`_check_conf` を流用すると範囲外時のエラーメッセージが
  "kpt-conf-min must be in ..." と無関係な引数名で表示されるため。高-1 対応）。
- 既存 `--out` / `--json-out` / `--device` / `--kpt-conf-min` / `--min-roi-area` / `--percentile` /
  `--sat-min` / `--val-min` は維持。

**処理ロジック**: 新規チェッカと positional 定義を以下のように追加・変更する（意図伝達用、そのままコピー不可）:
```python
def _check_ratio(v: str) -> float:
    fv = float(v)
    if not (0.0 <= fv <= 1.0):
        raise argparse.ArgumentTypeError(f"threshold must be in [0.0, 1.0], got {fv}")
    return fv

parser.add_argument('images', type=str, nargs='+', help='Input still image path(s)')
parser.add_argument('--threshold', type=_check_ratio, default=MIN_PINK_RATIO,
                    help='Per-image pink_ratio PASS threshold ([0.0,1.0], default 0.03)')
```

### 1.4.2 main 制御フロー（FR-001）

**処理ロジック**:
```
args = parse_args()
load_models() を 1 回だけ実行（両モード共通）
if len(args.images) == 1:
    run_single_image(args.images[0], args, models)   # feat-054 相当
else:
    run_multi_image(args.images, args, models)        # 複数画像モード
```

- **分岐の根拠**: 単一画像モードは feat-054 のコードパスをそのまま使い、出力を完全一致させる（ADR-3）。
- `run_single_image` は現行 `main()` 本体（画像読込〜PNG〜JSON）を関数へ切り出したもので、ロジックは不変。
  デフォルト出力名は現行どおり `<image_stem>_color_analysis.png` / `<image_stem>_hsv_config.json`、
  `--out`/`--json-out` 指定時はそれを使う。

**エラーハンドリング**:
- モデルロード失敗 → `[ERROR] モデルロード失敗: {e}` を表示し exit 1（現行どおり）。

### 1.4.2.1 run_multi_image のフェーズ順序（FR-002〜005 / 中-3, 中-4 対応）

`run_multi_image` は以下の 5 フェーズを**この順序**で実行する。**PNG/JSON の出力はフェーズ 4 以降**に置き、
読込・推論の失敗（フェーズ 1）が起きた場合は出力ファイルを一切作らないことを保証する（FR 信頼性 / 境界条件）。
各画像のクロマ画素は**フェーズ 1 で `compute_hsv_stats` を 1 回だけ呼び**、その戻り値の `Hc/Sc/Vc` を
プール（フェーズ 2）にも流用する（`extract_chroma_hsv` の二重呼び出しを避ける。中-3 対応）。

```python
def run_multi_image(images, args, models):
    if args.out is not None:
        print('[WARN] 複数画像モードでは --out は無視され、画像ごとの名前が使われます')  # ADR-5

    # --- フェーズ1: 全画像を逐次 imread→推論→ROI→stats 収集（失敗ならここで exit 1。出力ファイルなし）---
    per_image = []                      # 各要素 dict{name, frame, roi_box, stats}
    pooled_H, pooled_S, pooled_V = [], [], []
    for k, img in enumerate(images, 1):
        frame = cv2.imread(img)
        if frame is None:
            print(f'[ERROR] 画像を読み込めません: {img}'); sys.exit(1)
        h, w = frame.shape[:2]
        print(f'[INFO] [{k}/{len(images)}] 入力画像: {img} ({w}x{h})')
        halpe26 = estimate_halpe26_fullframe(...)            # 結果空なら内部で exit 1
        roi_box, roi_source = build_torso_roi(halpe26, w, h, args.kpt_conf_min, args.min_roi_area)
        x1, y1, x2, y2 = roi_box
        roi_bgr = frame[y1:y2, x1:x2]
        stats = compute_hsv_stats(roi_bgr, args.sat_min, args.val_min, args.percentile)  # Hc/Sc/Vc を含む
        per_image.append({'name': img, 'frame': frame, 'roi_box': roi_box, 'stats': stats})
        pooled_H.append(stats['Hc']); pooled_S.append(stats['Sc']); pooled_V.append(stats['Vc'])

    # --- フェーズ2: プール提案（np.concatenate で配列直結合、BGR往復なし）---
    allH = np.concatenate(pooled_H); allS = np.concatenate(pooled_S); allV = np.concatenate(pooled_V)
    proposed, s_lo, v_lo = propose_ranges_from_chroma(allH, allS, allV, args.percentile)
    if proposed:
        print('[INFO] === 推奨 (プール) ==='); print(f'[INFO] proposed FIXED_HSV_RANGES = {proposed}')
        print(f'[INFO] proposed S_low={s_lo}, V_low={v_lo}')
    else:
        print('[WARN] 推奨レンジ算出不可（全画像で有彩色画素なし）')

    # --- フェーズ3: 閾値検証レポート（表示のみ、exit 0）---
    min_ratio = 1.0
    for d in per_image:
        roi_bgr = d['frame'][d['roi_box'][1]:d['roi_box'][3], d['roi_box'][0]:d['roi_box'][2]]
        r = compute_ratio_for_ranges(roi_bgr, proposed); d['proposed_ratio'] = r
        min_ratio = min(min_ratio, r)
        print(f'[INFO]   {basename(d["name"])}: ratio={r:.4f} [{"OK" if r > args.threshold else "NG"}]')
    print(f'[INFO] min ratio = {min_ratio:.4f} ({"ALL PASS" if min_ratio > args.threshold else "SOME FAIL"})')
    if min_ratio <= args.threshold:
        print('[WARN] 閾値を下回る画像があります。--percentile を下げてレンジを広げるか、入力画像の選定を見直してください')

    # --- フェーズ4: 画像ごと PNG（提案後。フェーズ1失敗時はここに到達しない）---
    for d in per_image:
        roi_bgr = d['frame'][...]; current_ratio = compute_pink_ratio(roi_bgr)  # FIXED_HSV_RANGES基準
        out_path = splitext(d['name'])[0] + '_color_analysis.png'
        try:
            render_analysis_png(d['frame'], d['roi_box'], d['stats'], proposed,
                                current_ratio, d['proposed_ratio'], out_path)
        except Exception as e:
            if os.path.exists(out_path): os.remove(out_path)
            print(f'[ERROR] PNG保存失敗: {e}'); sys.exit(1)
        print(f'[INFO] 可視化PNGを保存: {out_path}')

    # --- フェーズ5: 統合 JSON（1個）---
    if proposed:
        json_out = args.json_out or (splitext(images[0])[0] + '_pooled_hsv_config.json')
        write_hsv_config(json_out, proposed, MIN_PINK_RATIO)
        print(f'[INFO] HSV 設定ファイルを保存: {json_out} (min_pink_ratio={MIN_PINK_RATIO})')
    else:
        print('[WARN] 推奨レンジが空のため HSV 設定ファイルは出力しません')
```

- `roi_bgr` は `frame` と `roi_box` から都度スライスする（メモリ節約のため per_image に保持しない。ビューなのでコストは無視可）。
- `compute_hsv_stats` の `Hc/Sc/Vc` をプールに流用するため `extract_chroma_hsv` は画像あたり 1 回のみ（中-3）。

### 1.4.3 プール提案（FR-002）

**データフロー**:
- 入力: 各画像の胴体 ROI（BGR, `np.ndarray`, shape=(h,w,3), uint8）。
- 中間: 各画像から `extract_chroma_hsv(roi, sat_min, val_min)` → `(Hc, Sc, Vc, chroma_ratio)`。
  `Hc/Sc/Vc` は uint8 1 次元配列（クロマ画素のみ）。
- プール: 全画像の `Hc` を `np.concatenate` で結合（`Sc`,`Vc` も同様）。**BGR への往復変換は行わない**（ADR-3）。
- 出力: `propose_ranges_from_chroma(pooled_Hc, pooled_Sc, pooled_Vc, percentile)` →
  `(proposed, s_lo, v_lo)`。`proposed` は `list[((H_lo,S_lo,V_lo),(H_hi,255,255))]`（1〜2 本）。

**処理ロジック（`propose_ranges_from_chroma`）**: 既存 `propose_hsv_ranges` の循環統計部分（実コードで
`theta = ...` から反転タプル破棄まで、概ね 210-230 行）をそのまま移設する。`proposed_ratio` の計算
（`compute_ratio_for_ranges`、231 行）と return（232 行）は新 `propose_hsv_ranges` 側に残す。すなわち:
1. `len(Hc)==0` なら `([], 0, 0)` を返す。
2. H を実角度（`H*2°`）に変換して循環平均 `H_center` を算出（`arctan2` ベース）。
3. `H_center` まわりの相対角 `rel = ((Hc - H_center + 90) % 180) - 90` を取り、
   `percentile` / `100-percentile` 分位で `rel_lo` / `rel_hi`。
4. `H_lo_i = round(H_center + rel_lo)`、`H_hi_i = round(H_center + rel_hi)`。
5. `s_lo = round(percentile(Sc, percentile))`、`v_lo = round(percentile(Vc, percentile))`（S/V 下限のみデータ駆動）。
6. `H_lo_i`/`H_hi_i` の範囲に応じて、通常 1 本・色相環またぎ時 2 本へ分割（既存と同一の 3 分岐）。
7. 反転タプル（lo>hi）を破棄して返す。

**リファクタ後の `propose_hsv_ranges`**（出力不変・後方互換用）:
```python
def propose_hsv_ranges(roi_bgr, sat_min, val_min, percentile):
    Hc, Sc, Vc, _ = extract_chroma_hsv(roi_bgr, sat_min, val_min)
    proposed, s_lo, v_lo = propose_ranges_from_chroma(Hc, Sc, Vc, percentile)
    proposed_ratio = compute_ratio_for_ranges(roi_bgr, proposed)
    return proposed, s_lo, v_lo, proposed_ratio
```

**エラーハンドリング / 境界条件**:
- 全画像でクロマ画素 0（`pooled_Hc` が空）→ `propose_ranges_from_chroma` は `([],0,0)` を返す。
  呼び出し側は `[WARN] 推奨レンジ算出不可（全画像で有彩色画素なし）` を表示し、PNG は描画するが
  JSON は出力しない（FR-005 AC-005-2）。
- 一部画像のみクロマ 0 → その画像は `Hc` 長さ 0 の配列を結合（寄与ゼロ）。提案は残り画像から算出され、
  当該画像の検証 ratio は低く出て FR-003 で `[NG]` として表示される。

### 1.4.4 閾値検証レポート（FR-003）

**データフロー**:
- 入力: `proposed`（プール提案）、各画像 ROI、`threshold`（float）。
- 出力（stdout）: 画像ごとに `ratio` と `[OK]`/`[NG]`、全体の `min ratio`、`ALL PASS`/`SOME FAIL`。

**処理ロジック**:
```
min_ratio = 1.0
for (name, roi) in rois:
    r = compute_ratio_for_ranges(roi, proposed)
    min_ratio = min(min_ratio, r)
    flag = 'OK' if r > threshold else 'NG'
    print(f'[INFO]   {basename(name)}: ratio={r:.4f} [{flag}]')
print(f'[INFO] min ratio = {min_ratio:.4f} ({"ALL PASS" if min_ratio > threshold else "SOME FAIL"})')
if min_ratio <= threshold:
    print('[WARN] 閾値を下回る画像があります。--percentile を下げてレンジを広げるか、'
          '入力画像の選定を見直してください')
```

- `proposed` が空（クロマ 0）のとき `compute_ratio_for_ranges` は 0.0 を返すため、全画像 `[NG]` /
  `SOME FAIL` となる。ただしこのケースは FR-002 の `[WARN]` が先に出る。
- **判定は表示のみ**。`SOME FAIL` でも exit 0 で正常終了する（ADR-2）。`> threshold` で PASS
  （等値は NG＝閾値ちょうどは満たさない、要求の「`> 0.03`」に一致）。

### 1.4.5 PNG 出力（FR-004）

**データフロー**:
- 入力: 各画像 frame、その roi_box、その画像の `stats`（`compute_hsv_stats` 結果）、共通 `proposed`、
  当該画像の `current_ratio`（`compute_pink_ratio(roi)`）、当該画像の `proposed_ratio`（`compute_ratio_for_ranges(roi, proposed)`）。
- 出力: 画像ごとに `<image_stem>_color_analysis.png`。

**処理ロジック**: ループ内で既存 `render_analysis_png(frame, roi_box, stats, proposed, current_ratio, proposed_ratio, out_path_i)` を
そのまま呼ぶ。`proposed` は全画像共通（プール結果）、`current_ratio`/`proposed_ratio` は画像ごとに計算する。
- `current_ratio` は `compute_pink_ratio(roi_bgr)`（`ranges` 省略＝グローバル `FIXED_HSV_RANGES` 基準）で計算する。
- `render_analysis_png` は**内部で current mask を `FIXED_HSV_RANGES` 固定で描画**する（既存実装、無変更）。
  すなわち各 PNG の "current mask" パネルは常に現行ハードコードレンジ基準、"proposed mask" パネルは
  プール提案レンジ基準で描かれる（中-2 の明示）。

**エラーハンドリング**:
- ある画像の PNG 保存に失敗 → 既存 `render_analysis_png` 呼び出しを `try/except` で囲み、
  失敗時は当該不完全ファイルを削除して `[ERROR] PNG保存失敗: {e}` を表示し exit 1（FR-004 AC-004-2、現行と同じ方針）。

**ADR-5（出力名規約）**:
- 複数画像モードでは PNG は常に `<image_stem>_color_analysis.png`（画像ごと）。`--out` が明示指定された場合は
  `[WARN] 複数画像モードでは --out は無視され、画像ごとの名前が使われます` を表示して無視する。

### 1.4.6 JSON 出力（FR-005）

**データフロー**:
- 入力: 共通 `proposed`、`MIN_PINK_RATIO`（=0.03 固定）。
- 出力: 1 個の JSON（`fixed_hsv_ranges` + `min_pink_ratio`）。整形は既存 `write_hsv_config` に委譲
  （`scripts/conf/*.json` と同じ compact 形式）。

**処理ロジック**:
```
if proposed:
    json_out = args.json_out or (splitext(images[0])[0] + '_pooled_hsv_config.json')
    write_hsv_config(json_out, proposed, MIN_PINK_RATIO)   # PNG 出力後に実行
    print(f'[INFO] HSV 設定ファイルを保存: {json_out} (min_pink_ratio={MIN_PINK_RATIO})')
else:
    print('[WARN] 推奨レンジが空のため HSV 設定ファイルは出力しません')
```

- `min_pink_ratio` は `MIN_PINK_RATIO`（0.03）固定（ADR-4）。`--threshold` は検証専用で JSON には書かない。
- JSON は全 PNG 保存後に書き出す（書込失敗でも診断 PNG を保全。feat-054 と同じ順序方針）。
- **エラーハンドリング**: 書込失敗 → `[ERROR] 設定ファイル保存失敗: {e}` を表示し exit 1（feat-054 と同じ）。

### 境界条件まとめ

| 入力 | 振る舞い |
|------|----------|
| 画像 1 枚 | 単一画像モード（feat-054 と完全一致） |
| 画像 0 枚 | argparse が `nargs='+'` で弾く（exit 2） |
| いずれかの画像が読込不可 | `[ERROR]` で exit 1（フェーズ1で fail fast、現行 `cv2.imread is None` 判定）。読込/推論失敗はフェーズ1で起き、PNG/JSON 出力（フェーズ4以降）より前なので**出力ファイルは一切作られない** |
| ある画像の推論結果が空 | 既存 `estimate_halpe26_fullframe` が `[ERROR]` exit 1（フェーズ1、出力ファイルなし） |
| ある画像で胴体 ROI 構築失敗 | `build_torso_roi` が画像全体へフォールバック（`[WARN]`） |
| 全画像クロマ 0 | 推奨レンジ空 → JSON 不出力 + `[WARN]`、PNG は描画 |
| 一部画像クロマ 0 | 寄与ゼロでプール、当該画像は検証で `[NG]` |

## 1.5 状態遷移

該当なし（ステートレスな CLI バッチ処理）。

## 1.6 ファイル・ディレクトリ設計

- **入力**: 1 個以上の画像ファイル（PNG/JPG 等、`cv2.imread` が読める形式）。
- **出力 PNG**: 各画像と同じディレクトリに `<image_stem>_color_analysis.png`。
- **出力 JSON（複数画像モード）**: `--json-out` 指定パス、省略時 `<first_image_stem>_pooled_hsv_config.json`。
- **出力 JSON（単一画像モード）**: feat-054 どおり `<image_stem>_hsv_config.json`（変更なし）。
- **JSON スキーマ**（feat-053 互換、2 キーのみ）:
  ```json
  {
    "fixed_hsv_ranges": [[[H_lo, S_lo, V_lo], [H_hi, 255, 255]], ...],
    "min_pink_ratio": 0.03
  }
  ```
  - `fixed_hsv_ranges`: list[[ [int,int,int], [int,int,int] ]]、各値 `[0,255]` の整数（H は `[0,179]`）。
  - `min_pink_ratio`: float, 既定 0.03。

## 1.7 インターフェース定義

新規・変更する公開関数のシグネチャ:

```python
def propose_ranges_from_chroma(
    Hc: np.ndarray, Sc: np.ndarray, Vc: np.ndarray, percentile: float,
) -> tuple[list, int, int]:
    """クロマ画素配列から循環統計で推奨レンジを算出。戻り値 (proposed_ranges, s_lo, v_lo)。
    Hc が空なら ([], 0, 0)。"""

def propose_hsv_ranges(
    roi_bgr: np.ndarray, sat_min: int, val_min: int, percentile: float,
) -> tuple[list, int, int, float]:
    """[リファクタ] extract_chroma_hsv → propose_ranges_from_chroma → ratio。戻り値・挙動は現行と同一。"""

def run_single_image(image: str, args: argparse.Namespace, models: tuple) -> None:
    """単一画像モード。feat-054 の main 本体を関数化したもの（ロジック不変）。"""

def run_multi_image(images: list[str], args: argparse.Namespace, models: tuple) -> None:
    """複数画像モード。全画像推論→ROI→クロマ抽出→プール提案→検証→画像ごとPNG→統合JSON。"""
```

- `models` タプルは `load_models()` の戻り値 6 要素
  `(wb_model, aic_model, wb_dataset, wb_dataset_info, aic_dataset, aic_dataset_info)`。
- 1 関数 1 責務: `run_single_image`/`run_multi_image` はモード別の手順統括、提案ロジックは
  `propose_ranges_from_chroma` に集約。

## 1.8 ログ・デバッグ設計

- 既存の `print('[INFO] ...')` / `[WARN]` / `[ERROR]` 接頭辞方式を踏襲（logging モジュールは使わない、現行踏襲）。
- 複数画像モードの主要ログポイント:
  - 各画像: `[INFO] [k/N] 入力画像: {path} ({w}x{h})`、`[INFO] ROI source=..., roi_box=...`
  - プール後: `[INFO] === 推奨 (プール) ===`、`proposed FIXED_HSV_RANGES = ...`、`proposed S_low=.., V_low=..`
  - 検証: 画像ごと `ratio=.. [OK/NG]`、`min ratio = .. (ALL PASS/SOME FAIL)`、未達時 `[WARN]`
  - 出力: `[INFO] 可視化PNGを保存: ...`（N 回）、`[INFO] HSV 設定ファイルを保存: ...`（1 回）
- ratio 表示は小数 4 桁（`:.4f`、現行踏襲）。

## 2.4 設計判断の記録（ADR）

### ADR-1: 提案方式はプール方式に一本化
- **採用**: 全画像の ROI クロマ画素を結合し 1 セット提案。
- **却下**: union 方式（各画像提案の単純結合）→ レンジ本数が増え冗長。`--method` 切替 → 実装・テスト・
  ドキュメントが増える割に、調査で両方式とも全 PASS かつプールの方が簡潔（2 本 vs 6 本）だったため不要。

### ADR-2: 閾値検証はレポートのみ（自動拡幅・エラー終了はしない）
- **採用**: 各画像 ratio と PASS/FAIL を表示し、未達時は `[WARN]` で対処（`--percentile` を下げる）を提示。exit 0。
- **却下**: percentile 自動拡幅 → 色相が本質的に重ならない画像群で無限に広がるリスク、上限ガード設計が必要で
  複雑化。エラー終了（exit 1）→ 診断ツールとしては不便（値を見て人が判断したい）。

### ADR-3: 単一画像モードは既存コードパスを維持し、プールに BGR 往復変換を使わない
- **採用**: `len(images)==1` は `run_single_image`（feat-054 相当）で処理し出力を完全一致。複数画像のプールは
  `extract_chroma_hsv` のクロマ配列を直接 `np.concatenate` し、`propose_ranges_from_chroma` に渡す。
- **却下**: 「クロマ画素を (N,1,3) の HSV 画像に詰めて HSV2BGR→propose_hsv_ranges に渡す」方式 →
  `cv2.COLOR_HSV2BGR`→`BGR2HSV` のラウンドトリップが非可逆で彩度境界の画素が約 0.4% 脱落する
  （調査スクリプトのレビューで確認）。配列直結合ならこの誤差が出ず、N=1 のプールが単一画像提案と数学的に一致する。
- **副次**: `propose_hsv_ranges` を「`extract_chroma_hsv` + `propose_ranges_from_chroma` + ratio」の薄いラッパに
  リファクタする（pure extract-method、出力不変）。これにより単一/複数で循環統計コードを共有する。

### ADR-4: JSON の min_pink_ratio は 0.03 固定、--threshold は検証専用
- **採用**: 出力 JSON の `min_pink_ratio` は `MIN_PINK_RATIO`（0.03）固定（feat-054 踏襲）。`--threshold` は
  各画像の PASS/FAIL 判定にのみ使い、JSON には書かない。
- **理由**: 静止画 ROI の pink_ratio は「服がほぼ全面」の上限値で、実動画 BB 比率はこれより低い（feat-054 の NOTE）。
  実運用の `min_pink_ratio` は `postprocess_pink_id.py --min-pink-ratio` で別途調整する前提のため、静止画から
  動画用閾値を確定できない。検証用の `--threshold` と runtime 設定値 `min_pink_ratio` を分離する。
- **却下**: `--threshold` をそのまま JSON の `min_pink_ratio` に書く → 単一画像モードの feat-054 出力
  バイト一致（AC-001-1）を壊しうる、かつ静止画閾値を動画にそのまま持ち込む誤用を招く。

### ADR-5: PNG は画像ごと、JSON は 1 個。複数画像モードで --out は無視
- **採用**: 複数画像モードでは PNG を `<image_stem>_color_analysis.png` で画像ごとに出力。JSON は
  `--json-out`（既定 `<first_image_stem>_pooled_hsv_config.json`）で 1 個。`--out` 明示時は `[WARN]` で無視。
- **却下**: 統合 PNG 1 枚 → 新規描画ロジックが必要（既存 `render_analysis_png` を再利用できない）。
  `--out` を複数画像で活かす（連番付与等）→ 命名規約が複雑化し既存規約から乖離。
