# feat-044 機能設計書: pink → blue 動画変換ツール

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001（ピンク領域抽出） | §4.1 |
| FR-002（青置換） | §4.2 |
| FR-003（動画出力） | §4.3 |
| FR-004（CLI 引数） | §4.4 / §7 |
| FR-005（進捗・サマリ） | §4.5 |
| NFR-001（性能） | §6 |

## 2. システム構成

### 2.1 モジュール構成

新規ファイル `scripts/convert_pink_to_blue_video.py` の単一ファイル構成。

```
scripts/convert_pink_to_blue_video.py
├─ 定数
│   └─ DEFAULT_HSV_RANGES (postprocess_pink_id.py の FIXED_HSV_RANGES と同一)
├─ 純関数
│   ├─ parse_args
│   ├─ build_pink_mask        (FR-001)
│   ├─ apply_blue_transform   (FR-002)
│   └─ format_summary         (FR-005)
└─ main
    └─ フレームループ・I/O 統括
```

### 2.2 依存関係

- `cv2` (OpenCV、既存)
- `numpy` (既存)
- `argparse` / `os` / `time` / `pathlib` (標準ライブラリ)

新規ライブラリの導入なし。

### 2.3 ディレクトリ構成

既存と同じ。新規ファイルは `scripts/convert_pink_to_blue_video.py` のみ。

## 3. 技術スタック

| 項目 | 値 | 選定理由 |
|------|-----|----------|
| 言語 | Python 3.10.16 | プロジェクト既定 |
| パッケージ管理 | uv | プロジェクト既定 |
| OpenCV | 既存 | HSV 変換・動画 I/O |
| numpy | 既存 | 配列演算 |

## 4. 各機能の詳細設計

### 4.1 FR-001: ピンク領域の HSV 抽出

#### 4.1.1 データフロー

- 入力: `frame: numpy.ndarray, shape=(H, W, 3), dtype=uint8, BGR`
- 中間: `hsv: numpy.ndarray, shape=(H, W, 3), dtype=uint8, HSV`
- 出力: `mask: numpy.ndarray, shape=(H, W), dtype=bool`

#### 4.1.2 処理ロジック

```python
DEFAULT_HSV_RANGES: list[tuple[tuple[int, int, int], tuple[int, int, int]]] = [
    ((0, 60, 80), (10, 255, 255)),
    ((140, 60, 80), (159, 255, 255)),
    ((160, 60, 80), (179, 255, 255)),
]

def build_pink_mask(
    hsv: np.ndarray,
    hsv_ranges: list[tuple[tuple[int, int, int], tuple[int, int, int]]],
) -> np.ndarray:
    """HSV 配列から複数範囲 OR のマスクを返す（bool 配列）。"""
    mask_total = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lo, hi in hsv_ranges:
        m = cv2.inRange(hsv, np.array(lo, dtype=np.uint8), np.array(hi, dtype=np.uint8))
        mask_total = cv2.bitwise_or(mask_total, m)
    return mask_total > 0
```

`postprocess_pink_id.py` の `compute_pink_ratio` 内のマスク生成ロジックと同一。

#### 4.1.3 境界条件

- 全画素がピンク範囲外 ⇒ `mask` は全 False、後段の代入処理は no-op
- 全画素がピンク範囲内 ⇒ `mask` は全 True、後段で全画素が変換される

### 4.2 FR-002: ピンク領域の青置換

#### 4.2.1 データフロー

- 入力:
  - `hsv: numpy.ndarray, shape=(H, W, 3), dtype=uint8`
  - `mask: numpy.ndarray, shape=(H, W), dtype=bool`
  - `target_h: int (0-179)`、`s_scale: float (0.0-1.0)`、`s_max: int (0-255)`
- 出力: `hsv` を in-place で改変（戻り値なし、または同オブジェクト返却）

#### 4.2.2 処理ロジック

```python
def apply_blue_transform(
    hsv: np.ndarray,
    mask: np.ndarray,
    target_h: int,
    s_scale: float,
    s_max: int,
) -> np.ndarray:
    """マスク内画素の H を target_h、S を min(S*s_scale, s_max) に置換。
    V は変更しない。配列は in-place で改変される。
    """
    if not mask.any():
        return hsv
    hsv[mask, 0] = target_h
    s_orig = hsv[mask, 1].astype(np.int32)
    s_new = np.clip(s_orig * s_scale, 0, s_max).astype(np.uint8)
    hsv[mask, 1] = s_new
    # V は変更しない
    return hsv
```

`s_scale * s_orig` は float 演算なので int32 に昇格してから乗算し、`np.clip` で `[0, s_max]` にクランプし `uint8` に戻す。

#### 4.2.3 設計判断の記録（ADR）

- **採用案: H 置換 + S 圧縮（V 不変）**: Blue2/Blue4.png の HSV 分析で「H が明確に青（中央値 108-110）、S は低〜中彩度（中央値 25-43）、V は明るい〜中央値」だったため、H と S のみ変換。V を変えると元動画の照明感（陰影）が壊れる
- **却下案: H/S/V すべてをパラメトリック分布に置換**: 元動画のシワ・陰影など視覚的特徴が失われ、検出ロジックが「テクスチャなしの均一な色塗り領域」を学習してしまうリスクがある
- **却下案: マスク外領域も微調整**: スコープ拡大、本案件の目的（ピンク → 青の単純変換）から逸脱
- **照明変動への対応方針**: Blue1/2 と Blue3/4 は**同一個体（同一の青病院着・同一人物）の異なる照明条件下のサンプル**（Blue1/2 が暗め、Blue3/4 が明るめ）。S 中央値が 25 ⇔ 43、V 中央値が 137 ⇔ 158 と大きく動くことが確認された。このため、デフォルト値は「ある特定の照明条件に最適」ではなく「両者の中間を狙う」設計とした（`s-scale=0.35`、`s-max=80`）。検証時は `--s-scale 0.3 --s-max 60`（Blue2 寄り、暗め）と `--s-scale 0.4 --s-max 80`（Blue4 寄り、明るめ）の 2 通り出力して比較することで、照明変動が下流（feat-045 検出側）に与える影響を別個に評価可能

#### 4.2.4 境界条件

- `mask` が全 False ⇒ 早期 return、`hsv` 変更なし
- `s_scale = 0.0` ⇒ S が全て 0（無彩色グレー）になる
- `s_scale = 1.0`、`s_max = 255` ⇒ S は元のまま、H のみ変更（L1 相当の挙動）
- `target_h` が 110（青中心） / 0（赤、変換しても意味なし）等の境界値も設計上は許容（CLI で指定可能、値域 [0, 179]）

### 4.3 FR-003: 合成動画の出力

#### 4.3.1 データフロー

- 入力: 変換済み `hsv` フレームの逐次列
- 中間: BGR フレーム (`cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)`)
- 出力: MP4 ファイル

#### 4.3.2 処理ロジック

メインループ内:

```python
cap = cv2.VideoCapture(args.input)
fps = cap.get(cv2.CAP_PROP_FPS)
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

out_name = f"{Path(args.input).stem}_blue.mp4"
out_path = os.path.join(args.out_dir, out_name)
os.makedirs(args.out_dir, exist_ok=True)

writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))

while True:
    ret, frame = cap.read()
    if not ret:
        break
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = build_pink_mask(hsv, hsv_ranges)
    apply_blue_transform(hsv, mask, args.target_h, args.s_scale, args.s_max)
    bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    writer.write(bgr)
    ...

cap.release()
writer.release()
```

#### 4.3.3 境界条件

- 入力動画が開けない ⇒ `cap.isOpened() == False` で標準エラー出力 + `sys.exit(1)`
- 入力動画の `fps <= 0` または `width <= 0` または `height <= 0` ⇒ 標準エラーに `ERROR: invalid video metadata (fps=X, size=WxH)` を出力 + `sys.exit(1)`（壊れた MP4 / 一部のコーデックで `cap.get(...)` が 0 を返すケース対応、AC-003-6）
- `args.out_dir` 存在しない ⇒ `os.makedirs(args.out_dir, exist_ok=True)` で自動作成
- 既存の出力ファイルがある場合 ⇒ 警告なく上書き（既存 visualize 系と同じ挙動、AC-003-5）

### 4.4 FR-004: CLI 引数

§7 で詳述。

### 4.5 FR-005: 進捗表示・サマリ

#### 4.5.1 処理ロジック

開始ログは §4.3.2 の `out_path` / `total_frames` / `fps` / `width` / `height` 算出後にまとめて出す。

```python
PROGRESS_INTERVAL_FRAMES = 3000

# 注: 以下は §4.3.2 で out_path / total_frames / fps / width / height が確定した後に実行する
print(f"Video: {args.input} ({total_frames} frames, {fps} fps, {width}x{height})")
print(f"HSV transform: H -> {args.target_h}, S *= {args.s_scale} (max {args.s_max}), V kept")
print(f"Output: {out_path}")

frame_idx = 0
total_pink_pixels = 0
total_pixels = 0
start_time = time.time()

while True:
    ret, frame = cap.read()
    if not ret:
        break
    ...
    total_pink_pixels += int(mask.sum())
    total_pixels += mask.size
    if frame_idx % PROGRESS_INTERVAL_FRAMES == 0:
        pct = frame_idx / total_frames * 100 if total_frames > 0 else 0
        print(f"Processing frame {frame_idx:06d}/{total_frames} ({pct:.1f}%)")
    frame_idx += 1

elapsed = time.time() - start_time
fps_actual = frame_idx / elapsed if elapsed > 0 else 0.0
avg_ratio = total_pink_pixels / total_pixels if total_pixels > 0 else 0.0
print(f"Total frames: {frame_idx}")
print(f"Processing time: {elapsed:.1f} sec ({fps_actual:.1f} fps)")
print(f"Average pink ratio: {avg_ratio*100:.2f}%")
print(f"Output: {out_path}")
```

## 5. ファイル・ディレクトリ設計

### 5.1 入出力パス

- 入力: CLI `--input`（必須）
- 出力: `{args.out_dir}/{入力 stem}_blue.mp4`（FR-003）

### 5.2 推奨実行コマンド（手動テスト用）

```bash
uv run python scripts/convert_pink_to_blue_video.py \
  --input testdata/camSony1_S.mp4 \
  --out-dir /tmp/feat044_test
# 出力: /tmp/feat044_test/camSony1_S_blue.mp4
```

オプション指定例:

```bash
uv run python scripts/convert_pink_to_blue_video.py \
  --input testdata/camSony1_S.mp4 \
  --out-dir /tmp/feat044_test \
  --target-h 105 --s-scale 0.35 --s-max 80
```

## 6. パフォーマンス影響

各フレーム処理は以下の順序:
1. `cap.read()` → I/O + デコード（数 ms）
2. `cvtColor(BGR2HSV)` → numpy 演算（数 ms）
3. `cv2.inRange × 3` + `bitwise_or` → numpy 演算（数 ms）
4. boolean indexing 代入 + `np.clip` → numpy 演算（数 ms）
5. `cvtColor(HSV2BGR)` → numpy 演算（数 ms）
6. `writer.write()` → エンコード（数 ms）

camSony1_S（900 frames、640×480 程度）で 30 秒以内を目標。camSony1_L の目標は requirements.md NFR-001 に従い実測後に判断する。GPU 不使用。

## 7. インターフェース定義

### 7.1 CLI 引数

```python
def _check_h(v):
    iv = int(v)
    if not (0 <= iv <= 179):
        raise argparse.ArgumentTypeError(f"target-h must be in [0, 179], got {iv}")
    return iv

def _check_scale(v):
    fv = float(v)
    if not (0.0 <= fv <= 1.0):
        raise argparse.ArgumentTypeError(f"s-scale must be in [0.0, 1.0], got {fv}")
    return fv

def _check_smax(v):
    iv = int(v)
    if not (0 <= iv <= 255):
        raise argparse.ArgumentTypeError(f"s-max must be in [0, 255], got {iv}")
    return iv

parser = argparse.ArgumentParser(
    description="Convert pink regions in a video to blue (HSV-based)"
)
parser.add_argument("--input", required=True, type=str, help="Input video file")
parser.add_argument("--out-dir", default="output", type=str, help="Output directory")
parser.add_argument(
    "--target-h", type=_check_h, default=110,
    help="Target H value (0-179) after replacement (default: 110, blue center)",
)
parser.add_argument(
    "--s-scale", type=_check_scale, default=0.35,
    help="S compression factor (0.0-1.0). New S = min(S*s_scale, s_max) (default: 0.35)",
)
parser.add_argument(
    "--s-max", type=_check_smax, default=80,
    help="Maximum S after compression (0-255). (default: 80)",
)
```

引数値域チェックは `argparse` の `type` カスタム関数で実施し、値域外の場合は `ArgumentTypeError` で exit code 2 で終了する。これにより `target_h=200` を渡したときの uint8 ラップ等の不定動作を防ぐ（FR-004 AC-004-6）。

### 7.2 公開関数シグネチャ

| 関数 | シグネチャ |
|------|-----------|
| `build_pink_mask(hsv, hsv_ranges)` | `(np.ndarray, list) -> np.ndarray (bool)` |
| `apply_blue_transform(hsv, mask, target_h, s_scale, s_max)` | `(np.ndarray, np.ndarray, int, float, int) -> np.ndarray` |
| `main()` | `() -> None` |

## 8. ログ・デバッグ設計

### 8.1 既存ログ準拠

`run_halpe26_pipeline_yolo11.py` / `visualize_patient_video.py` の進捗表示形式を踏襲（FR-005）。

### 8.2 追加ログ

なし。

## 9. 実装完了後のチェックリスト

- [ ] `scripts/convert_pink_to_blue_video.py` を新規作成
- [ ] `build_pink_mask` / `apply_blue_transform` の単体動作確認（小さい合成画像で）
- [ ] testdata/camSony1_S.mp4 で動作確認、出力動画を再生して視覚確認
- [ ] 出力動画の任意フレームを HSV 解析し、ピンク領域だった場所の H が `target_h`、S が `s_max` 以下、V が変化なしを確認（AC-002）
- [ ] camSony1_S で処理時間が 30 秒以内（NFR-001）
- [ ] `scripts/README.md` に `convert_pink_to_blue_video.py` セクションを追加
- [ ] CLAUDE.md の feat-044 エントリを完了済み案件として追記
- [ ] CLAUDE.md ディレクトリ構成に新規スクリプトを追記
- [ ] `docs/BACKLOG.md` の feat-044 を Closed に変更
- [ ] `docs/issues/feat-044-convert-pink-to-blue-video/README.md` のステータスを Closed に更新

## 10. 設計判断の記録（全体 ADR サマリ）

- **L2 採用**: H 置換 + S 圧縮、V 不変
- **既定 HSV 範囲は postprocess_pink_id.py と同一**: 既知の高精度範囲を流用
- **変換パラメータ（`--target-h` / `--s-scale` / `--s-max`）は CLI で調整可、HSV 範囲は定数固定**: ユーザー要望「3 案件構成完成後に変換精度を再評価」に対応するため、よく動かす変換パラメータをコード再ビルド不要で調整可能とする。HSV 範囲は `postprocess_pink_id.py` と同期させたいため定数固定（変更が必要になれば別案件）
- **出力命名規約 `{stem}_blue.mp4`**: feat-038 の `vis_*.mp4` のような目的別プレフィックスではなく接尾辞、変換系ツールのため
- **動画出力の音声非対応**: OpenCV VideoWriter の制約。本案件のスコープでは音声不要
