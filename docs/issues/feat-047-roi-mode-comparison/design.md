# feat-047 機能設計書: ROI モード比較・可視化ツール

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001（JSON 読み込み） | §4.1 |
| FR-002（α-1 散布図） | §4.2 |
| FR-003（不一致 CSV） | §4.3 |
| FR-004（compare サマリ） | §4.4 |
| FR-005（不一致 PNG） | §4.5 |
| FR-006（シーク失敗） | §4.6 |
| FR-007（visualize サマリ） | §4.7 |
| NFR-001（性能） | §6 |

## 2. システム構成

### 2.1 モジュール構成

```
scripts/
├─ compare_roi_modes.py             # 新規
└─ visualize_disagreement_frames.py # 新規
```

両スクリプトは独立。`compare_roi_modes.py` の出力 CSV を `visualize_disagreement_frames.py` の入力として連鎖実行する想定。

### 2.2 依存関係

- 共通: `cv2`, `numpy`, `json`, `csv`, `argparse`, `os`, `sys`, `pathlib`, `time`
- `compare_roi_modes.py`: `matplotlib` (Agg バックエンド)

新規ライブラリ追加なし。

### 2.3 ディレクトリ構成

既存と同じ。新規スクリプトを `scripts/` 配下に追加。

## 3. 技術スタック

| 項目 | 値 | 備考 |
|------|-----|------|
| Python | 3.10.16 | プロジェクト既定 |
| matplotlib | 既存 | feat-040 で使用済み |
| OpenCV | 既存 | 動画 I/O、描画 |

## 4. 各機能の詳細設計

### compare_roi_modes.py

### 4.1 FR-001: JSON ディレクトリ読み込み

#### 4.1.1 データフロー

- 入力: `--bb-json-dir`, `--kp-json-dir`
- 中間: `frame_data: dict[int, dict]` （key=frame_idx、value=各モードの選択結果）
- 出力: 内部データ、後続関数に渡す

#### 4.1.2 関数シグネチャ

```python
def load_pink_id_results(json_dir: str) -> dict[int, dict]:
    """JSON ディレクトリから {frame_idx: {selected_bb_index, pink_ratio, bbox}} を返す。
    pink_id == 1 の人物が存在すれば値、なければ {selected_bb_index: None, pink_ratio: None, bbox: None}。
    """
```

#### 4.1.3 処理ロジック

```python
import re, json
PATTERN = re.compile(r"_(\d{6})\.json$")

def load_pink_id_results(json_dir: str) -> dict[int, dict]:
    result = {}
    for fname in os.listdir(json_dir):
        m = PATTERN.search(fname)
        if not m:
            continue
        frame_idx = int(m.group(1))
        with open(os.path.join(json_dir, fname)) as f:
            data = json.load(f)
        pink_person = next(
            (p for p in data.get("people", []) if p.get("pink_id") == 1),
            None,
        )
        if pink_person is None:
            result[frame_idx] = {"bb_index": None, "pink_ratio": None, "bbox": None}
        else:
            result[frame_idx] = {
                "bb_index": pink_person.get("bb_index"),
                "pink_ratio": pink_person.get("pink_ratio"),
                "bbox": pink_person.get("bbox"),
            }
    return result
```

#### 4.1.4 ディレクトリ存在チェック

main 冒頭で:
```python
for d in [args.bb_json_dir, args.kp_json_dir]:
    if not os.path.isdir(d):
        print(f"ERROR: JSON directory not found: {d}", file=sys.stderr)
        sys.exit(1)
```

#### 4.1.5 共通フレーム計算

```python
bb_results = load_pink_id_results(args.bb_json_dir)
kp_results = load_pink_id_results(args.kp_json_dir)
common_frames = sorted(set(bb_results) & set(kp_results))
only_bb_frames = set(bb_results) - set(kp_results)
only_kp_frames = set(kp_results) - set(bb_results)
if only_bb_frames or only_kp_frames:
    print(f"WARNING: bb-only frames={len(only_bb_frames)}, kp-only frames={len(only_kp_frames)}")
```

### 4.2 FR-002: α-1 散布図 PNG

#### 4.2.1 データ抽出

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

xs, ys = [], []
both_none_excluded = 0
for f in common_frames:
    bb_r = bb_results[f]["pink_ratio"]
    kp_r = kp_results[f]["pink_ratio"]
    # both_none（両モードとも pink_id=1 なし）は散布図から除外（FR-002 AC-002-4）
    if bb_r is None and kp_r is None:
        both_none_excluded += 1
        continue
    # 片方 None は 0.0 として軸端にプロット（only_bb / only_kp 群として観察可能）
    xs.append(bb_r if bb_r is not None else 0.0)
    ys.append(kp_r if kp_r is not None else 0.0)
```

#### 4.2.2 描画

```python
fig, ax = plt.subplots(figsize=(10, 10), dpi=80)
ax.scatter(xs, ys, s=4, alpha=0.3, color="navy")
ax.plot([0, 1], [0, 1], "k--", linewidth=1, label="y=x")
ax.set_xlim(0, 1.0)
ax.set_ylim(0, 1.0)
ax.set_xlabel("bb mode pink_ratio")
ax.set_ylabel("keypoint-rect mode pink_ratio")
ax.set_title(
    f"α-1 scatter: bb vs keypoint-rect "
    f"(plotted={len(xs)}, excluded both_none={both_none_excluded})"
)
ax.legend(loc="upper left")
ax.grid(True, alpha=0.3)
plt.savefig(os.path.join(args.out_dir, "alpha1_scatter.png"))
plt.close(fig)
```

### 4.3 FR-003: 不一致 CSV

#### 4.3.1 不一致タイプ判定ロジック

```python
def classify_disagreement(bb_idx, kp_idx) -> str | None:
    if bb_idx is None and kp_idx is None:
        return None  # both_none, CSV には含めない
    if bb_idx is None:
        return "only_kp"
    if kp_idx is None:
        return "only_bb"
    if bb_idx != kp_idx:
        return "both_selected_different"
    return None  # 同じ bb_index = 一致、CSV に含めない
```

#### 4.3.2 CSV 書き出し

```python
import csv
csv_path = os.path.join(args.out_dir, "disagreement.csv")
with open(csv_path, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "frame_idx", "disagreement_type",
        "bb_selected_bb_index", "bb_pink_ratio", "bb_bbox",
        "kp_selected_bb_index", "kp_pink_ratio", "kp_bbox",
    ])
    for fr_idx in common_frames:
        bb = bb_results[fr_idx]
        kp = kp_results[fr_idx]
        dtype = classify_disagreement(bb["bb_index"], kp["bb_index"])
        if dtype is None:
            continue
        # bbox 要素を小数 2 桁に丸めて CSV 可読性と再パース安定性を高める
        def _bbox_str(bbox):
            if bbox is None:
                return ""
            return "[" + ", ".join(f"{round(v, 2)}" for v in bbox) + "]"
        writer.writerow([
            fr_idx, dtype,
            bb["bb_index"] if bb["bb_index"] is not None else "",
            f"{bb['pink_ratio']:.4f}" if bb["pink_ratio"] is not None else "",
            _bbox_str(bb["bbox"]),
            kp["bb_index"] if kp["bb_index"] is not None else "",
            f"{kp['pink_ratio']:.4f}" if kp["pink_ratio"] is not None else "",
            _bbox_str(kp["bbox"]),
        ])
```

### 4.4 FR-004: compare サマリ標準出力

```python
counts = {"both_selected_different": 0, "only_bb": 0, "only_kp": 0, "both_none": 0}
for fr_idx in common_frames:
    bb_idx = bb_results[fr_idx]["bb_index"]
    kp_idx = kp_results[fr_idx]["bb_index"]
    if bb_idx is None and kp_idx is None:
        counts["both_none"] += 1
    elif bb_idx is None:
        counts["only_kp"] += 1
    elif kp_idx is None:
        counts["only_bb"] += 1
    elif bb_idx != kp_idx:
        counts["both_selected_different"] += 1
print(f"Total frames processed: {len(common_frames)}")
print(f"Disagreement counts: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
print(f"Output: {args.out_dir}/alpha1_scatter.png")
print(f"Output: {args.out_dir}/disagreement.csv")
```

### visualize_disagreement_frames.py

### 4.5 FR-005: 不一致フレーム PNG 出力

#### 4.5.0 argparse 引数バリデータ

```python
def _positive_int(s: str) -> int:
    v = int(s)
    if v < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {v}")
    return v

parser.add_argument("--max-samples", type=_positive_int, default=50)
```

`type=_positive_int` で 0 / 負値を argparse 側で弾く（exit code 2、AC-005-6）。

#### 4.5.1 CSV 読み込みとサンプリング

```python
import csv, ast
rows = []
with open(args.csv) as f:
    reader = csv.DictReader(f)
    for r in reader:
        rows.append(r)

original_row_count = len(rows)
if not args.all and len(rows) > args.max_samples:
    step = len(rows) / args.max_samples
    # 注: int(i * step) で末尾の `len(rows) - 1` インデックスに届かない場合がある
    # (例: len(rows)=1000, max_samples=50 → step=20.0、最終 index=int(49*20.0)=980)
    # 仕様としては均等サンプリングを優先し、末尾フレームの取りこぼしは許容する
    indices = [int(i * step) for i in range(args.max_samples)]
    rows = [rows[i] for i in indices]
```

#### 4.5.2 動画読み込みとフレーム描画

```python
cap = cv2.VideoCapture(args.video)
if not cap.isOpened():
    print(f"ERROR: failed to open video: {args.video}", file=sys.stderr)
    sys.exit(1)

success_count = 0
seek_fail_count = 0

for r in rows:
    fr_idx = int(r["frame_idx"])
    cap.set(cv2.CAP_PROP_POS_FRAMES, fr_idx)
    ret, frame = cap.read()
    if not ret:
        seek_fail_count += 1
        print(f"WARNING: failed to seek frame {fr_idx}", file=sys.stderr)
        continue
    
    # CSV 文字列 → list パース。異常な文字列の場合は WARNING を出して当該 bbox を None 扱いに
    def _parse_bbox(s: str, label: str):
        if not s:
            return None
        try:
            v = ast.literal_eval(s)
            if not isinstance(v, list) or len(v) != 4:
                raise ValueError(f"expected list of 4, got {v!r}")
            return v
        except (ValueError, SyntaxError) as e:
            print(f"WARNING: failed to parse {label} bbox at frame {fr_idx}: {e}", file=sys.stderr)
            return None
    bb_bbox = _parse_bbox(r["bb_bbox"], "bb")
    kp_bbox = _parse_bbox(r["kp_bbox"], "kp")
    # 既存 JSON の bbox は float の list。cv2.rectangle は int 必須なので変換
    bb_bbox_i = tuple(int(round(v)) for v in bb_bbox) if bb_bbox is not None else None
    kp_bbox_i = tuple(int(round(v)) for v in kp_bbox) if kp_bbox is not None else None
    
    # disagreement_type ベースの描画分岐（AC-005-4 への対応）:
    #   - both_selected_different: 赤(bb) + 青(kp) 両方
    #   - only_bb: 赤のみ
    #   - only_kp: 青のみ
    # CSV 生成側（§4.3.2）が only_bb 時は kp_bbox を空欄、only_kp 時は bb_bbox を空欄に
    # 書き出すため、結果として「bbox があれば描画」のロジックで AC を満たす。
    # 念のため disagreement_type で明示分岐し、CSV の不整合（手編集等）にも頑健にする。
    dtype = r["disagreement_type"]
    if dtype in ("both_selected_different", "only_bb") and bb_bbox_i is not None:
        cv2.rectangle(frame, (bb_bbox_i[0], bb_bbox_i[1]), (bb_bbox_i[2], bb_bbox_i[3]),
                      (0, 0, 255), 2)  # 赤 = bb モード
    if dtype in ("both_selected_different", "only_kp") and kp_bbox_i is not None:
        cv2.rectangle(frame, (kp_bbox_i[0], kp_bbox_i[1]), (kp_bbox_i[2], kp_bbox_i[3]),
                      (255, 0, 0), 2)  # 青 = keypoint-rect モード
    
    # テキストオーバーレイ（黒縁取り + 白文字で背景非依存の可読性確保）
    lines = [
        f"Frame: {fr_idx:06d} | Type: {r['disagreement_type']}",
    ]
    if r["bb_selected_bb_index"]:
        lines.append(f"BB: idx={r['bb_selected_bb_index']} ratio={r['bb_pink_ratio']}")
    if r["kp_selected_bb_index"]:
        lines.append(f"KP: idx={r['kp_selected_bb_index']} ratio={r['kp_pink_ratio']}")
    
    for i, line in enumerate(lines):
        org = (10, 25 + 25 * i)
        # 黒縁取り（厚さ 3）
        cv2.putText(frame, line, org, cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 0, 0), 3)
        # 白本体（厚さ 1）
        cv2.putText(frame, line, org, cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (255, 255, 255), 1)
    
    out_path = os.path.join(args.out_dir, f"frame_{fr_idx:06d}_disagree.png")
    cv2.imwrite(out_path, frame)
    success_count += 1

cap.release()
```

### 4.6 FR-006: シーク失敗フォールバック

§4.5.2 のループ内で `cap.read()` が False の場合に処理を実装。

設計判断: シーク失敗フレームを 1 件ずつスキップし、警告を出力。残りのフレーム処理は継続。全フレーム失敗時もクラッシュせず exit code 0。

### 4.7 FR-007: visualize サマリ標準出力

```python
print(f"Total disagreement frames in CSV: {original_row_count}")
print(f"Samples to process: {len(rows)}")
print(f"PNGs successfully saved: {success_count}")
print(f"Seek failures: {seek_fail_count}")
print(f"Output: {args.out_dir}/")
```

## 5. ファイル・ディレクトリ設計

### 5.1 入出力パス

| ファイル | 入出力 | 例 |
|---|---|---|
| `--bb-json-dir` | 入力 | `experiments/results/camSony1_L_pink_json_bb` |
| `--kp-json-dir` | 入力 | `experiments/results/camSony1_L_pink_json_kp` |
| `--out-dir` (compare) | 出力 | `experiments/results/camSony1_L_roi_compare` |
| `alpha1_scatter.png` | 出力 | `experiments/results/camSony1_L_roi_compare/alpha1_scatter.png` |
| `disagreement.csv` | 出力 | `experiments/results/camSony1_L_roi_compare/disagreement.csv` |
| `--video` (visualize) | 入力 | `experiments/input/camSony1_L.mp4` |
| `--csv` (visualize) | 入力 | `experiments/results/camSony1_L_roi_compare/disagreement.csv` |
| `--out-dir` (visualize) | 出力 | `experiments/results/camSony1_L_roi_compare/disagreement_frames` |

### 5.2 推奨実行コマンド（手動テスト用）

```bash
# Step 1: compare
mkdir -p experiments/results/camSony1_S_roi_compare
uv run python scripts/compare_roi_modes.py \
  --bb-json-dir experiments/results/camSony1_S_pink_json_bb \
  --kp-json-dir experiments/results/camSony1_S_pink_json_kp \
  --out-dir experiments/results/camSony1_S_roi_compare

# Step 2: visualize disagreement
mkdir -p experiments/results/camSony1_S_roi_compare/disagreement_frames
uv run python scripts/visualize_disagreement_frames.py \
  --video testdata/camSony1_S.mp4 \
  --csv experiments/results/camSony1_S_roi_compare/disagreement.csv \
  --out-dir experiments/results/camSony1_S_roi_compare/disagreement_frames \
  --max-samples 50
```

## 6. パフォーマンス影響

### compare_roi_modes.py
- JSON 読み込み: 321K フレーム × json.load ≒ 数十秒（IO bound）
- 散布図描画: 数秒
- CSV 書き出し: 数秒
- 合計 NFR-001 の 2 分以内に十分収まる見込み

### visualize_disagreement_frames.py
- 50 件シーク + 描画 + 保存: 1 件あたり 0.1-0.3 秒（mp4v シーク時間が支配的）
- 合計 30 秒以内に収まる見込み（NFR-001）

## 7. インターフェース定義

### 7.1 compare_roi_modes.py CLI

| 引数 | 型 | デフォルト | 説明 |
|------|------|----------|------|
| `--bb-json-dir` | str | 必須 | bb モード JSON ディレクトリ |
| `--kp-json-dir` | str | 必須 | keypoint-rect モード JSON ディレクトリ |
| `--out-dir` | str | 必須 | 出力ディレクトリ |

### 7.2 visualize_disagreement_frames.py CLI

| 引数 | 型 | デフォルト | 説明 |
|------|------|----------|------|
| `--video` | str | 必須 | 元動画ファイル |
| `--csv` | str | 必須 | disagreement.csv パス |
| `--out-dir` | str | 必須 | PNG 出力先 |
| `--max-samples` | int | 50 | サンプル数上限。値域 `>= 1`。0/負値は argparse でエラー（exit code 2、AC-005-6） |
| `--all` | flag | False | 全件出力（max-samples 無視） |

### 7.3 公開関数（compare_roi_modes.py）

| 関数 | シグネチャ |
|------|-----------|
| `load_pink_id_results` | `(json_dir: str) -> dict[int, dict]` |
| `classify_disagreement` | `(bb_idx, kp_idx) -> str \| None` |
| `main` | `() -> None` |

### 7.4 公開関数（visualize_disagreement_frames.py）

| 関数 | シグネチャ |
|------|-----------|
| `main` | `() -> None` |

（処理ロジックが単純なため、サブ関数は不要。可読性のため必要に応じて分解可）

## 8. ログ・デバッグ設計

### 8.1 既存ログ準拠

進捗表示は `compare_roi_modes.py` は出さない（処理時間短いため）。`visualize_disagreement_frames.py` は 10 件ごとに `Processing frame {N}/{total}` を表示。

### 8.2 エラーログ

- ディレクトリ不在 / ファイル不在: 標準エラーに `ERROR: ...`、exit code 1
- シーク失敗: 標準エラーに `WARNING: failed to seek frame {N}`、継続

## 9. 設計判断の記録（全体 ADR サマリ）

- **V-2 採用**（静止画 PNG、フレームごと 1 ファイル）: 数千件の不一致でも閲覧可能。動画より個別フレームの精査がしやすい
- **均等サンプリング**: 不一致時刻が偏らないよう均等間隔で抽出。デフォルト 50 件で目視負荷を抑制
- **BB 描画色**: bb モード = 赤、keypoint-rect モード = 青。OpenCV BGR で `(0,0,255), (255,0,0)`。FR-003 の不一致分類で「同一 bb_index は CSV から除外」されるため、visualize 入力には「同一 BB を選んだフレーム」は含まれず、紫描画は不要
- **float bbox の int 変換**: `cv2.rectangle` は int を要求するが既存 JSON の `bbox` は float の list。描画前に `tuple(int(round(v)) for v in bbox)` で int 変換する
- **テキストオーバーレイの可読性**: 黒縁取り（厚さ 3）の上に白文字（厚さ 1）を 2 回 putText で重ね、明暗どちらの背景でも値が読み取れるようにする
- **CSV bbox 文字列の小数桁数**: 既存 JSON の bbox は float（例: 509.0524597167969）だが、CSV に full precision で書き出すと可読性が低い。`round(v, 2)` で 2 桁に丸めて書き出す。再パース時は `ast.literal_eval` で問題なくリスト化できる
- **CSV パース失敗時の挙動**: visualize 側で `ast.literal_eval` が例外を投げた場合（CSV が他ツールで編集されて壊れている等の異常ケース）は当該 bbox を None 扱いとし、`WARNING: failed to parse ... bbox at frame N` を標準エラーに出力して継続。クラッシュさせない
- **CSV 形式**: 8 列。`bb_bbox` / `kp_bbox` は Python の list 文字列表現（`[x1,y1,x2,y2]`）。`ast.literal_eval` でパース可能
- **2 スクリプト分割**: compare（数値比較）と visualize（描画）を分離。compare の出力を visualize の入力として連鎖
- **`--all` フラグ**: 最終的に全件確認したいユーザーニーズ（論点 10）に対応。デフォルト 50 件でクイック確認、`--all` で本番確認
- **OpenCV シーク精度の許容**: `cap.set(CAP_PROP_POS_FRAMES, N)` は H.264 等のロングGOP 動画でキーフレーム単位に丸められ、`cap.read()` が要求と異なるフレームを返すケースがある。本案件では検証対象動画（camSony1_S / camSony1_L、CFR mp4）でこの問題が実害として観測されなければ許容。完全な精度が必要になった場合は、開始から逐次 read してターゲットフレームまで進める方式（コスト大）への切替を別案件で検討する。出力 PNG ファイル名と画像内容が乖離する可能性は本仕様の前提として認知する
- **散布図から both_none を除外**（FR-002 AC-002-4）: 両モードとも pink_id=1 なしのフレームは (0,0) 点として原点に大量集積し散布図の情報量を下げるため除外。タイトルに除外件数を明記。only_bb / only_kp は片方軸 0 で残し、観察対象として可視化
- **PNG 描画は disagreement_type ベースで明示分岐**: CSV 生成側で「描画すべき bbox 列が空欄」になるため bbox 有無分岐でも結果は同じだが、手編集 CSV の不整合に頑健にするため `disagreement_type` を読んで色ごとに描画可否を判定する（AC-005-4 への対応）

## 10. 実装完了後のチェックリスト

### compare_roi_modes.py
- [ ] スクリプト新規作成
- [ ] camSony1_S の 2 モード JSON で実行、散布図と CSV が出力されることを確認
- [ ] camSony1_L で実行、NFR-001 の 2 分以内を確認

### visualize_disagreement_frames.py
- [ ] スクリプト新規作成
- [ ] camSony1_S の disagreement.csv で実行、PNG が `max-samples` 数だけ出力されることを確認
- [ ] camSony1_L で `--all` 実行、不一致全件 PNG 出力を確認
- [ ] 各 PNG にテキストオーバーレイと BB が描画されていることを目視確認

### 共通
- [ ] `scripts/README.md` に両スクリプトのセクション追加
- [ ] CLAUDE.md の feat-047 エントリを完了済み案件として追記
- [ ] CLAUDE.md ディレクトリ構成に両スクリプト追記
- [ ] `docs/BACKLOG.md` の feat-047 を Closed に変更
- [ ] `docs/issues/feat-047-roi-mode-comparison/README.md` のステータスを Closed に更新
