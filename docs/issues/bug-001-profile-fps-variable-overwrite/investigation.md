# bug-001: プロファイル表示で変数fpsが動画FPSを上書きする — 修正計画

## イテレーション1 (2026-03-29)

### 1.1 不具合の特定

- **現在の動作**: `scripts/run_halpe26_pipeline.py` 70行目で動画FPSを `fps` 変数に格納し、83行目で `cv2.VideoWriter` に渡している。191行目で処理速度（frames/sec）を同じ `fps` 変数に代入するため、70行目の値が上書きされる。現時点では191行目以降で動画FPSを参照する箇所がないため実害なし
- **再現手順**: `--profile` 付きで実行すると、191行目で `fps` が上書きされる
- **期待する動作**: 動画FPSと処理速度FPSが別変数で管理され、互いに干渉しない

### 1.2 原因分析

- **原因箇所**: `scripts/run_halpe26_pipeline.py` 191行目
  ```python
  fps = frame_idx / total_elapsed if total_elapsed > 0 else 0.0
  ```
- **原因の説明**: 処理速度FPSの変数名に動画FPSと同じ `fps` を使用している
- **根本原因**: 変数名の重複（根本原因）

### 1.3 修正内容

- **変更対象ファイル**: `scripts/run_halpe26_pipeline.py`
- **変更内容**: 191行目の変数名 `fps` を `processing_fps` にリネームし、192行目の参照も更新する
- **変更しないファイル**: なし（他ファイルへの影響なし）

**修正前** (191-193行目):
```python
fps = frame_idx / total_elapsed if total_elapsed > 0 else 0.0
print(f'\n--- Profile ({frame_idx} frames, {total_elapsed:.1f}s, '
      f'{fps:.1f} fps) ---')
```

**修正後**:
```python
processing_fps = frame_idx / total_elapsed if total_elapsed > 0 else 0.0
print(f'\n--- Profile ({frame_idx} frames, {total_elapsed:.1f}s, '
      f'{processing_fps:.1f} fps) ---')
```

### 1.4 影響範囲

- **他の機能への影響**: なし。`fps` 変数は191行目以降で他に参照されていない。`processing_fps` は192行目のprint文でのみ使用
- **リグレッションリスク**: なし。変数のリネームのみで、処理ロジックに変更なし

### 1.5 確認方法

- **テスト項目**: `--profile` 付き実行でプロファイル表示が正常に出力されること
- **テストコマンド**:
  ```bash
  cd /home/sakagawa/git/ViTPose
  uv run python scripts/run_halpe26_pipeline.py \
    --video testdata/pexels_4441000.mp4 \
    --out-dir experiments/results/bug-001-test \
    --mode video --profile
  ```
- **期待される出力**: `--- Profile (N frames, X.Xs, Y.Y fps) ---` が正常に表示される
