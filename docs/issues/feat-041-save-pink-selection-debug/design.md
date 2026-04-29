# feat-041 機能設計書: postprocess_pink_id.py に選択スコア診断フィールド追加

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001（bb_index 付与） | §4.1 |
| FR-002（iou_with_prev 付与） | §4.2 |
| FR-003（selection_score 付与） | §4.3 |
| FR-004（既存非変更） | §4.4 |
| NFR-001（パフォーマンス） | §6 / §4.2 |
| NFR-002（下流互換性） | §4.4 |

## 2. システム構成

### 2.1 モジュール構成

単一ファイル `scripts/postprocess_pink_id.py` のみを修正する。新規ファイルは作成しない。

```
scripts/postprocess_pink_id.py
├─ 定数（変更なし）
│   ├─ FIXED_HSV_RANGES
│   ├─ MIN_PINK_RATIO = 0.03
│   └─ IOU_CONT_WEIGHT = 0.05
├─ 純関数（変更なし）
│   ├─ compute_pink_ratio
│   ├─ compute_iou           ← 既存。本案件で再利用
│   ├─ clip_bbox
│   └─ select_pink_bbox
├─ I/O（変更なし）
│   ├─ load_json_frames
│   └─ write_json_frame
└─ main（pink_id 付与ループに数行追加のみ）
    └─ 各 person dict に bb_index / iou_with_prev / selection_score を代入
```

### 2.2 依存関係

- `compute_iou` は既存の純関数（`def compute_iou(...)` で定義、現行 L57 付近、参考）。本案件で再利用するのみで変更しない
- 追加 import なし

### 2.3 ディレクトリ構成

既存と同じ。新規ファイルは作成しない。

## 3. 技術スタック

| 項目 | 値 | 選定理由 |
|------|-----|----------|
| 言語 | Python 3.10.16 | プロジェクト既定 |
| パッケージ管理 | uv | プロジェクト既定 |
| OpenCV | 既存依存 | 変更なし |
| numpy | 既存依存 | 変更なし |

追加ライブラリの導入は行わない。

## 4. 各機能の詳細設計

### 4.1 FR-001: bb_index フィールドの付与

#### 4.1.1 データフロー

- 入力: 既存 `for i, person in enumerate(people):` ループの `i`
- 出力: 各 person dict に `bb_index: int`

#### 4.1.2 処理ロジック

現行 `scripts/postprocess_pink_id.py` の **`# pink_id / pink_ratio 付与` コメント直下のループ**（参考行: L252 付近）を改修対象とする。行番号は将来コード変更で陳腐化するため、コメントアンカーを正とする:

**修正前**:

```python
# pink_id / pink_ratio 付与
for i, person in enumerate(people):
    person["pink_id"] = 1 if i == sel_idx else -1
    person["pink_ratio"] = ratios[i]
```

**修正後**:

```python
# pink_id / pink_ratio / bb_index / iou_with_prev / selection_score 付与
for i, person in enumerate(people):
    person["pink_id"] = 1 if i == sel_idx else -1
    person["pink_ratio"] = ratios[i]
    person["bb_index"] = i
    iou = ious[i]
    person["iou_with_prev"] = iou
    person["selection_score"] = (
        None if iou is None else ratios[i] + IOU_CONT_WEIGHT * iou
    )
```

`ious: list[float | None]` は §4.2 で計算。コードスニペットは意図の伝達目的であり、実装時はインデント・周辺コードをファイルに合わせる。

#### 4.1.3 境界条件

- `people == []`: ループが空回りし `bb_index` は何も書かれない（既存の `pink_id` / `pink_ratio` も書かれないのと同じ挙動）
- `bbox` 欠損 person: AC-001-3 の通り、ループは継続するため `bb_index` は付与される（pink_id / pink_ratio と同様）

### 4.2 FR-002: iou_with_prev フィールドの付与

#### 4.2.1 データフロー

- 入力:
  - `bboxes: list[tuple[int, int, int, int] | None]`（既存。bbox 欠損は None）
  - `prev_selected_bbox_for_iou: tuple[int, int, int, int] | None`（current_prev、§4.2.2 参照）
- 中間: `ious: list[float | None]`、`people` と同長
- 出力: 各 person dict に `iou_with_prev: float | None`

#### 4.2.2 処理ロジック

`select_pink_bbox` 呼び出し直後（`sel_idx = select_pink_bbox(...)` の次行）かつ **pink_id 付与ループより前**に IoU リストを構築する。重要ポイント: 「現フレームの IoU 計算で参照すべき前フレーム選択 BB」は `select_pink_bbox` に渡された時点の `prev_selected_bbox` の値であり、コードブロック末尾の `prev_selected_bbox = selected_bbox` で**現フレーム**の選択 BB に上書きされる前の値。本案件の追加コードは上書き処理より前に置かれるため、自然に正しい値を参照できる。

**追加ロジック**:

```python
sel_idx = select_pink_bbox(bboxes, ratios, prev_selected_bbox)

# IoU 計算（現フレームのスコア計算で参照した prev_selected_bbox を使う）
ious: list[float | None] = []
for bb in bboxes:
    if bb is None or prev_selected_bbox is None:
        ious.append(None)
    else:
        ious.append(compute_iou(prev_selected_bbox, bb))

# pink_id / pink_ratio / bb_index / iou_with_prev / selection_score 付与
for i, person in enumerate(people):
    person["pink_id"] = 1 if i == sel_idx else -1
    person["pink_ratio"] = ratios[i]
    person["bb_index"] = i
    person["iou_with_prev"] = ious[i]
    person["selection_score"] = (
        None if ious[i] is None
        else ratios[i] + IOU_CONT_WEIGHT * ious[i]
    )
```

その後の `prev_selected_bbox = ...` 更新ブロック（`# 統計・前フレーム状態更新` コメント直下、参考行 L262 付近）は変更しない。次フレームに進む前に `prev_selected_bbox` が更新されるが、本フレームの `ious` は既に計算済みなので影響なし。

#### 4.2.3 設計判断の記録（ADR）

- **採用案: 連続性切れ時 = `null`**: 「前 BB あり & IoU=0」と「前 BB なし」の区別を保持。後段で誤選択が連続性切れ起因かを判別可能
- **却下案: `iou_with_prev = 0.0` で代用**: 上記区別が不可能になるため却下
- **`compute_iou` を流用**: 既存の純関数で計算式は `select_pink_bbox` 内で使われているものと完全一致。本案件で計算式の独自実装はしない

#### 4.2.4 境界条件

- `prev_selected_bbox is None`（連続性切れ）: 全 `ious[i] = None`
- `bboxes[i] is None`（bbox 欠損）: `ious[i] = None`
- 両者が共に成立: `ious[i] = None`（どちらの優先順位でも結果は同じ）
- 両 BB が完全一致: IoU = 1.0
- 両 BB が完全に離れている: IoU = 0.0

#### 4.2.5 パフォーマンス影響

`compute_iou` は単純な算術演算（10 行未満、numpy 不使用）。1 BB 1 フレームあたり数 μs オーダー。camSony1_L で総 BB 数 100 万強 → 追加コストは数秒以内で NFR-001 の 20% 以内に余裕で収まる見込み。

### 4.3 FR-003: selection_score フィールドの付与

#### 4.3.1 データフロー

- 入力: `ratios[i]: float`、`ious[i]: float | None`、定数 `IOU_CONT_WEIGHT`
- 出力: 各 person dict に `selection_score: float | None`

#### 4.3.2 処理ロジック

§4.2.2 のコードスニペットに含まれる:

```python
person["selection_score"] = (
    None if ious[i] is None
    else ratios[i] + IOU_CONT_WEIGHT * ious[i]
)
```

#### 4.3.3 計算式の整合性

`select_pink_bbox` 関数（`def select_pink_bbox(...)` で定義、参考行 L86 付近）内の選択判定式:

```python
score = ratios[i] + IOU_CONT_WEIGHT * compute_iou(prev_selected_bbox, bboxes[i])
```

と完全に一致する。AC-003-4 の「`pink_id == 1` の人物の `selection_score` が同フレーム全 BB の中で最大値」は、`select_pink_bbox` の `argmax` 挙動と本フィールドの計算が同一式であることから自明に成立。

#### 4.3.4 境界条件

- `ious[i] is None`: `selection_score = None`
- `ratios[i] = 0.0` かつ `ious[i] = 0.0`: `selection_score = 0.0`
- `ratios[i] = 1.0` かつ `ious[i] = 1.0`: `selection_score = 1.05`（理論上の最大値）

### 4.4 FR-004: 既存フィールド・ロジックの非変更

#### 4.4.1 不変事項

以下は本案件で一切変更しない:

- CLI 引数: `--video`, `--json-dir`, `--out-dir`
- 出力ディレクトリの上書き防止チェック（`os.path.realpath` 比較ブロック、参考行 L178 付近）
- サマリ出力（`# サマリ` コメント直下のブロック、参考行 L289 付近、feat-039 の AC-003-3 で列挙した 7 項目）
- `select_pink_bbox` の選択ロジックと 3 つの定数
- `pink_id` の値規約（選択 = 1 / 非選択 = -1）
- `pink_ratio` の値規約（feat-039 で追加した float、値域 [0.0, 1.0]、bbox 欠損は 0.0）
- `prev_selected_bbox` の更新ロジック（`# 統計・前フレーム状態更新` コメント直下のブロック、参考行 L262 付近）
- 既存フィールド（`person_id`, `bbox`, `pose_keypoints_2d`, `bbox_score`, `stable_id` 等）の書き戻しスルー（生 dict 保持設計）

#### 4.4.2 下流互換性の確認

- feat-035 `postprocess_track.py`: `track_id` のみ追加。本案件の追加フィールドは無視される
- feat-036 `postprocess_patient_id.py`: `pink_id` / `track_id` のみ参照。追加フィールドは無視
- feat-037 `plot_pink_track_timeline.py`: `pink_track_id` ベース。追加フィールドは無視
- feat-038 `visualize_patient_video.py`: `pink_id` / `pink_track_id` / `track_id` / `bbox_score` を参照。追加フィールドは無視
- feat-040 `plot_pink_ratio_timeline.py`: `pink_id` / `pink_ratio` のみ参照。追加フィールドは無視

#### 4.4.3 既存挙動との等価性確認方法

実装後の検証で、改修前と改修後の出力 JSON について以下を比較する:

1. `pink_id == 1` の (frame_idx, bbox) ペアが完全一致
2. `pink_ratio` の値が完全一致（浮動小数点誤差含めず厳密一致のはず。同一計算式 + 同一入力）

## 5. ファイル・ディレクトリ設計

### 5.1 出力 JSON スキーマ（改修後、1 人物エントリの抜粋）

```json
{
  "person_id": [-1],
  "pose_keypoints_2d": [/* 26 * 3 = 78 float */],
  "bbox": [x1, y1, x2, y2],
  "bbox_score": 0.912,
  "pink_id": 1,
  "pink_ratio": 0.147,
  "bb_index": 0,
  "iou_with_prev": 0.823,
  "selection_score": 0.18815
}
```

連続性切れフレームの例:

```json
{
  ...,
  "pink_id": 1,
  "pink_ratio": 0.147,
  "bb_index": 0,
  "iou_with_prev": null,
  "selection_score": null
}
```

bbox 欠損 person の例:

```json
{
  ...,
  "pink_id": -1,
  "pink_ratio": 0.0,
  "bb_index": 2,
  "iou_with_prev": null,
  "selection_score": null
}
```

### 5.2 入出力パス

既存と同じ。ファイル命名規約（`*_{6 桁フレーム番号}.json`）も変更しない。

## 6. ログ・デバッグ設計

### 6.1 既存ログ

進捗表示・サマリ・WARNING は変更しない。

### 6.2 追加ログ

なし。本案件で新規ログは出さない。

### 6.3 事後確認の指針（実装者向けガイド）

実装後に以下を確認する:

1. camSony1_S（軽量、約 445 フレーム）で実行し、出力 JSON の任意 1 フレームを目視:
   - 全 `people[i]` に `bb_index` / `iou_with_prev` / `selection_score` の 3 キーが存在
   - 連続性切れフレーム（典型的に 1 フレーム目）で `iou_with_prev = null`、`selection_score = null`
2. `pink_id == 1` の人物について `selection_score == pink_ratio + 0.05 × iou_with_prev` が等式成立（浮動小数点誤差を除く）
3. 改修前後で `pink_id == 1` の (frame, bb_index) 集合が一致（`bb_index` は本案件で初めて付くが、改修前の `enumerate(people)` 順序と同一なので `i` で代用可能）
4. NFR-001 の確認: camSony1_L で処理時間が改修前の 120% 以内

## 7. インターフェース定義

### 7.1 公開関数の変更

なし。既存関数のシグネチャは一切変更しない。

### 7.2 モジュール間の呼び出し方向

変更なし。単一スクリプト内で完結。他モジュールへ import されない。

## 8. 設計判断の記録（全体 ADR サマリ）

- **CLI フラグ化しない**: `--write-debug-fields` のような ON/OFF フラグを設けず常時書き込み。理由は feat-039 と同じ（計算コスト小、下流影響なし、デバッグ目的で常時欲しい情報）
- **連続性切れ時は null**: 「前 BB なし」と「IoU=0」を区別保持するため
- **`bb_index` を `postprocess_pink_id.py` で付与**: 上流（`run_halpe26_pipeline_yolo11.py`）への変更は影響範囲が広いため避ける。本スクリプトの `enumerate(people)` 順序と一致させればよい
- **`compute_iou` 既存関数を流用**: 計算式の独自実装は避ける。`select_pink_bbox` 内の式と完全に一致させる
- **`selection_score` の数式**: `pink_ratio + IOU_CONT_WEIGHT × iou_with_prev` で固定。`select_pink_bbox` の式と同一

## 9. 実装完了後のチェックリスト

- [ ] `scripts/postprocess_pink_id.py` の pink_id 付与ループ前後に IoU 計算と 3 フィールド代入を追加
- [ ] camSony1_S で実行し、出力 JSON の任意 1 フレームに 3 キーが存在することを確認
- [ ] 連続性切れフレーム（1 フレーム目など）で `iou_with_prev = null`、`selection_score = null` を確認
- [ ] `pink_id == 1` 人物の `selection_score == pink_ratio + 0.05 × iou_with_prev` 等式成立を確認
- [ ] 改修前後で `pink_id == 1` の (frame, bb_index) 集合が一致することを確認
- [ ] camSony1_L で処理時間が改修前の 120% 以内であることを確認
- [ ] `scripts/README.md` の `postprocess_pink_id.py` 記述に `bb_index` / `iou_with_prev` / `selection_score` の追加を反映
- [ ] CLAUDE.md の feat-041 エントリを完了済み案件として追記
- [ ] `docs/BACKLOG.md` の feat-041 を Closed テーブルに移動
- [ ] `docs/issues/feat-041-save-pink-selection-debug/README.md` のステータスを Closed に更新
