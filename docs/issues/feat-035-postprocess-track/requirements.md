# feat-035: postprocess_track.py 実装（Deep OC-SORT 単独、track_id 付与） — 要求仕様書

## 1. プロジェクト概要

### 1.1 何を作るのか

`scripts/postprocess_track.py`（新規）を作成する。本スクリプトは、`run_halpe26_pipeline_yolo11.py` が出力した HALPE 26 OpenPose JSON ディレクトリと元動画を入力とし、各フレームの各人物 BB に対して BoxMOT の Deep OC-SORT が付与する `track_id` を、**入力 JSON 辞書の既存フィールドを一切変更せずに**追加した新しい JSON ディレクトリを出力する。

### 1.2 なぜ作るのか

feat-034 ロードマップで確定した 4 ステージトラッキングパイプラインの Stage 2 に該当する。Stage 2 では、Deep OC-SORT を「単独で」実行して生の `track_id` を JSON に付与する純粋なポストプロセスを提供する。Stage 3（`postprocess_pink_id.py`、feat-033）および Stage 4（`postprocess_pink_track_id.py`、feat-036）はこの Stage 2 の出力に依存する。既存の `postprocess_reid.py`（feat-028）は `custom_reid.py` による `stable_id` 付与も含む複合処理だが、feat-034 ロードマップでは `custom_reid.py` 系の Re-ID ロジックを**一切使わない**方針のため、本案件ではシンプル版として切り出す。

### 1.3 誰が使うのか

本プロジェクトの開発者。生成された `track_id` 付与 JSON を Stage 3 の入力として用いるほか、feat-036 の `pink_track_id` 算出ロジック開発で対象 track_id 候補として参照する。

### 1.4 どこで使うのか

Linux 開発マシン（本プロジェクトの既存 ViTPose uv 環境、NVIDIA RTX 5060 Ti）。コマンドラインから実行する。ViTPose/MMPose のキーポイント推定は行わず、既存の動画と既存 JSON のみで動作する。

## 2. 用語定義

本ドキュメント、機能設計書、実装コード内で同じ用語を用いる。

| 用語 | 定義 |
|------|------|
| track_id | BoxMOT Deep OC-SORT が各フレームで割り当てる正の整数の識別子。見切れ復帰後は新しい ID が付与されることがある（Re-ID 補正は行わない） |
| HALPE 26 JSON | `run_halpe26_pipeline_yolo11.py` が出力する OpenPose 互換 JSON。`version`, `people[*].person_id`, `pose_keypoints_2d`, `bbox_score`, `bbox` 等を含む |
| 入力 JSON | 本スクリプトが読み込む HALPE 26 JSON（1 フレーム 1 ファイル、命名 `{video_stem}_{frame_idx:06d}.json`） |
| 出力 JSON | 入力 JSON の各 `people` エントリに `track_id` フィールドを追加したもの。既存フィールドは変更しない |
| 生 dict 保持設計 | 入力 JSON を `json.load()` で辞書として読み込み、既存フィールドを削除・変換せず、`track_id` キーを追加するだけで出力する方式。feat-033 `postprocess_pink_id.py` で採用 |
| 有効人物 | 1 フレーム内の JSON `people` 要素のうち、`bbox: [x1, y1, x2, y2]`（4 要素の数値リスト）と `bbox_score: float` がいずれも存在し型正常な人物 |
| 無効人物 | 有効人物以外の `people` 要素（`bbox` または `bbox_score` が欠損または型不正）。Deep OC-SORT には渡さず、`track_id = -1` を割り当てる |
| valid_indices | 1 フレーム内の `people` 配列における有効人物のインデックスリスト。`dets` 配列の行順と 1:1 で対応する |
| 検出（det） | 1 フレーム内の 1 つの有効人物 BB。`[x1, y1, x2, y2, bbox_score, class=0]` の 6 列配列として Deep OC-SORT に渡す |
| tracked_bboxes | Deep OC-SORT の `update()` 戻り値から構築する辞書。`{int(track_id): [x1, y1, x2, y2]}` 形式 |
| 生 track_id | 本スクリプトが出力する `track_id`。Deep OC-SORT がその場で発番した ID をそのまま使う。`stable_id` のような Re-ID 補正は一切加えない |

## 3. 機能要求一覧

### FR-001: 入力 JSON 読み込み（生 dict 保持）

- **概要**: `--json-dir` 配下の全 JSON ファイルを読み込み、`{frame_idx: (filename, content_dict)}` の辞書として保持する純関数を実装する
- **入力**:
  - `json_dir`: str、JSON ディレクトリパス
- **出力**:
  - `frame_to_json`: `dict[int, tuple[str, dict]]`
    - キー: フレーム番号（ファイル名末尾 `_(\d{6})\.json$` を正規表現抽出した 6 桁番号を int 化）
    - 値: `(filename, content_dict)` のタプル。`content_dict` は `json.load()` で読み込んだ生の辞書（フィールド抽出・変換・バリデーションは一切行わない）
- **処理内容**:
  1. `json_dir` 配下の `*.json` をソートして列挙する
  2. ファイル名末尾が `_(\d{6})\.json$`（末尾アンカー付き）にマッチしないファイルはスキップする
  3. 各 JSON を `json.load()` で読み込み、辞書としてそのまま保持する
  4. `json.JSONDecodeError` が発生した場合は `WARNING: Failed to parse {filename}, treating as empty` を出力し、`content_dict = {"version": 1.3, "people": []}` として `frame_to_json` に登録する
  5. JSON ファイルが 1 件もない場合は `ERROR: No JSON files found in {json_dir}` を出力して `sys.exit(1)` する
  6. 同一フレーム番号 `(\d{6})` にマッチする複数のファイルが存在する場合（例: `foo_000005.json` と `bar_000005.json` が同一ディレクトリに存在）、`sorted` 順で後から読まれたものが `frame_to_json[5]` に保持される（辞書の上書き挙動）。通常 `run_halpe26_pipeline_yolo11.py` の出力ディレクトリでは発生しない境界ケース
- **受け入れ基準**:
  - AC-001-1: 読み込み結果の dict のキー数は、命名規約 `_(\d{6})\.json$` に合致し、かつフレーム番号が重複しないファイルの数と一致する
  - AC-001-2: 各値の `content_dict` は `json.load()` が返すのと同一の辞書オブジェクトである（`people[*]` 内の任意のフィールド、`stable_id`/`pink_id` を含む、を保持する）
  - AC-001-3: JSON デコードに失敗したファイルは WARNING を出し、`{"version": 1.3, "people": []}` という空 people 辞書として `frame_to_json` に登録される（その後 FR-005 の通常フローで出力される）
  - AC-001-4: JSON ファイル 0 件の場合は ERROR を出し終了コード 1 で終了する
  - AC-001-5: 同一フレーム番号にマッチするファイルが複数存在する場合、`sorted` 順で最後に処理されたもののみが辞書に保持される（上書き挙動。通常は発生しない境界ケース）

### FR-002: Deep OC-SORT 初期化

- **概要**: BoxMOT の `DeepOcSort` を初期化する純関数を実装する
- **入力**:
  - `device`: str、PyTorch デバイス文字列（例: `cuda:0`, `cpu`）
- **出力**:
  - `DeepOcSort` インスタンス
- **処理内容**:
  1. Re-ID 重みパスを `Path(__file__).resolve().parent.parent / "osnet_x0_25_msmt17.pt"` で解決する（`scripts/postprocess_track.py` の親ディレクトリ直下 = リポジトリルート）
  2. `DeepOcSort(reid_weights=<path>, device=device, half="cuda" in device, max_age=30, w_association_emb=0.0)` で初期化する
  3. `TypeError`（`w_association_emb` 未対応の BoxMOT バージョン）が発生した場合は `WARNING: w_association_emb not supported, falling back without it` を出し、`w_association_emb` を省略してフォールバック初期化する
- **受け入れ基準**:
  - AC-002-1: 正常パスで `DeepOcSort` インスタンスが返り、`None` ではない
  - AC-002-2: `TypeError` フォールバック時は上記 WARNING ログが出力される
  - AC-002-3: `osnet_x0_25_msmt17.pt` が存在しない場合、BoxMOT 側が raise する例外（`FileNotFoundError` 等）を本スクリプトでは捕捉せずそのまま伝播させ、Python のデフォルト終了コード 1 で終了する

### FR-003: 検出データ配列構築（有効人物抽出）

- **概要**: 1 フレーム分の JSON 人物リストから、有効人物のみを抽出して Deep OC-SORT 入力用の numpy 配列を構築し、合わせて有効人物の元インデックスリストを返す純関数を実装する
- **入力**:
  - `people`: list[dict]、1 フレーム分の JSON `people` 配列
  - `frame_idx`: int、WARNING ログに含めるフレーム番号（検査除外メッセージ用）
- **出力**:
  - `dets`: numpy.ndarray、shape=(M, 6)、dtype=float32、各行 `[x1, y1, x2, y2, bbox_score, 0.0]`（M は有効人物数、0 を含む）
  - `valid_indices`: list[int]、長さ M、各要素は `dets[i]` に対応する元 `people` 配列のインデックス
- **処理内容**:
  1. `people` が空リストなら `(np.empty((0, 6), dtype=np.float32), [])` を返す
  2. 各人物について以下を検査する:
     - `bbox` キーが存在し、長さ 4 の数値リスト/タプルであること
     - `bbox_score` キーが存在し、数値（int/float）であること
  3. 検査を通過した人物のみから `[bbox[0], bbox[1], bbox[2], bbox[3], bbox_score, 0.0]` を構築し、float32 配列にスタックする。元 `people` のインデックスを `valid_indices` に追加する
  4. 検査で除外された人物（無効人物）は `WARNING: Invalid bbox/bbox_score in frame {frame_idx} person {i}, excluding from tracking` を出力する
- **受け入れ基準**:
  - AC-003-1: 3 人全員が有効人物の場合、`dets.shape == (3, 6)` かつ `valid_indices == [0, 1, 2]` が返る
  - AC-003-2: 空リスト入力に対して `(shape=(0, 6), [])` が返る
  - AC-003-3: 3 人のうち中間の 1 人（インデックス 1）が `bbox` 欠損の場合、`dets.shape == (2, 6)` かつ `valid_indices == [0, 2]` が返る
  - AC-003-4: 戻り値 `dets` の各行 5 列目は `bbox_score`、6 列目は常に 0.0（単一クラス）である
  - AC-003-5: 無効人物検出時に WARNING ログが出力される

### FR-004: track_id の JSON 人物への割り当て（IoU マッチング）

- **概要**: Deep OC-SORT 戻り値から構築した `tracked_bboxes` 辞書と JSON `people` 配列、`valid_indices` を入力として、各 `people` 要素に対応する `track_id` を IoU マッチングで決定する純関数を実装する
- **入力**:
  - `people`: list[dict]、1 フレーム分の JSON `people` 配列
  - `valid_indices`: list[int]、FR-003 が返した有効人物インデックス
  - `tracked_bboxes`: `dict[int, list[float]]`、キーが `track_id`、値が `[x1, y1, x2, y2]`
  - `iou_threshold`: float、デフォルト 0.5
- **出力**:
  - `track_ids`: list[int]、長さ `len(people)`。無効人物・IoU 閾値未満・IoU=0・マッチなしはすべて `-1`
- **処理内容**:
  1. `result = [-1] * len(people)` で初期化する
  2. `tracked_bboxes` が空辞書なら `result` をそのまま返す
  3. `valid_indices` 内の各インデックス `i` について以下を実行する:
     a. `best_iou = 0.0`、`best_tid = None` で初期化する
     b. `tracked_bboxes` の各エントリ `(tid, trk_bbox)` について `person = people[i]` の `bbox` と `trk_bbox` の IoU を計算する
     c. `iou > best_iou` の場合、`best_iou` と `best_tid` を**両方**更新する（`best_iou := iou`, `best_tid := tid`）
     d. `iou == best_iou` かつ `best_tid is not None` かつ `tid < best_tid` の場合、`best_tid` のみを更新する（`best_iou` は不変）。これは「同値タイブレークで最小 `track_id` を優先する」の実装
     e. 全 `(tid, trk_bbox)` のループ終了後、`best_iou >= iou_threshold` かつ `best_tid is not None` なら `result[i] = best_tid`、それ以外は `result[i] = -1` のまま
  4. `result` を返す
- **受け入れ基準**:
  - AC-004-1: `tracked_bboxes` が空辞書のとき、戻り値の全要素が `-1` になる
  - AC-004-2: 1 つだけ bbox が完全一致する track_id が存在する有効人物には、その track_id が割り当てられる
  - AC-004-3: IoU 最大値が `iou_threshold` 未満の場合は `-1` が割り当てられる
  - AC-004-4: 全 track との IoU が 0 の有効人物（空間的に全く重ならない）は `-1` が割り当てられる（`best_iou = 0.0` 初期値からの比較 `iou > best_iou` により、0 同値は最大値として採用されないため）
  - AC-004-5: 2 つの track の IoU が完全同値（例: 両者 0.8、共に閾値以上）の場合、`track_id` が小さい方が採用される
  - AC-004-6: 無効人物（`valid_indices` に含まれない）は `-1` が割り当てられる
  - AC-004-7: 本マッチングは貪欲 IoU 最大方式であり、ハンガリアン法等の最適割り当ては行わない。同一 `track_id` が 1 フレーム内で複数の有効人物に割り当てられることは仕様として許容する（BB 重複除去が完全でない入力を想定）

### FR-005: ポストプロセス本体

- **概要**: FR-001 〜 FR-004 を組み合わせ、動画の全フレームについて `track_id` を付与した出力 JSON を生成するメインロジックを実装する
- **入力**:
  - 入力動画ファイル（MP4）
  - 入力 JSON ディレクトリ
  - 出力 JSON ディレクトリ
  - デバイス文字列
- **処理内容**:
  1. 出力ディレクトリと入力ディレクトリが同一パス（`os.path.realpath` 比較）なら `ERROR: --out-dir must differ from --json-dir to prevent overwriting` を出し終了コード 1 で終了する
  2. 出力ディレクトリを `os.makedirs(..., exist_ok=True)` で作成する
  3. FR-001 で入力 JSON を読み込む（`frame_to_json`）
  4. `cv2.VideoCapture` で動画をオープンする。`cap.isOpened()` が False なら `ERROR: Cannot open video {args.video}` を出して終了コード 1 で終了する
  5. FR-002 で Deep OC-SORT を初期化する（`tracker`）
  6. `frame_idx = 0` から開始し、`cap.read()` で動画フレームを順次取得する（`ret == False` でループ終了）
  7. 各フレームで以下を実行する:
     - `entry = frame_to_json.get(frame_idx)` で対応エントリを取得する
     - **入力 JSON がないフレーム（`entry is None`）の場合**:
       - 時間同期のため `tracker.update(np.empty((0, 6), dtype=np.float32), frame)` を呼び出し内部状態のみ更新する
       - 出力 JSON は書き出さない（AC-005-2）
       - `frame_idx += 1` して次フレームへ
     - **入力 JSON がある場合**:
       - `filename, content_dict = entry`
       - `people = content_dict.get("people", [])`
       - FR-003 で `dets, valid_indices = build_dets(people, frame_idx)` を構築する（`frame_idx` は WARNING ログ用）
       - `tracks = tracker.update(dets, frame)` を呼ぶ。戻り値は numpy 配列 shape=(N, 5 以上)、インデックス 4 が `track_id`、インデックス 0〜3 が bbox
       - `tracked_bboxes = {int(t[4]): t[:4].tolist() for t in tracks}`（戻り値が空配列の場合は空辞書）
       - FR-004 で `assigned_track_ids = assign_track_ids(people, valid_indices, tracked_bboxes)` を計算する
       - `people` の各要素に `person["track_id"] = assigned_track_ids[i]` を書き込む
       - `os.path.join(out_dir, filename)` に `json.dump(content_dict, f)` で書き出す
       - `frame_idx += 1`
  8. ループ終了後、`cap.release()` を呼ぶ
- **重要な設計判断（生 dict 保持、feat-033 ADR-001 踏襲）**:
  - `content_dict` の既存フィールドは一切変更しない。`people[*]` への新キー追加のみ許可する
  - 入力 JSON に `stable_id`, `pink_id` 等が含まれる場合、そのまま出力 JSON に保持される
  - 出力時のキー順序は保証しない
- **受け入れ基準**:
  - AC-005-1: 指定した動画・入力 JSON ディレクトリに対してエラーなく処理完了し、終了コード 0 で終わる
  - AC-005-2: 出力ディレクトリに生成される JSON ファイルは、動画フレーム走査中に `frame_to_json` にキーが存在したフレーム分だけ出力される（`entry is None` のフレームは出力しない）
  - AC-005-3: 出力 JSON の各 `people[*]` に `track_id: int` フィールドが追加されている
  - AC-005-4: 入力 JSON の既存フィールド（`version`, `people[*].person_id`, `pose_keypoints_2d`, `bbox_score`, `bbox`, およびその他任意のフィールド `stable_id`/`pink_id` を含む）は出力 JSON で**変更されない**
  - AC-005-5: 1 フレーム内の `people` が空配列の場合、空配列のまま `{"version": 1.3, "people": []}` が出力される（`track_id` 追加対象なし）
  - AC-005-6: Deep OC-SORT の `update()` が空配列を返したフレームの全有効人物は `track_id = -1` になる
  - AC-005-7: `--out-dir` と `--json-dir` が同一（realpath 比較）の場合、ERROR ログを出して終了コード 1 で終了する
  - AC-005-8: 動画オープン失敗時は ERROR ログを出して終了コード 1 で終了する
  - AC-005-9: 入力 JSON がないフレームでも `tracker.update()` が空 dets で呼ばれ、tracker 内部の時間カウントが正しく進む

### FR-006: CLI インタフェース

- **概要**: FR-005 を実行するコマンドラインインタフェースを提供する
- **コマンド**: `uv run python scripts/postprocess_track.py [引数]`
- **引数**:

  | 引数 | 必須 | 型 | デフォルト | 意味 |
  |------|------|----|-----------|------|
  | `--video` | 必須 | パス | - | 入力動画ファイル |
  | `--json-dir` | 必須 | パス | - | 入力 HALPE 26 JSON ディレクトリ |
  | `--out-dir` | 必須 | パス | - | 出力 JSON ディレクトリ（`--json-dir` と同一パス禁止） |
  | `--device` | 任意 | str | `cuda:0` | BoxMOT デバイス |

- **受け入れ基準**:
  - AC-006-1: 必須引数が未指定の場合、argparse のエラーメッセージを表示して終了コード 2 で終了する
  - AC-006-2: 出力ディレクトリが存在しない場合、自動作成する
  - AC-006-3: `--device` 未指定時は `cuda:0` が使用される
  - AC-006-4: `--device` に不正な文字列（例: `foo`）が渡された場合、BoxMOT/PyTorch 側が raise する例外（`RuntimeError` 等）を本スクリプトでは捕捉せずそのまま伝播させる

### FR-007: 進捗表示・サマリ出力

- **概要**: 長尺動画向けに進捗ログを出力し、処理完了時にサマリを表示する
- **出力(標準出力)**:
  - 進捗: `frame_idx % 3000 == 0` を満たすフレーム（すなわち `frame_idx = 0, 3000, 6000, ...`）で以下を出力する:
    - `total_frames > 0` の場合: `Processing frame {frame_idx:06d}/{total_frames} ({pct:.1f}%)`
    - `total_frames <= 0` の場合: `Processing frame {frame_idx:06d}/?`
  - サマリ（処理終了時）:
    - `Total frames: <int>`（`cap.read()` が `ret=True` を返した回数 = ループ終了時点の `frame_idx` 値。`entry is None`（入力 JSON なし）のフレームも含み、動画が途中で破損・読み取り失敗した場合はその時点までに読めた分までをカウントする）
    - `Unique track IDs: <int>`（出力 JSON に登場した `track_id >= 1` のユニーク数）
    - `Processing time: <float> sec (<float> fps)`
    - `Output directory: <str>`
- **受け入れ基準**:
  - AC-007-1: 321,239 フレーム処理時、`frame_idx = 0, 3000, 6000, ..., 321000` の計 108 行（`frame_idx = 0` を含む）の進捗ログが出力される
  - AC-007-2: 処理完了後、上記 4 行のサマリが出力される
  - AC-007-3: `Unique track IDs` は `track_id >= 1` の人物のみをカウントする（`-1` は除外）

## 4. 非機能要求

### NFR-001: パフォーマンス

- 目標: camSony1_L.mp4（321,239 フレーム、30 fps）の処理が途中クラッシュせず完了する
- 下限 FPS は設けない。feat-028 `postprocess_reid.py` の実測値（約 190 fps）と同等以上を期待するが保証しない
- 検証段階: camSony1_S.mp4（900 フレーム）→ camSony1_L.mp4（321K フレーム）の順で実行する

### NFR-002: 対応環境

- OS: Linux（Ubuntu）
- Python: 3.10.16
- パッケージ管理: uv（`uv run python` 経由で実行）
- GPU: NVIDIA RTX 5060 Ti（CUDA 12.8）。`--device cpu` も引数上は受け付けるが本案件では実測・チューニング対象外

### NFR-003: 信頼性

- 321K フレーム全処理で途中クラッシュなし
- JSON デコード失敗フレームは WARNING を出して空 people として処理継続
- 動画読み取りが途中で失敗した時点で処理を終了する（途中終了でも出力済み JSON は保持する）

### NFR-004: メモリ使用量

- 入力 JSON は全フレーム分を一括メモリ読み込みする（`frame_to_json` 辞書）
- **検証基準**: camSony1_L（321,239 フレーム）の処理中、OOM（Out Of Memory）で異常終了せず最後まで完了すること。常駐メモリ使用量（RSS）は 500 MB 以下を目標値とするが、超過した場合でも OOM に至らず完走すれば手動テストを通過とする（超過時の改修は別案件で扱う）
- JSON 書き出しは 1 フレームずつ行い、出力バッファを蓄積しない

## 5. 制約条件

### 5.1 使用必須のライブラリ

- BoxMOT（`DeepOcSort`）
- OpenCV（動画読み込み）
- numpy（配列演算）
- argparse, json, os, re, sys, time, pathlib（標準ライブラリ）

### 5.2 使用禁止

- `scripts/custom_reid.py`（Re-ID ロジック一切使用禁止、feat-034 ロードマップで確定）
- ハンガリアン法 / `scipy.optimize` による最適割り当て（貪欲 IoU マッチングのみ）

### 5.3 変更禁止

- `scripts/run_halpe26_pipeline_yolo11.py`
- `scripts/postprocess_reid.py`
- `scripts/postprocess_pink_id.py`
- `scripts/custom_reid.py`
- `scripts/visualize_tracking.py`
- 既存 JSON 出力フォーマット（`track_id` フィールドを追加するのみ）

### 5.4 データ制約

- 入力 JSON は `scripts/run_halpe26_pipeline_yolo11.py`（または互換スクリプト）の出力形式に準拠する
- 各人物は `bbox = [x1, y1, x2, y2]`（ピクセル、xyxy 形式、float）を持つ前提。欠損時は無効人物として扱う
- 入力 JSON に `stable_id` / `pink_id` 等が含まれる場合はそのまま保持する（参照・変更なし）

### 5.5 Deep OC-SORT パラメータ

feat-028 `postprocess_reid.py` と同一の初期化を用いる:

```python
DeepOcSort(
    reid_weights=<scripts の親ディレクトリ>/osnet_x0_25_msmt17.pt,
    device=<args.device>,
    half="cuda" in <args.device>,
    max_age=30,
    w_association_emb=0.0,
)
```

`TypeError` が発生した場合は `w_association_emb` を省略してフォールバックする。その他のパラメータはチューニング対象外とする。

## 6. 優先順位

### 6.1 MoSCoW

| ID | 機能 | 優先度 |
|----|------|--------|
| FR-001 | 入力 JSON 読み込み（生 dict 保持） | Must |
| FR-002 | Deep OC-SORT 初期化 | Must |
| FR-003 | 検出データ配列構築（有効人物抽出） | Must |
| FR-004 | track_id の JSON 人物への割り当て（IoU マッチング） | Must |
| FR-005 | ポストプロセス本体 | Must |
| FR-006 | CLI インタフェース | Must |
| FR-007 | 進捗表示・サマリ出力 | Should |

### 6.2 Won't（本案件のスコープ外）

- `custom_reid.py` を使った Re-ID 処理
- `stable_id` の付与・更新
- `pink_id` の計算（Stage 3 で実装済み）
- `pink_track_id` の算出（feat-036）
- Deep OC-SORT のパラメータチューニング
- 可視化スクリプトの作成・修正
- `halpe26_to_openpose.py` への変更（feat-028 では追加したが、本案件では不要）

### 6.3 MVP

- FR-001 〜 FR-006 が動作し、camSony1_S.mp4（900 フレーム）に対して `track_id` 付与 JSON が生成できる状態を最小実行可能プロダクトとする
- FR-007（進捗表示・サマリ出力）は Should。実装コストが低いため本案件内で一括実装する
