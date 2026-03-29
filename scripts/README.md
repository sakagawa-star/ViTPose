# scripts/

HALPE 26キーポイント推定パイプラインのスクリプト群。

## run_halpe26_pipeline.py（推奨）

統合パイプライン。動画からHALPE 26キーポイントを推定し、可視化動画とOpenPose JSONを出力する。

```bash
# 動画 + JSON（デフォルト）
uv run python scripts/run_halpe26_pipeline.py \
  --video testdata/pexels_4441000.mp4 \
  --out-dir output

# JSONのみ出力
uv run python scripts/run_halpe26_pipeline.py \
  --video testdata/pexels_4441000.mp4 \
  --out-dir output \
  --mode json

# 動画のみ出力（キーポイント閾値を変更）
uv run python scripts/run_halpe26_pipeline.py \
  --video testdata/pexels_4441000.mp4 \
  --out-dir output \
  --mode video --kpt-thr 0.5

# プロファイリング付き
uv run python scripts/run_halpe26_pipeline.py \
  --video testdata/pexels_4441000.mp4 \
  --out-dir output \
  --profile
```

| 引数 | 型 | デフォルト | 説明 |
|------|----|-----------|------|
| `--video` | str | (必須) | 入力動画パス |
| `--out-dir` | str | `output` | 出力ディレクトリ |
| `--device` | str | `cuda:0` | 推論デバイス |
| `--mode` | str | `both` | 出力モード: `both`, `video`, `json` |
| `--kpt-thr` | float | `0.3` | キーポイント描画のconfidence閾値（0.0-1.0） |
| `--profile` | flag | - | ステップごとの処理時間を表示 |

### 出力

- `--mode video` / `both`: `{out-dir}/vis_halpe26_{動画ファイル名}` （可視化動画）
- `--mode json` / `both`: `{out-dir}/{動画stem}_json/{動画stem}_{フレーム番号:06d}.json` （OpenPose JSON）

### JSON出力フォーマット

```json
{
  "version": 1.3,
  "people": [
    {
      "person_id": [-1],
      "pose_keypoints_2d": [x0, y0, c0, x1, y1, c1, ...],
      "bbox_score": 0.968,
      "bbox": [40.0, 185.0, 1515.0, 1077.0],
      "face_keypoints_2d": [],
      "hand_left_keypoints_2d": [],
      "hand_right_keypoints_2d": [],
      "pose_keypoints_3d": [],
      "face_keypoints_3d": [],
      "hand_left_keypoints_3d": [],
      "hand_right_keypoints_3d": []
    }
  ]
}
```

- `pose_keypoints_2d`: HALPE 26キーポイント（26点 x 3値 = 78要素）。各キーポイントは [x, y, confidence]
- `bbox_score`: 人物検出のバウンディングボックス信頼度スコア（0.0-1.0）
- `bbox`: バウンディングボックスのROI座標 [x1, y1, x2, y2]（ピクセル単位）

## merge_halpe26.py

WholeBody 133 + AIC 14 からHALPE 26キーポイントを結合する。静止画1枚に対して実行。

```bash
uv run python scripts/merge_halpe26.py \
  --img testdata/sample.jpg \
  --out-dir output/merge-test \
  --device cuda:0
```

| 引数 | 型 | デフォルト | 説明 |
|------|----|-----------|------|
| `--img` | str | (必須) | 入力画像パス |
| `--out-dir` | str | `output/feat-009` | 出力ディレクトリ |
| `--device` | str | `cuda:0` | 推論デバイス |

### 出力

- `{out-dir}/halpe26_keypoints.npy` — キーポイントのnumpy配列
- `{out-dir}/vis_halpe26.jpg` — 可視化画像

## halpe26_to_openpose.py

動画からHALPE 26キーポイントを推定し、OpenPose JSON形式で出力する（動画可視化なし）。

```bash
uv run python scripts/halpe26_to_openpose.py \
  --video testdata/pexels_4441000.mp4 \
  --out-dir output/openpose-test \
  --device cuda:0
```

| 引数 | 型 | デフォルト | 説明 |
|------|----|-----------|------|
| `--video` | str | (必須) | 入力動画パス |
| `--out-dir` | str | `output/feat-010` | 出力ディレクトリ |
| `--device` | str | `cuda:0` | 推論デバイス |

## visualize_halpe26_video.py

動画にHALPE 26キーポイントを描画する（JSON出力なし）。

```bash
uv run python scripts/visualize_halpe26_video.py \
  --video testdata/pexels_4441000.mp4 \
  --out-dir output/vis-test \
  --device cuda:0
```

| 引数 | 型 | デフォルト | 説明 |
|------|----|-----------|------|
| `--video` | str | (必須) | 入力動画パス |
| `--out-dir` | str | `output/feat-011` | 出力ディレクトリ |
| `--device` | str | `cuda:0` | 推論デバイス |

## スクリプトの関係

```
run_halpe26_pipeline.py  ← 統合パイプライン（推奨）
  ├── merge_halpe26.py   ← 結合ロジック・描画関数（ライブラリとして使用）
  └── halpe26_to_openpose.py  ← JSON変換関数（ライブラリとして使用）

halpe26_to_openpose.py   ← JSON出力の単体スクリプト
visualize_halpe26_video.py  ← 動画可視化の単体スクリプト
merge_halpe26.py         ← 静止画の結合・可視化の単体スクリプト
```

通常は `run_halpe26_pipeline.py` を使用する。他のスクリプトは開発時の動作確認用。
