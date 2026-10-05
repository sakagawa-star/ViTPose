# CHANGELOG

## リリース履歴

案件完了ごとに、日付見出しの下へ完了内容を記録する。新しい日付を上に置く。

update-001 より前に完了した案件の記録は、update-001 で `CLAUDE.md`「完了済み案件」節から移したものである。移動元に記述がなかった完了案件（bug-001・bug-002・bug-005）は記載していない。完了案件の一覧は `docs/BACKLOG.md` を参照する。

### 2026-10-05

- **update-002**: 開発テンプレート最新版の取り込み（2/2）（2026-10-05完了、`CLAUDE.md` の開発フロー・運用ルールをテンプレート〔DEV_TEMPLATE `ffd2c49`〕に更新: 機能追加フローのロードマップ・マイルストーン化、ドキュメント更新フロー・実験プロトコルの導入、Codex レビューを Herdr 対話方式〔1回ゲート型〕へ移行、実装の Sonnet 委任・git 操作の Opus 委任、行き詰まり検出。`AGENTS.md`・`docs/HERDR_SETUP.md`・`docs/codex-exec-ubuntu24-bwrap-fix.md` を導入し、`docs/BUGFIX_STANDARD.md`・`docs/DESIGN_STANDARD.md`・`docs/REVIEW_CRITERIA.md` を更新。自動テストの置き場を `tests/scripts/` に定めた。Codex レビュー 4回で高・中ゼロに収束）
- **update-001**: 開発テンプレート最新版の取り込み（1/2）（2026-10-05完了、`docs/PROJECT_KNOWLEDGE.md` と `docs/CHANGELOG.md` を新設し、`CLAUDE.md` の知識節・完了済み案件節をそれぞれへ無改変で転記。`docs/TECH_STACK.md` を実環境に合わせて全面更新し、`CLAUDE.md` の技術スタック節をポインタ化。`docs/BACKLOG.md` にステータス凡例を導入し、凍結6案件を On Hold に統一、完了日一覧の欠落8行を補完。Codex レビュー 6回で高・中ゼロに収束）
- **feat-062**: 2 パス推論構成のままポーズ推定を高速化（backbone fp16 + CUDA Graph）（2026-10-05完了、`scripts/pose_accel.py` を新規作成し、`run_halpe26_pipeline_yolo11.py` に `--pose-fp16` / `--cuda-graph`（いずれも既定 ON）と `--cuda-graph-max-batch`（既定 8）を追加。分割プロファイルでポーズ推定時間の 95% が ViT-H backbone forward と特定し、backbone のみ fp16 化（head/decode は fp32）と、入力形状ごとの CUDA Graph 再生を採用。CUDA Graph は fp16 で顕在化する CPU 側のカーネル発行遅延を回避するためのもので、fp32 単体では効果 3%。`AcceleratedBackbone` が `model.backbone` を差し替える方式で `mmpose/` は無変更、両機構 OFF ではモデルに触れない。N=1 は起動時に事前キャプチャ、N≥2 は遅延キャプチャ、max_batch 超過は eager、キャプチャ失敗は exit 1（`--no-cuda-graph` で回避）、`--device cpu` では自動無効化。camSony1_S 900 フレームで WB+AIC 100.5 → 30.6 ms/frame、全体 8.5 → 21.3 fps（2.5 倍）、fp16 の出力差は確信点の 2 px 超 0.50%。camSony1_L 321K フレームは 21.0 fps / 4 時間 15 分で完走し下流 3 ステージも通過。flip test 無効化（出力が変わるため利用者判断で不採用）・複数フレームのバッチ化（GPU はバッチ 1 で飽和）・CPU 後処理見直し・YOLO11x fp16 は不採用。要求仕様・設計を Codexレビュー 3 往復で高中低ゼロ化、実装も Subagentレビュー（高中ゼロ）。AC-003-1 は fp32 GPU 推論の実行間の非決定性（改修前コード同士でも confidence の最下位桁が揺れる）によりバイト一致が成立しないと判明し、「座標・bbox・bbox_score 一致、confidence 最大差 1e-4 以下」に改定。scripts/README.md / CLAUDE.md を整合更新）

### 2026-06-24

- **feat-061**: YOLO 検出ゼロ時の固定 ROI フォールバック（2026-06-24完了、`scripts/run_halpe26_pipeline_yolo11.py` に `--fallback-roi x1 y1 x2 y2` / `--fallback-score`（既定 1.0）を追加。YOLO11x が `bbox_thr` 以上の person BB を 1 件も返さなかったフレームに限り、CLI で与えた固定 ROI を 1 個の BB として ViTPose（WB+AIC）に流す。既定無効（`--fallback-roi` 指定時のみ有効）で、1 件以上検出されたフレームには介入しない。feat-060 の診断で、キーポイント未出力の原因が YOLO の検出失敗（`--bbox-thr` を下げても検出ゼロ）と確定したことを受けた対処。ROI 検証は基本検証（非負・`x1<x2` かつ `y1<y2`）とクリップ検証（画像範囲へのクリップ、縮退時は exit 1）の 2 段で、いずれもモデル初期化より前に完了（ADR-4）。注入 BB は推論経路では特別扱いせず素通しし（ADR-3）、`scripts/halpe26_to_openpose.py` の `halpe26_to_openpose_json` に任意引数 `fallback_flags` を追加して注入由来の person に `"fallback": true` を付与（ADR-6、既存 `stable_ids` と同パターン）。YOLO 呼び出しの `conf` は変更しない（ADR-5）。処理終了時に発動フレーム数を 1 行サマリ出力。`--fallback-roi` 未指定時は従来と後方互換。複数 ROI・ROI 自動推定・他検出器版パイプラインへの展開は対象外）

### 2026-06-23

- **feat-060**: 静止画1枚のポーズ推定診断ツール（2026-06-23完了、`scripts/diagnose_pose.py` を新規作成。1枚の静止画でパイプラインがキーポイントを出力しない原因を「YOLO の検出失敗」か「ViTPose 自体の推定失敗」かに切り分ける CLI 診断ツール。①YOLO11x で person 検出し総数/閾値以上/除外数と各BBの score を出力 ②画像全体を1BBとして ViTPose（WB+AIC）に流し HALPE26 全26点の confidence と有効点数（`conf > kpt_thr` 超過判定、`draw_halpe26` と統一）を出力 ③左=YOLO検出BB / 右=全画像1BB枠+スケルトン の2パネル PNG 出力 ④総合判定 VERDICT を出力。核心は `estimate_halpe26_fullframe_safe`＝既存 `analyze_clothing_color.py:estimate_halpe26_fullframe` が推論空時に `sys.exit(1)` するのを流用せず、空・OOM以外の推論例外を None に畳み込み FAILED 記録して切り分け結論を必ず出す分離実装（ADR-1）。エラーを致命（exit 1: 画像読込不可・モデルロード失敗・PNG保存失敗・CUDA OOM・device不正）と推論失敗（exit 0・FAILED記録）の2分類に明確化。`_resolve_device` は `run_halpe26_pipeline_yolo11.py` から import せず自前定義（ADR-3、副作用回避）、SystemExit を `[ERROR]` 整形して exit 1。`merge_halpe26` から `HALPE26_NAMES`/`merge_to_halpe26`/`draw_halpe26`/`draw_bbox` を再利用、全画像1BB枠のみ `cv2.rectangle`（draw_bbox はラベルが画像外になるため）。要求仕様・設計を **Codexレビュー** 3往復で高1中2→中3→高中ゼロ化、実装も Subagentレビュー（高中ゼロ）。既存 merge_halpe26.py / analyze_clothing_color.py / run_halpe26_pipeline_yolo11.py / postprocess_pink_id.py は無変更。scripts/README.md / CLAUDE.md を整合更新）

### 2026-06-01

- **feat-059**: analyze_clothing_color.py の色非依存レンジ提案（有彩色・白・黒・灰対応）（2026-06-01完了、`scripts/analyze_clothing_color.py` を有彩色専用から色非依存化。白服（E0049）で対象を追える特徴量を出せない問題に対し、ROIの chroma_ratio を `--chroma-regime-min`（既定0.4）で判定して chromatic / achromatic の2レジームに自動分岐。achromatic は新関数 `propose_achromatic_ranges` で色相H全域・S/V上下限を全画素percentileで囲む（白＝低S高V・黒＝低S低Vが分布に追従）。chromatic は既存 `propose_hsv_ranges` / `propose_ranges_from_chroma` を無変更で呼び後方互換維持（提案行の前に regime 行が1行増えるのみ）。新規関数 `extract_all_hsv` / `decide_color_regime` / `propose_achromatic_ranges`、`render_analysis_png` に `regime` / `all_hsv` 引数追加（achromatic時は全画素ヒストグラム＋S/V境界線、境界は proposed_ranges[0] から取得）。単一・複数画像モード両対応（複数はプール全体のchroma_ratioで1回判定し全画像同一レジーム）。方式B（分類せず分布から直接percentile包囲）を**消去法で**採用（方式A=有彩/白/黒/灰分類は信頼できる閾値を決められず前提が成立しないため却下）。デフォルト閾値0.4は実測（白E0049 chroma_ratio最大0.247 / ピンクE0014最小0.713）の両側マージンから決定、`--sat-min`/`--val-min` 依存をhelpに明記。要求仕様・設計を **Codexレビュー**（CLAUDE.md新ルール、`codex exec --dangerously-bypass-approvals-and-sandbox`）3往復で高1中2→中1→高中ゼロ化、実装差分も Subagentレビュー（高中ゼロ）。AC全PASS：ピンク単一/複数の後方互換 `git stash` 突合でJSONバイト一致・提案行一致、白服 achromatic で proposed_ratio 0.83〜0.98、閾値切替・help注記確認。既存 merge_halpe26.py / postprocess_pink_id.py は無変更。scripts/README.md / CLAUDE.md を整合更新。判別力（白服対象を他人・白い寝具と区別して動画で正しく選べるか）の検証は別案件）

### 2026-05-28

- **feat-055**: analyze_clothing_color.py の複数画像入力・プール提案・閾値検証対応（2026-05-28完了、`scripts/analyze_clothing_color.py` の位置引数を `nargs='+'` 化し、2枚以上で「複数画像モード」に分岐。全画像の胴体ROIクロマ画素を `np.concatenate` でプール（BGR往復変換なし＝画素脱落ゼロ）し循環統計で全画像を覆う単一レンジを提案、各画像 `pink_ratio` を `--threshold`（既定0.03、`ratio > threshold` でPASS・==はFAIL）と照合してレポート（表示のみ、exit 0）。`propose_hsv_ranges` の循環統計コアを `propose_ranges_from_chroma(Hc,Sc,Vc,percentile)` に抽出（pure refactor、戻り値4要素不変）。フェーズ順序＝1)全画像推論・ROI・stats収集 2)プール提案 3)閾値検証 4)画像ごとPNG 5)統合JSON。PNG/JSON出力は提案後なので読込/推論失敗時は出力ファイルなし。複数画像モードのPNGは画像ごと `<stem>_color_analysis.png`、JSONは統合1個（`--json-out` or `<first_stem>_pooled_hsv_config.json`、`min_pink_ratio`=0.03固定、`--out`は無視＋WARN）。1枚指定時は単一画像モードで feat-054 と完全一致（AC-001-1：`git stash` 突合で推奨/ratio行一致・JSONバイト一致）。要求仕様・設計を Subagentレビュー1往復で高1中5低1→高中ゼロ化、実装差分も Write前 Subagentレビュー。`testdata/E0014/` 3枚で全AC PASS（プール推奨 `[((0,21,117),(12,255,255)),((163,21,117),(179,255,255))]`、3枚 ratio=0.5928/0.7701/0.7049 全て>0.03でALL PASS、生成JSONは手書き `scripts/conf/E0014.json` と一致）。既存 merge_halpe26.py / postprocess_pink_id.py は無変更）
- **feat-056**: postprocess_pink_id.py への確認動画同時出力統合（--visualize）（2026-05-28完了、`scripts/postprocess_pink_id.py` に `--visualize` を追加し、pink_id 付与 JSON 書き出しと同時に確認用 MP4（BB・スケルトン・pink_id ラベルをオーバーレイ）を出力。描画は `visualize_patient_video.py` の `draw_person` / `filter_people` / `get_color_for_mode` / `draw_frame_number` を import 再利用し、`visualize_patient_video.py` は無変更。動画フルスキャンを 1 回に集約（従来の postprocess→visualize 別実行の 2 回読みを削減）。描画 ID は pink_id 固定、デフォルト filter モード（pink_id=1）。追加CLI: `--vis-out-dir` / `--vis-mode {filter,all}` / `--vis-filter-values` / `--vis-kpt-thr` / `--draw-start` / `--draw-end` / `--show-*` 5フラグ（visualize 互換）。`--visualize` 無指定時は完全後方互換（※bug-004 でデフォルトON化し、後方互換は `--no-visualize` 指定時に変更）。MP4名は `vis_pink_id_<mode>_<stem>.mp4`。pink_id 計算は描画範囲によらず常に全フレーム実行、`--draw-start/--draw-end` は MP4 書き込み範囲のみ制限（出力 JSON は常に全フレーム）。要求仕様・設計を Subagentレビュー1往復で高0中2低3→全反映、実装差分も Write前 Subagentレビューで高中ゼロ。camSony1_S 900フレームで AC 全PASS：後方互換 `git stash` diff -r 差分0、描画範囲 0-99 で MP4 100フレーム・出力 JSON 全900フレーム・JSON内容は後方互換版と一致、処理0.6秒（1493fps、描画100フレームのみ）。既存 visualize_patient_video.py / merge_halpe26.py は無変更）
- **feat-057**: postprocess_pink_id.py の --out-dir 自動導出（任意化）（2026-05-28完了、`scripts/postprocess_pink_id.py` の `--out-dir` を `required=True` から任意化し、未指定時は `os.path.normpath(args.json_dir) + "_pink_id"` を自動導出（INFOログ1行出力）。既存の上書き防止チェック（json-dir と out-dir 同一禁止）は維持、接尾辞付与により自動導出値は自然に非抵触。要求仕様・設計を Subagentレビュー（高中ゼロ）、実装差分も Write前 Subagentレビュー。後方互換: `--out-dir` 明示時は従来と完全一致。動画出力先 `--vis-out-dir` とは独立で連動しない）
- **bug-004**: postprocess_pink_id.py の確認動画がデフォルトで出力されない（feat-056 仕様漏れ）（2026-05-28完了、`scripts/postprocess_pink_id.py:381` の `--visualize` を `action="store_true"`（既定 False）から `argparse.BooleanOptionalAction` + `default=True` に変更し、確認動画 MP4 をデフォルトON化（`--no-visualize` で抑制）。feat-056 が確認動画をオプトイン設計にしていた仕様漏れの修正。分岐ロジック（`if args.visualize:`）・出力先 `--vis-out-dir`（既定 output）は不変。feat-056 の requirements.md / design.md を本文更新＋変更履歴追記、scripts/README.md 3箇所・CLAUDE.md を整合更新（方針: 過去案件ドキュメントは現行挙動に本文更新し末尾に変更履歴1行追記）。investigation.md を Subagentレビュー（高中ゼロ）。リグレッション注意: デフォルトで全フレーム描画になり大規模動画では処理時間増、`--no-visualize` で従来の JSON のみ高速処理に戻せる。feat-057 の手動テストはこの修正で動画出力を確認できるようになり完了）
- **feat-058**: postprocess_pink_id.py の確認動画保存先デフォルトを out-dir の親に変更（2026-05-28完了、`scripts/postprocess_pink_id.py` の `--vis-out-dir` を `default="output"` から `default=None` に変更し、未指定時は `os.path.dirname(os.path.normpath(args.out_dir)) or "."`（out-dir の親、末尾スラッシュは normpath で吸収・親なし相対パスは `.` フォールバック）を出力先とする。挿入位置は feat-057 の `--out-dir` 自動導出後・`os.makedirs(args.out_dir)` 直後。feat-056 の既定 `output` 固定がテスト用ディレクトリで本番動画と混ざる問題を解消。`--vis-out-dir` 明示時はその値を優先（後方互換）。`--no-visualize` 時は導出するが未使用で無害。要求仕様・設計を Subagentレビュー（高中ゼロ、低3反映）、実装差分も Write前 Subagentレビュー（高中ゼロ）。scripts/README.md / CLAUDE.md を整合更新）

### 2026-05-27

- **feat-054**: analyze_clothing_color.py の HSV 設定ファイル（JSON）出力対応（2026-05-27完了、`scripts/analyze_clothing_color.py` に `--json-out` を追加し、`propose_hsv_ranges()` の推奨レンジを feat-053 互換 JSON（`fixed_hsv_ranges` + `min_pink_ratio`）として常時書き出す。案C の機能②＝手写経撲滅。`min_pink_ratio` は固定 0.03（`postprocess_pink_id.MIN_PINK_RATIO` を import、静止画では動画BB比率の適切値を決められないため実運用は `--min-pink-ratio` で再調整）。新規関数 `build_hsv_config_dict` / `write_hsv_config`。JSON は PNG 保存後に書き出し（書込失敗でも診断PNGを保全）、推奨レンジ空時は JSON 不出力＋`[WARN]`。整形は `scripts/conf/*.json` と同じ compact 形式（1レンジ=1行）。要求仕様・設計を Subagentレビュー2往復で高中ゼロ化、実装差分も Write前 Subagentレビュー。AC-001（2キーのみ・`load_hsv_config` 通過・整数維持・stdout一致）/ AC-002（デフォルトパス・INFOログ）/ AC-003（空レンジ時不出力）全PASS。E0014-01.png で生成 JSON が手写経の `scripts/conf/E0014.json` とバイト一致を確認。既存 stdout/PNG 出力・`postprocess_pink_id.py` / `merge_halpe26.py` は無変更）
- **feat-053**: postprocess_pink_id.py の HSV 設定ファイル読み込み対応（2026-05-27完了、`scripts/postprocess_pink_id.py` に `--hsv-config` を追加し、ハードコードの `FIXED_HSV_RANGES` / `min_pink_ratio` を JSON 設定ファイルから差し替え可能化（feat-052 推奨レンジを実運用へ反映する案C の機能①＝コア）。設定ファイルは `fixed_hsv_ranges` + `min_pink_ratio` の2キー必須（B-1）、`min_pink_ratio` 優先順位は CLI明示 > 設定ファイル > 既定0.03（A-1、`--min-pink-ratio` の default を None 化して明示判定）。`compute_pink_ratio(roi, ranges=None)` で後方互換維持、`FIXED_HSV_RANGES` / `MIN_PINK_RATIO` 定数は残置（analyze_clothing_color.py / plot_pink_ratio_timeline.py の import 互換）。要求仕様・設計を Subagentレビュー2往復で高中ゼロ化、実装差分も Write前 Subagentレビュー。AC-001-1（`git stash` で改修前と camSony1_S 900フレーム `diff -r` 差分0）/ AC-001-2 / AC-002（不正設定で exit 1）/ AC-003（優先順位）/ AC-005（サマリ表示）全PASS。サンプル `docs/issues/feat-053-pink-id-hsv-config/example_hsv_config.json`、対象向け設定 `scripts/conf/E0014.json` を配置。機能②（analyze_clothing_color.py の同スキーマ JSON 出力）は後続案件）

### 2026-05-26

- **feat-052**: 服パッチ静止画からの服色特徴量分析・HSVレンジ提案ツール（2026-05-26完了、`scripts/analyze_clothing_color.py` を新規作成。服パッチ静止画1枚から画像全体1BBで ViTPose 推論→HALPE26 胴体4点で ROI 切り出し→ROI内 HSV を測定し、`postprocess_pink_id.py` 用の推奨 `FIXED_HSV_RANGES`・S/V下限を提案する CLI 診断ツール。循環統計で色相環またぎに対応、S/V下限のみデータ駆動（上限255固定）。要求仕様・設計を Subagentレビュー3往復で高中ゼロ化、実装コードも Write前 Subagentレビュー。E0014-01.png（本番 pink_id 取りこぼし実例）で current pink_ratio=0.0099→proposed=0.6046（約61倍、推奨レンジ `[((153,21,125),(179,255,255)),((0,21,125),(12,255,255))]`）を確認。既存 merge_halpe26.py / postprocess_pink_id.py は無変更。推奨レンジの postprocess_pink_id.py への実反映は別案件）

### 2026-05-15

- **feat-048**: 不一致フレーム可視化の情報再設計（2026-05-15完了、`scripts/visualize_disagreement_frames.py` を全面書き直し。CSV 経路を廃止し bb / kp 両 JSON ディレクトリ直読みに刷新。`only_bb` ケースで bb 選択人物の `bb_index` を kp 側 JSON で線形検索して `roi_bbox` を取得 → 不一致 94% を占める only_bb ケースでも kp-rect ROI 描画可能に。`build_attempted_roi`（area チェック省略版）を新規追加し fail_area でも矩形を描画。状態別色分け（ok=黄、fail_area=オレンジ、fail_kpt=描画なし）、胴体 4 点に LS/RS/LH/RH ラベル + 高信頼=塗りつぶし円/低信頼=× マーク、idx ラベルを BB 右上角外側に配置してキーポイントとの重なり回避）
- **feat-051**: selection_score 範囲によるフレーム抽出 PNG ツール（2026-05-15完了、`scripts/extract_score_range_frames.py` を新規作成。kp モード JSON と動画から、フレーム max selection_score が指定範囲 `[score-min, score-max]`（両端含む、`==` 許容）にあるフレームを抽出し PNG 出力。`selection_score=None` のときは `pink_ratio` で代替するローカルフォールバック規約（feat-041 の null 規約は JSON 形式不変）。出力 PNG は元動画フレームの上に高さ 60 px の黒帯バナーを `np.vstack` で積層し、その内側に Frame / effective_s / range / ROI 状態を白文字描画（BB ラベルと衝突しない構造、AC-004-5）。1 フレーム 1 person（max s）のみ描画。BB 上部ラベル `pink_id:` / `score:` は v2 で省略（診断ラベル `idx pid r iou s` と近接して可読性低下のため）。--min-pink-ratio 閾値検討用途で camSony1_L で動作確認、ピンク服 vs 灰色服の pink_ratio が同水準（~0.055）になる構造的問題が判明 → HSV レンジ調整 or 学習ベース移行の検討材料を提供）

### 2026-05-14

- **feat-050**: postprocess_pink_id.py に --min-pink-ratio CLI 引数追加（2026-05-14完了、`MIN_PINK_RATIO = 0.03` 定数を CLI 引数 `--min-pink-ratio`（値域 `[0.0, 1.0]`、デフォルト 0.03）で外部化。`select_pink_bbox` シグネチャに `min_pink_ratio: float` 引数追加。サマリに `Min pink ratio threshold: 0.XXX` を 1 行追加。`git stash` ベースで改修前後の `diff -r` 差分 0 を確認、AC-001-1 PASS）

### 2026-05-13

- **feat-046**: postprocess_pink_id.py のキーポイントベース ROI 対応（2026-05-13完了、`postprocess_pink_id.py` に `--roi-mode {bb, keypoint-rect}` / `--kpt-conf-min` / `--min-roi-area` を追加。`build_keypoint_rect_roi` 関数で HALPE26 胴体 4 点（5/6/11/12）から軸並行最小矩形 ROI を構築（K-2 方式 = 信頼点 2 個以上、F2 厳しめ = 構築失敗時 pink_ratio=0）。bb モードは既存 JSON と完全互換、keypoint-rect モード時のみ `roi_mode` / `roi_bbox` フィールドを追加。camSony1_S 全 900 フレームで AC-003-1 `diff -r` 差分 0 確認）
- **feat-047**: ROI モード比較・可視化ツール（2026-05-13完了、`scripts/compare_roi_modes.py` で α-1 散布図 + 不一致 CSV を出力、`scripts/visualize_disagreement_frames.py` で不一致フレームの目視確認 PNG を出力。CSV 経路は feat-048 v2 で JSON 直読みに刷新されたが本スクリプト自体は残置）

### 2026-04-30

- **feat-041**: postprocess_pink_id.py に選択スコア診断フィールド追加（2026-04-30完了、`scripts/postprocess_pink_id.py` の pink_id 付与ループに 3 フィールド追加: `bb_index: int`、`iou_with_prev: float | null`、`selection_score: float | null`。連続性切れ時は null（案 B、「前 BB なし」と「IoU=0」の区別を保持）。改修前後で `pink_id` / `pink_ratio` 完全一致を確認、camSony1_L で処理時間 −0.6%。当初動機の IoU 連続性ボーナスによる誤選択は動画再確認の結果、過去の観察ミスの可能性が高いと判明したが、診断フィールド自体は将来の解析ツールとして汎用価値がある）
- **feat-042**: visualize_patient_video.py に pink 選択診断フィールド描画拡張（2026-04-30完了、既存 `scripts/visualize_patient_video.py` を拡張。BB 内部 (x1+4, y1+16) に診断 5 フィールド（`bb_index` / `pink_id` / `pink_ratio` / `iou_with_prev` / `selection_score`）を 1 行描画。フィールド別 `--show-X` / `--no-show-X` フラグ（`argparse.BooleanOptionalAction`、デフォルト全 ON）。フォントスケール 0.45、小数 3 桁、整数フィールドは `int(...)` ラップ、5 フィールドすべて null 安全。`build_debug_label` 7 ケース全パス）
- **bug-003**: visualize_patient_video.py の --draw-start/--draw-end が出力動画範囲を制限しない（2026-04-30完了、`scripts/visualize_patient_video.py` のフレームループを修正。`cap.set(cv2.CAP_PROP_POS_FRAMES, draw_start)` でシーク + ループ冒頭で `draw_end` 到達時に break。`in_draw_range` フラグ廃止。出力 MP4 のフレーム数 = 指定範囲のみ。テスト 1（1397 フレーム）/ 4（リグレッション 900 フレーム）/ 5（`--draw-start 100` で 800 フレーム）すべて期待通り。処理時間 30 分超 → 4.8 秒に短縮）

### 2026-04-29

- **feat-040**: pink_ratio 時系列可視化グラフ（2026-04-29完了、`scripts/plot_pink_ratio_timeline.py` を新規作成。feat-039 改修済み JSON から 4 パネル構成の PNG 時系列グラフを出力。Panel 1: 全 BB の pink_ratio 散布図 + 閾値ライン、Panel 2: pink_id=1 有無、Panel 3: BB 数内訳、Panel 4: 「選択 BB ratio − 次点 BB ratio」差分（< 0.05 のフレームは赤背景帯で強調、負値含む）。次点 BB は全 BB の pink_ratio 降順 2 位（案 a-2、選択 BB を含む全体ランキング）。`--frame-start` / `--frame-end` で部分描画可。camSony1_L 321K フレームで 37.4 秒 / Frames with close margin = 4108）

### 2026-04-21

- **feat-039**: postprocess_pink_id.py に pink_ratio フィールド追加（デバッグ用）（2026-04-21完了、`scripts/postprocess_pink_id.py` の pink_id 付与ループに 1 行追加し、各 `people[i]` に HSV ピンク画素比率 `pink_ratio`（float、値域 [0.0, 1.0]）を保存。選択ロジック・CLI・サマリ出力は未変更。閾値 `MIN_PINK_RATIO=0.03` の妥当性検証と feat-037 で検出された誤検出区間の原因解析を、ポストプロセス再実行なしで行えるようにする。下流スクリプト（feat-035/036/037/038）は生 dict 保持設計により互換）

### 2026-04-17

- **feat-038**: pink_track_id/pink_id/track_id 動画可視化（2026-04-17完了、`scripts/visualize_patient_video.py` を新規作成。`--id-type` で pink_track_id/pink_id/track_id を切替、`--mode` で filter（指定 ID 値のみ）/ all（全 BB 色分け）を選択、`--draw-start/--draw-end` でフレーム範囲指定。BB・スケルトン・ID テキスト・bbox_score を元動画にオーバーレイした MP4 を出力。camSony1_S / camSony1_L で動作確認済み）

### 2026-04-16

- **feat-034**: pink_id + Deep OC-SORT による新トラッキング方式（ロードマップ）（2026-04-16完了、4ステージパイプラインの全体設計と発番計画を確定。Stage1 推論は既存 `run_halpe26_pipeline_yolo11.py`、Stage2 track_id 付与は feat-035、Stage3 pink_id 付与は feat-033 既存実装を流用、Stage4 pink_track_id 算出は feat-036。実装は子案件で段階的に進める）
- **feat-035**: postprocess_track.py 実装（Deep OC-SORT 単独、track_id 付与）（2026-04-16完了、4ステージパイプライン Stage 2。`scripts/postprocess_track.py` を新規作成し、`custom_reid.py` 依存を削除したシンプル版として Deep OC-SORT 単独で `track_id` を付与。camSony1_L 321Kフレームで 191.2 fps / 約28分で完走、Unique track IDs = 1,034。feat-033 と同じ生 dict 保持設計により既存フィールドを変更せず `track_id` のみ追加）
- **feat-036**: postprocess_patient_id.py 実装（pink_id + track_id ハイブリッド、2パス方式）（2026-04-16完了、4ステージパイプライン Stage 4。`scripts/postprocess_patient_id.py` を新規作成。`pink_id` を種・`track_id` を拡張手段とする階層構造で `pink_track_id`（値域 `{1, -1, -2}`）を各 BB に付与。要求 E のデデュプにより各フレーム `pink_track_id=1` は最大 1 つ保証。camSony1_L 321Kフレームで 5489 fps / 58.5秒で完走、Unique patient track_ids = 641、Frames with pink_track_id=1 = 248,752、Frames with pink_track_id=-2 = 17,296）
- **feat-037**: pink_track_id 時系列可視化グラフ（2026-04-16完了、`scripts/plot_pink_track_timeline.py` を新規作成。feat-036 出力 JSON から 5 パネル構成の時系列 PNG グラフを出力する診断ツール。camSony1_L のグラフ目視により feat-033 `pink_id` の誤検出（対象不在区間での `pink_id=1` 検出）を発見）

### 2026-04-15

- **feat-033**: 服装の色による対象同定（ポストプロセス）（2026-04-15完了、postprocess_pink_id.pyでHSVピンク比率ベースに対象BBを選択し既存JSONにpink_idを付与。camSony1_L 321Kフレームで色ベース方式が stable_id より安定して同一対象を追跡可能と確認（stable_id は444個に断片化、色ベースは一貫）。これを受けて feat-034 新トラッキング方式へ移行）

### 2026-04-09

- **feat-025**: BB重複除去方式の比較（2026-04-09完了、案A採用。FR-001で比較CLI実装、FR-002でYOLO11xパイプラインに案A重複除去を組み込み）

### 2026-04-07

- **feat-028**: JSONにトラッキングID記録（2026-04-07完了、postprocess_reid.pyで既存JSONにstable_idを付与するポストプロセス。camSony1_L 321Kフレーム、845ユニークstable_id）
- **feat-029**: トラッキング付き動画可視化（2026-04-07完了、visualize_tracking.pyでstable_idごとに色分けしたスケルトン・BB・IDテキストをMP4出力）

### 2026-04-06

- **feat-022**: 室内動画トラッキング・Re-ID検証（2026-04-06完了、カスタムRe-ID+遅延マッチN=180。camSony1_Sでstable_id収束率92.8%）

### 2026-04-03

- **feat-023**: YOLOX-l検出器検証（2026-04-03完了、camSony1_SではBB重複解消、cam05520125では重複残存）
- **feat-024**: YOLO11x検出器検証（2026-04-03完了、cam05520125/pexelsで重複残存。COCO系トップダウン検出器の限界）

### 2026-03-30

- **feat-020**: BoxMOT環境構築（2026-03-30完了）
- **feat-021**: 既存JSON+動画でBoxMOT動作検証（2026-03-30完了）

### 2026-03-29

- **feat-016**: JSONにBBスコアを保存（2026-03-29完了）
- **feat-017**: キーポイント描画のconfidence閾値を引数指定可能にする（2026-03-29完了）
- **feat-018**: JSONにBBのROI座標を保存（2026-03-29完了）
- **feat-019**: 人物トラッキング調査・ロードマップ（2026-03-29完了）

### 2026-03-28

- **feat-001**: MMPose環境構築・動作確認（2026-03-28完了）
- **feat-002**: MoEチェックポイントDL・分割（2026-03-28完了）
- **feat-003**: COCO 17 静止画推定（2026-03-28完了）
- **feat-004**: COCO 17 動画推定（2026-03-28完了）
- **feat-005**: WholeBody 静止画推定（2026-03-28完了）
- **feat-006**: WholeBody 動画推定（2026-03-28完了）
- **feat-007**: AIC 静止画推定（2026-03-28完了）
- **feat-008**: AIC 動画推定（2026-03-28完了）
- **feat-009**: WholeBody + AIC結合ロジック（2026-03-28完了）
- **feat-010**: OpenPose JSON出力（2026-03-28完了）
- **feat-011**: 結合結果の可視化・検証（2026-03-28完了）
- **feat-012**: HALPE 26統合パイプライン（2026-03-28完了）
- **feat-013**: バウンディングボックス描画（2026-03-28完了）
- **feat-014**: パイプライン処理速度プロファイリング（2026-03-28完了）
- **feat-015**: WholeBody/AIC並列推論（2026-03-28完了、効果なしでコード戻し。RTX 5060 TiではGPU飽和により並列化効果ゼロ）
