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

既存のHALPE 26 JSONと動画を入力とし、各人物BBのHSVピンクマスク比率ベースで「ピンク服の患者」BBを選択し、各personに `pink_id` フィールド（選択=1 / 非選択=-1）と `pink_ratio` フィールド（当該BBのHSVピンク画素比率、float、値域 [0.0, 1.0]、デバッグ用）を付与した新しいJSONを出力する。ViTPose推論・トラッカーは不要。feat-033 で追加、feat-039 で `pink_ratio` を追加、feat-046 で keypoint-rect ROI モードを追加。

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
| `--roi-mode` | str | `bb` | pink_ratio 計算に使う ROI。`bb`（既存挙動、人物 BB）または `keypoint-rect`（HALPE26 胴体 4 点の軸並行最小矩形、feat-046） |
| `--kpt-conf-min` | float | `0.3` | keypoint-rect ROI で使うキーポイントの信頼度閾値、値域 `[0.0, 1.0]` |
| `--min-roi-area` | int | `200` | keypoint-rect ROI の最低面積（px²）、値域 `>=1`。下回ったら `fail_area` として ratio=0.0 |
| `--min-pink-ratio` | float | `0.03` | pink_id=1 候補とする最低 `pink_ratio`、値域 `[0.0, 1.0]`（feat-050 で CLI 化）|

出力JSONは入力JSONの全フィールド（`stable_id` を含む）を維持し、各personに `pink_id` フィールドを追加する。1フレーム内で `pink_id=1` となる人物は最大1人。`--roi-mode keypoint-rect` のときは追加で `roi_mode`（文字列 `"keypoint-rect"`）と `roi_bbox`（`[x1,y1,x2,y2]` または ROI 構築失敗時 `null`）を各 person に書き込む（`bb` モード時は書き込まない、既存 JSON と完全互換）。`keypoint-rect` モードではサマリ末尾に ROI 構築成功 / `fail_kpt`（信頼点 2 個未満）/ `fail_area`（面積 < `--min-roi-area`）の 3 統計を表示する。

## postprocess_patient_id.py

既存のHALPE 26 JSON（`pink_id` と `track_id` が両方付与済み）を入力とし、各人物BBに `pink_track_id` フィールドを付与した新しいJSONを出力する。`pink_id`（種）と `track_id`（拡張手段）の階層構造で患者を判定する。動画ファイルは不要（JSON のみで完結）。feat-034 ロードマップの Stage 4 として feat-036 で追加。

```bash
uv run python scripts/postprocess_patient_id.py \
  --json-dir experiments/results/camSony1_S_pink_json/ \
  --out-dir experiments/results/camSony1_S_patient_json/
```

| 引数 | 型 | デフォルト | 説明 |
|------|-----|-----------|------|
| `--json-dir` | str | (必須) | 入力HALPE 26 JSONディレクトリ（`pink_id` / `track_id` 付与済み） |
| `--out-dir` | str | (必須) | 出力JSONディレクトリ（`--json-dir`と異なるパスを指定） |

出力JSONは入力JSONの全フィールド（`pink_id` / `track_id` / `stable_id` を含む）を維持し、各personに `pink_track_id` フィールドを追加する。値域: `1`（患者）/ `-1`（非患者）/ `-2`（重複BB）。

## plot_pink_track_timeline.py

feat-036 出力のHALPE 26 JSON（`pink_track_id` 付与済み）から、時系列グラフ（5パネル構成のPNG画像1枚）を出力する診断ツール。動画ファイルは不要。feat-037 で追加。

```bash
uv run python scripts/plot_pink_track_timeline.py \
  --json-dir experiments/results/camSony1_S_patient_json/ \
  --out-path experiments/results/pink_track_timeline_camSony1_S.png
```

| 引数 | 型 | デフォルト | 説明 |
|------|-----|-----------|------|
| `--json-dir` | str | (必須) | 入力JSONディレクトリ（`pink_track_id` 付与済み） |
| `--out-path` | str | (必須) | 出力PNGファイルパス |

5パネル構成: (1) pink_track_id=1有無、(2) BB数内訳、(3) 患者BBのtrack_id推移、(4) 患者BBのbbox_score推移、(5) pink_id=1有無。

## plot_pink_ratio_timeline.py

feat-039 改修済み `postprocess_pink_id.py` 出力 JSON（`pink_id` / `pink_ratio` 付与済み）から、時系列グラフ（4 パネル構成の PNG 画像 1 枚）を出力する診断ツール。動画ファイルは不要。feat-040 で追加。

```bash
uv run python scripts/plot_pink_ratio_timeline.py \
  --json-dir experiments/results/camSony1_L_pink_json/ \
  --out-path experiments/results/pink_ratio_timeline_camSony1_L.png
```

| 引数 | 型 | デフォルト | 説明 |
|------|-----|-----------|------|
| `--json-dir` | str | (必須) | 入力JSONディレクトリ（`pink_id` / `pink_ratio` 付与済み） |
| `--out-path` | str | (必須) | 出力PNGファイルパス |
| `--frame-start` | int | 0 | 描画開始フレーム番号（JSONファイル名末尾の6桁） |
| `--frame-end` | int | -1 | 描画終了フレーム番号。-1 で最終フレーム |

4 パネル構成: (1) 全 BB の `pink_ratio` 散布図 + 閾値ライン (`MIN_PINK_RATIO=0.03`)、(2) `pink_id=1` 有無、(3) BB 数内訳（`pink_id=1` / `-1` かつ候補 / `-1` かつ非候補）、(4) 「選択 BB ratio − 次点 BB ratio」差分（差分 < 0.05 のフレームは赤背景帯で強調）。次点 BB は同フレーム全 BB の `pink_ratio` 降順 2 位（選択 BB を含む全体ランキング）で定義。camSony1_L（321K フレーム）で約 37 秒で完走。

## visualize_patient_video.py

元動画に BB・スケルトン・ID テキスト・bbox_score をオーバーレイした MP4 を出力する。`--id-type` で描画に使用する ID 種別（pink_track_id/pink_id/track_id）を選択、`--mode` で描画モード（filter: 指定 ID 値のみ / all: 全 BB 色分け）を切替できる。feat-038 で追加。feat-042 で BB 内部に診断フィールド（`bb_index` / `pink_id` / `pink_ratio` / `iou_with_prev` / `selection_score`）を 1 行描画する機能を追加（フィールド別 ON/OFF フラグ 5 個、デフォルト全 ON）。

```bash
# pink_track_id=1 のみ描画（filter モード）
uv run python scripts/visualize_patient_video.py \
  --video testdata/camSony1_S.mp4 \
  --json-dir experiments/results/camSony1_S_patient_json/ \
  --out-dir experiments/results \
  --id-type pink_track_id --mode filter --filter-values 1

# 全 BB 色分け描画（all モード）
uv run python scripts/visualize_patient_video.py \
  --video testdata/camSony1_S.mp4 \
  --json-dir experiments/results/camSony1_S_patient_json/ \
  --out-dir experiments/results \
  --id-type pink_track_id --mode all
```

| 引数 | 型 | デフォルト | 説明 |
|------|-----|-----------|------|
| `--video` | str | (必須) | 入力動画ファイル |
| `--json-dir` | str | (必須) | 入力JSONディレクトリ |
| `--out-dir` | str | `output` | 出力ディレクトリ |
| `--id-type` | str | `pink_track_id` | ID種別: `pink_track_id` / `pink_id` / `track_id` |
| `--mode` | str | `all` | 描画モード: `filter`（指定ID値のみ） / `all`（全BB色分け） |
| `--filter-values` | int list | `[1]` | filterモード時の対象ID値 |
| `--draw-start` | int | `0` | 描画開始フレーム |
| `--draw-end` | int | `-1` | 描画終了フレーム（-1=末尾まで） |
| `--kpt-thr` | float | `0.3` | キーポイント描画のconfidence閾値 |
| `--show-bb-index` / `--no-show-bb-index` | bool | True | BB 内部診断ラベルに `bb_index` を含めるか |
| `--show-pink-id` / `--no-show-pink-id` | bool | True | BB 内部診断ラベルに `pink_id` を含めるか |
| `--show-pink-ratio` / `--no-show-pink-ratio` | bool | True | BB 内部診断ラベルに `pink_ratio` を含めるか |
| `--show-iou-with-prev` / `--no-show-iou-with-prev` | bool | True | BB 内部診断ラベルに `iou_with_prev` を含めるか |
| `--show-selection-score` / `--no-show-selection-score` | bool | True | BB 内部診断ラベルに `selection_score` を含めるか |

出力ファイル名: `vis_{id_type}_{mode}_{video_stem}.mp4`

診断ラベル形式: `idx=2 pid=1 r=0.421 iou=0.823 s=0.463`（BB 内部、左上から `(+4, +16)` のオフセットに描画。値が `null` のフィールドは `iou=null` のように文字列表示。キー欠損フィールドはラベルから省略）。

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

## convert_pink_to_blue_video.py

**Frozen（feat-044、2026-04-30）**: 凍結中。現状コードはピンク服と肌が HSV 空間で重なる問題（investigation.md イテレーション 1 で確定）により、ピンク服がほぼ変換されず肌が誤変換される不具合あり。既存ツール（ffmpeg / DaVinci Resolve / G'MIC 等）への方針転換のため独自実装は中断。再開時は `docs/issues/feat-044-convert-pink-to-blue-video/` を参照のこと。以下は凍結時点の仕様。

入力動画の HSV 空間でピンク領域を低彩度の青に置換した合成動画を出力する。NDA により本物の青患者動画が入手不可のため、青色対応パイプライン（feat-045 以降）の検証用合成データを生成する。L2 変換: `H -> target_h`、`S -> min(S × s_scale, s_max)`、V 不変。HSV 範囲は `postprocess_pink_id.py` の `FIXED_HSV_RANGES` と同期した定数固定。feat-044 で追加。

```bash
# 既定パラメータ（target-h=110, s-scale=0.35, s-max=80）
uv run python scripts/convert_pink_to_blue_video.py \
  --input testdata/camSony1_S.mp4 \
  --out-dir experiments/results/feat044_test
# 出力: experiments/results/feat044_test/camSony1_S_blue.mp4

# パラメータ調整例（暗め照明寄り）
uv run python scripts/convert_pink_to_blue_video.py \
  --input testdata/camSony1_S.mp4 \
  --out-dir experiments/results/feat044_test \
  --s-scale 0.3 --s-max 60
```

| 引数 | 型 | デフォルト | 説明 |
|------|-----|-----------|------|
| `--input` | str | (必須) | 入力動画ファイル |
| `--out-dir` | str | `output` | 出力ディレクトリ |
| `--target-h` | int | `110` | 置換後 H 値、値域 `[0, 179]` |
| `--s-scale` | float | `0.35` | S 圧縮係数、値域 `[0.0, 1.0]` |
| `--s-max` | int | `80` | S 上限値、値域 `[0, 255]` |

出力ファイル名: `{入力ファイル拡張子なし名}_blue.mp4`。値域外引数は argparse のメッセージ + exit code 2 で終了。

## compare_roi_modes.py

feat-046 で導入した `postprocess_pink_id.py --roi-mode {bb,keypoint-rect}` の 2 モード出力を比較し、散布図 PNG と不一致 CSV を生成する（feat-047、feat-048 で診断列を拡張）。

```bash
uv run python scripts/compare_roi_modes.py \
  --bb-json-dir experiments/results/camSony1_S_pink_json_bb \
  --kp-json-dir experiments/results/camSony1_S_pink_json_kp \
  --out-dir experiments/results/camSony1_S_roi_compare
```

| 引数 | 型 | デフォルト | 説明 |
|------|----|-----------|------|
| `--bb-json-dir` | str | (必須) | bb モード JSON ディレクトリ |
| `--kp-json-dir` | str | (必須) | keypoint-rect モード JSON ディレクトリ |
| `--out-dir` | str | (必須) | `alpha1_scatter.png` / `disagreement.csv` の出力先 |

出力:
- `alpha1_scatter.png`: 同一フレームの `pink_ratio` を bb vs keypoint-rect で比較した散布図。`both_none` フレームは除外。
- `disagreement.csv`: `pink_id=1` 選択が不一致なフレームの一覧。**11 列**（`both_none` は含めない）。
  - 既存 8 列: `frame_idx`, `disagreement_type`, `bb_selected_bb_index`, `bb_pink_ratio`, `bb_bbox`, `kp_selected_bb_index`, `kp_pink_ratio`, `kp_bbox`
  - feat-048 追加 3 列: `kp_roi_bbox`（keypoint-rect モード ROI 矩形）、`bb_kpts_torso` / `kp_kpts_torso`（HALPE26 胴体 4 点の `[[x,y,conf]×4]` JSON 文字列、`ast.literal_eval` でパース可能）

## visualize_disagreement_frames.py

bb モード JSON ディレクトリと keypoint-rect モード JSON ディレクトリを **直接読み込み**、不一致フレーム（pink_id=1 の選択が両モード間で異なるフレーム）について 1 枚の PNG を出力する（feat-048 v2 で CSV 経路を廃止し JSON 直読みに刷新）。

```bash
uv run python scripts/visualize_disagreement_frames.py \
  --bb-json-dir experiments/results/camSony1_S_pink_json_bb \
  --kp-json-dir experiments/results/camSony1_S_pink_json_kp \
  --video testdata/camSony1_S.mp4 \
  --out-dir experiments/results/camSony1_S_disagree \
  --all
```

### 描画内容

- **人物 BB**: bb モード選択 = 赤枠、keypoint-rect モード選択 = 青枠（いずれも線幅 2）
- **idx ラベル**: 各 BB の **右上角外側**（画像端なら内側に折り返し）に BB と同色で `idx=N`
- **keypoint-rect ROI 矩形**: 黄色 (BGR=(0,255,255))、線幅 2。bb 選択人物の kp-rect ROI（kp モード JSON 内の同一 `bb_index` person から取得）と kp 選択人物の kp-rect ROI を描画、同一座標は dedup
- **HALPE26 胴体 4 点**（5=LShoulder, 6=RShoulder, 11=LHip, 12=RHip）:
  - bb 選択人物 = 暗赤、kp 選択人物 = 暗青
  - 高信頼（conf ≥ `--kpt-conf-min`）= 塗りつぶし円（半径 6）、低信頼 = × マーク
  - 各点に 2 文字ラベル `LS` / `RS` / `LH` / `RH` を併記
  - 信頼度テキスト `0.XX` は `--show-kpt-conf` で ON/OFF
- **上部診断ラベル**: 黒縁取り + 白文字で 1〜3 行
  - `Frame: NNNNNN | Type: <both_selected_different/only_bb/only_kp>`
  - `bb: idx=N ratio=0.XXX kp-rect ROI: <ok/fail_kpt/fail_area/not_present> [x1,y1,x2,y2 or ->]`
  - `kp: idx=N ratio=0.XXX kp-rect ROI: ...`

ROI 状態は visualize 内で `build_keypoint_rect_roi` を再呼び出して判定（`--kpt-conf-min` / `--min-roi-area` は kp モード JSON 生成時の `postprocess_pink_id.py` 実行時と同値を渡すこと）。

### 引数

| 引数 | 型 | デフォルト | 説明 |
|------|----|-----------|------|
| `--bb-json-dir` | str | (必須) | bb モード JSON ディレクトリ |
| `--kp-json-dir` | str | (必須) | keypoint-rect モード JSON ディレクトリ |
| `--video` | str | (必須) | 元動画ファイル |
| `--out-dir` | str | (必須) | PNG 出力先ディレクトリ |
| `--max-samples` | int | `50` | サンプル数上限（`>=1`、0/負値は exit code 2）。`--all` 時は無視 |
| `--all` | flag | False | 全件出力（`--max-samples` を無視） |
| `--show-kpt-conf` / `--no-show-kpt-conf` | flag | True | 胴体 4 点の信頼度テキストを描画するか |
| `--kpt-conf-min` | float | `0.3` | ROI 状態再計算の信頼度閾値（値域 `[0.0, 1.0]`、kp JSON 生成時と同値） |
| `--min-roi-area` | int | `200` | ROI 状態再計算の最低面積（値域 `>=1`、kp JSON 生成時と同値） |

出力ファイル名: `frame_{NNNNNN}_disagree.png`（フレーム番号 6 桁ゼロ埋め）。シーク失敗フレームはスキップ + 標準エラーに警告。サマリで disagreement_type ごとのカウント、成功 PNG 数、シーク失敗数を表示。

**注**: feat-047 / feat-048 初版で使っていた `--csv` 引数は廃止された。CSV 経路では only_bb ケース（不一致の大半）で kp ROI 情報が描画できないという設計不備があり、v2 で JSON 直読みに刷新した。`compare_roi_modes.py` の CSV / 散布図出力は別目的（将来用）として残置されているが、本スクリプトとは独立して動作する。

## extract_score_range_frames.py

kp モード JSON ディレクトリと動画を入力に、各フレームの最大 `selection_score`（= `pink_ratio + 0.05 × iou_with_prev`）が指定範囲 `[score-min, score-max]`（両端含む）にあるフレームを抽出し、対象 person の BB / ROI / 胴体 4 点 / 診断ラベルを描画した PNG を出力する（feat-051、`--min-pink-ratio` 閾値検討用）。

```bash
uv run python scripts/extract_score_range_frames.py \
  --json-dir experiments/results/camSony1_L_pink_json_kp \
  --video experiments/input/camSony1_L.mp4 \
  --out-dir experiments/results/camSony1_L_score_010_020 \
  --score-min 0.10 --score-max 0.20
```

### 描画内容（feat-048 と同色系で統一）

- **人物 BB**: 対象 person の `bbox` を青枠（線幅 2）で描画
- **keypoint-rect ROI**: `build_attempted_roi` で再計算した試行 ROI。`ok`=黄、`fail_area`=オレンジ、`fail_kpt`=描画なし
- **HALPE26 胴体 4 点**: 暗青、高信頼=塗りつぶし円・低信頼=× マーク、LS/RS/LH/RH ラベル + 信頼度テキスト（`--show-kpt-conf` で ON/OFF）
- **BB 上部**: `pink_id:{value} score:{bbox_score:.2f}`（キー欠損 ⇒ 省略、値 None ⇒ `null` 文字列）
- **BB 内部診断ラベル**: `idx={N} pid={N} r={0.XXX} iou={0.XXX or null} s={0.XXX or null}`
- **上部診断ラベル**: `Frame: NNNNNN  effective_s: 0.XXX (range: [min, max])` と `kp-rect ROI: <status>`（フォールバック発動時は `(s fallback: r used as s)` 注記）

### フォールバック規約（feat-041 由来の `selection_score=None` 対応）

`selection_score` が JSON で None（連続性切れ復帰直後など）の場合、本ツール内でローカルに `pink_ratio` を有効 s として代替。1 フレーム内で複数 person がある場合は **有効 s の最大値**を持つ person のみ描画。

### 引数

| 引数 | 型 | デフォルト | 説明 |
|------|----|-----------|------|
| `--json-dir` | str | (必須) | kp モード JSON ディレクトリ |
| `--video` | str | (必須) | 元動画 |
| `--out-dir` | str | (必須) | PNG 出力先 |
| `--score-min` | float | (必須) | 有効 s 下限（`[0.0, 1.05]`、含む） |
| `--score-max` | float | (必須) | 有効 s 上限（`[0.0, 1.05]`、含む。`==` 許容） |
| `--kpt-conf-min` | float | `0.3` | ROI 状態再計算用閾値（kp JSON 生成時と同値を渡すこと） |
| `--min-roi-area` | int | `200` | ROI 状態再計算用最低面積（同上） |
| `--show-kpt-conf` / `--no-show-kpt-conf` | flag | True | キーポイント信頼度テキスト表示 |

出力ファイル名: `frame_{NNNNNN}_s{0.XXX}.png`。サマリで scanned / extracted / fallback / success / seek_fail / output dir を表示（シーク失敗 0 件でも常に表示）。
