# Backlog

## ロードマップ

ViTPose++ MoEモデルを使い、HALPE 26相当のキーポイントをOpenPose JSON形式で出力することが最終目標。
段階的に各データセットの推論を単独で動作確認し、最後に結合する。

### Phase 0: 環境準備

| ID | Title | 概要 | 依存 |
|----|-------|------|------|
| feat-001 | MMPose環境構築・動作確認 | MMPose + mmcv + MMDetection の環境構築。既存デモスクリプトで動作確認 | - |
| feat-002 | MoEチェックポイントDL・分割 | ViTPose++ Huge MoEモデルをOneDriveからDLし、model_split.pyで6データセット分に分割 | feat-001 |

### Phase 1: COCO 17キーポイント推定

| ID | Title | 概要 | 依存 |
|----|-------|------|------|
| feat-003 | COCO 17 静止画推定 | 分割済みcoco.pth + COCO設定で静止画1枚のポーズ推定・可視化 | feat-002 |
| feat-004 | COCO 17 動画推定 | COCO 17で室内動画のポーズ推定・可視化動画出力 | feat-003 |

### Phase 2: COCO-WholeBody 133キーポイント推定

| ID | Title | 概要 | 依存 |
|----|-------|------|------|
| feat-005 | WholeBody 静止画推定 | 分割済みwholebody.pth + WholeBody設定で静止画1枚のポーズ推定・可視化 | feat-002 |
| feat-006 | WholeBody 動画推定 | WholeBody 133で動画推定。足6点(BigToe/SmallToe/Heel)が正しく出力されるか確認 | feat-005 |

### Phase 3: AIC 14キーポイント推定

| ID | Title | 概要 | 依存 |
|----|-------|------|------|
| feat-007 | AIC 静止画推定 | 分割済みaic.pth + AIC設定で静止画1枚のポーズ推定・可視化 | feat-002 |
| feat-008 | AIC 動画推定 | AIC 14で動画推定。Head/Neckが正しく出力されるか確認 | feat-007 |

### Phase 4: HALPE 26結合出力

| ID | Title | 概要 | 依存 |
|----|-------|------|------|
| feat-009 | WholeBody + AIC結合ロジック | WholeBody(23点)とAIC(Head/Neck)のマッピング + Hip center計算 | feat-006, feat-008 |
| feat-010 | OpenPose JSON出力 | Pose2Sim互換のOpenPose JSONフォーマットで26キーポイントを出力 | feat-009 |
| feat-011 | 結合結果の可視化・検証 | HALPE 26の可視化動画作成。キーポイント位置・左右の正しさを目視確認 | feat-010 |

### Phase 5: 人物トラッキング（BoxMOT + Deep OC-SORT）

| ID | Title | 概要 | 依存 |
|----|-------|------|------|
| feat-019 | 人物トラッキング調査・ロードマップ | トラッキング手法の調査と段階的実装計画の作成 | - |
| feat-020 | BoxMOT環境構築 | boxmotインストール | feat-019 |
| feat-021 | 既存JSON+動画でBoxMOT動作検証 | 出力済みJSON(bbox)と元動画でDeep OC-SORTの動作確認（ViTPose推論不要） | feat-020 |
| feat-022 | 室内動画トラッキング・Re-ID検証 | 室内動画でトラッキング精度を目視確認 | feat-021 |
| feat-023 | YOLOX-l検出器検証 | 臥位人物検出の改善検証（Faster R-CNN→YOLOX-l） | feat-022 |
| feat-024 | YOLO11x検出器検証 | YOLOX-lで不十分な動画に対しYOLO11xで検出精度を検証 | feat-023 |
| feat-025 | BB重複除去方式の比較（案A vs 案E） | 外接矩形再推定(A) vs スコア最大BB選択(E)の精度比較CLI | feat-024 |
| feat-028 | JSONにトラッキングID記録 | person_idにstable_idを記録 | feat-025 |
| feat-026 | 見切れ再同定の検証 | 見切れ場面でID維持されるか確認（凍結中: pink_id + Deep OC-SORT ベースの新トラッキング方式への移行により当面再開予定なし） | feat-028 |
| feat-029 | トラッキング付き動画可視化 | ID別色分け描画 | feat-028 |
| feat-027 | Deep OC-SORT + HALPE 26統合 | パイプラインにDeep OC-SORTを統合（凍結中: 新トラッキング方式 feat-034 への移行により当面再開予定なし） | feat-026 |
| feat-030 | 対象ID特定スクリプト | 最長出現IDを対象として特定（凍結中: stable_id 前提のため、新トラッキング方式 feat-034 の ID 体系確定後に再設計） | feat-028 |
| feat-031 | 対象フィルタリング | 指定IDのキーポイントのみ抽出（凍結中: feat-030 の後続、新トラッキング方式 feat-034 の ID 体系確定後に再設計） | feat-030 |
| feat-033 | 服装の色による対象同定（ポストプロセス） | HSVピンク比率ベースで対象BBを選択し既存JSONにpink_idを付与。camSony1_Lで色ベース方式が stable_id より安定追跡可能と確認 | feat-028 |
| feat-032 | ポーズ誘導外観特徴量の独立検証 | custom_reid.pyから特徴量計算ロジックを分離し、Re-ID非依存で時系列変化を可視化・定量化（凍結中: feat-033 の結果で色ベース方式の優位性が確認され、新トラッキング方式 feat-034 への移行により当面再開予定なし） | feat-026 |
| feat-034 | pink_id + Deep OC-SORT による新トラッキング方式（ロードマップ） | 4ステージパイプライン（Stage1: 推論 / Stage2: track_id / Stage3: pink_id / Stage4: pink_track_id）の全体設計 meta 案件。実装は feat-035 / feat-036 で行う | feat-033 |
| feat-035 | postprocess_track.py 実装（Deep OC-SORT 単独） | HALPE 26 JSON + 動画を入力に、生 track_id を付与するポストプロセス。custom_reid.py は使わない | feat-034 |
| feat-036 | postprocess_patient_id.py 実装（pink_id + track_id ハイブリッド、2パス方式） | feat-035 の track_id と feat-033 の pink_id を結合し、対象 ID `pink_track_id`（値域 `{1, -1, -2}`）を付与するポストプロセス。重複 BB は `-2`、2 パス方式で全区間走査 | feat-035 |
| feat-037 | pink_track_id 時系列可視化グラフ | feat-036 出力の pink_track_id が正常かを目視確認するための時系列グラフ（PNG）を出力するスクリプト | feat-036 |
| feat-038 | pink_track_id/pink_id/track_id 動画可視化 | 選択した ID 種別で BB・スケルトン・テキストを動画にオーバーレイする可視化スクリプト | feat-036 |
| feat-039 | postprocess_pink_id.py に pink_ratio フィールド追加（デバッグ用） | 各 BB の HSV ピンク画素比率を JSON に保存し、閾値チューニングと誤検出解析を容易にする | feat-033 |
| feat-040 | pink_ratio 時系列可視化グラフ | feat-039 で保存した `pink_ratio` をフレーム軸の PNG グラフとして可視化し、閾値妥当性検証と誤検出解析を支援する | feat-039 |
| feat-041 | postprocess_pink_id.py に選択スコア診断フィールド追加 | `iou_with_prev` / `selection_score` / `bb_index` を JSON に保存し、IoU 連続性ボーナスによる誤選択の解析と BB 同定を可能にする | feat-033 |
| feat-042 | visualize_patient_video.py に pink 選択診断フィールド描画拡張 | feat-041 の診断フィールド（`bb_index` / `pink_id` / `pink_ratio` / `iou_with_prev` / `selection_score`）を BB 内部に 1 行描画し、誤選択区間の動画解析を可能にする | feat-041 |
| feat-044 | pink → blue 動画変換ツール（合成テスト動画生成） | NDA により本物の青対象動画が入手不可のため、ピンク対象動画の HSV 空間でピンク領域を低彩度の青に置換した合成テスト動画を生成。青色対応パイプライン（feat-045 以降）の検証用 | feat-033 |
| feat-046 | postprocess_pink_id.py のキーポイントベース ROI 対応 | pink_ratio 計算 ROI を BB 全体から HALPE26 4 キーポイント（両肩・両腰）の min/max 軸並行矩形に切替可能にする `--roi-mode keypoint-rect` を追加。背景・四肢・顔の HSV ノイズを除外して識別精度向上を狙う | feat-033 |
| feat-047 | ROI モード比較・可視化ツール | feat-046 の 2 モード効果を α-1 散布図と不一致フレーム CSV / PNG で比較検証する compare_roi_modes.py + visualize_disagreement_frames.py | feat-046 |
| feat-048 | 不一致フレーム可視化の情報再設計 | feat-047 / feat-048 初版（CSV 経路）では only_bb ケース（不一致 94%）で kp ROI 情報が描画できず δ 目視判定不能と判明。visualize の入力を bb / kp 両 JSON ディレクトリ直読みに変更し、bb 選択人物に対する kp-rect ROI も含めて描画。idx ラベル位置、キーポイント識別、ROI 状態テキスト等の可読性も一括是正 | feat-047 |
| feat-049 | keypoint-rect モード単体・全フレーム可視化ツール | postprocess_pink_id.py --roi-mode keypoint-rect の出力 JSON と動画から、全フレームを 1 枚ずつ PNG として描画。pink_id=1 人物の BB / ROI / 胴体 4 点 / pink_ratio / ROI 状態を表示。bb モードとは比較せず、kp モード単体の挙動を個別フレーム単位で目視検証するためのツール | feat-046 |
| feat-050 | postprocess_pink_id.py に --min-pink-ratio CLI 引数追加 | pink_id=1 候補とする pink_ratio の最低値（既存定数 MIN_PINK_RATIO = 0.03）を CLI から指定可能にする。閾値チューニング作業の煩雑さ解消 | feat-033 |
| feat-051 | selection_score 範囲によるフレーム抽出 PNG ツール | kp モード JSON と動画から、フレーム max selection_score が指定範囲 [min, max) にあるフレームを抽出し PNG 出力。--min-pink-ratio 閾値検討のために s 帯域別サンプルを目視取得する。selection_score=None の場合は pink_ratio で代替（ローカルフォールバック規約） | feat-046, feat-048 |
| feat-052 | 服パッチ静止画からの服色特徴量分析・HSVレンジ提案ツール | 対象の服パッチ静止画1枚から ViTPose（画像全体1BB）で胴体ROIを切り出し、HSV色特徴量を測定し postprocess_pink_id.py 用の推奨 FIXED_HSV_RANGES / MIN_PINK_RATIO を提案する CLI 診断ツール | feat-046, feat-051 |
| feat-053 | postprocess_pink_id.py の HSV 設定ファイル読み込み対応 | ハードコードされた FIXED_HSV_RANGES / min_pink_ratio を JSON 設定ファイル（`--hsv-config`）から差し替え可能にする。feat-052 推奨レンジを実運用へ反映する案C の機能①（コア）。compute_pink_ratio を引数化、未指定時は従来定数で後方互換 | feat-052 |
| feat-054 | analyze_clothing_color.py の HSV 設定ファイル（JSON）出力対応 | `propose_hsv_ranges()` の推奨レンジを feat-053 互換 JSON（`fixed_hsv_ranges` + `min_pink_ratio`）として常時書き出し、手写経をなくす。案C の機能②。`min_pink_ratio` は固定 0.03、空レンジ時は JSON 不出力 | feat-052, feat-053 |

## Open

| ID | Type | Title | Status |
|----|------|-------|--------|
| feat-056 | feat | postprocess_pink_id.py に確認動画同時出力（--visualize）を統合（pink_id 付与と同時に visualize_patient_video.py の描画関数を import 再利用して MP4 を 1 回の動画読みで出力） | Closed |
| feat-055 | feat | analyze_clothing_color.py の複数画像入力・プール提案・閾値検証対応（複数の服パッチ静止画から全画像を覆う単一 HSV 設定 JSON を生成） | Closed |
| feat-054 | feat | analyze_clothing_color.py の HSV 設定ファイル（JSON）出力対応（推奨レンジを feat-053 互換 JSON で常時出力） | Closed |
| feat-053 | feat | postprocess_pink_id.py の HSV 設定ファイル読み込み対応（FIXED_HSV_RANGES / min_pink_ratio の外部化、--hsv-config） | Closed |
| feat-052 | feat | 服パッチ静止画からの服色特徴量分析・HSVレンジ提案ツール（scripts/analyze_clothing_color.py） | Closed |
| feat-049 | feat | keypoint-rect モード単体・全フレーム可視化ツール（scripts/visualize_kp_frames.py） | Open（要件再ヒアリング中、既存 visualize_patient_video.py で代替可能と判明） |
| feat-046 | feat | postprocess_pink_id.py のキーポイントベース ROI 対応 | Closed |
| feat-047 | feat | ROI モード比較・可視化ツール（compare_roi_modes.py + visualize_disagreement_frames.py） | Closed |
| feat-048 | feat | 不一致フレーム可視化の情報再設計（JSON 直読み + idx ラベル / ROI 矩形 / 胴体 4 点描画 + ROI 状態表示） | Closed |
| feat-050 | feat | postprocess_pink_id.py に --min-pink-ratio CLI 引数追加（MIN_PINK_RATIO ハードコードの外部化） | Closed |
| feat-051 | feat | selection_score 範囲によるフレーム抽出 PNG ツール（閾値検討用） | Closed |
| feat-044 | feat | pink → blue 動画変換ツール（合成テスト動画生成） | Frozen（HSV 単独では服と肌が分離不可と判明、独自実装中断。既存ツール活用へ方針転換） |
| bug-003 | bug | visualize_patient_video.py の --draw-start/--draw-end が出力動画範囲を制限しない | Closed |
| feat-042 | feat | visualize_patient_video.py に pink 選択診断フィールド描画拡張 | Closed |
| feat-041 | feat | postprocess_pink_id.py に選択スコア診断フィールド追加 | Closed |
| feat-040 | feat | pink_ratio 時系列可視化グラフ | Closed |
| feat-039 | feat | postprocess_pink_id.py に pink_ratio フィールド追加（デバッグ用） | Closed |
| feat-038 | feat | pink_track_id/pink_id/track_id 動画可視化 | Closed |
| feat-037 | feat | pink_track_id 時系列可視化グラフ | Closed |
| feat-036 | feat | postprocess_patient_id.py 実装（pink_id + track_id ハイブリッド、2パス方式） | Closed |
| feat-035 | feat | postprocess_track.py 実装（Deep OC-SORT 単独） | Closed |
| feat-034 | feat | pink_id + Deep OC-SORT による新トラッキング方式（ロードマップ） | Closed |
| feat-033 | feat | 服装の色による対象同定（ポストプロセス） | Closed |
| feat-032 | feat | ポーズ誘導外観特徴量の独立検証 | Frozen（feat-034 への移行により当面再開予定なし） |
| feat-031 | feat | 対象フィルタリング | Frozen（feat-034 の ID 体系確定後に再設計） |
| feat-030 | feat | 対象ID特定スクリプト | Frozen（feat-034 の ID 体系確定後に再設計） |
| feat-029 | feat | トラッキング付き動画可視化 | Closed |
| feat-027 | feat | Deep OC-SORT + HALPE 26統合 | Frozen（feat-034 への移行により当面再開予定なし） |
| feat-026 | feat | 見切れ再同定の検証 | Frozen（feat-034 への移行により当面再開予定なし） |
| feat-025 | feat | BB重複除去方式の比較（案A vs 案E） | Closed |
| feat-024 | feat | YOLO11x検出器検証 | Closed |
| feat-023 | feat | YOLOX-l検出器検証 | Closed |
| feat-020 | feat | BoxMOT環境構築 | Closed |
| feat-021 | feat | 既存JSON+動画でBoxMOT動作検証 | Closed |
| feat-022 | feat | 室内動画トラッキング・Re-ID検証 | Closed |
| feat-001 | feat | MMPose環境構築・動作確認 | Closed |
| feat-002 | feat | MoEチェックポイントDL・分割 | Closed |
| feat-003 | feat | COCO 17 静止画推定 | Closed |
| feat-004 | feat | COCO 17 動画推定 | Closed |
| feat-005 | feat | WholeBody 静止画推定 | Closed |
| feat-006 | feat | WholeBody 動画推定 | Closed |
| feat-007 | feat | AIC 静止画推定 | Closed |
| feat-008 | feat | AIC 動画推定 | Closed |
| feat-009 | feat | WholeBody + AIC結合ロジック | Closed |
| feat-010 | feat | OpenPose JSON出力 | Closed |
| feat-011 | feat | 結合結果の可視化・検証 | Closed |
| feat-012 | feat | HALPE 26統合パイプライン | Closed |
| feat-013 | feat | バウンディングボックス描画 | Closed |
| feat-014 | feat | パイプライン処理速度プロファイリング | Closed |
| feat-015 | feat | WholeBody/AIC並列推論 | Closed (効果なし、コード戻し) |
| bug-001 | bug | プロファイル表示で変数fpsが動画FPSを上書き | Closed |
| bug-002 | bug | --mode json時にout_pathが未定義で参照されるリスク | Closed |
| feat-016 | feat | JSONにBBスコアを保存 | Closed |
| feat-017 | feat | キーポイント描画のconfidence閾値を引数指定可能にする | Closed |
| feat-018 | feat | JSONにBBのROI座標を保存 | Closed |

## Closed

| ID | Type | Title | Resolved |
|----|------|-------|----------|
| feat-001 | feat | MMPose環境構築・動作確認 | 2026-03-28 |
| feat-002 | feat | MoEチェックポイントDL・分割 | 2026-03-28 |
| feat-003 | feat | COCO 17 静止画推定 | 2026-03-28 |
| feat-004 | feat | COCO 17 動画推定 | 2026-03-28 |
| feat-005 | feat | WholeBody 静止画推定 | 2026-03-28 |
| feat-006 | feat | WholeBody 動画推定 | 2026-03-28 |
| feat-007 | feat | AIC 静止画推定 | 2026-03-28 |
| feat-008 | feat | AIC 動画推定 | 2026-03-28 |
| feat-009 | feat | WholeBody + AIC結合ロジック | 2026-03-28 |
| feat-010 | feat | OpenPose JSON出力 | 2026-03-28 |
| feat-011 | feat | 結合結果の可視化・検証 | 2026-03-28 |
| feat-012 | feat | HALPE 26統合パイプライン | 2026-03-28 |
| feat-013 | feat | バウンディングボックス描画 | 2026-03-28 |
| feat-014 | feat | パイプライン処理速度プロファイリング | 2026-03-28 |
| feat-015 | feat | WholeBody/AIC並列推論 | 2026-03-28 (効果なし、コード戻し) |
| bug-001 | bug | プロファイル表示で変数fpsが動画FPSを上書き | 2026-03-29 |
| bug-002 | bug | --mode json時にout_pathが未定義で参照されるリスク | 2026-03-29 |
| feat-016 | feat | JSONにBBスコアを保存 | 2026-03-29 |
| feat-017 | feat | キーポイント描画のconfidence閾値を引数指定可能にする | 2026-03-29 |
| feat-018 | feat | JSONにBBのROI座標を保存 | 2026-03-29 |
| feat-019 | feat | 人物トラッキング調査・ロードマップ | 2026-03-29 |
| feat-020 | feat | BoxMOT環境構築 | 2026-03-30 |
| feat-021 | feat | 既存JSON+動画でBoxMOT動作検証 | 2026-03-30 |
| feat-022 | feat | 室内動画トラッキング・Re-ID検証 | 2026-04-06 |
| feat-023 | feat | YOLOX-l検出器検証 | 2026-04-03 |
| feat-024 | feat | YOLO11x検出器検証 | 2026-04-03 |
| feat-025 | feat | BB重複除去方式の比較（案A vs 案E） | 2026-04-09 |
| feat-028 | feat | JSONにトラッキングID記録 | 2026-04-07 |
| feat-033 | feat | 服装の色による対象同定（ポストプロセス） | 2026-04-15 |
| feat-034 | feat | pink_id + Deep OC-SORT による新トラッキング方式（ロードマップ） | 2026-04-16 |
| feat-029 | feat | トラッキング付き動画可視化 | 2026-04-07 |
| feat-035 | feat | postprocess_track.py 実装（Deep OC-SORT 単独） | 2026-04-16 |
| feat-036 | feat | postprocess_patient_id.py 実装（pink_id + track_id ハイブリッド、2パス方式） | 2026-04-16 |
| feat-037 | feat | pink_track_id 時系列可視化グラフ | 2026-04-16 |
| feat-038 | feat | pink_track_id/pink_id/track_id 動画可視化 | 2026-04-17 |
| feat-039 | feat | postprocess_pink_id.py に pink_ratio フィールド追加（デバッグ用） | 2026-04-21 |
| feat-040 | feat | pink_ratio 時系列可視化グラフ | 2026-04-29 |
| feat-052 | feat | 服パッチ静止画からの服色特徴量分析・HSVレンジ提案ツール | 2026-05-26 |
| feat-053 | feat | postprocess_pink_id.py の HSV 設定ファイル読み込み対応 | 2026-05-27 |
| feat-054 | feat | analyze_clothing_color.py の HSV 設定ファイル（JSON）出力対応 | 2026-05-27 |
| feat-055 | feat | analyze_clothing_color.py の複数画像入力・プール提案・閾値検証対応 | 2026-05-28 |
| feat-056 | feat | postprocess_pink_id.py に確認動画同時出力（--visualize）を統合 | 2026-05-28 |
| feat-057 | feat | postprocess_pink_id.py の --out-dir 自動導出（任意化） | 2026-05-28 |
| bug-004 | bug | postprocess_pink_id.py の確認動画がデフォルトで出力されない（feat-056 仕様漏れ） | 2026-05-28 |
| feat-058 | feat | postprocess_pink_id.py の確認動画保存先デフォルトを out-dir の親に変更 | 2026-05-28 |
| feat-059 | feat | analyze_clothing_color.py の色非依存レンジ提案（有彩色・白・黒・灰対応） | 2026-06-01 |
