# feat-039 機能設計書: postprocess_pink_id.py に pink_ratio フィールド追加

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001（pink_ratio フィールドの付与） | §4.1 |
| FR-002（BB 欠損 person の値規約） | §4.2 |
| FR-003（既存フィールド・CLI の非変更） | §4.3 |
| NFR-001（パフォーマンス） | §4.1 / §6 |
| NFR-002（下流互換性） | §4.3 |

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
│   ├─ compute_pink_ratio(roi_bgr) -> float
│   ├─ compute_iou(a, b) -> float
│   ├─ clip_bbox(bbox, W, H) -> tuple[int, int, int, int]
│   └─ select_pink_bbox(bboxes, ratios, prev_selected_bbox) -> int | None
├─ I/O（変更なし）
│   ├─ load_json_frames
│   └─ write_json_frame
└─ main（1 行追加のみ）
    └─ pink_id 付与ループ内に pink_ratio 代入を追加
```

### 2.2 依存関係

- 既存の `cv2`, `numpy`, 標準ライブラリ（`argparse`, `json`, `os`, `re`, `sys`, `time`, `pathlib`）のみ
- 追加依存なし

### 2.3 ディレクトリ構成

既存と同じ。新規ファイルは作成しない。

## 3. 技術スタック

| 項目 | 値 | 選定理由 |
|------|-----|----------|
| 言語 | Python 3.10.16 | プロジェクト既定 |
| パッケージ管理 | uv | プロジェクト既定。`uv run python scripts/postprocess_pink_id.py` で実行 |
| OpenCV | 既存 uv 環境の opencv-python | 既存利用（BGR→HSV 変換、マスク生成）。変更なし |
| numpy | 既存 uv 環境の numpy | 既存利用。変更なし |

追加ライブラリの導入は行わない。

## 4. 各機能の詳細設計

### 4.1 FR-001: pink_ratio フィールドの付与

#### 4.1.1 データフロー

- 入力: 既存の `ratios: list[float]`（`people` と同長、各要素の値域 [0.0, 1.0]）
- 出力: 各 `person: dict` に `pink_ratio: float` を追加（値域 [0.0, 1.0]）

`ratios[i]` は既存実装のループ（現行 L230–248 周辺、`for i, person in enumerate(people):` から `ratios.append(compute_pink_ratio(roi))` まで）で `compute_pink_ratio(roi)` により計算済みで、再計算しない。

#### 4.1.2 処理ロジック

現行 `scripts/postprocess_pink_id.py` の L253–254 周辺（`# pink_id 付与` コメント直下の `for i, person in enumerate(people):` ブロック）を修正する。

**修正前**:

```python
# pink_id 付与
for i, person in enumerate(people):
    person["pink_id"] = 1 if i == sel_idx else -1
```

**修正後**:

```python
# pink_id / pink_ratio 付与
for i, person in enumerate(people):
    person["pink_id"] = 1 if i == sel_idx else -1
    person["pink_ratio"] = ratios[i]
```

上記コードスニペットは意図の伝達目的であり、実装時はインデントと周辺コードをファイルに合わせる。

#### 4.1.3 値の型

- `ratios[i]` は `compute_pink_ratio` 内で `pink_pixels / total_pixels`（`int / int`）として計算されるため Python の `float`（ネイティブ型）。`json.dump` でそのまま数値シリアライズ可能で、numpy スカラー変換は不要。
- ROI サイズ 0 の場合は `compute_pink_ratio` が `0.0` を返す。
- `total_pixels == 0` の三項演算子保護により ZeroDivisionError は発生しない。

#### 4.1.4 エラーハンドリング

- 本改修で新規に発生し得るエラーはなし（既存計算結果の再利用のみ）。
- `ratios[i]` が存在しないインデックス i は存在しない（`ratios` は `people` と同じループで逐次 append されるため）。

#### 4.1.5 境界条件

- `people == []` のフレーム: `for` ループが空回りし、`pink_ratio` は何も書かれない（従来と同様、`pink_id` も書かれない）。出力 JSON の `people` は空配列のまま保存される。
- `ratios[i] == 0.0`: そのまま `pink_ratio = 0.0` が書かれる。
- `ratios[i] == 1.0`（全画素がピンク範囲）: そのまま `pink_ratio = 1.0` が書かれる。

### 4.2 FR-002: BB 欠損 person の値規約

#### 4.2.1 データフロー

- 入力: `person["bbox"]` が存在しない、または長さ 4 でない `people[i]`
- 中間: 既存実装では `bboxes.append(None); ratios.append(0.0)` として処理される（現行 L232–240、`bb is None or len(bb) != 4:` の分岐）
- 出力: `person["pink_ratio"] = 0.0`

#### 4.2.2 処理ロジック

- §4.1.2 の修正だけで自動的に満たされる。`ratios[i]` が `0.0` として append されているため、`person["pink_ratio"] = ratios[i]` で `0.0` が書かれる。
- 既存 WARNING ログ（`WARNING: Missing/invalid bbox in frame {frame_idx} person {i}`）は変更しない。

#### 4.2.3 設計判断の記録（ADR）

- **採用案**: bbox 欠損 person に対して `pink_ratio = 0.0` を書き込む。
- **却下案 1**: `pink_ratio = None`（JSON 上は `null`）を書き込む。下流が未知フィールドを参照したときに型が揺れるリスクがあるため却下。
- **却下案 2**: bbox 欠損 person には `pink_ratio` キー自体を書かない。キー有無で分岐させるより、数値 0.0 で統一した方がデバッグ解析（CSV 化やグラフ化）が素直なため却下。

### 4.3 FR-003: 既存フィールド・CLI の非変更

#### 4.3.1 不変事項

以下は本案件で一切変更しない。

- CLI 引数: `--video`, `--json-dir`, `--out-dir`
- 出力ディレクトリの上書き防止チェック（現行 L178–180、`os.path.realpath` 比較）
- サマリ出力（現行 L289–299、FR-003 の AC-003-3 に列挙した 7 項目）
- `select_pink_bbox` の選択ロジックと 3 つの定数
- `pink_id` の値規約（選択 = 1 / 非選択 = -1）
- `prev_selected_bbox` の更新ロジック
- 既存フィールド（`person_id`, `bbox`, `pose_keypoints_2d`, `bbox_score`, `stable_id` 等）は書き戻しをスルー（生 dict 保持設計）

#### 4.3.2 下流互換性の確認

- feat-035 `postprocess_track.py`: 生 dict 保持、`track_id` のみ追加。`pink_ratio` の存在は影響なし。
- feat-036 `postprocess_patient_id.py`: `pink_id` と `track_id` のみ参照。`pink_ratio` は無視される。
- feat-037 `plot_pink_track_timeline.py`: `pink_track_id` ベースの時系列描画。`pink_ratio` は参照しない（将来の拡張候補だが本案件外）。
- feat-038 `visualize_patient_video.py`: `pink_id` / `pink_track_id` / `track_id` / `bbox_score` を参照。`pink_ratio` は無視される。

## 5. ファイル・ディレクトリ設計

### 5.1 出力 JSON スキーマ（改修後、1 人物エントリの抜粋）

```json
{
  "person_id": [-1],
  "pose_keypoints_2d": [/* 26 * 3 = 78 float */],
  "bbox": [x1, y1, x2, y2],
  "bbox_score": 0.912,
  "pink_id": 1,
  "pink_ratio": 0.147
}
```

- 既存フィールド順は保存しない（Python dict の挿入順に依存）。既存実装でも順序保証はしていないため、読み込み側のキー参照で支障なし。
- 改修で新規追加されるキーは `pink_ratio` のみ。

### 5.2 入出力パス

既存と同じ。ファイル命名規約（`*_{6 桁フレーム番号}.json`）も変更しない。

## 6. ログ・デバッグ設計

### 6.1 既存ログ

- 進捗表示（`Processing frame ...`）、サマリ、WARNING は変更しない。

### 6.2 追加ログ

なし。`pink_ratio` の書き込み自体はログ出力しない。

### 6.3 事後確認の指針（実装者向けガイド）

- 改修後に camSony1_S（約 445 フレーム、NFR-001 の軽量テスト）で実行し、1 フレームの出力 JSON を目視して `pink_ratio` が各 `people[i]` に含まれることを確認する。
- `pink_id == 1` の人物の `pink_ratio >= 0.03` が成立することを 1 サンプル確認する（AC-001-3 の健全性チェック）。
- 改修前後の出力で `pink_id == 1` が付与される (frame, person_index) 集合が一致することを `diff` 相当の方法で確認する（AC-003-1）。

## 7. インターフェース定義

### 7.1 公開関数の変更

なし。関数シグネチャ（`compute_pink_ratio`, `compute_iou`, `clip_bbox`, `select_pink_bbox`, `load_json_frames`, `write_json_frame`, `main`）は一切変更しない。

### 7.2 モジュール間の呼び出し方向

変更なし。単一スクリプト内で完結し、他モジュールへ import されない。

## 8. 設計判断の記録（全体 ADR サマリ）

- **CLI フラグ化しない**: `--write-pink-ratio` のような ON/OFF フラグを設けず、常時書き込みとする。理由: (1) 計算コストは既に発生しており追加コストゼロ、(2) フラグを増やすと下流とのインタフェース条件分岐が増えデバッグ目的の趣旨に反する、(3) フィールドの存在は下流で無視されるため常時書き込みでも副作用なし。
- **フィールド名**: `pink_ratio` に固定。feat-033 の用語定義「ピンク比率」と整合する。他候補（`hsv_pink_ratio`, `pink_score`）は却下。
- **欠損時は 0.0**: §4.2.3 を参照。

## 9. 実装完了後のチェックリスト

- [ ] `scripts/postprocess_pink_id.py` の pink_id 付与ループに `person["pink_ratio"] = ratios[i]` が追加されている
- [ ] camSony1_S で実行し、出力 JSON の任意 1 フレームに `pink_ratio` が含まれることを確認
- [ ] 改修前後で `pink_id == 1` の (frame, person_index) 集合が一致することを確認
- [ ] `scripts/README.md` の `postprocess_pink_id.py` 記述に `pink_ratio` フィールドの追加を反映
- [ ] CLAUDE.md の feat-039 エントリを Closed として更新
- [ ] `docs/BACKLOG.md` の feat-039 を Closed テーブルに追記
