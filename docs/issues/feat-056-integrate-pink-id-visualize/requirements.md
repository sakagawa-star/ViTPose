# feat-056 要求仕様書: postprocess_pink_id.py への確認動画同時出力統合

## 1. プロジェクト概要

### 1.1 何を作るのか
`scripts/postprocess_pink_id.py` に `--visualize` オプションを追加し、pink_id 付与 JSON の
書き出しと同時に、確認用 MP4（BB・スケルトン・pink_id ラベルを元動画にオーバーレイ）を
1 回の実行で出力できるようにする。

### 1.2 なぜ作るのか
現状は `postprocess_pink_id.py` → `visualize_patient_video.py` を毎回 2 コマンド手動実行
しており手間。かつ動画フルスキャンが 2 回走り非効率。これを 1 コマンド・動画 1 回読みに
統合し、作業効率と処理時間を改善する。

### 1.3 誰が使うのか
開発者（本人）。患者同定（pink_id）の結果を目視確認する用途。

### 1.4 どこで使うのか
ローカル PC（uv 環境、Python 3.10）。GPU 不要（cv2 のみ使用、ViTPose 推論は含まない）。

## 2. 用語定義

- **pink_id**: HSV ピンク比率ベースで選択された患者 BB に 1、それ以外に -1 を付与する ID（feat-033）。
- **filter モード**: 指定した ID 値を持つ人物のみ描画する描画モード（visualize_patient_video.py 由来）。
- **all モード**: 全人物を ID ごとに色分けして描画する描画モード（同上）。
- **後方互換**: `--visualize` を指定しない場合、出力 JSON が改修前と完全一致すること。
- 上記用語は機能設計書・コード内でも同一の語で用いる。

## 3. 機能要求一覧

### FR-001: --visualize による MP4 同時出力（オプトイン）
- **概要**: `--visualize` フラグ指定時のみ、pink_id 付与と同時に確認用 MP4 を出力する。
- **入力**: CLI フラグ `--visualize`（store_true、デフォルト False）。
- **出力**: MP4 ファイル 1 本（指定ディレクトリに自動命名で書き出し）。
- **受け入れ基準**:
  - `--visualize` 無指定時は MP4 を出力せず、出力 JSON ディレクトリは改修前と
    `diff -r` で差分 0（後方互換、FR-008 と重複確認）。
  - `--visualize` 指定時、MP4 が 1 本生成され、cv2.VideoCapture で開けて、
    フレーム数が「実際に `cap.read()` が成功したフレームのうち描画範囲（FR-005）内の数」と
    一致する（元動画メタデータの CAP_PROP_FRAME_COUNT ではなく実読み込みフレーム基準）。

### FR-002: 描画 ID は pink_id 固定
- **概要**: 統合版が描画する ID 種別は `pink_id` のみとする（CLI で変更不可）。
- **入力**: なし（固定）。
- **出力**: BB ラベルに `pid:<value>` 形式で pink_id を表示。
- **受け入れ基準**: 出力 MP4 の BB ラベルが `pid:` プレフィックスで pink_id 値を示す。

### FR-003: 描画モード選択
- **概要**: `--vis-mode {filter, all}` で描画モードを選べる。デフォルトは `filter`。
  filter 時の対象 ID 値は `--vis-filter-values`（int 複数、デフォルト `[1]`）で指定する。
- **入力**: `--vis-mode`（既定 filter）、`--vis-filter-values`（既定 [1]）。
- **出力**: filter 時は指定 pink_id 値の人物のみ、all 時は全人物を色分け描画。
- **受け入れ基準**:
  - `--vis-mode filter --vis-filter-values 1` で pink_id=1 の人物のみ描画される。
  - `--vis-mode all` で全人物が描画される。

### FR-004: 動画読み込みは 1 回
- **概要**: pink_id 計算に使うフレーム BGR をそのまま描画にも流用し、動画フルスキャンを
  1 回に抑える。
- **入力**: なし（内部実装要件）。
- **出力**: なし。
- **受け入れ基準**: `--visualize` 指定時、`cv2.VideoCapture` のオープンは 1 回のみ
  （コードレビューで確認）。

### FR-005: 描画範囲指定
- **概要**: `--draw-start` / `--draw-end` で MP4 に書き出すフレーム範囲を指定できる。
  pink_id 計算（連続性を保つため）は範囲によらず常に全フレームで実行する。
  両端 inclusive（`draw-start <= frame_idx <= draw-end`）。
  なお `visualize_patient_video.py` は `cap.set()` でシークする方式だが、本統合は
  シークせず全フレームを pink_id 計算しつつ範囲外フレームの MP4 書き込みのみ抑制する別方式
  であり、一致させるのは描画範囲の境界含意（両端 inclusive）のみとする。
- **入力**: `--draw-start`（int、既定 0）、`--draw-end`（int、既定 -1=最終フレームまで）。
- **出力**: MP4 には `draw-start`〜`draw-end` のフレームのみ書き込まれる。範囲外フレームは
  pink_id 計算は行うが MP4 には書かない。
- **受け入れ基準**:
  - `--draw-start 100 --draw-end 199` で MP4 が 100 フレームになる。
  - 同条件で出力 JSON は全フレーム分が生成される（pink_id 計算は範囲非依存）。

### FR-006: 診断ラベル表示フラグ
- **概要**: visualize_patient_video.py と同じ 5 個の診断フィールド表示フラグ
  （`--show-bb-index` / `--show-pink-id` / `--show-pink-ratio` / `--show-iou-with-prev` /
  `--show-selection-score`、各 `BooleanOptionalAction`、デフォルト全 ON）を持つ。
- **入力**: 上記 5 フラグ。
- **出力**: BB 内部に診断ラベル（`idx=... pid=... r=... iou=... s=...`）を描画。
- **受け入れ基準**: `--no-show-pink-ratio` 指定時、ラベルから `r=` 部分が消える。

### FR-007: 描画パラメータ・出力先
- **概要**: 描画キーポイント閾値 `--vis-kpt-thr`（float、既定 0.3）と、MP4 出力ディレクトリ
  `--vis-out-dir`（既定 `output`）を指定できる。MP4 ファイル名は
  `vis_pink_id_<vis-mode>_<video_stem>.mp4` で自動生成する。
  `--vis-kpt-thr` は描画専用で、既存 `--kpt-conf-min`（keypoint-rect ROI 構築用）とは独立。
  `--vis-out-dir` は既存 `--out-dir`（JSON 出力先、required）とは独立で、未指定時は
  カレントディレクトリ直下に `output/` を新規作成する（JSON と同じ場所には出さない）。
- **入力**: `--vis-kpt-thr`、`--vis-out-dir`。
- **出力**: `<vis-out-dir>/vis_pink_id_<mode>_<stem>.mp4`。
- **受け入れ基準**: 既定で（`--vis-out-dir` 未指定時）カレント直下に
  `output/vis_pink_id_filter_<stem>.mp4` が生成される。

### FR-008: 後方互換
- **概要**: `--visualize` を指定しない場合、本改修前と完全に同一の動作（出力 JSON・標準出力
  サマリ）を保つ。
- **入力**: `--visualize` 無指定。
- **出力**: 改修前と一致。
- **受け入れ基準**: 同一入力で `--visualize` 無指定実行の出力 JSON ディレクトリが、
  `git stash` で戻した改修前バージョンの出力と `diff -r` で差分 0。

## 4. 非機能要求

- **パフォーマンス**: `--visualize` 指定時、動画フルスキャンは 1 回（FR-004）。従来の
  「postprocess + visualize 別実行」に対し、動画読み込み・JSON 再読み込み 1 周分の時間を削減する。
- **対応環境**: Linux、Python 3.10、uv 経由実行。GPU 不要。
- **信頼性**: MP4 出力（VideoWriter）に失敗しても、JSON 出力は完了している状態を保つ
  （描画は JSON 書き出し後に行うため）。VideoWriter のオープン失敗時はエラー終了する（FR は下記制約参照）。

## 5. 制約条件

- 描画は `scripts/visualize_patient_video.py` の既存関数を import して再利用する
  （描画コードの重複実装を禁止）。
- `scripts/visualize_patient_video.py` は本案件で**変更しない**。
- MP4 出力は cv2.VideoWriter（コーデック `mp4v`）を用いる（visualize_patient_video.py と同一）。
- pink_id 計算ロジック・既存 CLI（`--roi-mode` / `--hsv-config` / `--min-pink-ratio` 等）の
  挙動は変更しない。
- 新規ライブラリは追加しない。

## 6. 優先順位（MoSCoW）

- **Must**: FR-001, FR-002, FR-003, FR-004, FR-007, FR-008
- **Should**: FR-005, FR-006
- **MVP**: FR-001/002/003/004/007/008（`--visualize` で pink_id=1 を filter 描画した MP4 を
  動画 1 回読みで出力、無指定時は完全後方互換）。FR-005/006 は visualize 互換のための付加機能。
