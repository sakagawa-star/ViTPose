# feat-014: パイプライン処理速度プロファイリング 機能設計書

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|----------------|
| FR-001 | 4.1 プロファイリング機能 |

## 2. システム構成

### 変更対象ファイル

```
scripts/
└── run_halpe26_pipeline.py    # [変更] --profileオプションと計測コードを追加
```

### 依存関係

新規依存なし。標準ライブラリ `time` のみ追加import。`import time` はモジュールレベルで無条件に行う（計測コードの「実行」には含まない）。

## 3. 技術スタック

既存と同一。新規ライブラリの追加なし。

## 4. 各機能の詳細設計

### 4.1 プロファイリング機能（FR-001）

#### CLI引数追加

`parse_args()` に以下を追加:

```python
parser.add_argument('--profile', action='store_true',
                    help='Enable per-step profiling')
```

#### データフロー

- 入力: `args.profile` フラグ（bool）
- 中間データ: ステップ名をキーとする累積時間の辞書 `profile: dict[str, float]`
- 出力: 処理完了後に標準出力へ計測結果テーブルを表示

#### 処理ロジック

**import追加**（ファイル先頭）:

変更前:
```python
import argparse
import json
import os
import sys
```

変更後:
```python
import argparse
import json
import os
import sys
import time
```

**main() 内の変更**（`# [追加]` = 新規追加コード、それ以外は既存コード）:

```python
    # [追加] プロファイル用辞書の初期化（--profile時のみ）
    if args.profile:
        profile = {
            'read': 0.0, 'det': 0.0, 'wb': 0.0, 'aic': 0.0,
            'merge': 0.0, 'draw': 0.0, 'json': 0.0,
        }
        total_start = time.time()

    # 5. Frame loop（既存コード、変更なし）
    frame_idx = 0
    while cap.isOpened():
        # [追加] 計測: フレーム読み出し
        if args.profile:
            t = time.time()
        ret, frame = cap.read()  # 既存コード
        if not ret:
            break
        if args.profile:
            profile['read'] += time.time() - t

        # 5a. Person detection（既存コード）
        if args.profile:
            t = time.time()
        mmdet_results = inference_detector(det_model, frame)
        person_results = process_mmdet_results(mmdet_results, cat_id=1)
        if args.profile:
            profile['det'] += time.time() - t

        # 5b. WholeBody estimation（既存コード、引数省略）
        if args.profile:
            t = time.time()
        wb_results, _ = inference_top_down_pose_model(...)
        if args.profile:
            profile['wb'] += time.time() - t

        # 5c. AIC estimation（既存コード、引数省略）
        if args.profile:
            t = time.time()
        aic_results, _ = inference_top_down_pose_model(...)
        if args.profile:
            profile['aic'] += time.time() - t

        # 5d. Merge to HALPE 26（既存コード）
        if args.profile:
            t = time.time()
        # ... 既存のmerge処理をそのまま維持 ...
        if args.profile:
            profile['merge'] += time.time() - t

        # 5e. Video output（既存コード）
        if do_video:
            if args.profile:
                t = time.time()
            # ... 既存の描画処理をそのまま維持 ...
            if args.profile:
                profile['draw'] += time.time() - t

        # 5f. JSON output（既存コード）
        if do_json:
            if args.profile:
                t = time.time()
            # ... 既存のJSON処理をそのまま維持 ...
            if args.profile:
                profile['json'] += time.time() - t

        # 進捗表示（既存コード、変更なし）
        if frame_idx % 100 == 0:
            print(f'Processing frame {frame_idx}/{total_frames}...')
        frame_idx += 1

    # [追加] 計測: 全体時間
    if args.profile:
        total_elapsed = time.time() - total_start
```

**計測結果の表示**（リソース解放後、`--profile` 時のみ）:

```python
if args.profile:
    fps = frame_idx / total_elapsed if total_elapsed > 0 else 0.0
    print(f'\n--- Profile ({frame_idx} frames, {total_elapsed:.1f}s, '
          f'{fps:.1f} fps) ---')
    print(f'{"Step":<12} {"Total(s)":>10} {"Avg(ms)":>10} {"Ratio":>8}')
    for key, label in [('read', 'Read'),
                       ('det', 'Detection'),
                       ('wb', 'WholeBody'),
                       ('aic', 'AIC'),
                       ('merge', 'Merge'),
                       ('draw', 'Draw'),
                       ('json', 'JSON')]:
        total_s = profile[key]
        avg_ms = (total_s / frame_idx * 1000) if frame_idx > 0 else 0
        ratio = (total_s / total_elapsed * 100) if total_elapsed > 0 else 0
        print(f'{label:<12} {total_s:>10.2f} {avg_ms:>10.1f} {ratio:>7.1f}%')
```

#### 出力例

```
--- Profile (900 frames, 180.3s, 5.0 fps) ---
Step           Total(s)    Avg(ms)    Ratio
Read               0.52        0.6      0.3%
Detection         30.15       33.5     16.7%
WholeBody         65.20       72.4     36.2%
AIC               62.80       69.8     34.8%
Merge              0.05        0.1      0.0%
Draw               8.50        9.4      4.7%
JSON               2.10        2.3      1.2%
```

（上記は推定値であり、実測値は異なる）

#### エラーハンドリング

| 条件 | 振る舞い |
|------|----------|
| `--profile` なし | profile辞書の初期化、`total_start`、`total_elapsed`、各ステップの計測コードは全て実行されない。既存動作と同一 |
| 0フレームの動画 | ループに入らず終了。profile表示時は `frame_idx=0` のため avg_ms=0、`total_elapsed` が0の場合 fps=0.0 |

## 5. ファイル・ディレクトリ設計

変更なし。出力ファイルに影響なし。

## 6. ログ・デバッグ設計

`--profile` 時のみ、処理完了後にプロファイル結果テーブルを `print()` で標準出力（stdout）に出力する。

## 7. インターフェース定義

### `parse_args()` の戻り値変更

`argparse.Namespace` に `profile: bool` フィールドが追加される。`--profile` 指定時は `True`、未指定時は `False`。

## 8. 設計判断

### 採用案: `time.time()` による手動計測

- シンプルで追加依存なし。各ステップの累積時間を辞書に加算するのみ

### 却下案: `cProfile` や `torch.profiler` の使用

- 理由: 関数呼び出し単位の詳細なプロファイルは不要。処理ステップ単位の所要時間がわかれば十分。外部ツールは出力が冗長で、ボトルネックの特定が難しくなる

### 却下案: 常時計測（`--profile` フラグなし）

- 理由: 計測コード自体のオーバーヘッドは小さいが、通常実行時に不要な出力を避けるためフラグで制御する
