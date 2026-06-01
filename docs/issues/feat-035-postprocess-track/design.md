# feat-035: postprocess_track.py 実装（Deep OC-SORT 単独、track_id 付与） — 機能設計書

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001（入力 JSON 読み込み、生 dict 保持） | §4.1 |
| FR-002（Deep OC-SORT 初期化） | §4.2 |
| FR-003（検出データ配列構築、有効人物抽出） | §4.3 |
| FR-004（track_id の JSON 人物への割り当て） | §4.4 |
| FR-005（ポストプロセス本体） | §4.5 |
| FR-006（CLI インタフェース） | §4.6 |
| FR-007（進捗表示・サマリ出力） | §4.7 |
| NFR-001（パフォーマンス） | §7.1 |
| NFR-003（信頼性） | §4.5.4 / §8 |
| NFR-004（メモリ） | §7.2 |

## 2. システム構成

### 2.1 モジュール構成

本案件で作成するのは 1 つの独立スクリプト `scripts/postprocess_track.py` のみ。他スクリプトからの import は想定しない。

```
scripts/postprocess_track.py
├─ 定数
│   ├─ IOU_THRESHOLD = 0.5
│   ├─ TRACK_ID_UNMATCHED = -1
│   ├─ PROGRESS_INTERVAL_FRAMES = 3000
│   └─ DEEP_OC_SORT_MAX_AGE = 30
├─ 純関数
│   ├─ load_json_frames(json_dir) → dict[int, tuple[str, dict]]       (FR-001)
│   ├─ init_tracker(device) → DeepOcSort                               (FR-002)
│   ├─ build_dets(people, frame_idx) → tuple[np.ndarray, list[int]]    (FR-003)
│   ├─ _is_valid_bbox(bbox) → bool                                     (FR-003 ヘルパー)
│   ├─ _is_number(v) → bool                                            (FR-003 ヘルパー)
│   ├─ parse_tracks(tracks_array) → dict[int, list[float]]             (FR-005 内部ユーティリティ)
│   ├─ compute_iou(a, b) → float
│   └─ assign_track_ids(people, valid_indices, tracked_bboxes) → list[int]  (FR-004)
├─ I/O 関数
│   ├─ write_json_frame(out_path, data) → None
│   └─ print_summary(total_frames_processed, all_track_ids, elapsed, out_dir) → None   (FR-007)
└─ エントリポイント
    └─ main() → None                                                    (FR-005, FR-006, FR-007)
```

### 2.2 既存ファイルとの関係

- **流儀元**: `scripts/postprocess_reid.py`（feat-028）の CLI 構造、フレームループ、Deep OC-SORT 初期化、`compute_iou` ロジックを流用
- **生 dict 保持のお手本**: `scripts/postprocess_pink_id.py`（feat-033）の `load_json_frames` および「入力 content_dict を直接書き換えて出力」の流儀を採用
- **変更禁止**: 既存ファイル（`postprocess_reid.py`, `postprocess_pink_id.py`, `custom_reid.py`, `visualize_tracking.py`, `run_halpe26_pipeline_yolo11.py`）は本案件で一切変更しない。コードは流儀を参考にコピー・改変する（共通モジュールへの切り出しは本案件のスコープ外）

### 2.3 ディレクトリ構成

```
scripts/
├── postprocess_reid.py              # 既存（変更しない）
├── postprocess_pink_id.py           # 既存（変更しない）
└── postprocess_track.py             # 新規（本案件）

experiments/results/
├── camSony1_S_json/                 # 入力（既存、変更しない）
└── camSony1_S_track_json/           # 出力（本案件で生成、推奨命名）
```

出力ディレクトリ名の規約: `{入力ディレクトリ名}_track`（例: `camSony1_S_json` → `camSony1_S_track_json`）。規約は README と feat-034 ロードマップでの推奨にとどめ、スクリプト内では強制しない（CLI 引数で任意パス指定可）。

## 3. 技術スタック

| 項目 | 値 | 選定理由 |
|------|-----|----------|
| 言語 | Python 3.10.16 | プロジェクト既定 |
| パッケージ管理 | uv | プロジェクト既定。`uv run python scripts/postprocess_track.py` で実行 |
| BoxMOT | 既存 uv 環境の `boxmot.DeepOcSort` | Deep OC-SORT トラッカー。feat-028 と同一バージョン（本案件でバージョン変更なし） |
| OpenCV | 既存 uv 環境の `opencv-python` | 動画読み込み（`cv2.VideoCapture`） |
| numpy | 既存 uv 環境の `numpy` | 検出配列構築、トラッカー戻り値のパース |

追加ライブラリの導入は行わない。`custom_reid`、`scipy`、`pandas`、`matplotlib` は import しない。

## 4. 各機能の詳細設計

### 4.1 FR-001: 入力 JSON 読み込み（生 dict 保持）

#### 4.1.1 データフロー

- 入力: `json_dir: str`（JSON ディレクトリパス）
- 中間: `json_files: list[Path]`（`sorted(Path(json_dir).glob("*.json"))`）
- 出力: `frame_to_json: dict[int, tuple[str, dict]]`

#### 4.1.2 処理ロジック

```python
def load_json_frames(json_dir: str) -> dict[int, tuple[str, dict]]:
    """JSONディレクトリを全読み込みし、生dict を辞書として保持する（FR-001）。

    Returns: {frame_idx: (original_filename, content_dict)}
    """
    json_path = Path(json_dir)
    json_files = sorted(json_path.glob("*.json"))
    if not json_files:
        print(f"ERROR: No JSON files found in {json_dir}")
        sys.exit(1)

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

※コードスニペットは意図伝達用。実装時は docstring・型ヒントを整える。

#### 4.1.3 境界条件

- `json_dir` が存在しないまたは空 → `sorted(Path(...).glob(...))` は空リストを返し、ERROR 出力後 `sys.exit(1)`
- ファイル名が `_(\d{6})\.json$` パターンに合致しない → スキップ（辞書に登録しない）
- 単一ファイルで `json.load()` が `JSONDecodeError` を raise → WARNING を出し、`{"version": 1.3, "people": []}` を登録

#### 4.1.4 エラーハンドリング

- 本関数は JSON 0 件のときに `sys.exit(1)` する以外、例外を raise しない
- ファイル単位のデコード失敗は空 people へのフォールバックで回復可能

### 4.2 FR-002: Deep OC-SORT 初期化

#### 4.2.1 データフロー

- 入力: `device: str`（例: `cuda:0`, `cpu`）
- 出力: `DeepOcSort` インスタンス

#### 4.2.2 処理ロジック

```python
def init_tracker(device: str) -> DeepOcSort:
    """Deep OC-SORT トラッカーを初期化する（FR-002）。"""
    reid_path = Path(__file__).resolve().parent.parent / "osnet_x0_25_msmt17.pt"
    try:
        return DeepOcSort(
            reid_weights=reid_path,
            device=device,
            half="cuda" in device,
            max_age=DEEP_OC_SORT_MAX_AGE,
            w_association_emb=0.0,
        )
    except TypeError:
        print("WARNING: w_association_emb not supported, falling back without it")
        return DeepOcSort(
            reid_weights=reid_path,
            device=device,
            half="cuda" in device,
            max_age=DEEP_OC_SORT_MAX_AGE,
        )
```

- `reid_path` はリポジトリルート直下の `osnet_x0_25_msmt17.pt`（`postprocess_reid.py` と同じ解決規則）
- `DEEP_OC_SORT_MAX_AGE = 30`（feat-028 と同値）
- `w_association_emb=0.0` により外観埋め込みの重みをゼロにする（feat-028 踏襲）

#### 4.2.3 境界条件

- `osnet_x0_25_msmt17.pt` が存在しない場合、BoxMOT 内部で `FileNotFoundError` または関連例外が raise される。本関数では捕捉しない（デフォルト終了コード 1 で終了）
- `device` が不正（例: `foo`）な場合、BoxMOT/PyTorch 内部で `RuntimeError` 等が raise される。本関数では捕捉しない

### 4.3 FR-003: 検出データ配列構築（有効人物抽出）

#### 4.3.1 データフロー

- 入力:
  - `people: list[dict]`（1 フレーム分の JSON `people` 配列）
  - `frame_idx: int`（WARNING ログ出力用）
- 出力: `(dets: np.ndarray, valid_indices: list[int])`
  - `dets.shape == (M, 6)`, `dtype == float32`、M は有効人物数
  - `valid_indices[i]` は `dets[i]` に対応する元 `people` のインデックス

#### 4.3.2 処理ロジック

```python
def build_dets(
    people: list[dict],
    frame_idx: int,
) -> tuple[np.ndarray, list[int]]:
    """有効人物のみから Deep OC-SORT 入力用の dets 配列を構築する（FR-003）。"""
    if len(people) == 0:
        return np.empty((0, 6), dtype=np.float32), []

    rows: list[list[float]] = []
    valid_indices: list[int] = []
    for i, person in enumerate(people):
        bbox = person.get("bbox")
        score = person.get("bbox_score")
        if not _is_valid_bbox(bbox) or not _is_number(score):
            print(
                f"WARNING: Invalid bbox/bbox_score in frame {frame_idx} "
                f"person {i}, excluding from tracking"
            )
            continue
        rows.append([bbox[0], bbox[1], bbox[2], bbox[3], float(score), 0.0])
        valid_indices.append(i)

    if len(rows) == 0:
        return np.empty((0, 6), dtype=np.float32), []
    return np.array(rows, dtype=np.float32), valid_indices


def _is_valid_bbox(bbox) -> bool:
    if bbox is None:
        return False
    if not isinstance(bbox, (list, tuple)):
        return False
    if len(bbox) != 4:
        return False
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in bbox)


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)
```

- `frame_idx` を引数で受け取るのは WARNING メッセージにフレーム番号を含めるため
- `bool` は `int` のサブクラスなので明示的に除外する（座標・スコアとして `True/False` が入ることを防ぐ）

#### 4.3.3 境界条件

- `people` が空 → `(shape=(0, 6), [])` を返す
- 全員無効人物 → `(shape=(0, 6), [])` を返す（WARNING は人数分出力される）
- 1 人だけ有効 → `dets.shape == (1, 6)`、`valid_indices == [対応インデックス]`

#### 4.3.4 エラーハンドリング

- 本関数は例外を raise しない。入力の型不正は WARNING を出してその人物を除外する

### 4.4 FR-004: track_id の JSON 人物への割り当て（IoU マッチング）

#### 4.4.1 データフロー

- 入力:
  - `people: list[dict]`
  - `valid_indices: list[int]`
  - `tracked_bboxes: dict[int, list[float]]`
  - `iou_threshold: float = IOU_THRESHOLD`（定数 0.5）
- 出力: `result: list[int]`、長さ `len(people)`

#### 4.4.2 処理ロジック

```python
def compute_iou(a: list[float], b: list[float]) -> float:
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def assign_track_ids(
    people: list[dict],
    valid_indices: list[int],
    tracked_bboxes: dict[int, list[float]],
    iou_threshold: float = IOU_THRESHOLD,
) -> list[int]:
    """各 JSON 人物に track_id を割り当てる（FR-004）。"""
    result = [TRACK_ID_UNMATCHED] * len(people)
    if not tracked_bboxes:
        return result

    for i in valid_indices:
        person_bbox = people[i]["bbox"]
        best_iou = 0.0
        best_tid: int | None = None
        for tid, trk_bbox in tracked_bboxes.items():
            iou = compute_iou(person_bbox, trk_bbox)
            if iou > best_iou:
                best_iou = iou
                best_tid = tid
            elif iou == best_iou and best_tid is not None and tid < best_tid:
                best_tid = tid
        if best_iou >= iou_threshold and best_tid is not None:
            result[i] = best_tid
    return result
```

- `best_iou = 0.0` 初期値のため、全 track との IoU が 0 の人物は `best_tid = None` のままで `-1` が割り当てられる（AC-004-4）
- 同値タイブレークは `elif iou == best_iou and best_tid is not None and tid < best_tid` により track_id が小さい方を優先（AC-004-5）
- `valid_indices` に含まれない人物（無効人物）は `result` の初期値 `-1` のままとなる（AC-004-6）
- `postprocess_reid.py` L178-195 の `assign_stable_ids` と同じ貪欲 IoU 最大方式（AC-004-7）

#### 4.4.3 境界条件

- `tracked_bboxes` が空辞書 → 全要素 `-1` を返す（AC-004-1）
- `valid_indices` が空リスト → 全要素 `-1` を返す
- `len(people) == 0` → 空リストを返す（`valid_indices` も空になるため for ループを通らない）
- IoU がすべて `iou_threshold` 未満 → `-1` を返す（AC-004-3）
- 全 track との IoU が 0 の有効人物 → `best_iou = 0.0` 初期値に対して `iou > best_iou` は `0 > 0` で False となり、`elif iou == best_iou` 分岐に入るが `best_tid is not None` ガードにより更新スキップされる。結果 `best_tid = None` のまま閾値判定に進み、`result[i]` は `-1` のまま（AC-004-4）

#### 4.4.4 エラーハンドリング

- 本関数は例外を raise しない。不正入力は呼び出し元（FR-003 / FR-005）で弾かれる前提

### 4.5 FR-005: ポストプロセス本体

#### 4.5.1 データフロー

- 入力:
  - `args.video: str`（動画ファイルパス）
  - `args.json_dir: str`（入力 JSON ディレクトリ）
  - `args.out_dir: str`（出力 JSON ディレクトリ）
  - `args.device: str`（BoxMOT デバイス）
- 中間:
  - `frame_to_json: dict[int, tuple[str, dict]]`
  - `tracker: DeepOcSort`
  - `cap: cv2.VideoCapture`
  - `frame_bgr: np.ndarray`（shape=(H, W, 3), dtype=uint8, BGR）
  - `dets: np.ndarray`（shape=(M, 6), dtype=float32）
  - `valid_indices: list[int]`
  - `tracks: np.ndarray`（Deep OC-SORT の戻り値、shape=(N, 5 以上), インデックス 4 が track_id）
  - `tracked_bboxes: dict[int, list[float]]`
  - `assigned_track_ids: list[int]`
- 出力:
  - 出力ディレクトリに `{video_stem}_{frame_idx:06d}.json` を書き出す

#### 4.5.2 初期化フェーズ擬似コード

```
1. args = argparse.parse_args()
2. if os.path.realpath(args.json_dir) == os.path.realpath(args.out_dir):
       print("ERROR: --out-dir must differ from --json-dir to prevent overwriting")
       sys.exit(1)
3. os.makedirs(args.out_dir, exist_ok=True)
4. frame_to_json = load_json_frames(args.json_dir)     # FR-001
5. print(f"Loaded {len(frame_to_json)} frames from JSON")
6. cap = cv2.VideoCapture(args.video)
7. if not cap.isOpened():
       print(f"ERROR: Cannot open video {args.video}")
       sys.exit(1)
8. total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
9. tracker = init_tracker(args.device)                 # FR-002
10. all_track_ids = set()  # ユニーク集計用
11. frame_idx = 0
12. start_time = time.time()
```

#### 4.5.3 メインループ擬似コード

```
loop:
    ret, frame_bgr = cap.read()
    if not ret:
        break

    entry = frame_to_json.get(frame_idx)

    if entry is None:
        # 入力 JSON がないフレーム: tracker の時間同期のみ、JSON は出力しない
        tracker.update(np.empty((0, 6), dtype=np.float32), frame_bgr)
    else:
        filename, content_dict = entry
        people = content_dict.get("people", [])

        # FR-003: 有効人物抽出
        dets, valid_indices = build_dets(people, frame_idx)

        # Deep OC-SORT でトラッキング
        tracks = tracker.update(dets, frame_bgr)

        # tracks を辞書化（parse_tracks ユーティリティ）
        tracked_bboxes = parse_tracks(tracks)

        # FR-004: 各人物に track_id 割り当て
        assigned = assign_track_ids(people, valid_indices, tracked_bboxes)

        # 生 dict に track_id を書き込む（既存フィールド不変）
        for i, person in enumerate(people):
            person["track_id"] = assigned[i]

        # ユニーク集計（>= 1 のみ）
        for tid in assigned:
            if tid >= 1:
                all_track_ids.add(tid)

        # JSON 書き出し
        out_path = os.path.join(args.out_dir, filename)
        write_json_frame(out_path, content_dict)

    # 進捗表示（FR-007）
    if frame_idx % PROGRESS_INTERVAL_FRAMES == 0:
        if total_frames > 0:
            pct = frame_idx / total_frames * 100
            print(f"Processing frame {frame_idx:06d}/{total_frames} ({pct:.1f}%)")
        else:
            print(f"Processing frame {frame_idx:06d}/?")

    frame_idx += 1

cap.release()
elapsed = time.time() - start_time
print_summary(frame_idx, all_track_ids, elapsed, args.out_dir)
```

補助関数:

```python
def parse_tracks(tracks: np.ndarray) -> dict[int, list[float]]:
    """Deep OC-SORT の戻り値を {track_id: [x1, y1, x2, y2]} に変換する。

    tracks: shape=(N, 5 以上) の numpy 配列。
      インデックス 0〜3 が bbox、インデックス 4 が track_id。
      空配列（shape=(0,) または shape=(0, K)）の場合は空辞書を返す。
    """
    if len(tracks) == 0:
        return {}
    return {int(t[4]): t[:4].tolist() for t in tracks}


def write_json_frame(out_path: str, data: dict) -> None:
    with open(out_path, "w") as f:
        json.dump(data, f)
```

#### 4.5.4 エラーハンドリング

| 想定エラー | 検出方法 | 処理 | ログ |
|-----------|----------|------|------|
| `--out-dir == --json-dir` | `os.path.realpath` 比較 | ERROR 出力 → `sys.exit(1)` | `ERROR: --out-dir must differ from --json-dir to prevent overwriting` |
| 入力 JSON ディレクトリにファイルなし | `load_json_frames` 内で 0 件検出 | ERROR 出力 → `sys.exit(1)` | `ERROR: No JSON files found in {json_dir}` |
| 入力動画が開けない | `cap.isOpened() == False` | ERROR 出力 → `sys.exit(1)` | `ERROR: Cannot open video {path}` |
| `osnet_x0_25_msmt17.pt` が存在しない | BoxMOT 内部で例外 | 例外を捕捉せず伝播（Python デフォルト終了コード 1） | - |
| `--device` が不正 | BoxMOT/PyTorch 内部で例外 | 例外を捕捉せず伝播 | - |
| `w_association_emb` 未対応 | `DeepOcSort()` が `TypeError` を raise | `w_association_emb` を省略してフォールバック初期化 | `WARNING: w_association_emb not supported, falling back without it` |
| 個別 JSON の parse 失敗 | `json.JSONDecodeError` | WARNING 出力、空 people として処理継続 | `WARNING: Failed to parse {name}, treating as empty` |
| 個別人物の `bbox`/`bbox_score` 欠損 | `_is_valid_bbox` / `_is_number` false | WARNING 出力、無効人物として扱い `-1` 割り当て | `WARNING: Invalid bbox/bbox_score in frame {idx} person {i}, excluding from tracking` |
| 入力 JSON の `people` キーがリストでない/不正型 | 後続の `for person in people:` で `TypeError` | 例外を捕捉せず伝播（入力 JSON は `run_halpe26_pipeline_yolo11.py` 出力に準拠する前提。準拠しない入力はサポート外） | - |
| 途中フレームで動画読み込み失敗 | `cap.read()` が `ret == False` | ループを break（処理済み JSON はそのまま保持） | - |

### 4.6 FR-006: CLI インタフェース

```python
parser = argparse.ArgumentParser(
    description="Add track_id to HALPE 26 JSON via Deep OC-SORT"
)
parser.add_argument("--video", required=True, help="Video file path")
parser.add_argument(
    "--json-dir", required=True, help="Input HALPE 26 JSON directory"
)
parser.add_argument(
    "--out-dir", required=True,
    help="Output JSON directory (must differ from --json-dir)",
)
parser.add_argument(
    "--device", default="cuda:0", help="BoxMOT device (e.g., cuda:0, cpu)"
)
args = parser.parse_args()
```

- 必須引数未指定時の argparse エラー（終了コード 2）は argparse のデフォルト挙動に任せる
- 同一パスチェックは `postprocess_reid.py` L238-240 と同じ

#### フェーズ1実行コマンド（手動テスト時に実行）

```
uv run python scripts/postprocess_track.py \
  --video testdata/camSony1_S.mp4 \
  --json-dir experiments/results/camSony1_S_json \
  --out-dir experiments/results/camSony1_S_track_json
```

#### フェーズ2実行コマンド（本番スケール検証）

```
uv run python scripts/postprocess_track.py \
  --video experiments/input/camSony1_L.mp4 \
  --json-dir experiments/results/camSony1_L_json \
  --out-dir experiments/results/camSony1_L_track_json
```

### 4.7 FR-007: 進捗表示・サマリ出力

#### 4.7.1 進捗表示

メインループ内で `frame_idx % PROGRESS_INTERVAL_FRAMES == 0`（`PROGRESS_INTERVAL_FRAMES = 3000`）を満たすフレームで進捗を出力する。`frame_idx = 0` も含まれる。`entry is None`（入力 JSON なし）のフレームでも、動画から読み取った全フレームが `frame_idx` カウントに含まれるため、進捗ログは動画フレーム数基準で出力される。

```python
if frame_idx % PROGRESS_INTERVAL_FRAMES == 0:
    if total_frames > 0:
        pct = frame_idx / total_frames * 100
        print(f"Processing frame {frame_idx:06d}/{total_frames} ({pct:.1f}%)")
    else:
        print(f"Processing frame {frame_idx:06d}/?")
```

- 321,239 フレーム処理時: `frame_idx = 0, 3000, ..., 321000` → 計 108 行（AC-007-1）
- `total_frames <= 0` のときは `/?` 表記

#### 4.7.2 サマリ出力

メインループ終了後、`cap.release()` の後に出力する:

```python
def print_summary(
    total_frames_processed: int,
    all_track_ids: set[int],
    elapsed: float,
    out_dir: str,
) -> None:
    fps = total_frames_processed / elapsed if elapsed > 0 else 0.0
    print()
    print(f"Total frames: {total_frames_processed}")
    print(f"Unique track IDs: {len(all_track_ids)}")
    print(f"Processing time: {elapsed:.1f} sec ({fps:.1f} fps)")
    print(f"Output directory: {out_dir}")
```

- `total_frames_processed` は `cap.read()` が成功した回数（= ループ終了時点の `frame_idx`）。`entry is None`（入力 JSON なし）のフレームも含む動画フレーム総数。出力 JSON 数ではない
- `all_track_ids` は `track_id >= 1` のユニーク集合。`-1` は除外（AC-007-3）

## 5. 状態遷移

本スクリプトにはスクリプト側の明示的な状態遷移はない。Deep OC-SORT トラッカー内部には以下の隠れた状態があるが、本スクリプトからは `tracker.update()` の呼び出しでのみアクセスする:

| 内部状態 | 説明 |
|---------|------|
| `active_tracks` | Deep OC-SORT が現在保持している track オブジェクト集合 |
| `frame_count` | `tracker.update()` の呼び出し回数 |

**重要な設計判断**: 入力 JSON がないフレームでも `tracker.update(np.empty((0, 6), dtype=np.float32), frame_bgr)` を呼び出すことで、`frame_count` と各 track の `time_since_update` を正しく進める。これにより `max_age` による古い track の淘汰が動画フレーム数ベースで正確に動作する（AC-005-9）。

## 6. ファイル・ディレクトリ設計

### 6.1 入力ファイル規約

- 動画: 任意のパス、`.mp4` 形式
- 入力 JSON: `{任意のディレクトリ}/{video_stem}_{frame_idx:06d}.json`
  - 例: `experiments/results/camSony1_S_json/camSony1_S_000000.json`
  - `video_stem`: 動画ファイル名から拡張子を除いたもの
  - `frame_idx`: 6 桁ゼロ埋め

### 6.2 出力ファイル規約

- 出力ディレクトリ: CLI 引数 `--out-dir` で指定される任意パス
- ファイル名: 入力 JSON と完全に同一（`{video_stem}_{frame_idx:06d}.json`）
- 中身: 入力 JSON の各 `people[*]` に `track_id: int` を追加したもの。その他のフィールドは元通り

### 6.3 出力 JSON スキーマ差分

```json
{
  "version": 1.3,
  "people": [
    {
      "person_id": [-1],
      "pose_keypoints_2d": [...],
      "bbox": [x1, y1, x2, y2],
      "bbox_score": 0.95,
      "stable_id": 3,        // 入力に存在する場合のみ、変更なし
      "pink_id": 1,          // 入力に存在する場合のみ、変更なし
      "track_id": 5          // 新規追加（Deep OC-SORT が発番した 1 以上の正整数。マッチなし/無効人物は -1）
    }
  ]
}
```

### 6.4 Stage 順序との関係

feat-034 ロードマップでは Stage 2（本案件）→ Stage 3（feat-033）→ Stage 4（feat-036）の順序で実行する。本設計の生 dict 保持により、`track_id` は Stage 3 を通過する際に自動保持される。

## 7. 非機能

### 7.1 パフォーマンス見積もり

- camSony1_S（900 フレーム）: 数秒〜十数秒で完了見込み
- camSony1_L（321K フレーム）: feat-028 `postprocess_reid.py` の実測値（約 190 fps）と同等以上を期待。`custom_reid` 呼び出しを削除する分、若干の高速化が見込まれる（カスタム Re-ID の HSV 特徴量計算が不要）。ただし保証しない

### 7.2 メモリ使用量

`frame_to_json` 辞書のメモリ見積もり:

- **1 人あたりの主要フィールドのバイト数（JSON テキスト基準）**:
  - `pose_keypoints_2d`: HALPE 26 キーポイント 26 × 3 = 78 float。JSON テキストで約 500〜700 bytes
  - `bbox`: 4 float、約 50〜80 bytes
  - `bbox_score`: 1 float、約 15〜25 bytes
  - `person_id`, `face_keypoints_2d`, `hand_left_keypoints_2d` 等の空配列・メタ: 約 200〜300 bytes
  - 合計: **1 人あたり約 1 KB の JSON テキスト**
- **1 フレームあたりの人数**: 室内動画は通常 1〜3 人、多くても 5 人程度
- **camSony1_L（321,239 フレーム）の見積もり**:
  - JSON テキスト合計: 約 321,239 × 3 人 × 1 KB ≒ 約 0.96 GB
  - Python dict として保持する場合、オブジェクトヘッダ・参照オーバーヘッドで 2〜3 倍になりうる（約 2〜3 GB）

**500 MB 目標との乖離**: 上記見積もりは 500 MB を大きく超える可能性がある。要求仕様書 NFR-004 の検証基準は「OOM で異常終了せず完走すること」が必須、「500 MB 以下」は目標値として扱う。超過した場合は本案件内で改修せず、別案件でストリーミング読み込み（全フレーム一括読み込みの廃止、`Path.glob()` + 1 フレームずつの lazy 読み込み）への切り替えを検討する。

**補足**:
- JSON 書き出しは 1 フレームずつ行い、出力バッファは保持しない
- Deep OC-SORT 内部の `active_tracks` は `max_age = 30` で淘汰されるため有界（検出人物数 × 30 フレーム分の track オブジェクト）
- 手動テスト時は `uv run python scripts/postprocess_track.py ...` を実行し、`ps` / `top` / `psutil` 等で RSS を観測する

## 8. ログ・デバッグ設計

- ログ手段: `print()`（`postprocess_reid.py` / `postprocess_pink_id.py` と揃える。`logging` モジュールは導入しない）
- ログレベル表記: `ERROR:` / `WARNING:` / (INFO は prefix なしで `print`)
- ログ出力ポイント:
  - 起動時: `Loaded N frames from JSON`
  - メインループ中: 進捗表示（`frame_idx % 3000 == 0`）
  - エラー・警告: §4.5.4 のテーブル参照
  - 終了時: サマリ（§4.7.2）

## 9. インターフェース定義（関数シグネチャ）

```python
def load_json_frames(
    json_dir: str,
) -> dict[int, tuple[str, dict]]: ...

def init_tracker(device: str) -> DeepOcSort: ...

def build_dets(
    people: list[dict],
    frame_idx: int,
) -> tuple[np.ndarray, list[int]]: ...

def parse_tracks(tracks: np.ndarray) -> dict[int, list[float]]: ...

def compute_iou(
    a: list[float],
    b: list[float],
) -> float: ...

def assign_track_ids(
    people: list[dict],
    valid_indices: list[int],
    tracked_bboxes: dict[int, list[float]],
    iou_threshold: float = IOU_THRESHOLD,
) -> list[int]: ...

def write_json_frame(out_path: str, data: dict) -> None: ...

def print_summary(
    total_frames_processed: int,
    all_track_ids: set[int],
    elapsed: float,
    out_dir: str,
) -> None: ...

def _is_valid_bbox(bbox) -> bool: ...
def _is_number(v) -> bool: ...

def main() -> None: ...
```

クラスは作らない。すべてモジュールレベル関数で実装する。

定数:

```python
IOU_THRESHOLD: float = 0.5
TRACK_ID_UNMATCHED: int = -1
PROGRESS_INTERVAL_FRAMES: int = 3000
DEEP_OC_SORT_MAX_AGE: int = 30
```

## 10. 設計判断の記録（ADR）

### ADR-001: 生 dict 保持設計の採用（feat-033 ADR-001 踏襲）

- **採用案**: 入力 JSON を `json.load()` で生の辞書として読み込み、`people[*]` に `track_id` キーを追加するだけで出力する
- **却下案**: feat-028 `postprocess_reid.py` のように入力ファイルを出力時に再度読み直し、必要フィールドのみ抽出・保持する方式
- **理由**: 4 ステージパイプラインの Stage 2 として Stage 3（feat-033）→ Stage 4（feat-036）の順で処理される。生 dict 保持により Stage 2 出力に `stable_id` / `pink_id` / 将来フィールドが混在しても自動保持される。feat-033 ADR-001 と同じ設計思想により 4 ステージ全体の一貫性を確保する

### ADR-002: IoU マッチング方式の採用（det_ind 方式の却下）

- **採用案**: Deep OC-SORT の戻り値から `tracked_bboxes` 辞書を構築し、各 JSON 人物の `bbox` との IoU を貪欲に最大化して `track_id` を割り当てる（`postprocess_reid.py` の `assign_stable_ids` と同等）
- **却下案**: Deep OC-SORT 戻り値の第 7 列 `trk.det_ind`（元 dets のインデックス）を直接利用する
- **理由**: (1) `det_ind` は BoxMOT の内部実装依存で、将来バージョンで挙動が変わる可能性がある。(2) feat-028 で IoU マッチング方式が既に動作実績あり、リスクゼロで流用できる。(3) 貪欲 IoU 最大方式は BB 重複入力に対しても意味的に妥当（同一 `track_id` が複数人物に割り当たるのは「同じ人物の重複 BB」という解釈が成り立つ。BB 重複除去の最終責任は feat-025 が担い、本案件のスコープ外）

### ADR-003: `custom_reid.py` 依存を完全削除

- **採用案**: `CustomReID` / `stable_id` 関連のコードを一切 import しない。`postprocess_reid.py` から CLI 構造と `compute_iou` のみをコピー改変する
- **却下案**: `postprocess_reid.py` に `--no-reid` フラグを追加し、Re-ID をスキップできるようにする
- **理由**: feat-034 ロードマップで `custom_reid.py` 系統は凍結中。新トラッキング方式では Stage 2 が Deep OC-SORT 単独、Stage 3 が `pink_id`、Stage 4 がハイブリッドという明確な責務分離になっている。既存 `postprocess_reid.py` にフラグを追加すると複合責務が残り、設計の意図が曖昧になる

### ADR-004: 入力 JSON がないフレームでも `tracker.update()` を呼ぶ

- **採用案**: `entry is None`（`frame_to_json.get(frame_idx) is None`）のフレームでも `tracker.update(np.empty((0, 6), dtype=np.float32), frame_bgr)` を呼び出し、tracker の内部 `frame_count` と各 track の `time_since_update` を進める。出力 JSON は書き出さない
- **却下案A**: 入力 JSON がないフレームは `tracker.update()` を呼ばずスキップする
- **却下案B**: 空の JSON を出力ディレクトリに作成する
- **理由**: (1) Deep OC-SORT の `max_age` 判定は `frame_count` ベースで動作するため、`update()` を飛ばすと「古い track が淘汰されずに残留」する問題が発生する。(2) 出力 JSON は「入力 JSON に対応するフレームのみ」という設計（AC-005-2）を守るため、空 JSON の作成は行わない。この両方を満たす唯一の方式が「tracker 更新 + JSON 出力なし」

### ADR-005: モジュール分離はしない

- **採用案**: 1 ファイル `scripts/postprocess_track.py` で完結させる
- **却下案**: `compute_iou` や `assign_track_ids` を共通モジュール（例: `scripts/tracking_utils.py`）に切り出す
- **理由**: (1) `postprocess_reid.py` / `postprocess_pink_id.py` も 1 ファイル完結。既存の流儀と揃える。(2) feat-034 ロードマップで今後 Stage 4（`postprocess_pink_track_id.py`）も新規作成される。共通化の必要性はその時点で判断する。早すぎる抽象化は避ける

### ADR-006: ログは `print` で統一

- **採用案**: `print(f"ERROR: ...")`, `print(f"WARNING: ...")` の prefix 付き print
- **却下案**: `logging` モジュール導入
- **理由**: 既存 `postprocess_reid.py` / `postprocess_pink_id.py` と統一する。本案件はスクリプト 1 本の独立ツールで、ログ集約や構造化ログの必要はない
