# feat-056 機能設計書: postprocess_pink_id.py への確認動画同時出力統合

## 1.1 対応要求マッピング

| 要求ID | 設計セクション |
|--------|----------------|
| FR-001 | 4.1（CLI）, 4.4（VideoWriter ライフサイクル）, 4.5（描画ブロック） |
| FR-002 | 4.5（id_type="pink_id" 固定） |
| FR-003 | 4.1（--vis-mode / --vis-filter-values）, 4.5（filter_people） |
| FR-004 | 4.4（動画 1 回読み: 既存ループ流用） |
| FR-005 | 4.1（--draw-start/end）, 4.5（描画範囲判定） |
| FR-006 | 4.1（--show-* 5 フラグ）, 4.5（build_debug_label 経由） |
| FR-007 | 4.1（--vis-kpt-thr / --vis-out-dir）, 4.6（命名規約） |
| FR-008 | 4.3（オプトイン分岐）, 6（境界・後方互換テスト） |

## 1.2 システム構成

### 改修対象
- `scripts/postprocess_pink_id.py` のみ改修。

### 依存関係（import 方向）
```
postprocess_pink_id.py  ──import──▶  visualize_patient_video.py  ──import──▶  merge_halpe26.py
```
- 一方向（循環なし）。`visualize_patient_video.py` は `postprocess_pink_id.py` を import しない
  （現状コードで確認済み）。
- `visualize_patient_video.py` をモジュールとして import すると、そのトップレベルで
  `COLOR_PALETTE = _generate_palette(20)` 等の定数生成（副作用なし）が走る。`main()` は
  `if __name__ == "__main__"` ガード内なので実行されない。

### import するシンボル（visualize_patient_video.py から、いずれも無変更で再利用）
- `draw_person(img, person, color, id_type, kpt_thr, debug_flags)` — BB・ラベル・診断ラベル・
  スケルトンをまとめて描画。内部で `draw_skeleton` / `build_debug_label` を呼ぶ。
- `filter_people(people, id_type, mode, filter_values)` — mode に応じて描画対象 person を抽出。
- `get_color_for_mode(id_value, mode)` — filter は緑（COLOR_FILTER）、all は palette/gray。
- `draw_frame_number(img, frame_idx)` — 左上にフレーム番号を描画。

### import 文（postprocess_pink_id.py トップレベルに追加）
```python
sys.path.insert(0, os.path.dirname(__file__))
from visualize_patient_video import (  # noqa: E402
    draw_frame_number,
    draw_person,
    filter_people,
    get_color_for_mode,
)
```
- `sys`, `os` は既に import 済み。`sys.path.insert` は visualize_patient_video.py が
  `merge_halpe26` を相対 import するために必要（visualize 側と同じ作法）。
- **採用理由**: `--visualize` 未指定でも常に import する（トップレベル）。lazy import
  （関数内 import）は分岐が増え可読性が下がるため不採用。import コストは定数生成のみで軽微。

## 1.3 技術スタック

- Python 3.10、uv 経由実行。
- OpenCV (cv2)：VideoCapture / VideoWriter（コーデック `mp4v`）。既存依存、追加なし。
- numpy：既存依存。
- 新規ライブラリ追加なし。

## 4. 各機能の詳細設計

### 4.1 CLI 引数（追加分）

`main()` の argparse に以下を追加する。すべて `--visualize` 指定時のみ意味を持つ
（無指定時は無視。警告は出さない＝設計判断 ADR-2）。

| 引数 | 型 / action | デフォルト | 説明 |
|------|-------------|-----------|------|
| `--visualize` | store_true | False | MP4 同時出力を有効化 |
| `--vis-out-dir` | str | `"output"` | MP4 出力ディレクトリ |
| `--vis-mode` | str, choices=[filter, all] | `"filter"` | 描画モード |
| `--vis-filter-values` | int, nargs="+" | `[1]` | filter モードで描画する pink_id 値 |
| `--vis-kpt-thr` | float | `0.3` | 描画キーポイント信頼度閾値 |
| `--draw-start` | int | `0` | 描画開始フレーム |
| `--draw-end` | int | `-1` | 描画終了フレーム（-1=最終まで） |
| `--show-bb-index` | BooleanOptionalAction | True | 診断ラベル bb_index 表示 |
| `--show-pink-id` | BooleanOptionalAction | True | 診断ラベル pink_id 表示 |
| `--show-pink-ratio` | BooleanOptionalAction | True | 診断ラベル pink_ratio 表示 |
| `--show-iou-with-prev` | BooleanOptionalAction | True | 診断ラベル iou_with_prev 表示 |
| `--show-selection-score` | BooleanOptionalAction | True | 診断ラベル selection_score 表示 |

- 既存引数（`--video` / `--json-dir` / `--out-dir` / `--roi-mode` / `--kpt-conf-min` /
  `--min-roi-area` / `--min-pink-ratio` / `--hsv-config`）は変更しない。
- **命名の衝突回避**: 描画用の閾値は既存 `--kpt-conf-min`（ROI 構築用）と別物なので
  `--vis-kpt-thr` とする。MP4 出力先は既存 `--out-dir`（JSON 用）と別物なので
  `--vis-out-dir` とする。

`debug_flags` 辞書は visualize と同一構造で組み立てる:
```python
debug_flags = {
    "bb_index": args.show_bb_index,
    "pink_id": args.show_pink_id,
    "pink_ratio": args.show_pink_ratio,
    "iou_with_prev": args.show_iou_with_prev,
    "selection_score": args.show_selection_score,
}
```

### 4.2 データフロー

- 入力フレーム: `frame_bgr` … numpy.ndarray, shape=(H,W,3), dtype=uint8, BGR（既存 L412 で取得）。
- 描画対象 person: `content["people"]` の各 dict（pink_id / pink_ratio / bb_index /
  iou_with_prev / selection_score / bbox / pose_keypoints_2d を保持。L487-500 で付与済み）。
- 出力: MP4（fps=元動画 fps、解像度=元動画解像度、コーデック mp4v）。

### 4.3 オプトイン分岐と VideoWriter 初期化

`cap` オープン成功後（既存 L393 付近の後）、ループ開始前に:
```python
writer = None
if args.visualize:
    os.makedirs(args.vis_out_dir, exist_ok=True)
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    video_stem = Path(args.video).stem
    out_name = f"vis_pink_id_{args.vis_mode}_{video_stem}.mp4"
    vis_out_path = os.path.join(args.vis_out_dir, out_name)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(vis_out_path, fourcc, fps, (width, height))
    if not writer.isOpened():
        print(f"ERROR: Failed to open VideoWriter: {vis_out_path}")
        sys.exit(1)
    print(f"Visualize: ON -> {vis_out_path}")
    print(f"  mode={args.vis_mode}, filter_values={args.vis_filter_values}, "
          f"draw_range={args.draw_start}-{'end' if args.draw_end == -1 else args.draw_end}")
```
- `--visualize` 無指定時は `writer is None`。以降の描画・write・release はすべて
  `writer is not None` ガードでスキップする ⇒ 完全後方互換（FR-008）。

### 4.4 動画 1 回読み（FR-004）

既存のフレームループ（`while True: ret, frame_bgr = cap.read()`）をそのまま使う。
新たな VideoCapture は作らない。描画は同ループ内、JSON 書き出し（既存 L504）の直後に行う。

### 4.5 描画ブロック（既存 JSON 書き出し直後に挿入）

`write_json_frame(out_path, content)` の直後に以下を挿入:
```python
if writer is not None:
    in_draw_range = frame_idx >= args.draw_start and (
        args.draw_end == -1 or frame_idx <= args.draw_end
    )
    if in_draw_range:
        draw_frame_number(frame_bgr, frame_idx)
        visible = filter_people(
            people, "pink_id", args.vis_mode, args.vis_filter_values
        )
        for person in visible:
            id_value = person.get("pink_id", -1)
            color = get_color_for_mode(id_value, args.vis_mode)
            draw_person(
                frame_bgr, person, color, "pink_id",
                args.vis_kpt_thr, debug_flags,
            )
        writer.write(frame_bgr)
```
- `people` は既存ループで取得済みの `content["people"]`（L432）。pink_id 等は付与済み。
- `frame_bgr` は描画で in-place 改変される。ROI 切り出し（既存 L455/470）は描画より前に
  完了しているため、改変が pink_id 計算に影響しない。
- **id_type に "pink_id" を渡す**ことで、draw_person 内のラベルが `pid:<value>` 形式になる
  （ID_TYPE_SHORT["pink_id"]="pid"、FR-002）。
- **範囲判定方式の注記**: `visualize_patient_video.py` は `cap.set(CAP_PROP_POS_FRAMES, draw_start)`
  でシークしてから `frame_idx > draw_end: break` する方式（同 L277-288）。本統合は pink_id 計算の
  連続性のためシークせず、全フレームを計算しつつ `in_draw_range` で MP4 書き込みのみ抑制する
  別方式とする。一致させるのは境界含意（両端 inclusive）のみ。出力 MP4 のフレーム数は両方式で
  同一になる。

ループ終了後、`cap.release()` の近くに:
```python
if writer is not None:
    writer.release()
```

### 4.6 ファイル・出力規約

- MP4 パス: `<vis-out-dir>/vis_pink_id_<vis-mode>_<video_stem>.mp4`
  - 例: `output/vis_pink_id_filter_camSony1_S.mp4`
- `vis-out-dir` は `os.makedirs(..., exist_ok=True)` で作成（既存 out-dir と独立）。
  - 既存 `--out-dir`（JSON 用、required=True）とは無関係。`--vis-out-dir` 未指定時は
    デフォルト値 `"output"` によりカレントディレクトリ直下に `output/` を**新規作成**する
    （JSON と同じ場所には出さない）。実装者はこの暗黙生成を JSON 出力先に変更してはならない。
- サマリ出力（既存ブロック末尾）に `--visualize` 時のみ 1 行追加:
  `print(f"Visualization MP4: {vis_out_path}")`

## 1.7 インターフェース定義

- 本案件で新規の公開関数は作らない（描画は import 関数の呼び出しのみ）。
- import するシグネチャは 1.2 に記載。いずれも変更しない。

## 1.8 ログ・デバッグ設計

- `--visualize` 有効化時: 開始時に出力パス・mode・filter_values・draw 範囲を 2 行で INFO 出力。
- VideoWriter オープン失敗: `ERROR: Failed to open VideoWriter: <path>` を出し `sys.exit(1)`。
- 既存の進捗表示・サマリは維持。サマリに MP4 パスを 1 行追加（visualize 時のみ）。

## エラーハンドリング

| エラー | 検出 | 動作 |
|--------|------|------|
| VideoWriter オープン失敗 | `writer.isOpened()` が False | `ERROR` 出力後 `sys.exit(1)`。VideoWriter 初期化は必ずフレームループ開始前（4.3）に行うため、この時点で JSON はまだ 1 フレームも書いていない＝副作用最小 |
| `--visualize` 無指定で `--vis-*` が明示された | 検出しない | 無視（ADR-2）。警告なし |
| 描画範囲が動画長を超える / start>end | 自動 | 該当フレームが 0 件 → MP4 は 0 フレーム（空動画）。エラーにしない |
| people が空のフレーム | 自動 | frame_number のみ描画して write |

## 境界条件

- `--draw-start 0 --draw-end -1`（デフォルト）: 全フレーム描画。
- `--draw-start 100 --draw-end 199`: MP4 は 100 フレーム。pink_id 計算・JSON 出力は全フレーム
  （シークしない＝連続性維持。bug-003 の「処理範囲を絞らない」方針と整合）。
- people=[]: BB なしフレームを書き込む（frame_number のみ）。
- `--visualize` 無指定: writer 関連コードは全スキップ、出力 JSON は改修前とバイト一致。

## 設計判断の記録（ADR）

- **ADR-1: 統合方式は「postprocess に --visualize 統合」（案1）を採用**。
  - 却下案 A（2 スクリプトを順次呼ぶラッパー新規作成）: 動画 2 回読みのままでワンコマンド化
    しか達成できず、ファイルも増える。
  - 却下案 B（visualize 側に pink_id 計算を逆統合）: 責務が逆転し visualize が肥大化。
  - 採用理由: postprocess のループが描画素材を既に保持しており、動画 1 回読みを最小差分で
    実現できる。描画は import で再利用しコード重複ゼロ。

- **ADR-2: `--visualize` 無指定時に `--vis-*` 等が指定されても警告を出さず無視**。
  - 却下案（argparse のデフォルト値と明示値を区別して WARN）: 判定が煩雑で実装判断を増やす。
  - 採用理由: visualize 単体の挙動と一貫。無害な無視で十分。

- **ADR-3: 描画 ID は pink_id 固定（CLI で切替不可）**。
  - 採用理由: postprocess_pink_id.py 直後に存在する ID は pink_id のみ。track_id /
    pink_track_id は別ステージで付与されるため、本統合の対象外（README スコープ）。

- **ADR-4: 描画関数は import で再利用し visualize_patient_video.py は無変更**。
  - 採用理由: 描画仕様の単一情報源を保ち、二重メンテを避ける。弱い結合（visualize 側の
    関数シグネチャ変更が波及）は許容範囲とする。
