# bug-005 調査・修正計画

## イテレーション1 (2026-06-15)

`docs/BUGFIX_STANDARD.md` に従って記述する。

---

## 1. 不具合の特定

### 1.1 現在の動作
`scripts/run_halpe26_pipeline_yolo11.py` に `--device cuda:N`（N ≠ 0）を指定すると、
モデルのロードと "Models initialized" / "Processing video" までは正常に進むが、
最初のフレームのポーズ推論（`inference_top_down_pose_model`）で
`IndexError: list index out of range` が発生して異常終了する。
`--device cuda:0`（デフォルト）のときだけ正常動作する。

再現手順は README.md 参照。

### 1.2 期待する動作
`--device cuda:1` を指定したら物理GPU1で推論が走り、最後まで完走する。

### 1.3 エラーメッセージ（トレースバック）
バグレポートに記録された全記録を以下に転記する。本不具合はマルチGPU環境
（`torch.cuda.device_count() = 7`）でのみ再現し、現在の開発機（単一GPU）では再現できない
ため、これがユーザーから提供された完全な記録である（中間フレームは元レポートで `...` 省略）。
再現環境での手動テスト（ステップ7）時に、省略なしの完全トレースバックを本節へ追記する。

```
File "scripts/run_halpe26_pipeline_yolo11.py", line 241, in main
  wb_results, _ = inference_top_down_pose_model(
File "mmpose/apis/inference.py", line 282, in _inference_single_pose_model
  batch_data = scatter(batch_data, [device])[0]
...
File "torch/nn/parallel/_functions.py", line 174, in _get_stream
  if _streams[device.index] is None:
IndexError: list index out of range
```

---

## 2. 原因分析

### 2.1 原因箇所
- `scripts/run_halpe26_pipeline_yolo11.py:232`
  `yolo_results = det_model(frame, device=args.device, verbose=False)`
- ultralytics `select_device`:
  `.venv/.../ultralytics/utils/torch_utils.py:168`（`"cuda:"` 除去で `cuda:1` → `1`）、
  `:221`（`os.environ["CUDA_VISIBLE_DEVICES"] = device`）
- mmpose `mmpose/apis/inference.py:282`
  `batch_data = scatter(batch_data, [device])[0]`（device は絶対インデックス `cuda:N`）
- torch `.venv/.../torch/nn/parallel/_functions.py:173-174`
  `_streams = [None] * torch.accelerator.device_count()` → `_streams[device.index]`

### 2.2 原因の説明（実コードで検証済み）
1. `init_pose_model(..., device='cuda:1')`（`:176-177`）でポーズモデルを物理GPU1へ配置。
   この時点でプロセスから全GPUが見えており `torch.cuda.device_count() = 7`。
   モデルパラメータは `device.index = 1`。
2. フレームループ内の YOLO 検出（`:232`）が ultralytics `select_device` を呼ぶ。
   `select_device` は引数 device 文字列を正規化（`torch_utils.py:168` で `"cuda:"` を除去し
   `cuda:1` → `1`）し、`torch_utils.py:221` の `elif device:` 分岐で
   `os.environ["CUDA_VISIBLE_DEVICES"] = "1"` を**実行時に**セットする。
3. これ以降 `torch.cuda.device_count()` / `torch.accelerator.device_count()` が環境変数を
   読み直し、7 → 1 に変わる（見えるGPUが1個になる）。既にGPUへ載っているポーズモデルの
   パラメータは `device.index = 1` のまま変わらない。
4. 続くポーズ推論（`:241`）→ `mmpose/apis/inference.py:282` の `scatter(batch_data, [device])`
   → torch `_get_stream` で
   `_streams = [None] * torch.accelerator.device_count()`（= 長さ1）に対し
   `_streams[device.index]`（= `_streams[1]`）で長さ1リストへ index 1 アクセスし IndexError。

**なぜ cuda:0 だけ成功するか**: cuda:0 のときも device_count は 1 へ減るが、ポーズモデルの
index も 0 なので `_streams[0]`（長さ1リストの index 0）が範囲内に収まり成功する。
つまり「0 以外のインデックスは構造上必ず失敗する」。

### 2.3 根本原因 or 表面的原因
**根本原因**: 「ultralytics(YOLO) が推論のたびに `CUDA_VISIBLE_DEVICES` を書き換え、見える
GPU数を縮小する」ことと、「mmpose/torch がモデルの絶対インデックス（`cuda:N`）で scatter する」
ことの非互換。スクリプト内部で扱うデバイスのインデックスが 0 以外になると必ず破綻する。

---

## 3. 修正内容

### 3.1 方針（採用案 = レポート案1）
スクリプト内部で扱うデバイスのインデックスを**常に 0 に固定**する。これにより、ultralytics が
`CUDA_VISIBLE_DEVICES` を書き換えて device_count が 1 に縮んでも `_streams[0]` が常に範囲内に
収まり、IndexError を構造的に回避できる。物理GPUの選択は `CUDA_VISIBLE_DEVICES` で行う。

具体的には:
- `--device cuda:N` から物理GPUインデックス N を取り出し、**torch を初期化する前に**
  `os.environ["CUDA_VISIBLE_DEVICES"] = "N"` を設定する。
- スクリプト内部のデバイス（pose モデル・YOLO 双方に渡す値）は常に `cuda:0` を使う。
- これにより物理GPU N がプロセスから見て index 0 として見え、内部 index は常に 0。

#### 不変条件
「内部デバイスの index == 0」を保てば本バグは起きない。物理GPU選択は
`CUDA_VISIBLE_DEVICES` に委ねる。

#### 外部 CUDA_VISIBLE_DEVICES との両立（`--device cuda:N` の意味を一貫させる）
外部 `CUDA_VISIBLE_DEVICES` が設定済みのとき、単に「上書きしない」だけだと
`CUDA_VISIBLE_DEVICES=2,3 --device cuda:1`（通常は物理GPU3を期待）が内部 cuda:0 = 物理GPU2 を
使ってしまい、クラッシュはしないが**指定と異なるGPUを使う誤使用バグ**になる（Codexレビュー高指摘）。
これを避けるため、`--device cuda:N` の N を「**現在プロセスから見えているGPUリストの N 番目**」
として解決する設計にする。物理GPU選択は常に `--device` の指定どおりになる。

判定ルール（重い import より前に実行）:
- `--device` が `cpu` → 内部デバイス `cpu`、env 操作なし。
- `--device` が `cuda`（= `cuda:0` 扱い）または `cuda:N`:
  0. `N` の検証: `cuda:N` の N が 0 以上の整数（`str.isdigit()` で判定、負号・非数字を排除）で
     なければ `SystemExit` で分かりやすいエラー終了（`cuda:-1` / `cuda:foo` を排除）。
  1. 現在の `CUDA_VISIBLE_DEVICES` を「未設定」「設定済み空文字」「設定済み非空」で区別して読む。
     - **設定済み空文字（`""`）** → ユーザーが GPU を不可視化した明示指定。`--device cuda*` は
       矛盾するため `SystemExit` で終了（CUDA_VISIBLE_DEVICES を外すか `--device cpu` を促す）。
     - **未設定** → 見えるGPUリストは「全GPUが物理 index 昇順で見える」とみなし、
       解決後の物理ID = N（`CUDA_VISIBLE_DEVICES = str(N)`）。
     - **設定済み非空（例 `"2,3"`）** → カンマ分割した `devices = ["2","3"]` を見えるGPUリストとし、
       N がリスト長以上なら**即座にエラー終了**（`SystemExit`、分かりやすいメッセージ）。
       範囲内なら解決後の物理ID = `devices[N]`（`CUDA_VISIBLE_DEVICES = devices[N]`）。
  2. いずれの場合も `CUDA_VISIBLE_DEVICES` を「選んだ1枚」に絞り込み、内部デバイスは `cuda:0`。
- 上記以外（`cpu` / `cuda` / `cuda:N` のいずれでもない想定外文字列）は `SystemExit` で
  分かりやすいエラー終了（重い import 前なので推論を開始しない）。

この設計により:
- 外部マスク未設定 `--device cuda:1` → `CUDA_VISIBLE_DEVICES="1"`、物理GPU1（本バグ修正）。
- 暫定回避策 `CUDA_VISIBLE_DEVICES=1 --device cuda:0` → `devices=["1"]`, `devices[0]="1"` →
  `CUDA_VISIBLE_DEVICES="1"`、物理GPU1（後方互換維持）。
- `CUDA_VISIBLE_DEVICES=2,3 --device cuda:1` → `devices[1]="3"` → 物理GPU3（指定どおり）。
- いずれも内部 index は常に 0 で本バグを構造的に回避。

#### 実装上の制約: import 順序
ultralytics / mmpose / torch を import すると CUDA が初期化され得るため、
`CUDA_VISIBLE_DEVICES` の設定は**重い import より前**に行う必要がある。
現状スクリプトは先頭で `from ultralytics import YOLO` 等を import している（`:11-12`）。
そこで、標準ライブラリ（`argparse` / `os` / `sys`）import 直後・重い import の前に、
`sys.argv` から `--device` を素朴に先読みして env を確定する小関数を挿入する。

### 3.2 変更対象ファイル
**`scripts/run_halpe26_pipeline_yolo11.py`** のみ。

変更1: 重い import より前（`import sys` の後、`import cv2` の前）に、device 先読み + env 設定を追加。

```python
# --- 修正後（追加） ---
import argparse
import json
import os
import sys
import time


def _resolve_device(argv: list) -> str:
    """--device を先読みし、CUDA_VISIBLE_DEVICES を1枚に絞って内部デバイス名を返す。

    重い import（torch/ultralytics/mmpose）前に呼ぶこと。内部デバイスは常に cuda:0 に
    固定し、物理GPU選択は CUDA_VISIBLE_DEVICES へ委ねる（bug-005）。--device cuda:N の N は
    「現在見えている GPU リストの N 番目」として解決する。
    """
    raw = 'cuda:0'
    for i, a in enumerate(argv):
        if a == '--device' and i + 1 < len(argv):
            raw = argv[i + 1]
        elif a.startswith('--device='):
            raw = a.split('=', 1)[1]
    if raw == 'cpu':
        return 'cpu'
    if raw == 'cuda' or raw.startswith('cuda:'):
        # N の検証: cuda 単体は 0、cuda:N は 0 以上の整数のみ許可
        suffix = raw.split(':', 1)[1] if ':' in raw else '0'
        if not suffix.isdigit():   # isdigit() は負号・非数字を弾く（cuda:-1 / cuda:foo を排除）
            raise SystemExit(
                f"--device の値が不正です: {raw!r}。cpu / cuda / cuda:N (N>=0) を指定してください")
        idx = int(suffix)
        # 「未設定」と「設定済み空文字（GPU不可視の明示指定）」を区別する
        present = 'CUDA_VISIBLE_DEVICES' in os.environ
        visible = os.environ.get('CUDA_VISIBLE_DEVICES', '')
        if present and visible == '':
            raise SystemExit(
                "CUDA_VISIBLE_DEVICES='' (GPU 不可視) が指定されています。"
                "GPU を使うなら CUDA_VISIBLE_DEVICES を外すか、--device cpu を指定してください")
        if not present:
            # 外部マスクなし: 物理 index = N
            os.environ['CUDA_VISIBLE_DEVICES'] = str(idx)
        else:
            # 外部マスクあり: 見えるリストの N 番目を選ぶ
            devices = [d for d in visible.split(',') if d != '']
            if idx >= len(devices):
                raise SystemExit(
                    f"--device cuda:{idx} は CUDA_VISIBLE_DEVICES={visible!r} の範囲外です "
                    f"(見える GPU 数 = {len(devices)})")
            os.environ['CUDA_VISIBLE_DEVICES'] = devices[idx]
        return 'cuda:0'
    raise SystemExit(
        f"--device の値が不正です: {raw!r}。cpu / cuda / cuda:N (N>=0) を指定してください")


INTERNAL_DEVICE = _resolve_device(sys.argv)

import cv2
import numpy as np

from ultralytics import YOLO
...
```

変更2: `args.device` を使っている3箇所を `INTERNAL_DEVICE` に置き換える。
- `:176` `wb_model = init_pose_model(WB_CONFIG, WB_CHECKPOINT, device=INTERNAL_DEVICE)`
- `:177` `aic_model = init_pose_model(AIC_CONFIG, AIC_CHECKPOINT, device=INTERNAL_DEVICE)`
- `:232` `yolo_results = det_model(frame, device=INTERNAL_DEVICE, verbose=False)`

変更3: `--device` の help を更新し、内部で cuda:0 固定 + CUDA_VISIBLE_DEVICES へマップする旨を明記。
（`:142-143`）。`--device` 引数自体は残す（後方互換のため CLI は不変）。

> 補足: ログに「物理GPU選択は CUDA_VISIBLE_DEVICES、内部デバイスは cuda:0」を1行出すと
> 運用時の混乱を避けられる（任意。実装時に1行 print を追加する程度）。

### 3.3 変更しないファイル
- `scripts/run_halpe26_pipeline_yolox.py`: 検出器に **mmdet**（`init_detector` /
  `inference_detector`、推論時に device を渡さない）を使っており、ultralytics の
  `select_device` を呼ばないため `CUDA_VISIBLE_DEVICES` の書き換えが起きない。本バグの影響を
  受けないので変更不要（実コードで確認済み。レポートの「yoloxでも起き得る」推測は本リポジトリの
  実装には当てはまらない）。
- `mmpose/` / ultralytics / torch: ライブラリ本体は変更しない（CLAUDE.md 方針）。
- `scripts/run_halpe26_pipeline.py`（無検出器版）等: 本件の対象外。

### 3.4 修正コード（修正前 → 修正後の要点）
- 修正前: `args.device`（例 `cuda:1`）を pose モデル init と YOLO 呼び出しへそのまま渡す
  → 内部 index が 1 になり scatter で破綻。
- 修正後: 重い import 前に `CUDA_VISIBLE_DEVICES` を確定し、内部は常に `cuda:0` を渡す
  → 内部 index は常に 0、scatter は `_streams[0]` で安全。

---

## 4. 影響範囲

### 4.1 他の機能への影響
- `--device cuda:0`（デフォルト・外部マスクなし）: `CUDA_VISIBLE_DEVICES="0"` をセットし内部
  `cuda:0`。従来と同じ物理GPU0・同じ内部挙動 → **挙動不変**。
- 暫定回避策 `CUDA_VISIBLE_DEVICES=1 --device cuda:0`: `devices=["1"]`,`devices[0]="1"` →
  `CUDA_VISIBLE_DEVICES="1"`、内部 `cuda:0` → **従来どおり物理GPU1で動作**（後方互換維持）。
- `--device cpu`: env 操作なし、内部 `cpu` → 従来どおり。
- `--device cuda:1`（外部マスクなし）: `CUDA_VISIBLE_DEVICES="1"`、内部 `cuda:0` →
  **新たに正常動作（本バグ修正）**。
- `CUDA_VISIBLE_DEVICES=2,3 --device cuda:1`: `devices[1]="3"` → 物理GPU3、内部 `cuda:0` →
  指定どおりのGPUを使用。
- `CUDA_VISIBLE_DEVICES=2 --device cuda:1`: 範囲外として `SystemExit` で即エラー終了
  （誤GPU使用を防止）。

### 4.2 リグレッションリスク
- 出力（JSON / 動画）の数値・内容は使用GPUに依存しないため、`--device cuda:0` での出力は
  修正前と同一になるはず（AC-1 で `diff -r` 検証）。
- `_resolve_device` の argv 先読みは argparse とは独立。`--device` の表記揺れ
  （`--device cuda:1` と `--device=cuda:1` の両形式）に対応済み。argparse 側の検証
  （未知の値など）は従来どおり後段で効く。
- 外部マスク併用時は `--device cuda:N` を見えるリストの N 番目として解決する。範囲外の N は
  `SystemExit` で早期エラーにし、誤GPU使用を防ぐ。`--device` の意味（指定どおりの物理GPU）が
  外部マスクの有無によらず一貫する旨を help に明記する。

---

## 5. 確認方法

### 5.1 テスト項目
- AC-1（後方互換）: 修正前後で `--device cuda:0` の出力 JSON が一致する。
- AC-2（バグ修正）: `--device cuda:1` を指定して IndexError を出さずに完走する
  （マルチGPU環境でのみ実施可能）。
- AC-3（回避策後方互換）: `CUDA_VISIBLE_DEVICES=1 --device cuda:0` で完走する。
- AC-4（物理GPU確認）: `--device cuda:1` 実行中に `nvidia-smi` で物理GPU1が使われている。
- AC-5（範囲外エラー）: `CUDA_VISIBLE_DEVICES=2 --device cuda:1` で `SystemExit` の
  分かりやすいメッセージとともに即終了する（推論を開始しない）。

### 5.2 テストコマンド
AC-1（単一GPU環境でも実施可能。`git stash` で改修前を退避して突合）:
```bash
# 改修後
uv run python scripts/run_halpe26_pipeline_yolo11.py \
    --video testdata/camSony1.mp4 --out-dir /tmp/bug005_after/ \
    --bbox-thr 0.3 --oks-thr 0.5 --device cuda:0 --mode json
# 改修前（git stash 後に同じコマンドで /tmp/bug005_before/ へ出力）
diff -r /tmp/bug005_before/ /tmp/bug005_after/   # 差分0 を期待
```

AC-2 / AC-4（マルチGPU環境）:
```bash
uv run python scripts/run_halpe26_pipeline_yolo11.py \
    --video testdata/camSony1.mp4 --out-dir /tmp/bug005_gpu1/ \
    --bbox-thr 0.3 --oks-thr 0.5 --device cuda:1
# 別端末: nvidia-smi で GPU1 の利用を確認。完走（IndexError なし）を確認。
```

AC-3（マルチGPU環境）:
```bash
CUDA_VISIBLE_DEVICES=1 uv run python scripts/run_halpe26_pipeline_yolo11.py \
    --video testdata/camSony1.mp4 --out-dir /tmp/bug005_workaround/ \
    --bbox-thr 0.3 --oks-thr 0.5 --device cuda:0
```

AC-5（範囲外・異常系エラー。単一GPU環境でも検証可能。モデル初期化前に即終了する）:
```bash
# 範囲外: 見える GPU は1枚なのに cuda:1 を要求 → SystemExit
CUDA_VISIBLE_DEVICES=2 uv run python scripts/run_halpe26_pipeline_yolo11.py \
    --video testdata/camSony1.mp4 --out-dir /tmp/bug005_oob/ \
    --bbox-thr 0.3 --oks-thr 0.5 --device cuda:1
# 期待: "--device cuda:1 は CUDA_VISIBLE_DEVICES='2' の範囲外です (見える GPU 数 = 1)" で終了

# GPU 不可視の明示指定に cuda を要求 → SystemExit
CUDA_VISIBLE_DEVICES="" uv run python scripts/run_halpe26_pipeline_yolo11.py \
    --video testdata/camSony1.mp4 --out-dir /tmp/bug005_empty/ \
    --bbox-thr 0.3 --oks-thr 0.5 --device cuda:0
# 期待: "CUDA_VISIBLE_DEVICES='' (GPU 不可視) ..." で終了

# 不正値 → SystemExit
uv run python scripts/run_halpe26_pipeline_yolo11.py \
    --video testdata/camSony1.mp4 --out-dir /tmp/bug005_bad/ \
    --bbox-thr 0.3 --oks-thr 0.5 --device cuda:foo
# 期待: "--device の値が不正です: 'cuda:foo' ..." で終了
```
いずれも "Models initialized" を出力する前（モデルロード前）に終了することを確認する。

> 注: 開発機が単一GPUの場合 AC-2/3/4 はユーザーのマルチGPU環境で手動テストとなる。
> AC-1（後方互換）・AC-5（異常系）は単一GPUでも検証可能。

---

## 6. 実装・検証結果 (2026-06-15)

実装完了（`scripts/run_halpe26_pipeline_yolo11.py`、変更1〜3を適用）。開発機（GPU 1枚）で
実施可能な AC を検証した。

- **AC-1（後方互換）**: `cam05520125.mp4` 300フレーム / `--device cuda:0 --mode json` で改修前
  （`git stash`）と改修後を突合。座標は完全一致、confidence の末尾 ~6桁のみ一部フレームで微差。
  **同一コードを2回実行しても同規模・同性質の差**が出ることを確認したため、この差は GPU(cuDNN)
  の実行ごと浮動小数非決定性であり本修正とは無関係。GPUノイズの範囲内で **実質 PASS**。
- **AC-5（異常系）**: 4ケースすべて期待メッセージで、モデルロード（"Initializing models"）前に
  `SystemExit` で即終了することを確認。**PASS**。
  - 範囲外 `CUDA_VISIBLE_DEVICES=2 --device cuda:1` → "範囲外です (見える GPU 数 = 1)"
  - 空文字 `CUDA_VISIBLE_DEVICES="" --device cuda:0` → "GPU 不可視 ..."
  - 不正値 `--device cuda:foo` / `--device gpu0` → "--device の値が不正です ..."
- **AC-2 / AC-3 / AC-4（マルチGPU依存）**: 開発機が単一GPUのため未実施。ユーザーのマルチGPU環境
  での手動テスト（ステップ7）に委ねる。
