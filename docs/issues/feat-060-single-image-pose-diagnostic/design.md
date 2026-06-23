# feat-060 機能設計書: 静止画1枚のポーズ推定診断ツール

## 1.1 対応要求マッピング

| 要求ID | 設計セクション |
|--------|----------------|
| FR-001（YOLO検出経路） | 1.4 §A、1.7 `run_yolo_detection` |
| FR-002（全画像1BB経路） | 1.4 §B、1.7 `estimate_halpe26_fullframe_safe` |
| FR-003（可視化PNG） | 1.4 §C、1.7 `render_diagnostic_png` |
| FR-004（総合判定） | 1.4 §D、1.7 `print_verdict` |

## 1.2 システム構成

- 新規ファイル: `scripts/diagnose_pose.py`（本案件で追加する唯一のファイル）
- 依存（import、いずれも既存・無変更）:
  - `merge_halpe26`: `WB_CONFIG` / `WB_CHECKPOINT` / `AIC_CONFIG` / `AIC_CHECKPOINT` /
    `merge_to_halpe26` / `draw_halpe26` / `draw_bbox`
  - `ultralytics.YOLO`
  - `mmpose.apis.inference_top_down_pose_model` / `init_pose_model`
  - `mmpose.datasets.DatasetInfo`
  - `cv2` / `numpy` / `matplotlib`（Agg）
- 依存方向: `diagnose_pose.py` → 既存モジュール（一方向、循環なし）

```
scripts/
├── diagnose_pose.py        # 本案件で新規追加
├── merge_halpe26.py        # 再利用（無変更）
└── run_halpe26_pipeline_yolo11.py  # _resolve_device / process_yolo11_results を参考（import はしない）
```

注: `run_halpe26_pipeline_yolo11.py` からは関数を import せず、必要なロジック
（`_resolve_device` 相当・person 抽出）は本ファイルに自前で持つ。理由は ADR-3。

## 1.3 技術スタック

- Python 3.10.16 / 実行は `uv run python`
- MMPose 0.24.0、mmcv-full 1.7.2、ultralytics（YOLO11x）、OpenCV、numpy、matplotlib
- パッケージ管理: uv
- 選定理由: 既存パイプラインと同一スタックを流用し、診断結果が本番パイプラインの挙動と
  一致することを担保する。

## 1.4 各機能の詳細設計

### §A YOLO検出経路（FR-001）

#### データフロー
- 入力: 画像パス（str）→ `cv2.imread` → `frame`（np.ndarray, (H,W,3), uint8, BGR）
- 中間: `YOLO('checkpoints/yolo11x.pt')(frame, device=INTERNAL_DEVICE, verbose=False)`
  → `results[0].boxes`
- 出力: `person_boxes`（list[np.ndarray([x1,y1,x2,y2,score], float32)]）。
  cls==0（person）のみ抽出。

#### 処理ロジック
YOLO 推論呼び出しは ViTPose 側と同じ2分類で例外を畳み込む。
```
try:
    results = det_model(frame, device=INTERNAL_DEVICE, verbose=False)
    boxes = results[0].boxes
except torch.cuda.OutOfMemoryError:
    raise                          # 致命: main で [ERROR] exit 1
except Exception as e:
    print(f'[WARN] YOLO 推論例外: {type(e).__name__}: {e}')
    return [], 0                   # YOLO detection = FAILED、FR-002 へ続行
person_boxes_all = []  # 閾値適用前の全 person BB
for i in range(len(boxes)):
    if int(boxes.cls[i]) == 0:        # person クラス
        xyxy = boxes.xyxy[i].cpu().numpy()
        score = float(boxes.conf[i].cpu())
        person_boxes_all.append([*xyxy, score])
person_boxes = [b for b in person_boxes_all if b[4] >= bbox_thr]
person_boxes.sort(key=score 降順)
n_total = len(person_boxes_all); n_kept = len(person_boxes)
print 各 BB（n_kept 個）
yolo_success = n_kept >= 1
print 結論行（SUCCESS / FAILED）
```
- person クラス ID は 0 固定（`process_yolo11_results` と同値）。

#### エラーハンドリング
- YOLO チェックポイント不在 → `YOLO(...)` が例外 → main の try で捕捉し `[ERROR]` exit 1。
- YOLO 推論中の例外（OOM 以外）→ `[WARN]` ログ後 `([], 0)` 返却 → YOLO detection FAILED、
  FR-002 へ続行（診断目的のため切り分け結論を必ず出す）。
- YOLO 推論中の CUDA OOM → 再 raise → main で `[ERROR]` exit 1。
- 検出0個 → 例外ではない。FAILED として記録し後続へ進む（AC-001-2, AC-001-3）。

#### 境界条件
- person 0 個: `n_kept=0`、FAILED、空一覧。
- 全 BB が閾値未満: `n_total>0, n_kept=0`、FAILED、除外個数 `n_total` を報告。

### §B 全画像1BB経路（FR-002）

#### データフロー
- 入力: `frame`（§A と共有）。
- BB: `person = [{'bbox': np.array([0,0,W,H,1.0], dtype=float32)}]`
- 中間: WB 推論結果 `wb_results`、AIC 推論結果 `aic_results`
- 出力: `halpe26`（np.ndarray, (26,3), float, [x,y,conf]）または None（推論空時）

#### 処理ロジック（`estimate_halpe26_fullframe_safe`）
推論失敗を「空結果」と「例外」の両方で None に畳み込む。CUDA OOM だけは致命エラーとして
再 raise し、main 側で exit 1 にする（要求 1.4 信頼性の2分類）。
```
h, w = frame.shape[:2]
person = [{'bbox': np.array([0,0,w,h,1.0], np.float32)}]
try:
    wb_results, _  = inference_top_down_pose_model(wb_model, frame, person, bbox_thr=None,
                        format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)
    aic_results, _ = inference_top_down_pose_model(aic_model, frame, person, bbox_thr=None,
                        format='xyxy', dataset=aic_dataset, dataset_info=aic_dataset_info)
except torch.cuda.OutOfMemoryError:
    raise                            # ★ 致命: main で [ERROR] exit 1（要求 信頼性）
except Exception as e:
    print(f'[WARN] ViTPose 推論例外: {type(e).__name__}: {e}')
    return None                      # ★ 推論失敗: FAILED 記録（exit しない）
if len(wb_results) == 0 or len(aic_results) == 0:
    return None                      # ★ analyze_clothing_color.py は sys.exit(1)。
                                     #   診断では None を返し FAILED 記録（ADR-1, AC-002-2）
return merge_to_halpe26(wb_results[0]['keypoints'], aic_results[0]['keypoints'])
```
呼び出し側:
```
halpe26 = estimate_halpe26_fullframe_safe(...)
if halpe26 is None:
    vitpose_success = False; print FAILED（推論結果が空 or 推論例外）
else:
    print 全26点 index:name=(x,y,conf)   # 名前は HALPE26_NAMES（本ファイル定数）
    m = int((halpe26[:,2] > kpt_thr).sum())   # > で統一（draw_halpe26 と同判定、要求 FR-002）
    vitpose_success = m >= 1
    print 結論行（SUCCESS m/26 / FAILED 有効点0）
```
- `HALPE26_NAMES`: CLAUDE.md のHALPE26定義に対応する26要素の名称タプルを本ファイルに定義する。
- `torch` は本ファイル冒頭で `import torch`（OOM 型参照のため）。`torch.cuda.OutOfMemoryError`
  は CPU 実行時も型として参照可能（発生しないだけ）。

#### エラーハンドリング
- 推論結果が空（WB or AIC 0件）→ None 返却 → FAILED（exit しない、AC-002-2）。
- 推論中の例外（OOM 以外）→ `[WARN]` ログ後 None 返却 → FAILED（exit しない）。
- CUDA OOM → 再 raise → main で `[ERROR]` exit 1。
- モデルロード失敗 → main の try で `[ERROR]` exit 1。

#### 境界条件
- 全点 conf <= kpt_thr: `m=0`、FAILED、exit 0（AC-002-3）。26点の値自体は出力する。

### §C 可視化 PNG（FR-003）

#### データフロー
- 入力: `frame`、`person_boxes`（§A）、`halpe26`（§B、None 可）、`out_path`
- 出力: PNG ファイル1個（matplotlib, 1行2列）

#### 処理ロジック（`render_diagnostic_png`）
```
left  = frame.copy();  for b in person_boxes: left = draw_bbox(left, b, color=(0,255,0))
right = frame.copy()
# 全画像1BB枠は score 表示不要かつラベルが画像外（y1-5<0）になるため draw_bbox を使わず
# cv2.rectangle で枠のみ描く（中 レビュー指摘 #2）。シアン=(255,255,0) BGR。
cv2.rectangle(right, (0, 0), (W - 1, H - 1), (255, 255, 0), 2)
if halpe26 is not None: right = draw_halpe26(right, halpe26, kpt_thr=kpt_thr)
fig, axes = subplots(1, 2, figsize=(14, 7))
axes[0].imshow(cv2.cvtColor(left,  BGR2RGB));  axes[0].set_title(f'YOLO det ({n_kept} boxes)')
axes[1].imshow(cv2.cvtColor(right, BGR2RGB));  axes[1].set_title(右タイトル)
   # 右タイトル: halpe26 is None → 'fullframe 1BB: FAILED'、else → f'fullframe 1BB ({m}/26 kpts > thr)'
両 axis off; tight_layout; savefig(out_path, dpi=120); close
```
- `draw_bbox` / `draw_halpe26` は BGR を返すので imshow 前に `BGR2RGB` 変換する。
- `draw_halpe26` の描画判定は `>`（merge_halpe26.py:144）。FR-002 の有効点カウントと同判定で一致。

#### エラーハンドリング
- 保存失敗（IOError 等）: 既存ファイルがあれば `os.remove`、`[ERROR]` ログ、exit 1（AC-003-3）。
  実装は `analyze_clothing_color.py:render_analysis_png` 呼び出し側の try/except パターンに倣う。

#### 境界条件
- YOLO 0個: 左パネルは BB なしの素画像、右パネルは通常描画（AC-003-2）。
- `halpe26 is None`: 右パネルは全画像1BB枠のみ、タイトル `fullframe 1BB FAILED`。

### §D 総合判定（FR-004）

#### 処理ロジック（`print_verdict`）
```
if not vitpose_success:
    print '[VERDICT] ViTPose 自体が当該画像で推定失敗（YOLO の成否によらずポーズが出ない）'
elif not yolo_success:                 # vitpose_success == True
    print '[VERDICT] 原因は YOLO 検出失敗の可能性が高い（ViTPose は全画像1BBで推定成功）'
else:
    print '[VERDICT] 両経路とも成功。パイプライン側の閾値/連携を確認のこと'
```
- 分岐は vitpose_success を最優先（ViTPose 失敗なら YOLO 成否は判定に無関係）。

## 1.5 状態遷移

ステートフル処理なし（1パス・直線的実行）。該当なし。

## 1.6 ファイル・ディレクトリ設計

- 入力: 任意の画像パス（位置引数 1 個）。
- 出力 PNG: `--out` 指定時はその値。未指定時は `<画像stem>_pose_diagnostic.png`
  （`os.path.splitext(image)[0] + '_pose_diagnostic.png'`、入力画像と同一ディレクトリ）。
- 設定ファイルなし。

## 1.7 インターフェース定義

```python
# デバイス解決（重い import 前に実行。run_halpe26_pipeline_yolo11.py の _resolve_device と同仕様）
def _resolve_device(argv: list) -> str: ...   # 返り値 'cpu' or 'cuda:0'（内部固定）
# --device 不正時: 既存 _resolve_device は SystemExit(メッセージ) を raise する。本ツールでは
# 要求 1.4（device不正は [ERROR] exit 1）に合わせ、トップレベルで SystemExit を捕捉して
# [ERROR] 形式に整形してから sys.exit(1) する。
try:
    INTERNAL_DEVICE = _resolve_device(sys.argv)
except SystemExit as e:
    print(f'[ERROR] {e}')
    sys.exit(1)

def parse_args() -> argparse.Namespace: ...
    # images(位置, 1個) / --out(str,None) / --device(str,'cuda:0')
    # --bbox-thr(float,0.3,[0,1]) / --kpt-thr(float,0.3,[0,1])

def load_models(device: str) -> tuple: ...
    # 返り値 (wb_model, aic_model, wb_dataset, wb_dataset_info, aic_dataset, aic_dataset_info)
    # analyze_clothing_color.py:load_models と同一構造

def run_yolo_detection(det_model, frame: np.ndarray, bbox_thr: float
                       ) -> tuple[list[np.ndarray], int]: ...
    # 返り値 (person_boxes(閾値以上, score降順), n_total(閾値前総数))

def estimate_halpe26_fullframe_safe(
    wb_model, aic_model, frame: np.ndarray,
    wb_dataset: str, wb_dataset_info,
    aic_dataset: str, aic_dataset_info) -> np.ndarray | None: ...
    # 推論結果が空なら None（exit しない）

def render_diagnostic_png(frame: np.ndarray, person_boxes: list,
                          halpe26: np.ndarray | None, kpt_thr: float,
                          out_path: str) -> None: ...

def print_verdict(yolo_success: bool, vitpose_success: bool) -> None: ...

def main() -> None: ...
```

- 引数チェッカ `_check_thr`（[0.0,1.0]）を本ファイルに定義（`analyze_clothing_color.py:_check_conf`
  と同型。import せず自前定義 = ADR-3 と同方針で疎結合を保つ）。
- クラスは作らない（手続き的、1ファイル完結）。

## 1.8 ログ・デバッグ設計

- `print` ベース（既存スクリプトと統一、logging は使わない）。
- プレフィックス規約:
  - `[INFO]`: 進捗（画像読込、モデルロード、PNG保存）
  - `[RESULT]`: 各経路の成否結論行（FR-001 / FR-002）
  - `[VERDICT]`: 総合判定（FR-004）
  - `[WARN]`: 閾値未満で除外した BB がある等
  - `[ERROR]`: 致命的（画像読込不可・モデルロード失敗・PNG保存失敗・CUDA OOM・device不正）→ exit 1
- main のエラー分類（要求 1.4 信頼性に対応）:
  - 致命エラーは `main` 冒頭〜モデルロードの try と PNG 保存の try で捕捉し `[ERROR]` exit 1。
  - 推論失敗（空・OOM以外の例外）は `estimate_halpe26_fullframe_safe` 内で None に畳み込み、
    FAILED 記録 → exit 0。main に包括 `except: exit 1` は置かない（FAILED が握り潰されるため）。
- フォーマット: `[LEVEL] メッセージ`（既存スクリプトと同形式）。

## 設計判断の記録（ADR）

- **ADR-1: 推論空時に exit せず None 返却**
  - 採用: `estimate_halpe26_fullframe_safe` は WB/AIC が空のとき None を返す。
  - 却下: `analyze_clothing_color.py:estimate_halpe26_fullframe` をそのまま import 再利用
    （空時 `sys.exit(1)`）。診断ツールは「空だった」事実を FR-002 FAILED / FR-004 判定に
    使うため、exit されると切り分け結論が出せない。よって流用せず分離実装する。

- **ADR-2: 可視化は matplotlib 2パネル**
  - 採用: 左=YOLO検出、右=全画像1BB推論 を1枚に並べ、両経路を一目で比較可能にする。
  - 却下: cv2.imwrite で2枚別ファイル。比較しづらく FR-003 の意図（並置）に反する。

- **ADR-3: run_halpe26_pipeline_yolo11.py から関数 import しない**
  - 採用: `_resolve_device` 相当・person 抽出ロジックは本ファイルに自前で持つ（コピー）。
  - 却下: 同ファイルから import。同ファイルはトップレベルで `_resolve_device(sys.argv)` を
    実行し YOLO/mmpose を import する副作用を持つため、import すると診断ツールの引数解釈と
    競合し得る。疎結合のため自前定義する（重複は数十行で許容範囲）。

- **ADR-4: モノクロ3ch化の明示処理を入れない**
  - 採用: `cv2.imread` の既定（IMREAD_COLOR, 3ch化）に委ねる。
  - 却下: 1ch→3ch複製の明示処理。imread 既定で 3ch になるため不要。要求 1.5 の通り本案件
    対象外（ユーザー選択）。
