# feat-028: JSONにトラッキングID記録 要求仕様書

## 1.1 プロジェクト概要

### 何を作るのか
既存のHALPE 26 OpenPose JSONと動画ファイルを入力とし、Deep OC-SORT + カスタムRe-IDを実行して、各人物にstable_idを付与した新しいJSONファイルを出力するポストプロセススクリプト。

### なぜ作るのか
現在のパイプライン（`run_halpe26_pipeline.py`）はキーポイントとBB情報のみをJSONに出力し、トラッキングIDを記録していない。feat-026（見切れ再同定の検証）で、stable_idごとのスケルトン可視化には per-frame の stable_id → キーポイント対応がJSONに保存されている必要があることが判明した。

### 誰が使うのか
ViTPose パイプラインの開発・検証を行う研究者（ユーザー自身）。CLIスクリプトとして使用する。

### どこで使うのか
GPU搭載ワークステーション（NVIDIA RTX 5060 Ti, Ubuntu Linux）。Python 3.10.16, uv管理環境。

---

## 1.2 用語定義

| 用語 | 定義 |
|------|------|
| track_id | Deep OC-SORTが各フレームで割り当てるID。見切れ復帰後は新しいIDが付与される |
| stable_id | カスタムRe-IDが維持する安定ID。見切れ後も同一人物には同じIDを付与する |
| 入力JSON | `run_halpe26_pipeline.py`（または`run_halpe26_pipeline_yolox.py`等）が出力したHALPE 26 OpenPose JSON。`stable_id`フィールドを持たない |
| 出力JSON | 入力JSONの各personに`stable_id`フィールドを追加したJSON |
| ポストプロセス | 2Dキーポイント推定（ViTPose）は行わず、既存JSONと動画のみで処理する方式 |

---

## 1.3 機能要求一覧

### FR-001: stable_id付与ポストプロセススクリプト

- **機能名**: Re-IDポストプロセス
- **概要**: 既存JSONと動画を入力とし、Deep OC-SORT + カスタムRe-IDを実行して、各personにstable_idを付与した新しいJSONを出力する
- **変更対象**: 新規スクリプト `scripts/postprocess_reid.py`
- **入力（CLI引数）**:
  - `--video`: 動画ファイルパス（必須）
  - `--json-dir`: 入力HALPE 26 JSONディレクトリ（必須）
  - `--out-dir`: 出力JSONディレクトリ（必須）。`os.path.realpath()` で正規化した絶対パスが `--json-dir` と一致する場合、エラーメッセージを出力して終了する（上書き防止）。ディレクトリが存在しない場合は自動作成する
  - `--device`: 推論デバイス（デフォルト: `cuda:0`）
- **出力**: `--out-dir` にJSONファイルを出力する。ファイル名は `{video_stem}_{frame_idx:06d}.json`（`video_stem` は動画ファイル名から拡張子を除いたもの、`frame_idx` は動画フレーム番号、0始まり）
- **処理フロー**:
  1. `--json-dir` から全JSONファイルを一括メモリに読み込む（`test_custom_reid_offline.py` の `load_data()` と同等のロジック。`{frame_idx: list[dict]}` 形式。各dictは `{"bbox": list[float], "bbox_score": float, "kpts": np.ndarray(26, 3)}` を持つ。欠番フレームはキーに含まれない。JSONファイルが0件の場合はエラーメッセージを出力して `sys.exit(1)` する。バリデーション: キーポイント数78、bbox/bbox_score存在チェック。失敗時はその人物をスキップしWARNINGを出力）
  2. `cv2.VideoCapture` で動画をオープンする。`cap.isOpened()` が False の場合、エラーメッセージを出力して `sys.exit(1)` する。JSONのフレーム番号（0始まり連番）と動画フレーム番号は一致する前提
  3. Deep OC-SORTトラッカーを初期化する（`w_association_emb=0.0`、`osnet_x0_25_msmt17.pt`。TypeErrorフォールバックあり）
  4. カスタムRe-IDを初期化する（`delay_frames=180`）
  5. 動画の各フレームについて（`cv2.VideoCapture.read()` でフレーム順次取得）:
     a. JSONからそのフレームの人物データを取得する。辞書にキーがないフレーム（欠番）は0人検出として扱う（`json_people = []`）
     b. JSON人物のbboxとbbox_scoreから検出データ配列を構築する（`np.array([x1, y1, x2, y2, bbox_score, 0], dtype=np.float32)`、0人の場合は `np.empty((0, 6), dtype=np.float32)`）
     c. 検出データ配列と動画フレームをDeep OC-SORTに渡してtrack_idを取得する。`tracker.update(dets, frame)` の戻り値は `np.ndarray shape=(N, 5+)` で各行は `[x1, y1, x2, y2, track_id, ...]`。`tracked_bboxes = {int(t[4]): t[:4].tolist() for t in tracks}` で変換する
     d. track_idのbboxとJSON人物のbboxをIoUでマッチングし、キーポイントを対応付ける（カスタムRe-ID用。`test_custom_reid_offline.py` の `match_by_iou()` と同一方向: track_id → JSON人物）
     e. カスタムRe-IDの `update()` を呼び出して `{track_id: stable_id}` を取得する
     f. 各JSON人物にstable_idを割り当てる（FR-002参照。stable_id=-1の人物も含め、全人物データを出力する）
     g. 入力JSONのdictを読み込み、各personに `stable_id` フィールドを追加して出力する（FR-003参照）。0人検出フレームでは `{"version": 1.3, "people": []}` を出力する
  6. 処理完了後、サマリーを出力する（総フレーム数、処理時間、FPS、ユニークstable_id数、出力ディレクトリ）
- **動画とJSONのフレーム数不一致**: 動画フレーム数 > JSONファイル数の場合、JSONが存在しないフレームは0人検出として扱い、空のpeopleでJSONを出力する。動画フレーム数 < JSONファイル数の場合、動画終了時点で処理を終了し、余剰JSONは無視する
- **受け入れ基準**:
  - camSony1_L.mp4で全フレーム処理が完了し、出力JSONファイル数が `cap.read()` 成功回数と一致すること
  - 出力JSONの各personに `stable_id` フィールドが含まれること
  - `--out-dir` と `--json-dir` が同じパス（`os.path.realpath()` で正規化後）の場合、エラーメッセージを出力して終了すること
  - 動画がオープンできない場合、エラーメッセージを出力して終了すること

### FR-002: stable_idとJSON人物の対応付け

- **機能名**: track_id経由のstable_id割り当て
- **概要**: Deep OC-SORTのtrack_idとJSON人物をIoUでマッチングし、stable_idを各人物に割り当てる
- **入力**:
  - `tracked_bboxes`: `{track_id: [x1, y1, x2, y2]}`（Deep OC-SORTの出力）
  - `stable_ids`: `{track_id: stable_id}`（カスタムRe-IDの出力）
  - `json_people`: そのフレームのJSON人物リスト（各dictに `"bbox": [x1, y1, x2, y2]` を持つ、xyxy形式）
- **出力**: 各JSON人物に対応する `stable_id`（int）のリスト。長さは `len(json_people)` と同一。マッチしない人物は `-1`
- **処理**:
  1. 各JSON人物のbboxと全てのtracked_bboxesのIoUを計算する
  2. IoU最大かつ閾値（0.5）以上のtrack_idを割り当てる。IoU最大値が同率の場合はtrack_id最小を優先する
  3. 割り当てられたtrack_idからstable_idsを参照してstable_idを取得する
  4. IoU < 0.5 でマッチしない人物、またはtrack_idにstable_idがない場合は `-1` を割り当てる
- **マッチング方向**: JSON人物 → track_id の方向でマッチングする。理由: JSON出力は人物単位であり、各人物に対してstable_idを割り当てる必要があるため。カスタムRe-IDに渡す `keypoints_map`（track_id → kpts）の構築には別途 `test_custom_reid_offline.py` と同じ track_id → JSON人物 方向の `match_by_iou()` を使用する（FR-001 ステップ5d）
- **BB重複が残存する前提**: 入力JSONのBB重複除去は完璧ではない。同一人物に対して複数のBBが存在する場合がある
  - **Deep OC-SORTへの影響**: 重複BBがdets配列に含まれる場合、Deep OC-SORTが同一人物に複数のtrack_idを割り当てる可能性がある。これはトラッカー側の挙動であり、本スクリプトでは制御しない
  - **stable_id割り当てへの影響**: 複数のJSON人物が同一track_idにIoU最大でマッチした場合、全てに同じstable_idが割り当てられる。同一stable_idが同一フレーム内で複数のJSON人物に付与されることは仕様として許容する（同一人物の重複BBであるため、stable_idが同じであることは意味的に正しい）
  - ハンガリアン法による最適割り当ては行わない
- **受け入れ基準**:
  - 1人の人物が映っているフレームで、stable_id >= 1 が割り当てられること
  - 0人検出フレームでは空のpeopleリストが出力されること
  - Deep OC-SORTが検出しないフレーム（トラッキングロスト中）では、JSON人物のstable_idは `-1` になること

### FR-003: 出力JSONフォーマット

- **機能名**: stable_id付きOpenPose JSON出力
- **概要**: 入力JSONのdictを読み込み、各personに `stable_id` フィールドを直接追加して書き出す。入力JSONの全フィールドをそのまま維持する
- **出力方法**: 入力JSONファイルを `json.load()` で読み込み、`people` リストの各personに `stable_id` キーを追加し、`json.dump()` で出力する。`halpe26_to_openpose_json()` は使用しない（ndarrayへの変換・逆変換が冗長なため）
- **出力JSON構造**:
  ```json
  {
    "version": 1.3,
    "people": [
      {
        "person_id": [-1],
        "pose_keypoints_2d": [x0, y0, c0, ...],
        "bbox_score": 0.988,
        "bbox": [x1, y1, x2, y2],
        "face_keypoints_2d": [],
        "hand_left_keypoints_2d": [],
        "hand_right_keypoints_2d": [],
        "pose_keypoints_3d": [],
        "face_keypoints_3d": [],
        "hand_left_keypoints_3d": [],
        "hand_right_keypoints_3d": [],
        "stable_id": 1
      }
    ]
  }
  ```
- **`stable_id` フィールドの仕様**:
  - 型: int
  - 値: 1以上の正の整数（カスタムRe-IDが発番したstable_id）、またはマッチしない場合は `-1`
  - JSON出力時のキー順序は保証しない（JSONとしてキー順序に意味がないため）
- **`person_id` フィールド**: 従来通り `[-1]` を維持する。変更しない
- **`halpe26_to_openpose_json()` への変更**: 将来のパイプライン統合（feat-027）に備え、`stable_ids: list[int] | None = None` 引数を追加する。`all_halpe26` と同じ長さの `list[int]` を渡すと、各要素が対応するpersonの `stable_id` フィールドに設定される。`stable_ids=None` の場合、`stable_id` フィールドは出力しない（後方互換）。本スクリプト（`postprocess_reid.py`）では使用しない
- **0人検出フレームの出力**: 入力JSONが欠番のフレームでは `{"version": 1.3, "people": []}` を出力する
- **受け入れ基準**:
  - 出力JSONの各personに `stable_id` フィールドが含まれること
  - 入力JSONの既存フィールド（`pose_keypoints_2d`, `bbox`, `bbox_score` 等）が出力JSONでそのまま維持されること
  - `halpe26_to_openpose_json()` に `stable_ids=None` で呼び出した場合、`stable_id` フィールドが出力されないこと（後方互換）
  - 既存の `run_halpe26_pipeline.py` で生成されるJSONフォーマットが変わらないこと

### FR-004: 進捗表示

- **機能名**: 長尺動画向け進捗ログ
- **概要**: 321Kフレーム処理中に適切な間隔で進捗を出力する
- **出力（標準出力）**: 3000フレームごとに以下を出力:
  `Processing frame {frame_idx:06d}/{total_frames} ({pct:.1f}%)`
  - `total_frames` が0以下の場合: `Processing frame {frame_idx:06d}/?`
- **受け入れ基準**:
  - 321Kフレームの処理中、約107行の進捗ログが出力されること
  - 処理完了後にサマリー（総フレーム数、処理時間、FPS、ユニークstable_id数、出力ディレクトリ）が出力されること

---

## 1.4 非機能要求

- **処理速度**: 321Kフレームの処理が完了すること。下限FPSは設けない。`test_custom_reid_offline.py` と同等の処理速度（約190 fps）を期待する
- **メモリ使用量**: 321Kフレームの処理中にメモリ不足で異常終了しないこと。JSON読み込みは `test_custom_reid_offline.py` の `load_data()` と同様に全フレーム分を一括でメモリに読み込む方式とする。321Kフレーム×平均1人で約213MB、複数人フレームを考慮しても500MB以下で問題ない。JSON書き出しは1フレームずつ行う
- **対応環境**: Ubuntu Linux、Python 3.10.16、uv管理環境、NVIDIA RTX 5060 Ti
- **信頼性**: 321,239フレームの全処理で途中クラッシュなし

---

## 1.5 制約条件

- 新規ライブラリの追加は禁止（既存環境のOpenCV、NumPy、BoxMOTのみ使用）
- `halpe26_to_openpose.py` への変更は `stable_ids` オプション引数の追加のみ（将来のパイプライン統合用）。既存の関数シグネチャの後方互換を維持する。本スクリプトでは使用しない
- `custom_reid.py` への変更なし
- `test_custom_reid_offline.py` からのコード流用: `load_data()`, `compute_iou()`, `match_by_iou()` 相当のロジックを `postprocess_reid.py` 内にコピーして独立実装する。共通ユーティリティへの切り出しは本案件のスコープ外
- Deep OC-SORTの初期化パラメータは `test_custom_reid_offline.py` と同一（`w_association_emb=0.0`, `max_age=30`, TypeErrorフォールバック）
- テストデータ:
  - 動画: `experiments/input/camSony1_L.mp4`（321,239フレーム、30fps）
  - 入力JSON: `experiments/results/camSony1_L_json/`（321,239ファイル）
  - 実行例: `uv run python scripts/postprocess_reid.py --video experiments/input/camSony1_L.mp4 --json-dir experiments/results/camSony1_L_json/ --out-dir experiments/results/camSony1_L_reid_json/`

---

## 1.6 優先順位

| ID | 機能名 | MoSCoW |
|----|--------|--------|
| FR-001 | stable_id付与ポストプロセススクリプト | Must |
| FR-002 | stable_idとJSON人物の対応付け | Must |
| FR-003 | 出力JSONフォーマット | Must |
| FR-004 | 進捗表示 | Must |

**MVP**: FR-001〜FR-004 すべて
