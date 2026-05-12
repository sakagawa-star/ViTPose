# feat-046 機能設計書: postprocess_pink_id.py のキーポイントベース ROI 対応

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001（--roi-mode 引数） | §4.1 / §7.1 |
| FR-002（kpt-conf-min / min-roi-area 引数） | §4.1 / §7.1 |
| FR-003（bb モード挙動維持） | §4.2 |
| FR-004（keypoint-rect ROI 構築） | §4.3 |
| FR-005（keypoint-rect pink_ratio 計算） | §4.4 |
| FR-006（roi_mode / roi_bbox フィールド） | §4.5 |
| FR-007（サマリ統計） | §4.6 |
| NFR-001（性能） | §6 |
| NFR-003（互換性） | §4.2 / §4.5 |

## 2. システム構成

### 2.1 モジュール構成

`scripts/postprocess_pink_id.py` 単一ファイルを修正。新規ファイルは作成しない。

```
scripts/postprocess_pink_id.py
├─ 定数（既存）
│   ├─ FIXED_HSV_RANGES
│   ├─ MIN_PINK_RATIO = 0.03
│   └─ IOU_CONT_WEIGHT = 0.05
├─ 新規定数
│   └─ TORSO_KEYPOINT_INDICES = (5, 6, 11, 12)  # LShoulder, RShoulder, LHip, RHip
├─ 純関数
│   ├─ compute_pink_ratio（既存、変更なし）
│   ├─ compute_iou（既存、変更なし）
│   ├─ clip_bbox（既存、変更なし）
│   ├─ select_pink_bbox（既存、変更なし）
│   └─ build_keypoint_rect_roi（新規）
├─ argparse type checkers
│   ├─ _check_conf（新規）
│   └─ _check_area（新規）
└─ main
    ├─ CLI 引数追加（--roi-mode, --kpt-conf-min, --min-roi-area）
    └─ pink_ratio 計算ループ内で roi_mode による分岐
```

### 2.2 依存関係

追加 import なし。既存の `cv2` / `numpy` / `json` / `argparse` で完結。

## 3. 技術スタック

| 項目 | 値 | 備考 |
|------|-----|------|
| 言語 | Python 3.10.16 | プロジェクト既定 |
| OpenCV | 既存依存 | 変更なし |
| numpy | 既存依存 | 変更なし |

## 4. 各機能の詳細設計

### 4.1 FR-001 / FR-002: CLI 引数

#### 4.1.1 argparse type checkers（新規）

```python
def _check_conf(v: str) -> float:
    fv = float(v)
    if not (0.0 <= fv <= 1.0):
        raise argparse.ArgumentTypeError(f"kpt-conf-min must be in [0.0, 1.0], got {fv}")
    return fv

def _check_area(v: str) -> int:
    iv = int(v)
    if iv < 1:
        raise argparse.ArgumentTypeError(f"min-roi-area must be >= 1, got {iv}")
    return iv
```

#### 4.1.2 CLI 引数追加

既存の `parser` に以下を追加（既存引数の直後）:

```python
parser.add_argument(
    "--roi-mode", default="bb", choices=["bb", "keypoint-rect"],
    help="ROI for pink ratio. bb: existing BB; keypoint-rect: min/max axis-aligned rect of 4 torso keypoints (default: bb)",
)
parser.add_argument(
    "--kpt-conf-min", type=_check_conf, default=0.3,
    help="Minimum keypoint confidence to use for keypoint-rect ROI (0.0-1.0, default: 0.3)",
)
parser.add_argument(
    "--min-roi-area", type=_check_area, default=200,
    help="Minimum ROI area in pixels (>=1, default: 200)",
)
```

### 4.2 FR-003: bb モード挙動完全維持

bb モード時は新規ロジックを一切実行せず、既存の処理フローを通す。

#### 4.2.1 メインループ内の分岐

```python
# 既存: for i, person in enumerate(people):
for i, person in enumerate(people):
    bb = person.get("bbox")
    # ... bbox 妥当性チェック（既存）...
    
    if args.roi_mode == "bb":
        # 既存処理
        clipped = clip_bbox(bb, width, height)
        roi = frame[clipped[1]:clipped[3], clipped[0]:clipped[2]]
        ratio = compute_pink_ratio(roi)
    else:  # keypoint-rect
        # FR-004 / FR-005 のロジック
        ...
```

#### 4.2.2 既存挙動との完全一致を担保する設計

- bb モード分岐内の処理は既存コードの完全コピー（リファクタなし、§2.2 制約準拠）
- 既存 `clipped` / `roi` / `ratio` 変数は同一名・同一型
- bb モード時、`roi_mode` / `roi_bbox` フィールドは書き込まない（FR-006 AC-006-1）
- bb モード時、サマリは既存と完全一致（FR-007 AC-007-1）

### 4.3 FR-004: keypoint-rect ROI 構築

#### 4.3.1 関数シグネチャ

```python
def build_keypoint_rect_roi(
    kpts_flat: list[float],         # length 78 (26 keypoints × 3)
    width: int,                     # 画像幅
    height: int,                    # 画像高さ
    conf_min: float,                # キーポイント信頼度閾値
    area_min: int,                  # ROI 最低面積（px）
) -> tuple[tuple[int, int, int, int] | None, str]:
    """
    Returns:
        (roi_bbox, status):
            roi_bbox = (x1, y1, x2, y2) または None
            status ∈ {"ok", "fail_kpt", "fail_area"}
    """
```

`status` は FR-007 のサマリ集計で使う。

#### 4.3.2 処理ロジック

```python
TORSO_KEYPOINT_INDICES = (5, 6, 11, 12)

def build_keypoint_rect_roi(kpts_flat, width, height, conf_min, area_min):
    if len(kpts_flat) < 78:
        return None, "fail_kpt"
    # 4 点抽出
    candidates = []
    for idx in TORSO_KEYPOINT_INDICES:
        base = idx * 3
        x, y, c = kpts_flat[base], kpts_flat[base+1], kpts_flat[base+2]
        if c >= conf_min:
            candidates.append((x, y))
    # 信頼できる点が 2 個未満
    if len(candidates) < 2:
        return None, "fail_kpt"
    # min/max 矩形 → 既存 clip_bbox を再利用（DRY、丸め・クランプ基準を完全に揃える）
    xs = [p[0] for p in candidates]
    ys = [p[1] for p in candidates]
    x1, y1, x2, y2 = clip_bbox(
        (min(xs), min(ys), max(xs), max(ys)),
        width, height,
    )
    # 面積チェック（x1 == x2 または y1 == y2 で線分縮退、AC-004-3 と整合）
    if x2 <= x1 or y2 <= y1:
        return None, "fail_area"
    area = (x2 - x1) * (y2 - y1)
    if area < area_min:
        return None, "fail_area"
    return (x1, y1, x2, y2), "ok"
```

#### 4.3.3 境界条件

- `kpts_flat` が None / 長さ 78 未満 ⇒ "fail_kpt"
- 4 点すべての conf < conf_min ⇒ candidates = [] ⇒ len 0 < 2 ⇒ "fail_kpt"
- 4 点中 1 点のみ conf>=conf_min ⇒ len 1 < 2 ⇒ "fail_kpt"
- 4 点中 2 点が同一座標（同じキーポイント信頼度高） ⇒ area 0 ⇒ "fail_area"
- min/max 矩形が画像外（4 点とも画像左上端の (0,0) など極端ケース） ⇒ clip 後 area 0 ⇒ "fail_area"
- 通常ケース（4 点で胴体らしい矩形） ⇒ "ok"

### 4.4 FR-005: keypoint-rect モード pink_ratio 計算

#### 4.4.1 メインループ内の keypoint-rect 分岐

```python
else:  # args.roi_mode == "keypoint-rect"
    kpts_flat = person.get("pose_keypoints_2d", [])
    roi_bbox, status = build_keypoint_rect_roi(
        kpts_flat, width, height, args.kpt_conf_min, args.min_roi_area,
    )
    if roi_bbox is None:
        ratio = 0.0
    else:
        rx1, ry1, rx2, ry2 = roi_bbox
        roi = frame[ry1:ry2, rx1:rx2]
        ratio = compute_pink_ratio(roi)
    # FR-007 統計カウンタ更新
    stats_kpt[status] += 1
    # FR-006 で参照する roi_bbox は本ブロックの変数をそのまま使用
```

#### 4.4.2 bbox 欠損時の挙動

既存コード (`postprocess_pink_id.py` の bbox 妥当性チェック、L233-240 付近) では、`person.get("bbox")` が無効な場合に `bboxes.append(None); ratios.append(0.0)` で WARNING を出力する経路がある。**keypoint-rect モードでもこの経路はそのまま通る**:

- `bbox` 欠損 ⇒ 既存の early-continue 経路で `bboxes.append(None); ratios.append(0.0)`、`build_keypoint_rect_roi` は呼ばれない
- これにより、`bb_index` / `iou_with_prev` / `selection_score` の欠損経路（feat-041 の null 規約）が既存と同じ意味論を維持

#### 4.4.3 IoU 連続性・selection_score の意味論（keypoint-rect モード）

keypoint-rect モードでも、`select_pink_bbox` 内部の IoU 計算は **既存と同じ `bboxes`（=人物 BB）** を使用する。具体的には:

- `pink_ratio`: keypoint-rect ROI（胴体矩形）内の HSV 比率（**ROI ベース**）
- `iou_with_prev`: 当該人物の `bbox`（= 人物 BB）と `prev_selected_bbox` の IoU（**BB ベース**、既存と同じ）
- `selection_score = pink_ratio + 0.05 × iou_with_prev`（既存式と同じ）
- `prev_selected_bbox` 更新: 選択された人物の `bboxes[sel_idx]`（= 人物 BB）を代入（既存と同じ）

これは**色は ROI、連続性は BB のハイブリッド構造**。`select_pink_bbox` 関数のシグネチャ・引数・ロジックは一切変更しない（FR-003 / §5.2 スコープ外）。

#### 4.4.4 設計判断の記録（ADR）

- **採用: K-2 方式**（信頼できる点のみで矩形構築）。低信頼点の座標が (0, 0) などのとき矩形が画像左上まで膨らむ事故を回避
- **却下: K-1 方式**（4 点すべての座標を使う）。低信頼点の位置誤差が矩形に直接反映するリスクが大きい
- **採用: F2 厳しめフォールバック**（ROI 構築不能なら pink_ratio = 0）。BB モードと keypoint-rect モードの効果を厳密比較するため、自動フォールバックを行わない
- **却下: F1 自動 BB フォールバック**。挙動が「成功すれば keypoint、失敗すれば BB」のハイブリッドとなり、純粋な比較ができなくなる
- **意図的なハイブリッド構造（色=ROI、連続性=BB）**: `pink_ratio` のみ ROI ベースに切り替え、IoU 連続性は人物 BB ベースを維持。理由: (1) IoU は「人物の動き」を捉える指標であり、胴体 ROI でなく人物 BB のほうが物理的な追跡として自然、(2) `select_pink_bbox` の変更スコープを最小化し、bb モードとの差分を「ROI のみ」に局所化することで効果比較の純度を高める
- **却下: IoU も ROI ベースに**。連続性ボーナスの値が大きく変わり、bb モードとの選択挙動差が「ROI 変更」+「IoU 変更」の合算となって効果分離できなくなる

#### 4.4.5 廃止: 旧 ADR 番号（4.4.2）

§4.4.4 に統合（旧位置に重複があったため削除）。

### 4.5 FR-006: roi_mode / roi_bbox フィールド追加

#### 4.5.1 追加ロジック

既存の pink_id 付与ループ末尾に追加:

```python
# 既存: person["pink_id"] = ...; person["pink_ratio"] = ...; ...
# 新規追加（keypoint-rect モード時のみ）
if args.roi_mode == "keypoint-rect":
    person["roi_mode"] = "keypoint-rect"
    person["roi_bbox"] = list(roi_bbox) if roi_bbox is not None else None
```

#### 4.5.2 互換性（NFR-003）

- bb モード時はこれらを書き込まない → JSON 出力は既存と完全一致 (AC-003-1)
- keypoint-rect モード時は新規フィールドのみ追加 → 既存フィールド (`pink_id`, `pink_ratio`, `bb_index`, `iou_with_prev`, `selection_score`, `bbox`, `pose_keypoints_2d`, `bbox_score` 等) は変更なし
- 下流スクリプト（feat-035 / 036 / 037 / 038 / 039 / 040 / 041 / 042）はすべて生 dict 保持設計のため、未知フィールドを無視。動作に影響なし

### 4.6 FR-007: サマリ統計

#### 4.6.1 統計カウンタの初期化

main 関数冒頭で初期化:

```python
stats_kpt = {"ok": 0, "fail_kpt": 0, "fail_area": 0}
```

bb モード時はこのカウンタを使用しない（更新も出力もしない）。

#### 4.6.2 サマリ出力

既存サマリブロック末尾に追加:

```python
# 既存: print(f"Frames with pink_id=1: {summary_selected}") など
if args.roi_mode == "keypoint-rect":
    total_persons = stats_kpt["ok"] + stats_kpt["fail_kpt"] + stats_kpt["fail_area"]
    print(f"ROI mode: keypoint-rect")
    print(f"  ROI built (ok):       {stats_kpt['ok']:6d} / {total_persons:6d}")
    print(f"  ROI failed (kpt):     {stats_kpt['fail_kpt']:6d} / {total_persons:6d}")
    print(f"  ROI failed (area):    {stats_kpt['fail_area']:6d} / {total_persons:6d}")
```

bb モード時は何も出力しない（既存サマリと完全一致）。

## 5. ファイル・ディレクトリ設計

### 5.1 入出力パス

既存 `postprocess_pink_id.py` と同じ。`--video` / `--json-dir` / `--out-dir` の変更なし。

### 5.2 推奨実行コマンド（手動テスト用）

```bash
# bb モード（既存挙動、AC-003-1 で比較確認用）
uv run python scripts/postprocess_pink_id.py \
  --video testdata/camSony1_S.mp4 \
  --json-dir experiments/results/camSony1_S_halpe26_json \
  --out-dir experiments/results/camSony1_S_pink_json_bb \
  --roi-mode bb

# keypoint-rect モード（新機能）
uv run python scripts/postprocess_pink_id.py \
  --video testdata/camSony1_S.mp4 \
  --json-dir experiments/results/camSony1_S_halpe26_json \
  --out-dir experiments/results/camSony1_S_pink_json_kp \
  --roi-mode keypoint-rect
```

注: 上記 `--json-dir` は HALPE26 推論結果（`run_halpe26_pipeline_yolo11.py` 出力）を指す。既存の `camSony1_S_pink_json` ではない（pink_id 付与前の JSON が入力）。

## 6. パフォーマンス影響

keypoint-rect モードの追加処理:
- 各人物 1 回: `build_keypoint_rect_roi` 呼び出し（min/max 計算と数値判定のみ、O(1)）
- `roi_mode` / `roi_bbox` フィールド書き込み（dict 代入 2 回）

camSony1_L で人物数 100 万強 × 数 μs ≒ 数秒の追加。NFR-001 の 20% 以内（既存 ~250 秒に対し +5 秒程度）に余裕で収まる見込み。

## 7. インターフェース定義

### 7.1 CLI 引数まとめ

| 引数 | 型 | デフォルト | 値域 | 使用モード |
|------|------|----------|------|----------|
| `--video` | str | 必須 | - | 両 |
| `--json-dir` | str | 必須 | - | 両 |
| `--out-dir` | str | 必須 | - | 両 |
| `--roi-mode` | str | `bb` | `{bb, keypoint-rect}` | 両 |
| `--kpt-conf-min` | float | `0.3` | `[0.0, 1.0]` | keypoint-rect |
| `--min-roi-area` | int | `200` | `>=1` | keypoint-rect |

### 7.2 公開関数シグネチャ

| 関数 | シグネチャ | 変更 |
|------|-----------|------|
| `compute_pink_ratio` | `(np.ndarray) -> float` | 変更なし |
| `compute_iou` | `(tuple, tuple) -> float` | 変更なし |
| `clip_bbox` | `(tuple, int, int) -> tuple` | 変更なし |
| `select_pink_bbox` | `(list, list, tuple|None) -> int` | 変更なし |
| `build_keypoint_rect_roi` | `(list[float], int, int, float, int) -> (tuple|None, str)` | 新規追加 |

## 8. ログ・デバッグ設計

### 8.1 既存ログ準拠

進捗表示・サマリは既存形式を踏襲。bb モード時は完全に既存と同じ。

### 8.2 追加ログ

keypoint-rect モード時のみ、サマリ末尾に 3 統計を追加（FR-007）。WARNING や DEBUG ログは追加しない。

## 9. 設計判断の記録（全体 ADR サマリ）

- **K-2 採用**: 信頼できる点のみで min/max 矩形を構築。K-1（4 点全座標使用）の暴走リスクを回避
- **F2 厳しめ採用**: BB 自動フォールバックなし。比較の純度を保つため
- **--roi-mode のデフォルト bb**: 後方互換性を最優先
- **新規フィールド roi_mode / roi_bbox は keypoint-rect モード時のみ書き込み**: bb モード JSON の完全互換性確保
- **新規キー名 `roi_mode` / `roi_bbox` の衝突確認済み**: 既存 JSON のキー一覧（`person_id, pose_keypoints_2d, face_keypoints_2d, hand_left_keypoints_2d, hand_right_keypoints_2d, pose_keypoints_3d, face_keypoints_3d, hand_left_keypoints_3d, hand_right_keypoints_3d, bbox_score, bbox, pink_id, pink_ratio, bb_index, iou_with_prev, selection_score` 等）と衝突なし。feat-018 の `bbox` フィールドとは別名で混同リスクなし
- **TORSO_KEYPOINT_INDICES = (5, 6, 11, 12) で固定**: 本案件のスコープでカスタマイズ不要。Neck (18) や Hip 中心 (19) を追加するアイデアは別案件で検討
- **CLI 名は `keypoint-rect`（ハイフン区切り）**: argparse の `dest` は自動で `args.roi_mode` 等になる。Python 識別子としても問題なし

## 10. 実装完了後のチェックリスト

- [ ] `scripts/postprocess_pink_id.py` に `_check_conf` / `_check_area` / `build_keypoint_rect_roi` / `TORSO_KEYPOINT_INDICES` を追加
- [ ] argparse に 3 引数追加
- [ ] main ループに roi_mode 分岐を追加
- [ ] サマリに keypoint-rect 統計を追加
- [ ] camSony1_S で bb モード実行、改修前と JSON 完全一致を確認（AC-003-1）
- [ ] camSony1_S で keypoint-rect モード実行、サマリ統計が表示されることを確認（AC-007-2）
- [ ] keypoint-rect モード JSON で `roi_mode` / `roi_bbox` フィールドが存在することを確認（AC-006-2, AC-006-3）
- [ ] 値域外引数 6 ケースで exit code 2 を確認（AC-002-2）
- [ ] camSony1_L で keypoint-rect モード実行、処理時間が bb モードの 120% 以内（NFR-001）
- [ ] `scripts/README.md` に新規引数を反映
- [ ] CLAUDE.md の feat-046 エントリを完了済み案件として追記
- [ ] `docs/BACKLOG.md` の feat-046 を Closed に変更
- [ ] `docs/issues/feat-046-keypoint-rect-roi/README.md` のステータスを Closed に更新
