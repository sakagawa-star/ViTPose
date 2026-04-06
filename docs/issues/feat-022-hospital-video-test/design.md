# feat-022 イテレーション2: カスタムRe-IDモジュール 機能設計書

## 1.1 対応要求マッピング

| 要求 ID | 設計セクション |
|---------|--------------|
| FR-001 | 1.4.1 頭部領域抽出 |
| FR-002 | 1.4.2 上半身領域抽出 |
| FR-003 | 1.4.3 HSV ヒストグラム計算 |
| FR-004 | 1.4.4 EMA 特徴量更新 |
| FR-005 | 1.4.5 Re-ID 判定 |
| FR-006 | 1.4.6 stable_id 状態管理 |
| FR-007 | 1.4.7 オフライン検証スクリプト |
| FR-008 | 1.4.8 Re-ID 遅延マッチ実験 |

---

## 1.2 システム構成

### モジュール構成

```
scripts/
├── custom_reid.py              # [新規] カスタム Re-ID モジュール
└── test_custom_reid_offline.py # [新規] オフライン検証スクリプト
```

`test_boxmot_offline.py`（既存）は変更しない。

### モジュール間の依存関係

```
test_custom_reid_offline.py
  ├── custom_reid.py          # CustomReID クラス
  └── boxmot.DeepOcSort       # トラッカー（既存環境）
```

`custom_reid.py` は他の scripts/ ファイルに依存しない（独立モジュール）。

---

## 1.3 技術スタック

| 技術 | バージョン | 用途 |
|------|-----------|------|
| Python | 3.10.16 | 実装言語 |
| uv | - | パッケージ管理（`uv run python` で実行） |
| NumPy | 2.2.6 | 特徴量計算・行列演算 |
| OpenCV (cv2) | 4.13.0.92 | HSV 変換・ヒストグラム計算・画像切り出し |
| BoxMOT | 16.0.11 | Deep OC-SORT トラッカー |

新規ライブラリは追加しない。

---

## 1.4 各機能の詳細設計

### 1.4.1 頭部領域抽出（FR-001）

#### データフロー

- 入力: `frame` (H, W, 3) uint8 BGR、`kpts` (26, 3) float32 [x, y, conf]
- 出力: `region` (h, w, 3) uint8 BGR または None

#### 処理ロジック

```
HEAD_INDICES = [0, 1, 2, 3, 4, 17, 18]  # Nose, LEye, REye, LEar, REar, Head, Neck
HEAD_EXPAND = 20  # px
H, W = frame.shape[:2]

visible = [kpts[i] for i in HEAD_INDICES if kpts[i][2] > 0.3]
if len(visible) == 0:
    return None

x1 = max(0, min(p[0] for p in visible) - HEAD_EXPAND)
y1 = max(0, min(p[1] for p in visible) - HEAD_EXPAND)
x2 = min(W, max(p[0] for p in visible) + HEAD_EXPAND)   # exclusive: numpy slice [y1:y2, x1:x2]
y2 = min(H, max(p[1] for p in visible) + HEAD_EXPAND)   # exclusive

if x2 <= x1 or y2 <= y1:
    return None

return frame[int(y1):int(y2), int(x1):int(x2)]
```

#### エラーハンドリング

- キーポイント座標が画面外（負値・画面サイズ超過）: clamp 処理で安全に切り出す
- 拡張後の幅・高さがゼロ: None を返す

---

### 1.4.2 上半身領域抽出（FR-002）

#### データフロー

- 入力: `frame` (H, W, 3) uint8 BGR、`kpts` (26, 3) float32
- 出力: `region` (h, w, 3) uint8 BGR または None

#### 処理ロジック

```
TORSO_INDICES = [5, 6, 11, 12]  # LShoulder, RShoulder, LHip, RHip
H, W = frame.shape[:2]

visible = [kpts[i] for i in TORSO_INDICES if kpts[i][2] > 0.3]
if len(visible) < 2:
    return None

x1 = max(0, min(p[0] for p in visible))
y1 = max(0, min(p[1] for p in visible))
x2 = min(W, max(p[0] for p in visible))   # exclusive: numpy slice [y1:y2, x1:x2]
y2 = min(H, max(p[1] for p in visible))   # exclusive
# visible が 2 点でも同一座標（肩が x 座標同一など）の場合は x2 <= x1 または y2 <= y1 となり None を返す
# すべての visible キーポイントが画面外（x > W）の場合:
#   max(0, min(xs)) = max(0, 画面外) → 0、min(W, max(xs)) = min(W, 画面外) = W → x2 > x1 となる
#   ただし座標が [0, W]×[0, H] の範囲を大幅に逸脱する場合は通常起きない（MMPose 出力の制約）

if x2 <= x1 or y2 <= y1:
    return None

return frame[int(y1):int(y2), int(x1):int(x2)]
```

#### エラーハンドリング

- キーポイント座標が画面外（負値・画面サイズ超過）: clamp 処理（`max(0, ...)` / `min(W, ...)`）で安全に切り出す
- visible が 2 点でも同一座標（一直線に並ぶ）場合: x2 <= x1 または y2 <= y1 となり None を返す

---

### 1.4.3 HSV ヒストグラム計算（FR-003）

#### データフロー

- 入力: `region` (h, w, 3) uint8 BGR または None
- 出力: `hist` (68,) float32 正規化済み または None

#### 処理ロジック

```
if region is None:
    return None

hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

h_hist = cv2.calcHist([hsv], [0], None, [36], [0, 180])  # shape (36, 1)
s_hist = cv2.calcHist([hsv], [1], None, [32], [0, 256])  # shape (32, 1)

hist = np.concatenate([h_hist.flatten(), s_hist.flatten()])  # shape (68,)
total = hist.sum()

if total < 1e-6:
    return None

hist = hist / total  # 正規化（合計 1.0）
return hist.astype(np.float32)
```

#### 設計判断

- **V チャネル除外**: 採用。病室の照明変化（日照変化、医療機器の光）による輝度変動の影響を避けるため。
- **ビン数 H=36, S=32**: 採用。H の 36 ビンは 5 度単位（0-180 の範囲を 36 分割）。S の 32 ビンは色の鮮やかさを十分に表現できる解像度。計算量と識別精度のバランスを考慮した。
- **mask=None**: 採用。FR-001/002 で切り出した領域画像全体をヒストグラム対象とするため、さらなるマスキングは不要。

---

### 1.4.4 EMA 特徴量更新（FR-004）

#### データフロー

- 入力: `current: PersonFeature | None`、`new_frame: PersonFeature`
- 出力: `updated: PersonFeature`

#### PersonFeature データクラス定義

```python
from dataclasses import dataclass

@dataclass
class PersonFeature:
    head_hist: np.ndarray | None   # shape=(68,) float32 または None
    torso_hist: np.ndarray | None  # shape=(68,) float32 または None
```

#### 処理ロジック（PersonFeature レベルで適用）

```python
ALPHA = 0.1

def _ema_single(current_h: np.ndarray | None, new_h: np.ndarray | None) -> np.ndarray | None:
    if current_h is None:
        return new_h      # 初回: 新フレームをそのまま使用
    if new_h is None:
        return current_h  # 部位が見えない: 既存 EMA を維持
    return ALPHA * new_h + (1.0 - ALPHA) * current_h

def _ema_update(current: PersonFeature | None, new_frame: PersonFeature) -> PersonFeature:
    current_head = current.head_hist if current is not None else None
    current_torso = current.torso_hist if current is not None else None
    return PersonFeature(
        head_hist=_ema_single(current_head, new_frame.head_hist),
        torso_hist=_ema_single(current_torso, new_frame.torso_hist),
    )
```

---

### 1.4.5 Re-ID 判定（FR-005）

#### データフロー

- 入力: `feature: PersonFeature`、`disappeared: dict[int, PersonFeature]`
- 出力: `matched_stable_id: int | None`

#### 処理ロジック

```
SIM_THRESHOLD = 0.3

def _compute_similarity(f1: PersonFeature, f2: PersonFeature) -> float:
    sims = []
    if f1.head_hist is not None and f2.head_hist is not None:
        sims.append(float(np.minimum(f1.head_hist, f2.head_hist).sum()))
    if f1.torso_hist is not None and f2.torso_hist is not None:
        sims.append(float(np.minimum(f1.torso_hist, f2.torso_hist).sum()))
    if len(sims) == 0:
        return 0.0
    return sum(sims) / len(sims)

def _match(self, feature: PersonFeature) -> int | None:
    # _disappeared はインスタンス変数を参照する
    disappeared = self._disappeared
    if len(disappeared) == 0:
        return None  # 新規人物

    if len(disappeared) == 1:
        # 消去法
        stable_id, feat = next(iter(disappeared.items()))
        sim = _compute_similarity(feature, feat)
        return stable_id if sim > SIM_THRESHOLD else None

    # 2 件以上: 最高類似度を選択（同点時は stable_id 最小を優先）
    best_id, best_sim = None, 0.0
    for stable_id, feat in disappeared.items():
        sim = _compute_similarity(feature, feat)
        # sim > best_sim: より高い類似度を優先
        # sim == best_sim: 同点時は stable_id が小さい方を優先（要求仕様 FR-005 同点処理）
        # best_id is not None: best_sim == 0.0 で未設定の場合はスキップ（最終判定で棄却されるため）
        if sim > best_sim or (sim == best_sim and best_id is not None and stable_id < best_id):
            best_sim = sim
            best_id = stable_id
    return best_id if best_sim > SIM_THRESHOLD else None
```

#### 設計判断

- **類似度閾値 0.3**: 採用。ヒストグラム交差で 0.3 は「ある程度の色の一致」を要求する閾値。完全に異なる色の人物は 0.1 未満になることが多い。調整が必要な場合はコンストラクタ引数で変更可能にする。
- **消去法の採用**: 採用。病室は最大 2〜3 人であり、消失 ID が 1 件のみのケースが多い。消去法を使うことで、特徴量が曖昧な場合（布団で全身遮蔽など）でも正しく再同定できる。

---

### 1.4.6 stable_id 状態管理（FR-006）

#### 状態変数（CustomReID クラスのインスタンス変数）

```python
_active_features: dict[int, PersonFeature]  # track_id -> EMA 特徴量
_active_stable: dict[int, int]              # track_id -> stable_id
_disappeared: dict[int, PersonFeature]       # stable_id -> EMA 特徴量（無制限保持）
_prev_track_ids: set[int]                   # 前フレームの track_id 集合
_next_stable_id: int                        # 次に割り当てる stable_id（1 始まり）
```

**設計判断: 消失 ID の保持期間**: 無制限（1セッション中は削除しない）。マッチして再同定された時点でのみ `_disappeared` から除去する。
- **採用理由**: 病室の人数は最大 2〜3 人であり、1時間セッション中に蓄積される消失 ID は数件程度。メモリ問題は発生しない。タイムアウトを設けると 1 分以上の見切れで再同定できなくなる。
- **却下案**: `MAX_DISAPPEARED_AGE` によるタイムアウト削除。見切れ要件「最低 1 分」に反するため却下。

#### フレームごとの処理ロジック

```
# 注: 以下の擬似コードでは self. を省略している。実装ではすべてのインスタンス変数参照に self. を付ける。
def update(frame, track_ids, keypoints_map) -> dict[int, int]:
    # keypoints_map: {track_id: np.ndarray shape=(26,3) [x,y,conf]} または {track_id: None}

    curr = set(track_ids)
    prev = _prev_track_ids
    # 境界条件: track_ids が空リスト（0人検出）の場合
    # curr = set() → lost_ids = prev（前フレームの全 track_id が消失）、new_ids = set()、existing_ids = set()
    # 全 track_id が _disappeared へ移動し、戻り値は空辞書 {} を返す

    lost_ids = prev - curr
    new_ids = curr - prev
    existing_ids = curr & prev
    # 前提: lost_ids と new_ids に同一 track_id が同時に含まれることはない
    # （Deep OC-SORT の仕様上、一度削除された track_id は再利用されない）
    # new_ids を sorted() でソートし track_id の数値昇順にイテレーションする。
    # 複数の new_ids が同一 stable_id にマッチしようとした場合、数値最小の track_id を優先する。

    # 処理順序の理由: ステップ1（消失）をステップ2（新規）より先に実行する。
    # 理由: ステップ2の _match() が _disappeared を参照するため、消失 ID を先に移動しておく必要がある。
    # ステップ1→2→3の順序を変えてはならない。

    # 1. 消失した ID を disappeared へ移動
    for tid in lost_ids:
        sid = _active_stable[tid]
        _disappeared[sid] = _active_features[tid]
        del _active_stable[tid]
        del _active_features[tid]

    # 2. 新しい ID に stable_id を割り当て（数値昇順で処理: 同一 stable_id への競合時は最小 track_id が優先）
    for tid in sorted(new_ids):
        kpts = keypoints_map.get(tid)
        if kpts is not None:
            head_region = _extract_head(frame, kpts)
            torso_region = _extract_torso(frame, kpts)
            new_feat = PersonFeature(
                head_hist=_compute_hist(head_region),
                torso_hist=_compute_hist(torso_region),
            )
        else:
            new_feat = PersonFeature(head_hist=None, torso_hist=None)

        # 境界ケース: kpts が有効だが全キーポイントの confidence <= 0.3 の場合
        # PersonFeature は (head_hist=None, torso_hist=None) となり、
        # _match() は類似度 0.0 を返し新規 stable_id が発番される
        matched_sid = _match(new_feat)  # _disappeared はインスタンス変数を参照
        if matched_sid is not None:
            sid = matched_sid
            del _disappeared[matched_sid]  # 即座に削除することで後続の new_id が同一 stable_id に二重マッチするのを防ぐ
        else:
            sid = _next_stable_id
            _next_stable_id += 1

        _active_stable[tid] = sid
        _active_features[tid] = new_feat

    # 3. 継続する ID の EMA 更新
    for tid in existing_ids:
        kpts = keypoints_map.get(tid)
        if kpts is not None:
            head_region = _extract_head(frame, kpts)
            torso_region = _extract_torso(frame, kpts)
            new_feat = PersonFeature(
                head_hist=_compute_hist(head_region),
                torso_hist=_compute_hist(torso_region),
            )
        else:
            new_feat = PersonFeature(head_hist=None, torso_hist=None)
        _active_features[tid] = _ema_update(_active_features[tid], new_feat)

    _prev_track_ids = curr
    return dict(_active_stable)
    # 前提: keypoints_map のキー集合は track_ids と一致する（呼び出し元が保証）
    # 一致しない場合は .get(tid) で None を返すため EMA 維持となる（KeyError は発生しない）
```

---

### 1.4.7 オフライン検証スクリプト（FR-007）

#### ファイルパス

`scripts/test_custom_reid_offline.py`

#### CLI インターフェース

```
usage: test_custom_reid_offline.py --video VIDEO --json-dir JSON_DIR [--device DEVICE]

arguments:
  --video      動画ファイルパス（必須）
  --json-dir   HALPE 26 OpenPose JSON ディレクトリ（必須）
  --device     BoxMOT デバイス（デフォルト: cuda:0）
```

#### データフロー

```
JSON_DIR/*.json ──→ load_data() ──→ json_data (dict[int, list[dict]])
video フレーム

# 欠番補完付きフレームループ
# json_data のキー（frame_idx）と動画フレームを辞書引きで対応させる
frame_idx = 0
while cap.read() → frame:
    json_people = json_data.get(frame_idx, [])  # 欠番 or 動画フレーム超過 → []（0人）
    frame_idx += 1

    json_people ──→ dets (N, 6) [x1,y1,x2,y2,conf,class_id=0] ──→ DeepOcSort.update(dets, frame) ──→ tracks (M, 7)
    tracks ──→ track_ids, tracked_bboxes {track_id: bbox_xyxy}
    tracked_bboxes + json_people ──→ match_by_iou() ──→ keypoints_map {track_id: kpts}
    frame + track_ids + keypoints_map ──→ CustomReID.update() ──→ {track_id: stable_id}

    # dets 構築
    if len(json_people) > 0:
        dets = np.array([
            [p['bbox'][0], p['bbox'][1], p['bbox'][2], p['bbox'][3], p['bbox_score'], 0]
            for p in json_people
        ], dtype=np.float32)  # shape (N, 6): [x1, y1, x2, y2, conf, class_id=0(人物)]
    else:
        dets = np.empty((0, 6), dtype=np.float32)

    # tracks → tracked_bboxes 変換
    # tracks shape (M, 7): [x1, y1, x2, y2, track_id, conf, class_id]
    tracked_bboxes = {int(t[4]): t[:4].tolist() for t in tracks}
    track_ids = list(tracked_bboxes.keys())
```

#### JSON 読み込み形式

HALPE 26 OpenPose JSON（`halpe26_to_openpose.py` 出力形式）:

```json
{
  "version": 1.3,
  "people": [
    {
      "person_id": [-1],
      "pose_keypoints_2d": [x0,y0,c0, x1,y1,c1, ..., x25,y25,c25],
      "bbox_score": 0.95,
      "bbox": [x1, y1, x2, y2]
    }
  ]
}
```

- `pose_keypoints_2d`: 長さ 78 のフラット配列 → reshape(26, 3)
- `bbox`: xyxy 形式

#### トラッカー出力の bbox とキーポイントの対応付け（match_by_iou）

BoxMOT の `tracker.update()` 出力 `tracks` は shape (M, 7): `[x1, y1, x2, y2, track_id, conf, class_id]`。
入力した検出 bbox（JSON）と 1:1 対応していない場合があるため、IoU でマッチングする。

**設計前提（多対1マッチング）**: 病室の検出人数は最大 2〜3 人のため、複数の track_id が同一 JSON 人物にマッチすることは稀。1:1 対応の強制（ハンガリアン法等）は行わない。同一 JSON 人物が複数の track_id にマッチした場合は、それぞれの track_id に同一キーポイントを割り当てる（重複あり）。

```python
def match_by_iou(tracked_bboxes, json_people) -> dict[int, ndarray | None]:
    # tracked_bboxes: {track_id: [x1,y1,x2,y2]}
    # json_people: list of {bbox: [x1,y1,x2,y2], kpts: ndarray(26,3)}
    # 戻り値: {track_id: kpts(26,3) or None}

    keypoints_map: dict[int, np.ndarray | None] = {}

    if len(json_people) == 0:
        return {tid: None for tid in tracked_bboxes}

    for track_id, bbox in tracked_bboxes.items():
        best_iou, best_kpts = 0.0, None
        for person in json_people:
            iou = compute_iou(bbox, person['bbox'])
            if iou > best_iou:
                best_iou = iou
                best_kpts = person['kpts']
        # 閾値判定はループ外で一度だけ行う。
        # ループ内で早期フィルタ（if iou >= iou_threshold）してはならない。
        # 理由: 全候補の最大 IoU を正確に記録してから判定する必要があるため。
        keypoints_map[track_id] = best_kpts if best_iou >= iou_threshold else None

    return keypoints_map
```

IoU 閾値のデフォルト値 0.5 は `match_by_iou` の関数引数 `iou_threshold` として定義する（定数としてのハードコードは行わない）。IoU < `iou_threshold` の場合はキーポイントが取得できないため、そのフレームの特徴量更新をスキップ（EMA 維持）。

**設計判断: IoU 閾値 0.5**: 採用。PASCAL VOC の物体検出評価基準で標準的に使われる閾値であり、同一人物の BB が十分重なっていることを保証する。CLI 引数への露出は行わない（検証段階では固定値で十分。調整が必要な場合は関数引数で変更可能）。

#### Deep OC-SORT の Re-ID 無効化

BoxMOT 16.0.11 の `DeepOcSort` に `w_association_emb=0.0` を渡すことで Re-ID の重みをゼロにする。

`reid_path` はプロジェクトルート直下の `osnet_x0_25_msmt17.pt` をハードコードする（`test_boxmot_offline.py` と同一）:
```python
reid_path = Path(__file__).resolve().parent.parent / "osnet_x0_25_msmt17.pt"
```

```python
try:
    tracker = DeepOcSort(
        reid_weights=reid_path,
        device=args.device,
        half="cuda" in args.device,
        max_age=30,
        w_association_emb=0.0,  # 内蔵 Re-ID を無効化
    )
except TypeError:
    print("WARNING: w_association_emb not supported, falling back without it")
    tracker = DeepOcSort(
        reid_weights=reid_path,
        device=args.device,
        half="cuda" in args.device,
        max_age=30,
    )
```

**設計判断**: feat-022 イテレーション1では `w_association_emb` を 0.5〜0.9 で変化させても Re-ID の結果が変わらなかった。0.0 に設定することで Re-ID のコストを完全にゼロにし、IoU + Kalman のみで追跡させる。コンストラクタが `w_association_emb` を受け付けない場合は、`scripts/test_boxmot_offline.py` と同じ初期化方法を使い、Re-ID 部分は内部的に無効化されているものとして扱う（`osnet_x0_25_msmt17.pt` は引き続き初期化に必要）。

#### 標準出力フォーマット

```
Processing frame 0000: track_ids=[2], stable_ids={2: 1}
Processing frame 0010: track_ids=[2], stable_ids={2: 1}
...（frame_idx % 10 == 0 のフレームで出力。最終フレームが 10 の倍数でない場合、追加出力は行わない）...
Processing frame 0890: track_ids=[7], stable_ids={7: 1}

=== Re-ID Summary ===
Total frames: 900
Stable ID counts: {1: 704}
Unique stable IDs: 1
Processing time: X.X sec (XXX.X fps)
```

---

### 1.4.8 Re-ID 遅延マッチ実験（FR-008）

#### CustomReID への追加（custom_reid.py）

読み取り専用プロパティを2つ追加する。既存メソッドの変更なし。

```python
@property
def active_features(self) -> dict[int, PersonFeature]:
    """アクティブな track_id → EMA 特徴量（読み取り専用）"""
    return self._active_features

@property
def disappeared(self) -> dict[int, PersonFeature]:
    """消失した stable_id → EMA 特徴量（読み取り専用）"""
    return self._disappeared
```

#### test_custom_reid_offline.py への追加

メインループに以下のログ出力を追加する。CustomReID.update() の呼び出し前後に実行する。

##### 状態管理

```python
# メインループ外で初期化（メインループ内で毎フレーム上書きされるが、
# 型ヒント明示のために宣言しておく）
recently_appeared: dict[int, int] = {}  # {track_id: 出現フレーム番号}
snapshot_disappeared: dict[int, PersonFeature] = {}
```

##### メインループ内の処理

```python
# CustomReID.update() の直前で消失IDをスナップショット
# 理由: update() 内で消失IDが _disappeared に移動・削除されるため、
#        update() 後の _disappeared は更新後の状態。
#        比較対象として update() 前の消失ID特徴量を保持する必要がある。
snapshot_disappeared = dict(reid.disappeared)

# CustomReID.update() 呼び出し
stable_ids = reid.update(frame, track_ids, keypoints_map)

# 新規出現 track_id を記録
for tid in track_ids:
    if tid not in recently_appeared:
        recently_appeared[tid] = frame_idx

# 消失した track_id を recently_appeared から除去
disappeared_tids = set(recently_appeared.keys()) - set(track_ids)
for tid in disappeared_tids:
    del recently_appeared[tid]

# 類似度ログ出力
for tid, appear_frame in recently_appeared.items():
    offset = frame_idx - appear_frame
    current_feat = reid.active_features.get(tid)
    if current_feat is None:
        continue
    for sid, dis_feat in snapshot_disappeared.items():
        # このtidに割り当てられたstable_idと同じsidはスキップ
        # （自分自身との比較は無意味）
        if stable_ids.get(tid) == sid:
            continue
        sim = reid._compute_similarity(current_feat, dis_feat)
        print(
            f"Re-ID sim: frame={frame_idx:04d} offset={offset:02d} "
            f"track_id={tid} disappeared_sid={sid} sim={sim:.3f}"
        )
```

#### 設計判断

- **スナップショット方式**: 採用。update() 内で _disappeared が変更されるため、update() 前の状態を保持する必要がある。ディープコピーではなく dict() による浅いコピーで十分。`_ema_update` は新しい `PersonFeature` インスタンスを返す仕様（1.4.4 参照）のため、既存オブジェクトのフィールドがインプレース変更されることはなく、浅いコピーで安全。
- **_compute_similarity の外部呼び出し**: 採用。本来プライベートメソッドだが、実験用スクリプトでの一時的な使用として許容する。公開メソッド化は行わない（実験終了後に除去する可能性があるため）。
- **全期間ログ出力**: 採用。track_id がアクティブな全期間にわたり毎フレームのログを出力する（類似度の経時変化を観察するため）。大量出力になるが、実験用途のため許容する。出力の絞り込みが必要な場合は grep 等で offset をフィルタする。
- **snapshot_disappeared からの自己比較除外**: 採用。マッチ成功した場合のみ除外する。マッチ失敗した消失 ID は引き続き比較対象として類似度を出力する（遅延マッチの可能性を観察するため）。`stable_ids.get(tid) == sid` で除外する。

---

## 1.5 状態遷移

### stable_id の状態遷移

```
[初期状態]
  → （新 track_id 出現 & 消失 ID なし）→ [アクティブ: 新 stable_id 発番]
  → （新 track_id 出現 & 消失 ID あり & 類似度 > 0.3）→ [アクティブ: 既存 stable_id 引き継ぎ]
  → （新 track_id 出現 & 消失 ID あり & 類似度 ≤ 0.3）→ [アクティブ: 新 stable_id 発番]

[アクティブ]
  → （同 track_id が次フレームにも存在）→ [アクティブ: EMA 更新]
  → （track_id が次フレームに消える）→ [消失]

[消失]
  → （対応する stable_id が新 track_id にマッチ）→ [アクティブ: stable_id 引き継ぎ]
  → （消失のまま次の新 track_id が別の stable_id にマッチ）→ [消失: 継続]
  → （セッション終了）→ [削除（セッション内は無制限保持）]
```

不正遷移の扱い:
- 同一 track_id が消失状態から直接アクティブに復帰することはない（Deep OC-SORT は必ず新しい track_id を割り当てる）
- 同一 stable_id が複数の track_id に割り当てられることはない（Re-ID マッチ後に `_disappeared` から削除するため）

---

## 1.6 ファイル・ディレクトリ設計

### 新規作成ファイル

| ファイル | 説明 |
|---------|------|
| `scripts/custom_reid.py` | CustomReID クラス、PersonFeature データクラス |
| `scripts/test_custom_reid_offline.py` | オフライン検証スクリプト |

### 使用する既存ファイル（変更なし）

| ファイル | 用途 |
|---------|------|
| `osnet_x0_25_msmt17.pt` | DeepOcSort の Re-ID 重みファイル（Re-ID は無効化するが初期化に必要） |
| `testdata/camSony1_S.mp4` | 検証用動画 |
| `experiments/results/camSony1_S_json/` | 検証用 HALPE 26 JSON（既存） |

---

## 1.7 インターフェース定義

### custom_reid.py

```python
@dataclass
class PersonFeature:
    head_hist: np.ndarray | None   # shape=(68,) float32 または None
    torso_hist: np.ndarray | None  # shape=(68,) float32 または None

class CustomReID:
    def __init__(
        self,
        alpha: float = 0.1,
        sim_threshold: float = 0.3,
        kpt_conf_thr: float = 0.3,
        head_expand_px: int = 20,
        # インスタンス変数の初期値:
        #   _active_features: {}、_active_stable: {}、_disappeared: {}
        #   _prev_track_ids: set()、_next_stable_id: 1
    ) -> None: ...

    def update(
        self,
        frame: np.ndarray,          # (H, W, 3) uint8 BGR
        track_ids: list[int],       # Deep OC-SORT のアクティブ track_id 一覧
        keypoints_map: dict[int, np.ndarray | None],
        # {track_id: kpts(26,3) or None}
    ) -> dict[int, int]:            # {track_id: stable_id}
        ...
```

内部ヘルパーメソッド（公開しない）:

```python
    def _extract_head(self, frame, kpts) -> np.ndarray | None: ...
    def _extract_torso(self, frame, kpts) -> np.ndarray | None: ...
    def _compute_hist(self, region) -> np.ndarray | None: ...
    def _ema_update(self, current, new_frame) -> PersonFeature: ...
    def _compute_similarity(self, f1, f2) -> float: ...
    def _match(self, feature) -> int | None: ...

    @property
    def active_features(self) -> dict[int, PersonFeature]: ...
    @property
    def disappeared(self) -> dict[int, PersonFeature]: ...
```

### test_custom_reid_offline.py

```python
def load_data(json_dir: str) -> dict[int, list[dict]]:
    """JSON ディレクトリから全フレームの人物データを読み込む。
    Returns:
        {frame_idx: list[dict]}
        # キー: ファイル名末尾の6桁数値（frame_idx）を int に変換したもの
        # 値: その frame_idx の人物リスト。各人物は以下を持つ:
        #   bbox: list[float] xyxy 形式
        #   bbox_score: float
        #   kpts: np.ndarray shape=(26, 3) [x, y, conf]
        # 欠番フレームはキーに含まれない。main() で [] として補完する。
    frame_idx 抽出方法:
        ファイル名末尾の正規表現 `r'_(\d{6})\.json$'` で抽出する（6桁固定）。
        根拠: `halpe26_to_openpose.py` は `{:06d}` フォーマットで出力するため6桁固定。
        例: `camSony1_S_000042.json` → frame_idx = 42
        例: `cam05520125_000042.json` → frame_idx = 42（数字を含む video_name でも正しく末尾6桁を抽出する）
        注意: video_name 自体が6桁数字で終わる場合（例: `video_123456_000042.json`）も正しく動作する。
              `r'_(\d{6})\.json$'` は**末尾**の6桁にマッチするため。
    エラーハンドリング:
        - JSON ファイル 0 件: エラーメッセージ出力 + sys.exit(1)
        - 個別 JSON の json.JSONDecodeError: WARNING を出力し、そのフレームの people を [] として扱う
        - pose_keypoints_2d が 78 要素でない: WARNING を出力し、その人物をスキップ
        - bbox フィールドなし: WARNING を出力し、その人物をスキップ
        - bbox_score フィールドなし: WARNING を出力し、その人物をスキップ
    """

def match_by_iou(
    tracked_bboxes: dict[int, list[float]],
    json_people: list[dict],
    iou_threshold: float = 0.5,
    # IoU 閾値 0.5 は暫定値。必要に応じて呼び出し時に変更可能だが、CLI 引数には露出しない
) -> dict[int, np.ndarray | None]:
    """トラッカー出力 bbox と JSON 人物のキーポイントを IoU でマッチング。
    返り値のキー集合は tracked_bboxes と同一のキー集合を持つ（呼び出し元に保証を提供）。
    """

def compute_iou(bbox1: list[float], bbox2: list[float]) -> float:
    """xyxy 形式の bbox の IoU を計算する。
    処理:
        ix1 = max(bbox1[0], bbox2[0])
        iy1 = max(bbox1[1], bbox2[1])
        ix2 = min(bbox1[2], bbox2[2])
        iy2 = min(bbox1[3], bbox2[3])
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        area1 = (bbox1[2]-bbox1[0]) * (bbox1[3]-bbox1[1])
        area2 = (bbox2[2]-bbox2[0]) * (bbox2[3]-bbox2[1])
        union = area1 + area2 - inter
        return inter / union if union > 0 else 0.0
    """

def main() -> None: ...
```

---

## 1.8 ログ・デバッグ設計

すべてのログは `print()` で標準出力に出力する。`logging` モジュールは使用しない。WARNING / ERROR のプレフィックスは手動で付与する（例: `print("WARNING: ...")`、`print("ERROR: ...")`）。

- **INFO**: 10 フレームごとに `frame_idx, track_ids, stable_ids` を出力
- **WARNING**: IoU が `iou_threshold`（デフォルト 0.5）**未満**の候補しかない場合にのみ出力（`Warning: no keypoints for track_id=X at frame Y`）。json_people が空（0人検出）の場合は出力しない。IoU = 0.5（`>= iou_threshold`）はマッチ成功とみなし WARNING を出力しない
- **INFO**: 最終サマリー（stable_id 数、フレーム数、処理速度）
- **DEBUG**: 再出現 track_id の類似度推移（`Re-ID sim: frame=NNNN offset=MM track_id=T disappeared_sid=S sim=X.XXX`）。毎フレーム出力。消失 ID が 0 件の場合は出力しない
- **ERROR**: JSON ファイルが見つからない場合、動画が開けない場合はエラーメッセージを出力して sys.exit(1)
