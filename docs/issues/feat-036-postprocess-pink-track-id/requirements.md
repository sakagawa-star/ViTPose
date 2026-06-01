# feat-036: postprocess_patient_id.py 実装（pink_id + track_id ハイブリッド対象追跡） — 要求仕様書

## 1. プロジェクト概要

### 1.1 何を作るのか

`scripts/postprocess_patient_id.py`（新規）を作成する。本スクリプトは、feat-035 で `track_id` が、feat-033 で `pink_id` がそれぞれ付与済みの HALPE 26 OpenPose JSON ディレクトリを入力とし、各フレームの各人物 BB に対して「対象かどうか」を示す `pink_track_id: int` フィールドを、**入力 JSON 辞書の既存フィールドを一切変更せずに**追加した新しい JSON ディレクトリを出力する。

### 1.2 なぜ作るのか

feat-034 ロードマップで確定した 4 ステージトラッキングパイプラインの Stage 4 に該当する。`pink_id` は「その 1 フレームで色的に対象らしい BB」を示すが時間方向の一貫性がなく、`track_id` は「時間方向に一貫した ID」を示すが対象の区別はしない。両者を結合することで「時間一貫かつ対象判定された ID」を提供する。これは室内動画で対象ポーズを自動抽出するための最終的な ID 系列となる。

### 1.3 誰が使うのか

本プロジェクトの開発者。生成された `pink_track_id` 付与 JSON を下流（可視化・ポーズ解析・Pose2Sim 連携等）で「対象のみ」のフィルタリングに利用する。

### 1.4 どこで使うのか

Linux 開発マシン（本プロジェクトの既存 ViTPose uv 環境、NVIDIA RTX 5060 Ti）。コマンドラインから実行する。動画ファイルは参照せず（既に JSON に必要情報が全て入っているため）、純粋な JSON 変換ポストプロセスとして動作する。

### 1.5 機能の振る舞い（ユーザー視点での要求）

`pink_id` を**種**、`track_id` を**拡張手段**とする階層構造に基づき、各 BB の `pink_track_id` は以下のユーザー観察可能な振る舞いで決定されなければならない。本節は「何を達成したいか」を記述する WHAT レベルの要求であり、§4 の FR-001〜FR-007 はこれを 2 パス方式で実装する HOW レベルの手順として位置づけられる。

#### 要求 A: 種による直接判定

BB が有効な `pink_id=1` を持つ場合（重複除外後）、その BB は対象であり `pink_track_id=1` を受ける。`pink_id=1` は色ベースで対象を直接判定する情報源であり、これ自体が対象シグナルとなる。この判定は `track_id` の値や有無に依存しない。

#### 要求 B: `track_id` による時間方向への継続（過去・未来の両方向）

BB が `pink_id=1` を持たない場合でも、その BB の `track_id` が**動画のいずれかのフレーム**（現在より過去・未来いずれも可）で有効な `pink_id=1` BB に紐づいていれば、その BB は対象であり `pink_track_id=1` を受ける。これは「同じ `track_id` は同じ人物」という Deep OC-SORT の連続性を対象ラベルの拡張手段として利用する動作である。

この要求には以下の具体的な動作が含まれる:

- **継続ケース**: 対象の `track_id` が `T` で、過去フレーム `f1` で `pink_id=1` が観測された後、現在フレーム `f2` で同じ `track_id=T` だが `pink_id` が `1` ではなくなった（例: 服の色が一時的に見えなくなった）場合、その BB の `pink_track_id` は `1` のまま変化しない。`track_id=T` が過去に `pink_id=1` と紐づいた情報を既に保持しており、対象と認識するのに十分だからである
- **前方遡及ケース**: 対象の `track_id` が `T` で、将来のフレーム `f3` で初めて `pink_id=1` が観測された場合、それ以前（`f3` より前）の同じ `track_id=T` の全 BB も遡って `pink_track_id=1` を受ける
- **両方向の全区間参照**: 本機能はオンライン追跡（現在フレームまでの情報のみで決定する処理）ではなく、動画の**全区間を参照するオフライン処理**として動作する。過去フレームも未来フレームも同等に参照される

#### 要求 C: 重複除外

1 フレーム内に `pink_id=1` BB が複数存在する場合（BB 重複問題）、`bbox_score` が最大の 1 件のみを有効な `pink_id=1` BB として採用し、それ以外は重複 BB として `pink_track_id=-2` を受ける。重複 BB は:

- 要求 A（種による直接判定）の対象から除外される
- 要求 B（`track_id` 経由の継続）の**基点としても除外される**（重複 BB の `track_id` は対象 `track_id` 集合に追加されない）

`bbox_score` 同値時は `people` 配列のインデックスが小さい方を有効とする。

#### 要求 E: フレーム内 `pink_track_id=1` のデデュプ（単一対象保証）

要求 A〜B の判定結果として、同一フレーム内で複数の BB が `pink_track_id=1` を受ける場合がある（例: 一方は種による直接判定、他方は `track_id` 拡張による判定）。この場合、`bbox_score` が最も高い BB のみ `pink_track_id=1` を維持し、他の `pink_track_id=1` BB は `pink_track_id=-2`（重複）に降格する。

これにより、各フレームで `pink_track_id=1` は**最大 1 つ**に保証される。同値タイブレークはインデックスが小さい方を優先する。

背景: 個室の室内動画で対象は 1 名のみであるため、同一フレームに `pink_track_id=1` が複数あるのは YOLO が同一人物に対して複数 BB を検出した結果（重複 BB 問題）である。`bbox_score` が高い BB がより信頼できる検出結果であるため、それを優先する。

#### 要求 D: 非対象

要求 A〜C、E のいずれにも該当しない BB は `pink_track_id=-1` を受ける。これには以下が含まれる:

- `pink_id` が `1` ではなく、かつ `track_id` がいずれの有効 `pink_id=1` BB とも紐づかない BB
- `track_id` が欠損または `-1`（Deep OC-SORT マッチなし）で、かつ `pink_id` も `1` ではない BB
- 動画全体で `pink_id=1` が一度も観測されなかった場合の全 BB

## 2. 用語定義

本ドキュメント、機能設計書、実装コード内で同じ用語を用いる。

| 用語 | 定義 |
|------|------|
| `pink_id` | feat-033 `postprocess_pink_id.py` が各 BB に付与する `int` フィールド。`1`=そのフレームで色的に対象と判定、`-1`=それ以外。1 フレーム内に `1` は最大 1 件が通常だが、BB 重複問題により複数発生しうる |
| `track_id` | feat-035 `postprocess_track.py` が各 BB に付与する `int` フィールド。Deep OC-SORT の発番 ID。`-1`=マッチなし、`>=1`=有効 track_id |
| `pink_track_id` | 本スクリプトが各 BB に付与する `int` フィールド。値域は `{1, -1, -2}`（後述「3. 値域」参照）。既存 `pink_id` / `track_id` は変更せず新規追加する |
| HALPE 26 JSON | `run_halpe26_pipeline_yolo11.py` が出力する OpenPose 互換 JSON。`version`, `people[*].person_id`, `pose_keypoints_2d`, `bbox_score`, `bbox` 等を含む |
| 入力 JSON | 本スクリプトが読み込む HALPE 26 JSON。`pink_id`（feat-033 付与）と `track_id`（feat-035 付与）の**両方**を各 `people` 要素に含むこと |
| 出力 JSON | 入力 JSON の各 `people` エントリに `pink_track_id` フィールドを追加したもの。既存フィールドは一切変更しない |
| 生 dict 保持設計 | 入力 JSON を `json.load()` で辞書として読み込み、既存フィールドを削除・変換せず、`pink_track_id` キーを追加するだけで出力する方式。feat-033 `postprocess_pink_id.py` / feat-035 `postprocess_track.py` で採用 |
| 有効 `pink_id=1` BB | 1 フレーム内で `pink_id=1` を持つ BB のうち、`bbox_score` が最大の 1 件。タイブレークは person_idx 昇順（小さい方を有効） |
| 重複 `pink_id=1` BB | 1 フレーム内に `pink_id=1` が 2 件以上あった場合の「有効」以外の BB。BB 重複問題（YOLO が同一人物を複数検出）を想定 |
| patient_track_ids | 動画全体で「有効 `pink_id=1` BB」の `track_id` を集めた集合（`set[int]`）。パス 1 で構築し、パス 2 で参照する。重複 `pink_id=1` BB（§1.5 要求 C）の `track_id` は集合に追加しない。`track_id` が `-1`（無効）/ 欠損 / 非数値の BB も追加しない |
| 有効 track_id | `track_id >= 1` を満たす整数。`-1` は無効とみなす |
| パス 1 | 全入力 JSON を走査して `patient_track_ids` と各フレームの重複 BB 情報を構築するフェーズ |
| パス 2 | パス 1 の結果を用いて各 BB に `pink_track_id` を付与し、出力 JSON を書き出すフェーズ |

## 3. 値域

`pink_track_id` フィールドの値域:

| 値 | 意味 |
|----|------|
| `1` | 対象（有効 `pink_id=1` BB 本人、または `track_id` が `patient_track_ids` に含まれる BB） |
| `-1` | 非対象（対象と判定されなかった全ての BB） |
| `-2` | 重複 BB。以下の 2 ケースで付与される: (1) 同一フレームに複数の `pink_id=1` が存在し、`bbox_score` が最大でない側（要求 C）、(2) 要求 A〜B の判定後に同一フレームで複数 BB が `pink_track_id=1` となった場合、`bbox_score` が最大でない側（要求 E）。下流のトラッキング対象外として扱う |

## 4. 機能要求一覧

### 4.0 要求 A〜D と FR の対応マッピング

§1.5 で定義したユーザー視点の要求（WHAT）と、以下の FR（HOW）の対応関係を明示する。実装者およびレビュアーは本マッピングを通じて、WHAT ↔ HOW のトレーサビリティを確認できる。

| §1.5 要求 | 実装 FR | 対応する階層/処理 |
|----------|---------|------------------|
| 要求 A（種による直接判定） | FR-002（`valid_pink_idx` を特定）+ FR-004 階層 2（`i == valid_pink_idx` → `1`） | `pink_id=1` BB を `track_id` の値に関わらず直接対象判定 |
| 要求 B（全区間参照による `track_id` 経由の継続、過去・未来両方向） | FR-001（全 JSON メモリ読み込み）+ FR-003（全区間走査で `patient_track_ids` を構築）+ FR-004 階層 3（`track_id in patient_track_ids` → `1`） | パス 1 で全区間の情報を集合に集約し、パス 2 で各フレームが任意の他フレームの観測情報にアクセスするのと等価な動作を実現 |
| 要求 C（重複除外、拡張の基点としても除外） | FR-002（`bbox_score` 最大を有効、他を `duplicate_person_idxs` に分類、有効 BB の `track_id` のみ `valid_track_id` として返す）+ FR-003（`valid_track_id` のみ集合追加）+ FR-004 階層 1（`duplicate` → `-2`） | 重複 BB は対象判定対象からも拡張基点からも除外される |
| 要求 E（フレーム内 `pink_track_id=1` のデデュプ） | FR-004 ステップ C（後処理デデュプ）+ FR-007（`-2` カウント集計で自動反映） | 要求 A〜B 判定後に同一フレーム内で複数 `pink_track_id=1` → `bbox_score` 最大のみ維持、他を `-2` に降格 |
| 要求 D（非対象） | FR-004 初期値 `-1` + 階層 4（非該当時） | 要求 A〜E のいずれにも該当しない BB を `-1` に確定 |

### FR-001: 入力 JSON 読み込み（生 dict 保持）

- **概要**: `--json-dir` 配下の全 JSON ファイルを読み込み、`{frame_idx: (filename, content_dict)}` の辞書として保持する純関数を実装する
- **入力**:
  - `json_dir`: str、JSON ディレクトリパス
- **出力**:
  - `frame_to_json`: `dict[int, tuple[str, dict]]`
    - キー: フレーム番号（ファイル名末尾 `_(\d{6})\.json$` を正規表現抽出した 6 桁番号を int 化）
    - 値: `(filename, content_dict)` のタプル。`content_dict` は `json.load()` で読み込んだ生の辞書
- **処理内容**:
  1. `json_dir` 配下の `*.json` をソートして列挙する
  2. ファイル名末尾が `_(\d{6})\.json$`（末尾アンカー付き）にマッチしないファイルはスキップする
  3. 各 JSON を `json.load()` で読み込み、辞書としてそのまま保持する
  4. `json.JSONDecodeError` が発生した場合は `WARNING: Failed to parse {filename}, treating as empty` を出力し、`content_dict = {"version": 1.3, "people": []}` として `frame_to_json` に登録する
  5. JSON ファイルが 1 件もない場合は `ERROR: No JSON files found in {json_dir}` を出力して `sys.exit(1)` する
  6. 同一フレーム番号にマッチするファイルが複数存在する場合、`sorted` 順で最後に処理されたものが保持される（辞書上書き挙動、通常は発生しない境界ケース）
- **受け入れ基準**:
  - AC-001-1: 読み込み結果のキー数は、命名規約に合致しかつフレーム番号が重複しないファイルの数と一致する
  - AC-001-2: 各値の `content_dict` は `json.load()` が返すのと同一の辞書オブジェクトであり、`people[*]` 内の任意フィールド（`pink_id`, `track_id`, `stable_id` 等）を保持する
  - AC-001-3: JSON デコード失敗は WARNING を出し、空 people 辞書として登録される
  - AC-001-4: JSON ファイル 0 件の場合は ERROR を出し終了コード 1 で終了する
  - AC-001-5: 同一フレーム番号の重複ファイルは `sorted` 順で最後のものが保持される

### FR-002: パス 1 - 有効 `pink_id=1` BB の選択と重複 BB 特定（フレーム単位）

- **概要**: 1 フレーム分の `people` 配列から、`pink_id=1` を持つ BB を収集し、`bbox_score` 最大を「有効」として選び、他を「重複」として特定する純関数を実装する
- **入力**:
  - `people`: list[dict]、1 フレーム分の JSON `people` 配列
  - `frame_idx`: int、WARNING ログに含めるフレーム番号
- **出力**:
  - `valid_pink_idx`: `int | None`、有効 `pink_id=1` BB の `people` 内インデックス（該当なしなら `None`）
  - `valid_track_id`: `int | None`、有効 BB の `track_id`（該当なし、または `track_id` が欠損/無効/`<= 0` の場合は `None`）
  - `duplicate_person_idxs`: `set[int]`、重複 `pink_id=1` BB の `people` 内インデックス集合
- **処理内容**:
  1. `people` 内の各要素 `(i, person)` について、`person.get("pink_id") == 1` を満たす要素を候補として収集する
  2. 候補が 0 件なら `(None, None, set())` を返す
  3. 候補ごとに `bbox_score` を検査する。`bbox_score` が欠損または非数値の場合は `WARNING: Invalid bbox_score in frame {frame_idx} person {i} with pink_id=1, treating as score=-inf` を出力し、その候補のスコアを `-inf` とみなす（実質的に選ばれない）
  4. 候補の中から `bbox_score` 最大のものを 1 件選ぶ。同値タイブレークはインデックスが小さい方を採用する
  5. 選ばれた候補の `people` 内インデックスを `valid_pink_idx` とする
  6. 選ばれた候補の `track_id` を取得する:
     - `track_id` キーが欠損、または数値でない、または `<= 0`（`-1` 含む）の場合は `valid_track_id = None`
     - それ以外は `valid_track_id = int(track_id)`
  7. 候補のうち `valid_pink_idx` 以外の全インデックスを `duplicate_person_idxs` に入れる
- **受け入れ基準**:
  - AC-002-1: `pink_id=1` が 0 件のフレームでは `(None, None, set())` が返る
  - AC-002-2: `pink_id=1` が 1 件で `track_id=5` のフレームでは `(そのidx, 5, set())` が返る
  - AC-002-3: `pink_id=1` が 2 件で `bbox_score` が `0.9, 0.7` のフレームでは `0.9` 側が有効、`0.7` 側が重複として返る
  - AC-002-4: `pink_id=1` が 2 件で `bbox_score` が同値の場合、インデックスの小さい方が有効になる
  - AC-002-5: 有効 BB の `track_id=-1`（無効）の場合、`valid_track_id=None` が返る（`valid_pink_idx` と `duplicate_person_idxs` は通常通り）
  - AC-002-6: 有効 BB の `track_id` キーが欠損している場合、`valid_track_id=None` が返る
  - AC-002-7: `pink_id=1` 候補の `bbox_score` が欠損している場合、WARNING を出し、その候補はスコア `-inf` として選択対象から除外する（他に正常な候補があればそれが選ばれ、全候補が `-inf` なら AC-002-4 の規則で最小インデックスが選ばれる）。全候補が `-inf` の場合でも、`pink_id=1` は色ベース判定で対象シグナルが既に出ている以上、BB の採用を優先する方針。`bbox_score` の信頼性低下は WARNING ログで検知可能であり、仕様として受容する
  - AC-002-8: `pink_id=1` が 3 件で `bbox_score` がそれぞれ `0.9, 欠損, 0.7` の場合、`0.9` 側のインデックスが `valid_pink_idx` となり、残り 2 件（`-inf` 扱いの欠損側と `0.7` 側）は `duplicate_person_idxs` に入る

### FR-003: パス 1 - 全フレーム走査と `patient_track_ids` 集合構築

- **概要**: `frame_to_json` の全エントリに対して FR-002 を適用し、動画全体での `patient_track_ids` 集合と、各フレームの重複情報を構築する関数を実装する
- **入力**:
  - `frame_to_json`: `dict[int, tuple[str, dict]]`、FR-001 の戻り値
- **出力**:
  - `patient_track_ids`: `set[int]`、有効 `pink_id=1` BB の `track_id` を集めた集合（`None` は含めない）
  - `frame_classification`: `dict[int, tuple[int | None, set[int]]]`、キーはフレーム番号、値は `(valid_pink_idx, duplicate_person_idxs)`
- **処理内容**:
  1. `patient_track_ids = set()` と `frame_classification = {}` を初期化する
  2. `frame_to_json` の各エントリ `(frame_idx, (filename, content_dict))` について（`sorted(frame_to_json.keys())` で昇順走査する）:
     - `people = content_dict.get("people", [])`
     - FR-002 を呼び出して `(valid_pink_idx, valid_track_id, duplicate_person_idxs)` を取得する
     - `valid_track_id is not None` なら `patient_track_ids.add(valid_track_id)` する
     - `frame_classification[frame_idx] = (valid_pink_idx, duplicate_person_idxs)` として記録する
     - `frame_idx % 3000 == 0` を満たすとき、`Pass 1 processing frame {frame_idx:06d}` を標準出力に出力する（FR-007 と連動）
  3. `(patient_track_ids, frame_classification)` を返す
- **受け入れ基準**:
  - AC-003-1: 動画全体で `pink_id=1` が一度も発生しない場合、`patient_track_ids` は空集合になる
  - AC-003-2: 動画中で有効 `pink_id=1` BB の `track_id` が `[5, 5, 5, 8, 8]` だった場合、`patient_track_ids = {5, 8}`
  - AC-003-3: 有効 `pink_id=1` BB の `track_id` が全て `-1` だった場合、`patient_track_ids` は空集合になる
  - AC-003-4: `frame_classification` のキーは `frame_to_json` の全キーと一致し、`pink_id=1` が 1 件もないフレーム（空 people フレームを含む）の値は `(None, set())` である
  - AC-003-5: 各フレームの重複情報が正しく反映される（FR-002 の挙動に準じる）
  - AC-003-6: パス 1 走査中、`frame_idx % 3000 == 0` を満たすとき `Pass 1 processing frame {frame_idx:06d}` が標準出力に出力される
  - AC-003-7: 1 フレーム内に `pink_id=1` が 2 件あり、有効側の `track_id=5`、重複側の `track_id=8` の場合、`patient_track_ids = {5}` となり `8` は追加されない（§1.5 要求 C「重複 BB は拡張の基点としても除外される」の直接検証）
  - AC-003-8: 重複 `pink_id=1` BB のみ（すなわち、有効 BB の `track_id` が無効 `-1` で、重複 BB の `track_id=7` のような場合）でも、重複 BB の `track_id=7` は `patient_track_ids` に追加されない

### FR-004: パス 2 - `pink_track_id` の JSON 人物への割り当て

- **概要**: 1 フレーム分の `people` 配列、そのフレームの分類情報、`patient_track_ids` を入力として、各人物の `pink_track_id` を決定する純関数を実装する
- **入力**:
  - `people`: list[dict]、1 フレーム分の JSON `people` 配列
  - `valid_pink_idx`: `int | None`、FR-002 が返した有効 `pink_id=1` BB のインデックス
  - `duplicate_person_idxs`: `set[int]`、FR-002 が返した重複 BB インデックス集合
  - `patient_track_ids`: `set[int]`、FR-003 が返した対象 track_id 集合
- **出力**:
  - `pink_track_ids`: list[int]、長さ `len(people)`
- **判定の階層構造**:

  `pink_id` は色ベースで対象を直接判定する**種**、`track_id` はそれを時間方向に伝播させる**拡張手段**である。従って、判定は以下の 4 段階で行う（上から順に適用し、先にマッチした時点で確定する）:

  1. **重複除外**: `i in duplicate_person_idxs` → `result[i] = -2`（重複 BB は種にも拡張にもならない）
  2. **種（`pink_id=1` 直接判定）**: `i == valid_pink_idx` → `result[i] = 1`
  3. **拡張（`track_id` による伝播）**: `people[i].get("track_id")` が数値型かつ `>= 1` かつ `patient_track_ids` に含まれる → `result[i] = 1`
  4. **非対象**: 上記いずれにも該当しない → `result[i] = -1`（初期値のまま）

- **処理内容**（ステップ A〜D。階層構造 1〜4 と番号帯を分離する）:
  - **ステップ A**: `result = [-1] * len(people)` で初期化する
  - **ステップ B**: 各インデックス `i` について上記の階層 1〜4 の順に判定する
  - **ステップ C**: **後処理デデュプ（要求 E）**: `result` 内で `pink_track_id=1` が 2 つ以上あるかチェックする。2 つ以上ある場合、`bbox_score` が最大の BB のみ `1` を維持し、他の `1` は `-2` に降格する。同値タイブレークはインデックスが小さい方を優先する。`bbox_score` が欠損/非数値の場合は `-inf` として扱い、正常なスコアより後回しにする
  - **ステップ D**: `result` を返す
- **受け入れ基準**:
  - AC-004-1: 重複 BB インデックスには `-2` が割り当てられる
  - AC-004-2: 有効 `pink_id=1` BB インデックスには `1` が割り当てられる（種による直接判定）
  - AC-004-3: 重複でも有効 `pink_id=1` でもないが `track_id` が `patient_track_ids` に含まれる BB には `1` が割り当てられる（拡張による伝播）
  - AC-004-4: 重複でも有効 `pink_id=1` でもなく、`track_id` が `patient_track_ids` に含まれない BB には `-1` が割り当てられる
  - AC-004-5: `track_id = -1` の BB は、有効 `pink_id=1` でない限り `-1` が割り当てられる
  - AC-004-6: `track_id` キーが欠損している BB は、有効 `pink_id=1` でない限り `-1` が割り当てられる
  - AC-004-7: 有効 `pink_id=1` BB は種として直接判定されるため、`track_id` の値や有無に関わらず常に `pink_track_id=1` となる（種が拡張より優先される階層構造の帰結）
  - AC-004-8: 重複 BB 判定は種・拡張のいずれよりも優先される（同一 BB が「重複」と「有効」を同時に満たすことはないため順序依存は発生しないが、階層の最上位として明記）
  - AC-004-9: 階層判定後に `pink_track_id=1` が 2 つある場合（例: person 0 が `track_id` 拡張で `1`、person 1 が `pink_id=1` 種で `1`）、`bbox_score` が高い方のみ `1` を維持し、他方は `-2` に降格する（要求 E）
  - AC-004-10: 階層判定後に `pink_track_id=1` が 3 つある場合、`bbox_score` 最大の 1 つのみ `1` を維持し、残り 2 つは `-2` に降格する
  - AC-004-11: `pink_track_id=1` が 1 つ以下のフレームでは後処理デデュプは発火しない（`pink_track_id` は階層判定の結果のまま）
  - AC-004-12: 後処理デデュプで `bbox_score` が同値の場合、インデックスが小さい方を `1` として維持する
  - AC-004-13: 後処理デデュプで `bbox_score` が欠損/非数値の BB は `-inf` として扱われ、正常スコアの BB より後回しにされる。なお、デデュプ時の `bbox_score` 欠損では WARNING を出さない（FR-002 の `_score_for_selection` で既に WARNING が出力済みのため、重複ログを避ける）

### FR-005: ポストプロセス本体

- **概要**: FR-001 〜 FR-004 を組み合わせ、2 パス走査で `pink_track_id` を付与した出力 JSON を生成するメインロジックを実装する
- **入力**:
  - 入力 JSON ディレクトリ
  - 出力 JSON ディレクトリ
- **処理内容**:
  1. 出力ディレクトリと入力ディレクトリが同一パス（`os.path.realpath` 比較）なら `ERROR: --out-dir must differ from --json-dir to prevent overwriting` を出し終了コード 1 で終了する
  2. 出力ディレクトリを `os.makedirs(..., exist_ok=True)` で作成する
  3. FR-001 で入力 JSON を全件読み込む（`frame_to_json`）
  4. **パス 1**: FR-003 で `(patient_track_ids, frame_classification)` を構築する
  5. **パス 2**: `frame_to_json` の各エントリ `(frame_idx, (filename, content_dict))` について:
     - `people = content_dict.get("people", [])`
     - `(valid_pink_idx, duplicate_person_idxs) = frame_classification[frame_idx]`
     - FR-004 で `assigned = assign_pink_track_ids(people, valid_pink_idx, duplicate_person_idxs, patient_track_ids)` を計算する
     - `people` の各要素に `person["pink_track_id"] = assigned[i]` を書き込む
     - `os.path.join(out_dir, filename)` に `json.dump(content_dict, f)` で書き出す
- **重要な設計判断（生 dict 保持、feat-033 ADR-001 踏襲）**:
  - `content_dict` の既存フィールドは一切変更しない。`people[*]` への新キー `pink_track_id` 追加のみ許可する
  - 入力 JSON に `stable_id`, `pink_id`, `track_id` 等が含まれる場合、そのまま出力 JSON に保持される
  - 出力時のキー順序は保証しない
- **受け入れ基準**:
  - AC-005-1: 指定した入力 JSON ディレクトリに対してエラーなく処理完了し、終了コード 0 で終わる
  - AC-005-2: 出力ディレクトリに生成される JSON ファイルは、`frame_to_json` に読み込まれた全フレーム分（命名規約に合致したファイル分）出力される
  - AC-005-3: 出力 JSON の各 `people[*]` に `pink_track_id: int` フィールドが追加されている
  - AC-005-4: 入力 JSON の既存フィールド（`version`, `people[*].person_id`, `pose_keypoints_2d`, `bbox_score`, `bbox`, `pink_id`, `track_id`, およびその他任意のフィールド `stable_id` を含む）は出力 JSON で**変更されない**
  - AC-005-5: 1 フレーム内の `people` が空配列の場合、空配列のまま出力される（`pink_track_id` 追加対象なし）
  - AC-005-6: `--out-dir` と `--json-dir` が同一（realpath 比較）の場合、ERROR ログを出して終了コード 1 で終了する
  - AC-005-7: 動画全体で `pink_id=1` が一度も観測されなかった場合、全 BB の `pink_track_id` が `-1` になる（重複も発生しないため `-2` も出ない）

### FR-006: CLI インタフェース

- **概要**: FR-005 を実行するコマンドラインインタフェースを提供する
- **コマンド**: `uv run python scripts/postprocess_patient_id.py [引数]`
- **引数**:

  | 引数 | 必須 | 型 | デフォルト | 意味 |
  |------|------|----|-----------|------|
  | `--json-dir` | 必須 | パス | - | 入力 HALPE 26 JSON ディレクトリ（`pink_id` / `track_id` 付与済み） |
  | `--out-dir` | 必須 | パス | - | 出力 JSON ディレクトリ（`--json-dir` と同一パス禁止） |

- **備考**: `--video` 引数は提供しない。本スクリプトは画素参照を行わず、JSON のみを入出力する
- **受け入れ基準**:
  - AC-006-1: 必須引数が未指定の場合、argparse のエラーメッセージを表示して終了コード 2 で終了する
  - AC-006-2: 出力ディレクトリが存在しない場合、自動作成する
  - AC-006-3: `--json-dir` と `--out-dir` が同一の場合、AC-005-6 の通り ERROR で終了する

### FR-007: 進捗表示・サマリ出力

- **概要**: 長尺動画向けに進捗ログを出力し、処理完了時にサマリを表示する
- **出力（標準出力）**:
  - パス 1 開始時: `Pass 1: Scanning frames to build patient_track_ids...`
  - パス 1 進捗: `frame_idx % 3000 == 0` を満たすフレーム（`frame_idx = 0, 3000, 6000, ...`）で `Pass 1 processing frame {frame_idx:06d}` を出力する
  - パス 1 終了時: `Pass 1 done: patient_track_ids = {N} unique track_ids` （`N` は集合サイズ）
  - パス 2 開始時: `Pass 2: Assigning pink_track_id...`
  - パス 2 進捗: 同様に `frame_idx % 3000 == 0` で `Pass 2 processing frame {frame_idx:06d}` を出力する
  - サマリ（処理終了時）:
    - `Total frames: <int>`（`frame_to_json` のエントリ数 = FR-001 が読み込んだファイル数）
    - `Unique patient track_ids: <int>`（`len(patient_track_ids)`）
    - `Frames with pink_track_id=1 (patient): <int>`（出力 JSON のどこかに `pink_track_id=1` を含むフレーム数）
    - `Frames with pink_track_id=-2 (duplicate): <int>`（出力 JSON のどこかに `pink_track_id=-2` を含むフレーム数）
    - `Processing time: <float> sec (<float> fps)`（fps = Total frames / Processing time）
    - `Output directory: <str>`
- **受け入れ基準**:
  - AC-007-1: パス 1 とパス 2 の進捗ログがそれぞれ 3000 フレーム間隔で出力される（`Pass 1 processing frame {frame_idx:06d}` / `Pass 2 processing frame {frame_idx:06d}`）
  - AC-007-2: 処理完了後、上記 6 行のサマリが出力される
  - AC-007-3: `Unique patient track_ids` は `patient_track_ids` 集合のサイズを正確に反映する
  - AC-007-4: `Frames with pink_track_id=1 (patient)` は、出力 JSON の各フレームにおいて少なくとも 1 つの BB が `pink_track_id=1` を持つフレームの総数（**フレーム単位カウント**、BB 単位ではない）
  - AC-007-5: `Frames with pink_track_id=-2 (duplicate)` は、出力 JSON の各フレームにおいて少なくとも 1 つの BB が `pink_track_id=-2` を持つフレームの総数（**フレーム単位カウント**、BB 単位ではない）

## 5. 非機能要求

### NFR-001: パフォーマンス

- 目標: camSony1_L.mp4（321,239 フレーム）相当の入力 JSON に対して途中クラッシュせず完了する
- 下限目安: feat-035（約 191 fps）を明確に上回ること。本案件は画素参照と Deep OC-SORT 推論がなく、純粋な辞書走査と JSON I/O のみとなるため、1000 fps 以上を期待する。下回った場合は I/O ボトルネック（`json.dump` 書き出し）を調査する
- 検証段階: camSony1_S 相当（900 フレーム）→ camSony1_L 相当（321K フレーム）の順で実行する

### NFR-002: 対応環境

- OS: Linux（Ubuntu）
- Python: 3.10.16
- パッケージ管理: uv（`uv run python` 経由で実行）
- GPU: 本スクリプトは画素処理・推論を行わないため GPU 不要

### NFR-003: 信頼性

- 321K フレーム全処理で途中クラッシュなし
- JSON デコード失敗フレームは WARNING を出して空 people として処理継続
- `pink_id` / `track_id` / `bbox_score` が欠損している BB に対しては WARNING を出して安全側にフォールバック（FR-002/004 の受け入れ基準参照）

### NFR-004: メモリ使用量

- 入力 JSON は全フレーム分を一括メモリ読み込みする（`frame_to_json` 辞書）
- パス 1 とパス 2 で同じ `frame_to_json` を共有する（2 回ロードしない）
- パス 2 はインプレースで `content_dict` に `pink_track_id` を書き込むため、追加メモリは小さい
- **検証基準**: camSony1_L 相当（321,239 フレーム分の JSON）の処理中、OOM（Out Of Memory）で異常終了せず最後まで完了すること。feat-035 実績（2〜3 GB 見積もり、OOM 回避確認済み）と同等の挙動を期待する。500 MB は目標値ではなく、OOM 回避が必須条件

## 6. 制約条件

### 6.1 使用必須のライブラリ

- 標準ライブラリのみ（`argparse`, `json`, `os`, `re`, `sys`, `time`, `pathlib`, `math`）

### 6.2 使用禁止

- OpenCV（動画不要、画素参照なし）
- BoxMOT / Deep OC-SORT（トラッキングは feat-035 で完了済み、本案件では参照のみ）
- numpy（純粋な辞書走査のみで十分）
- `scripts/custom_reid.py`（feat-034 ロードマップで Re-ID ロジック排除）

### 6.3 変更禁止

- `scripts/run_halpe26_pipeline_yolo11.py`
- `scripts/postprocess_reid.py`
- `scripts/postprocess_pink_id.py`
- `scripts/postprocess_track.py`
- `scripts/custom_reid.py`
- `scripts/visualize_tracking.py`
- 既存 JSON 出力フォーマット（`pink_track_id` フィールドを追加するのみ）

### 6.4 データ制約

- 入力 JSON は feat-035 `postprocess_track.py` の出力形式に準拠し、各 `people` 要素に `track_id`, `pink_id`, `bbox_score` を含むこと
- 入力 JSON に `stable_id` 等が含まれる場合はそのまま保持する（参照・変更なし）

### 6.5 単一対象前提

- 個室のため対象は 1 名のみ。複数対象（同時に異なる服装で 2 人以上）は非対応
- `patient_track_ids` は集合なので複数要素を持ちうるが、それは「同一対象が Deep OC-SORT 上で複数の track_id に分裂した」ケースを想定しており、全て同一対象として `pink_track_id=1` にまとめる

## 7. 優先順位

### 7.1 MoSCoW

| ID | 機能 | 優先度 |
|----|------|--------|
| FR-001 | 入力 JSON 読み込み（生 dict 保持） | Must |
| FR-002 | パス 1 フレーム単位の有効/重複 BB 特定 | Must |
| FR-003 | パス 1 全フレーム走査と `patient_track_ids` 集合構築 | Must |
| FR-004 | パス 2 `pink_track_id` 割り当て | Must |
| FR-005 | ポストプロセス本体 | Must |
| FR-006 | CLI インタフェース | Must |
| FR-007 | 進捗表示・サマリ出力 | Should |

### 7.2 Won't（本案件のスコープ外）

- `custom_reid.py` を使った Re-ID 処理
- `stable_id` の付与・更新
- `pink_id` の計算（Stage 3 で実装済み）
- `track_id` の計算（Stage 2 で実装済み）
- Deep OC-SORT のパラメータチューニング
- 可視化スクリプトの作成・修正
- `halpe26_to_openpose.py` への変更
- 複数対象の同時追跡
- 動画ファイル読み込み（画素参照なし）

### 7.3 MVP

- FR-001 〜 FR-006 が動作し、camSony1_S 相当（900 フレーム分の JSON）に対して `pink_track_id` 付与 JSON が生成できる状態を最小実行可能プロダクトとする
- FR-007（進捗表示・サマリ出力）は Should。実装コストが低いため本案件内で一括実装する
