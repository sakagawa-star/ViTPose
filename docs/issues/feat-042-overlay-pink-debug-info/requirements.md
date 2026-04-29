# feat-042 要求仕様書: visualize_patient_video.py に pink 選択診断フィールドを描画する拡張

## 1. プロジェクト概要

### 1.1 何を作るのか

既存 `scripts/visualize_patient_video.py` を拡張し、feat-041 で JSON 各 `people[i]` に追加された 5 つの診断フィールド（`bb_index` / `pink_id` / `pink_ratio` / `iou_with_prev` / `selection_score`）を BB 内部に 1 行のテキストとして描画する機能を追加する。

### 1.2 なぜ作るのか

- 現行のラベルは `{id_short}:{id_value} {bbox_score:.2f}` のみで、`pink_id` の誤選択原因を動画上で特定する情報量が不足している
- feat-041 で JSON に診断フィールドを追加したが、同フレームに複数 BB がある場合に「動画上のどの BB が JSON のどの people[i] か」が `bb_index` を描画しないと一意に特定できない
- 誤選択区間（camSony1_L フレーム 29519–30915 など、ピンク患者の前を別人が通り過ぎた直後に `pink_id=1` が別人にロックインする現象）の解析を動画ベースで行うため、`pink_ratio` / `iou_with_prev` / `selection_score` の値を BB ごとに見える化する必要がある

### 1.3 誰が使うのか

本プロジェクトの開発者（`pink_id` の誤選択原因解析、可視化動画と JSON の突合を行う者）。

### 1.4 どこで使うのか

既存 `visualize_patient_video.py` と同一の実行環境（uv 環境、CPU + OpenCV）。出力 MP4 のファイル名規約（`vis_{id_type}_{mode}_{video_stem}.mp4`）も維持する。

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| 診断フィールド | feat-041 で `postprocess_pink_id.py` が JSON に書き込む 5 フィールドの総称。本案件では描画対象として扱う |
| `pink_id` | int。`postprocess_pink_id.py` が付与する患者候補フラグ。値域 `{1, -1}`（典拠: `scripts/postprocess_pink_id.py:262` の `person["pink_id"] = 1 if i == sel_idx else -1`、および camSony1_L_pink_json の実データサンプリングで `{1, -1}` のみ観測）。feat-033 以降の改修済み JSON では常に存在、それ以前の古い JSON ではキー欠損もありうる（FR-004 参照） |
| `pink_ratio` | float。当該 BB の HSV ピンク画素比率。値域 [0.0, 1.0]。feat-039 以降で常に存在。古い JSON ではキー欠損もありうる（FR-004 参照） |
| `iou_with_prev` | float または null。前フレーム選択 BB との IoU。連続性切れ・bbox 欠損時は null。feat-041 改修前 JSON ではキー欠損 |
| `selection_score` | float または null。`pink_ratio + 0.05 × iou_with_prev`。`iou_with_prev` が null のときは null。feat-041 改修前 JSON ではキー欠損 |
| `bb_index` | int。同フレームの `people` リスト内 0 始まり連番。feat-041 改修前 JSON ではキー欠損 |
| BB 内部描画 | 1 行のテキストを BB の左上頂点から内側にオフセットした位置に描画する。BB の上方ではない（既存ラベルの位置とは異なる） |
| 短縮表記 | 各フィールドのラベル略号。`bb_index` → `idx`、`pink_id` → `pid`、`pink_ratio` → `r`、`iou_with_prev` → `iou`、`selection_score` → `s`。詳細は FR-002 |
| 既存 BB ラベル | 現行の `{id_short}:{id_value} {bbox_score:.2f}`（BB の上方に描画）。本案件では位置・内容を変更しない |

## 3. 機能要求一覧

### FR-001: BB 内部に診断フィールドを描画する

- **概要**: 各 BB の内部に、診断フィールドを 1 行のテキストとして描画する
- **入力**: feat-041 改修済み JSON（`people[i]` に診断フィールド 5 個を含む）
- **出力**: BB 内部にテキストが描画された MP4 動画
- **処理内容**:
  1. 既存の `draw_person` 関数で BB の矩形を描画した後、診断フィールドを 1 行に整形して BB 左上頂点から内側にオフセットした位置（FR-005 で定義）に `cv2.putText` で描画する
  2. 既存 BB ラベル（`{id_short}:{id_value} {bbox_score:.2f}`、BB 上方）は変更しない
- **受け入れ基準**:
  - AC-001-1: ON にしたフィールドの値が BB 内部にテキストとして見える
  - AC-001-2: BB 上方の既存ラベルは引き続き同じ位置・内容で描画される
  - AC-001-3: 全フラグを OFF にした場合、BB 内部に診断テキストが描画されない（既存ラベルのみが残る）

### FR-002: フィールド別 ON/OFF フラグを追加する

- **概要**: 5 つの診断フィールドそれぞれに独立した ON/OFF CLI フラグを設ける。デフォルトは全 ON
- **入力**: 以下の CLI フラグ（`argparse.BooleanOptionalAction` で `--show-X` / `--no-show-X` の対をなす）
  - `--show-bb-index` / `--no-show-bb-index` （デフォルト True）
  - `--show-pink-id` / `--no-show-pink-id` （デフォルト True）
  - `--show-pink-ratio` / `--no-show-pink-ratio` （デフォルト True）
  - `--show-iou-with-prev` / `--no-show-iou-with-prev` （デフォルト True）
  - `--show-selection-score` / `--no-show-selection-score` （デフォルト True）
- **出力**: ON のフィールドだけがラベル文字列に含まれる
- **処理内容**:
  1. ラベル順序は固定: `idx`, `pid`, `r`, `iou`, `s`
  2. ON のフィールドのみをスペース区切りで連結する
  3. 値の整形（5 フィールドすべて null 安全に統一）:
     - `bb_index`: 整数値を `int(...)` でラップして `idx={int}`（例: `idx=2`）。値が `None` なら `idx=null`
     - `pink_id`: 整数値を `int(...)` でラップして `pid={int}`（例: `pid=1`、`pid=-1`）。値が `None` なら `pid=null`
     - `pink_ratio`: float なら `r={float:.3f}`（例: `r=0.421`）。値が `None` なら `r=null`
     - `iou_with_prev`: float なら `iou={float:.3f}`、`None` なら `iou=null`
     - `selection_score`: float なら `s={float:.3f}`、`None` なら `s=null`
- **受け入れ基準**:
  - AC-002-1: `--no-show-bb-index` 指定時、ラベルから `idx=` 部分が消え、他フィールドの順序は変わらない
  - AC-002-2: 全フラグ ON のラベル例: `idx=2 pid=1 r=0.421 iou=0.823 s=0.462`
  - AC-002-3: `iou_with_prev` が null のフレームでは `iou=null s=null`（数値ではなく文字列 `null`）
  - AC-002-4: 全フラグ OFF 指定時、`cv2.putText` 呼び出しはスキップされる
  - AC-002-5: 5 フィールドのいずれかが `None` 値で渡された場合も TypeError でクラッシュせず、対応フィールドのみ `null` 文字列で表示される
  - AC-002-6: `bb_index` / `pink_id` が float 型で格納されていた場合（実装上 int で書かれる前提だが念のため）、`int(...)` ラップにより小数点なしで表示される

### FR-003: 描画対象 BB の互換性

- **概要**: 既存の `--id-type` × `--mode` の全組合せで本機能が動作する
- **入力**: 既存 `--id-type` (`pink_track_id` / `pink_id` / `track_id`) × `--mode` (`filter` / `all`) のすべて
- **出力**: 既存挙動と同様、`mode=filter` では `--filter-values` に一致する BB のみ描画、`mode=all` では全 BB を色分け描画
- **処理内容**:
  1. 既存の `filter_people` で抽出された BB に対してのみ診断フィールドを描画する（描画対象外 BB には描画しない）
  2. 描画フィールド値は `--id-type` に依存しない（常に同じ 5 フィールド）
- **受け入れ基準**:
  - AC-003-1: `--id-type pink_id --mode filter --filter-values 1` で実行時、`pink_id=1` の BB に診断テキストが描画される
  - AC-003-2: `--id-type pink_track_id --mode all` で実行時、全 BB に診断テキストが描画される
  - AC-003-3: `--id-type track_id` の場合も診断テキストの内容は同じ（`pink_id` / `pink_ratio` / `iou_with_prev` / `selection_score` を含む）
  - AC-003-4: 描画対象から外れた BB（`mode=filter` で `--filter-values` に該当しないもの）には診断テキストが描画されない

### FR-004: 診断フィールド欠損時のフォールバック

- **概要**: 古い JSON（feat-041 改修前）など診断フィールドが欠損する人物エントリでも、スクリプトは異常終了せず該当部分のみ表示を省略する
- **入力**: `people[i]` の一部または全部に診断フィールドが存在しない JSON
- **出力**: 欠損フィールドはラベルから省略、他のフィールドは通常通り描画される
- **処理内容**:
  1. `person.get(field_name)` で値を取得
  2. キーが存在しない（`KeyError` 相当）場合は当該フィールド部分をラベルから省略する
  3. キーは存在し値が `None` の場合（`iou_with_prev` / `selection_score` の連続性切れ）は `null` 文字列として表示する（FR-002 で規定済み）
- **受け入れ基準**:
  - AC-004-1: feat-041 改修前の JSON でスクリプトを実行してもクラッシュせず動画を生成できる
  - AC-004-2: 一部の人物エントリで `pink_ratio` キーが欠損していても、他のフィールドは通常通り描画される
  - AC-004-3: 5 フィールドすべてに対し、キー存在 + 値 None ⇒ `null` 文字列を表示、キー欠損 ⇒ ラベルから省略する規約を統一適用する

### FR-005: 描画位置・スタイル

- **概要**: 診断テキストを BB 内部の左上頂点から固定オフセット位置に、固定スタイルで描画する
- **入力**: BB 座標 `(x1, y1, x2, y2)`
- **出力**: BB 内部にテキストが配置される
- **処理内容**:
  1. テキスト基準点: `(x1 + 4, y1 + 16)`（左に 4px、下に 16px のオフセット）
  2. フォント: `cv2.FONT_HERSHEY_SIMPLEX`
  3. フォントスケール: `0.45`
  4. 太さ: `1`
  5. 色: BB の色と同じ（`get_color_for_mode` の戻り値を流用）
  6. 背景塗りつぶし: なし（既存ラベルと同じく素の `putText` のみ）
- **受け入れ基準**:
  - AC-005-1: テキスト基準点は BB の内側（`x1 + 4` ≦ x ≦ `x2`、`y1 + 16` ≦ y ≦ `y2` を満たす範囲、ただし BB の高さが 16px 未満または幅が 4px 未満の場合は文字が BB を超えてもよい）
  - AC-005-2: 既存の BB 上方ラベルとは異なる位置に描画される（縦方向に重ならない、ただし BB の高さが 16px 未満の場合の重なりは許容）
  - AC-005-3: 出力 MP4 を camSony1_L フレーム 29519–30915 の区間で再生し、誤選択が起きている近傍の任意 5 フレームについて、各 BB に描画された 5 フィールドの値（小数 3 桁部分を含む）を人間が等倍再生で読み取れる

### FR-006: 既存挙動の非変更

- **概要**: 本案件で診断テキスト描画以外の既存挙動を変更しない
- **入力**: 既存
- **出力**: 既存
- **処理内容**:
  1. 既存 BB 矩形描画（`cv2.rectangle`）の位置・色・太さは変更しない
  2. 既存 BB 上方ラベル（`{id_short}:{id_value} {bbox_score:.2f}`）の位置・内容は変更しない
  3. 既存 `draw_skeleton` は変更しない
  4. 既存 CLI 引数（`--video` / `--json-dir` / `--out-dir` / `--id-type` / `--mode` / `--filter-values` / `--draw-start` / `--draw-end` / `--kpt-thr`）は名前・デフォルト値とも変更しない
  5. 出力ファイル命名規約 `vis_{id_type}_{mode}_{video_stem}.mp4` は変更しない
- **受け入れ基準**:
  - AC-006-1: 全フラグ OFF で実行した場合、出力動画は本案件改修前と視覚的に区別不能（BB 矩形・既存ラベル・スケルトンが同じ位置・色で描画される）
  - AC-006-2: 既存 CLI 引数のヘルプメッセージは変更されない（追加引数の説明だけが新規に増える）

## 4. 非機能要求

### NFR-001: パフォーマンス

- 既存実装に対し、同一入力（camSony1_L 全体、321K フレーム）で処理時間の増加が **30% 以内** に収まる
  - 根拠: BB 1 個あたり `cv2.putText` 呼び出しが 1 回追加。文字列整形は数 μs オーダー。BB 数は典型 1〜5 個/フレーム

### NFR-002: 対応環境

- 既存 `visualize_patient_video.py` と同一（Python 3.10.16、uv 環境、CPU 実行、OpenCV）

### NFR-003: 出力品質

- 描画されたテキストが既存 BB 矩形・スケルトンを大きく覆い隠さない（FR-005 の固定オフセットで担保）

## 5. 制約条件

### 5.1 使用必須のライブラリ

- 既存依存のみ（OpenCV、numpy）。追加ライブラリの導入は行わない

### 5.2 追加禁止

- 新規スクリプトの作成（既存 `visualize_patient_video.py` を拡張する）
- 描画位置を BB 上方にする変更（既存ラベルと衝突するため BB 内部に固定）
- フィールド単位の色分け（描画スタイル単純化のため、診断テキストは BB と同じ単一色）
- 背景塗りつぶしや半透明矩形の追加（スコープ簡略化のため）
- フォントスケールの CLI 引数化（FR-005 で固定値）

### 5.3 値表記規約

- 小数点以下 3 桁に固定（FR-002）
- null は文字列 `null` として描画（FR-002, FR-004）
- フィールド順序固定: `idx`, `pid`, `r`, `iou`, `s`（FR-002）

### 5.4 デフォルト挙動

- 全 5 フラグのデフォルトは ON。理由: 既存の `pink_id` 描画では情報量不足で誤選択解析に使えないため、本案件のデフォルトは「診断情報が常に出る」状態とする

## 6. 優先順位

| ID | 機能 | 優先度 |
|----|------|--------|
| FR-001 | BB 内部に診断フィールドを描画 | Must |
| FR-002 | フィールド別 ON/OFF フラグ | Must |
| FR-003 | 描画対象 BB の互換性 | Must |
| FR-004 | 診断フィールド欠損時のフォールバック | Must |
| FR-005 | 描画位置・スタイル | Must |
| FR-006 | 既存挙動の非変更 | Must |
| NFR-001 | パフォーマンス（処理時間 30% 以内） | Should |

MVP = FR-001 + FR-002 + FR-003 + FR-004 + FR-005 + FR-006。NFR-001 は実装後の確認項目。
