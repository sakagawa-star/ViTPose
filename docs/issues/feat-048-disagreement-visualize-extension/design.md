# feat-048 機能設計書: 不一致フレーム可視化の情報再設計

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001（JSON 直読み） | §4.1 |
| FR-002（サンプリング） | §4.2 |
| FR-003（人物 BB 描画） | §4.3 |
| FR-004（idx ラベル） | §4.4 |
| FR-005（ROI 矩形描画） | §4.5 |
| FR-006（胴体 4 点描画） | §4.6 |
| FR-007（上部診断ラベル） | §4.7 |
| FR-008（シーク失敗） | §4.8 |
| FR-009（サマリ統計） | §4.9 |
| NFR-001（性能） | §6 |
| NFR-002（対応環境） | §3 |
| NFR-003（既存スクリプト整合性） | §2.2 / §9 |

## 2. システム構成

### 2.1 モジュール構成

```
scripts/
├─ visualize_disagreement_frames.py  # 全面書き直し
├─ compare_roi_modes.py              # 変更なし
└─ postprocess_pink_id.py            # 変更なし
```

`visualize_disagreement_frames.py` は CSV 読み込み版を完全に置き換える。feat-047 / feat-048 初版で実装した CSV パース・描画ロジックは破棄。

### 2.2 依存関係

新規 import 候補:
- `postprocess_pink_id` から `build_keypoint_rect_roi` を import（FR-007 で `fail_kpt` / `fail_area` の再判定に使用）
- 既存依存（`cv2`, `numpy` は描画上必要なら使う、その他標準 `json` / `argparse` / `os` / `sys` / `pathlib` / `re`）

ライブラリ追加なし。

### 2.3 共通定数

```python
# HALPE26 胴体 4 点（feat-046 と同値）
TORSO_KEYPOINT_INDICES = (5, 6, 11, 12)
TORSO_KPT_LABELS = ("LS", "RS", "LH", "RH")

# 信頼度閾値・最小 ROI 面積は CLI で受け取る（kp モード JSON 生成時と同値を渡すため）
# - --kpt-conf-min (デフォルト 0.3)
# - --min-roi-area (デフォルト 200)

# 色定数 (BGR)
RED = (0, 0, 255)            # bb 選択人物 BB
BLUE = (255, 0, 0)           # kp 選択人物 BB
RED_DARK = (0, 0, 200)       # bb 選択胴体キーポイント
BLUE_DARK = (200, 100, 0)    # kp 選択胴体キーポイント
ROI_COLOR_OK = (0, 255, 255)        # ROI ok: 黄色
ROI_COLOR_FAIL_AREA = (0, 165, 255)  # ROI fail_area: オレンジ（試行矩形を残す）
LABEL_TEXT_BLACK = (0, 0, 0)
LABEL_TEXT_WHITE = (255, 255, 255)

# 描画サイズ
BB_LINE_WIDTH = 2
ROI_LINE_WIDTH = 2
KPT_RADIUS = 6
KPT_CROSS_HALF = 6           # 低信頼点の × マークの半長
TOP_LABEL_FONT_SCALE = 0.6
IDX_LABEL_FONT_SCALE = 0.55
KPT_LABEL_FONT_SCALE = 0.4
```

## 3. 技術スタック

既存と同一（Python 3.10.16、uv、OpenCV、numpy、CPU 実行）。変更なし。

## 4. 各機能の詳細設計

### 4.1 FR-001: JSON ディレクトリ直読み

#### 4.1.1 JSON 読み込みヘルパ

```python
PATTERN = re.compile(r"_(\d{6})\.json$")

def load_all_json(json_dir: str) -> dict[int, dict]:
    """JSON ディレクトリから {frame_idx: 全 content} を返す。"""
    result = {}
    for fname in os.listdir(json_dir):
        m = PATTERN.search(fname)
        if not m:
            continue
        with open(os.path.join(json_dir, fname)) as f:
            result[int(m.group(1))] = json.load(f)
    return result
```

各 JSON の `people` 配列を生 dict のまま保持。

#### 4.1.2 disagreement 判定ロジック

```python
def find_pink_person(content: dict) -> dict | None:
    """pink_id == 1 の person を返す。なければ None。"""
    for p in content.get("people", []):
        if p.get("pink_id") == 1:
            return p
    return None

def classify(bb_idx, kp_idx) -> str | None:
    if bb_idx is None and kp_idx is None:
        return None  # both_none, スキップ
    if bb_idx is None:
        return "only_kp"
    if kp_idx is None:
        return "only_bb"
    if bb_idx != kp_idx:
        return "both_selected_different"
    return None  # 一致, スキップ
```

#### 4.1.3 不一致フレーム列挙

```python
bb_data = load_all_json(args.bb_json_dir)
kp_data = load_all_json(args.kp_json_dir)
common_frames = sorted(set(bb_data) & set(kp_data))
only_bb_files = set(bb_data) - set(kp_data)
only_kp_files = set(kp_data) - set(bb_data)
if only_bb_files or only_kp_files:
    print(f"WARNING: bb-only frames={len(only_bb_files)}, kp-only frames={len(only_kp_files)}",
          file=sys.stderr)

disagreement_frames = []  # [(frame_idx, dtype), ...]
counts = {"both_selected_different": 0, "only_bb": 0, "only_kp": 0}
for f in common_frames:
    bb_p = find_pink_person(bb_data[f])
    kp_p = find_pink_person(kp_data[f])
    bb_idx = bb_p["bb_index"] if bb_p else None
    kp_idx = kp_p["bb_index"] if kp_p else None
    dtype = classify(bb_idx, kp_idx)
    if dtype is None:
        continue
    disagreement_frames.append((f, dtype))
    counts[dtype] += 1
```

#### 4.1.4 ディレクトリ存在チェック

main 冒頭:
```python
for d in [args.bb_json_dir, args.kp_json_dir]:
    if not os.path.isdir(d):
        print(f"ERROR: JSON directory not found: {d}", file=sys.stderr)
        sys.exit(1)
```

### 4.2 FR-002: サンプリング

```python
def _positive_int(s: str) -> int:
    v = int(s)
    if v < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {v}")
    return v

def _check_conf(v: str) -> float:
    fv = float(v)
    if not (0.0 <= fv <= 1.0):
        raise argparse.ArgumentTypeError(
            f"kpt-conf-min must be in [0.0, 1.0], got {fv}"
        )
    return fv

def _check_area(v: str) -> int:
    iv = int(v)
    if iv < 1:
        raise argparse.ArgumentTypeError(f"min-roi-area must be >= 1, got {iv}")
    return iv

parser.add_argument("--max-samples", type=_positive_int, default=50)
parser.add_argument("--all", action="store_true")
parser.add_argument("--kpt-conf-min", type=_check_conf, default=0.3,
                    help="ROI 状態再計算のキーポイント信頼度閾値 "
                         "(kp モード JSON 生成時と同値を渡すこと)")
parser.add_argument("--min-roi-area", type=_check_area, default=200,
                    help="ROI 状態再計算の最低面積 "
                         "(kp モード JSON 生成時と同値を渡すこと)")

original_count = len(disagreement_frames)
if not args.all and original_count > args.max_samples:
    step = original_count / args.max_samples
    indices = [int(i * step) for i in range(args.max_samples)]
    disagreement_frames = [disagreement_frames[i] for i in indices]
```

feat-047 と同等の均等サンプリング。

### 4.3 FR-003: 人物 BB 描画

```python
def draw_person_bbox(frame, bbox, color):
    if bbox is None or len(bbox) != 4:
        return
    x1, y1, x2, y2 = (int(round(v)) for v in bbox)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, BB_LINE_WIDTH)
```

呼び出し:
```python
if dtype in ("both_selected_different", "only_bb") and bb_person is not None:
    draw_person_bbox(frame, bb_person.get("bbox"), RED)
if dtype in ("both_selected_different", "only_kp") and kp_person is not None:
    draw_person_bbox(frame, kp_person.get("bbox"), BLUE)
```

### 4.4 FR-004: idx ラベル

#### 4.4.1 位置決定

BB 右上角の外側に配置。具体的には:
- 基準位置: `(x2 + 4, y1 + 14)`
- 画像幅 W に対し `x2 + 50 > W` なら画像内側に折り返し `(x2 - 50, y1 + 14)`

```python
def draw_idx_label(frame, bbox_i, idx_str, color, img_w):
    x1, y1, x2, y2 = bbox_i
    label_w_estimate = 50  # 50 px 程度
    if x2 + label_w_estimate < img_w:
        org = (x2 + 4, y1 + 14)
    else:
        org = (max(x2 - label_w_estimate, 0), y1 + 14)
    cv2.putText(frame, idx_str, org, cv2.FONT_HERSHEY_SIMPLEX,
                IDX_LABEL_FONT_SCALE, LABEL_TEXT_BLACK, 3)
    cv2.putText(frame, idx_str, org, cv2.FONT_HERSHEY_SIMPLEX,
                IDX_LABEL_FONT_SCALE, color, 1)
```

#### 4.4.2 重なり回避の根拠

BB 右上角外側に置くことで、人物 BB 内のキーポイント（HALPE26 5/6/11/12 は胴体部分、概ね BB 中央〜下半分）と物理的に離れる。BB 上部に頭部キーポイントがあるケースでも本案件の描画対象 4 点には含まれないため衝突しない。

### 4.5 FR-005: ROI 矩形描画（試行矩形を含めて常に描く）

#### 4.5.1 ROI 取得経路

##### bb_index 線形検索

```python
def find_person_by_bb_index(content: dict, bb_idx: int) -> dict | None:
    """content の people から bb_index フィールド一致 person を線形検索。

    bb モードと kp モードで people 配列順序が同一とは保証されないため、
    配列インデックス直参照ではなく bb_index フィールドで引く。
    """
    if bb_idx is None:
        return None
    for p in content.get("people", []):
        if p.get("bb_index") == bb_idx:
            return p
    return None
```

##### 試行 ROI 構築（area チェック省略版）

`build_keypoint_rect_roi`（feat-046）の area チェックを省略した版を visualize 内に新規ヘルパとして用意。`clip_bbox` を再利用して丸め基準を揃える:

```python
from postprocess_pink_id import build_keypoint_rect_roi, clip_bbox

def build_attempted_roi(
    kpts_flat, width: int, height: int, conf_min: float, area_min: int,
) -> tuple[tuple[int, int, int, int] | None, str]:
    """ROI 構築を試みた結果を返す。area チェックは判定のみで矩形は破棄しない。

    Returns:
        (roi_bbox, status):
            roi_bbox = (x1, y1, x2, y2) または None
            status ∈ {"ok", "fail_kpt", "fail_area"}
        - "ok" / "fail_area": roi_bbox は非 None（試行矩形を返す）
        - "fail_kpt": roi_bbox は None（信頼点 2 個未満で矩形構築不能）

    feat-046 の build_keypoint_rect_roi との差分:
        本関数は fail_area でも矩形を返す。可視化目的で「試行された矩形」を
        画面に残す必要があるため。pink_ratio の計算には使わない。
    """
    if kpts_flat is None or len(kpts_flat) < 78:
        return None, "fail_kpt"
    candidates = []
    for idx in TORSO_KEYPOINT_INDICES:
        base = idx * 3
        x, y, c = kpts_flat[base], kpts_flat[base + 1], kpts_flat[base + 2]
        if c >= conf_min:
            candidates.append((x, y))
    if len(candidates) < 2:
        return None, "fail_kpt"
    xs = [p[0] for p in candidates]
    ys = [p[1] for p in candidates]
    x1, y1, x2, y2 = clip_bbox(
        (min(xs), min(ys), max(xs), max(ys)), width, height,
    )
    if x2 <= x1 or y2 <= y1:
        return None, "fail_kpt"
    area = (x2 - x1) * (y2 - y1)
    # clip_bbox は int タプルを返す（feat-046 で確認済み）。dedup の set 比較で
    # ハッシュ不一致を起こさないため、ここでも明示的に int 化して返す。
    rect = (int(x1), int(y1), int(x2), int(y2))
    if area < area_min:
        return rect, "fail_area"  # 矩形は返す
    return rect, "ok"
```

##### 対象人物の取得と試行 ROI 算出

各 disagreement フレームについて、以下 2 人分の試行 ROI を取得:

```python
# bb 選択人物の kp 側対応 person
bb_idx_val = bb_person["bb_index"] if bb_person else None
bb_owner_person = (
    find_person_by_bb_index(kp_data[f], bb_idx_val)
    if bb_idx_val is not None else None
)

# kp 選択人物
kp_idx_val = kp_person["bb_index"] if kp_person else None
# kp_person 自体を直接使う（pink_id=1 で find_pink_person 済み）

def get_attempted_roi_for_person(person, img_w, img_h, kpt_conf_min, min_roi_area):
    if person is None:
        return None, "not_present"
    return build_attempted_roi(
        person.get("pose_keypoints_2d", []),
        img_w, img_h, kpt_conf_min, min_roi_area,
    )

bb_owner_roi, bb_owner_status = get_attempted_roi_for_person(
    bb_owner_person, img_w, img_h, args.kpt_conf_min, args.min_roi_area
)
kp_owner_roi, kp_owner_status = get_attempted_roi_for_person(
    kp_person, img_w, img_h, args.kpt_conf_min, args.min_roi_area
)
```

`bb_owner_status = "not_present"` は bb 選択人物が kp 側 JSON に存在しない異常系。**WARNING 出力は §4.7.2 `build_top_labels` 内に一本化**（同一フレーム同一 bb_index で 2 回出ないよう、§4.5.1 側では出さない）。

#### 4.5.2 描画

```python
def draw_roi(frame, roi_bbox_i, status: str):
    """状態に応じた色で ROI 矩形を描画。

    status="ok"        → 黄色
    status="fail_area" → オレンジ（試行矩形を残す、feat-048 v2 改訂の追加要件）
    呼び出し側で roi_bbox_i is None（fail_kpt / not_present）は除外済み。
    """
    if roi_bbox_i is None:
        return
    color = ROI_COLOR_OK if status == "ok" else ROI_COLOR_FAIL_AREA
    cv2.rectangle(
        frame,
        (roi_bbox_i[0], roi_bbox_i[1]),
        (roi_bbox_i[2], roi_bbox_i[3]),
        color, ROI_LINE_WIDTH,
    )

# 同一座標の ROI は 1 つだけ描画。色は先勝ち（bb_owner 優先）
drawn_roi_keys = set()
for roi, status in (
    (bb_owner_roi, bb_owner_status),
    (kp_owner_roi, kp_owner_status),
):
    if roi is None:
        continue  # fail_kpt または not_present
    if roi in drawn_roi_keys:
        continue
    draw_roi(frame, roi, status)
    drawn_roi_keys.add(roi)
```

ROI 色:
- **ok = 黄 (0,255,255)**: 人物 BB の赤・青と独立で視認性高
- **fail_area = オレンジ (0,165,255)**: 矩形は構築できたが面積不足で feat-046 上は無効。可視化として「試行された矩形」を残す
- 線幅は両状態とも 2 で人物 BB と同等の存在感

### 4.6 FR-006: 胴体 4 点描画

#### 4.6.1 ヘルパ

```python
def extract_torso_kpts(person: dict | None) -> list[tuple[float, float, float]] | None:
    if person is None:
        return None
    kpts = person.get("pose_keypoints_2d", [])
    if len(kpts) < 78:
        return None
    return [
        (kpts[i*3], kpts[i*3+1], kpts[i*3+2])
        for i in TORSO_KEYPOINT_INDICES
    ]
```

#### 4.6.2 描画

```python
def draw_kpt_marker(frame, x, y, conf, color, kpt_conf_min: float):
    """高信頼=塗りつぶし円、低信頼=× マーク。"""
    cx, cy = int(round(x)), int(round(y))
    if conf >= kpt_conf_min:
        cv2.circle(frame, (cx, cy), KPT_RADIUS, color, -1)  # 塗りつぶし
    else:
        # × マーク
        h = KPT_CROSS_HALF
        cv2.line(frame, (cx - h, cy - h), (cx + h, cy + h), color, 2)
        cv2.line(frame, (cx + h, cy - h), (cx - h, cy + h), color, 2)

def draw_torso_kpts(frame, kpts, color, show_conf: bool, kpt_conf_min: float):
    if kpts is None:
        return
    for (x, y, c), label in zip(kpts, TORSO_KPT_LABELS):
        draw_kpt_marker(frame, x, y, c, color, kpt_conf_min)
        cx, cy = int(round(x)), int(round(y))
        # 2 文字ラベル
        cv2.putText(frame, label, (cx + 8, cy - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, KPT_LABEL_FONT_SCALE,
                    LABEL_TEXT_BLACK, 2)
        cv2.putText(frame, label, (cx + 8, cy - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, KPT_LABEL_FONT_SCALE,
                    color, 1)
        if show_conf:
            cv2.putText(frame, f"{c:.2f}", (cx + 8, cy + 10),
                        cv2.FONT_HERSHEY_SIMPLEX, KPT_LABEL_FONT_SCALE,
                        LABEL_TEXT_BLACK, 2)
            cv2.putText(frame, f"{c:.2f}", (cx + 8, cy + 10),
                        cv2.FONT_HERSHEY_SIMPLEX, KPT_LABEL_FONT_SCALE,
                        color, 1)
```

#### 4.6.3 呼び出し

```python
bb_kpts = extract_torso_kpts(bb_person)
kp_kpts = extract_torso_kpts(kp_person)

# 安全装置（理論上発動しないがデータ異常時の防護）:
# bb_index 一致時は kp 側を描画しない（同位置・同座標で塗りつぶし円が
# 重なると後描画色だけが見える問題を回避。座標値が同一なので情報量はゼロ）
bb_idx_val = bb_person["bb_index"] if bb_person else None
kp_idx_val = kp_person["bb_index"] if kp_person else None
same_person = (
    bb_idx_val is not None and kp_idx_val is not None
    and bb_idx_val == kp_idx_val
)

if bb_kpts is not None:
    draw_torso_kpts(frame, bb_kpts, RED_DARK, args.show_kpt_conf,
                    args.kpt_conf_min)
if kp_kpts is not None and not same_person:
    draw_torso_kpts(frame, kp_kpts, BLUE_DARK, args.show_kpt_conf,
                    args.kpt_conf_min)
```

`both_selected_different` 以外でも、`only_bb` で kp 側 JSON 内に同一 `bb_index` の person が存在するケースで bb_person と kp_person 両方が同じ人物を指す可能性があるが、本実装では `kp_person = find_pink_person(kp_data[f])` を使うので `only_bb` 時は `kp_person is None`。同一人物時の重複が起きるのは `both_selected_different` で bb_idx == kp_idx という矛盾状態のみで、これは disagreement の定義上発生しない（bb_idx != kp_idx の時だけ `both_selected_different` になる）。

よって理論上 `same_person` は常に False になる。安全装置として残しておく。

### 4.7 FR-007: 上部診断ラベル

#### 4.7.1 ROI 状態判定

`build_keypoint_rect_roi` を import して再計算:

```python
from postprocess_pink_id import build_keypoint_rect_roi

def get_roi_status(person: dict | None, img_w: int, img_h: int,
                   kpt_conf_min: float, min_roi_area: int) -> str:
    """ROI 状態を判定。'ok' / 'fail_kpt' / 'fail_area' / 'not_present' を返す。

    person=None は『bb_index 検索で kp 側 person が見つからない』異常系
    （bb/kp で people 配列が乖離した場合のみ発生）。発生時は呼び出し側で
    標準エラーに WARNING を出力する。

    描画用途のため、§4.5.1 の build_attempted_roi を呼ぶ（feat-046 の
    build_keypoint_rect_roi と status は同等。fail_area で矩形を返すか否か
    だけが差で、本関数は status だけ取り出す）。
    """
    if person is None:
        return "not_present"
    _, status = build_attempted_roi(
        person.get("pose_keypoints_2d", []),
        img_w, img_h, kpt_conf_min, min_roi_area,
    )
    return status  # "ok" / "fail_kpt" / "fail_area"
```

`postprocess_pink_id.py` の同関数を流用するため、`scripts/` ディレクトリは Python パスに含まれている前提（既存スクリプトの `from postprocess_pink_id import ...` 想定で問題なし）。

#### 4.7.2 ラベル文字列構築

```python
def build_top_labels(fr_idx, dtype, bb_person, kp_person, kp_content,
                     img_w, img_h, kpt_conf_min, min_roi_area):
    lines = [f"Frame: {fr_idx:06d} | Type: {dtype}"]
    # bb 行
    if bb_person is not None:
        bb_idx = bb_person["bb_index"]
        # bb 選択人物に対応する kp 側 person を bb_index 線形検索
        kp_side_person = find_person_by_bb_index(kp_content, bb_idx)
        if kp_side_person is None:
            print(f"WARNING: frame {fr_idx} bb_index={bb_idx} not found in kp JSON",
                  file=sys.stderr)
        # build_attempted_roi を直接呼んで矩形 + 状態を取得
        roi_bbox, roi_status = (
            (None, "not_present") if kp_side_person is None
            else build_attempted_roi(
                kp_side_person.get("pose_keypoints_2d", []),
                img_w, img_h, kpt_conf_min, min_roi_area,
            )
        )
        roi_str = str(list(roi_bbox)) if roi_bbox else "->"
        lines.append(
            f"bb: idx={bb_idx} ratio={bb_person.get('pink_ratio', 0):.3f}  "
            f"kp-rect ROI: {roi_status} {roi_str}"
        )
    # kp 行: kp_person は既に kp_content から取得済みなので直参照（bb_index 検索不要）
    if kp_person is not None:
        kp_idx = kp_person["bb_index"]
        roi_bbox, roi_status = build_attempted_roi(
            kp_person.get("pose_keypoints_2d", []),
            img_w, img_h, kpt_conf_min, min_roi_area,
        )
        roi_str = str(list(roi_bbox)) if roi_bbox else "->"
        lines.append(
            f"kp: idx={kp_idx} ratio={kp_person.get('pink_ratio', 0):.3f}  "
            f"kp-rect ROI: {roi_status} {roi_str}"
        )
    return lines
```

#### 4.7.3 描画

```python
def draw_top_labels(frame, lines):
    for i, line in enumerate(lines):
        org = (10, 25 + 25 * i)
        cv2.putText(frame, line, org, cv2.FONT_HERSHEY_SIMPLEX,
                    TOP_LABEL_FONT_SCALE, LABEL_TEXT_BLACK, 3)
        cv2.putText(frame, line, org, cv2.FONT_HERSHEY_SIMPLEX,
                    TOP_LABEL_FONT_SCALE, LABEL_TEXT_WHITE, 1)
```

### 4.8 FR-008: シーク失敗フォールバック

feat-047 と同じ。
```python
cap.set(cv2.CAP_PROP_POS_FRAMES, fr_idx)
ret, frame = cap.read()
if not ret:
    seek_fail_count += 1
    print(f"WARNING: failed to seek frame {fr_idx}", file=sys.stderr)
    continue
```

### 4.9 FR-009: サマリ統計

```python
print(f"Total disagreement frames: {original_count}")
print(f"  both_selected_different={counts['both_selected_different']}")
print(f"  only_bb={counts['only_bb']}")
print(f"  only_kp={counts['only_kp']}")
print(f"Samples to process: {len(disagreement_frames)}")
print(f"PNGs successfully saved: {success_count}")
print(f"Seek failures: {seek_fail_count}")
print(f"Output: {args.out_dir}/")
```

## 5. ファイル・ディレクトリ設計

### 5.1 入出力パス

| 引数 | 用途 | 例 |
|---|---|---|
| `--bb-json-dir` | 入力 | `experiments/results/camSony1_S_pink_json_bb` |
| `--kp-json-dir` | 入力 | `experiments/results/camSony1_S_pink_json_kp` |
| `--video` | 入力 | `testdata/camSony1_S.mp4` |
| `--out-dir` | 出力 | `experiments/results/camSony1_S_disagree` |

出力 PNG ファイル名は既存と同じ `frame_{NNNNNN}_disagree.png`。

### 5.2 推奨実行コマンド

```bash
# camSony1_S 全件確認
uv run python scripts/visualize_disagreement_frames.py \
  --bb-json-dir experiments/results/camSony1_S_pink_json_bb \
  --kp-json-dir experiments/results/camSony1_S_pink_json_kp \
  --video testdata/camSony1_S.mp4 \
  --out-dir experiments/results/camSony1_S_disagree \
  --all

# camSony1_L 50 件サンプリング
uv run python scripts/visualize_disagreement_frames.py \
  --bb-json-dir experiments/results/camSony1_L_pink_json_bb \
  --kp-json-dir experiments/results/camSony1_L_pink_json_kp \
  --video experiments/input/camSony1_L.mp4 \
  --out-dir experiments/results/camSony1_L_disagree \
  --max-samples 50
```

## 6. パフォーマンス影響

### 入力 JSON 読み込み
- bb / kp 両方の JSON を全フレーム分読み込む
- camSony1_S 900 フレーム × 2 = 1800 ファイル → 数秒程度
- camSony1_L 321K × 2 = 642K ファイル → 数十秒程度（ただし visualize はサンプル 50 件のみ処理）

### 描画コスト
- 1 フレームあたり 20 程度の cv2 呼び出し（BB×2, idx×2, ROI×2, 胴体点×8, ラベル×8）
- 1 件 10〜20 ms 想定。50 件で 1 秒以内
- camSony1_S 139 件全件で 3 秒以内

### NFR-001 達成見込み
- camSony1_S: JSON 読み込み 2 秒 + シーク・描画 5 秒 = 7 秒 → 30 秒以内 ✓（必達）
- camSony1_L: JSON 読み込み 30 秒 + シーク・描画 30 秒 = 60 秒前後 → **ベストエフォート**。試算は楽観的（21K files/sec 想定）でストレージ依存。要件側でベストエフォートに緩和済み（requirements.md NFR-001）

camSony1_L で JSON 全読み込みがネックになる場合は、`pink_id=1 person` の有無のみ最初に走査して該当フレームのみ再読み込みする最適化を別案件で検討。本案件初版では全読みで進める。

## 7. インターフェース定義

### 7.1 CLI 引数

| 引数 | 型 | デフォルト | 説明 |
|------|------|----------|------|
| `--bb-json-dir` | str | 必須 | bb モード JSON ディレクトリ |
| `--kp-json-dir` | str | 必須 | keypoint-rect モード JSON ディレクトリ |
| `--video` | str | 必須 | 元動画 |
| `--out-dir` | str | 必須 | PNG 出力先 |
| `--max-samples` | int | 50 | サンプル数上限（>=1、0/負値は exit code 2） |
| `--all` | flag | False | 全件出力 |
| `--show-kpt-conf` | BooleanOptionalAction | True | 胴体 4 点の信頼度テキスト表示 |

`--csv` 引数は削除。

### 7.2 公開関数

| 関数 | シグネチャ | 種別 |
|------|-----------|------|
| `load_all_json` | `(str) -> dict[int, dict]` | 新規 |
| `find_pink_person` | `(dict) -> dict\|None` | 新規 |
| `classify` | `(int\|None, int\|None) -> str\|None` | 新規 |
| `build_attempted_roi` | `(list\|None, int, int, float, int) -> (tuple\|None, str)` | 新規（area チェック省略版、`fail_area` で矩形を返す） |
| `get_roi_status` | `(dict\|None, int, int) -> str` | 新規 |
| `extract_torso_kpts` | `(dict\|None) -> list\|None` | 新規 |
| `draw_person_bbox` / `draw_idx_label` / `draw_roi` / `draw_kpt_marker` / `draw_torso_kpts` / `draw_top_labels` | 内部描画ヘルパ | 新規 |
| `main` | `() -> None` | 書き直し |

## 8. ログ・デバッグ設計

### 8.1 既存ログ準拠
- 10 件ごとに `Processing frame {N}/{total}` を標準出力（既存通り）

### 8.2 エラー・警告
- ディレクトリ不在 / 動画オープン失敗: `ERROR: ...`、exit code 1
- 片方のみのフレーム: WARNING（標準エラー）
- シーク失敗: WARNING（標準エラー）+ skip + 継続

## 9. 設計判断の記録（全体 ADR サマリ）

- **CSV 経路の完全廃止**: feat-047 design.md §9 の「compare → visualize の CSV 連鎖」設計は、only_bb ケース（94%）で必要情報が失われる根本的不備があり、列拡張の積み上げでは解決できなかった。JSON 直読みに変更し、データ源と描画の間に間接層を入れない
- **`compare_roi_modes.py` 残置**: ユーザー指示。CSV / alpha1_scatter.png 出力は将来別目的で使う可能性。本案件では同スクリプトには触れない
- **bb 選択人物の kp-rect ROI 取得**: keypoint-rect モード JSON は全 person に `roi_bbox` を持つ（`pink_id=1` person だけでなく `-1` の人物も含めて）。bb 選択人物の `bb_index` で kp 側 JSON を引けば、bb 選択人物が kp モードで「どの ROI を試みたか」「未構築だったか」を取得可能。これにより only_bb ケースでも視覚化が成立
- **ROI 色は黄 (0,255,255)**: 人物 BB の赤・青と独立。線幅 2 で BB と同等の存在感を持たせて視認性確保
- **低信頼キーポイントは × マーク**: 円の塗りつぶし／中抜きは半径 6 でも判別困難という手動テスト指摘を受け、形状を完全に変える。線の交差は判別容易
- **2 文字ラベル (LS/RS/LH/RH)**: 各キーポイントの体側を明示。フルネーム（LShoulder 等）は文字数が多すぎて他要素を覆うため 2 文字に短縮
- **ROI 状態の再計算（import 経由）**: JSON には `roi_status` フィールドがない（feat-046 が `roi_bbox` のみ保存）。再計算は `build_keypoint_rect_roi` を import で流用すれば DRY を保ちつつ実装可能。JSON 側にフィールド追加する案も検討したが、feat-046 改修が必要になるため見送り
- **idx ラベル位置を BB 右上角外側**: 初版は BB 内側に置いていたが、人物 BB 内のキーポイント（HALPE26 5/6/11/12）と必ず重なる構造的問題があり、外側に移す
- **解像度リサイズしない**: 元動画解像度のまま描画。要素サイズで調整する。リサイズは PNG ファイルサイズと処理時間が増えるため、描画品質改善で対応する判断
- **試行 ROI を `fail_area` でも描画**: feat-046 では `fail_area` 時に `roi_bbox=None` を JSON に保存するが、可視化目的では「アルゴリズムがどの矩形を試みたか」「なぜ却下されたか」を画像上に残す必要がある（feat-048 初版手動テストで「ROI がほとんどの PNG で描かれていない」指摘を受けた）。本案件で `build_attempted_roi` を新規ヘルパとして用意し、area 判定の前段で矩形を返す。状態は `ok` / `fail_area` / `fail_kpt` を引き続き返し、描画側で色分けする
- **`fail_area` の色をオレンジ (0,165,255)**: `ok` の黄と区別しつつ視認性を確保。赤系（警告）でもなく緑（成功）でもない中間色で「試行されたが採用されなかった」のニュアンスを表現
- **`fail_kpt` は描画不能で上部ラベルのみ**: 信頼点 2 個未満では矩形が形成できないため画像上に矩形を描く方法がない。上部診断ラベル（FR-007）で状態を明示する

## 10. 実装完了後のチェックリスト

- [ ] `scripts/visualize_disagreement_frames.py` を全面書き直し（CSV 関連コード削除、JSON 直読みに変更）
- [ ] FR-001〜FR-009 全て実装
- [ ] camSony1_S（不一致 139 件）で `--all` 実行、全件成功
- [ ] frame 898（`both_selected_different`）で bb 選択 ROI と kp 選択 ROI（同一の可能性あり）が描画されることを目視確認
- [ ] frame 11（`only_bb`）で bb 選択人物の kp-rect ROI または ROI 未構築理由が描画されることを目視確認
- [ ] idx ラベルとキーポイントが重ならないことを目視確認
- [ ] 高信頼点（塗りつぶし円）と低信頼点（× マーク）が判別できることを目視確認
- [ ] LS/RS/LH/RH ラベルが各点に併記されていることを目視確認
- [ ] ROI 矩形が視覚的に明確であることを目視確認（`ok`=黄 / `fail_area`=オレンジが赤系の人物 BB と混同せず判別可能）
- [ ] 上部診断ラベルに `kp-rect ROI: ok / fail_kpt / fail_area / not_present` が表示されることを目視確認
- [ ] `--no-show-kpt-conf` で信頼度テキストが消えることを確認
- [ ] camSony1_L 50 件サンプリング実行、60 秒以内（NFR-001）
- [ ] `compare_roi_modes.py` の出力（CSV / 散布図）が本案件で変化しないことを確認
- [ ] `scripts/README.md` の visualize セクションを全面改訂
- [ ] CLAUDE.md / `docs/BACKLOG.md` の feat-048 を Closed に更新
