# feat-021: 既存JSON+動画でBoxMOT動作検証 — 機能設計書

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|--------------|
| FR-1 | 4.1 JSON読み込み |
| FR-2 | 4.2 動画フレーム読み込み |
| FR-3 | 4.3 トラッキング実行 |
| FR-4 | 4.4 結果出力 |

## 2. システム構成

### 新規ファイル

- `scripts/test_boxmot_offline.py` — テストスクリプト（単一ファイル、他モジュールへの依存なし）

### 既存ファイルの変更

なし

### コマンドライン引数

```
uv run python scripts/test_boxmot_offline.py \
    --video testdata/pexels_4441000.mp4 \
    --json-dir experiments/results/feat-018-test/pexels_4441000_json/ \
    --device cuda:0
```

| 引数 | 型 | 必須 | デフォルト | 説明 |
|------|-----|:--:|-----------|------|
| `--video` | str | Yes | — | 入力動画のパス |
| `--json-dir` | str | Yes | — | OpenPose JSONディレクトリのパス |
| `--device` | str | No | `cuda:0` | トラッカーのデバイス（`cuda:N` または `cpu`）。無効な値の場合はBoxMOTのエラーをそのまま表示して終了する |

## 3. 技術スタック

| ライブラリ | バージョン | 用途 |
|-----------|----------|------|
| boxmot | 16.0.11 | Deep OC-SORTトラッカー |
| opencv-python | 4.13.0.92 | 動画フレーム読み込み |
| numpy | 2.2.6 | bbox配列の変換 |
| Python | 3.10.16 | 実行環境 |

## 4. 各機能の詳細設計

### 4.1 JSON読み込み（FR-1）

#### データフロー

- **入力**: JSONディレクトリパス（str）
- **中間**: JSONファイルパスのリスト（ファイル名でソート）
- **出力**: `list[list[dict]]` — フレームごとの人物bboxリスト

各フレームのデータ構造:
```python
# 1フレーム分
[
    {"bbox": [x1, y1, x2, y2], "bbox_score": float},  # person 0
    {"bbox": [x1, y1, x2, y2], "bbox_score": float},  # person 1
    ...
]
```

#### 処理ロジック

1. `json_dir` 内の `*.json` ファイルを `glob` で取得する
2. ファイル名の辞書順（`sorted()`）でソートする。ファイル名はゼロパディングされた連番形式（例: `pexels_4441000_000000.json`, `pexels_4441000_000001.json`）であることを前提とする
3. 各JSONファイルを読み込み、`people` 配列から `bbox` と `bbox_score` を抽出する
4. `bbox` または `bbox_score` が存在しない人物はスキップする

#### エラーハンドリング

- JSONファイルが0件の場合: エラーメッセージを出力して終了する
- JSONの `people` 配列が空のフレーム: 空リストとして扱う（0人検出）
- `bbox` フィールドが存在しない人物: その人物をスキップし、警告を出力する

### 4.2 動画フレーム読み込み（FR-2）

#### データフロー

- **入力**: 動画ファイルパス（str）
- **出力**: フレーム画像（numpy.ndarray, shape=(H, W, 3), dtype=uint8, BGR色空間）

#### 処理ロジック

1. `cv2.VideoCapture` で動画を開く
2. フレーム総数を取得し、JSONファイル数と一致するか確認する
3. ループ内で `cap.read()` でフレームを1枚ずつ読み込む

#### エラーハンドリング

- 動画ファイルが開けない場合: エラーメッセージを出力して終了する
- フレーム数とJSONファイル数が不一致の場合: 警告を出力し、少ない方の数だけ処理する
- `cap.read()` が途中のフレームで `ret=False` を返した場合: 警告を出力し、そのフレームは `tracker.update()` を呼ばずにスキップする（トラッカーの内部状態は前フレームのまま維持される）。スキップフレーム数はサマリーに含める

### 4.3 トラッキング実行（FR-3）

#### データフロー

- **入力**:
  - bbox情報: `list[dict]`（1フレーム分の人物bboxリスト）
  - フレーム画像: numpy.ndarray (H, W, 3), uint8, BGR
- **変換**: BoxMOT入力形式に変換
  - ndarray shape (N, 6): `[x1, y1, x2, y2, score, class]`
  - class は全て `0`（person）
- **出力**:
  - tracks: ndarray shape (M, 8): `[x1, y1, x2, y2, track_id, confidence, class, index]`
  - track_id は `tracks[:, 4].astype(int)` で取得

#### 処理ロジック

```python
from boxmot import DeepOcSort
from pathlib import Path
import numpy as np

# Re-IDモデルのパスをスクリプト位置基準で解決
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
reid_path = project_root / 'osnet_x0_25_msmt17.pt'

if not reid_path.exists():
    print(f"Error: Re-ID model not found: {reid_path}")
    print("feat-020のセットアップが完了しているか確認してください。")
    sys.exit(1)

# 初期化（1回のみ）
# その他のパラメータはBoxMOT v16.0.11のデフォルト値を使用する
# 主要デフォルト: det_thresh=0.3, max_age=30, min_hits=3, iou_threshold=0.3
tracker = DeepOcSort(
    reid_weights=reid_path,
    device=args.device,
    half=True if 'cuda' in args.device else False,
)

# フレームループ
for frame_idx in range(num_frames):
    ret, frame = cap.read()
    if not ret:
        # フレーム読み込み失敗: tracker.update()を呼ばずにスキップ
        skipped += 1
        continue

    people = all_bboxes[frame_idx]

    if len(people) == 0:
        dets = np.empty((0, 6), dtype=np.float32)
    else:
        dets = np.array([
            [*p['bbox'], p['bbox_score'], 0]
            for p in people
        ], dtype=np.float32)

    tracks = tracker.update(dets, frame)

    if len(tracks) > 0:
        track_ids = tracks[:, 4].astype(int)
```

上記コードは意図の伝達が目的であり、そのままコピーして使うものではない。

**Re-IDモデルファイルの配置**: `osnet_x0_25_msmt17.pt` はfeat-020でプロジェクトルート（`/home/sakagawa/git/ViTPose/`）にダウンロード済み。パスは `Path(__file__).resolve().parent.parent / 'osnet_x0_25_msmt17.pt'` でスクリプト位置基準の絶対パスに解決する。ファイルが存在しない場合はエラーメッセージを出力して終了する。

#### 境界条件

- 検出0人のフレーム: `np.empty((0, 6))` を渡す。trackerは内部状態を維持し、次フレーム以降で再出現時にIDを割り当てる
- 検出が途切れた後の再出現: Re-IDにより同一IDが割り当てられることが期待される

#### エラーハンドリング

- `tracker.update()` でエラーが発生した場合: エラーメッセージとフレーム番号を出力して処理を継続する（そのフレームはスキップ）。スキップしたフレーム数はサマリーに `Skipped frames: N` として出力する。総フレーム数にはスキップフレームも含める
- 最初の10フレームで連続してエラーが発生した場合: トラッカーの初期化に問題がある可能性が高いため、エラーメッセージを出力してスクリプトを終了する

### 4.4 結果出力（FR-4）

#### フレームごとの出力

```
Frame 0000: 1 person(s) [track_id: 1]
Frame 0001: 1 person(s) [track_id: 1]
...
```

フレームごとの出力は10フレームおきに表示する（全フレーム表示すると冗長なため）。

#### サマリー出力

```
=== Tracking Summary ===
Total frames: 1244
Skipped frames: 0
Unique track IDs: {1: 1200, 3: 44}
  ID 1: 1200 frames
  ID 3: 44 frames
Processing time: 12.3 sec (101.1 fps)
```

## 5. 該当なしのセクション

本案件はテストスクリプトの作成のみであり、以下は該当なし:

- **1.5 状態遷移**: GUI/ステートフル処理なし
- **1.6 ファイル・ディレクトリ設計**: ファイル出力なし（コンソール出力のみ）
- **1.8 ログ・デバッグ設計**: テストスクリプトのため、print文で十分

## 6. インターフェース定義

### 公開関数

テストスクリプトのため、`main()` 関数と `argparse` によるCLIのみ。再利用可能なモジュールとしては設計しない。

```python
def main() -> None:
    """テストスクリプトのエントリーポイント。"""
```

## 7. 設計判断

| 判断 | 採用案 | 却下案と理由 |
|------|--------|------------|
| 出力形式 | コンソール出力のみ | JSON出力 → 本案件は動作確認が目的であり、ファイル出力は不要 |
| フレーム出力頻度 | 10フレームおき | 全フレーム → 1244行の出力は冗長 |
| スクリプト配置場所 | `scripts/test_boxmot_offline.py` | `experiments/` → scriptsディレクトリがパイプラインスクリプトの格納場所 |
| half精度 | deviceにcudaが含まれる場合True、cpuの場合False | 常にTrue → CPU実行時にhalf=Trueだとエラーになる可能性がある |

## 8. テスト方法

```bash
uv run python scripts/test_boxmot_offline.py \
    --video testdata/pexels_4441000.mp4 \
    --json-dir experiments/results/feat-018-test/pexels_4441000_json/
```

合格条件:
1. エラーなく全1244フレームの処理が完了する
2. サマリーが出力される
3. 1人の人物に一貫したtrack_idが付与される
