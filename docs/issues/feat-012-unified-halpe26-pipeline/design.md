# feat-012: HALPE 26統合パイプライン 機能設計書

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|----------------|
| FR-001 | 4.1 推論パイプライン |
| FR-002 | 4.2 可視化動画出力 |
| FR-003 | 4.3 OpenPose JSON出力 |
| FR-004 | 4.4 出力モード選択 |

## 2. システム構成

### モジュール構成

```
scripts/
├── run_halpe26_pipeline.py    # [新規] 統合パイプラインスクリプト（本案件で作成）
├── merge_halpe26.py           # [既存] HALPE 26結合ロジック・描画・定数
└── halpe26_to_openpose.py     # [既存] OpenPose JSON変換関数
```

### 依存関係

```
run_halpe26_pipeline.py
├── merge_halpe26.py
│   ├── merge_to_halpe26()      # WholeBody+AIC → HALPE 26結合
│   ├── draw_halpe26()          # キーポイント描画
│   ├── DET_CONFIG/CHECKPOINT   # 人物検出モデルパス
│   ├── WB_CONFIG/CHECKPOINT    # WholeBodyモデルパス
│   └── AIC_CONFIG/CHECKPOINT   # AICモデルパス
├── halpe26_to_openpose.py
│   └── halpe26_to_openpose_json()  # HALPE 26 → OpenPose JSON変換
├── mmpose.apis                 # ポーズ推定API
└── mmdet.apis                  # 人物検出API
```

## 3. 技術スタック

既存スクリプトと同一。新規ライブラリの追加なし。

- Python 3.10.16
- MMPose 0.24.0, mmcv-full 1.7.2, mmdet 2.28.2
- OpenCV (cv2), NumPy

## 4. 各機能の詳細設計

### 4.1 推論パイプライン（FR-001）

#### データフロー

1. 入力: 動画ファイル（mp4等、OpenCVが読み込めるフォーマット）
2. フレーム読み出し: `cv2.VideoCapture` → `np.ndarray` (H, W, 3), dtype=uint8, BGR
3. 人物検出: `inference_detector(det_model, frame)` → `process_mmdet_results(mmdet_results, cat_id=1)` → `list[dict]`（bbox情報）
4. WholeBody推定: `inference_top_down_pose_model(wb_model, frame, person_results, bbox_thr=0.3, format='xyxy', dataset=wb_dataset, dataset_info=wb_dataset_info)` → `list[dict]`（各dictに`keypoints`: shape=(133, 3)）
5. AIC推定: `inference_top_down_pose_model(aic_model, frame, person_results, bbox_thr=0.3, format='xyxy', dataset=aic_dataset, dataset_info=aic_dataset_info)` → `list[dict]`（各dictに`keypoints`: shape=(14, 3)）
6. HALPE 26結合: `merge_to_halpe26(wb_kps, aic_kps)` → `np.ndarray` shape=(26, 3)
7. 中間データ: `all_halpe26: list[np.ndarray]`（長さ=検出人数、各要素 shape=(26, 3), dtype=float32。結果数不一致時は空リスト `[]`）

#### 処理ロジック

```
# モデル初期化
det_model = init_detector(DET_CONFIG, DET_CHECKPOINT, device=device)
wb_model = init_pose_model(WB_CONFIG, WB_CHECKPOINT, device=device)
aic_model = init_pose_model(AIC_CONFIG, AIC_CHECKPOINT, device=device)

# DatasetInfo取得（inference_top_down_pose_modelの引数に必要）
wb_dataset = wb_model.cfg.data['test']['type']
wb_dataset_info = DatasetInfo(wb_model.cfg.data['test']['dataset_info'])
aic_dataset = aic_model.cfg.data['test']['type']
aic_dataset_info = DatasetInfo(aic_model.cfg.data['test']['dataset_info'])

# 出力先準備
os.makedirs(args.out_dir, exist_ok=True)
video_stem = os.path.splitext(os.path.basename(args.video))[0]
動画オープン（cap = cv2.VideoCapture(args.video)）
if do_video:
    out_name = f'vis_halpe26_{os.path.basename(args.video)}'
    out_path = os.path.join(args.out_dir, out_name)
    writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))
if do_json:
    json_dir = os.path.join(args.out_dir, f'{video_stem}_json')
    os.makedirs(json_dir, exist_ok=True)

frame_idx = 0
while cap.isOpened():  # 既存スクリプトと同一パターン
    ret, frame = cap.read()
    if not ret:
        break
    人物検出 → person_results
    WholeBody推定 → wb_results
    AIC推定 → aic_results

    if len(wb_results) != len(aic_results):
        警告出力（print + "Warning:" prefix）
        all_halpe26 = []  # 空リスト: list[np.ndarray]
    else:
        all_halpe26 = [merge_to_halpe26(wb_results[i]['keypoints'],
                                         aic_results[i]['keypoints'])
                       for i in range(len(wb_results))]

    if do_video:
        vis_frame = frame.copy()  # 元フレームを保持するためコピー（既存コードと同一）
        for kps in all_halpe26:
            # draw_halpe26内部でもimg.copy()が実行される（既存動作と同一の二重コピー）
            vis_frame = draw_halpe26(vis_frame, kps)
        writer.write(vis_frame)

    if do_json:
        openpose_dict = halpe26_to_openpose_json(all_halpe26)  # list[np.ndarray]を渡す
        json_path = os.path.join(json_dir, f'{video_stem}_{frame_idx:06d}.json')
        with open(json_path, 'w') as f:
            json.dump(openpose_dict, f)  # インデントなし（既存と同一）

    if frame_idx % 100 == 0:  # フレーム0を含む
        print(f'Processing frame {frame_idx}/{total_frames}...')
    frame_idx += 1

リソース解放（cap.release, writer.release）
```

#### エラーハンドリング

| エラー | 検出方法 | 対処 |
|--------|----------|------|
| 動画オープン失敗 | `cap.isOpened()` が False | assertで即時停止、エラーメッセージ表示 |
| WholeBody/AIC結果数不一致 | `len(wb_results) != len(aic_results)` | 警告出力、該当フレームのキーポイントをスキップ（既存動作と同一） |
| 人物未検出 | `len(person_results) == 0` | 空の結果として正常処理（可視化は元フレーム、JSONは空のpeople） |

#### 境界条件

| 条件 | 振る舞い |
|------|----------|
| 0フレームの動画 | ループに入らず終了。可視化動画は0フレーム、JSONは0ファイル |
| 人物未検出フレーム | 可視化は元フレーム描画、JSONは`{"version": 1.3, "people": []}` |

### 4.2 可視化動画出力（FR-002）

#### データフロー

- 入力: 元フレーム画像 + HALPE 26キーポイント（人物ごと）
- 処理: `draw_halpe26(frame, keypoints, kpt_thr=0.3)` を人物ごとに呼び出し
- 出力: `{out-dir}/vis_halpe26_{os.path.basename(args.video)}`（既存コードと同一。`os.path.basename`は拡張子込みのファイル名を返す）

#### 処理ロジック

- `cv2.VideoWriter` を mp4v コーデックで初期化（入力動画と同一の fps, width, height）
- 各フレームで描画済み画像を `writer.write()` で書き込み
- modeが `json` の場合、video writerは作成しない

### 4.3 OpenPose JSON出力（FR-003）

#### データフロー

- 入力: HALPE 26キーポイントのリスト（人物ごと、各 shape=(26, 3)）
- 処理: `halpe26_to_openpose_json(all_halpe26)` で辞書に変換
- 出力: `{out-dir}/{video_stem}_json/{video_stem}_{frame_idx:06d}.json`

#### 処理ロジック

- 出力ディレクトリ `{out-dir}/{video_stem}_json/` を `os.makedirs(exist_ok=True)` で作成
- フレームごとに `json.dump()` で書き込み（既存と同一）
- modeが `video` の場合、JSONディレクトリは作成しない

### 4.4 出力モード選択（FR-004）

#### CLI引数

| 引数 | 型 | デフォルト | 選択肢 | 説明 |
|------|----|-----------|--------|------|
| `--video` | str | 必須 | - | 入力動画パス |
| `--out-dir` | str | `output/feat-012` | - | 出力ベースディレクトリ |
| `--device` | str | `cuda:0` | - | 推論デバイス |
| `--mode` | str | `both` | `both`, `video`, `json` | 出力モード |

#### 処理ロジック

- mode判定は推論ループの外で1回だけ行い、bool変数 `do_video` と `do_json` に変換する
  - `both`: `do_video=True, do_json=True`
  - `video`: `do_video=True, do_json=False`
  - `json`: `do_video=False, do_json=True`
- ループ内では `do_video` / `do_json` のフラグで出力を分岐する

## 5. ファイル・ディレクトリ設計

### 出力構成例

`--video /path/to/cam05520129.mp4 --out-dir output/feat-012 --mode both` の場合:

```
output/feat-012/
├── vis_halpe26_cam05520129.mp4          # 可視化動画
└── cam05520129_json/                     # OpenPose JSONディレクトリ
    ├── cam05520129_000000.json
    ├── cam05520129_000001.json
    └── ...
```

ファイル命名規則は既存スクリプトと完全に同一。

## 6. インターフェース定義

### 新規スクリプト: `scripts/run_halpe26_pipeline.py`

スクリプトレベルのエントリポイントのみ。再利用可能な関数の新規定義は不要（既存関数で十分）。

```python
def parse_args() -> argparse.Namespace:
    """CLI引数をパースする。"""

def main() -> None:
    """統合パイプラインのメイン処理。"""
```

### 再利用する既存関数

| 関数 | モジュール | 用途 |
|------|-----------|------|
| `merge_to_halpe26(wb_kps, aic_kps)` | merge_halpe26.py | WholeBody+AIC → HALPE 26結合 |
| `draw_halpe26(img, kps, kpt_thr)` | merge_halpe26.py | キーポイント描画 |
| `halpe26_to_openpose_json(all_halpe26)` | halpe26_to_openpose.py | OpenPose JSON変換 |

## 7. ログ・デバッグ設計

全て `print()` で出力する（既存スクリプトと同一方式）。WARNING相当のメッセージは先頭に `Warning:` を付与する:

| タイミング | 出力内容 | レベル |
|-----------|----------|--------|
| モデル初期化開始 | `Initializing models...` | INFO |
| モデル初期化完了 | `Models initialized.` | INFO |
| 動画オープン時 | `Processing video: {path} ({frames} frames, {fps} fps)` | INFO |
| 出力モード表示 | `Output mode: {mode}` | INFO |
| 100フレームごと | `Processing frame {idx}/{total}...` | INFO |
| 結果数不一致 | `Warning: frame {idx} result count mismatch ...` | WARNING |
| 完了時（動画） | `Saved: {path} ({frame_count} frames)` | INFO |
| 完了時（JSON） | `Saved {frame_count} JSON files to {dir}` | INFO |

## 8. 設計判断

### 採用案: 新規スクリプト `run_halpe26_pipeline.py` を作成

- 既存の `visualize_halpe26_video.py` と `halpe26_to_openpose.py` を残したまま、統合版を新規作成する
- 既存スクリプトは個別実行が必要なケースに備えて残す

### 却下案: 既存スクリプトを統合して1つにまとめる

- 理由: 既存スクリプトはfeat-010/011の成果物であり、テスト済み。削除・統合すると既存の動作確認結果が無効になる
