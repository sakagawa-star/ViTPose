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

## test_boxmot_offline.py

既存のOpenPose JSON（bbox + bbox_score）と元動画を使い、BoxMOT Deep OC-SORTの動作を確認するテストスクリプト。ViTPose推論不要。

```bash
uv run python scripts/test_boxmot_offline.py \
  --video testdata/pexels_4441000.mp4 \
  --json-dir experiments/results/feat-018-test/pexels_4441000_json/
```

| 引数 | 型 | デフォルト | 説明 |
|------|----|-----------|------|
| `--video` | str | (必須) | 入力動画パス |
| `--json-dir` | str | (必須) | OpenPose JSONディレクトリ |
| `--device` | str | `cuda:0` | トラッカーのデバイス（`cuda:N` または `cpu`） |

## スクリプトの関係

```
run_halpe26_pipeline.py  ← 統合パイプライン（推奨）
  ├── merge_halpe26.py   ← 結合ロジック・描画関数（ライブラリとして使用）
  └── halpe26_to_openpose.py  ← JSON変換関数（ライブラリとして使用）

halpe26_to_openpose.py   ← JSON出力の単体スクリプト
visualize_halpe26_video.py  ← 動画可視化の単体スクリプト
merge_halpe26.py         ← 静止画の結合・可視化の単体スクリプト
```

postprocess_reid.py  ← 既存JSONにstable_idを付与するポストプロセス
  └── custom_reid.py  ← カスタムRe-IDモジュール（ライブラリとして使用）

visualize_tracking.py  ← stable_id付きJSONを使ったトラッキング可視化
  └── merge_halpe26.py  ← HALPE26_SKELETONをインポート
```

通常は `run_halpe26_pipeline.py` でJSON出力後、`postprocess_reid.py` でstable_idを付与し、`visualize_tracking.py` で可視化する。

## postprocess_reid.py

既存のHALPE 26 JSONと動画を入力とし、Deep OC-SORT + カスタムRe-IDでstable_idを付与した新しいJSONを出力する。ViTPose推論は行わない。

```bash
uv run python scripts/postprocess_reid.py \
  --video experiments/input/camSony1_L.mp4 \
  --json-dir experiments/results/camSony1_L_json/ \
  --out-dir experiments/results/camSony1_L_reid_json/
```

| 引数 | 型 | デフォルト | 説明 |
|------|-----|-----------|------|
| `--video` | str | (必須) | 動画ファイルパス |
| `--json-dir` | str | (必須) | 入力HALPE 26 JSONディレクトリ |
| `--out-dir` | str | (必須) | 出力JSONディレクトリ（`--json-dir`と異なるパスを指定） |
| `--device` | str | `cuda:0` | BoxMOTデバイス |

出力JSONは入力JSONの全フィールドを維持し、各personに `stable_id` フィールドを追加する。

## postprocess_track.py

既存のHALPE 26 JSONと動画を入力とし、Deep OC-SORT単独で各人物に `track_id` フィールドを付与した新しいJSONを出力する。`custom_reid.py` / `stable_id` 関連のロジックは使用しない。feat-034 ロードマップの Stage 2（track_id 付与）として feat-035 で追加。

```bash
uv run python scripts/postprocess_track.py \
  --video testdata/camSony1_S.mp4 \
  --json-dir experiments/results/camSony1_S_json/ \
  --out-dir experiments/results/camSony1_S_track_json/
```

| 引数 | 型 | デフォルト | 説明 |
|------|-----|-----------|------|
| `--video` | str | (必須) | 動画ファイルパス |
| `--json-dir` | str | (必須) | 入力HALPE 26 JSONディレクトリ |
| `--out-dir` | str | (必須) | 出力JSONディレクトリ（`--json-dir`と異なるパスを指定） |
| `--device` | str | `cuda:0` | BoxMOTデバイス |

出力JSONは入力JSONの全フィールド（`stable_id` / `pink_id` を含む）を維持し、各personに `track_id` フィールドを追加する。マッチしない人物・無効な bbox を持つ人物は `track_id = -1`。

## postprocess_pink_id.py

既存のHALPE 26 JSONと動画を入力とし、各人物BBのHSVピンクマスク比率ベースで「ピンク服の患者」BBを選択し、各personに `pink_id` フィールド（選択=1 / 非選択=-1）を付与した新しいJSONを出力する。ViTPose推論・トラッカーは不要。feat-033 で追加。

参考元: `/home/sakagawa/Downloads/pink_tracker_jhub.py`（別プロジェクト）。HSVレンジ・閾値は固定値（`FIXED_HSV_RANGES`、`MIN_PINK_RATIO=0.03`、`IOU_CONT_WEIGHT=0.05`）。

```bash
uv run python scripts/postprocess_pink_id.py \
  --video testdata/camSony1_S.mp4 \
  --json-dir experiments/results/camSony1_S_json/ \
  --out-dir experiments/results/camSony1_S_pink_json/
```

| 引数 | 型 | デフォルト | 説明 |
|------|-----|-----------|------|
| `--video` | str | (必須) | 動画ファイルパス |
| `--json-dir` | str | (必須) | 入力HALPE 26 JSONディレクトリ |
| `--out-dir` | str | (必須) | 出力JSONディレクトリ（`--json-dir`と異なるパスを指定） |

出力JSONは入力JSONの全フィールド（`stable_id` を含む）を維持し、各personに `pink_id` フィールドを追加する。1フレーム内で `pink_id=1` となる人物は最大1人。

## visualize_tracking.py

stable_id付きJSONと元動画から、トラッキングIDごとに色分けしたスケルトン・BB・IDテキストを描画したMP4動画を出力する。

```bash
# 全stable_id色分け描画（全体モード）
uv run python scripts/visualize_tracking.py \
  --video experiments/input/camSony1_L.mp4 \
  --json-dir experiments/results/camSony1_L_reid_json/ \
  --out-dir output

# 指定stable_idのみ描画（フィルタモード）
uv run python scripts/visualize_tracking.py \
  --video experiments/input/camSony1_L.mp4 \
  --json-dir experiments/results/camSony1_L_reid_json/ \
  --out-dir output \
  --ids 1 2
```

| 引数 | 型 | デフォルト | 説明 |
|------|-----|-----------|------|
| `--video` | str | (必須) | 入力動画パス |
| `--json-dir` | str | (必須) | stable_id付きJSONディレクトリ |
| `--ids` | int... | None | 描画対象のstable_idリスト（省略で全体モード） |
| `--out-dir` | str | `output` | 出力ディレクトリ |
| `--kpt-thr` | float | `0.3` | キーポイント描画のconfidence閾値（0.0-1.0） |
