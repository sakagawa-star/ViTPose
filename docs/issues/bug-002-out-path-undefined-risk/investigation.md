# bug-002: --mode json時にout_pathが未定義で参照されるリスク — 修正計画

## イテレーション1 (2026-03-29)

### 1.1 不具合の特定

- **現在の動作**: `scripts/run_halpe26_pipeline.py` 81行目で `out_path` は `do_video=True` の場合のみ定義される。185-186行目で `if do_video:` ガード内で参照されているため、`--mode json` 時には到達しない。条件分岐のガードに依存した安全性であり、将来のリファクタリングで NameError が発生するリスクがある
- **再現手順**: 現時点では `--mode json` で実行しても正常動作する（ガードで保護されているため）
- **期待する動作**: `out_path` が常に定義されており、条件分岐のガードに依存しない

### 1.2 原因分析

- **原因箇所**: `scripts/run_halpe26_pipeline.py` 79-81行目（条件付き定義）と185-186行目（参照）
  ```python
  # 79-81行目
  if do_video:
      out_name = f'vis_halpe26_{os.path.basename(args.video)}'
      out_path = os.path.join(args.out_dir, out_name)
  ```
  ```python
  # 185行目
  if do_video:
      print(f'Saved: {out_path} ({frame_idx} frames)')
  ```
- **原因の説明**: `out_path` の定義が `if do_video:` ブロック内にあり、条件が False の場合は変数が存在しない
- **根本原因**: 変数の条件付き定義（根本原因）

### 1.3 修正内容

- **変更対象ファイル**: `scripts/run_halpe26_pipeline.py`
- **変更内容**: 77行目の `out_path` 初期値を `None` で定義する
- **変更しないファイル**: なし（他ファイルへの影響なし）

**修正前** (77-81行目):
```python
    writer = None
    json_dir = None
    if do_video:
        out_name = f'vis_halpe26_{os.path.basename(args.video)}'
        out_path = os.path.join(args.out_dir, out_name)
```

**修正後**:
```python
    writer = None
    json_dir = None
    out_path = None
    if do_video:
        out_name = f'vis_halpe26_{os.path.basename(args.video)}'
        out_path = os.path.join(args.out_dir, out_name)
```

### 1.4 影響範囲

- **他の機能への影響**: なし。`out_path` は83行目（VideoWriter）と186行目（print）でのみ使用され、両方とも `if do_video:` ガード内
- **リグレッションリスク**: なし。`out_path = None` の初期化追加のみで、既存の処理フローに変更なし。`do_video=True` 時は81行目で上書きされるため動作は同一

### 1.5 確認方法

- **テスト項目1**: `--mode json` で NameError が発生しないこと（既存動作の確認）
- **テスト項目2**: `--mode video` で動画が正常に出力されること（リグレッション確認）
- **テストコマンド**:
  ```bash
  cd /home/sakagawa/git/ViTPose
  # json モード
  uv run python scripts/run_halpe26_pipeline.py \
    --video testdata/pexels_4441000.mp4 \
    --out-dir experiments/results/bug-002-test \
    --mode json
  # video モード
  uv run python scripts/run_halpe26_pipeline.py \
    --video testdata/pexels_4441000.mp4 \
    --out-dir experiments/results/bug-002-test \
    --mode video
  ```
- **期待される出力**: 両モードとも正常終了し、それぞれJSON/動画が出力される
