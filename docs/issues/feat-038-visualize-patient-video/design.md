# feat-038: pink_track_id / pink_id / track_id 動画可視化 — 機能設計書

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001（CLI） | §4.1 |
| FR-002（動画フレームループ） | §4.2 |
| FR-003（BB 描画） | §4.3 |
| FR-004（キーポイント・スケルトン描画） | §4.4 |
| FR-005（色パレット） | §4.5 |
| FR-006（フレーム番号オーバーレイ） | §4.6 |
| FR-007（進捗表示・サマリ） | §4.7 |

## 2. システム構成

### 2.1 モジュール構成

```
scripts/visualize_patient_video.py
├─ 定数
│   ├─ PROGRESS_INTERVAL_FRAMES = 3000
│   └─ COLOR_GRAY = (128, 128, 128)
├─ 色パレット
│   ├─ _generate_palette(n) → list[tuple[int, int, int]]    (FR-005)
│   └─ get_color(id_value) → tuple[int, int, int]            (FR-005)
├─ 描画関数
│   ├─ draw_person(img, person, color, id_type, kpt_thr)     (FR-003, FR-004)
│   └─ draw_frame_number(img, frame_idx)                      (FR-006)
├─ JSON ヘルパー
│   ├─ detect_json_stem(json_dir) → str
│   └─ load_frame_json(json_path) → list[dict]
├─ フィルタリング
│   └─ filter_people(people, id_type, mode, filter_values) → list[dict]
└─ エントリポイント
    └─ main()                                                  (FR-001, FR-002, FR-007)
```

### 2.2 既存ファイルとの関係

- **流儀元**: `scripts/visualize_tracking.py`（feat-029）の描画関数、色パレット、JSON ヘルパー、フレームループ構造を流用
- **import**: スクリプト先頭で `sys.path.insert(0, os.path.dirname(__file__))` を呼んだ上で `from merge_halpe26 import HALPE26_SKELETON`（`visualize_tracking.py` と同じパス解決方式）
- **変更禁止**: 既存ファイルは一切変更しない

## 3. 技術スタック

| 項目 | 値 |
|------|-----|
| 言語 | Python 3.10.16 |
| OpenCV | 動画読み書き、描画 |
| numpy | キーポイント配列操作 |
| merge_halpe26 | HALPE26_SKELETON の import |

## 4. 各機能の詳細設計

### 4.1 FR-001: CLI

```python
parser = argparse.ArgumentParser(
    description="Visualize BB/skeleton on video with pink_track_id/pink_id/track_id"
)
parser.add_argument("--video", required=True)
parser.add_argument("--json-dir", required=True)
parser.add_argument("--out-dir", default="output")
parser.add_argument("--id-type", default="pink_track_id",
                    choices=["pink_track_id", "pink_id", "track_id"])
parser.add_argument("--mode", default="all", choices=["filter", "all"])
parser.add_argument("--filter-values", type=int, nargs="+", default=[1])
parser.add_argument("--draw-start", type=int, default=0)
parser.add_argument("--draw-end", type=int, default=-1)
parser.add_argument("--kpt-thr", type=float, default=0.3)
```

出力ファイル名: `vis_{id_type}_{mode}_{video_stem}.mp4`

### 4.2 FR-002: フレームループ

```python
while True:
    ret, frame = cap.read()
    if not ret:
        break

    draw_frame_number(frame, frame_idx)

    in_draw_range = (frame_idx >= draw_start) and (draw_end == -1 or frame_idx <= draw_end)

    if in_draw_range:
        json_path = os.path.join(json_dir, f"{json_stem}_{frame_idx:06d}.json")
        people = load_frame_json(json_path)
        visible_people = filter_people(people, id_type, mode, filter_values)
        for person in visible_people:
            id_value = person.get(id_type, -1)
            color = get_color_for_mode(id_value, mode)
            draw_person(frame, person, color, id_type, kpt_thr)

    writer.write(frame)
    frame_idx += 1
```

- JSON を 1 フレームずつ読み込む（メモリ節約、`visualize_tracking.py` と同じ方式）
- 描画範囲外のフレームは JSON 読み込みもスキップ

### 4.3 FR-003: BB 描画

```python
def draw_person(
    img: np.ndarray,
    person: dict,
    color: tuple[int, int, int],
    id_type: str,
    kpt_thr: float,
) -> None:
    bbox = person.get("bbox")
    if bbox is None or len(bbox) != 4:
        return
    x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

    # ID テキスト + bbox_score（略称マッピングで表示を短縮）
    ID_TYPE_SHORT = {"pink_track_id": "ptid", "pink_id": "pid", "track_id": "tid"}
    id_value = person.get(id_type, "?")
    score = person.get("bbox_score", 0)
    short = ID_TYPE_SHORT.get(id_type, id_type)
    label = f"{short}:{id_value} {score:.2f}"
    text_y = y1 - 8 if y1 - 8 > 0 else y1 + 20
    cv2.putText(img, label, (x1, text_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    # キーポイント・スケルトン（FR-004）
    draw_skeleton(img, person, color, kpt_thr)
```

### 4.4 FR-004: キーポイント・スケルトン描画

```python
def draw_skeleton(
    img: np.ndarray,
    person: dict,
    color: tuple[int, int, int],
    kpt_thr: float,
) -> None:
    kpts_flat = person.get("pose_keypoints_2d", [])
    if len(kpts_flat) < 26 * 3:
        return
    kpts = np.array(kpts_flat).reshape(26, 3)

    for i, j in HALPE26_SKELETON:
        if kpts[i, 2] > kpt_thr and kpts[j, 2] > kpt_thr:
            pt1 = (int(kpts[i, 0]), int(kpts[i, 1]))
            pt2 = (int(kpts[j, 0]), int(kpts[j, 1]))
            cv2.line(img, pt1, pt2, color, 2)

    for idx in range(26):
        if kpts[idx, 2] > kpt_thr:
            x, y = int(kpts[idx, 0]), int(kpts[idx, 1])
            cv2.circle(img, (x, y), 4, color, -1)
```

`visualize_tracking.py` の `draw_halpe26_colored` と同一ロジック。

### 4.5 FR-005: 色パレット

```python
def _generate_palette(n: int = 20) -> list[tuple[int, int, int]]:
    palette = []
    for i in range(n):
        h = int(180 * i / n)
        hsv = np.array([[[h, 255, 255]]], dtype=np.uint8)
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        palette.append(tuple(int(c) for c in bgr[0, 0]))
    return palette

COLOR_PALETTE = _generate_palette(20)
COLOR_GRAY = (128, 128, 128)
COLOR_FILTER = (0, 255, 0)  # filter モード用の固定色（緑）

def get_color_for_mode(id_value: int, mode: str) -> tuple[int, int, int]:
    if mode == "filter":
        return COLOR_FILTER
    if id_value < 0:
        return COLOR_GRAY
    return COLOR_PALETTE[id_value % len(COLOR_PALETTE)]
```

### 4.6 FR-006: フレーム番号オーバーレイ

```python
def draw_frame_number(img: np.ndarray, frame_idx: int) -> None:
    cv2.putText(img, f"Frame: {frame_idx}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
```

### 4.7 FR-007: 進捗表示・サマリ

`visualize_tracking.py` と同じ方式。3000 フレームごとに進捗表示、処理完了後にサマリ（総フレーム数、処理時間、fps、出力パス）。

### 4.8 JSON ヘルパー

#### detect_json_stem

`visualize_tracking.py` と同一ロジック。`json_dir` 内の最初の JSON ファイルから stem（`{video_stem}` 部分）を正規表現 `^(.+)_\d{6}\.json$` で抽出する。マッチするファイルが 0 件の場合は `ERROR: No valid JSON files found in {json_dir}` を出力して `sys.exit(1)` する。

```python
def detect_json_stem(json_dir: str) -> str:
    json_path = Path(json_dir)
    pattern = re.compile(r"^(.+)_\d{6}\.json$")
    for f in sorted(json_path.glob("*.json")):
        m = pattern.match(f.name)
        if m:
            return m.group(1)
    print(f"ERROR: No valid JSON files found in {json_dir}")
    sys.exit(1)
```

#### load_frame_json

1 フレーム分の JSON を読み込む。ファイルが存在しない場合は空リストを返す（素通しフレーム扱い）。`JSONDecodeError` 時は WARNING を出し空リストを返す。

```python
def load_frame_json(json_path: str) -> list[dict]:
    if not os.path.exists(json_path):
        return []
    try:
        with open(json_path) as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print(f"WARNING: Failed to parse {json_path}")
        return []
    return data.get("people", [])
```

### 4.9 filter_people

ID フィールドの値に基づいて描画対象の人物をフィルタする。

```python
def filter_people(
    people: list[dict],
    id_type: str,
    mode: str,
    filter_values: list[int],
) -> list[dict]:
    if mode == "all":
        return people
    # mode == "filter": 指定 ID 値を持つ BB のみ
    result = []
    for person in people:
        id_val = person.get(id_type)
        # ID フィールドが存在しない（None）場合はスキップ
        if id_val is None:
            continue
        if id_val in filter_values:
            result.append(person)
    return result
```

- `mode == "all"`: 全 BB をそのまま返す
- `mode == "filter"`: `person.get(id_type)` が `filter_values` に含まれる BB のみ返す
- ID フィールドが存在しない BB（`get` が `None`）はフィルタ対象外（スキップ）

## 5. インターフェース定義

```python
def _generate_palette(n: int = 20) -> list[tuple[int, int, int]]: ...
def get_color_for_mode(id_value: int, mode: str) -> tuple[int, int, int]: ...
def detect_json_stem(json_dir: str) -> str: ...
def load_frame_json(json_path: str) -> list[dict]: ...
def filter_people(people: list[dict], id_type: str, mode: str, filter_values: list[int]) -> list[dict]: ...
def draw_person(img, person: dict, color, id_type: str, kpt_thr: float) -> None: ...
def draw_skeleton(img, person: dict, color, kpt_thr: float) -> None: ...
def draw_frame_number(img, frame_idx: int) -> None: ...
def main() -> None: ...
```

## 6. 設計判断の記録（ADR）

### ADR-001: 1 フレームずつ JSON 読み込み（全件メモリ読み込みではなく）

- **採用案**: フレームループ内で 1 フレーム分の JSON を都度読み込む
- **却下案**: 全 JSON を `load_json_frames` で一括読み込み
- **理由**: (1) `visualize_tracking.py` と同じ方式。(2) 動画可視化は逐次処理であり、パス 2 のような全件参照は不要。(3) 321K フレーム分の JSON を全件読み込むとメモリ 2〜3 GB を消費する。動画 I/O がボトルネックであり JSON の 1 件読み込みの I/O コストは相対的に小さい

### ADR-002: `draw_person` に BB + スケルトンを統合

- **採用案**: `draw_person` 1 関数で BB 描画 + テキスト + スケルトン描画を一括実行
- **却下案**: `draw_bbox` と `draw_skeleton` を分離して呼び出し側で組み合わせる
- **理由**: 描画要素のオン/オフ切り替えの要求がないため、1 関数にまとめた方が呼び出しコードが簡潔。将来要素ごとのオン/オフが必要になったら分離すればよい

### ADR-003: filter モードの固定色

- **採用案**: filter モードでは全描画対象 BB を固定色（緑）で描画
- **却下案**: filter モードでも ID 値に応じた色分けを行う
- **理由**: filter モードは「この ID 値の BB だけ見たい」という目的なので、全 BB が同一色で問題ない。色分けは all モードの責務
