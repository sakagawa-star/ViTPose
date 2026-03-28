# feat-015: WholeBody/AIC並列推論 機能設計書

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|----------------|
| FR-001 | 4.1 並列推論 |

## 2. システム構成

### 変更対象ファイル

```
scripts/
└── run_halpe26_pipeline.py    # [変更] WholeBody/AICの並列実行
```

### 依存関係

新規依存なし。標準ライブラリ `concurrent.futures` のみ追加import。

## 3. 技術スタック

既存と同一。新規ライブラリの追加なし。

## 4. 各機能の詳細設計

### 4.1 並列推論（FR-001）

#### データフロー

- 入力: `frame` (np.ndarray), `person_results` (list[dict]) — 既存と同一
- 並列実行: WholeBody推定とAIC推定を2スレッドで同時実行
- 出力: `wb_results` (list[dict]), `aic_results` (list[dict]) — 既存と同一

#### 処理ロジック

**import追加**（ファイル先頭）:

変更前:
```python
import argparse
import json
import os
import sys
import time
```

変更後:
```python
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import sys
import time
```

**main() 内の変更**:

`ThreadPoolExecutor` をフレームループの外で1回だけ作成し、ループ内で再利用する。ループ終了後に `shutdown` する。

```python
    # [追加] スレッドプール作成（既存コードの行84と行86の間、出力ターゲット作成後、フレームループ開始前）
    executor = ThreadPoolExecutor(max_workers=2)

    # 5. Frame loop（既存コード）
    frame_idx = 0
    while cap.isOpened():
        # ... フレーム読み出し、人物検出は既存と同一 ...

        # [変更] 5b+5c. WholeBody + AIC 並列推論
        if args.profile:
            t = time.time()
        wb_future = executor.submit(
            inference_top_down_pose_model,
            wb_model, frame, person_results, bbox_thr=0.3,
            format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)
        aic_future = executor.submit(
            inference_top_down_pose_model,
            aic_model, frame, person_results, bbox_thr=0.3,
            format='xyxy', dataset=aic_dataset, dataset_info=aic_dataset_info)
        wb_results, _ = wb_future.result()
        aic_results, _ = aic_future.result()
        if args.profile:
            profile['pose'] += time.time() - t

        # 5d〜5f は既存と同一 ...

    # [追加] スレッドプール終了（リソース解放セクション）
    # wait=True で全スレッドの完了を待つ（例外でループを抜けた場合の安全性確保）
    executor.shutdown(wait=True)
```

#### 変更前後の対比

**変更前**（ステップ5b + 5c、逐次実行）:
```python
        # 5b. WholeBody estimation
        if args.profile:
            t = time.time()
        wb_results, _ = inference_top_down_pose_model(
            wb_model, frame, person_results, bbox_thr=0.3,
            format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)
        if args.profile:
            profile['wb'] += time.time() - t

        # 5c. AIC estimation
        if args.profile:
            t = time.time()
        aic_results, _ = inference_top_down_pose_model(
            aic_model, frame, person_results, bbox_thr=0.3,
            format='xyxy', dataset=aic_dataset, dataset_info=aic_dataset_info)
        if args.profile:
            profile['aic'] += time.time() - t
```

**変更後**（ステップ5b+5c、並列実行）:
```python
        # 5b+5c. WholeBody + AIC parallel estimation
        if args.profile:
            t = time.time()
        wb_future = executor.submit(
            inference_top_down_pose_model,
            wb_model, frame, person_results, bbox_thr=0.3,
            format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)
        aic_future = executor.submit(
            inference_top_down_pose_model,
            aic_model, frame, person_results, bbox_thr=0.3,
            format='xyxy', dataset=aic_dataset, dataset_info=aic_dataset_info)
        wb_results, _ = wb_future.result()
        aic_results, _ = aic_future.result()
        if args.profile:
            profile['pose'] += time.time() - t
```

#### プロファイル辞書の変更

変更前:
```python
profile = {
    'read': 0.0, 'det': 0.0, 'wb': 0.0, 'aic': 0.0,
    'merge': 0.0, 'draw': 0.0, 'json': 0.0,
}
```

変更後:
```python
profile = {
    'read': 0.0, 'det': 0.0, 'pose': 0.0,
    'merge': 0.0, 'draw': 0.0, 'json': 0.0,
}
```

#### プロファイル表示の変更

変更前:
```python
for key, label in [('read', 'Read'),
                   ('det', 'Detection'),
                   ('wb', 'WholeBody'),
                   ('aic', 'AIC'),
                   ('merge', 'Merge'),
                   ('draw', 'Draw'),
                   ('json', 'JSON')]:
```

変更後:
```python
for key, label in [('read', 'Read'),
                   ('det', 'Detection'),
                   ('pose', 'Pose(WB+AIC)'),
                   ('merge', 'Merge'),
                   ('draw', 'Draw'),
                   ('json', 'JSON')]:
```

#### エラーハンドリング

| 条件 | 振る舞い |
|------|----------|
| スレッド内で例外発生 | `future.result()` が例外を再送出する。既存のエラーハンドリングと同等 |
| 人物未検出（person_results が空） | 両スレッドとも空の結果を返す。既存と同一の動作 |

#### 境界条件

| 条件 | 振る舞い |
|------|----------|
| 0フレームの動画 | ループに入らず終了。executor.shutdown() は正常に完了 |

## 5. ファイル・ディレクトリ設計

変更なし。出力ファイルに影響なし。

## 6. ログ・デバッグ設計

プロファイル出力の `WholeBody` と `AIC` の行が `Pose(WB+AIC)` に統合される。並列化後はWholeBody/AICの個別計測ができなくなる。個別計測が必要な場合は、並列化前のコードに一時的に切り戻して逐次実行する。それ以外の変更なし。

## 7. インターフェース定義

CLI引数の変更なし。`parse_args()` の戻り値の変更なし。

## 8. 設計判断

### 採用案: `ThreadPoolExecutor(max_workers=2)` で `inference_top_down_pose_model` を並列実行

- 最小限の変更（約10行の変更）で実装可能
- PyTorchのCUDAカーネル実行中にGILが解放されるため、一方のGPU推論中に他方のCPU前処理をオーバーラップできる
- 効果が見込めない場合はコードを元に戻す（実験的案件）

### 却下案: CUDAストリームによる並列化

- 理由: mmpose のAPIを分解して前処理・推論・後処理を分離する必要があり、変更量が大きい。効果もGPU計算リソース飽和により限定的

### 却下案: multiprocessing による並列化

- 理由: GPUメモリが2倍必要、プロセス間通信のオーバーヘッドが大きい。1GPU環境では非推奨

### 設計上の注意: スレッドセーフティ

- **`frame` の共有**: `inference_top_down_pose_model` は内部で `frame` を読み取り専用で使用する。`TopDownAffine` が `cv2.warpAffine` で新しい配列を生成するため、元の `frame` は変更されない。2スレッドからの同時読み取りは安全
- **`person_results` の共有**: `inference_top_down_pose_model` 内部で `person_result.copy()` で各要素をコピーして使用する。元のリストや要素は変更されない。安全
- **PyTorchモデルの並列実行**: `wb_model` と `aic_model` は別オブジェクトであり、`torch.no_grad()` 内のフォワードパスは異なるスレッドから呼び出し可能（PyTorchが公式にサポート）。ただしCUDAのデフォルトストリームでは実際のGPU計算は逐次化される可能性がある。CPU側の前処理（アフィン変換、正規化等のパイプライン処理）はオーバーラップされる
- **パイプライン構築のスレッドセーフティ**: `_inference_single_pose_model` 内で `Compose(cfg.test_pipeline)` が呼ばれるが、`wb_model.cfg` と `aic_model.cfg` は別オブジェクト。MMCVレジストリ(`PIPELINES`)は構築済みクラスの読み取り専用アクセスのみであり、安全
