# feat-029: トラッキング付き動画可視化 — 機能設計書

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|----------------|
| FR-001 | 4.1 メインループ、4.2 JSONフィルタリング、4.6 スケルトン描画 |
| FR-002 | 4.1 メインループ、4.2 JSONフィルタリング、4.3 色割り当て |
| FR-003 | 4.4 BB描画 |
| FR-004 | 4.5 stable_idテキスト描画 |
| FR-005 | 4.7 出力ファイル命名 |
| FR-006 | 4.9 進捗表示 |

## 2. システム構成

### モジュール構成

```
scripts/
├── visualize_tracking.py      # 新規: メインスクリプト（本設計の対象）
└── merge_halpe26.py           # 既存: HALPE26_SKELETON をインポート
```

### 依存関係

- `visualize_tracking.py` → `merge_halpe26.py`（`HALPE26_SKELETON` のみインポート）
- インポート方法: `sys.path.insert(0, os.path.dirname(__file__))` の後に `from merge_halpe26 import HALPE26_SKELETON`（既存の `visualize_halpe26_video.py` と同一パターン）
- 描画関数（`draw_halpe26_colored`, `draw_bbox_colored`）は `visualize_tracking.py` 内に定義する（色のカスタマイズが必要なため、既存の `draw_halpe26` / `draw_bbox` は使用しない）

## 3. 技術スタック

- **言語**: Python 3.10.16
- **ライブラリ**: OpenCV（cv2）、numpy、標準ライブラリ（json, argparse, pathlib, time, re, os, sys）
- **新規ライブラリ追加**: なし

### モジュールレベルのインポート文

```python
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from merge_halpe26 import HALPE26_SKELETON  # noqa: E402
```

## 4. 各機能の詳細設計

### 4.1 メインループ（FR-001, FR-002）

#### データフロー

```
入力:
  --video: str (MP4ファイルパス)
  --json-dir: str (stable_id付きJSONディレクトリパス)
  --ids: list[int] | None (指定stable_idリスト。Noneなら全体モード)
  --out-dir: str (出力ディレクトリ、デフォルト "output")
  --kpt-thr: float (キーポイント信頼度閾値、0.0〜1.0、デフォルト 0.3)

処理:
  1. 動画を開く（VideoCapture）
  2. 出力動画を作成（VideoWriter）
  3. フレームごとにループ:
     a. フレーム読み込み
     b. 対応するJSONファイルを読み込む
     c. JSONの people を走査し、描画対象を選別
     d. 描画対象の人物について BB + スケルトン + IDテキストを描画
     e. フレームを書き込み
  4. リリース

出力:
  MP4動画ファイル
```

#### 処理ロジック（擬似コード）

```python
def main():
    args = parse_args()

    # json-dir 存在チェック
    if not os.path.isdir(args.json_dir):
        print(f"ERROR: JSON directory not found: {args.json_dir}")
        sys.exit(1)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"ERROR: Failed to open video: {args.video}")
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_stem = Path(args.video).stem

    # 出力ディレクトリ自動作成
    os.makedirs(args.out_dir, exist_ok=True)

    # 出力パスを構築（FR-005参照）
    out_path = build_output_path(args)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

    # JSONファイル名のstemを取得（最初のJSONファイルから）
    json_stem = detect_json_stem(args.json_dir)

    mode = "filter" if args.ids is not None else "all"
    print(f"Video: {args.video} ({total_frames} frames, {fps} fps)")
    print(f"JSON dir: {args.json_dir} (stem: {json_stem})")
    print(f"Mode: {mode}, IDs: {args.ids}, kpt_thr: {args.kpt_thr}")

    start_time = time.time()
    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # JSONを読み込む
        json_path = os.path.join(args.json_dir, f"{json_stem}_{frame_idx:06d}.json")
        people = load_frame_json(json_path)  # list[dict] or []

        # 描画対象をフィルタ
        targets = filter_people(people, args.ids)  # FR-001/FR-002

        # 描画
        vis_frame = frame.copy()
        for person in targets:
            sid = person.get("stable_id", -1)
            color = get_color(sid)
            bbox = person.get("bbox")
            kpts_flat = person.get("pose_keypoints_2d", [])

            # BB描画（bboxがある場合のみ）
            if bbox is not None and len(bbox) >= 4:
                draw_bbox_colored(vis_frame, bbox, color, sid)

            # スケルトン描画（pose_keypoints_2dが78要素の場合のみ）
            if len(kpts_flat) == 78:
                kpts = np.array(kpts_flat, dtype=np.float32).reshape(26, 3)
                draw_halpe26_colored(vis_frame, kpts, color, args.kpt_thr)

        writer.write(vis_frame)

        # 進捗表示（FR-006）
        if frame_idx % 1000 == 0:
            print(f"Processing frame {frame_idx}/{total_frames} ...")
        frame_idx += 1

    cap.release()
    writer.release()

    elapsed = time.time() - start_time
    print(f"Done: {out_path} ({elapsed:.1f}s)")
```

### 4.2 JSONフィルタリング（FR-001）

#### データフロー

- 入力: `people`（list[dict]）、`target_ids`（list[int] | None）
- 出力: `targets`（list[dict]）— 描画対象の人物リスト

#### 処理ロジック

```python
def filter_people(people: list[dict], target_ids: list[int] | None) -> list[dict]:
    """描画対象の人物をフィルタする。

    Args:
        people: JSONの people リスト
        target_ids: 指定stable_idリスト。Noneなら全体モード

    Returns:
        描画対象の人物リスト
    """
    result = []
    for person in people:
        sid = person.get("stable_id", -1)
        if target_ids is None:
            # 全体モード: stable_id=-1 も含めて全て描画
            result.append(person)
        else:
            # フィルタモード: 指定IDのみ。-1は常に除外
            if sid != -1 and sid in target_ids:
                result.append(person)
    return result
```

#### 境界条件

- `people` が空リスト: 空リストを返す（描画なし）
- `target_ids` が空リスト: 空リストを返す（誰も描画しない）
- `stable_id` フィールドが存在しないperson: `sid = -1` として扱う

### 4.3 色割り当て（FR-002, FR-003）

#### 処理ロジック

stable_idに対して決定論的に色を割り当てる。HSV色空間で色相を均等分割し、彩度・明度を固定する。

```python
# モジュールレベル定数として _generate_palette(20) の結果を保持する
COLOR_PALETTE: list[tuple[int, int, int]] = _generate_palette(20)

GRAY = (128, 128, 128)  # stable_id=-1 用

def get_color(stable_id: int) -> tuple[int, int, int]:
    """stable_idからBGR色を返す。"""
    if stable_id < 0:
        return GRAY
    return COLOR_PALETTE[stable_id % len(COLOR_PALETTE)]
```

#### 設計判断

- **採用案**: HSV色相均等分割の20色パレット。stable_id % 20 でインデックスする。20色は近傍のstable_idが同色にならないよう十分な間隔を提供する。845ユニークID（camSony1_L）では衝突が発生するが、同一フレーム内の人物数は少ないため目視検証には十分
- **却下案A**: ランダム色生成 → 同一stable_idが実行ごとに異なる色になるため不採用
- **却下案B**: 既存の `HALPE26_COLORS` を流用 → 3色（左右+中央）しかなく、人物区別に不向き

#### カラーパレット生成コード

```python
def _generate_palette(n: int = 20) -> list[tuple[int, int, int]]:
    """HSV色相均等分割でn色のBGRパレットを生成する。"""
    palette = []
    for i in range(n):
        h = int(180 * i / n)  # OpenCV HSVのHは0-179
        hsv = np.array([[[h, 255, 255]]], dtype=np.uint8)
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        palette.append(tuple(int(c) for c in bgr[0, 0]))
    return palette
```

### 4.4 BB描画（FR-003）

#### データフロー

- 入力: `img`（np.ndarray, BGR）、`bbox`（list[float], [x1, y1, x2, y2]）、`color`（tuple[int, int, int], BGR）、`stable_id`（int）
- 出力: `img`（np.ndarray, BGR）— BB矩形とIDテキストが描画された画像

#### 処理ロジック

```python
def draw_bbox_colored(
    img: np.ndarray,
    bbox: list[float],
    color: tuple[int, int, int],
    stable_id: int,
    thickness: int = 2,
) -> np.ndarray:
    """BBとstable_idテキストを描画する。"""
    x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)
    label = f"ID:{stable_id}"
    # テキスト位置: y1-8 が画面外（負値）になる場合はフォント高さ分下にずらす
    text_y = y1 - 8 if y1 - 8 > 0 else y1 + 20
    cv2.putText(img, label, (x1, text_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return img
```

注意: `draw_bbox` は既存の `merge_halpe26.py` にあるが、スコア表示が不要でstable_id表示が必要なため、新規関数として実装する。引数の `img` は破壊的に変更する（コピーしない）。呼び出し元の `main()` で `frame.copy()` 済みのため。

### 4.5 stable_idテキスト描画（FR-004）

FR-003の `draw_bbox_colored` 内で実装する（4.4参照）。独立関数にはしない。

- フォント: `cv2.FONT_HERSHEY_SIMPLEX`
- スケール: 0.6
- 太さ: 2
- 位置: BB左上 `(x1, y1 - 8)`。`y1 - 8` が0以下の場合は `(x1, y1 + 20)` にフォールバック
- テキスト形式: `ID:{stable_id}`（例: `ID:1`）

### 4.6 スケルトン描画

#### 処理ロジック

```python
def draw_halpe26_colored(
    img: np.ndarray,
    keypoints: np.ndarray,
    color: tuple[int, int, int],
    kpt_thr: float = 0.3,
) -> np.ndarray:
    """HALPE 26スケルトンを指定色で描画する。

    Args:
        img: BGR画像（破壊的に変更）
        keypoints: shape=(26, 3), [x, y, confidence]
        color: BGR色
        kpt_thr: 信頼度閾値。これ以下のキーポイントは描画しない

    Returns:
        描画済み画像
    """
    # スケルトン線を描画（線の太さ2ピクセル、キーポイント円の半径4ピクセルは既存 draw_halpe26 と同一値）
    for i, j in HALPE26_SKELETON:
        if keypoints[i, 2] > kpt_thr and keypoints[j, 2] > kpt_thr:
            pt1 = (int(keypoints[i, 0]), int(keypoints[i, 1]))
            pt2 = (int(keypoints[j, 0]), int(keypoints[j, 1]))
            cv2.line(img, pt1, pt2, color, 2)

    # キーポイント円を描画
    for idx in range(26):
        if keypoints[idx, 2] > kpt_thr:
            x, y = int(keypoints[idx, 0]), int(keypoints[idx, 1])
            cv2.circle(img, (x, y), 4, color, -1)

    return img
```

#### 設計判断

- **採用案**: キーポイント番号テキストは描画しない（既存の `draw_halpe26` はキーポイント番号を表示するが、トラッキング可視化では不要。視認性を優先）
- **却下案**: 既存 `draw_halpe26` をそのまま使用 → 色のカスタマイズが引数に無く、キーポイント番号テキストも不要なため新規実装

### 4.7 出力ファイル命名（FR-005）

#### 処理ロジック

```python
def build_output_path(args) -> str:
    """出力ファイルパスを構築する。"""
    video_stem = Path(args.video).stem
    if args.ids is not None:
        ids_str = "_".join(str(i) for i in args.ids)
        filename = f"vis_tracking_{video_stem}_ids_{ids_str}.mp4"
    else:
        filename = f"vis_tracking_{video_stem}_all.mp4"
    return os.path.join(args.out_dir, filename)
```

### 4.8 JSONファイル名stem検出

#### 処理ロジック

json-dir内のJSONファイルは `{stem}_{frame_idx:06d}.json` の形式。stemが動画ファイル名と一致するとは限らない（例: 動画=`camSony1_L.mp4` でJSON stem=`camSony1_L`）。アルファベット順ソートで最初のJSONファイルからstemを自動検出する。

**前提条件**: json-dir には単一動画のJSONファイルのみが格納されていること。複数のstemが混在している場合、最初にヒットしたstemのみ使用される。

json-dirの存在チェックはメインループ（4.1）で先行して行うため、この関数内では行わない。

```python
def detect_json_stem(json_dir: str) -> str:
    """json-dir内の最初のJSONファイルからstemを検出する。

    ファイル名パターン: {stem}_{6桁数字}.json
    例: camSony1_L_000000.json → stem = "camSony1_L"

    ソート順: PosixPathのアルファベット順（sorted）
    """
    json_path = Path(json_dir)
    pattern = re.compile(r"^(.+)_\d{6}\.json$")
    for f in sorted(json_path.glob("*.json")):
        m = pattern.match(f.name)
        if m:
            return m.group(1)
    print(f"ERROR: No valid JSON files found in {json_dir}")
    sys.exit(1)
```

### 4.9 進捗表示（FR-006）

```python
if frame_idx % 1000 == 0:
    print(f"Processing frame {frame_idx}/{total_frames} ...")

# 完了時
elapsed = time.time() - start_time
print(f"Done: {out_path} ({elapsed:.1f}s)")
```

### 4.10 JSON読み込み

#### 処理ロジック

```python
def load_frame_json(json_path: str) -> list[dict]:
    """1フレーム分のJSONを読み込む。

    Args:
        json_path: JSONファイルパス

    Returns:
        people リスト。ファイルが存在しない場合は空リスト
    """
    if not os.path.exists(json_path):
        return []
    try:
        with open(json_path) as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print(f"WARNING: Failed to parse {json_path}, treating as 0 people")
        return []
    return data.get("people", [])
```

#### エラーハンドリング

- JSONファイルが存在しない: 空リストを返す（描画なし。フレーム欠番は正常ケース）
- JSONパースエラー: `json.JSONDecodeError` をキャッチし、WARNING出力して空リストを返す

#### 境界条件

- `people` が空: 描画なしで元フレームをそのまま書き込む
- `bbox` フィールドが存在しないperson: メインループ内の `person.get("bbox")` が None を返し、BB描画をスキップする（4.1の擬似コード参照）。WARNING出力はしない（サイレントスキップ）
- `pose_keypoints_2d` の長さが78でない: メインループ内の `len(kpts_flat) == 78` チェックでスケルトン描画をスキップする（4.1の擬似コード参照）。WARNING出力はしない（サイレントスキップ）
- `stable_id` フィールドが存在しないJSON（`postprocess_reid.py` 未処理のJSON）: `person.get("stable_id", -1)` で -1 にフォールバックする。全体モードではグレーで描画、フィルタモードでは描画対象外となる

#### 動画フレーム数とJSONファイル数の不一致

- 動画フレーム数 > JSONファイル数: 動画フレーム数を基準とする。JSONが存在しないフレームは `load_frame_json` が空リストを返し、描画なしで出力する
- 動画フレーム数 < JSONファイル数: 動画フレーム数を基準とする。超過するJSONは無視する（`while cap.isOpened()` + `if not ret: break` で自然終了）

## 5. ファイル・ディレクトリ設計

### 入力

- 動画: 任意のMP4ファイル
- JSONディレクトリ: `{stem}_{frame_idx:06d}.json` 形式のファイルが格納されたディレクトリ

### 出力

- `{out-dir}/vis_tracking_{video_stem}_ids_{id1}_{id2}.mp4`（フィルタモード）
- `{out-dir}/vis_tracking_{video_stem}_all.mp4`（全体モード）

## 6. インターフェース定義

### CLI引数

```python
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize tracking results with stable_id color coding")
    parser.add_argument("--video", type=str, required=True,
                        help="Input video path")
    parser.add_argument("--json-dir", type=str, required=True,
                        help="Directory of stable_id-annotated JSON files")
    parser.add_argument("--ids", type=int, nargs="+", default=None,
                        help="stable_ids to draw (omit for all)")
    parser.add_argument("--out-dir", type=str, default="output",
                        help="Output directory")
    parser.add_argument("--kpt-thr", type=float, default=0.3,
                        help="Keypoint confidence threshold (0.0-1.0)")
    return parser.parse_args()
```

### 公開関数

| 関数 | 引数 | 戻り値 | 責務 |
|------|------|--------|------|
| `main()` | なし（argparse） | なし | エントリポイント |
| `detect_json_stem(json_dir: str)` | JSONディレクトリパス | str | JSONファイル名stemの自動検出 |
| `load_frame_json(json_path: str)` | JSONファイルパス | list[dict] | 1フレーム分のJSON読み込み |
| `filter_people(people, target_ids)` | list[dict], list[int]\|None | list[dict] | 描画対象フィルタ |
| `get_color(stable_id: int)` | int | tuple[int,int,int] | stable_id→BGR色 |
| `draw_bbox_colored(img, bbox, color, stable_id)` | ndarray, list, tuple, int | ndarray | BB+IDテキスト描画 |
| `draw_halpe26_colored(img, kpts, color, kpt_thr)` | ndarray, ndarray, tuple, float | ndarray | スケルトン描画 |
| `build_output_path(args)` | Namespace | str | 出力パス構築 |

注: `_generate_palette(n)` はモジュール内部関数として実装する。公開APIではないため上表には含めない。

## 7. ログ・デバッグ設計

- INFO: 処理開始時に動画パス・JSONディレクトリ・モード・総フレーム数を `print` で出力
- INFO: 1000フレームごとに進捗表示（frame_idx=0 を含む）
- INFO: 完了時に出力パスと処理時間を表示
- WARNING: JSONパースエラー（`load_frame_json` 内で出力）
- サイレントスキップ（WARNING出力なし）: bbox欠損、keypoints長不正、stable_id欠損
