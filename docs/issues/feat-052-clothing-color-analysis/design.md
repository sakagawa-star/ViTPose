# feat-052 機能設計書: 服パッチ静止画からの服色特徴量分析・HSVレンジ提案ツール

作成日: 2026-05-26
準拠: `docs/DESIGN_STANDARD.md`
対象成果物: `scripts/analyze_clothing_color.py`（新規）

---

## 1.1 対応要求マッピング

| 要求ID | 設計セクション |
|--------|----------------|
| FR-001 静止画ポーズ推定 | 1.4.1, 1.7 `load_models` / `estimate_halpe26_fullframe` |
| FR-002 胴体ROI構築 | 1.4.2, 1.7 `build_torso_roi`（`build_keypoint_rect_roi` 再利用） |
| FR-003 ROI内色測定 | 1.4.3, 1.7 `compute_hsv_stats` |
| FR-004 可視化PNG出力 | 1.4.4, 1.7 `render_analysis_png` |
| FR-005 推奨HSVレンジ算出・提示 | 1.4.5, 1.7 `propose_hsv_ranges` / `compute_ratio_for_ranges` |
| FR-006 CLI引数 | 1.6, 1.7 `parse_args` |
| FR-007 ROI構築失敗フォールバック | 1.4.2（処理ロジック内）、1.4.6 |

## 1.2 システム構成

- **単一スクリプト**: `scripts/analyze_clothing_color.py`
- **モジュール依存（呼び出し方向）**:
  - `analyze_clothing_color` → `merge_halpe26`（`WB_CONFIG`/`WB_CHECKPOINT`/`AIC_CONFIG`/`AIC_CHECKPOINT`/`merge_to_halpe26`。可視化は matplotlib で行うため `draw_halpe26`/`draw_bbox` は使わない）
  - `analyze_clothing_color` → `postprocess_pink_id`（`build_keypoint_rect_roi`/`compute_pink_ratio`/`FIXED_HSV_RANGES`/`TORSO_KEYPOINT_INDICES`）
  - `analyze_clothing_color` → `mmpose.apis`（`inference_top_down_pose_model`/`init_pose_model`）、`mmpose.datasets.DatasetInfo`
  - 逆依存なし。既存2モジュール（`merge_halpe26` / `postprocess_pink_id`）は**一切変更しない**
- **import 方式**: `scripts/` 内相対 import（既存 `run_halpe26_pipeline_yolo11.py` が `from merge_halpe26 import ...` とする方式に倣う。`scripts/` をカレントに実行）

## 1.3 技術スタック

- 言語: Python 3.10.16（uv 管理、`uv run python` で実行）
- ライブラリ:
  - MMPose 0.24.0（`inference_top_down_pose_model`, `init_pose_model`, `DatasetInfo`）
  - OpenCV（cv2）— 画像 I/O・HSV変換・矩形描画
  - NumPy — 配列演算・パーセンタイル・循環統計
  - Matplotlib 3.10.9（導入確認済み）— ヒストグラム・合成PNG描画
- 選定理由: 既存 HALPE26 パイプライン資産（`merge_halpe26` / `postprocess_pink_id`）を再利用し、推論・ROI・pink_ratio ロジックの重複実装を避ける。Matplotlib は feat-040 `plot_pink_ratio_timeline.py` で使用実績あり

## 1.4 各機能の詳細設計

### 1.4.1 FR-001 静止画ポーズ推定

**データフロー**
- 入力: 画像パス（str）→ `cv2.imread` → `frame: np.ndarray, shape=(H,W,3), dtype=uint8, BGR`
- 画像全体BB: `np.array([0, 0, W, H, 1.0], dtype=np.float32)`（W=frame.shape[1], H=frame.shape[0]）
- 中間: `wb_results[0]['keypoints']: (133,3)`, `aic_results[0]['keypoints']: (14,3)`
- 出力: `halpe26: np.ndarray, shape=(26,3), [x, y, conf]`

**処理ロジック**
1. `frame = cv2.imread(image_path)`。`None` なら FileError（1.4.6）
2. `H, W = frame.shape[:2]`
3. `person = [{'bbox': np.array([0,0,W,H,1.0], dtype=np.float32)}]`
4. `wb_results, _ = inference_top_down_pose_model(wb_model, frame, person, bbox_thr=None, format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)`
5. `aic_results, _ = inference_top_down_pose_model(aic_model, frame, person, ...同様...)`
6. `wb_results`/`aic_results` のいずれかが空なら InferenceError（1.4.6）。通常 `bbox_thr=None` かつ明示BBのため必ず1件返る
7. `halpe26 = merge_to_halpe26(wb_results[0]['keypoints'], aic_results[0]['keypoints'])`

**境界条件**: 画像が極端に小さい場合も全体BBで推論は実行される。キーポイント信頼度が低い場合は FR-002/FR-007 で処理

### 1.4.2 FR-002 胴体ROI構築（＋FR-007 フォールバック）

**データフロー**
- 入力: `halpe26 (26,3)`, `W`, `H`, `conf_min: float`, `area_min: int`
- 中間: `kpts_flat = halpe26.flatten().tolist()`（`len == 78`。`build_keypoint_rect_roi` は `len >= 78` を要求）
- 出力: `roi_box: tuple[int,int,int,int] = (x1,y1,x2,y2)`, `roi_source: str ∈ {"torso", "fullframe"}`

**処理ロジック**
1. `kpts_flat = halpe26.flatten().tolist()`
2. `box, status = build_keypoint_rect_roi(kpts_flat, W, H, conf_min, area_min)`
3. `status == "ok"` の場合: `roi_box = box`, `roi_source = "torso"`
4. `status != "ok"`（"fail_kpt" / "fail_area"）の場合（FR-007）:
   - 警告 print: `f"[WARN] 胴体ROI構築失敗 (status={status})。画像全体をROIとして測定します"`
   - `roi_box = (0, 0, W, H)`, `roi_source = "fullframe"`（スライス `frame[0:H, 0:W]` で真の画像全体。torso ケースの `roi_box` は `build_keypoint_rect_roi`→`clip_bbox` で width-1/height-1 にクリップされるが、既存 `postprocess_pink_id.py` と同一規約のため整合）

**境界条件**: 胴体4点のうち信頼点が2点未満 → "fail_kpt" → fullframe フォールバック。面積 < area_min → "fail_area" → fullframe フォールバック

### 1.4.3 FR-003 ROI内色測定（出力a）

**データフロー**
- 入力: `roi_bgr = frame[y1:y2, x1:x2]`（`shape=(h,w,3), BGR`）、`sat_min: int`, `val_min: int`, `percentile: float`
- 中間: `hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)`（H:[0,179], S:[0,255], V:[0,255]）、無彩色除外マスク `chroma_mask = (S >= sat_min) & (V >= val_min)`
- 出力（dict）: `{H_lo, H_med, H_hi, S_lo, S_med, S_hi, V_lo, V_med, V_hi}`（各 int。`n_chroma==0` のときは 9 キーすべて `None`）、`chroma_ratio: float`（`n_chroma==0` のとき 0.0）、`Hc`/`Sc`/`Vc`（有彩色画素の1次元 np.ndarray。`render_analysis_png` のヒストグラム描画用。`n_chroma==0` なら空配列）。`current_ratio` は本関数の戻り dict に**含めない**（`main` が別途算出。下記 step5）

**処理ロジック**
1. `Hc, Sc, Vc, chroma_ratio = extract_chroma_hsv(roi_bgr, sat_min, val_min)`（1.7 の共用ヘルパ。HSV変換・無彩色除外マスク `(S>=sat_min)&(V>=val_min)`・有彩色画素抽出・chroma_ratio 算出を一括。`propose_hsv_ranges` と同一ヘルパを使い二重実装を排除）
2. `n_chroma = len(Hc)`
3. `n_chroma > 0` の場合: 有彩色画素 H/S/V のパーセンタイル `p_low=percentile, p_med=50, p_high=100-percentile` を算出（H は循環非考慮の単純パーセンタイルで「分布把握用」に表示。レンジ算出は 1.4.5 で循環処理）。本関数が返す `S_lo`/`V_lo` は 1.4.5 の `s_lo`/`v_lo` と同一の `Sc`/`Vc`・同一 percentile から算出するため定義上一致する
4. `n_chroma == 0` の場合: H/S/V 統計は `None` 扱いで表示し、推奨レンジ算出（1.4.5）はスキップ（境界条件）
5. `current_ratio` は `compute_hsv_stats` の責務外とし、`main` が別途 `compute_pink_ratio(roi_bgr)` で算出する（**再利用**。現状 `FIXED_HSV_RANGES` をグローバル参照。一般化版 `compute_ratio_for_ranges` に `FIXED_HSV_RANGES` を渡すのではなく、既存ロジックを忠実に再現するため既存関数を直接使う）

**境界条件**: `n_chroma == 0`（白服・暗所で有彩色画素なし）→ 統計 None、推奨レンジ算出不可の旨を出力し現状 pink_ratio のみ報告

### 1.4.4 FR-004 可視化PNG出力

**データフロー**
- 入力: `frame`（BGR）、`roi_box`、現状レンジ・推奨レンジ、HSV統計、`current_ratio`、`proposed_ratio`、`out_path`
- 出力: PNG ファイル（`out_path`）

**処理ロジック**（Matplotlib、2行×3列の subplot）
1. `(0,0)` 元画像: `cv2.cvtColor(frame, COLOR_BGR2RGB)` を `imshow`、`roi_box` を `matplotlib.patches.Rectangle`(edgecolor='lime', fill=False) で重畳
2. `(0,1)` 現状レンジマスク: `build_mask_for_ranges(roi_bgr, FIXED_HSV_RANGES)`（1.7）を `imshow(cmap='gray')`、タイトル `f"current ratio={current_ratio:.4f}"`
3. `(0,2)` 推奨レンジマスク: `build_mask_for_ranges(roi_bgr, proposed_ranges)`（1.7）を同様に、タイトル `f"proposed ratio={proposed_ratio:.4f}"`
4. `(1,0)/(1,1)/(1,2)` H/S/V ヒストグラム: 有彩色画素の各チャンネルを `hist`（H は bins=180、S/V は bins=256）、推奨レンジの下限/上限を縦線で重畳
5. `figure.suptitle` または下部 `figtext` に推奨 `FIXED_HSV_RANGES`・S下限/V下限・ビフォーアフター ratio を記載
6. `fig.savefig(out_path, dpi=120, bbox_inches='tight')`、`plt.close(fig)`

**エラーハンドリング**: 保存失敗（権限・パス不正）は IOError として 1.4.6。推奨レンジが空（`n_chroma==0`）の場合は `(0,2)` を空マスク＋"N/A" 表示、`(1,*)` は空表示（`stats` の H/S/V 9キーが `None` のためヒストグラム・推奨レンジ縦線の描画をスキップする）

### 1.4.5 FR-005 推奨HSVレンジ算出・提示（出力b）

**データフロー**
- 入力: `roi_bgr`、`sat_min`, `val_min`, `percentile`
- 中間: 有彩色画素の `Hc, Sc, Vc`、循環平均中心 `H_center`、相対角度パーセンタイル
- 出力: `proposed_ranges: list[tuple[tuple[int,int,int],tuple[int,int,int]]]`（1〜2要素）、`s_lo: int`, `v_lo: int`、`proposed_ratio: float`

**処理ロジック（循環統計による色相環対応）**

H は色相環（OpenCV H:[0,179] が 0〜360° を表す＝実角度 = H×2°）。赤・ピンクは H=0 境界の両側に分布するため、**循環平均を中心に相対化**してからパーセンタイルを取る。

```
# Hc, Sc, Vc は extract_chroma_hsv(roi_bgr, sat_min, val_min) で取得（1.4.3 と共用）
theta = Hc.astype(float) * 2.0 * pi / 180.0          # ラジアン
H_center = (atan2(mean(sin theta), mean(cos theta)) * 180 / (2*pi)) % 180  # [0,180)
if H_center >= 180.0:   # 浮動小数点誤差で raw が微小負値だと % が 180.0 を返す稀なケースを 0 へ正規化
    H_center = 0.0
rel = ((Hc.astype(float) - H_center + 90.0) % 180.0) - 90.0   # [-90, 90)
rel_lo = percentile(rel, percentile)        # 例 5%
rel_hi = percentile(rel, 100.0 - percentile)# 例 95%
H_lo = H_center + rel_lo     # 0未満/179超を取りうる
H_hi = H_center + rel_hi
s_lo = int(round(percentile(Sc, percentile)))   # S下限のみデータ駆動
v_lo = int(round(percentile(Vc, percentile)))   # V下限のみデータ駆動
```

レンジ構築（S/V 上限は 255 固定。ADR-4）:
```
H_lo_i, H_hi_i = int(round(H_lo)), int(round(H_hi))
if 0 <= H_lo_i and H_hi_i <= 179:
    # 色相環をまたがない → 1レンジ
    proposed = [((H_lo_i, s_lo, v_lo), (H_hi_i, 255, 255))]
elif H_lo_i < 0:
    # 下端が179側へ回り込む（赤・ピンク） → 2レンジ
    proposed = [((0, s_lo, v_lo), (H_hi_i, 255, 255)),
                ((180 + H_lo_i, s_lo, v_lo), (179, 255, 255))]
else:  # H_hi_i > 179: 上端が0側へ回り込む
    proposed = [((H_lo_i, s_lo, v_lo), (179, 255, 255)),
                ((0, s_lo, v_lo), (H_hi_i - 180, 255, 255))]
proposed = [r for r in proposed if r[0][0] <= r[1][0]]  # 反転タプル(lo>hi)を破棄（下記「境界条件」参照）
proposed_ratio = compute_ratio_for_ranges(roi_bgr, proposed)  # proposed=[] なら 0.0
```

**`compute_ratio_for_ranges(roi_bgr, ranges)`**: `compute_pink_ratio` の一般化版（任意レンジを引数で受ける）。`compute_pink_ratio` は `FIXED_HSV_RANGES` グローバル固定のため推奨レンジに使えず、本ツールに新規実装する。内部で `build_mask_for_ranges(roi_bgr, ranges)`（1.7）を呼び、得たマスクの 非ゼロ画素 / 全画素 を返す。マスク生成ロジックは `compute_pink_ratio`（`postprocess_pink_id.py:70-83`）と同一（各レンジで `cv2.inRange` → OR 合成）

**出力（コンソール）**: 推奨 `FIXED_HSV_RANGES` を Python literal で print、`s_lo`/`v_lo`、`current_ratio`（before）/`proposed_ratio`（after）を小数4桁、MIN_PINK_RATIO 注記を print

**境界条件**: `n_chroma == 0` → `proposed = []`, `proposed_ratio = 0.0`、「推奨レンジ算出不可（有彩色画素なし）」を print。また、レンジ構築後に各タプルで `lo[0] <= hi[0]`（H下限 <= H上限）を満たさないレンジは破棄する（循環平均の強い非対称分布で稀に `rel_lo > 0` 等となり反転タプルが生じ得るため）。全レンジ破棄時は `proposed = []`, `proposed_ratio = 0.0` とし `n_chroma == 0` と同じ縮退表示にする

### 1.4.6 エラーハンドリング一覧

| エラー | 検出方法 | 処理 |
|--------|----------|------|
| 入力画像読込失敗 | `cv2.imread` が `None` | `[ERROR]` print、`sys.exit(1)` |
| モデルチェックポイント欠如 | `init_pose_model` が例外 | 例外メッセージを `[ERROR]` print、`sys.exit(1)` |
| 推論結果が空 | `len(wb_results)==0 or len(aic_results)==0` | `[ERROR]` print、`sys.exit(1)` |
| 胴体ROI構築失敗 | `status != "ok"` | `[WARN]` print、画像全体へフォールバック（FR-007、継続） |
| 有彩色画素ゼロ | `n_chroma == 0` | `[WARN]` print、推奨レンジ算出スキップ、現状 ratio のみ報告（継続） |
| PNG保存失敗 | `savefig` 例外 | `[ERROR]` print、`out_path` が存在すれば削除（不完全ファイルを残さない）、`sys.exit(1)` |
| CLI引数範囲外 | `parse_args` の型チェック関数 | argparse エラー、`sys.exit(2)` |

## 1.5 状態遷移

GUI を持たないステートレスな単発 CLI のため、状態遷移は**該当なし**。処理は「読込 → 推論 → ROI → 測定 → 提案 → 描画 → 終了」の一方向シーケンシャル実行。

## 1.6 ファイル・ディレクトリ設計

- 入力: 任意パスの静止画（位置引数 `image`）
- 出力PNG: `--out` 指定。デフォルトは入力画像と同ディレクトリ・同 stem に `_color_analysis.png` 付与（例: `testdata/E0014-01.png` → `testdata/E0014-01_color_analysis.png`）
- 設定ファイル: なし（全てCLI引数）
- 標準出力: 測定値・推奨レンジ・ビフォーアフターを人間可読テキストで出力

## 1.7 インターフェース定義

```python
def parse_args() -> argparse.Namespace: ...
#   image(位置), --out, --device='cuda:0', --kpt-conf-min=0.3,
#   --min-roi-area=200, --percentile=5.0, --sat-min=20, --val-min=60
#   範囲チェックは本スクリプトに新規定義する以下のヘルパを argparse の type= に渡して実施する
#   （既存 postprocess_pink_id.py の同名関数は import せず独立させる。ADR-6）:
#     _check_conf(v)       -> float : 値域 [0.0, 1.0]    （--kpt-conf-min 用）
#     _check_area(v)       -> int   : 値域 >=1, 既定200   （--min-roi-area 用）
#     _check_percentile(v) -> float : 値域 [0.0, 50.0]   （--percentile 用）
#     _check_uint8(v)      -> int   : 値域 [0, 255]      （--sat-min / --val-min 用）
#   範囲外は argparse.ArgumentTypeError を送出し sys.exit(2)

def load_models(device: str) -> tuple:
    """戻り値: (wb_model, aic_model, wb_dataset, wb_dataset_info,
                aic_dataset, aic_dataset_info)。merge_halpe26 の定数を使用"""

def estimate_halpe26_fullframe(
    wb_model, aic_model, frame: np.ndarray,
    wb_dataset: str, wb_dataset_info,
    aic_dataset: str, aic_dataset_info,
) -> np.ndarray:
    """画像全体1BBで推論し halpe26 (26,3) を返す"""

def build_torso_roi(
    halpe26: np.ndarray, width: int, height: int,
    conf_min: float, area_min: int,
) -> tuple[tuple[int, int, int, int], str]:
    """build_keypoint_rect_roi を呼び、失敗時は全体ROIへフォールバック。
       戻り値: (roi_box, roi_source ∈ {'torso','fullframe'})"""

def compute_hsv_stats(
    roi_bgr: np.ndarray, sat_min: int, val_min: int, percentile: float,
) -> dict:
    """H/S/V パーセンタイル・chroma_ratio・有彩色画素配列 Hc/Sc/Vc（ヒストグラム描画用）を
       返す（current_ratio は呼び出し側で）"""

def extract_chroma_hsv(
    roi_bgr: np.ndarray, sat_min: int, val_min: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """roi_bgr を HSV 変換し、無彩色除外マスク (S>=sat_min)&(V>=val_min) を適用した
       有彩色画素の Hc, Sc, Vc（各1次元 np.ndarray）と chroma_ratio(float) を返す。
       compute_hsv_stats と propose_hsv_ranges が共用し、chromaマスク/有彩色抽出の
       二重実装を避ける（M-4 対応）"""

def build_mask_for_ranges(
    roi_bgr: np.ndarray,
    ranges: list[tuple[tuple[int, int, int], tuple[int, int, int]]],
) -> np.ndarray:
    """各レンジで cv2.inRange → OR 合成した2値マスク (uint8, shape=(h,w)) を返す。
       ranges 空なら全0マスク。compute_ratio_for_ranges と render_analysis_png が共用"""

def compute_ratio_for_ranges(
    roi_bgr: np.ndarray,
    ranges: list[tuple[tuple[int, int, int], tuple[int, int, int]]],
) -> float:
    """compute_pink_ratio の一般化版（任意レンジ）。build_mask_for_ranges を呼び
       非ゼロ画素/全画素を返す。ranges 空なら 0.0"""

def propose_hsv_ranges(
    roi_bgr: np.ndarray, sat_min: int, val_min: int, percentile: float,
) -> tuple[list, int, int, float]:
    """戻り値: (proposed_ranges, s_lo, v_lo, proposed_ratio)"""

def render_analysis_png(
    frame: np.ndarray, roi_box: tuple, stats: dict,
    proposed_ranges: list, current_ratio: float, proposed_ratio: float,
    out_path: str,
) -> None: ...

def main() -> None: ...
```

- 1関数1責務。`main` がオーケストレーションのみ担当

## 1.8 ログ・デバッグ設計

- ライブラリ `logging` は使わず、既存スクリプト（`postprocess_pink_id.py` 等）に倣い `print` で統一
- 出力ポイント（INFO相当、接頭辞なしまたは `[INFO]`）: モデルロード開始/完了、ROI構築結果（`roi_source`/`roi_box`）、chroma_ratio、current_ratio、proposed_ratio、推奨レンジ、PNG保存先
- `[WARN]`: ROIフォールバック発動、有彩色画素ゼロ
- `[ERROR]`: 1.4.6 のエラー（直後に `sys.exit`）

## 設計判断の記録（ADR）

- **ADR-1 推論経路**: 採用＝WB+AIC→`merge_to_halpe26`→HALPE26（`method_a` 完全踏襲）。却下＝WBのみ。理由: 胴体4点は WB だけでも取れるが、`build_keypoint_rect_roi` が HALPE26 前提（len>=78）で、既存推論経路と完全一致させる方が一貫性が高く、静止画1枚なら AIC 推論コストは無視できる
- **ADR-2 色相環対応**: 採用＝循環平均中心の相対角度パーセンタイル。却下＝固定シフト（H>90→H-180、赤専用ヒューリスティック）。理由: 循環平均は任意色相（赤・青・緑）で数学的に正しく中心化でき、将来の青・白対象対応（Could）の布石になる。事前実測の固定シフトはピンクでは同結果だが汎用性を欠く
- **ADR-3 ROI失敗時**: 採用＝画像全体フォールバック＋警告。却下＝エラー停止。理由: 診断ツールであり「測れないより測る」。フォールバックは `roi_source='fullframe'` として出力に明示し、利用者が品質を判断できる
- **ADR-4 S/V上限**: 採用＝255固定（下限のみデータ駆動）。却下＝S/V上限もデータ駆動。理由: 現状 `FIXED_HSV_RANGES` も上限255。彩度・明度の上限を絞ると、同色でより鮮やか/明るい画素を取りこぼす。下限のみが「淡い服を拾う/拾わない」を分ける意味のあるパラメータ
- **ADR-5 推奨レンジ pink_ratio 算出**: 採用＝`compute_ratio_for_ranges`（一般化版）を新規実装。却下＝`compute_pink_ratio` 流用。理由: `compute_pink_ratio` は `FIXED_HSV_RANGES` をグローバル固定参照しており任意レンジを渡せない。既存関数を変更しない制約（FR-1.5）下では一般化版の新規実装が必要
- **ADR-6 CLI引数チェッカ**: 採用＝本スクリプトに `_check_conf`/`_check_area`/`_check_percentile`/`_check_uint8` を新規定義。却下＝`postprocess_pink_id.py` の `_check_*` を import 流用。理由: 本ツール独自の値域（`--percentile` [0.0,50.0]、`--sat-min`/`--val-min` [0,255]）は既存チェッカになく、既存の CLI 都合に縛られず独立性を保つため。`--min-roi-area` は既存 `build_keypoint_rect_roi` と整合させ下限>=1・既定200とし、`area_min=0` による `fail_area` 無効化を防ぐ

---

注: 本設計書のコードスニペットは意図伝達が目的であり、そのままのコピー利用を前提としない（DESIGN_STANDARD 2.3）。
