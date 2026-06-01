# feat-051 機能設計書: selection_score 範囲によるフレーム抽出 PNG ツール

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001（CLI と検証） | §4.1 |
| FR-002（有効 s 計算） | §4.2 |
| FR-003（フレーム max s 抽出） | §4.3 |
| FR-004（PNG 描画） | §4.4 |
| FR-005（命名規約） | §4.5 |
| FR-006（サマリ統計） | §4.6 |
| NFR-001（性能） | §6 |
| NFR-002（対応環境） | §3 |
| NFR-003（既存スクリプト整合性） | §2.2 |

## 2. システム構成

### 2.1 モジュール構成

```
scripts/
├─ extract_score_range_frames.py    # 新規
├─ visualize_disagreement_frames.py # 既存（feat-048）、描画ヘルパを参照
└─ postprocess_pink_id.py           # 既存（feat-046）
```

### 2.2 依存関係

feat-048 から import:
- データ取得: `load_all_json`, `build_attempted_roi`, `extract_torso_kpts`
- 描画: `draw_person_bbox`, `draw_roi`, `draw_torso_kpts`（`draw_top_labels` は本案件では使用しない。黒帯バナー内のテキストは本ファイルで直接描画）
- バリデータ: `_check_conf`, `_check_area`
- 色: `BLUE`, `BLUE_DARK`, `ROI_COLOR_OK`, `ROI_COLOR_FAIL_AREA`（`fail_kpt` 時は roi_bbox=None で描画スキップのため専用色定数は不要）
- 定数: `TORSO_KEYPOINT_INDICES`, `TORSO_KPT_LABELS`, `KPT_RADIUS`, `BB_LINE_WIDTH`, `ROI_LINE_WIDTH` 等の描画サイズは `draw_*` 内に閉じている前提

新規 import:
- `numpy as np`（バナー領域の `np.zeros` / `np.vstack` 用）

新規ヘルパ:
- `_check_score`（s 値域 `[0.0, 1.05]` バリデータ）
- `compute_effective_s`（FR-002）

### 2.3 既存ヘルパ流用方針

`visualize_disagreement_frames.py` から関数 import。共通モジュール化は本案件スコープ外。

## 3. 技術スタック

既存と同一。

## 4. 各機能の詳細設計

### 4.1 FR-001: CLI と検証

```python
def _check_score(s: str) -> float:
    fv = float(s)
    if not (0.0 <= fv <= 1.05):
        raise argparse.ArgumentTypeError(
            f"score must be in [0.0, 1.05], got {fv}"
        )
    return fv

parser.add_argument("--json-dir", required=True)
parser.add_argument("--video", required=True)
parser.add_argument("--out-dir", required=True)
parser.add_argument("--score-min", type=_check_score, required=True)
parser.add_argument("--score-max", type=_check_score, required=True)
parser.add_argument("--kpt-conf-min", type=_check_conf, default=0.3)
parser.add_argument("--min-roi-area", type=_check_area, default=200)
parser.add_argument("--show-kpt-conf", action=argparse.BooleanOptionalAction,
                    default=True)

args = parser.parse_args()

if args.score_min > args.score_max:
    print(f"ERROR: --score-min ({args.score_min}) must be <= --score-max ({args.score_max})",
          file=sys.stderr)
    sys.exit(2)

# AC-001-1: ディレクトリ・動画存在チェック（exit code 1）
if not os.path.isdir(args.json_dir):
    print(f"ERROR: JSON directory not found: {args.json_dir}", file=sys.stderr)
    sys.exit(1)
if not os.path.isfile(args.video):
    print(f"ERROR: video not found: {args.video}", file=sys.stderr)
    sys.exit(1)
os.makedirs(args.out_dir, exist_ok=True)
```

### 4.2 FR-002: 有効 s 計算

```python
def compute_effective_s(person: dict) -> tuple[float | None, bool]:
    """有効 s 値と「フォールバック発動フラグ」を返す。

    Returns:
        (effective_s, used_fallback):
            effective_s: float または None
            used_fallback: selection_score が None で pink_ratio で代替したとき True
    """
    s = person.get("selection_score")
    if s is not None:
        return float(s), False
    r = person.get("pink_ratio")
    if r is not None:
        return float(r), True
    return None, False
```

### 4.3 FR-003: フレーム max s 抽出

```python
def find_max_s_person(people: list[dict]) -> tuple[dict | None, float | None, bool]:
    """全 person 中の有効 s 最大の person を返す。"""
    best = None
    best_s = None
    best_fallback = False
    for p in people:
        s, fb = compute_effective_s(p)
        if s is None:
            continue
        if best_s is None or s > best_s:
            best = p
            best_s = s
            best_fallback = fb
    return best, best_s, best_fallback

# フレーム走査
for fr_idx in sorted(json_data):
    content = json_data[fr_idx]
    target, max_s, used_fallback = find_max_s_person(content.get("people", []))
    if max_s is None:
        continue
    if not (args.score_min <= max_s <= args.score_max):
        continue
    # 抽出対象フレーム → PNG 描画
    ...
```

### 4.4 FR-004: PNG 描画

#### 4.4.1 動画シーク

```python
cap.set(cv2.CAP_PROP_POS_FRAMES, fr_idx)
ret, frame = cap.read()
if not ret:
    seek_fail_count += 1
    continue
```

#### 4.4.2 描画順序

実装の処理は **2 段階**で構成:

**段階 A**: `frame`（元動画フレーム）への in-place 描画（z-order: 後に描いたものが上に重なる）

1. 人物 BB（青枠、線幅 2）
2. ROI 矩形（`build_attempted_roi`、状態別色）
3. 胴体 4 点 + ラベル + 信頼度テキスト
4. BB 内部診断ラベル（idx / pid / r / iou / s）

（feat-051 v2 で BB 上部ラベル（`pink_id:` / `score:`）は省略。BB 内部診断ラベルと近接して可読性が落ちるため、AC-004-6）

**段階 B**: 元フレームの**上**に黒帯バナーを `np.vstack` で積層（別領域操作、`frame` への描画ではなく `frame` を含む新画像を生成、AC-004-5 を満たす）

5. 黒帯バナー（高さ 60 px、背景 BGR=(0,0,0)）を新規作成し、その内側に診断テキスト 2 行を描画。`np.vstack([banner, frame])` で出力画像を生成

**注**: 段階 B は z-order の概念に乗らない（`frame` 内部のレイヤではなく、`frame` の上に別領域として連結）。要求 FR-004 処理内容の番号 1〜5 は描画要素の項目列挙であり、段階 A 内部の z-order とは独立。

```python
img_h, img_w = frame.shape[:2]
bbox = target.get("bbox")
if bbox is None or len(bbox) != 4:
    continue  # 異常データ、スキップ
bbox_i = tuple(int(round(v)) for v in bbox)

# 1) 人物 BB（feat-048 の draw_person_bbox は内部で int 化するため raw bbox を渡す）
draw_person_bbox(frame, bbox, BLUE)

# 2) ROI
roi_bbox, roi_status = build_attempted_roi(
    target.get("pose_keypoints_2d", []),
    img_w, img_h, args.kpt_conf_min, args.min_roi_area,
)
if roi_bbox is not None:
    draw_roi(frame, roi_bbox, roi_status)

# 3) 胴体 4 点
kpts = extract_torso_kpts(target)
if kpts is not None:
    draw_torso_kpts(frame, kpts, BLUE_DARK, args.show_kpt_conf,
                    args.kpt_conf_min)

# 4) BB 内部診断ラベル
diag = build_diag_label(target)  # idx pid r iou s 形式
draw_diag_label(frame, bbox_i, diag, BLUE)

# （feat-051 v2: BB 上部ラベル `pink_id:` / `score:` は描画しない、AC-004-6）

# 5) 黒帯バナーを元フレームの上に追加し、診断テキストを描画
BANNER_HEIGHT = 60
banner = np.zeros((BANNER_HEIGHT, img_w, 3), dtype=np.uint8)  # 黒背景
top_lines = [
    f"Frame: {fr_idx:06d}  effective_s: {max_s:.3f} "
    f"(range: [{args.score_min}, {args.score_max}])",
    f"kp-rect ROI: {roi_status}"
    + ("  (s fallback: r used as s)" if used_fallback else ""),
]
for i, line in enumerate(top_lines):
    org = (10, 22 + 24 * i)
    cv2.putText(banner, line, org, cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (255, 255, 255), 1, cv2.LINE_AA)

# バナーを元フレームの上に積む（vstack）。出力 PNG 高さ = img_h + BANNER_HEIGHT
output_img = np.vstack([banner, frame])
```

`build_diag_label` / `draw_diag_label` は本ファイル内に新規定義（visualize_patient_video.py の同等処理を参考に簡略実装）。`draw_top_bb_label` は feat-051 v2 で BB 上部ラベル描画を廃止したため不要（実装側でも削除）。

```python
def build_diag_label(p: dict) -> str:
    parts = []
    if "bb_index" in p:
        parts.append(f"idx={p['bb_index']}")
    if "pink_id" in p:
        parts.append(f"pid={p['pink_id']}")
    if "pink_ratio" in p and p["pink_ratio"] is not None:
        parts.append(f"r={p['pink_ratio']:.3f}")
    if "iou_with_prev" in p:
        v = p["iou_with_prev"]
        parts.append("iou=null" if v is None else f"iou={v:.3f}")
    if "selection_score" in p:
        v = p["selection_score"]
        parts.append("s=null" if v is None else f"s={v:.3f}")
    return " ".join(parts)

def draw_diag_label(frame, bbox_i, text, color):
    org = (bbox_i[0] + 4, bbox_i[1] + 16)
    cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (0, 0, 0), 2)
    cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                color, 1)

```

（`draw_top_bb_label` は feat-051 v2 で廃止）

### 4.5 FR-005: 命名規約

```python
out_path = os.path.join(
    args.out_dir, f"frame_{fr_idx:06d}_s{max_s:.3f}.png"
)
cv2.imwrite(out_path, output_img)  # バナー + 元フレーム積層後の画像を保存
```

### 4.6 FR-006: サマリ統計

```python
scanned = len(json_data)  # 入力 JSON 総フレーム数（FR-006-1）
print(f"Total JSON frames scanned: {scanned}")
print(f"Frames in range [{args.score_min}, {args.score_max}]: {extracted}")
print(f"Fallback used (s=None → r): {fallback_count}")
print(f"PNGs successfully saved: {success_count}")
print(f"Seek failures: {seek_fail_count}")
print(f"Output: {args.out_dir}/")
```

## 5. ファイル・ディレクトリ設計

### 5.1 入出力パス

| 引数 | 例 |
|---|---|
| `--json-dir` | `experiments/results/camSony1_L_pink_json_kp` |
| `--video` | `experiments/input/camSony1_L.mp4` |
| `--out-dir` | `experiments/results/camSony1_L_score_010_012` |

### 5.2 推奨実行コマンド

```bash
uv run python scripts/extract_score_range_frames.py \
  --json-dir experiments/results/camSony1_L_pink_json_kp \
  --video experiments/input/camSony1_L.mp4 \
  --out-dir experiments/results/camSony1_L_score_010_012 \
  --score-min 0.10 --score-max 0.12
```

## 6. パフォーマンス影響

- JSON 読み込み: 321K × 1-2ms = 数百秒（最大ボトルネック、camSony1_S の場合は数秒）
- 範囲フィルタ判定: O(persons per frame) で軽量
- PNG 描画 + 保存: 抽出フレーム数依存。1 枚あたり 10-20 ms 想定

NFR-001 5 分以内は、`s` 範囲が狭く抽出数が少なければ余裕。広い範囲（数千フレーム抽出）では境界。

将来最適化: 範囲外フレームの JSON 読み込みを skip するため、ファイル名でフレーム範囲を絞る `--frame-start / --frame-end` 追加可能（本案件初版では含めず）。

## 7. インターフェース定義

### 7.1 CLI 引数

| 引数 | 型 | デフォルト | 説明 |
|------|------|----------|------|
| `--json-dir` | str | 必須 | kp モード JSON ディレクトリ |
| `--video` | str | 必須 | 元動画 |
| `--out-dir` | str | 必須 | PNG 出力先 |
| `--score-min` | float | 必須 | 有効 s 下限（[0.0, 1.05]、含む） |
| `--score-max` | float | 必須 | 有効 s 上限（[0.0, 1.05]、含む） |
| `--kpt-conf-min` | float | 0.3 | ROI 状態再計算の信頼度閾値 |
| `--min-roi-area` | int | 200 | ROI 状態再計算の最低面積 |
| `--show-kpt-conf` | BooleanOptionalAction | True | 信頼度テキスト表示 |

### 7.2 公開関数

| 関数 | シグネチャ | 種別 |
|---|---|---|
| `_check_score` | `(str) -> float` | 新規 |
| `compute_effective_s` | `(dict) -> (float\|None, bool)` | 新規 |
| `find_max_s_person` | `(list[dict]) -> (dict\|None, float\|None, bool)` | 新規 |
| `build_diag_label` | `(dict) -> str` | 新規 |
| `draw_diag_label` | `(np.ndarray, tuple, str, tuple) -> None` | 新規 |
| `main` | `() -> None` | 新規 |

## 8. ログ・デバッグ設計

- 1000 フレームごとに `Scanning frame N/total` を標準出力
- エラー: ディレクトリ / 動画不在 → exit code 1
- 警告: シーク失敗、フレームスキップ

## 9. 設計判断の記録（ADR）

- **`compute_effective_s` フォールバック規約**: feat-041 で `selection_score=None` を「前 BB なし vs IoU=0」識別目的に採用したが、`s` を threshold 検討で使う本ツールでは `r` で代替する方が情報量を保てる。JSON 形式は変更せず、ツールローカルでフォールバック
- **1 フレーム 1 person のみ描画**: 最大 s の person のみ。複数 person を描くと「どれが対象か」が画像から判らなくなる。閾値検討用途では最大 s の挙動が知りたい情報
- **PNG ファイル名に s 値を含める**: ディレクトリリストでソートすれば s 順に並び、目視作業が効率化
- **`s` 値域 `[0.0, 1.05]`**: 理論最大値 1.0 + 0.05 = 1.05 を許容。実データでは 1.0 を超えるケースは稀だが、バリデータは緩めに
- **`build_attempted_roi` 再利用**: feat-048 から import。feat-046 → feat-048 → feat-051 で同じ ROI 再計算ロジックを再利用し DRY
- **`--frame-start/--end` を初版に含めない**: 性能最適化用途。初版は機能優先、必要なら別案件で追加
- **上部診断テキストを黒帯バナーで描画**: 元動画フレーム内に重ねる方式（feat-048 / visualize_disagreement_frames の `draw_top_labels`）は対象 BB が画面上部にあるケースで衝突して可読性を失う。元フレームの上に高さ 60 px の黒帯領域を `np.vstack` で追加し、その内側にテキストを描画することで衝突を構造的に回避。出力 PNG の高さは元動画高さ + 60 px となるが、元動画ピクセルは一切覆われない（AC-004-5）
- **`draw_top_labels` を流用しない**: 黒帯背景 + 白文字単独で十分可読なため、黒縁取り + 白文字の 2 重 putText を行う既存ヘルパは不要。本ファイル内で直接 `cv2.putText` を呼ぶ

## 10. 実装完了後のチェックリスト

- [ ] `scripts/extract_score_range_frames.py` 新規作成
- [ ] feat-048 からヘルパ import
- [ ] CLI バリデータ 3 種実装（`_check_score`、`_check_conf`/`_check_area` 流用）
- [ ] `compute_effective_s` / `find_max_s_person` 実装
- [ ] 描画ヘルパ 2 種新規実装（`build_diag_label` / `draw_diag_label`）。feat-051 v2 で `draw_top_bb_label` は廃止
- [ ] camSony1_S で `--score-min 0.10 --score-max 0.20` 等を実行、PNG 出力確認
- [ ] camSony1_L で実行、NFR-001 5 分以内（範囲依存）
- [ ] `--score-min > --score-max` で exit code 2（`--score-min == --score-max` は許容）
- [ ] 値域外引数で exit code 2
- [ ] フォールバック発動フレームでサマリにカウントが出ることを確認
- [ ] 出力 PNG の高さ = 元動画高さ + 60 px、幅は元動画と同一を確認（AC-004-5）
- [ ] 黒帯バナーが元フレームピクセル領域と重ならないことを構造的に確認（バナーは元フレーム外の別領域なので、定義上絶対に衝突しない）。feat-051 v2 で BB 上部ラベルは廃止済みのため、バナー直下と BB 上部ラベルの近接問題は対象外
- [ ] `scripts/README.md` に新スクリプトのセクション追加
- [ ] BACKLOG / CLAUDE.md 更新
