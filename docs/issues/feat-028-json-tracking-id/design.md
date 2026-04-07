# feat-028: JSONにトラッキングID記録 機能設計書

## 1.1 対応要求マッピング

| 要求 ID | 設計セクション |
|---------|--------------|
| FR-001 | 1.4.1 ポストプロセススクリプト |
| FR-002 | 1.4.2 stable_idとJSON人物の対応付け |
| FR-003 | 1.4.3 出力JSONフォーマット |
| FR-004 | 1.4.4 進捗表示 |

---

## 1.2 システム構成

### モジュール構成

```
scripts/
├── postprocess_reid.py         # [新規] Re-IDポストプロセススクリプト
├── halpe26_to_openpose.py      # [変更] stable_ids引数追加（将来のパイプライン統合用）
├── custom_reid.py              # [変更なし] CustomReIDクラス
└── test_custom_reid_offline.py # [変更なし] オフライン検証（参考実装）
```

### モジュール間の依存関係

```
postprocess_reid.py
  ├── custom_reid.py            # CustomReID クラス
  └── boxmot.DeepOcSort         # トラッカー（既存環境）
```

`postprocess_reid.py` は `test_custom_reid_offline.py` のJSON読み込み・トラッカー初期化・IoUマッチングロジックを流用するが、import関係は持たない（コードをコピーして独立させる）。共通ユーティリティへの切り出しは本案件のスコープ外とする。将来的に重複コードが問題になった場合は別案件で対応する。

`postprocess_reid.py` は `halpe26_to_openpose.py` をimportしない。JSON出力は入力JSONのdictを直接編集する方式のため。

---

## 1.3 技術スタック

既存の技術スタックを使用する。新規ライブラリの追加なし。

| 技術 | バージョン | 用途 |
|------|-----------|------|
| Python | 3.10.16 | 実装言語 |
| uv | - | パッケージ管理 |
| NumPy | 2.2.6 | 配列演算 |
| OpenCV (cv2) | 4.13.0.92 | 動画読み込み |
| BoxMOT | 16.0.11 | Deep OC-SORT トラッカー |

---

## 1.4 各機能の詳細設計

### 1.4.1 ポストプロセススクリプト（FR-001）

#### ファイル: `scripts/postprocess_reid.py`

#### CLI引数

```python
parser = argparse.ArgumentParser(description="Add stable_id to HALPE 26 JSON via Re-ID")
parser.add_argument("--video", required=True, help="Video file path")
parser.add_argument("--json-dir", required=True, help="Input HALPE 26 JSON directory")
parser.add_argument("--out-dir", required=True, help="Output JSON directory (must differ from --json-dir)")
parser.add_argument("--device", default="cuda:0", help="BoxMOT device")
```

#### 上書き防止チェック

```python
if os.path.realpath(args.json_dir) == os.path.realpath(args.out_dir):
    print("ERROR: --out-dir must differ from --json-dir to prevent overwriting")
    sys.exit(1)
```

#### メインループの処理フロー

```python
def main() -> None:
    args = parse_args()

    # 上書き防止チェック
    if os.path.realpath(args.json_dir) == os.path.realpath(args.out_dir):
        print("ERROR: --out-dir must differ from --json-dir to prevent overwriting")
        sys.exit(1)

    # 出力ディレクトリ作成
    os.makedirs(args.out_dir, exist_ok=True)

    # JSON データ読み込み（全フレーム分を一括メモリに保持、321K×1人で約213MB）
    json_data = load_data(args.json_dir)
    print(f"Loaded {len(json_data)} frames from JSON")

    # 動画オープン
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"ERROR: Cannot open video {args.video}")
        sys.exit(1)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Deep OC-SORT 初期化
    tracker = init_tracker(args.device)

    # カスタム Re-ID 初期化
    reid = CustomReID(delay_frames=180)

    # 動画ファイル名のステム（JSONファイル名生成用）
    video_stem = os.path.splitext(os.path.basename(args.video))[0]

    # stable_id集計
    all_stable_ids: set[int] = set()

    frame_idx = 0
    start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        json_people = json_data.get(frame_idx, [])

        # 1. Deep OC-SORT でトラッキング
        dets = build_dets(json_people)
        tracks = tracker.update(dets, frame)
        tracked_bboxes = parse_tracks(tracks)
        track_ids = list(tracked_bboxes.keys())

        # 2. IoU マッチング: track_id → キーポイント（Re-ID用）
        keypoints_map = match_track_to_json(tracked_bboxes, json_people)

        # 3. カスタム Re-ID 更新
        stable_ids = reid.update(frame, track_ids, keypoints_map, frame_idx)

        # 4. JSON人物 → stable_id の割り当て
        person_stable_ids = assign_stable_ids(
            json_people, tracked_bboxes, stable_ids
        )

        # 5. JSON出力（入力JSONのdictを読み込み、stable_idを追加して書き出す）
        output_json = build_output_json(
            args.json_dir, video_stem, frame_idx, json_people, person_stable_ids
        )
        json_path = os.path.join(args.out_dir, f"{video_stem}_{frame_idx:06d}.json")
        with open(json_path, "w") as f:
            json.dump(output_json, f)

        # stable_id 集計
        for sid in person_stable_ids:
            if sid >= 1:
                all_stable_ids.add(sid)

        # 進捗表示（FR-004）
        if frame_idx % 3000 == 0:
            if total_frames > 0:
                pct = frame_idx / total_frames * 100
                print(f"Processing frame {frame_idx:06d}/{total_frames} ({pct:.1f}%)")
            else:
                print(f"Processing frame {frame_idx:06d}/?")

        frame_idx += 1

    cap.release()
    elapsed = time.time() - start_time

    # サマリー出力
    print()
    print(f"Total frames: {frame_idx}")
    print(f"Unique stable IDs: {len(all_stable_ids)}")
    if elapsed > 0:
        print(f"Processing time: {elapsed:.1f} sec ({frame_idx / elapsed:.1f} fps)")
    else:
        print(f"Processing time: {elapsed:.1f} sec")
    print(f"Output directory: {args.out_dir}")
```

#### JSON読み込み: `load_data()`

`test_custom_reid_offline.py` の `load_data()` と同一のロジックをコピーする。

- 戻り値: `dict[int, list[dict]]` — `{frame_idx: [{"bbox": list[float], "bbox_score": float, "kpts": np.ndarray(26, 3)}, ...]}`
- バリデーション: キーポイント数78、bbox/bbox_score存在チェック。失敗時はスキップしWARNING出力
- JSONファイルが0件の場合: エラーメッセージ出力 + `sys.exit(1)`

#### トラッカー初期化: `init_tracker()`

```python
def init_tracker(device: str) -> DeepOcSort:
    reid_path = Path(__file__).resolve().parent.parent / "osnet_x0_25_msmt17.pt"
    try:
        return DeepOcSort(
            reid_weights=reid_path, device=device,
            half="cuda" in device, max_age=30, w_association_emb=0.0,
        )
    except TypeError:
        print("WARNING: w_association_emb not supported, falling back without it")
        return DeepOcSort(
            reid_weights=reid_path, device=device,
            half="cuda" in device, max_age=30,
        )
```

#### ヘルパー関数

```python
def build_dets(json_people: list[dict]) -> np.ndarray:
    """JSON人物リストからDeep OC-SORT入力用のdets配列を構築する。"""
    if len(json_people) > 0:
        return np.array(
            [[p["bbox"][0], p["bbox"][1], p["bbox"][2], p["bbox"][3],
              p["bbox_score"], 0] for p in json_people],
            dtype=np.float32,
        )
    return np.empty((0, 6), dtype=np.float32)

def parse_tracks(tracks: np.ndarray) -> dict[int, list[float]]:
    """Deep OC-SORT出力をtracked_bboxes辞書に変換する。
    tracks: shape=(N, 5+), 各行=[x1, y1, x2, y2, track_id, ...]
    """
    if len(tracks) > 0:
        return {int(t[4]): t[:4].tolist() for t in tracks}
    return {}
```

#### JSON出力: `build_output_json()`

```python
def build_output_json(
    json_dir: str,
    video_stem: str,
    frame_idx: int,
    json_people: list[dict],
    person_stable_ids: list[int],
) -> dict:
    """入力JSONを読み込み、stable_idを追加した出力JSONを構築する。

    入力JSONが存在する場合: そのまま読み込み、各personに stable_id を追加する。
    入力JSONが存在しない場合（欠番）: {"version": 1.3, "people": []} を返す。
    """
    json_path = os.path.join(json_dir, f"{video_stem}_{frame_idx:06d}.json")

    if os.path.exists(json_path):
        with open(json_path) as f:
            data = json.load(f)
        # 各personに stable_id を追加
        for i, person in enumerate(data.get("people", [])):
            if i < len(person_stable_ids):
                person["stable_id"] = person_stable_ids[i]
            else:
                person["stable_id"] = -1
    else:
        # 欠番フレーム: 空のpeopleで出力
        data = {"version": 1.3, "people": []}

    return data
```

**設計判断**:
- **入力JSONのdictを直接編集する方式を採用**: `halpe26_to_openpose_json()` を使わない。理由: ポストプロセスではJSONの全フィールドをそのまま維持する必要があり、ndarrayへの変換→逆変換は冗長で非効率。直接編集なら入力JSONの全フィールドが確実に保持される
- **入力JSONファイルを2回読む理由**: `load_data()` で1回目（バリデーション + kptsのndarray化）、`build_output_json()` で2回目（元のdictをそのまま取得）。2回目の読み込みはI/Oコストが発生するが、OSのファイルキャッシュにより321Kファイルでも実用的な速度になる。1回で済ませる案（`load_data()` で元dictも保持）はメモリ使用量が倍増するため採用しない

### 1.4.2 stable_idとJSON人物の対応付け（FR-002）

#### 関数: `assign_stable_ids()`

```python
def assign_stable_ids(
    json_people: list[dict],
    tracked_bboxes: dict[int, list[float]],
    stable_ids: dict[int, int],
    iou_threshold: float = 0.5,
) -> list[int]:
    """各JSON人物にstable_idを割り当てる。

    JSON人物 → track_id 方向の貪欲マッチング。
    BB重複除去は完璧ではないため、複数のJSON人物が同一track_idにマッチし、
    全てに同じstable_idが割り当てられることがある。
    IoU最大値が同率の場合はtrack_id最小を優先する。
    """
    result: list[int] = []

    if len(tracked_bboxes) == 0:
        return [-1] * len(json_people)

    for person in json_people:
        best_iou = 0.0
        best_tid = None
        for tid, bbox in tracked_bboxes.items():
            iou = compute_iou(person["bbox"], bbox)
            if iou > best_iou or (iou == best_iou and best_tid is not None and tid < best_tid):
                best_iou = iou
                best_tid = tid
        if best_iou >= iou_threshold and best_tid is not None:
            result.append(stable_ids.get(best_tid, -1))
        else:
            result.append(-1)

    return result
```

#### `match_track_to_json()` 関数

カスタムRe-IDに渡すための track_id → キーポイント マッチング。`test_custom_reid_offline.py` の `match_by_iou()` と同一ロジック・同一方向。

```python
def match_track_to_json(
    tracked_bboxes: dict[int, list[float]],
    json_people: list[dict],
    iou_threshold: float = 0.5,
) -> dict[int, np.ndarray | None]:
    """track_id → キーポイントのマッチング（Re-ID用）。"""
    keypoints_map: dict[int, np.ndarray | None] = {}
    if len(json_people) == 0:
        return {tid: None for tid in tracked_bboxes}
    for track_id, bbox in tracked_bboxes.items():
        best_iou, best_kpts = 0.0, None
        for person in json_people:
            iou = compute_iou(bbox, person["bbox"])
            if iou > best_iou:
                best_iou = iou
                best_kpts = person["kpts"]
        keypoints_map[track_id] = best_kpts if best_iou >= iou_threshold else None
    return keypoints_map
```

#### `compute_iou()` 関数

`test_custom_reid_offline.py` の `compute_iou()` と同一。xyxy形式のbboxを受け取る。

### 1.4.3 出力JSONフォーマット（FR-003）

#### ポストプロセススクリプトでの出力方法

`build_output_json()` で入力JSONのdictを読み込み、各personに `stable_id` キーを直接追加する。`halpe26_to_openpose_json()` は使用しない。

#### `halpe26_to_openpose.py` への変更（将来のパイプライン統合用）

`halpe26_to_openpose_json()` 関数に `stable_ids` オプション引数を追加する。本スクリプトでは使用しないが、将来のfeat-027（パイプライン統合）で使用する。

```python
def halpe26_to_openpose_json(
    all_halpe26: list,
    bbox_scores: list | None = None,
    bboxes: list | None = None,
    stable_ids: list[int] | None = None,
) -> dict:
```

既存の辞書構築パターンに従い、条件付き追加する:

```python
        if bbox_scores is not None:
            person['bbox_score'] = bbox_scores[i]
        if bboxes is not None:
            person['bbox'] = bboxes[i]
        if stable_ids is not None:
            person['stable_id'] = stable_ids[i]
```

- `stable_ids=None` 時: `stable_id` フィールドは出力されない（後方互換）
- `stable_ids` の長さは `all_halpe26` と一致する前提。不一致は呼び出し元のバグであり `IndexError` で即座にクラッシュする（意図的）

### 1.4.4 進捗表示（FR-004）

3000フレームごとに進捗を出力する（ハードコード、CLI引数にしない）。

サマリー出力は1.4.1のメインループ末尾に含まれる（`Total frames`, `Unique stable IDs`, `Processing time`, `Output directory`）。

---

## 1.5 状態遷移

本案件では状態遷移はない。全てのフレームを順次処理するバッチ処理。

---

## 1.6 ファイル・ディレクトリ設計

### 入力ファイル

| パス | 内容 |
|------|------|
| `experiments/input/camSony1_L.mp4` | 長尺動画（321,239フレーム、30fps） |
| `experiments/results/camSony1_L_json/` | 入力HALPE 26 JSON（321,239ファイル） |

### 出力ファイル

| パス | 内容 |
|------|------|
| `experiments/results/camSony1_L_reid_json/` | stable_id付きJSON（動画フレーム数分） |

出力ファイル名: `{video_stem}_{frame_idx:06d}.json`（入力JSONと同一のファイル名パターン）。

---

## 1.7 インターフェース定義

### postprocess_reid.py の主要関数

```python
def load_data(json_dir: str) -> dict[int, list[dict]]:
    """JSONディレクトリから全フレームの人物データを読み込む。
    戻り値: {frame_idx: [{"bbox": list[float], "bbox_score": float,
                          "kpts": np.ndarray(26, 3)}, ...]}
    """

def init_tracker(device: str) -> DeepOcSort:
    """Deep OC-SORTトラッカーを初期化する。"""

def build_dets(json_people: list[dict]) -> np.ndarray:
    """JSON人物リストからdets配列(shape=(N,6))を構築する。"""

def parse_tracks(tracks: np.ndarray) -> dict[int, list[float]]:
    """Deep OC-SORT出力をtracked_bboxes辞書に変換する。"""

def compute_iou(bbox1: list[float], bbox2: list[float]) -> float:
    """xyxy形式のbboxのIoUを計算する。"""

def match_track_to_json(
    tracked_bboxes: dict[int, list[float]],
    json_people: list[dict],
    iou_threshold: float = 0.5,
) -> dict[int, np.ndarray | None]:
    """track_id → キーポイントのマッチング（Re-ID用）。"""

def assign_stable_ids(
    json_people: list[dict],
    tracked_bboxes: dict[int, list[float]],
    stable_ids: dict[int, int],
    iou_threshold: float = 0.5,
) -> list[int]:
    """各JSON人物にstable_idを割り当てる。"""

def build_output_json(
    json_dir: str,
    video_stem: str,
    frame_idx: int,
    json_people: list[dict],
    person_stable_ids: list[int],
) -> dict:
    """入力JSONを読み込み、stable_idを追加した出力JSONを構築する。"""
```

### halpe26_to_openpose.py の変更

```python
def halpe26_to_openpose_json(
    all_halpe26: list,
    bbox_scores: list | None = None,
    bboxes: list | None = None,
    stable_ids: list[int] | None = None,  # 追加
) -> dict:
```

---

## 1.8 ログ・デバッグ設計

| 出力 | 条件 | フォーマット |
|------|------|-------------|
| JSON読み込み件数 | 読み込み完了時 | `Loaded N frames from JSON` |
| 進捗ログ | `frame_idx % 3000 == 0` | `Processing frame {frame_idx:06d}/{total_frames} ({pct:.1f}%)` |
| Delayed Re-ID | 遅延マッチ発動時 | `Delayed Re-ID: ...`（custom_reid.py の既存print） |
| サマリー | 処理完了後 | Total frames, Unique stable IDs, Processing time, Output directory |
| エラー | 動画オープン失敗 | `ERROR: Cannot open video {path}` + sys.exit(1) |
| エラー | 上書き防止 | `ERROR: --out-dir must differ from --json-dir ...` + sys.exit(1) |
| エラー | JSONファイル0件 | `ERROR: No JSON files found in {dir}` + sys.exit(1) |
| WARNING | バリデーション失敗 | `WARNING: Invalid keypoints length ...` / `WARNING: Missing bbox ...` |
| WARNING | TypeErrorフォールバック | `WARNING: w_association_emb not supported ...` |

全て標準出力に出力する（logging モジュールは使用しない。既存の print ベースを維持）。
