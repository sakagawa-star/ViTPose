# feat-061 機能設計書: YOLO 検出ゼロ時の固定 ROI フォールバック

## 1.1 対応要求マッピング

| 要求ID | 設計セクション |
|--------|----------------|
| FR-001（CLI 指定） | 1.4 §A、1.7 `parse_args` |
| FR-002（座標検証） | 1.4 §B、1.7 `check_fallback_roi_basic` / `clip_fallback_roi` |
| FR-003（注入本体） | 1.4 §C、1.7 フレームループ改修 |
| FR-004（集計ログ） | 1.4 §D |
| FR-005（fallback フィールド） | 1.4 §E、1.7 `halpe26_to_openpose_json` |

## 1.2 システム構成

- 改修対象: `scripts/run_halpe26_pipeline_yolo11.py`（本体）と
  `scripts/halpe26_to_openpose.py`（`halpe26_to_openpose_json` への引数追加のみ）。
- 追加要素:
  - CLI 引数 `--fallback-roi`（int×4, nargs=4, 既定 None）、`--fallback-score`（float, 既定 1.0）
  - 新規関数 `check_fallback_roi_basic(roi) -> None`（基本検証、モデルロード前）
  - 新規関数 `clip_fallback_roi(roi, width, height) -> list[int]`（クリップ検証、動画サイズ後）
  - フレームループ内の検出ゼロ判定 + 注入ブロック（既存 5a の直後）
  - 発動カウンタ `fallback_count` とサマリ出力
  - main の処理順組み替え（動画 open をモデル初期化より前へ移動し、ROI 検証をモデルロード前に完了）
  - `halpe26_to_openpose.py`: `halpe26_to_openpose_json` に任意引数 `fallback_flags` を追加
- 依存方向: 既存 import に変更なし。新規ライブラリ追加なし。

```
scripts/
└── run_halpe26_pipeline_yolo11.py  # 本案件で改修
```

## 1.3 技術スタック

- Python 3.10.16 / 実行は `uv run python`
- ultralytics（YOLO11x）、MMPose 0.24.0、mmcv-full 1.7.2、OpenCV、numpy（いずれも既存）
- 新規依存なし。選定理由: 既存パイプライン内の局所改修であり、追加ライブラリ不要。

## 1.4 各機能の詳細設計

### §A CLI 指定（FR-001）

#### データフロー
- `--fallback-roi`: `nargs=4, type=int, default=None` → `args.fallback_roi` は
  `None` または `[x1, y1, x2, y2]`（list[int]）。
- `--fallback-score`: `type=float, default=1.0`、チェッカで [0.0, 1.0] を検証。

#### 処理ロジック
```
parser.add_argument('--fallback-roi', type=int, nargs=4, default=None,
                    metavar=('X1', 'Y1', 'X2', 'Y2'),
                    help='YOLO 検出ゼロフレームに流す固定 ROI（未指定で無効）')
parser.add_argument('--fallback-score', type=_check_thr, default=1.0,
                    help='フォールバック注入 BB の bbox_score（既定 1.0）')
```
- `_check_thr`: float を [0.0, 1.0] で検証する argparse type 関数を本ファイルに新規定義
  （範囲外は `argparse.ArgumentTypeError`）。
- 起動時、`args.fallback_roi is not None` なら 1 行ログ:
  `print(f'Fallback ROI: {roi}, score: {args.fallback_score}')`（検証・クリップ後の値）。

#### 境界条件
- 未指定（None）: 後続の検証・注入を一切行わない（既存挙動と完全一致、AC-001-1）。

### §B 座標検証（FR-002）

#### データフロー
- 入力: `roi`（list[int] 4 値）、`width`・`height`（動画フレームサイズ、`cap` から取得済み）。
- 出力: クリップ済み `[x1, y1, x2, y2]`（list[int]）。違反時は `SystemExit`。

#### 処理ロジック（2 段検証）
検証は 2 段に分け、**基本検証はモデルロード前**、**クリップ検証は動画サイズ取得後**に実行する。
これにより不正 ROI がモデルロード失敗・CUDA OOM に隠されない（中レビュー指摘 #2）。

```
def check_fallback_roi_basic(roi):   # モデルロード前（main 冒頭、parse_args 直後）
    x1, y1, x2, y2 = roi
    if min(x1, y1, x2, y2) < 0:
        print(f'[ERROR] fallback-roi に負値: {roi}'); sys.exit(1)
    if x1 >= x2 or y1 >= y2:
        print(f'[ERROR] fallback-roi は x1<x2 かつ y1<y2 が必要: {roi}'); sys.exit(1)

def clip_fallback_roi(roi, width, height):   # 動画サイズ取得後、フレームループ前
    x1, y1, x2, y2 = roi
    cx1, cy1 = max(0, x1), max(0, y1)
    cx2, cy2 = min(width, x2), min(height, y2)
    if [cx1, cy1, cx2, cy2] != [x1, y1, x2, y2]:
        print(f'[WARN] fallback-roi を画像範囲にクリップ: {roi} -> {[cx1,cy1,cx2,cy2]}')
    if cx1 >= cx2 or cy1 >= cy2:
        print(f'[ERROR] クリップ後の fallback-roi が縮退: {[cx1,cy1,cx2,cy2]}'); sys.exit(1)
    return [cx1, cy1, cx2, cy2]
```

main での呼び出し順（ADR-4）。**ROI 検証（基本＋クリップ縮退）を両方ともモデル初期化より前に
完了**させるため、現行 main の「モデル初期化 → 出力先 → 動画 open」の順を組み替え、動画 open を
モデル初期化より前へ移す:
1. `args = parse_args()`
2. `if args.fallback_roi is not None: check_fallback_roi_basic(args.fallback_roi)`  ← モデルロード前（非負・大小）
3. 動画 open・`width`/`height` 取得（`cap = cv2.VideoCapture(...)`、`assert cap.isOpened()`）
4. `fallback_roi = clip_fallback_roi(args.fallback_roi, width, height) if args.fallback_roi is not None else None`  ← モデルロード前（クリップ縮退）
5. モデル初期化（`YOLO(...)` / `init_pose_model(...)`）
6. 出力先作成（`os.makedirs` / `VideoWriter` / json_dir）
7. フレームループ

注: 動画 open とモデル初期化に相互依存はなく、順序入れ替えで出力 JSON・動画の内容は不変
（起動ログの行順のみ変わる）。AC-001-1 は出力ファイルの `diff` 一致を見るのでログ順は無関係。

#### エラーハンドリング
- 負値・`x1>=x2`・`y1>=y2`・クリップ後縮退 → `[ERROR]` ログ + `sys.exit(1)`（AC-002-1, AC-002-3）。
- 画像はみ出し → クリップ + `[WARN]`（AC-002-2、致命ではない）。

#### 境界条件
- ROI が画像と完全一致（`[0,0,W,H]`）: クリップ不要、`[WARN]` なし、そのまま採用。

### §C 注入本体（FR-003）

#### データフロー
- 入力: `bbox_thr` フィルタ後の `person_results`（list[dict]、空の可能性あり）、
  検証済み `fallback_roi`（list[int] または None）、`args.fallback_score`（float）。
- 出力: 注入後の `person_results`（検出ゼロ かつ ROI 指定時のみ 1 要素を持つ）。

#### 処理ロジック（既存 5a の直後、5b の直前に挿入）
既存コード（line 282-283）:
```
person_results = process_yolo11_results(yolo_results[0])
person_results = [p for p in person_results if p['bbox'][4] >= args.bbox_thr]
```
の直後に挿入（YOLO 呼び出し `det_model(frame, ...)` の `conf` は無変更=既定 0.25 のまま。
よって `person_results` 空判定は「既定 conf 適用後 + `bbox_thr` フィルタ後に 0 件」を意味する。ADR-5）:
```
is_fallback_frame = False                      # 各フレーム先頭で False に初期化
...
if fallback_roi is not None and len(person_results) == 0:
    x1, y1, x2, y2 = fallback_roi
    person_results = [{'bbox': np.array(
        [x1, y1, x2, y2, args.fallback_score], dtype=np.float32)}]
    fallback_count += 1
    is_fallback_frame = True                    # 5f の fallback_flags 生成に使う（§E）
```
- 以降の 5b（WB）・5c（AIC）・5d（merge）・5d2（dedup）・5e（draw）は無変更。5f（JSON）は §E で
  `fallback_flags` を渡す形に変更する。注入 BB は 1 個のため 5d2 の `n_persons >= 2` 条件に
  非該当で素通りし、`len(all_halpe26)` は 1 のまま。
- `fallback_count` は frame_idx 初期化付近で `fallback_count = 0` として宣言する。
- `is_fallback_frame` は各フレームループ先頭（5a の前）で `False` に初期化する。

#### エラーハンドリング
- 注入後の WB/AIC が空になるケース: 既存パイプラインの挙動（`wb_results`/`aic_results` の
  件数で `all_halpe26` を構築）に委ねる。本案件で新たな例外処理は追加しない
  （`bbox_thr=None` の top-down 推論は与えた BB ごとに必ず結果を返すため、注入 1 個に対し
  WB/AIC とも 1 件を返す）。

#### 境界条件
- 検出ゼロ かつ ROI 未指定: 注入なし。`person_results` 空のまま既存処理（`all_halpe26=[]`、
  `people` 空の JSON）→ 改修前と一致（AC-003-3）。
- 検出 1 件以上: 注入条件 `len(person_results)==0` が偽 → 注入なし（AC-003-2）。

### §D 集計ログ（FR-004）

#### 処理ロジック
- フレームループ後、既存の「Saved ...」ログ群の付近に追加:
```
if fallback_roi is not None:
    print(f'Fallback applied to {fallback_count} / {frame_idx} frames')
```
- `--fallback-roi` 未指定（`fallback_roi is None`）時は出力しない（AC-004-2）。

### §E `fallback` フィールド付与（FR-005）

#### データフロー
- 入力: `is_fallback_frame`（bool、§C）、`all_halpe26`（dedup 後、注入フレームは長さ 1）。
- 出力: 注入フレームの JSON `people[*]` に `"fallback": true`。非注入フレームは当該キーなし。

#### 処理ロジック

(1) `halpe26_to_openpose.py` の `halpe26_to_openpose_json` に任意引数を追加（既存
`stable_ids` と同パターン、デフォルト None で後方互換）:
```
def halpe26_to_openpose_json(all_halpe26, bbox_scores=None, bboxes=None,
                             stable_ids=None, fallback_flags=None):
    ...
    for i, kps in enumerate(all_halpe26):
        ...
        if stable_ids is not None:
            person['stable_id'] = stable_ids[i]
        if fallback_flags is not None and fallback_flags[i]:   # True の要素のみ付与
            person['fallback'] = True
        people.append(person)
```
- `fallback_flags` が None、または要素が False の person には `fallback` キーを付けない
  （キーの有無で判別、AC-005-2）。

(2) `run_halpe26_pipeline_yolo11.py` の 5f（JSON 出力）:
```
fallback_flags = [True] * len(all_halpe26) if is_fallback_frame else None
openpose_dict = halpe26_to_openpose_json(
    all_halpe26, bbox_scores=bbox_scores, bboxes=bboxes,
    fallback_flags=fallback_flags)
```
- 非注入フレーム（`is_fallback_frame` False）は `fallback_flags=None` → `fallback` キーなし。
  よって `--fallback-roi` 未指定時は全フレームで None となり改修前とバイト一致（AC-001-1, AC-005-2）。
- 注入フレームは長さ 1 の `all_halpe26` に対し `[True]` を渡し、その person に `fallback: true`。

#### エラーハンドリング
- `fallback_flags` の長さは `all_halpe26` と一致（`[True] * len(all_halpe26)`）。
  index ずれは起こらない。新たな例外処理は不要。

#### 境界条件
- 注入フレームで dedup が万一 person を 0 にした場合（理論上起きない）: `all_halpe26` 空 →
  `fallback_flags=[]` → ループに入らず `people` 空。JSON は空 people で破綻しない。

## 1.5 状態遷移

ステートフル処理なし（既存同様 1 パスのフレームループ）。該当なし。

## 1.6 ファイル・ディレクトリ設計

- 入出力パス・JSON 命名・動画命名は既存仕様を踏襲（変更なし）。
- 設定ファイルなし（ROI は CLI 引数で与える）。

## 1.7 インターフェース定義

```python
def _check_thr(value: str) -> float: ...
    # float 化し [0.0, 1.0] を検証。範囲外は argparse.ArgumentTypeError。
    # --fallback-score の type に使う。

def check_fallback_roi_basic(roi: list[int]) -> None: ...
    # 非負・大小関係を検証。違反時は sys.exit(1)。モデルロード前に呼ぶ。

def clip_fallback_roi(roi: list[int], width: int, height: int) -> list[int]: ...
    # 返り値: クリップ済み [x1, y1, x2, y2]。縮退時は sys.exit(1)。動画サイズ取得後に呼ぶ。

def parse_args() -> argparse.Namespace: ...
    # 既存に --fallback-roi(int×4, None) / --fallback-score(_check_thr, 1.0) を追加。

def main() -> None: ...
    # parse_args 直後（モデルロード前）に check_fallback_roi_basic を呼ぶ。
    # width/height 取得後に clip_fallback_roi を 1 回呼ぶ。
    # フレームループ 5a 直後に注入ブロック、5f で fallback_flags を渡す、ループ後にサマリ。

# scripts/halpe26_to_openpose.py（引数追加のみ）
def halpe26_to_openpose_json(
    all_halpe26: list, bbox_scores=None, bboxes=None,
    stable_ids=None, fallback_flags: list[bool] | None = None) -> dict: ...
    # fallback_flags[i] が真の person にのみ person['fallback']=True を付与。
    # None または既存呼び出し（引数省略）時は完全後方互換（キー追加なし）。
```
- クラスは追加しない（既存同様 手続き的）。
- 既存関数（`process_yolo11_results` / `method_a` / dedup 群 / `_resolve_device`）は無変更。
- `halpe26_to_openpose_json` の既存呼び出し元（`run_halpe26_pipeline.py` /
  `run_halpe26_pipeline_yolox.py` / `postprocess_*`）は引数省略のため無影響（デフォルト None）。

## 1.8 ログ・デバッグ設計

- `print` ベース（既存スクリプトと統一、logging は使わない）。
- プレフィックス規約:
  - 起動ログ `Fallback ROI: [...], score: X`（既存の「Bbox threshold: ...」群と同形式、無印）
  - `[WARN]`: ROI 画像範囲クリップ発生時
  - `[ERROR]`: ROI 不正・クリップ後縮退（→ exit 1）
  - サマリ `Fallback applied to N / M frames`（既存の「Saved ...」と同形式、無印）
- 既存の `Processing frame .../...` 等のログは変更しない。

## 設計判断の記録（ADR）

- **ADR-1: 注入位置は bbox_thr フィルタ直後（5a の末尾）**
  - 採用: `person_results = [p for p in ... >= bbox_thr]` の直後に空判定 + 注入。
  - 却下: YOLO 呼び出し前に ROI を常時混ぜる方式。検出があるフレームにも余計な BB が増え、
    FR-003（検出ゼロ限定）に反する。よって「フィルタ後に空」を発動条件とする。

- **ADR-2: フォールバック score を可変（既定 1.0）にする**
  - 採用: `--fallback-score`（既定 1.0）で注入 BB の `bbox_score` を与える。
  - 却下: 0.0 や検出スコア相当の固定埋め込み。下流（`postprocess_pink_id.py` 等）が
    `bbox_score` で足切りする運用に備え、既定 1.0（必ず通る）かつ上書き可能にしておく。

- **ADR-3: 注入 BB を推論経路では特別扱いせず素通しする（JSON フラグのみ付与）**
  - 採用: 注入 BB を検出 BB と同一形式 `{'bbox': np.array([...], float32)}` にし、
    WB/AIC/merge/dedup/draw を一切変更しない。判別情報は JSON の `fallback` フィールド
    （FR-005、§E）でのみ表現する。
  - 却下: 注入 BB 専用の可視化色分け。要求外（Won't）。推論経路への介入を最小化して
    後方互換（AC-001-1）を担保する。

- **ADR-4: 検証を 2 段に分割し、両方ともモデル初期化より前に完了させる**
  - 採用: 非負・大小関係の基本検証 `check_fallback_roi_basic` を parse_args 直後に、画像範囲
    クリップ検証 `clip_fallback_roi` を動画サイズ取得後に行う。**動画 open をモデル初期化より
    前へ移し**、クリップ縮退（例: `99999 99999 100000 100000`）もモデルロード前に弾けるようにする。
  - 却下: 現行 main の順序（モデル初期化 → 動画 open）のままクリップ検証だけ後ろに置く。
    不正 ROI でも先に重いモデルロード・GPU 初期化が走り、ROI エラーがモデル読み込み失敗・
    CUDA OOM に隠される（中レビュー指摘 #2・再レビュー指摘）。要求 1.4 信頼性「早期に弾く」に反する。
  - 却下: フレームごとに検証。ROI は不変なのでループ内検証は無駄。

- **ADR-5: YOLO 呼び出しの conf を変更しない（既定 0.25 のまま）**
  - 採用: 発動条件は「Ultralytics 既定 conf 適用後 + `bbox_thr` フィルタ後に 0 件」。
    `det_model(frame, ...)` の `conf` は既存のまま（既定 0.25）。
  - 却下: `conf=args.bbox_thr` を渡して `bbox_thr` を実質下限にする（高レビュー指摘 #1 の代替案）。
    既存検出結果（0.25 未満の BB が新たに通る）が変わり AC-001-1（未指定時バイト一致）を壊す。
    feat-060 の切り分けも既定 conf で検出ゼロを確認しており、用途上も既定のままで十分。

- **ADR-6: `fallback` フィールドは `halpe26_to_openpose_json` への引数追加で実現する**
  - 採用: `halpe26_to_openpose.py` の `halpe26_to_openpose_json` に任意引数 `fallback_flags`
    （既定 None）を足し、既存 `stable_ids` と同じパターンで person に `fallback: true` を付与する。
  - 却下: `run_halpe26_pipeline_yolo11.py` 側で生成後の dict を後付け編集（`openpose_dict
    ['people'][i]['fallback']=True`）。共通関数 `halpe26_to_openpose.py` を無変更に保てるが、
    JSON 整形ロジックが本体側に漏れ、既存フィールド付与（`bbox`/`stable_id`）と一貫性を欠く。
    既存パターン（feat-028 stable_ids）に揃える方を採る。引数追加は後方互換（既存呼び出し元は
    省略で無影響）。
