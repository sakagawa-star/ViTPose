# feat-042 機能設計書: visualize_patient_video.py に pink 選択診断フィールドを描画する拡張

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001（BB 内部描画） | §4.1 |
| FR-002（フィールド別フラグ） | §4.2 / §7.1 |
| FR-003（id_type × mode 互換） | §4.3 |
| FR-004（欠損フォールバック） | §4.4 |
| FR-005（描画位置・スタイル） | §4.5 |
| FR-006（既存非変更） | §4.6 |
| NFR-001（パフォーマンス） | §6 |

## 2. システム構成

### 2.1 モジュール構成

単一ファイル `scripts/visualize_patient_video.py` のみを修正する。新規ファイル・新規モジュールの追加は行わない。

```
scripts/visualize_patient_video.py
├─ 定数（変更なし）
│   ├─ PROGRESS_INTERVAL_FRAMES
│   ├─ COLOR_GRAY / COLOR_FILTER
│   ├─ ID_TYPE_SHORT
│   └─ COLOR_PALETTE
├─ 純関数
│   ├─ _generate_palette（変更なし）
│   ├─ get_color_for_mode（変更なし）
│   ├─ detect_json_stem（変更なし）
│   ├─ load_frame_json（変更なし）
│   ├─ filter_people（変更なし）
│   ├─ draw_skeleton（変更なし）
│   ├─ draw_person（拡張: 診断テキスト描画呼び出しを追加）
│   ├─ build_debug_label（新規追加）
│   └─ draw_frame_number（変更なし）
└─ main（CLI 引数 5 個追加・関数呼び出しに引数引き渡し）
```

### 2.2 依存関係

追加 import なし。既存の `argparse` / `cv2` / `numpy` で完結。

### 2.3 ディレクトリ構成

既存と同じ。

## 3. 技術スタック

| 項目 | 値 | 選定理由 |
|------|-----|----------|
| 言語 | Python 3.10.16 | プロジェクト既定 |
| パッケージ管理 | uv | プロジェクト既定 |
| OpenCV | 既存依存 | `cv2.putText` 流用 |
| argparse | 標準ライブラリ | `BooleanOptionalAction` で `--show-X` / `--no-show-X` 対を一括定義 |

## 4. 各機能の詳細設計

### 4.1 FR-001: BB 内部に診断フィールドを描画する

#### 4.1.1 データフロー

- 入力: 1 つの `person: dict`（`bb_index` / `pink_id` / `pink_ratio` / `iou_with_prev` / `selection_score` を含むことが期待されるが、欠損許容）
- 中間: `label: str`（`build_debug_label` の戻り値、空文字列の可能性あり）
- 出力: BB 内部に描画されたテキスト（`cv2.putText` の副作用）

#### 4.1.2 処理ロジック

`draw_person` 関数で **`draw_skeleton` 呼び出しの直前** に診断テキスト描画を追加する（位置は本設計で固定。実装者は他の位置に置かないこと）。理由: 既存 BB 上方ラベル → 診断テキスト → スケルトンの順で z-order を統一し、骨格描画が一番上に来る。

**修正前 (`draw_person` 抜粋)**:

```python
def draw_person(img, person, color, id_type, kpt_thr):
    bbox = person.get("bbox")
    if bbox is None or len(bbox) != 4:
        return
    x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

    id_value = person.get(id_type, "?")
    score = person.get("bbox_score", 0)
    short = ID_TYPE_SHORT.get(id_type, id_type)
    label = f"{short}:{id_value} {score:.2f}"
    text_y = y1 - 8 if y1 - 8 > 0 else y1 + 20
    cv2.putText(img, label, (x1, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    draw_skeleton(img, person, color, kpt_thr)
```

**修正後 (`draw_person` シグネチャ拡張)**:

```python
def draw_person(img, person, color, id_type, kpt_thr, debug_flags):
    bbox = person.get("bbox")
    if bbox is None or len(bbox) != 4:
        return
    x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

    # 既存 BB 上方ラベル（変更なし）
    id_value = person.get(id_type, "?")
    score = person.get("bbox_score", 0)
    short = ID_TYPE_SHORT.get(id_type, id_type)
    label = f"{short}:{id_value} {score:.2f}"
    text_y = y1 - 8 if y1 - 8 > 0 else y1 + 20
    cv2.putText(img, label, (x1, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    # 診断テキスト（BB 内部）
    debug_label = build_debug_label(person, debug_flags)
    if debug_label:
        cv2.putText(
            img, debug_label, (x1 + 4, y1 + 16),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1,
        )

    draw_skeleton(img, person, color, kpt_thr)
```

`debug_flags` は `dict[str, bool]` で main から渡す（§7.1）。

### 4.2 FR-002: フィールド別 ON/OFF フラグ

#### 4.2.1 build_debug_label 関数（新規）

```python
def build_debug_label(person: dict, debug_flags: dict[str, bool]) -> str:
    """診断フィールドを ON 順に整形した 1 行ラベルを返す。
    キー欠損: その部分をラベルから省略。
    値が None: 当該部分を `null` 文字列で表示（5 フィールド統一）。
    """
    parts: list[str] = []

    if debug_flags["bb_index"] and "bb_index" in person:
        v = person["bb_index"]
        parts.append("idx=null" if v is None else f"idx={int(v)}")

    if debug_flags["pink_id"] and "pink_id" in person:
        v = person["pink_id"]
        parts.append("pid=null" if v is None else f"pid={int(v)}")

    if debug_flags["pink_ratio"] and "pink_ratio" in person:
        v = person["pink_ratio"]
        parts.append("r=null" if v is None else f"r={v:.3f}")

    if debug_flags["iou_with_prev"] and "iou_with_prev" in person:
        v = person["iou_with_prev"]
        parts.append("iou=null" if v is None else f"iou={v:.3f}")

    if debug_flags["selection_score"] and "selection_score" in person:
        v = person["selection_score"]
        parts.append("s=null" if v is None else f"s={v:.3f}")

    return " ".join(parts)
```

整数フィールド（`bb_index` / `pink_id`）は `int(v)` でラップする。理由: 万が一 float で格納されていた場合に `pid=1.0` のような表記を避けるため。

#### 4.2.2 値表記の固定

- 小数点以下 3 桁: `f"{v:.3f}"`
- 整数: そのまま（`bb_index` / `pink_id`）
- null: 文字列 `"null"`
- 順序: idx → pid → r → iou → s（`build_debug_label` の if 文順で固定）

#### 4.2.3 設計判断の記録（ADR）

- **採用案: フィールドごとに独立フラグ**: 個別ハンドリング容易、要求仕様 4 の通り
- **却下案: 単一フラグ `--show-debug-info` で全 ON/OFF**: 「`pink_ratio` だけ見たい」等のニーズに応えられない
- **採用案: `argparse.BooleanOptionalAction`**: `--show-X` / `--no-show-X` の対を 1 行で定義可能、デフォルト True を簡潔に表現
- **却下案: `--show-X true/false` の文字列引数**: 型変換ロジックが煩雑

### 4.3 FR-003: id_type × mode 互換

#### 4.3.1 処理ロジック

既存の `filter_people` で抽出された人物リストに対して、`get_color_for_mode` で色を取得し、`draw_person` を呼ぶ既存フローを変更しない。`draw_person` のシグネチャに `debug_flags` を追加するのみ。

`build_debug_label` の出力は `--id-type` に依存せず、常に同じ 5 フィールドを参照する（`person` dict から直接フィールド名で取得）。

### 4.4 FR-004: 欠損フォールバック

#### 4.4.1 処理ロジック

`build_debug_label` で `if "X" in person` チェックを各フィールドに対して行う。キー欠損時は `parts` への append をスキップする。

null 値（連続性切れ）はキー存在 + 値 None ⇒ `null` 文字列として表示。これは feat-041 で規定された値規約と整合する。

#### 4.4.2 境界条件

- 全フラグ ON だが全フィールドが欠損している old JSON: `parts == []` ⇒ `" ".join([]) == ""` ⇒ `if debug_label:` で false ⇒ `cv2.putText` スキップ ⇒ クラッシュしない
- 一部のみ欠損: 存在するフィールドのみ描画
- `pink_ratio` が float 0.0: `r=0.000` と描画される（値ありなのでスキップしない）
- 5 フィールドのいずれかがキー存在 + 値 `None`: 当該フィールドのみ `null` 文字列。`int(None)` / `f"{None:.3f}"` の TypeError は起こさない（事前 `is None` 判定で回避）

### 4.5 FR-005: 描画位置・スタイル

#### 4.5.1 固定値

| パラメータ | 値 |
|-----------|-----|
| テキスト基準点 | `(x1 + 4, y1 + 16)` |
| フォント | `cv2.FONT_HERSHEY_SIMPLEX` |
| フォントスケール | `0.45` |
| 太さ | `1` |
| 色 | BB の色（`get_color_for_mode` 戻り値） |
| 背景 | なし |

#### 4.5.2 設計判断の記録（ADR）

- **採用案: BB 内部 (`x1 + 4, y1 + 16`)**: 既存 BB 上方ラベルと衝突せず、複数 BB が縦に重なっても各 BB のテキストが BB 内に収まる
- **却下案: BB 下方 (`x1, y2 + N`)**: BB 下端に他 BB の上方ラベルが乗りやすく可読性が下がる
- **却下案: BB 上方の右側 (`x2, y1 - N`)**: BB が画面右端にあると見切れる
- **採用案: フォントスケール 0.45 / 太さ 1**: 既存 BB 上方ラベル (0.5 / 1) よりやや小さく、5 フィールド分の文字列（最大 50 文字程度）が BB 内に収まりやすい
- **テキスト色 = BB 色**: 採用。理由: BB と一目で対応が取れる。視認性低下のリスクは小さい（描画位置 (x1+4, y1+16) は BB 矩形線から離れている）。AC-005-3 の手動テスト（誤選択区間で 5 フィールド値が等倍再生で読み取れる）で実測確認する
- **却下案: 黒影 + 色細の 2 重 putText**: 視認性は上がるが描画コストが倍。NFR-001 の 30% 制約に余裕があれば将来案件で再評価可

### 4.6 FR-006: 既存挙動の非変更

#### 4.6.1 不変事項

- 既存 CLI 引数の名前・デフォルト値・help 文字列
- 出力ファイル命名規約 `vis_{id_type}_{mode}_{video_stem}.mp4`
- `cv2.rectangle` の位置・色・太さ
- 既存 BB 上方ラベルの位置・内容
- `draw_skeleton` の挙動
- `draw_frame_number` の挙動
- フレーム描画範囲制御 (`--draw-start` / `--draw-end`)

#### 4.6.2 全フラグ OFF 時の振る舞い

- `build_debug_label` が空文字列を返す
- `if debug_label:` で false
- `cv2.putText` 呼び出しがスキップされ、出力動画は改修前と視覚的に同一になる（AC-006-1）

## 5. ファイル・ディレクトリ設計

### 5.1 入出力パス

- 入力動画: 既存と同じ（`--video`）
- 入力 JSON: 既存と同じ（`--json-dir`）。**feat-041 改修済みの JSON を想定**するが、欠損フォールバックにより改修前の JSON でも動作する
- 出力 MP4: 既存と同じ命名 `vis_{id_type}_{mode}_{video_stem}.mp4`

### 5.2 推奨実行コマンド（手動テスト用）

camSony1_L フレーム 29519–30915 の誤選択区間で、`pink_id=1` のみフィルタ表示:

```bash
uv run python scripts/visualize_patient_video.py \
  --video testdata/camSony1.mp4 \
  --json-dir experiments/results/camSony1_L_pink_json \
  --out-dir experiments/results \
  --id-type pink_id --mode filter --filter-values 1 \
  --draw-start 29519 --draw-end 30915
```

`--mode all` で全 BB 確認:

```bash
uv run python scripts/visualize_patient_video.py \
  --video testdata/camSony1.mp4 \
  --json-dir experiments/results/camSony1_L_pink_json \
  --out-dir experiments/results \
  --id-type pink_id --mode all \
  --draw-start 29519 --draw-end 30915
```

## 6. パフォーマンス影響

`cv2.putText` 1 回追加 + 文字列整形（5 フィールド分の `f"..."`）。1 BB あたり数十 μs オーダー。camSony1_L で総 BB 数 100 万強 → 追加コストは数十秒以内。NFR-001 の 30% 以内には余裕で収まる見込み。

## 7. インターフェース定義

### 7.1 CLI 引数追加

```python
parser.add_argument(
    "--show-bb-index",
    action=argparse.BooleanOptionalAction, default=True,
    help="Show bb_index in debug label (BB interior)",
)
parser.add_argument(
    "--show-pink-id",
    action=argparse.BooleanOptionalAction, default=True,
    help="Show pink_id in debug label",
)
parser.add_argument(
    "--show-pink-ratio",
    action=argparse.BooleanOptionalAction, default=True,
    help="Show pink_ratio in debug label",
)
parser.add_argument(
    "--show-iou-with-prev",
    action=argparse.BooleanOptionalAction, default=True,
    help="Show iou_with_prev in debug label",
)
parser.add_argument(
    "--show-selection-score",
    action=argparse.BooleanOptionalAction, default=True,
    help="Show selection_score in debug label",
)
```

main 内で `debug_flags` dict を構築:

```python
debug_flags = {
    "bb_index": args.show_bb_index,
    "pink_id": args.show_pink_id,
    "pink_ratio": args.show_pink_ratio,
    "iou_with_prev": args.show_iou_with_prev,
    "selection_score": args.show_selection_score,
}
```

`draw_person(frame, person, color, args.id_type, args.kpt_thr, debug_flags)` で渡す。

### 7.2 関数シグネチャ変更

| 関数 | 旧シグネチャ | 新シグネチャ |
|------|-------------|-------------|
| `draw_person` | `(img, person, color, id_type, kpt_thr)` | `(img, person, color, id_type, kpt_thr, debug_flags)` |
| `build_debug_label` | (新規) | `(person: dict, debug_flags: dict[str, bool]) -> str` |

他関数のシグネチャは変更しない。

## 8. ログ・デバッグ設計

### 8.1 既存ログ

進捗表示・サマリは変更しない。

### 8.2 追加ログ

なし。

## 9. 設計判断の記録（全体 ADR サマリ）

- **既存スクリプト拡張 vs 新規スクリプト**: 拡張を採用（要求 1）。理由: 機能の重複を避ける
- **BB 内部描画 vs BB 上方/下方**: BB 内部 (x1+4, y1+16)。理由: 既存ラベルと衝突せず、複数 BB が縦に重なっても各 BB のテキストが BB 内に収まる
- **フィールド別フラグ vs 単一フラグ**: フィールド別。理由: 個別解析時の柔軟性。デフォルトは全 ON（情報量重視、要求 1.4）
- **値表記**: 小数 3 桁固定、null は文字列表示、順序は固定。理由: 仕様の単純化と一貫性
- **`argparse.BooleanOptionalAction` 採用**: `--show-X` / `--no-show-X` 対の簡潔な定義
- **欠損フォールバック方式**: `if "X" in person` チェックでキー欠損時はスキップ。null 値は `null` 文字列。理由: feat-041 改修前 JSON との後方互換性を維持しつつ、null と欠損を区別

## 10. 実装完了後のチェックリスト

- [ ] `scripts/visualize_patient_video.py` に `build_debug_label` 関数を追加
- [ ] `draw_person` のシグネチャに `debug_flags` を追加し、診断テキスト描画ロジックを追加
- [ ] main に CLI 引数 5 個を追加し、`debug_flags` dict を構築して `draw_person` に渡す
- [ ] camSony1_S（軽量）で全フラグ ON のデフォルト挙動を確認
- [ ] camSony1_L フレーム 29519–30915 の誤選択区間で `--id-type pink_id --mode filter --filter-values 1` を実行し、誤選択 BB の `selection_score` / `iou_with_prev` が動画上で確認できることを目視
- [ ] 全フラグ OFF で実行し、既存出力と視覚的に区別不能であることを確認（AC-006-1）
- [ ] feat-041 改修前の JSON（古い出力）でも動作することを確認（AC-004-1）
- [ ] camSony1_L で処理時間が改修前の 130% 以内であることを確認（NFR-001）
- [ ] `scripts/README.md` の `visualize_patient_video.py` 記述に新規 5 フラグを反映
- [ ] CLAUDE.md の feat-042 エントリを完了済み案件として追記
- [ ] `docs/BACKLOG.md` の feat-042 を Closed テーブルに移動
- [ ] `docs/issues/feat-042-overlay-pink-debug-info/README.md` のステータスを Closed に更新
