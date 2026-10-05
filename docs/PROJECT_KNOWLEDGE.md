# PROJECT_KNOWLEDGE

本リポジトリ（ViTPose）の**プロジェクト知識**（データの所在と仕様・ディレクトリ構成・ドメイン知識）を集約したファイル。
開発フロー・レビュー手順・運用ルールなどの**統治**は `CLAUDE.md` にあり、本ファイルには含めない。

## 本ファイルの扱い

- **必読**: 実作業・案件の調査に入る前に本ファイルを全文読む（`CLAUDE.md`「プロジェクト知識」参照）
- **更新**: 各案件の完了処理で更新する（feat/bug: 案件で得た知見・データの状態・ファイルの追加削除の反映。update: ファイルの追加削除の反映）。更新内容は案件の設計書等に定義しレビューを通したものに限る。追記には出所の案件 ID を付す（例: 「（feat-016）」）
- **構成の変更**（分割・セクション再編）は update 案件で扱う
- **分割の目安**: **本ファイルが 500 行を超えたら分割を検討する。分割しない判断をしてもよいが、その判断と理由を記録する**（記録先は末尾の「分割検討の記録」）。行数は `wc -l docs/PROJECT_KNOWLEDGE.md` で確認する

## データ

テストデータは `testdata/` ディレクトリに配置する（`.gitignore` でgit管理外）。

- **`testdata/cam05520129.mp4`**: 室内の対象動画（1フレーム目から人が映っている）。2Dキーポイント推定の動作確認に使用する
- **`testdata/pexels_4441000.mp4`**: 全身が映る男性の動画（Pexels、49.8秒）。HALPE 26の全キーポイント確認に使用する
- **`testdata/camSony1.mp4`**: 室内の対象動画（低解像度）

## ディレクトリ構成（主要部分）

```
ViTPose/
├── CLAUDE.md               # 開発フロー・運用ルール（統治）
├── AGENTS.md               # Codex が起動時に読む指示ファイル（レビュー定型指示と CLAUDE.md の規定への適合確認。update-002）
├── README.md               # オリジナルのREADME
├── configs/                # モデル設定ファイル
│   ├── body/               # 人体ポーズ推定
│   │   └── 2d_kpt_sview_rgb_img/topdown_heatmap/
│   │       ├── coco/       # COCO 17キーポイント（ViTPose設定あり）
│   │       ├── aic/        # AIC 14キーポイント（ViTPose設定あり）
│   │       └── mpii/       # MPII 16キーポイント
│   ├── wholebody/          # 全身ポーズ推定
│   │   └── 2d_kpt_sview_rgb_img/topdown_heatmap/
│   │       ├── coco-wholebody/  # COCO-WholeBody 133キーポイント（ViTPose設定あり）
│   │       └── halpe/           # HALPE（HRNet設定のみ、ViTPose設定なし）
│   └── _base_/             # 共通設定
│       └── datasets/       # データセット定義
├── mmpose/                 # コアライブラリ
│   └── models/backbones/
│       ├── vit.py          # ViT バックボーン
│       └── vit_moe.py      # ViT MoE バックボーン（ViTPose++用）
├── tools/                  # 学習・推論スクリプト
│   ├── train.py            # 学習
│   ├── test.py             # 評価
│   └── model_split.py      # MoEモデルのデータセット別分割
├── testdata/               # テスト用動画（.gitignore対象）
├── experiments/            # 実験用データ（.gitignore対象、センシティブデータ含む）
│   ├── input/              # 実験用入力データ
│   └── results/            # 実験結果
├── demo/                   # デモスクリプト
├── docs/                   # ドキュメント（開発プロセス基準）
│   ├── PROJECT_KNOWLEDGE.md  # 本ファイル（プロジェクト知識）
│   ├── BACKLOG.md
│   ├── CHANGELOG.md          # 完了履歴
│   ├── BUGFIX_STANDARD.md
│   ├── DESIGN_STANDARD.md
│   ├── REQUIREMENTS_STANDARD.md
│   ├── REVIEW_CRITERIA.md
│   ├── TECH_STACK.md
│   ├── HERDR_SETUP.md        # Herdr によるエージェント連携のセットアップ手順（update-002）
│   ├── codex-exec-ubuntu24-bwrap-fix.md  # Ubuntu 24 系での codex の bwrap エラー対策（update-002）
│   └── issues/             # 案件ディレクトリ
├── scripts/                # 推論パイプラインスクリプト
│   ├── merge_halpe26.py              # HALPE 26結合ロジック・描画
│   ├── halpe26_to_openpose.py        # OpenPose JSON変換
│   ├── visualize_halpe26_video.py    # HALPE 26動画可視化（単体）
│   ├── run_halpe26_pipeline.py        # HALPE 26統合パイプライン（feat-012）
│   ├── run_halpe26_pipeline_yolox.py # YOLOX-l検出器版パイプライン（feat-023）
│   ├── run_halpe26_pipeline_yolo11.py # YOLO11x検出器版パイプライン（feat-024。feat-061で検出ゼロフレームの固定ROIフォールバック --fallback-roi を追加。feat-062で backbone fp16 + CUDA Graph を既定ON化、--no-pose-fp16 / --no-cuda-graph で従来経路）
│   ├── pose_accel.py                 # ViTPose backbone 高速化モジュール（feat-062、AcceleratedBackbone / accelerate_pose_model。run_halpe26_pipeline_yolo11.py から import）
│   ├── compare_dedup_methods.py      # BB重複除去方式比較CLI（feat-025）
│   ├── custom_reid.py                # カスタムRe-IDモジュール（feat-022）
│   ├── test_custom_reid_offline.py   # カスタムRe-IDオフライン検証（feat-022）
│   ├── postprocess_reid.py           # Re-IDポストプロセス：JSONにstable_id付与（feat-028）
│   ├── postprocess_pink_id.py        # Pink-idポストプロセス：JSONにpink_id付与（feat-033、feat-053で--hsv-config対応、feat-056で確認動画同時出力対応・bug-004でデフォルトON化（--no-visualizeで抑制）・feat-058で確認動画デフォルト出力先を--out-dirの親に変更）
│   ├── postprocess_track.py          # Trackポストプロセス：JSONにtrack_id付与（feat-035、Deep OC-SORT単独）
│   ├── postprocess_patient_id.py     # Patient-idポストプロセス：JSONにpink_track_id付与（feat-036、pink_id+track_idハイブリッド2パス方式）
│   ├── plot_pink_track_timeline.py   # pink_track_id時系列可視化グラフ（feat-037、5パネルPNG出力）
│   ├── plot_pink_ratio_timeline.py   # pink_ratio時系列可視化グラフ（feat-040、4パネルPNG出力）
│   ├── visualize_patient_video.py   # ID選択可能な動画可視化（feat-038、BB・スケルトン・テキストをオーバーレイ）
│   ├── visualize_tracking.py        # トラッキング付き動画可視化（feat-029）
│   ├── analyze_clothing_color.py    # 服色特徴量分析・HSVレンジ提案ツール（feat-052、静止画→ViTPose胴体ROI→推奨FIXED_HSV_RANGES。feat-054で推奨レンジを--hsv-config互換JSON出力。feat-055で複数画像入力対応：2枚以上のクロマ画素をプールし全画像を覆う単一レンジ提案＋--threshold閾値検証。feat-059で無彩色（白・黒・灰）対応：chroma_ratioを--chroma-regime-min既定0.4で判定しchromatic/achromaticに分岐、achromaticはH全域・S/V上下限データ駆動）
│   ├── diagnose_pose.py             # 静止画1枚のポーズ推定診断ツール（feat-060、YOLO検出成否＋全画像1BBでのViTPose推論を並べて出力し原因切り分け・可視化PNG）
│   └── conf/                         # HSV設定ファイル置き場（feat-053、--hsv-config用JSON。例: E0014.json）
├── requirements/           # 依存関係定義
└── setup.py                # インストール設定
```

## ドメイン知識

### ViTPose++ MoEモデルの仕組み

MMPose版のViTPose++は、バックボーン（ViT MoE）とデコーダヘッドが**データセットごとに分離**されている。

- `tools/model_split.py` でMoEモデルをデータセットごとに分割できる
- 分割後は各データセット用の設定ファイル + チェックポイントで独立推論が可能
- 対応データセット: COCO, AIC, MPII, AP10K, APT36K, WholeBody

#### AIC 14キーポイント定義

```
 0: RShoulder     4: LElbow      8: RAnkle     12: Head
 1: RElbow        5: LWrist      9: LHip       13: Neck
 2: RWrist        6: RHip       10: LKnee
 3: LShoulder     7: RKnee      11: LAnkle
```

#### HALPE 26キーポイント定義（ターゲット）

```
 0: Nose          9: LWrist       18: Neck
 1: LEye         10: RWrist       19: Hip (中心)
 2: REye         11: LHip         20: LBigToe
 3: LEar         12: RHip         21: RBigToe
 4: REar         13: LKnee        22: LSmallToe
 5: LShoulder    14: RKnee        23: RSmallToe
 6: RShoulder    15: LAnkle       24: LHeel
 7: LElbow       16: RAnkle       25: RHeel
 8: RElbow       17: Head
```

### 室内動画の特性

- 対象は臥位（ベッド上）または座位がほとんど、立位はほぼない
- 布団、チューブ、医療機器による遮蔽が頻繁
- 通常1人の対象が対象（マルチパーソンではない）

### 4ステージパイプライン（feat-034 ロードマップ、全ステージ完了）

feat-034 ロードマップに基づく 4 ステージパイプラインの全ステージが完了した:

- Stage1 推論: 既存 `run_halpe26_pipeline_yolo11.py`（変更なし）
- Stage2 track_id 付与: `postprocess_track.py`（feat-035 完了）
- Stage3 pink_id 付与: `postprocess_pink_id.py`（feat-033 完了、生 dict 保持設計により Stage 2 の `track_id` は自動通過）
- Stage4 pink_track_id 算出: `postprocess_patient_id.py`（feat-036 完了、pink_id を種・track_id を拡張手段とする 2 パス方式。要求 E のデデュプにより各フレーム pink_track_id=1 は最大 1 つ保証）

### 関連リポジトリ

- **HuggingFace版**: `~/git/ViTPose_HuggingFace/` — HuggingFace Transformers経由のViTPose++推論。COCO 17キーポイントのみ対応。feat-001でHead/Neck取得不可と判明し、本リポジトリに移行

## 分割検討の記録

<!-- 500 行を超えた時点で行を追加する。記入例: | 2026-09-02 | 512 | 分割しない | セクション間の相互参照が多く、分割すると読む手数が増えるため | -->

| 日付 | 行数 | 判断 | 理由 |
|---|---|---|---|
