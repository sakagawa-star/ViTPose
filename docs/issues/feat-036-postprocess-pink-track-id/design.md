# feat-036: postprocess_patient_id.py 実装（pink_id + track_id ハイブリッド対象追跡） — 機能設計書

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001（入力 JSON 読み込み、生 dict 保持） | §4.1 |
| FR-002（パス 1 フレーム単位の有効/重複 BB 特定） | §4.2 |
| FR-003（パス 1 全フレーム走査と `patient_track_ids` 集合構築） | §4.3 |
| FR-004（パス 2 `pink_track_id` 割り当て） | §4.4 |
| FR-005（ポストプロセス本体） | §4.5 |
| FR-006（CLI インタフェース） | §4.6 |
| FR-007（進捗表示・サマリ出力） | §4.7 |
| NFR-001（パフォーマンス） | §7.1 |
| NFR-003（信頼性） | §4.5.4 / §8 |
| NFR-004（メモリ） | §7.2 |

## 2. システム構成

### 2.1 モジュール構成

本案件で作成するのは 1 つの独立スクリプト `scripts/postprocess_patient_id.py` のみ。他スクリプトからの import は想定しない。

```
scripts/postprocess_patient_id.py
├─ 定数
│   ├─ PINK_TRACK_ID_PATIENT = 1
│   ├─ PINK_TRACK_ID_NOT_PATIENT = -1
│   ├─ PINK_TRACK_ID_DUPLICATE = -2
│   └─ PROGRESS_INTERVAL_FRAMES = 3000
├─ 純関数
│   ├─ load_json_frames(json_dir) → dict[int, tuple[str, dict]]                    (FR-001)
│   ├─ classify_frame_pink(people, frame_idx)
│   │       → tuple[int | None, int | None, set[int]]                              (FR-002)
│   ├─ build_patient_state(frame_to_json)
│   │       → tuple[set[int], dict[int, tuple[int | None, set[int]]]]              (FR-003)
│   ├─ assign_pink_track_ids(people, valid_pink_idx, duplicate_person_idxs,
│   │                        patient_track_ids) → list[int]                        (FR-004)
│   └─ _is_number(v) → bool                                                        (共通ヘルパー)
├─ I/O 関数
│   ├─ write_json_frame(out_path, data) → None
│   └─ print_summary(total_frames, patient_track_ids, frames_patient,
│                   frames_duplicate, elapsed, out_dir) → None                     (FR-007)
└─ エントリポイント
    └─ main() → None                                                                (FR-005, FR-006, FR-007)
```

### 2.2 既存ファイルとの関係

- **流儀元**: `scripts/postprocess_track.py`（feat-035）の CLI 構造・`load_json_frames`・`_is_number` ヘルパー・サマリ出力形式を流用する
- **生 dict 保持のお手本**: `scripts/postprocess_pink_id.py`（feat-033）/ `scripts/postprocess_track.py`（feat-035）の「入力 content_dict を直接書き換えて出力」流儀を採用
- **変更禁止**: 既存ファイル（`postprocess_reid.py`, `postprocess_pink_id.py`, `postprocess_track.py`, `custom_reid.py`, `visualize_tracking.py`, `run_halpe26_pipeline_yolo11.py`）は本案件で一切変更しない。コードは流儀を参考にコピー・改変する（共通モジュールへの切り出しは本案件のスコープ外）

### 2.3 ディレクトリ構成

```
scripts/
├── postprocess_pink_id.py           # 既存（変更しない、feat-033）
├── postprocess_track.py             # 既存（変更しない、feat-035）
└── postprocess_patient_id.py        # 新規（本案件）

experiments/results/
├── camSony1_S_track_pink_json/      # 入力（Stage 3 出力、既存、変更しない）
└── camSony1_S_patient_json/         # 出力（本案件で生成、推奨命名）
```

出力ディレクトリ名の規約: `{入力ディレクトリ名}_patient` もしくは `{動画名}_patient_json`。規約は README と feat-034 ロードマップでの推奨にとどめ、スクリプト内では強制しない（CLI 引数で任意パス指定可）。

## 3. 技術スタック

| 項目 | 値 | 選定理由 |
|------|-----|----------|
| 言語 | Python 3.10.16 | プロジェクト既定 |
| パッケージ管理 | uv | プロジェクト既定。`uv run python scripts/postprocess_patient_id.py` で実行 |
| 標準ライブラリ | `argparse`, `json`, `os`, `re`, `sys`, `time`, `math`, `pathlib` | 全機能が標準ライブラリのみで実装可能 |

追加ライブラリの導入は行わない。**numpy / OpenCV / BoxMOT / custom_reid は import しない**（画素処理・トラッキング・Re-ID は不要）。

## 4. 各機能の詳細設計

### 4.1 FR-001: 入力 JSON 読み込み（生 dict 保持）

#### 4.1.1 データフロー

- 入力: `json_dir: str`
- 出力: `frame_to_json: dict[int, tuple[str, dict]]`

#### 4.1.2 処理ロジック

feat-035 `postprocess_track.py` の `load_json_frames` をそのまま流用する:

```python
def load_json_frames(json_dir: str) -> dict[int, tuple[str, dict]]:
    """JSONディレクトリを全読み込みし、生dict を辞書として保持する（FR-001）。

    Returns: {frame_idx: (original_filename, content_dict)}
    """
    json_path = Path(json_dir)
    json_files = sorted(json_path.glob("*.json"))
    if not json_files:
        print(f"ERROR: No JSON files found in {json_dir}")
        sys.exit(1)

    pattern = re.compile(r"_(\d{6})\.json$")
    out: dict[int, tuple[str, dict]] = {}
    for jf in json_files:
        m = pattern.search(jf.name)
        if m is None:
            continue
        fidx = int(m.group(1))
        try:
            with open(jf) as f:
                content = json.load(f)
        except json.JSONDecodeError:
            print(f"WARNING: Failed to parse {jf.name}, treating as empty")
            content = {"version": 1.3, "people": []}
        out[fidx] = (jf.name, content)
    return out
```

#### 4.1.3 境界条件

- `json_dir` が存在しないまたは空 → ERROR 出力後 `sys.exit(1)`
- ファイル名が命名規約に合致しない → スキップ
- 単一ファイルの `JSONDecodeError` → WARNING、空 people フォールバック

#### 4.1.4 エラーハンドリング

JSON 0 件のときに `sys.exit(1)` する以外は例外を raise しない。

### 4.2 FR-002: パス 1 - 有効 `pink_id=1` BB の選択と重複 BB 特定（フレーム単位）

#### 4.2.1 データフロー

- 入力:
  - `people: list[dict]`（1 フレーム分の JSON `people` 配列）
  - `frame_idx: int`（WARNING ログ出力用）
- 出力: `(valid_pink_idx: int | None, valid_track_id: int | None, duplicate_person_idxs: set[int])`

#### 4.2.2 処理ロジック

```python
def classify_frame_pink(
    people: list[dict],
    frame_idx: int,
) -> tuple[int | None, int | None, set[int]]:
    """1 フレームの pink_id=1 候補から有効 BB と重複 BB を特定する（FR-002）。

    Returns:
        (valid_pink_idx, valid_track_id, duplicate_person_idxs)

        - valid_pink_idx: 有効 pink_id=1 BB の people 内インデックス（該当なしなら None）
        - valid_track_id: 有効 BB の track_id（track_id が欠損/無効/<=0 の場合は None）
        - duplicate_person_idxs: 重複 pink_id=1 BB のインデックス集合
    """
    # 1) pink_id=1 の候補インデックスを列挙
    pink_candidates: list[int] = [
        i for i, p in enumerate(people) if p.get("pink_id") == 1
    ]
    if not pink_candidates:
        return None, None, set()

    # 2) bbox_score 最大の候補を選ぶ（タイブレーク: 最小インデックス）
    best_idx = pink_candidates[0]
    best_score = _score_for_selection(people[best_idx], frame_idx, best_idx)
    for i in pink_candidates[1:]:
        score = _score_for_selection(people[i], frame_idx, i)
        if score > best_score:
            best_score = score
            best_idx = i
        # score == best_score のときは best_idx を維持（最小インデックス優先）

    # 3) 有効 BB の track_id を取り出す
    valid_person = people[best_idx]
    tid = valid_person.get("track_id")
    if _is_number(tid) and int(tid) >= 1:
        valid_track_id: int | None = int(tid)
    else:
        valid_track_id = None

    # 4) 重複 BB 集合（有効以外の pink_id=1）
    duplicate_person_idxs: set[int] = {i for i in pink_candidates if i != best_idx}

    return best_idx, valid_track_id, duplicate_person_idxs


def _score_for_selection(person: dict, frame_idx: int, person_idx: int) -> float:
    """bbox_score を取り出す。欠損/非数値なら -inf を返し WARNING を出す。"""
    score = person.get("bbox_score")
    if not _is_number(score):
        print(
            f"WARNING: Invalid bbox_score in frame {frame_idx} person {person_idx}"
            f" with pink_id=1, treating as score=-inf"
        )
        return float("-inf")
    return float(score)


def _is_number(v) -> bool:
    """数値判定。bool は int のサブクラスだが除外する。"""
    return isinstance(v, (int, float)) and not isinstance(v, bool)
```

#### 4.2.3 境界条件

- `pink_id=1` 候補 0 件 → `(None, None, set())` 即リターン（AC-002-1）
- `pink_id=1` 候補 1 件 → その候補が有効、重複集合は空（AC-002-2）
- 候補が複数で全て `bbox_score=-inf` → 最小インデックスが選ばれる（全て同値のため初期値 `pink_candidates[0]` が維持される）（AC-002-7 の後半）
- 有効 BB の `track_id` が欠損/`-1`/非数値 → `valid_track_id = None`（AC-002-5, AC-002-6）

#### 4.2.4 エラーハンドリング

本関数は例外を raise しない。`bbox_score` の型不正は WARNING を出してその候補を選択対象から実質除外する（`-inf` 扱い）。

### 4.3 FR-003: パス 1 - 全フレーム走査と `patient_track_ids` 集合構築

#### 4.3.1 データフロー

- 入力: `frame_to_json: dict[int, tuple[str, dict]]`
- 出力:
  - `patient_track_ids: set[int]`
  - `frame_classification: dict[int, tuple[int | None, set[int]]]`

#### 4.3.2 処理ロジック

```python
def build_patient_state(
    frame_to_json: dict[int, tuple[str, dict]],
) -> tuple[set[int], dict[int, tuple[int | None, set[int]]]]:
    """全フレーム走査でパス 1 の結果を構築する（FR-003）。"""
    patient_track_ids: set[int] = set()
    frame_classification: dict[int, tuple[int | None, set[int]]] = {}

    sorted_frame_idxs = sorted(frame_to_json.keys())
    for frame_idx in sorted_frame_idxs:
        _, content_dict = frame_to_json[frame_idx]
        people = content_dict.get("people", [])

        valid_pink_idx, valid_track_id, duplicate_person_idxs = classify_frame_pink(
            people, frame_idx
        )
        if valid_track_id is not None:
            patient_track_ids.add(valid_track_id)
        frame_classification[frame_idx] = (valid_pink_idx, duplicate_person_idxs)

        if frame_idx % PROGRESS_INTERVAL_FRAMES == 0:
            print(f"Pass 1 processing frame {frame_idx:06d}")

    return patient_track_ids, frame_classification
```

- `sorted(frame_to_json.keys())` で決定的な走査順を保証する（進捗ログが昇順で出る）
- `valid_track_id is None` のフレームは `patient_track_ids` に何も追加しない（AC-003-3）
- `frame_classification` は全フレーム分を保持する（空 people のフレームも `(None, set())` として登録される）（AC-003-4）

#### 4.3.3 境界条件

- `frame_to_json` が空 → `(set(), {})` を返す（通常は FR-001 で `sys.exit(1)` 済みなので到達しない）
- `pink_id=1` が全動画で観測されない → `patient_track_ids == set()`（AC-003-1）

#### 4.3.4 エラーハンドリング

本関数は例外を raise しない。

### 4.4 FR-004: パス 2 - `pink_track_id` の JSON 人物への割り当て

#### 4.4.1 データフロー

- 入力:
  - `people: list[dict]`
  - `valid_pink_idx: int | None`
  - `duplicate_person_idxs: set[int]`
  - `patient_track_ids: set[int]`
- 出力: `result: list[int]`、長さ `len(people)`

#### 4.4.2 処理ロジック

```python
def assign_pink_track_ids(
    people: list[dict],
    valid_pink_idx: int | None,
    duplicate_person_idxs: set[int],
    patient_track_ids: set[int],
) -> list[int]:
    """各 BB に pink_track_id を割り当てる（FR-004）。

    処理ステップ A〜D（requirements.md FR-004 と対応）:
      ステップ A: result を初期化
      ステップ B: 各 BB を階層 1〜4 で判定
        階層 1) 重複除外: -2
        階層 2) 種（pink_id=1 直接判定）: 1
        階層 3) 拡張（track_id 経由の伝播）: 1
        階層 4) 非対象: -1
      ステップ C: 後処理デデュプ（要求 E）
      ステップ D: result を返す
    """
    # ステップ A: 初期化
    result: list[int] = [PINK_TRACK_ID_NOT_PATIENT] * len(people)
    # ステップ B: 階層 1〜4 で判定
    for i, person in enumerate(people):
        # 階層 1) 重複除外
        if i in duplicate_person_idxs:
            result[i] = PINK_TRACK_ID_DUPLICATE
            continue
        # 階層 2) 種: pink_id=1 による直接判定（track_id の状態に依存しない）
        if i == valid_pink_idx:
            result[i] = PINK_TRACK_ID_PATIENT
            continue
        # 階層 3) 拡張: 種が付いた track_id を時間方向へ伝播
        tid = person.get("track_id")
        if _is_number(tid) and int(tid) >= 1 and int(tid) in patient_track_ids:
            result[i] = PINK_TRACK_ID_PATIENT
        # 階層 4) 非対象: 初期値 -1 のまま

    # ステップ C: 後処理デデュプ（要求 E）— 同一フレーム内で pink_track_id=1 が複数 → bbox_score 最大のみ維持
    patient_indices = [i for i, v in enumerate(result) if v == PINK_TRACK_ID_PATIENT]
    if len(patient_indices) >= 2:
        best_i = patient_indices[0]
        best_score = _score_for_dedup(people[best_i])
        for i in patient_indices[1:]:
            score = _score_for_dedup(people[i])
            if score > best_score:
                best_score = score
                best_i = i
        for i in patient_indices:
            if i != best_i:
                result[i] = PINK_TRACK_ID_DUPLICATE

    # ステップ D: 返却
    return result


def _score_for_dedup(person: dict) -> float:
    """デデュプ用 bbox_score 取得。欠損/非数値なら -inf。WARNING は出さない。"""
    score = person.get("bbox_score")
    if not _is_number(score):
        return float("-inf")
    return float(score)
```

- 判定順は「重複除外 → 種（`pink_id=1` 直接判定）→ 拡張（`track_id` 伝播）→ 非対象 → 後処理デデュプ」。種が拡張より上位にあるため、有効 `pink_id=1` BB は `track_id` の状態によらず常に `pink_track_id=1` を受ける（AC-004-7）
- 後処理デデュプ（ステップ C）は階層判定（ステップ B、階層 1〜4）の結果に対して適用され、同一フレーム内で `pink_track_id=1` が最大 1 つになることを保証する（AC-004-9〜13、要求 E）
- `_score_for_dedup` は `_score_for_selection`（FR-002 用）と異なり WARNING を出さない。デデュプは正常フローの一部であり、WARNING は FR-002 で既に出力済みのため重複ログを避ける
- `track_id` キー欠損や非数値の BB は拡張判定から自動的に除外される（AC-004-6）

#### 4.4.3 境界条件

- `people == []` → 空リストを返す
- `valid_pink_idx is None` かつ `duplicate_person_idxs == set()` → 全員 track_id 判定のみ
- `patient_track_ids == set()` → 有効/重複以外は全て `-1`

#### 4.4.4 エラーハンドリング

本関数は例外を raise しない。

### 4.5 FR-005: ポストプロセス本体

本メインロジックは、requirements.md §1.5 で定義された以下のユーザー要求を 2 パス方式で同時に満たす:

- **要求 A（種による直接判定）**: パス 2 で `assign_pink_track_ids` の階層 2（`i == valid_pink_idx → 1`）として実装
- **要求 B（全区間参照による `track_id` 経由の継続）**: パス 1（`build_patient_state`）で全区間の `patient_track_ids` 集合を構築 → パス 2 で `assign_pink_track_ids` の階層 3（`track_id in patient_track_ids → 1`）として実装。ADR-002 補足の「2 パス方式と全区間双方向参照の等価性」参照
- **要求 C（重複除外、基点除外）**: パス 1 で `classify_frame_pink` が `bbox_score` 最大を `valid_pink_idx` として採用し、他を `duplicate_person_idxs` に分類。重複 BB の `track_id` は `valid_track_id` として返されないため `patient_track_ids` に追加されず、拡張の基点にもならない。パス 2 で階層 1（`duplicate → -2`）として実装
- **要求 E（フレーム内 `pink_track_id=1` のデデュプ）**: パス 2 で `assign_pink_track_ids` のステップ C（後処理デデュプ）として実装。階層判定後に同一フレーム内で `pink_track_id=1` が複数存在する場合、`bbox_score` 最大の BB のみ `1` を維持し、他を `-2` に降格
- **要求 D（非対象）**: パス 2 で `assign_pink_track_ids` の初期値 `-1` および階層 4（非該当時）として実装

#### 4.5.1 データフロー

- 入力:
  - `args.json_dir: str`
  - `args.out_dir: str`
- 中間:
  - `frame_to_json: dict[int, tuple[str, dict]]`
  - `patient_track_ids: set[int]`
  - `frame_classification: dict[int, tuple[int | None, set[int]]]`
  - `frames_patient: int`（出力時にカウント）
  - `frames_duplicate: int`（出力時にカウント）
- 出力:
  - 出力ディレクトリに `{video_stem}_{frame_idx:06d}.json` を書き出す

#### 4.5.2 初期化フェーズ擬似コード

```
1. args = argparse.parse_args()
2. if os.path.realpath(args.json_dir) == os.path.realpath(args.out_dir):
       print("ERROR: --out-dir must differ from --json-dir to prevent overwriting")
       sys.exit(1)
3. os.makedirs(args.out_dir, exist_ok=True)
4. start_time = time.time()
5. frame_to_json = load_json_frames(args.json_dir)     # FR-001
6. print(f"Loaded {len(frame_to_json)} frames from JSON")
```

#### 4.5.3 パス 1 擬似コード

```
7. print("Pass 1: Scanning frames to build patient_track_ids...")
8. patient_track_ids, frame_classification = build_patient_state(frame_to_json)  # FR-003
9. print(f"Pass 1 done: patient_track_ids = {len(patient_track_ids)} unique track_ids")
```

#### 4.5.4 パス 2 擬似コード

```
10. print("Pass 2: Assigning pink_track_id...")
11. frames_patient = 0
12. frames_duplicate = 0
13. for frame_idx in sorted(frame_to_json.keys()):
        filename, content_dict = frame_to_json[frame_idx]
        people = content_dict.get("people", [])
        valid_pink_idx, duplicate_person_idxs = frame_classification[frame_idx]

        # FR-004: 割り当て
        assigned = assign_pink_track_ids(
            people,
            valid_pink_idx,
            duplicate_person_idxs,
            patient_track_ids,
        )

        # 生 dict に書き込む
        for i, person in enumerate(people):
            person["pink_track_id"] = assigned[i]

        # サマリ集計
        has_patient = any(v == PINK_TRACK_ID_PATIENT for v in assigned)
        has_duplicate = any(v == PINK_TRACK_ID_DUPLICATE for v in assigned)
        if has_patient:
            frames_patient += 1
        if has_duplicate:
            frames_duplicate += 1

        # 書き出し
        out_path = os.path.join(args.out_dir, filename)
        write_json_frame(out_path, content_dict)

        # 進捗（FR-007）
        if frame_idx % PROGRESS_INTERVAL_FRAMES == 0:
            print(f"Pass 2 processing frame {frame_idx:06d}")

14. elapsed = time.time() - start_time
15. print_summary(
        total_frames=len(frame_to_json),
        patient_track_ids=patient_track_ids,
        frames_patient=frames_patient,
        frames_duplicate=frames_duplicate,
        elapsed=elapsed,
        out_dir=args.out_dir,
    )
```

#### 4.5.5 エラーハンドリング

| 想定エラー | 検出方法 | 処理 | ログ |
|-----------|----------|------|------|
| `--out-dir == --json-dir` | `os.path.realpath` 比較 | ERROR 出力 → `sys.exit(1)` | `ERROR: --out-dir must differ from --json-dir to prevent overwriting` |
| 入力 JSON ディレクトリにファイルなし | `load_json_frames` 内で 0 件検出 | ERROR 出力 → `sys.exit(1)` | `ERROR: No JSON files found in {json_dir}` |
| 個別 JSON の parse 失敗 | `json.JSONDecodeError` | WARNING 出力、空 people として処理継続 | `WARNING: Failed to parse {name}, treating as empty` |
| `pink_id=1` BB の `bbox_score` 欠損 | `_is_number` false | WARNING 出力、`-inf` 扱いで選択対象から除外 | `WARNING: Invalid bbox_score in frame {idx} person {i} with pink_id=1, treating as score=-inf` |
| 有効 BB の `track_id` 欠損/無効 | `_is_number` false または `< 1` | `valid_track_id = None` とし、そのフレームでは集合に何も追加しない（WARNING は出さない、設計上の正常ケース） | - |
| 入力 JSON の `people` キーがリストでない/不正型 | 後続の `for person in people:` で `TypeError` | 例外を捕捉せず伝播（入力 JSON は feat-035 出力形式に準拠する前提） | - |

### 4.6 FR-006: CLI インタフェース

```python
parser = argparse.ArgumentParser(
    description=(
        "Add pink_track_id (patient id) to HALPE 26 JSON "
        "by combining pink_id and track_id"
    )
)
parser.add_argument(
    "--json-dir", required=True, help="Input HALPE 26 JSON directory"
)
parser.add_argument(
    "--out-dir", required=True,
    help="Output JSON directory (must differ from --json-dir)",
)
args = parser.parse_args()
```

- 必須引数未指定時の argparse エラー（終了コード 2）は argparse のデフォルト挙動に任せる
- 同一パスチェックは `postprocess_track.py` L226-228 と同じ

#### フェーズ 1 実行コマンド（手動テスト時に実行）

```
uv run python scripts/postprocess_patient_id.py \
  --json-dir experiments/results/camSony1_S_pink_json \
  --out-dir experiments/results/camSony1_S_patient_json
```

（`camSony1_S_pink_json` は feat-033 → feat-035 の順もしくは feat-035 → feat-033 の順で生成済みの、`pink_id` と `track_id` が両方付与された JSON ディレクトリ）

#### フェーズ 2 実行コマンド（本番スケール検証）

```
uv run python scripts/postprocess_patient_id.py \
  --json-dir experiments/results/camSony1_L_pink_json \
  --out-dir experiments/results/camSony1_L_patient_json
```

### 4.7 FR-007: 進捗表示・サマリ出力

#### 4.7.1 進捗表示

パス 1 とパス 2 それぞれで `frame_idx % PROGRESS_INTERVAL_FRAMES == 0`（`PROGRESS_INTERVAL_FRAMES = 3000`）を満たすフレームで進捗ログを出す。`sorted(frame_to_json.keys())` で走査するため、昇順で出力される。

```python
if frame_idx % PROGRESS_INTERVAL_FRAMES == 0:
    print(f"Pass 1 processing frame {frame_idx:06d}")
    # or "Pass 2 processing frame ..."
```

パス境界ログ:

```python
print("Pass 1: Scanning frames to build patient_track_ids...")
# ...
print(f"Pass 1 done: patient_track_ids = {len(patient_track_ids)} unique track_ids")
print("Pass 2: Assigning pink_track_id...")
```

#### 4.7.2 サマリ出力

パス 2 ループ終了後に出力する:

```python
def print_summary(
    total_frames: int,
    patient_track_ids: set[int],
    frames_patient: int,
    frames_duplicate: int,
    elapsed: float,
    out_dir: str,
) -> None:
    fps = total_frames / elapsed if elapsed > 0 else 0.0
    print()
    print(f"Total frames: {total_frames}")
    print(f"Unique patient track_ids: {len(patient_track_ids)}")
    print(f"Frames with pink_track_id=1 (patient): {frames_patient}")
    print(f"Frames with pink_track_id=-2 (duplicate): {frames_duplicate}")
    print(f"Processing time: {elapsed:.1f} sec ({fps:.1f} fps)")
    print(f"Output directory: {out_dir}")
```

- `total_frames` は `frame_to_json` のエントリ数（= 命名規約に合致した入力 JSON ファイル数）
- `frames_patient` / `frames_duplicate` はパス 2 でカウントする（1 フレームに複数対象 BB があっても 1 とカウント）
- `fps` はトータル（パス 1 + パス 2 + I/O 含む）の実効処理速度

## 5. 状態遷移

本スクリプトにはスクリプト側の明示的な状態遷移はない。2 パス方式のため、パス 1 の結果 `(patient_track_ids, frame_classification)` がパス 2 の入力になる単純なフェーズ遷移のみ:

```
init → load_json_frames → pass 1 (build_patient_state) → pass 2 (assign + write) → summary
```

feat-035 のような Deep OC-SORT 内部状態（`active_tracks` / `frame_count`）は本案件では持たない。

## 6. ファイル・ディレクトリ設計

### 6.1 入力ファイル規約

- 入力 JSON: `{任意のディレクトリ}/{video_stem}_{frame_idx:06d}.json`
  - 例: `experiments/results/camSony1_S_pink_json/camSony1_S_000000.json`
  - 各 `people` 要素は `bbox`, `bbox_score`, `pink_id`, `track_id` を含む（feat-033 + feat-035 の出力）

### 6.2 出力ファイル規約

- 出力ディレクトリ: CLI 引数 `--out-dir` で指定される任意パス
- ファイル名: 入力 JSON と完全に同一
- 中身: 入力 JSON の各 `people[*]` に `pink_track_id: int` を追加したもの。その他のフィールドは元通り

### 6.3 出力 JSON スキーマ差分

```json
{
  "version": 1.3,
  "people": [
    {
      "person_id": [-1],
      "pose_keypoints_2d": [...],
      "bbox": [x1, y1, x2, y2],
      "bbox_score": 0.95,
      "stable_id": 3,        // 入力に存在する場合のみ、変更なし
      "pink_id": 1,          // 変更なし
      "track_id": 5,         // 変更なし
      "pink_track_id": 1     // 新規追加（1=対象 / -1=非対象 / -2=重複）
    }
  ]
}
```

### 6.4 Stage 順序との関係

feat-034 ロードマップでは Stage 2（feat-035）→ Stage 3（feat-033）→ Stage 4（本案件）の順序で実行する。feat-033 と feat-035 はいずれも生 dict 保持設計なので、実行順は `feat-033 → feat-035` でも `feat-035 → feat-033` でも最終的に `track_id` と `pink_id` の両方が保持された JSON が得られる。本案件はその両方が付与済みの JSON を入力とする。

## 7. 非機能

### 7.1 パフォーマンス見積もり

- camSony1_S 相当（900 フレーム）: 1 秒未満で完了見込み（I/O 込みでも数秒以内）
- camSony1_L 相当（321K フレーム）: JSON I/O がボトルネックになる。画素処理も Deep OC-SORT 推論もないため、feat-035（191 fps）より大幅に高速と期待する。実測の目安は **1000 fps 以上**（321K フレームで 5 分以内）。ただし保証しない
- パス 1 はメモリ上の辞書走査のみ（I/O なし）で高速、パス 2 は各フレームで `json.dump` による書き出しが発生するためここが律速

### 7.2 メモリ使用量

`frame_to_json` 辞書のメモリ見積もり（feat-035 §7.2 と同じ計算）:

- 1 人あたり約 1 KB の JSON テキスト
- 室内動画は通常 1〜3 人、多くても 5 人程度
- camSony1_L（321,239 フレーム）: 約 321K × 3 人 × 1 KB ≒ 約 0.96 GB、Python dict オーバーヘッドで 2〜3 倍 → 約 2〜3 GB

`frame_classification` 追加分: 1 フレームあたり `(int | None, set[int])` で数十バイト。321K × 数十バイト ≒ 数十 MB（無視できる）。

`patient_track_ids` 追加分: `set[int]` で高々数千要素。数十〜数百 KB（無視できる）。

**500 MB 目標との乖離**: feat-035 と同様、上記見積もりは 500 MB を大きく超える可能性がある。要求仕様書 NFR-004 の検証基準は「OOM で異常終了せず完走すること」を必須とし、超過時は別案件でストリーミング読み込みへの切り替えを検討する。

**補足**:
- JSON 書き出しは 1 フレームずつ行い、出力バッファは保持しない
- パス 1 とパス 2 で `frame_to_json` を共有するため 2 回ロードしない

## 8. ログ・デバッグ設計

- ログ手段: `print()`（`postprocess_reid.py` / `postprocess_pink_id.py` / `postprocess_track.py` と揃える。`logging` モジュールは導入しない）
- ログレベル表記: `ERROR:` / `WARNING:` / (INFO は prefix なしで `print`)
- ログ出力ポイント:
  - 起動時: `Loaded N frames from JSON`
  - パス 1: `Pass 1: Scanning frames to build patient_track_ids...` / 進捗 3000 フレームごと / `Pass 1 done: ...`
  - パス 2: `Pass 2: Assigning pink_track_id...` / 進捗 3000 フレームごと
  - エラー・警告: §4.5.5 のテーブル参照
  - 終了時: サマリ（§4.7.2）

## 9. インターフェース定義（関数シグネチャ）

```python
def load_json_frames(
    json_dir: str,
) -> dict[int, tuple[str, dict]]: ...

def classify_frame_pink(
    people: list[dict],
    frame_idx: int,
) -> tuple[int | None, int | None, set[int]]: ...

def build_patient_state(
    frame_to_json: dict[int, tuple[str, dict]],
) -> tuple[set[int], dict[int, tuple[int | None, set[int]]]]: ...

def assign_pink_track_ids(
    people: list[dict],
    valid_pink_idx: int | None,
    duplicate_person_idxs: set[int],
    patient_track_ids: set[int],
) -> list[int]: ...

def write_json_frame(out_path: str, data: dict) -> None: ...

def print_summary(
    total_frames: int,
    patient_track_ids: set[int],
    frames_patient: int,
    frames_duplicate: int,
    elapsed: float,
    out_dir: str,
) -> None: ...

def _is_number(v) -> bool: ...
def _score_for_selection(person: dict, frame_idx: int, person_idx: int) -> float: ...
def _score_for_dedup(person: dict) -> float: ...

def main() -> None: ...
```

クラスは作らない。すべてモジュールレベル関数で実装する。

定数:

```python
PINK_TRACK_ID_PATIENT: int = 1
PINK_TRACK_ID_NOT_PATIENT: int = -1
PINK_TRACK_ID_DUPLICATE: int = -2
PROGRESS_INTERVAL_FRAMES: int = 3000
```

## 10. 設計判断の記録（ADR）

### ADR-001: 生 dict 保持設計の採用（feat-033 / feat-035 踏襲）

- **採用案**: 入力 JSON を `json.load()` で生の辞書として読み込み、`people[*]` に `pink_track_id` キーを追加するだけで出力する
- **却下案**: 必要フィールド（`pink_id`, `track_id`, `bbox_score`）のみ抽出した軽量データ構造で処理し、出力時に元 JSON を再読み込みする方式
- **理由**: feat-033 / feat-035 の ADR-001 と同じ設計思想。4 ステージパイプラインの Stage 4 として Stage 2/3 で追加された全フィールドをそのまま保持する必要がある。再読み込み方式は I/O が 2 倍になり性能的にも不利

### ADR-002: 2 パス方式の採用（リアルタイム継続判断の却下）

- **採用案**: 全フレームを 2 回走査する。パス 1 で `patient_track_ids` 集合と重複情報を確定し、パス 2 で `pink_track_id` を割り当てる
- **却下案A**: 1 パスでリアルタイムに patient track_id を継続判断する（「連続 N フレームで pink_id=1 が同じ track_id に付いたら更新」「消失時 M フレーム猶予後に手放す」等のオンライン追跡ロジック）
- **却下案B**: 1 パスで過去のみ参照（`pink_id=1` 観測前の前段は -1 確定）
- **理由**: (1) オンライン追跡はハイパーパラメータ（更新遅延、消失猶予、乗り換え閾値）が増え、動画ごとのチューニングが必要になる。(2) 本案件は既に JSON 化されたオフライン処理なので、全区間走査が可能。未来情報も自由に参照できる。(3) 2 パス方式は「track_id が動画のどこかで一度でも pink_id=1 に紐づけば対象」という直感的な仕様（requirements.md §1.5 要求 B）に最短距離で対応できる。(4) Deep OC-SORT が分裂させた複数 track_id を全て集合に入れることで、自然に見切れ耐性が確保される（feat-022/026 の要件「5〜10 秒の見切れ後に ID 維持」は、対象の track_id が消失前後で同一ならパス 1 で一括補足、別 track_id に切り替わっても再び pink_id=1 と観測されれば両方が集合に入る）

#### 2 パス方式と「全区間双方向参照」の等価性

requirements.md §1.5 要求 B は「動画の全区間（過去・未来両方向）を参照する」という振る舞いを要求するが、実装の FR-003 は `sorted(frame_to_json.keys())` による**昇順単方向ループ**である。この見かけの不一致について、以下の通り等価性が担保される:

- **パス 1 完了時点の状態**: パス 1 は全フレームを昇順に走査するが、処理内容は `patient_track_ids` 集合への追加のみで、集合は動画の**全区間**の観測情報（全ての有効 `pink_id=1` BB の `track_id`）を集約している
- **パス 2 実行時のアクセス範囲**: パス 2 で任意フレーム `f` の BB を評価する際、`patient_track_ids in` 判定は既に全区間の情報を含んでいる集合を参照するため、`f` より前（過去）だけでなく `f` より後（未来）のフレームで観測された `pink_id=1` 情報にもアクセスしているのと等価
- **結論**: パス 2 の各フレームは、「その時点までの過去情報のみ」で判定するオンライン処理ではなく、「動画全区間の観測結果を前提とした」オフライン判定として動作する。昇順ループで実装されているが、情報アクセスの観点では双方向参照と等価

この等価性を保つため、パス 1 完了前にパス 2 を開始する（ストリーム処理化する）実装は**禁止**する。仮に将来メモリ制約で分割処理が必要になった場合も、動画全区間に対するパス 1 を先に完了させてからパス 2 を実行するアーキテクチャを維持する必要がある。

### ADR-003: 重複 BB のタイブレークは `bbox_score` 最大、同値時は最小インデックス

- **採用案**: 1 フレーム内に `pink_id=1` が複数存在する場合、`bbox_score`（YOLO 検出スコア）最大の 1 件を「有効」とし、他を「重複」とする。`bbox_score` 同値の場合は `people` 配列の小さいインデックスを採用
- **却下案A**: `bbox` の面積最大を採用する
- **却下案B**: `pink_ratio`（HSV ピンク画素比率）最大を採用する
- **却下案C**: ハンガリアン法で最適割り当てを計算する
- **理由**: (1) ユーザー指定の判断基準は「信頼できる方」= `bbox_score` 最大。(2) 面積は人物の前後位置でブレやすく、重複 BB 判定に不向き。(3) `pink_ratio` は feat-033 の内部スコアで、feat-033 完了後の JSON には保存されていない（再計算が必要になりコストが高い）。(4) 同値タイブレークは feat-035 / feat-033 と揃えて「最小インデックス優先」とする

### ADR-004: `pink_id` を種、`track_id` を拡張手段とする階層構造

- **採用案**: パス 2 の判定は「重複除外 → 種（`pink_id=1` 直接判定）→ 拡張（`track_id` 伝播）→ 非対象」という 4 段階の階層順で行う。種と拡張は対等な条件ではなく、種が上位にある
- **却下案**: `track_id` と `pink_id` を対等な 2 つの独立条件として union-find（推移的連結）で扱う
- **理由**: (1) ユーザーの明示仕様「`pink_track_id` は `pink_id` を元に、`track_id` で拡張したもの」に従う。`pink_id` はドメイン知識（対象の服装が特徴的な色）に基づく信頼性の高い直接シグナルであり、`track_id` はそれを時間方向に伝播させる道具に過ぎない。(2) 両者を対等に扱うと意味的階層が破壊され、「種なしで拡張のみ」のような不自然なケース（`track_id` 連結だけで対象扱い）の発生余地ができる。(3) 本案件の全ての判定は「まず種を見つけ、次に種を拡張する」という一方向の流れで閉じており、双方向の連結やグラフ探索は不要

### ADR-005: 動画ファイル参照なし（CLI に `--video` を提供しない）

- **採用案**: CLI は `--json-dir` / `--out-dir` のみ受け取る。動画ファイルは参照しない
- **却下案A**: feat-033 / feat-035 と API を揃えるために `--video` を必須引数として受け取る（内部では使わない）
- **却下案B**: デバッグ用途のために動画を任意引数として受け取る
- **理由**: (1) 本案件は JSON に含まれる `pink_id` / `track_id` / `bbox_score` のみで完結する。画素参照は不要。(2) 不要な必須引数を要求するのはユーザビリティを損ねる。(3) デバッグ用途が必要になった時点で別途拡張すればよい（YAGNI）

### ADR-006: 1 ファイル完結・`print` ログ

- **採用案**: `scripts/postprocess_patient_id.py` 1 ファイルで完結、ログは `print` に統一
- **却下案**: 共通モジュール（例: `scripts/json_utils.py`）に `load_json_frames` / `_is_number` を切り出す。`logging` モジュール導入
- **理由**: (1) feat-033 / feat-035 と流儀を揃える。(2) `load_json_frames` は同じコードを 3 ファイルで重複させているが、共通化の必要性は将来 Stage 5 以降が発生した時点で判断する。早すぎる抽象化は避ける。(3) スクリプト 1 本の独立ツールで、構造化ログや集約の必要はない

### ADR-008: 要求 E のデデュプを `assign_pink_track_ids` 内の後処理ステップとして実装

- **採用案**: 階層判定（ステップ B）の結果配列に対して、同一関数内の後処理ステップ C で `pink_track_id=1` のデデュプを行う。スコア取得は `_score_for_dedup`（WARNING なし）を別関数とする
- **却下案A**: デデュプを `main()` のパス 2 ループ内で `assign_pink_track_ids` の外側に実装する
- **却下案B**: `_score_for_selection`（FR-002 用）を再利用し WARNING を出す
- **理由**: (1) デデュプは `pink_track_id` 割り当てロジックの一部であり、`assign_pink_track_ids` の責務に含めるのが凝集性が高い。外側に出すと「assign が返した配列を呼び出し側が事後修正する」という責務分散が生じる。(2) `_score_for_selection` は FR-002 の `pink_id=1` 候補選択時に WARNING を出す関数。デデュプ時に再度 WARNING を出すと同一 BB に対する重複ログとなるため、WARNING なしの `_score_for_dedup` を分離した。(3) デデュプの計算量は O(N)（N = 1 フレーム内の人物数、通常 1〜5 人）で性能影響は無視できる

### ADR-007: `_is_number` で `bool` を除外する

- **採用案**: `_is_number(v) = isinstance(v, (int, float)) and not isinstance(v, bool)`
- **却下案**: `isinstance(v, (int, float))` のみで `bool` を許可する
- **理由**: Python では `bool` は `int` のサブクラス（`isinstance(True, int) == True`）のため、単純な `isinstance` 判定だと `True` / `False` が数値として通ってしまう。`bbox_score` や `track_id` に論理値が入るのは入力 JSON の破損を示すため、安全側に倒して除外する。これは feat-035 `postprocess_track.py` の `_is_number` と同一実装の予防的措置
