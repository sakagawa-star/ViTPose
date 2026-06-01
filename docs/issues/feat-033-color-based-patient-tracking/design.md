# feat-033: 服装の色による対象同定（ポストプロセス） — 機能設計書

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001（HSVピンクマスク / ピンク比率計算） | §4.1 |
| FR-002（選択BBロジック） | §4.2 |
| FR-003（ポストプロセス本体） | §4.3 |
| FR-004（CLI インタフェース） | §4.4 |
| FR-005（サマリ出力） | §4.5 |
| NFR-001（パフォーマンス） | §7.1 |
| NFR-003（信頼性） | §4.3.4 / §8 |

## 2. システム構成

### 2.1 モジュール構成

本案件で作成するのは1つの独立スクリプト `scripts/postprocess_pink_id.py` のみ。他スクリプトからの import は想定しない（将来必要なら別案件で分離する）。

```
scripts/postprocess_pink_id.py
├─ 定数
│   ├─ FIXED_HSV_RANGES
│   ├─ MIN_PINK_RATIO = 0.03
│   └─ IOU_CONT_WEIGHT = 0.05
├─ 純関数
│   ├─ compute_pink_ratio(roi_bgr) → float          (FR-001)
│   ├─ compute_iou(bbox_a, bbox_b) → float
│   └─ select_pink_bbox(bboxes, ratios, prev) → int|None  (FR-002)
├─ I/O 関数
│   ├─ load_json_frames(json_dir) → dict[int, dict]  (JSONディレクトリ全読み込み、生dict保持)
│   └─ write_json_frame(out_path, data) → None
└─ エントリポイント
    └─ main() → None                                 (FR-003, FR-004, FR-005)
```

### 2.2 既存ファイルとの関係

- 参考元: `scripts/postprocess_reid.py`（命名・CLI・フレームループ構造を流用。ただしトラッカー・Re-ID 関連は不要なので取り除く）
- 変更禁止: §5.4（要求仕様書）の通り、既存ファイルは一切変更しない

### 2.3 ディレクトリ構成

```
scripts/
├── postprocess_reid.py              # 既存（変更しない）
└── postprocess_pink_id.py           # 新規（本案件）

experiments/results/
├── camSony1_S_json/                 # 入力（既存、変更しない）
└── camSony1_S_pink_json/            # 出力（本案件で生成）
```

出力ディレクトリ名の規約: `{入力ディレクトリ名}_pink`（例: `camSony1_S_json` → `camSony1_S_pink_json`）。ただしCLI引数で任意に指定可能であり、規約はREADMEやコミュニケーションでの推奨値にとどめ、スクリプト内では強制しない。

## 3. 技術スタック

| 項目 | 値 | 選定理由 |
|------|-----|----------|
| 言語 | Python 3.10.16 | プロジェクト既定 |
| パッケージ管理 | uv | プロジェクト既定。`uv run python scripts/postprocess_pink_id.py` で実行 |
| OpenCV | 既存 uv 環境の opencv-python | 動画読み込み、BGR→HSV変換、`cv2.inRange` によるマスク生成、`cv2.bitwise_or` によるマスク統合 |
| numpy | 既存 uv 環境の numpy | 配列演算・HSVレンジ定数の np.array 化 |

追加ライブラリの導入は行わない。`custom_reid`、`boxmot`、`pandas`、`matplotlib` は import しない。

## 4. 各機能の詳細設計

### 4.1 FR-001: HSVピンクマスク / ピンク比率計算

#### 4.1.1 データフロー

- 入力: `roi_bgr: np.ndarray`（shape = (h, w, 3), dtype = uint8, BGR色空間）
- 中間: HSV画像 `np.ndarray`（shape = (h, w, 3), dtype = uint8, OpenCV HSV規格で H:0-179, S:0-255, V:0-255）
- 中間: 各HSVレンジマスク `np.ndarray`（shape = (h, w), dtype = uint8, 値 0 または 255）
- 中間: 統合マスク `np.ndarray`（shape = (h, w), dtype = uint8, 値 0 または 255）
- 出力: `float`（値域 [0.0, 1.0]）

#### 4.1.2 処理ロジック

```python
def compute_pink_ratio(roi_bgr: np.ndarray) -> float:
    """要求: FR-001"""
    if roi_bgr.size == 0 or roi_bgr.shape[0] == 0 or roi_bgr.shape[1] == 0:
        return 0.0
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    mask_total = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lo, hi in FIXED_HSV_RANGES:
        lo_np = np.array(lo, dtype=np.uint8)
        hi_np = np.array(hi, dtype=np.uint8)
        mask = cv2.inRange(hsv, lo_np, hi_np)
        mask_total = cv2.bitwise_or(mask_total, mask)
    pink_pixels = int(np.count_nonzero(mask_total))
    total_pixels = roi_bgr.shape[0] * roi_bgr.shape[1]
    return pink_pixels / total_pixels if total_pixels > 0 else 0.0
```

※このコードスニペットは意図伝達用であり、そのまま動作させることも可能だが、実装時にdocstring・型整形を整えること。

#### 4.1.3 境界条件

- ROI が `shape = (0, w, 3)` や `(h, 0, 3)` の場合: 0.0 を返す
- ROI 全域がピンクレンジに完全に含まれる場合: 1.0 を返す
- ROI 全域がピンクレンジ外の場合: 0.0 を返す

#### 4.1.4 エラーハンドリング

- 本関数ではエラーを発生させない。呼び出し側でBBが画像範囲を超えていた場合は呼び出し側でクリッピングしてから渡す責務とする（§4.3.3 参照）

### 4.2 FR-002: 選択BBロジック

#### 4.2.1 データフロー

- 入力:
  - `bboxes: list[tuple[int, int, int, int]]`（ピクセル座標 xyxy）
  - `ratios: list[float]`（各BBのピンク比率）
  - `prev_selected_bbox: tuple[int, int, int, int] | None`
- 出力: `int | None`（選択BBのインデックス、または選択なし）

#### 4.2.2 処理ロジック

```python
def compute_iou(a: tuple, b: tuple) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    ua = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    ub = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = ua + ub - inter
    return inter / union if union > 0 else 0.0


def select_pink_bbox(
    bboxes: list[tuple[int, int, int, int]],
    ratios: list[float],
    prev_selected_bbox: tuple[int, int, int, int] | None,
) -> int | None:
    """要求: FR-002"""
    if not bboxes:
        return None
    candidates = [i for i, r in enumerate(ratios) if r >= MIN_PINK_RATIO]
    if not candidates:
        return None
    if prev_selected_bbox is None:
        # max by ratio, ties broken by smallest index
        best_i = candidates[0]
        best_r = ratios[best_i]
        for i in candidates[1:]:
            if ratios[i] > best_r:
                best_i = i
                best_r = ratios[i]
        return best_i
    # with continuity bonus
    best_i = candidates[0]
    best_score = ratios[best_i] + IOU_CONT_WEIGHT * compute_iou(
        prev_selected_bbox, bboxes[best_i]
    )
    for i in candidates[1:]:
        score = ratios[i] + IOU_CONT_WEIGHT * compute_iou(
            prev_selected_bbox, bboxes[i]
        )
        if score > best_score:
            best_i = i
            best_score = score
    return best_i
```

同値時の挙動: 最初に見つけたインデックス（= より小さいインデックス）を優先する。これは `pink_tracker_jhub.py` の `max(..., key=lambda t: t[1])` の暗黙挙動と一致する。

#### 4.2.3 境界条件

- `bboxes` が空: None を返す
- `candidates` が空（全員 ratio < 閾値）: None を返す
- 候補が1個: そのインデックスを返す（`prev_selected_bbox` に関係なく）
- 候補スコアが同値: インデックス小側を返す

### 4.3 FR-003: ポストプロセス本体

#### 4.3.1 データフロー

- 入力:
  - `args.video`: str（動画ファイルパス）
  - `args.json_dir`: str（入力JSONディレクトリ）
  - `args.out_dir`: str（出力JSONディレクトリ）
- 中間:
  - `frame_to_json: dict[int, dict]`（key = フレーム番号、value = 元JSONの生dict）
  - `frame_bgr: np.ndarray`（shape = (H, W, 3), dtype = uint8）
  - `prev_selected_bbox: tuple | None`
- 出力:
  - 出力ディレクトリに `{video_stem}_{frame_idx:06d}.json` を書き出す

#### 4.3.2 JSON読み込み方針

`postprocess_reid.py` の `load_data()` はキーポイント抽出に特化しており（78要素のflat配列を np.ndarray に変換）、本案件では不要。代わりに「JSONの元dictをそのまま保持し、`pink_id` のみを追加する」方針とする。具体的には以下のように実装する:

```python
def load_json_frames(json_dir: str) -> dict[int, tuple[str, dict]]:
    """
    JSONディレクトリを全読み込み。
    Returns: {frame_idx: (original_filename, content_dict)}
    """
    json_path = Path(json_dir)
    json_files = sorted(json_path.glob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"No JSON files in {json_dir}")
    pattern = re.compile(r"_(\d{6})\.json$")
    out: dict[int, tuple[str, dict]] = {}
    for jf in json_files:
        m = pattern.search(jf.name)
        if m is None:
            continue
        fidx = int(m.group(1))
        try:
            with open(jf) as f:
                content = json.load(f)
        except json.JSONDecodeError:
            print(f"WARNING: Failed to parse {jf.name}, treating as empty")
            content = {"version": 1.3, "people": []}
        out[fidx] = (jf.name, content)
    return out
```

この方式により、入力JSONに `stable_id` やその他の将来フィールドがあっても自動的に保持される。

#### 4.3.3 BBクリッピングとROI切り出し

動画フレーム画像 `frame_bgr` と人物BB `(bx1, by1, bx2, by2)` から ROI を切り出す際、BBが画像範囲外（bx1 < 0 や bx2 > W 等）の場合に備えて以下のようにクリッピングする:

```python
def clip_bbox(bbox: tuple[float, float, float, float], W: int, H: int) -> tuple[int, int, int, int]:
    bx1, by1, bx2, by2 = bbox
    x1 = max(0, min(W - 1, int(round(bx1))))
    y1 = max(0, min(H - 1, int(round(by1))))
    x2 = max(0, min(W - 1, int(round(bx2))))
    y2 = max(0, min(H - 1, int(round(by2))))
    return (x1, y1, x2, y2)

clipped = clip_bbox((bx1, by1, bx2, by2), W, H)
cx1, cy1, cx2, cy2 = clipped
if cx2 <= cx1 or cy2 <= cy1:
    roi = np.zeros((0, 0, 3), dtype=np.uint8)  # 空ROI扱い
else:
    roi = frame_bgr[cy1:cy2, cx1:cx2]
```

**BBリスト・`prev_selected_bbox` に格納するBBはすべてクリッピング後の整数タプル**を使用する。IoU 計算も `prev_selected_bbox`（クリッピング済み）と `bboxes[i]`（クリッピング済み）で行う。これは参考元 `pink_tracker_jhub.py` L114-117（`int(max(0, ...))`, `int(min(W-1, ...))`）の挙動と一致する。

**出力JSONの `bbox` フィールドはクリッピング前の元値をそのまま保持する**（既存フィールドを変更しない原則）。クリッピングは ROI 切り出しと連続性計算のための内部表現にのみ使用する。

#### 4.3.4 メインループ擬似コード

```
load frame_to_json from args.json_dir
open video with cv2.VideoCapture(args.video)
video_stem := basename(args.video) without extension
prev_selected_bbox := None
frame_idx := 0
summary := {total: 0, selected: 0, no_candidate: 0, json_missing: 0, breaks: 0}
start_time := time.time()

loop:
    ret, frame_bgr := cap.read()
    if not ret: break

    summary.total += 1
    H, W := frame_bgr.shape[:2]
    entry := frame_to_json.get(frame_idx)  # (filename, content) or None

    if entry is None:
        # JSONなしフレーム → 連続性切れ扱い
        summary.json_missing += 1
        if prev_selected_bbox is not None:
            summary.breaks += 1
        prev_selected_bbox := None
        # 何も出力しない（入力JSONがないフレームは出力ディレクトリにも作らない）
        frame_idx += 1
        continue

    filename, content := entry
    people := content.get("people", [])

    # BB と ratio 計算（欠損人物も含めて順序を維持する。
    # 欠損人物には None を詰め、選択段階で候補から必ず外す）
    bboxes := []          # list[tuple[int,int,int,int] | None]
    ratios := []          # list[float]   (欠損人物は 0.0)
    for person in people:
        bb := person.get("bbox")
        if bb is None or len(bb) != 4:
            bboxes.append(None)
            ratios.append(0.0)
            continue
        clipped := clip_bbox(bb, W, H)
        cx1, cy1, cx2, cy2 := clipped
        if cx2 <= cx1 or cy2 <= cy1:
            roi := np.zeros((0, 0, 3), dtype=np.uint8)
        else:
            roi := frame_bgr[cy1:cy2, cx1:cx2]
        bboxes.append(clipped)
        ratios.append(compute_pink_ratio(roi))

    # 選択。select_pink_bbox 内では bboxes[i] is None のインデックスは
    # 最初から candidates から除外する（ratio=0.0 なので閾値未満のため自動的に落ちる）
    sel_idx := select_pink_bbox(bboxes, ratios, prev_selected_bbox)

    # pink_id 付与
    for i, person in enumerate(people):
        person["pink_id"] := 1 if i == sel_idx else -1

    # JSON 書き出し（write_json_frame 関数経由）
    out_path := os.path.join(args.out_dir, filename)
    write_json_frame(out_path, content)

    # 統計・前フレーム状態更新
    if sel_idx is not None:
        summary.selected += 1
        prev_selected_bbox := bboxes[sel_idx]  # クリッピング済み整数タプル
    else:
        summary.no_candidate += 1  # people 空 / 候補ゼロ / 欠損のみ をすべて含む
        if prev_selected_bbox is not None:
            summary.breaks += 1
        prev_selected_bbox := None

    frame_idx += 1

cap.release()
elapsed := time.time() - start_time
print_summary(summary, elapsed)
```

**重要**: AC-003-2 では「出力ディレクトリに入力と同数のJSONファイルが生成される」と定めたが、動画に対応するフレームが存在しない（JSONだけ存在する）ケースも理論上ありうる。本設計では「JSONはあるが動画フレームが途中で終了した」場合は出力されないJSONも発生する。本案件はポストプロセスであり、動画とJSONの整合性は前段（`run_halpe26_pipeline_yolo11.py`）で保証されている前提なので、この非対称は許容する。

**境界条件の整理**（`no_candidate` は「有効なBB候補ゼロ」のすべてのケースを包含）:
- 動画にフレームがあるが対応JSONがない → 出力なし、`prev_selected_bbox` リセット（`summary.json_missing++`, 必要に応じ `summary.breaks++`）
- JSONはあるが `people` が空 → 空の `people` を出力、`prev_selected_bbox` リセット（`summary.no_candidate++`, 必要に応じ `summary.breaks++`）
- JSONはあるが全員 `bbox` 欠損/不正（`bboxes[i]` がすべて None、`ratios[i]` がすべて 0.0） → 全員 `pink_id = -1` のJSONを出力、`prev_selected_bbox` リセット（`summary.no_candidate++`, 必要に応じ `summary.breaks++`）
- JSONと `people` は正常だが全員ピンク比率 `MIN_PINK_RATIO` 未満 → 全員 `pink_id = -1` のJSONを出力、`prev_selected_bbox` リセット（`summary.no_candidate++`, 必要に応じ `summary.breaks++`）
- 動画よりJSONが多い → 余剰JSONは無視（動画終了でループ終了）

**サマリ等式の確認**: `summary.selected + summary.no_candidate + summary.json_missing == summary.total` が常に成り立つ（requirements.md AC-005-2）。上記擬似コードの各分岐はこの3カテゴリのいずれか1つのみを加算するため等式は破綻しない。

#### 4.3.5 エラーハンドリング

| 想定エラー | 検出方法 | 処理 | ログ |
|-----------|----------|------|------|
| 入力動画が開けない | `cap.isOpened() == False` | ERROR 出力 → exit(1) | `ERROR: Cannot open video {path}` |
| 入力JSONディレクトリにファイルなし | `load_json_frames` で FileNotFoundError | ERROR 出力 → exit(1) | `ERROR: No JSON files in {dir}` |
| 出力ディレクトリが入力と同一 | `os.path.realpath(in) == os.path.realpath(out)` | ERROR 出力 → exit(1) | `ERROR: --out-dir must differ from --json-dir` |
| 個別JSONファイルの parse 失敗 | `json.JSONDecodeError` | WARNING 出力、空 `people` として処理継続 | `WARNING: Failed to parse {name}, treating as empty` |
| 個別人物の `bbox` フィールド欠損 | `person.get("bbox") is None or len != 4` | ratio = 0.0 で候補から除外、その人物には `pink_id = -1` を付与 | `WARNING: Missing/invalid bbox in frame {idx} person {i}` |
| 途中フレームで動画読み込み失敗 | `cap.read()` が `ret == False` | ループを break（処理済みJSONはそのまま保持） | `WARNING: Frame read failed at {idx}, stopping` |

### 4.4 FR-004: CLI インタフェース

```python
parser = argparse.ArgumentParser(
    description="Add pink_id (color-based patient ID) to HALPE 26 JSON files"
)
parser.add_argument("--video", required=True, help="Input video file path")
parser.add_argument("--json-dir", required=True, help="Input HALPE 26 JSON directory")
parser.add_argument("--out-dir", required=True,
                    help="Output JSON directory (must differ from --json-dir)")
args = parser.parse_args()
```

- 同一パスチェックは `postprocess_reid.py` line 238-240 と同じロジックを流用
- `os.makedirs(args.out_dir, exist_ok=True)` で出力ディレクトリを事前作成

#### フェーズ1実行コマンド（設計書記載用、手動テスト時に実行）

```
uv run python scripts/postprocess_pink_id.py \
  --video testdata/camSony1_S.mp4 \
  --json-dir experiments/results/camSony1_S_json \
  --out-dir experiments/results/camSony1_S_pink_json
```

### 4.5 FR-005: サマリ出力

メインループ終了後に以下を `print()` で標準出力に書き出す（ラベルは `postprocess_reid.py` と揃え、`Total frames:` を用いる）:

```
Total frames: {summary.total}
Frames with pink_id=1: {summary.selected}
Frames without candidate (no valid bbox candidate above threshold): {summary.no_candidate}
Frames without json: {summary.json_missing}
Continuity breaks: {summary.breaks}
Processing time: {elapsed:.1f} sec ({fps:.1f} fps)
Output directory: {args.out_dir}
```

- `fps = summary.total / elapsed if elapsed > 0 else 0.0`
- `no_candidate` は「JSONは存在するが、有効なBB候補がゼロ（`people` 空 / 全員 bbox 欠損 / 全員ピンク比率 `MIN_PINK_RATIO` 未満）」のケースすべてを含む
- `json_missing` は「動画フレームに対応するJSONファイルが存在しない」ケース
- サマリ検証（AC-005-2）: `summary.selected + summary.no_candidate + summary.json_missing == summary.total` が常に成り立つ

## 5. 状態遷移

本スクリプトには `prev_selected_bbox` による内部状態があり、以下の2状態を遷移する:

| 状態 | 説明 |
|------|------|
| `HAS_PREV` | `prev_selected_bbox is not None`。前フレームで選択BBが存在する |
| `NO_PREV` | `prev_selected_bbox is None`。前フレームで選択なし（初期状態 or 連続性切れ後） |

| 現在状態 | イベント | 次状態 | 備考 |
|----------|---------|--------|------|
| NO_PREV | JSONなし | NO_PREV | summary.json_missing++ |
| NO_PREV | 有効BB候補ゼロ（people 空 / 全員 bbox 欠損 / 全員 ratio<閾値） | NO_PREV | summary.no_candidate++ |
| NO_PREV | 候補あり → 選択 | HAS_PREV | summary.selected++ |
| HAS_PREV | JSONなし | NO_PREV | summary.json_missing++, summary.breaks++ |
| HAS_PREV | 有効BB候補ゼロ（people 空 / 全員 bbox 欠損 / 全員 ratio<閾値） | NO_PREV | summary.no_candidate++, summary.breaks++ |
| HAS_PREV | 候補あり → 選択 | HAS_PREV | summary.selected++ |

初期状態は NO_PREV（`prev_selected_bbox = None`）。

## 6. ファイル・ディレクトリ設計

### 6.1 入力ファイル規約

- 動画: 任意のパス（`testdata/`, `experiments/input/` 等）、`.mp4` 形式
- 入力JSON: `{任意のディレクトリ}/{video_stem}_{frame_idx:06d}.json`
  - 例: `experiments/results/camSony1_S_json/camSony1_S_000000.json`
  - `video_stem` は動画ファイル名（拡張子除く）
  - `frame_idx` は 6 桁ゼロ埋め

### 6.2 出力ファイル規約

- 出力ディレクトリ: CLI引数 `--out-dir` で指定される任意パス
- ファイル名: 入力JSONと完全に同一（`{video_stem}_{frame_idx:06d}.json`）
- 中身: 入力JSONに各 `people[*]` へ `pink_id: int` を追加したもの。その他のフィールドは元通り

### 6.3 出力JSONスキーマ差分

```json
{
  "version": 1.3,
  "people": [
    {
      "person_id": [-1],
      "pose_keypoints_2d": [...],
      "bbox": [x1, y1, x2, y2],
      "bbox_score": 0.95,
      "stable_id": 3,    // 入力に存在する場合のみ、変更なし
      "pink_id": 1       // 新規追加（1 or -1）
    }
  ]
}
```

## 7. 非機能

### 7.1 パフォーマンス見積もり

- camSony1_S: 445フレーム × 平均 2〜5 BB/フレーム ≈ 1000〜2000 ROI 処理。各 ROI は数百〜数千画素。`cv2.cvtColor` + 3回 `cv2.inRange` + `cv2.bitwise_or` の合計コストは 1 ROI あたり数百μs オーダーのはず。動画デコード込みで数秒〜数十秒で完了する見込み。NFR-001 の 60 秒以内を満たす
- camSony1_L: 321K フレーム。S の約 720 倍。数十分〜数時間オーダーで完了する見込み

## 8. ログ・デバッグ設計

- ログ手段: `print()`（`postprocess_reid.py` に合わせる。logging モジュールは導入しない）
- ログレベル表記: `ERROR:` / `WARNING:` / (INFO は prefix なしで print)
- 進捗表示:
  - 入力動画の総フレーム数 `total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))` を取得
  - `progress_interval = max(1, total_frames // 10)` とし、`frame_idx % progress_interval == 0` のときに `Processing frame {frame_idx:06d}/{total_frames} ({pct:.1f}%)` を出力
  - 短い動画（S版 445 フレーム）では約 10 回の進捗 print が得られ、長い動画（L版 321K フレーム）でも約 10 回に集約される
- カウント統計はループ中に print せず、完了時のサマリとしてまとめて出力

## 9. インターフェース定義（関数シグネチャ）

```python
def compute_pink_ratio(roi_bgr: np.ndarray) -> float: ...

def compute_iou(
    a: tuple[int, int, int, int],
    b: tuple[int, int, int, int],
) -> float: ...

def clip_bbox(
    bbox: tuple[float, float, float, float],
    width: int,
    height: int,
) -> tuple[int, int, int, int]: ...

def select_pink_bbox(
    bboxes: list[tuple[int, int, int, int] | None],
    ratios: list[float],
    prev_selected_bbox: tuple[int, int, int, int] | None,
) -> int | None: ...

def load_json_frames(
    json_dir: str,
) -> dict[int, tuple[str, dict]]: ...

def write_json_frame(out_path: str, data: dict) -> None: ...

def main() -> None: ...
```

`select_pink_bbox` 内では `bboxes[i] is None` の要素は ratio も 0.0 であり `MIN_PINK_RATIO` 未満のため `candidates` から自動的に除外される。None を明示的にスキップする追加ロジックは不要。

クラスは作らない。すべてモジュールレベル関数で実装する（スクリプト1本完結のため）。

## 10. 設計判断の記録（ADR）

### ADR-001: `load_data` の流用ではなく生dict保持方式を採用

- **採用案**: JSONの全dictを読み込み時に保持し、`pink_id` フィールドのみを追加して書き戻す
- **却下案**: `postprocess_reid.py` の `load_data()` を流用してキーポイントを numpy 配列化する
- **理由**: 本案件ではキーポイントに触らないため numpy 変換は不要。生dict保持は `stable_id` や将来追加される任意フィールドを自動的に保持でき、出力の完全性が上がる

### ADR-002: スクリプトからのモジュール分離はしない

- **採用案**: 1ファイル `scripts/postprocess_pink_id.py` で完結
- **却下案**: `compute_pink_ratio` や `select_pink_bbox` を別モジュールとして分離
- **理由**: 本案件は検証ベースライン。将来 feat-032 の結果次第で廃止される可能性もあり、過度な抽象化は避ける。再利用が必要になった時点で別案件として分離する

### ADR-003: `prev_selected_bbox` はクリッピング後の整数タプルで保持

- **採用案**: BBを画像範囲でクリッピングし、`round()` で整数化した `tuple[int, int, int, int]` を `prev_selected_bbox` および内部 `bboxes` リストに格納する。IoU 計算もこのクリッピング後BB同士で行う。出力JSONの `bbox` フィールドは入力時の元値をそのまま保持し変更しない
- **却下案A**: クリッピングせず元BBをそのまま保持（負値や画像幅超えを許容）
- **却下案B**: float のまま保持
- **理由**: 参考元 `pink_tracker_jhub.py` L114-117 はクリッピング済みBBを `last_box` に格納しており、これと挙動を一致させる。float 保持は IoU 計算で微小誤差が蓄積し参考元と値がズレるため避ける。整数化による精度低下は IoU 計算上無視できる

### ADR-004: 出力JSONで入力フィールドを一切変更しない

- **採用案**: 入力JSONの生dictをそのまま保持し、`people[*].pink_id` のみ追加
- **却下案**: 不要フィールド（face_keypoints_2d 等の空配列）を削除して出力を軽量化
- **理由**: 互換性と最小差分の原則。既存ツール（`postprocess_reid.py` など）が再実行された場合に差分が発生しないようにする

### ADR-005: ログは logging ではなく print で

- **採用案**: `print(f"WARNING: ...")` のような prefix 付き print
- **却下案**: `logging` モジュール導入
- **理由**: 既存 `postprocess_reid.py` と揃える。本案件はスクリプト1本の独立ツールであり、ログ集約の必要はない
