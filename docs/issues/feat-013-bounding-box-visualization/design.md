# feat-013: バウンディングボックス描画 機能設計書

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|----------------|
| FR-001 | 4.1 BB描画関数 |
| FR-002 | 4.2 統合パイプラインへの組み込み |

## 2. システム構成

### 変更対象ファイル

```
scripts/
├── merge_halpe26.py           # [変更] draw_bbox関数を追加
└── run_halpe26_pipeline.py    # [変更] 可視化処理にdraw_bbox呼び出しを追加
```

### 依存関係

既存の依存関係に変更なし。`draw_bbox` は OpenCV のみ使用。

## 3. 技術スタック

既存と同一。新規ライブラリの追加なし。

## 4. 各機能の詳細設計

### 4.1 BB描画関数（FR-001）

#### インターフェース

`merge_halpe26.py` に以下の関数を追加する:

```python
def draw_bbox(
    img: np.ndarray,
    bbox: np.ndarray,
    color: tuple = (0, 255, 255),  # 黄色 (BGR)
    thickness: int = 2,
) -> np.ndarray:
```

#### データフロー

- 入力: `img` — BGR画像 `np.ndarray` (H, W, 3), dtype=uint8
- 入力: `bbox` — `np.ndarray` shape=(5,), `[x1, y1, x2, y2, score]`, dtype=float32
- 出力: BBとスコアが描画された画像 `np.ndarray` (H, W, 3)

#### 処理ロジック

```python
def draw_bbox(img, bbox, color=(0, 255, 255), thickness=2):
    img = img.copy()
    x1, y1, x2, y2, score = bbox[:5]
    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)
    label = f'{score:.2f}'
    cv2.putText(img, label, (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    return img
```

#### 設計判断

- **描画色**: 黄色 `(0, 255, 255)` (BGR) を採用。理由: キーポイントの緑（左）・オレンジ（右）・青（中央）と区別できる
- **スコア表示位置**: BBの左上 `(x1, y1 - 5)` に配置。y1が画像上端に近い場合、テキストが見切れる可能性があるが、実用上問題にならない（人物BBは通常画像内に余裕がある）
- **`img.copy()` を内部で実行**: `draw_halpe26` と同一方針。呼び出し元のフレームを変更しない。呼び出し元で `vis_frame = frame.copy()` 済みのため、複数人検出時に人数分のコピーが発生するが、推論処理に対して無視できるコストであり、既存の `draw_halpe26` と方針を統一することを優先する
- **関数の配置位置**: `merge_halpe26.py` 内の `draw_halpe26` 関数の直前に配置する

### 4.2 統合パイプラインへの組み込み（FR-002）

#### 変更箇所

`run_halpe26_pipeline.py` の可視化処理（`if do_video:` ブロック）を変更する。

#### 変更前

```python
if do_video:
    vis_frame = frame.copy()
    for kps in all_halpe26:
        vis_frame = draw_halpe26(vis_frame, kps)
    writer.write(vis_frame)
```

#### 変更後

```python
if do_video:
    vis_frame = frame.copy()
    # BB描画（キーポイントの下に描画するため、先にBBを描画）
    for i in range(len(wb_results)):
        vis_frame = draw_bbox(vis_frame, wb_results[i]['bbox'])
    # キーポイント・スケルトン描画
    for kps in all_halpe26:
        vis_frame = draw_halpe26(vis_frame, kps)
    writer.write(vis_frame)
```

#### 処理ロジック

- BBを先に描画し、キーポイント・スケルトンを後に描画する。これにより、キーポイントがBBの線に隠れない
- `wb_results` のbboxを使用する。理由: `wb_results` と `aic_results` は同一の `person_results` から推定されるため、同一のbboxを持つ。`wb_results` を代表として使用すれば十分
- 結果数不一致時（`all_halpe26` が空リスト）でも、BBは `wb_results` から描画する。件数不一致は検出はされたがWholeBody/AICの結合に失敗したフレームであり、BBだけでも描画することで検出モデルの動作確認に使える

#### エラーハンドリング

| 条件 | 振る舞い |
|------|----------|
| `wb_results` が空（人物未検出） | BBループに入らず、元フレームのまま |
| `bbox` のスコアが0に近い | 描画される（bbox_thr=0.3でフィルタ済みのため、0.3以上のもののみ存在） |
| bbox座標が画像範囲外（x1 < 0, x2 > width等） | OpenCVの`rectangle`/`putText`は内部でクリッピング処理を行うため、エラーにならない |
| `y1 - 5 < 0`（テキスト位置が画像外） | `putText`はクリッピングされ、テキストが見切れる。実用上問題にならないため対処しない |
| `wb_results` と `aic_results` の件数不一致 | BBのみ描画される（キーポイントは描画されない）。既存のWarningログ出力は維持 |

#### import変更

`run_halpe26_pipeline.py` の `merge_halpe26` からのimportに `draw_bbox` を追加する。

変更前:
```python
from merge_halpe26 import (merge_to_halpe26, draw_halpe26,
                            DET_CONFIG, DET_CHECKPOINT,
                            WB_CONFIG, WB_CHECKPOINT,
                            AIC_CONFIG, AIC_CHECKPOINT)
```

変更後:
```python
from merge_halpe26 import (merge_to_halpe26, draw_halpe26, draw_bbox,
                            DET_CONFIG, DET_CHECKPOINT,
                            WB_CONFIG, WB_CHECKPOINT,
                            AIC_CONFIG, AIC_CHECKPOINT)
```

## 5. ファイル・ディレクトリ設計

変更なし。出力ファイルのパス・命名規則は既存と同一。

## 6. ログ・デバッグ設計

追加のログ出力なし。BB描画は視覚的な変更のみ。

## 7. 設計判断

### 採用案: `merge_halpe26.py` に `draw_bbox` 関数を追加

- 描画関連の関数（`draw_halpe26`）と同じモジュールに配置し、凝集度を高める

### 却下案: `run_halpe26_pipeline.py` 内にインライン実装

- 理由: 今後 `visualize_halpe26_video.py` にもBB描画を追加する可能性があり、関数として共有可能にしておく方が再利用性が高い

### 却下案: `draw_halpe26` 関数にBB描画を統合

- 理由: `draw_halpe26` はキーポイント配列のみを引数に取る。bbox情報を追加すると関数シグネチャが変わり、既存の呼び出し箇所に影響する。単一責務を維持する
