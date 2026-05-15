# feat-049 機能設計書: keypoint-rect モード単体・全フレーム可視化ツール

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001（JSON / 動画読み込み） | §4.1 |
| FR-002（フレーム範囲・サンプリング） | §4.2 |
| FR-003（人物 BB 描画） | §4.3 |
| FR-004（idx ラベル） | §4.4 |
| FR-005（ROI 矩形描画） | §4.5 |
| FR-006（胴体 4 点描画） | §4.6 |
| FR-007（上部診断ラベル） | §4.7 |
| FR-008（サマリ統計） | §4.8 |
| NFR-001（性能） | §6 |
| NFR-002（対応環境） | §3 |
| NFR-003（feat-048 整合性） | §2.2 |

## 2. システム構成

### 2.1 モジュール構成

```
scripts/
├─ visualize_kp_frames.py            # 新規作成
├─ visualize_disagreement_frames.py  # 既存（feat-048）。共通ヘルパの参照元
└─ postprocess_pink_id.py            # 既存（feat-046）。clip_bbox を参照
```

### 2.2 依存関係

`visualize_disagreement_frames.py` から以下を import:
- `build_attempted_roi`（feat-048 で新規追加）
- `find_pink_person`
- `extract_torso_kpts`
- 描画ヘルパ: `draw_person_bbox`, `draw_idx_label`, `draw_roi`, `draw_kpt_marker`, `draw_torso_kpts`, `draw_top_labels`
- 色・サイズ定数: `BLUE`, `BLUE_DARK`, `ROI_COLOR_OK`, `ROI_COLOR_FAIL_AREA`, `KPT_RADIUS` 等

`postprocess_pink_id.py` から:
- `clip_bbox`（`build_attempted_roi` の依存。間接的）

新規ライブラリ追加なし。

### 2.3 共通モジュール化の判断

feat-048 と feat-049 で描画ヘルパが共通になるため、本案件で「`visualize_disagreement_frames.py` から関数を import する」方針を採用。将来重複が増えれば `scripts/_visualize_common.py` 等への分離を検討するが、本案件のスコープ外。

## 3. 技術スタック

既存と同一（Python 3.10.16、uv、OpenCV、CPU）。

## 4. 各機能の詳細設計

### 4.1 FR-001: JSON / 動画読み込み

#### 4.1.1 引数バリデータ

feat-048 の `_check_conf` / `_check_area` と同じロジック。feat-048 から import するか、本ファイル内に複製するかは実装時に判断（DRY のため import を優先）。

```python
from visualize_disagreement_frames import (
    build_attempted_roi, find_pink_person, extract_torso_kpts,
    draw_person_bbox, draw_idx_label, draw_roi,
    draw_torso_kpts, draw_top_labels,
    _check_conf, _check_area, _positive_int,
    BLUE, BLUE_DARK, ROI_COLOR_OK, ROI_COLOR_FAIL_AREA,
)
```

（feat-048 側のプライベートヘルパ `_check_conf` / `_check_area` / `_positive_int` を import で使うため、feat-048 側に `__all__` 等の制約は設けない。）

#### 4.1.2 JSON 読み込み

```python
PATTERN = re.compile(r"_(\d{6})\.json$")

def load_all_json(json_dir: str) -> dict[int, dict]:
    result = {}
    for fname in os.listdir(json_dir):
        m = PATTERN.search(fname)
        if not m:
            continue
        with open(os.path.join(json_dir, fname)) as f:
            result[int(m.group(1))] = json.load(f)
    return result
```

feat-048 と同じ関数。feat-048 側から import 推奨。

#### 4.1.3 ディレクトリ・動画存在チェック

main 冒頭:
```python
if not os.path.isdir(args.json_dir):
    print(f"ERROR: JSON directory not found: {args.json_dir}", file=sys.stderr)
    sys.exit(1)
if not os.path.isfile(args.video):
    print(f"ERROR: video not found: {args.video}", file=sys.stderr)
    sys.exit(1)
os.makedirs(args.out_dir, exist_ok=True)
```

### 4.2 FR-002: フレーム範囲・サンプリング

```python
total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
frame_start = max(0, args.frame_start)
frame_end = (
    total_video_frames - 1 if args.frame_end == -1
    else min(args.frame_end, total_video_frames - 1)
)
target_frames = list(range(frame_start, frame_end + 1, args.step))
```

`--step` は `_positive_int` バリデータで `>=1` を保証。

実行ロジック:
```python
cap.set(cv2.CAP_PROP_POS_FRAMES, frame_start)
for fr_idx in target_frames:
    cap.set(cv2.CAP_PROP_POS_FRAMES, fr_idx)
    ret, frame = cap.read()
    if not ret:
        seek_fail_count += 1
        print(f"WARNING: failed to seek frame {fr_idx}", file=sys.stderr)
        continue
    # 以降の描画処理（§4.3〜§4.7）
```

シーク精度は OpenCV 任せ（feat-047 ADR 踏襲）。

### 4.3 FR-003: 人物 BB 描画

```python
content = json_data.get(fr_idx)
kp_person = find_pink_person(content) if content else None

if kp_person is not None:
    draw_person_bbox(frame, kp_person.get("bbox"), BLUE)
```

### 4.4 FR-004: idx ラベル

```python
if kp_person is not None:
    bbox = kp_person.get("bbox")
    if bbox is not None and len(bbox) == 4:
        bbox_i = tuple(int(round(v)) for v in bbox)
        idx_val = kp_person.get("bb_index")
        draw_idx_label(frame, bbox_i, f"idx={idx_val}", BLUE, img_w)
```

### 4.5 FR-005: ROI 矩形

```python
roi_bbox, roi_status = (
    (None, "not_present") if kp_person is None
    else build_attempted_roi(
        kp_person.get("pose_keypoints_2d", []),
        img_w, img_h, args.kpt_conf_min, args.min_roi_area,
    )
)
if roi_bbox is not None:
    draw_roi(frame, roi_bbox, roi_status)
```

### 4.6 FR-006: 胴体 4 点

```python
kp_kpts = extract_torso_kpts(kp_person)
if kp_kpts is not None:
    draw_torso_kpts(frame, kp_kpts, BLUE_DARK, args.show_kpt_conf,
                    args.kpt_conf_min)
```

### 4.7 FR-007: 上部診断ラベル

```python
lines = [f"Frame: {fr_idx:06d}"]
if content is None:
    lines.append("(no JSON for this frame)")
elif kp_person is None:
    lines.append("kp: no pink_id=1 person in this frame")
else:
    kp_idx = kp_person["bb_index"]
    roi_str = str(list(roi_bbox)) if roi_bbox else "->"
    lines.append(
        f"kp: idx={kp_idx} ratio={kp_person.get('pink_ratio', 0):.3f}  "
        f"kp-rect ROI: {roi_status} {roi_str}"
    )

draw_top_labels(frame, lines)
```

### 4.8 FR-008: サマリ統計

```python
print(f"Target frames: {len(target_frames)}")
print(f"  with pink_id=1: {with_selection}")
print(f"  without pink_id=1: {without_selection}")
print(f"  missing JSON: {json_missing}")
print(f"PNGs successfully saved: {success_count}")
print(f"Seek failures: {seek_fail_count}")
print(f"Output: {args.out_dir}/")
```

## 5. ファイル・ディレクトリ設計

### 5.1 入出力パス

| 引数 | 用途 | 例 |
|---|---|---|
| `--json-dir` | 入力 | `experiments/results/camSony1_S_pink_json_kp` |
| `--video` | 入力 | `testdata/camSony1_S.mp4` |
| `--out-dir` | 出力 | `experiments/results/camSony1_S_kp_frames` |

出力 PNG ファイル名: `frame_{NNNNNN}.png`（6 桁ゼロ埋め）。

### 5.2 推奨実行コマンド

```bash
# 全フレーム描画
uv run python scripts/visualize_kp_frames.py \
  --json-dir experiments/results/camSony1_S_pink_json_kp \
  --video testdata/camSony1_S.mp4 \
  --out-dir experiments/results/camSony1_S_kp_frames

# 範囲指定
uv run python scripts/visualize_kp_frames.py \
  --json-dir experiments/results/camSony1_S_pink_json_kp \
  --video testdata/camSony1_S.mp4 \
  --out-dir experiments/results/camSony1_S_kp_frames \
  --frame-start 100 --frame-end 200

# 5 フレーム刻み
uv run python scripts/visualize_kp_frames.py \
  --json-dir experiments/results/camSony1_S_pink_json_kp \
  --video testdata/camSony1_S.mp4 \
  --out-dir experiments/results/camSony1_S_kp_frames \
  --step 5
```

## 6. パフォーマンス影響

### 試算（camSony1_S 全 900 フレーム）

- JSON 読み込み: 900 ファイル × 1〜2 ms ≒ 1〜2 秒
- 動画シーク + デコード: 900 × 5 ms ≒ 5 秒
- 描画: 1 件あたり 5〜10 ms × 900 ≒ 5〜10 秒
- PNG 書き出し: 1 枚 50〜100 KB × 900 ≒ 数秒
- 合計: 30 秒以内見込み（NFR-001 60 秒以内、達成見込み）

### camSony1_L（参考、本案件 NFR スコープ外）

- 321K フレーム → 全フレーム描画は約 1 時間規模。`--step` か `--frame-start/--frame-end` で範囲指定する運用が現実的

## 7. インターフェース定義

### 7.1 CLI 引数

| 引数 | 型 | デフォルト | 説明 |
|------|------|----------|------|
| `--json-dir` | str | 必須 | kp モード JSON ディレクトリ |
| `--video` | str | 必須 | 元動画 |
| `--out-dir` | str | 必須 | PNG 出力先 |
| `--frame-start` | int | 0 | 開始フレーム番号 |
| `--frame-end` | int | -1 | 終了フレーム番号（-1 = 動画末尾） |
| `--step` | int | 1 | N フレーム刻み（>=1） |
| `--show-kpt-conf` | BooleanOptionalAction | True | 信頼度テキスト表示 |
| `--kpt-conf-min` | float | 0.3 | ROI 状態再計算の信頼度閾値（[0.0, 1.0]） |
| `--min-roi-area` | int | 200 | ROI 状態再計算の最低面積（>=1） |

### 7.2 公開関数

| 関数 | シグネチャ | 種別 |
|------|-----------|------|
| `main` | `() -> None` | 新規 |

その他の描画・データ取得関数は feat-048 から import。

## 8. ログ・デバッグ設計

- 100 件ごとに `Processing frame N/total` を標準出力
- エラー: ディレクトリ不在 / 動画オープン失敗 → `ERROR: ...`、exit code 1
- 警告: JSON 欠落フレーム、シーク失敗 → 標準エラーに WARNING、continue

## 9. 設計判断の記録（全体 ADR サマリ）

- **feat-048 から関数 import**: 描画スタイルを feat-048 と完全に揃え、コード重複を避ける。共通モジュール化（`_visualize_common.py`）は本案件では行わず、必要が出てから別案件で対応
- **pink_id=1 person 以外は描画しない**: kp モード選択結果の検証に集中するため。他 person（pink_id=-1）を描画すると視認性が下がる
- **JSON 欠落フレームでも PNG 出力**: 動画フレームを描画するが診断ラベル 2 行目に `(no JSON for this frame)` を表示。これにより「JSON 欠落」を画像から判別可能にする
- **`--step` で間引き可能**: camSony1_L のような大規模データでも目視運用に耐えるよう、N フレーム刻み出力をサポート
- **シーク精度は OpenCV 任せ**: feat-047 ADR を踏襲。完全精度が必要になれば別案件で逐次読みに切替

## 10. 実装完了後のチェックリスト

- [ ] `scripts/visualize_kp_frames.py` を新規作成
- [ ] feat-048 から必要な関数・定数を import
- [ ] CLI 引数 9 種を実装
- [ ] camSony1_S 全 900 フレーム実行、NFR-001 60 秒以内
- [ ] frame 11（fail_area）/ frame 135（片側 2 点）等で PNG が期待通り出力されることを目視確認
- [ ] pink_id=-1 のみのフレーム（JSON はあるが pink_id=1 なし）で「no pink_id=1 person」ラベルが表示されることを確認
- [ ] `--step 10` で 91 枚（ceil(900/10)）出力されることを確認
- [ ] `--frame-start 100 --frame-end 200` で 101 枚出力されることを確認
- [ ] 値域外引数（`--kpt-conf-min 1.5` 等）で exit code 2 を確認
- [ ] `scripts/README.md` に新規スクリプトのセクション追加
- [ ] CLAUDE.md / `docs/BACKLOG.md` の feat-049 を Closed に更新
