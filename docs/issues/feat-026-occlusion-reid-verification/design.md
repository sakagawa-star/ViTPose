# feat-026: 見切れ再同定の検証 機能設計書

**注意**: feat-028（JSONにトラッキングID記録）は2026-04-07に完了済み。stable_id付きJSONは `experiments/results/camSony1_L_reid_json/` に生成済み。stable_idごとのスケルトン可視化による検証手法を本設計書に追加する必要がある。

## 1.1 対応要求マッピング

| 要求 ID | 設計セクション |
|---------|--------------|
| FR-001 | 1.4.1 長尺動画向け出力調整 |
| FR-002 | 1.4.2 Re-IDイベント収集 |
| FR-003 | 1.4.3 Re-IDサマリーレポート |
| FR-004 | 1.4.4 CustomReIDクラスへのイベント通知機能追加 |

---

## 1.2 システム構成

### モジュール構成

```
scripts/
├── custom_reid.py              # [変更] last_events プロパティ追加
└── test_custom_reid_offline.py # [変更] FR-001〜FR-003 の機能追加
```

### モジュール間の依存関係（変更なし）

```
test_custom_reid_offline.py
  ├── custom_reid.py          # CustomReID クラス
  └── boxmot.DeepOcSort       # トラッカー（既存環境）
```

---

## 1.3 技術スタック

既存の技術スタックを使用する。新規ライブラリの追加なし。

| 技術 | バージョン | 用途 |
|------|-----------|------|
| Python | 3.10.16 | 実装言語 |
| uv | - | パッケージ管理 |
| NumPy | 2.2.6 | 特徴量計算 |
| OpenCV (cv2) | 4.13.0.92 | 動画読み込み・HSV変換 |
| BoxMOT | 16.0.11 | Deep OC-SORT トラッカー |

---

## 1.4 各機能の詳細設計

### 1.4.1 長尺動画向け出力調整（FR-001）

#### CLI引数の追加

`argparse` に以下の引数を追加する。既存引数（`--video`, `--json-dir`, `--device`）は変更しない。

```python
parser.add_argument(
    "--print-interval", type=int, default=10,
    help="Progress log interval in frames (default: 10)"
)
parser.add_argument(
    "--no-sim-log", action="store_true",
    help="Suppress Re-ID similarity log output"
)
```

- `--print-interval` のデフォルトは 10（従来互換）。camSony1_L では `3000` を推奨
- `--no-sim-log` はフラグ引数。指定時に True

#### 進捗ログの変更

既存の `frame_idx % 10 == 0` のハードコードを `--print-interval` 引数に置き換える。

```python
# 総フレーム数を動画から取得（ループ開始前）
# CAP_PROP_FRAME_COUNT は一部コーデックで 0 や -1 を返すことがある
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

# ループ内（既存の frame_idx % 10 == 0 を置き換え）
if frame_idx % args.print_interval == 0:
    if total_frames > 0:  # 0以下の場合は取得失敗
        pct = frame_idx / total_frames * 100
        print(
            f"Processing frame {frame_idx:06d}/{total_frames} ({pct:.1f}%): "
            f"track_ids={track_ids}, stable_ids={stable_ids}"
        )
    else:
        print(
            f"Processing frame {frame_idx:06d}/?: "
            f"track_ids={track_ids}, stable_ids={stable_ids}"
        )
```

- フレーム番号のフォーマットを `{frame_idx:04d}` から `{frame_idx:06d}` に変更（6桁ゼロ埋め、321Kフレーム対応）

#### Re-ID類似度ログの抑制

既存の FR-008 関連処理（`snapshot_disappeared` のスナップショット取得、`recently_appeared` の更新、simログ出力ループ、test_custom_reid_offline.py 213-242行目）を `if not args.no_sim_log:` で囲む。`--no-sim-log` 指定時はこれらの処理を全てスキップする。

```python
if not args.no_sim_log:
    # FR-008: update() 前に消失IDをスナップショット
    snapshot_disappeared = dict(reid.disappeared)

# ... reid.update() 呼び出し ...

if not args.no_sim_log:
    # FR-008: 新規出現 track_id を記録
    for tid in track_ids:
        if tid not in recently_appeared:
            recently_appeared[tid] = frame_idx
    # FR-008: 消失した track_id を recently_appeared から除去
    disappeared_tids = set(recently_appeared.keys()) - set(track_ids)
    for tid in disappeared_tids:
        del recently_appeared[tid]
    # FR-008: 類似度ログ出力
    for tid, appear_frame in recently_appeared.items():
        # ... 既存のRe-ID simログ出力（変更なし）
```

#### 設計判断

- **デフォルト値 10**: camSony1_S（900フレーム）との後方互換を優先。長尺動画では CLI で明示的に指定する
- **`--no-sim-log` をフラグにした理由**: 長尺動画ではsimログが膨大になり実用的でないため、完全に抑制する選択肢を提供。部分的な出力（N フレームごと等）は複雑になるため採用しない

### 1.4.2 Re-IDイベント収集（FR-002）

#### データ構造

イベントを辞書のリストとして保持する。テストスクリプトの `main()` 内にローカル変数として定義する。

```python
reid_events: list[dict] = []
```

各イベントの辞書形式:

```python
# 消失
{"type": "disappear", "frame_idx": int, "track_id": int, "stable_id": int}

# 出現（即座マッチ）
{"type": "appear", "frame_idx": int, "track_id": int, "stable_id": int,
 "match_type": "instant", "from_sid": int}

# 出現（新規、_disappeared が空）
{"type": "appear", "frame_idx": int, "track_id": int, "stable_id": int,
 "match_type": "new"}

# 出現（保留状態、_disappeared に消失IDがあるが即座マッチ失敗）
{"type": "appear", "frame_idx": int, "track_id": int, "stable_id": int,
 "match_type": "pending"}

# 遅延マッチ成功
{"type": "delayed_match", "frame_idx": int, "track_id": int,
 "old_stable_id": int, "new_stable_id": int, "offset": int}

# 遅延マッチタイムアウト
{"type": "delayed_timeout", "frame_idx": int, "track_id": int,
 "stable_id": int}
```

#### イベント検出ロジック

イベント検出は以下の2つの情報源を組み合わせる:
- **(A) テストスクリプト側**: 消失の検出（track_id 集合の差分）
- **(B) `reid.last_events`**: 出現時の match_type 判定、遅延マッチ、タイムアウト（FR-004）

match_type の判定は `last_events` のみで行う。`update()` 内で `_disappeared` の状態が変化するため（先行する即座マッチで消費される等）、`update()` 完了後に外部から `_disappeared` を参照して "new" / "pending" を判定することはしない。

#### 処理順序とコード

`reid.update()` 呼び出し後に一括でイベント検出を行う。`track_ids` は `reid.update()` の前後で変化しないため、呼び出し後の検出で問題ない。

```python
# ループ外で初期化
prev_track_set: set[int] = set()
prev_stable_map: dict[int, int] = {}

# --- メインループ内（reid.update() 呼び出し後）---

# reid.update() 呼び出し
stable_ids = reid.update(frame, track_ids, keypoints_map, frame_idx)

# last_events から出現イベントの match_type マッピングを構築
# key: track_id, value: (match_type, from_sid or None)
appear_info: dict[int, tuple[str, int | None]] = {}
for event in reid.last_events:
    if event["type"] == "instant_match":
        appear_info[event["track_id"]] = ("instant", event["from_disappeared_sid"])
    elif event["type"] == "new_id":
        appear_info[event["track_id"]] = ("new", None)
    elif event["type"] == "pending":
        appear_info[event["track_id"]] = ("pending", None)

# (A) 消失検出: 前フレームにあって現フレームにない track_id
curr_track_set = set(track_ids)
lost_tids = prev_track_set - curr_track_set
for tid in sorted(lost_tids):
    sid = prev_stable_map[tid]
    reid_events.append({
        "type": "disappear", "frame_idx": frame_idx,
        "track_id": tid, "stable_id": sid
    })

# (B) 出現検出: last_events の appear_info に含まれる track_id
for tid in sorted(appear_info.keys()):
    assigned_sid = stable_ids[tid]
    match_type, from_sid = appear_info[tid]
    if match_type == "instant":
        reid_events.append({
            "type": "appear", "frame_idx": frame_idx,
            "track_id": tid, "stable_id": assigned_sid,
            "match_type": "instant", "from_sid": from_sid
        })
    elif match_type == "new":
        reid_events.append({
            "type": "appear", "frame_idx": frame_idx,
            "track_id": tid, "stable_id": assigned_sid,
            "match_type": "new"
        })
    elif match_type == "pending":
        reid_events.append({
            "type": "appear", "frame_idx": frame_idx,
            "track_id": tid, "stable_id": assigned_sid,
            "match_type": "pending"
        })

# (B) 遅延マッチ・タイムアウトイベントの取得
for event in reid.last_events:
    if event["type"] == "delayed_match":
        reid_events.append({
            "type": "delayed_match",
            "frame_idx": event["frame_idx"],
            "track_id": event["track_id"],
            "old_stable_id": event["old_stable_id"],
            "new_stable_id": event["new_stable_id"],
            "offset": event["offset"],
        })
    elif event["type"] == "delayed_timeout":
        reid_events.append({
            "type": "delayed_timeout",
            "frame_idx": event["frame_idx"],
            "track_id": event["track_id"],
            "stable_id": event["stable_id"],
        })

# ループ末尾で更新
prev_track_set = curr_track_set
prev_stable_map = dict(stable_ids)
```

#### `recently_appeared` との関係

既存コードの `recently_appeared` 辞書（FR-008 類似度ログ用）は、`prev_track_set` と類似した出現/消失追跡を行う。両者は目的が異なる（`recently_appeared`: simログ出力用、`prev_track_set`: イベント収集用）ため、独立した変数として維持する。`--no-sim-log` 指定時は `recently_appeared` の更新と `snapshot_disappeared` のスナップショット取得およびsimログループ全体をスキップする（不要な計算を省く）。

#### camSony1_S と camSony1_L の関係

camSony1_S.mp4 は camSony1_L.mp4 の途中から切り出したクリップである。そのため、camSony1_S で得られた feat-022 の検証結果（track_id=2 が offset=28 で遅延マッチ成功等）は camSony1_L の実行結果とは一致しない。camSony1_L では動画の先頭から処理するため、track_id の割り振りやイベントの発生タイミングは異なる。

#### 設計判断

- **消失イベントの stable_id 取得**: `prev_stable_map`（前フレームの `update()` 戻り値）を使用する。CustomReID のプライベート属性 `_active_stable` には直接アクセスしない
- **match_type 判定の情報源を `last_events` に完全一元化**: `update()` 内で `_disappeared` の状態が逐次変化するため、中間状態を正確に反映できるのは `update()` 内部でイベントを記録する方法のみ。テストスクリプト側で `disappeared` を参照する方法は採用しない
- **却下案: テストスクリプト側で `disappeared` のスナップショット比較**: `update()` 内で先行する即座マッチが `_disappeared` を消費した場合、後続の new_id が誤って "new" と判定される可能性がある。`last_events` 一元化でこの問題を回避する

### 1.4.3 Re-IDサマリーレポート（FR-003）

#### 出力タイミング

既存の `=== Re-ID Summary ===` セクションの後に出力する。

#### 出力生成関数

```python
def print_reid_report(
    reid_events: list[dict],
    reid: CustomReID,
    last_stable_ids: dict[int, int],
) -> None:
    """Re-IDイベントログと統計を出力する。

    Args:
        reid_events: 収集した全イベントのリスト
        reid: CustomReID インスタンス（最終状態の参照用）
        last_stable_ids: 最終フレームの update() 戻り値
    """
```

この関数はメインループ終了後に呼び出す。

#### (1) Re-ID Event Log

`reid_events` を `(frame_idx, type_order)` でソートして出力する。

ソートキー: `type_order` = `{"disappear": 0, "appear": 1, "delayed_match": 2, "delayed_timeout": 3}`

出力フォーマット（フレーム番号は6桁ゼロ埋め）:

```
=== Re-ID Event Log ===
[disappear] frame=000150 track_id=1 stable_id=1
[appear]    frame=000151 track_id=2 stable_id=2 (pending)
[delayed]   frame=000179 track_id=2 old_sid=2 new_sid=1 (offset=28)
[appear]    frame=001000 track_id=3 stable_id=3 (instant match from sid=1)
[appear]    frame=005000 track_id=4 stable_id=4 (new)
[timeout]   frame=010331 track_id=5 stable_id=5 (confirmed)
```

各タグの出力フォーマット（タグは `f"[{tag:<9}]"` で9文字幅に左寄せパディングする）:
- `[disappear]`: `frame={frame_idx:06d} track_id={tid} stable_id={sid}`
- `[appear   ]` (instant): `frame={frame_idx:06d} track_id={tid} stable_id={sid} (instant match from sid={from_sid})`
- `[appear   ]` (new): `frame={frame_idx:06d} track_id={tid} stable_id={sid} (new)`
- `[appear   ]` (pending): `frame={frame_idx:06d} track_id={tid} stable_id={sid} (pending)`
- `[delayed  ]`: `frame={frame_idx:06d} track_id={tid} old_sid={old_sid} new_sid={new_sid} (offset={offset})`
- `[timeout  ]`: `frame={frame_idx:06d} track_id={tid} stable_id={sid} (confirmed)`

`type_order` 辞書は `print_reid_report` 関数内のローカル変数として定義する。

#### (2) Re-ID Statistics

`reid_events` を集計して統計を出力する。

```python
appear_events = [e for e in reid_events if e["type"] == "appear"]
disappear_events = [e for e in reid_events if e["type"] == "disappear"]
delayed_matches = [e for e in reid_events if e["type"] == "delayed_match"]
delayed_timeouts = [e for e in reid_events if e["type"] == "delayed_timeout"]

instant_count = sum(1 for e in appear_events if e["match_type"] == "instant")
new_count = sum(1 for e in appear_events if e["match_type"] == "new")
pending_count = sum(1 for e in appear_events if e["match_type"] == "pending")

# pending の最終結果: delayed_match / delayed_timeout イベントの track_id と
# appear (pending) イベントの track_id を突き合わせて分類する
delayed_success = len(delayed_matches)
delayed_timeout_count = len(delayed_timeouts)

# 保留中消失: pending の appear イベントのうち、delayed/timeout が発生しなかったもの
delayed_match_tids = {e["track_id"] for e in delayed_matches}
delayed_timeout_tids = {e["track_id"] for e in delayed_timeouts}
pending_tids = {e["track_id"] for e in appear_events if e["match_type"] == "pending"}
pending_disappeared = len(pending_tids - delayed_match_tids - delayed_timeout_tids)

delayed_total = delayed_success + delayed_timeout_count
if delayed_total > 0:
    delayed_rate = f"{delayed_success}/{delayed_total} ({delayed_success/delayed_total*100:.1f}%)"
else:
    delayed_rate = "0/0 (N/A)"

# 出力
print()
print("=== Re-ID Statistics ===")
print(f"Total appear events: {len(appear_events)}")
print(f"  Instant match: {instant_count}")
print(f"  New (no disappeared): {new_count}")
print(f"  New (pending \u2192 delayed match): {delayed_success}")
print(f"  New (pending \u2192 timeout): {delayed_timeout_count}")
print(f"  New (pending \u2192 disappeared): {pending_disappeared}")
print(f"Total disappear events: {len(disappear_events)}")
print(f"Delayed match success rate: {delayed_rate}")
print(f"Unique stable IDs (final): {len(final_unique)}")
if len(active_at_last) > 0:
    print(f"Active stable IDs at last frame: {active_at_last}")
else:
    print("Active stable IDs at last frame: (no active tracks at last frame)")
```

**Unique stable IDs (final)** の計算（print 文の前に実行）:

```python
# 最終フレーム時点のアクティブ stable_id（update() 戻り値の values）
final_active_sids = set(last_stable_ids.values())
# 消失した stable_id（reid.disappeared の keys）
final_disappeared_sids = set(reid.disappeared.keys())
# ユニーク stable_id = アクティブ + 消失（重複なし）
# 遅延マッチ成功時、仮 stable_id は _active_stable から新しい stable_id に
# 置き換わるため、final_active_sids には含まれない。
# 保留中に消失した track_id の仮 stable_id は _disappeared のキーとして残るため、
# final_unique に含まれる。
final_unique = final_active_sids | final_disappeared_sids
```

**Active stable IDs at last frame**:

```python
# last_stable_ids の逆引き: {stable_id: track_id}
active_at_last = {sid: tid for tid, sid in last_stable_ids.items()}
```

#### 設計判断

- **Event Log の全件出力**: 321Kフレームでもイベントは数百件程度のため全件出力する。イベント数が1000件を超えることは病室動画では想定しにくい
- **保留中消失のカウント**: pending_count と delayed_success + delayed_timeout_count が一致しない場合がある（保留中に track_id が消失したケース）。差分を `pending → disappeared` として明示的にカウントし、`Total appear events` の内訳合計が一致することを保証する
- **`last_stable_ids` が空の場合**: 最終フレームで人物が検出されなかった場合、`(no active tracks at last frame)` と出力する

### 1.4.4 CustomReIDクラスへのイベント通知機能追加（FR-004）

#### 変更箇所

`scripts/custom_reid.py` の `CustomReID` クラスに以下を追加する。

**(1) `__init__` に `_last_events` を追加**

```python
self._last_events: list[dict] = []
```

既存の `self._pending` の後に追加する。

**(2) `update()` の先頭で `_last_events` をリセット**

```python
def update(self, frame, track_ids, keypoints_map, frame_idx):
    self._last_events = []
    # ... 既存処理（curr = set(track_ids) 以降は変更なし）
```

`self._last_events = []` を `curr = set(track_ids)` の前に挿入する。

**(3) ステップ2（新規ID処理）内の全分岐にイベント記録を追加（custom_reid.py 84-98行目付近）**

既存コード:
```python
for tid in sorted(new_ids):
    new_feat = self._build_feature(frame, keypoints_map.get(tid))
    matched_sid = self._match(new_feat)
    if matched_sid is not None:
        sid = matched_sid
        del self._disappeared[matched_sid]
    else:
        sid = self._next_stable_id
        self._next_stable_id += 1
        if len(self._disappeared) > 0:
            self._pending[tid] = (sid, frame_idx)
```

変更後:
```python
for tid in sorted(new_ids):
    new_feat = self._build_feature(frame, keypoints_map.get(tid))
    matched_sid = self._match(new_feat)
    if matched_sid is not None:
        sid = matched_sid
        del self._disappeared[matched_sid]
        self._last_events.append({
            "type": "instant_match",
            "track_id": tid,
            "stable_id": matched_sid,
            "from_disappeared_sid": matched_sid,
            "frame_idx": frame_idx,
        })
    else:
        sid = self._next_stable_id
        self._next_stable_id += 1
        if len(self._disappeared) > 0:
            self._pending[tid] = (sid, frame_idx)
            self._last_events.append({
                "type": "pending",
                "track_id": tid,
                "stable_id": sid,
                "frame_idx": frame_idx,
            })
        else:
            self._last_events.append({
                "type": "new_id",
                "track_id": tid,
                "stable_id": sid,
                "frame_idx": frame_idx,
            })
```

`new_id` と `pending` のイベントは `_disappeared` の**その時点の状態**（先行する即座マッチで消費された後の状態）に基づいて記録される。これにより、テストスクリプト側で `_disappeared` の中間状態を参照する必要がなくなる。

**(4) 遅延マッチ成功時にイベントを記録（ステップ4内、custom_reid.py 122行目付近）**

既存コード:
```python
if matched_sid is not None:
    # マッチ成功: stable_id を再割り当て
    old_sid = self._active_stable[tid]
    self._active_stable[tid] = matched_sid
    del self._disappeared[matched_sid]
    print(
        f"Delayed Re-ID: track_id={tid} reassigned "
        ...
    )
    resolved.append(tid)
```

変更後（`self._last_events.append(...)` を `print(...)` の前に挿入）:
```python
if matched_sid is not None:
    # マッチ成功: stable_id を再割り当て
    old_sid = self._active_stable[tid]
    self._active_stable[tid] = matched_sid
    del self._disappeared[matched_sid]
    self._last_events.append({
        "type": "delayed_match",
        "track_id": tid,
        "old_stable_id": old_sid,
        "new_stable_id": matched_sid,
        "offset": frame_idx - appear_frame,
        "frame_idx": frame_idx,
    })
    print(
        f"Delayed Re-ID: track_id={tid} reassigned "
        ...
    )
    resolved.append(tid)
```

**(5) タイムアウト時にイベントを記録（ステップ4内、custom_reid.py 133行目付近）**

既存コード:
```python
elif frame_idx - appear_frame >= self._delay_frames:
    # N フレーム経過: 仮stable_idを確定
    print(
        f"Delayed Re-ID timeout: track_id={tid} "
        ...
    )
    resolved.append(tid)
```

変更後（`self._last_events.append(...)` を `print(...)` の前に挿入）:
```python
elif frame_idx - appear_frame >= self._delay_frames:
    # N フレーム経過: 仮stable_idを確定
    self._last_events.append({
        "type": "delayed_timeout",
        "track_id": tid,
        "stable_id": self._active_stable[tid],
        "frame_idx": frame_idx,
    })
    print(
        f"Delayed Re-ID timeout: track_id={tid} "
        ...
    )
    resolved.append(tid)
```

**(6) `last_events` プロパティ（既存の `disappeared` プロパティの後に追加）**

```python
@property
def last_events(self) -> list[dict]:
    """直前の update() で発生したイベント（読み取り専用）"""
    return self._last_events
```

#### 既存動作への影響

- `update()` の戻り値は変更なし
- 既存の print 文は維持（`Delayed Re-ID:` / `Delayed Re-ID timeout:`）
- `_last_events` はメモリ上のリストで、各 `update()` 呼び出しで最大数件程度のため負荷は無視できる

---

## 1.5 状態遷移

本案件では新しい状態遷移はない。CustomReID の状態遷移は feat-022 の設計書で定義済みであり、変更しない。

---

## 1.6 ファイル・ディレクトリ設計

### 入力ファイル

| パス | 内容 |
|------|------|
| `experiments/input/camSony1_L.mp4` | 長尺動画（321,239フレーム、30fps） |
| `experiments/results/camSony1_L_json/` | HALPE 26 JSON（321,239ファイル） |

### 出力ファイル

なし（標準出力のみ）。

---

## 1.7 インターフェース定義

### CustomReID クラス（変更箇所のみ）

```python
class CustomReID:
    @property
    def last_events(self) -> list[dict]:
        """直前の update() で発生したイベントのリスト。
        update() 呼び出しごとにリセットされる。
        """
        ...
```

### test_custom_reid_offline.py の新規関数

```python
def print_reid_report(
    reid_events: list[dict],
    reid: CustomReID,
    last_stable_ids: dict[int, int],
) -> None:
    """Re-IDイベントログと統計情報を出力する。

    Args:
        reid_events: 収集した全イベントのリスト
        reid: CustomReID インスタンス（最終状態の参照用）
        last_stable_ids: 最終フレームの update() 戻り値
    """
    ...
```

---

## 1.8 ログ・デバッグ設計

### 出力ポイント

| 出力 | レベル | 条件 | フォーマット |
|------|--------|------|-------------|
| 進捗ログ | INFO | `frame_idx % print_interval == 0` | `Processing frame {frame_idx:06d}/{total_frames} ({pct:.1f}%): ...` |
| Re-ID sim | DEBUG | `--no-sim-log` 未指定時 | `Re-ID sim: frame=NNNN ...`（既存、変更なし） |
| Delayed Re-ID | INFO | 遅延マッチ発動時 | `Delayed Re-ID: ...`（既存、変更なし） |
| Re-ID Event Log | INFO | 処理完了後 | `[type] frame={frame_idx:06d} ...` |
| Re-ID Statistics | INFO | 処理完了後 | 集計値 |

全て標準出力に出力する（logging モジュールは使用しない。既存の print ベースを維持）。
