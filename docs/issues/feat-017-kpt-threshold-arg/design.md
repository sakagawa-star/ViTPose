# feat-017: キーポイント描画のconfidence閾値を引数指定可能にする — 機能設計書

## 1.1 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001 | 1.4 各機能の詳細設計 |

## 1.2 システム構成

変更対象ファイル:
- `scripts/run_halpe26_pipeline.py` — CLI引数追加 + `draw_halpe26` 呼び出し時に閾値を渡す

変更しないファイル:
- `scripts/merge_halpe26.py` — `draw_halpe26` は既に `kpt_thr` 引数を持っているため変更不要
- `scripts/halpe26_to_openpose.py` — JSON出力には影響なし
- `scripts/visualize_halpe26_video.py` — 単体可視化スクリプトは本案件のスコープ外

## 1.3 技術スタック

既存の技術スタックのみ使用。追加ライブラリなし。

## 1.4 各機能の詳細設計

### FR-001: CLI引数 `--kpt-thr` の追加

#### データフロー

1. CLI引数 `--kpt-thr` → float型、値域0.0〜1.0、デフォルト0.3
2. `args.kpt_thr` → `draw_halpe26(vis_frame, kps, kpt_thr=args.kpt_thr)` に渡す

#### 処理ロジック

**`parse_args` の変更（`run_halpe26_pipeline.py`）:**

以下の引数を追加する:
```python
parser.add_argument('--kpt-thr', type=float, default=0.3,
                    help='Keypoint confidence threshold for drawing (0.0-1.0, default: 0.3)')
```

**`draw_halpe26` 呼び出しの変更（`for kps in all_halpe26:` ループ内の `draw_halpe26` 呼び出し、現在の158行目）:**

変更前:
```python
vis_frame = draw_halpe26(vis_frame, kps)
```

変更後:
```python
vis_frame = draw_halpe26(vis_frame, kps, kpt_thr=args.kpt_thr)
```

#### エラーハンドリング

- `--kpt-thr` に0.0〜1.0の範囲外の値が指定された場合: argparseでバリデーションを行わない。`draw_halpe26` はfloatの比較のみ行うため、0.0未満を指定すれば全キーポイント描画、1.0超を指定すれば全キーポイント非描画となる。実害がないため、範囲チェックは追加しない
- `--mode json` の場合: `do_video=False` となり `draw_halpe26` が呼ばれないため、`--kpt-thr` は自然に無視される

#### 境界条件

- `--kpt-thr 0.0`: 全キーポイントが描画される（confidence > 0.0 のキーポイント）
- `--kpt-thr 1.0`: confidence > 1.0 のキーポイントのみ描画 → 実質何も描画されない
- `--kpt-thr` 未指定: デフォルト0.3で従来と同じ動作

## 1.5 状態遷移

なし（ステートレス処理）

## 1.6 ファイル・ディレクトリ設計

変更なし。

## 1.7 インターフェース定義

`draw_halpe26`（`merge_halpe26.py`）のシグネチャは変更なし:
```python
def draw_halpe26(
    img: np.ndarray,
    keypoints: np.ndarray,
    kpt_thr: float = 0.3,
) -> np.ndarray:
```

`run_halpe26_pipeline.py` のCLI引数に以下が追加される:
- `--kpt-thr`: float, default=0.3, キーポイント描画の閾値

## 1.8 ログ・デバッグ設計

追加のログ出力なし。

## 設計判断の記録

### 範囲バリデーションを追加しない理由

- **採用案**: バリデーションなし。0.0〜1.0範囲外でも実害なし
- **却下案**: argparseのtype関数で範囲チェック → 過剰な防御。開発者ツールであり、範囲外の値を指定しても有害な動作にはならない
