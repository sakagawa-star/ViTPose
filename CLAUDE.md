# CLAUDE.md

このファイルはClaude Codeがプロジェクトを理解するためのガイドです。

## セッション引き継ぎ

- セッション開始時にプロジェクトルートの `.claude/handovers/` ディレクトリを確認し、ファイルが存在すれば最新のものを読み込む
- セッション終了時や作業の区切りでは `/handover` の実行を促す

## プロジェクト概要

本プロジェクトは、ViTAE-Transformer/ViTPose（MMPoseベース）を使用して、病室の患者動画に対して2Dポーズ推定を行う。HuggingFace版ViTPose++ではデコーダヘッドがCOCO 17固定でHead/Neckキーポイントが取得できないため、MMPose版に移行した。

### 目標
- ViTPose++のMoEアーキテクチャを活用し、HALPE 26相当のキーポイント（COCO 17 + Head + Neck + Hip center + 足6点）を出力する
- 結果をPose2Simに渡せるOpenPose JSON形式で出力する

### 背景
- Pose2Sim付属のRTMPose + YOLOXでは、遮蔽物が多い病室環境で精度が不十分
- 遮蔽ベンチマーク(OCHuman)で高精度なViTPose++に切り替え
- HuggingFace版（`~/git/ViTPose_HuggingFace/`）で技術検証済み（feat-001）。dataset_indexを切り替えてもデコーダヘッドがCOCO 17固定のため、Head/Neck取得不可と判明
- MMPose版ではデータセットごとに別のデコーダヘッド（異なるnum_joints）を持つため、AIC 14点（Head/Neck含む）やCOCO-WholeBody 133点が取得可能

## 技術スタック

- **言語**: Python 3.10.16
- **パッケージ管理**: uv（Python環境構築・依存関係管理に使用）
- **フレームワーク**: MMPose 0.24.0 (OpenMMLab)
- **ポーズ推定**: ViTPose++ (MoE)
- **依存関係**: torch 2.11.0+cu128 / mmcv-full 1.7.2 (CUDA ops) / mmdet 2.28.2 / timm == 0.4.9 / einops
- **詳細**: `docs/TECH_STACK.md` を参照
- **注意**: mmpose/__init__.py の mmcv上限バージョンを 1.8.0 に緩和済み

## テストデータ

テストデータは `testdata/` ディレクトリに配置する（`.gitignore` でgit管理外）。

- **`testdata/cam05520129.mp4`**: 病室の患者動画（1フレーム目から人が映っている）。2Dキーポイント推定の動作確認に使用する
- **`testdata/pexels_4441000.mp4`**: 全身が映る男性の動画（Pexels、49.8秒）。HALPE 26の全キーポイント確認に使用する
- **`testdata/camSony1.mp4`**: 病室の患者動画（低解像度）

## ディレクトリ構成（主要部分）

```
ViTPose/
├── CLAUDE.md               # 本ファイル
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
│   ├── BACKLOG.md
│   ├── BUGFIX_STANDARD.md
│   ├── DESIGN_STANDARD.md
│   ├── REQUIREMENTS_STANDARD.md
│   ├── REVIEW_CRITERIA.md
│   ├── TECH_STACK.md
│   └── issues/             # 案件ディレクトリ
├── scripts/                # 推論パイプラインスクリプト
│   ├── merge_halpe26.py              # HALPE 26結合ロジック・描画
│   ├── halpe26_to_openpose.py        # OpenPose JSON変換
│   ├── visualize_halpe26_video.py    # HALPE 26動画可視化（単体）
│   ├── run_halpe26_pipeline.py        # HALPE 26統合パイプライン（feat-012）
│   ├── run_halpe26_pipeline_yolox.py # YOLOX-l検出器版パイプライン（feat-023）
│   ├── run_halpe26_pipeline_yolo11.py # YOLO11x検出器版パイプライン（feat-024）
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
│   └── conf/                         # HSV設定ファイル置き場（feat-053、--hsv-config用JSON。例: E0014.json）
├── requirements/           # 依存関係定義
└── setup.py                # インストール設定
```

## ViTPose++ MoEモデルの仕組み

MMPose版のViTPose++は、バックボーン（ViT MoE）とデコーダヘッドが**データセットごとに分離**されている。

- `tools/model_split.py` でMoEモデルをデータセットごとに分割できる
- 分割後は各データセット用の設定ファイル + チェックポイントで独立推論が可能
- 対応データセット: COCO, AIC, MPII, AP10K, APT36K, WholeBody

### AIC 14キーポイント定義

```
 0: RShoulder     4: LElbow      8: RAnkle     12: Head
 1: RElbow        5: LWrist      9: LHip       13: Neck
 2: RWrist        6: RHip       10: LKnee
 3: LShoulder     7: RKnee      11: LAnkle
```

### HALPE 26キーポイント定義（ターゲット）

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

## 病室動画の特性（ドメイン知識）

- 患者は臥位（ベッド上）または座位がほとんど、立位はほぼない
- 布団、チューブ、医療機器による遮蔽が頻繁
- 通常1人の患者が対象（マルチパーソンではない）

## 開発方針

- **シンプルな機能を一つずつ作り、積み重ねて目的を達成する**
- 大きな機能を一度に作らない。小さく作って動作確認し、次の機能へ進む
- MMPose版ViTPose++のコードは可能な限り変更せず、推論パイプラインを別途構築する

### 機能追加フロー（feat-XXX 案件）

新機能を追加する場合、以下のフローを**厳守**する。**planモードは使わない**（通常モードで調査・計画を行う）。

1. **案件作成** → `docs/issues/feat-{number}-{slug}/` フォルダを作成し、`docs/BACKLOG.md` に追加する
2. **調査・計画** → 通常モードで既存コードを調査し、要求仕様書（`docs/REQUIREMENTS_STANDARD.md` 準拠）と機能設計書（`docs/DESIGN_STANDARD.md` 準拠）を作成する
3. **ドキュメント保存** → 要求仕様書を `docs/issues/{案件フォルダ}/requirements.md`、機能設計書を `docs/issues/{案件フォルダ}/design.md` にファイル保存する。**保存が完了するまで実装に進んではならない**
4. **レビュー（Codex + 人）** → 保存されたドキュメントを **Codex** でレビューする。実行方法は後述の「Codexによるレビューの実行方法」を参照。ユーザーも同時にレビューする。レビュー実行時は `docs/REVIEW_CRITERIA.md` の基準に従うこと
5. **修正（必要な場合）** → レビューで問題があれば、再調査してドキュメントを更新する。**ステップ2〜4を問題がなくなるまで繰り返す**
6. **実装** → ドキュメント（要求仕様書・機能設計書・CLAUDE.md）を読んで実装する。実装完了後、「テスト」セクションのルールに従ってテストを実行する
7. **手動テスト** → ユーザーがテストする。以下の問題があれば `docs/BUGFIX_STANDARD.md` に従って修正計画を `docs/issues/{案件フォルダ}/investigation.md` に追記する（上書きしない。イテレーション番号を付けて履歴を残す）。**ユーザーの承認を得た上で、ステップ2〜7を繰り返す**（コード修正はステップ6で行う。ステップ7で直接コードを編集してはならない）
   - 不具合の発見
   - 要求通りに実装されていない
   - 要求仕様作成時のヒアリング漏れ
8. **完了** → `docs/BACKLOG.md` のステータスを Closed に更新する。ファイルの追加・削除があった場合は `CLAUDE.md` のディレクトリ構成を最新に更新する

### 不具合修正フロー（bug-XXX 案件）

既存機能の不具合を修正する場合、以下のフローを**厳守**する。

1. **案件作成** → `docs/issues/bug-{number}-{slug}/` フォルダを作成し、`docs/BACKLOG.md` に追加する。`README.md` に不具合の概要と再現手順を記録する
2. **調査・修正計画** → `docs/BUGFIX_STANDARD.md` に従い、既存コードを調査する。修正計画を `docs/issues/{案件フォルダ}/investigation.md` に記録する。**この時点でコードを編集してはならない**
3. **ドキュメント保存** → investigation.md の保存を確認する。**保存が完了するまで実装に進んではならない**
4. **レビュー（Codex + 人）** → 保存されたドキュメントを **Codex** でレビューする。実行方法は後述の「Codexによるレビューの実行方法」を参照。ユーザーも同時にレビューする。レビュー実行時は `docs/REVIEW_CRITERIA.md` の基準に従うこと
5. **修正（必要な場合）** → レビューで問題があれば、再調査してドキュメントを更新する。**ステップ2〜4を問題がなくなるまで繰り返す**
6. **実装** → 承認された修正計画に沿ってコードを修正する。計画にない変更が必要になった場合は中断して報告する
7. **手動テスト** → ユーザーがテストする。問題があれば `docs/BUGFIX_STANDARD.md` に従って investigation.md にイテレーション番号を付けて追記し、**ユーザーの承認を得た上で、ステップ2〜7を繰り返す**（コード修正はステップ6で行う。ステップ7で直接コードを編集してはならない）
8. **完了** → `docs/BACKLOG.md` のステータスを Closed に更新する。ファイルの追加・削除があった場合は `CLAUDE.md` のディレクトリ構成を最新に更新する

### ドキュメント作成ルール

- **実装前に必ずドキュメントを作成し、案件フォルダにファイル保存すること**
- ドキュメントが保存されていない場合は、**実装を中止**する
- 機能追加時: 要求仕様書（`docs/REQUIREMENTS_STANDARD.md` 準拠）と機能設計書（`docs/DESIGN_STANDARD.md` 準拠）を作成する
- 不具合修正時: `docs/BUGFIX_STANDARD.md` の基準に従い、修正計画を `investigation.md` に記録する
- レビュー実行時は `docs/REVIEW_CRITERIA.md` の基準に従うこと
- ドキュメントは `docs/issues/{案件フォルダ}/` に置く（`requirements.md`, `design.md`, `investigation.md`）
- **/clear 後でも実装がスムーズにできるよう、必要な情報を全て記述する**
- 暗黙知に頼らず、**自己完結したドキュメント**にする（前の会話コンテキストがなくても実装できること）
- ライブラリの追加・変更・削除を行った場合は `docs/TECH_STACK.md` も更新すること
- 新規ライブラリ導入時は用途・選定理由・バージョンを `TECH_STACK.md` に追記すること

### 案件ディレクトリ構成

```
docs/issues/
└── {type}-{number}-{slug}/    # 例: bug-001-xxx, feat-001-yyy
    ├── README.md              # 概要、ステータス、再現手順
    ├── requirements.md        # 要求仕様書（機能追加時、REQUIREMENTS_STANDARD.md 準拠）
    ├── design.md              # 機能設計書（機能追加時、DESIGN_STANDARD.md 準拠）
    └── investigation.md       # 不具合の調査・修正計画（BUGFIX_STANDARD.md 準拠）
```

### 命名規則

- フォルダ名は英語で統一（例: `bug-001-dataset-index-type`）
- 案件フォルダは完了後も削除・移動しない

### Codexによるレビューの実行方法

機能追加・不具合修正フローのステップ4（レビュー）では、Claude Code 自身が `codex exec` コマンドを実行して Codex にレビューさせる。Subagent は使わない。

使用するモデルは `~/.codex/config.toml` のデフォルト設定に従う。本ファイルのコマンドにはモデル指定（`-m`）を書かない。モデルを切り替えたい場合は `~/.codex/config.toml` を編集する（全プロジェクト共通で反映される）。

**sandbox について**: 本環境では Codex の sandbox（bubblewrap）が `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted` で失敗し、ファイル読み取りすらできずレビュー不能になる。このため全コマンドに `--dangerously-bypass-approvals-and-sandbox` を付けて bwrap を迂回する（レビューはドキュメント読み取りのみで副作用なし）。

#### 初回レビュー（機能追加の場合）

```bash
codex exec --dangerously-bypass-approvals-and-sandbox "docs/REVIEW_CRITERIA.md の基準に従い、以下のドキュメントをレビューせよ: docs/issues/{案件フォルダ}/requirements.md docs/issues/{案件フォルダ}/design.md 。瑣末な点へのクソリプはしないで、致命的な点のみ指摘して。発見した問題を重要度(高/中/低)で分類し、修正提案とともに報告すること。"
```

#### 初回レビュー（不具合修正の場合）

```bash
codex exec --dangerously-bypass-approvals-and-sandbox "docs/REVIEW_CRITERIA.md および docs/BUGFIX_STANDARD.md の基準に従い、以下のドキュメントをレビューせよ: docs/issues/{案件フォルダ}/investigation.md 。瑣末な点へのクソリプはしないで、致命的な点のみ指摘して。発見した問題を重要度(高/中/低)で分類し、修正提案とともに報告すること。"
```

#### 再レビュー（共通）

ドキュメントを更新して再レビューする場合、最初のレビューの文脈を保持するため `resume --last` を使う:

```bash
codex exec resume --last --dangerously-bypass-approvals-and-sandbox "ドキュメントを更新したので再レビューして。前回と同じ基準で。瑣末な点へのクソリプはしないで、致命的な点のみ指摘して。重要度(高/中/低)で分類し、修正提案とともに報告すること。"
```

**注意**: `resume --last` を付けないと最初のレビューの文脈が失われる。

#### レビュー終了条件

重要度「高」「中」の指摘がなくなるまで、修正 → 再レビューを繰り返す。「低」のみになったら人レビューに進む。

### コードレビュー

- レビューでは重要度(高/中/低)で分類し、修正提案とともに報告する
- 重要度:高と中は修正対象とする
- レビュー基準の詳細は `docs/REVIEW_CRITERIA.md` を参照

## コーディング規約

- **命名規則**:
  - クラス名: PascalCase (例: `PersonDetector`)
  - 関数・メソッド: snake_case (例: `detect`, `estimate`)
  - 定数: UPPER_SNAKE_CASE (例: `SKELETON`)

- **型ヒント**: 関数シグネチャに型ヒントを使用

## 4ステージパイプライン（feat-034 ロードマップ、全ステージ完了）

feat-034 ロードマップに基づく 4 ステージパイプラインの全ステージが完了した:

- Stage1 推論: 既存 `run_halpe26_pipeline_yolo11.py`（変更なし）
- Stage2 track_id 付与: `postprocess_track.py`（feat-035 完了）
- Stage3 pink_id 付与: `postprocess_pink_id.py`（feat-033 完了、生 dict 保持設計により Stage 2 の `track_id` は自動通過）
- Stage4 pink_track_id 算出: `postprocess_patient_id.py`（feat-036 完了、pink_id を種・track_id を拡張手段とする 2 パス方式。要求 E のデデュプにより各フレーム pink_track_id=1 は最大 1 つ保証）

## 凍結中の案件

`stable_id` / `custom_reid.py` ベースの既存トラッキング関連案件は、pink_id + Deep OC-SORT による新トラッキング方式（feat-034）への移行に伴い凍結中。

- **feat-026**: 見切れ再同定の検証（`stable_id` 前提のため凍結。feat-034 の ID 体系確定後に再評価）
- **feat-027**: Deep OC-SORT + HALPE 26統合（旧 `custom_reid.py` 経路を前提とするため凍結。新方式が feat-034 で統合パイプライン化される）
- **feat-030**: 患者ID特定スクリプト（`stable_id` の最長出現を前提とするため凍結。feat-034 の ID 体系確定後に再設計）
- **feat-031**: 患者フィルタリング（feat-030 の後続、同上の理由で凍結）
- **feat-032**: ポーズ誘導外観特徴量の独立検証（feat-033 で色ベース方式の優位性が確認され、`custom_reid.py` HSVヒストグラム経路の修正動機が薄れたため凍結）
- **feat-044**: pink → blue 動画変換ツール（HSV 分析でピンク服と肌が HSV 空間で本質的に重なる（H 円環距離 31、重なり率 46%）と確定。独自実装で空間制約（胴体内接矩形限定）を入れる方向で進められたが、ユーザー判断により既存ツール（ffmpeg / DaVinci Resolve / G'MIC 等）の活用へ方針転換することとなり、独自実装は中断）

## 完了済み案件

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
- **feat-016**: JSONにBBスコアを保存（2026-03-29完了）
- **feat-017**: キーポイント描画のconfidence閾値を引数指定可能にする（2026-03-29完了）
- **feat-018**: JSONにBBのROI座標を保存（2026-03-29完了）
- **feat-019**: 人物トラッキング調査・ロードマップ（2026-03-29完了）
- **feat-020**: BoxMOT環境構築（2026-03-30完了）
- **feat-021**: 既存JSON+動画でBoxMOT動作検証（2026-03-30完了）
- **feat-022**: 病室動画トラッキング・Re-ID検証（2026-04-06完了、カスタムRe-ID+遅延マッチN=180。camSony1_Sでstable_id収束率92.8%）
- **feat-023**: YOLOX-l検出器検証（2026-04-03完了、camSony1_SではBB重複解消、cam05520125では重複残存）
- **feat-024**: YOLO11x検出器検証（2026-04-03完了、cam05520125/pexelsで重複残存。COCO系トップダウン検出器の限界）
- **feat-025**: BB重複除去方式の比較（2026-04-09完了、案A採用。FR-001で比較CLI実装、FR-002でYOLO11xパイプラインに案A重複除去を組み込み）
- **feat-028**: JSONにトラッキングID記録（2026-04-07完了、postprocess_reid.pyで既存JSONにstable_idを付与するポストプロセス。camSony1_L 321Kフレーム、845ユニークstable_id）
- **feat-029**: トラッキング付き動画可視化（2026-04-07完了、visualize_tracking.pyでstable_idごとに色分けしたスケルトン・BB・IDテキストをMP4出力）
- **feat-033**: 服装の色による患者同定（ポストプロセス）（2026-04-15完了、postprocess_pink_id.pyでHSVピンク比率ベースに患者BBを選択し既存JSONにpink_idを付与。camSony1_L 321Kフレームで色ベース方式が stable_id より安定して同一患者を追跡可能と確認（stable_id は444個に断片化、色ベースは一貫）。これを受けて feat-034 新トラッキング方式へ移行）
- **feat-034**: pink_id + Deep OC-SORT による新トラッキング方式（ロードマップ）（2026-04-16完了、4ステージパイプラインの全体設計と発番計画を確定。Stage1 推論は既存 `run_halpe26_pipeline_yolo11.py`、Stage2 track_id 付与は feat-035、Stage3 pink_id 付与は feat-033 既存実装を流用、Stage4 pink_track_id 算出は feat-036。実装は子案件で段階的に進める）
- **feat-035**: postprocess_track.py 実装（Deep OC-SORT 単独、track_id 付与）（2026-04-16完了、4ステージパイプライン Stage 2。`scripts/postprocess_track.py` を新規作成し、`custom_reid.py` 依存を削除したシンプル版として Deep OC-SORT 単独で `track_id` を付与。camSony1_L 321Kフレームで 191.2 fps / 約28分で完走、Unique track IDs = 1,034。feat-033 と同じ生 dict 保持設計により既存フィールドを変更せず `track_id` のみ追加）
- **feat-036**: postprocess_patient_id.py 実装（pink_id + track_id ハイブリッド、2パス方式）（2026-04-16完了、4ステージパイプライン Stage 4。`scripts/postprocess_patient_id.py` を新規作成。`pink_id` を種・`track_id` を拡張手段とする階層構造で `pink_track_id`（値域 `{1, -1, -2}`）を各 BB に付与。要求 E のデデュプにより各フレーム `pink_track_id=1` は最大 1 つ保証。camSony1_L 321Kフレームで 5489 fps / 58.5秒で完走、Unique patient track_ids = 641、Frames with pink_track_id=1 = 248,752、Frames with pink_track_id=-2 = 17,296）
- **feat-037**: pink_track_id 時系列可視化グラフ（2026-04-16完了、`scripts/plot_pink_track_timeline.py` を新規作成。feat-036 出力 JSON から 5 パネル構成の時系列 PNG グラフを出力する診断ツール。camSony1_L のグラフ目視により feat-033 `pink_id` の誤検出（患者不在区間での `pink_id=1` 検出）を発見）
- **feat-038**: pink_track_id/pink_id/track_id 動画可視化（2026-04-17完了、`scripts/visualize_patient_video.py` を新規作成。`--id-type` で pink_track_id/pink_id/track_id を切替、`--mode` で filter（指定 ID 値のみ）/ all（全 BB 色分け）を選択、`--draw-start/--draw-end` でフレーム範囲指定。BB・スケルトン・ID テキスト・bbox_score を元動画にオーバーレイした MP4 を出力。camSony1_S / camSony1_L で動作確認済み）
- **feat-039**: postprocess_pink_id.py に pink_ratio フィールド追加（デバッグ用）（2026-04-21完了、`scripts/postprocess_pink_id.py` の pink_id 付与ループに 1 行追加し、各 `people[i]` に HSV ピンク画素比率 `pink_ratio`（float、値域 [0.0, 1.0]）を保存。選択ロジック・CLI・サマリ出力は未変更。閾値 `MIN_PINK_RATIO=0.03` の妥当性検証と feat-037 で検出された誤検出区間の原因解析を、ポストプロセス再実行なしで行えるようにする。下流スクリプト（feat-035/036/037/038）は生 dict 保持設計により互換）
- **feat-040**: pink_ratio 時系列可視化グラフ（2026-04-29完了、`scripts/plot_pink_ratio_timeline.py` を新規作成。feat-039 改修済み JSON から 4 パネル構成の PNG 時系列グラフを出力。Panel 1: 全 BB の pink_ratio 散布図 + 閾値ライン、Panel 2: pink_id=1 有無、Panel 3: BB 数内訳、Panel 4: 「選択 BB ratio − 次点 BB ratio」差分（< 0.05 のフレームは赤背景帯で強調、負値含む）。次点 BB は全 BB の pink_ratio 降順 2 位（案 a-2、選択 BB を含む全体ランキング）。`--frame-start` / `--frame-end` で部分描画可。camSony1_L 321K フレームで 37.4 秒 / Frames with close margin = 4108）
- **feat-041**: postprocess_pink_id.py に選択スコア診断フィールド追加（2026-04-30完了、`scripts/postprocess_pink_id.py` の pink_id 付与ループに 3 フィールド追加: `bb_index: int`、`iou_with_prev: float | null`、`selection_score: float | null`。連続性切れ時は null（案 B、「前 BB なし」と「IoU=0」の区別を保持）。改修前後で `pink_id` / `pink_ratio` 完全一致を確認、camSony1_L で処理時間 −0.6%。当初動機の IoU 連続性ボーナスによる誤選択は動画再確認の結果、過去の観察ミスの可能性が高いと判明したが、診断フィールド自体は将来の解析ツールとして汎用価値がある）
- **feat-042**: visualize_patient_video.py に pink 選択診断フィールド描画拡張（2026-04-30完了、既存 `scripts/visualize_patient_video.py` を拡張。BB 内部 (x1+4, y1+16) に診断 5 フィールド（`bb_index` / `pink_id` / `pink_ratio` / `iou_with_prev` / `selection_score`）を 1 行描画。フィールド別 `--show-X` / `--no-show-X` フラグ（`argparse.BooleanOptionalAction`、デフォルト全 ON）。フォントスケール 0.45、小数 3 桁、整数フィールドは `int(...)` ラップ、5 フィールドすべて null 安全。`build_debug_label` 7 ケース全パス）
- **bug-003**: visualize_patient_video.py の --draw-start/--draw-end が出力動画範囲を制限しない（2026-04-30完了、`scripts/visualize_patient_video.py` のフレームループを修正。`cap.set(cv2.CAP_PROP_POS_FRAMES, draw_start)` でシーク + ループ冒頭で `draw_end` 到達時に break。`in_draw_range` フラグ廃止。出力 MP4 のフレーム数 = 指定範囲のみ。テスト 1（1397 フレーム）/ 4（リグレッション 900 フレーム）/ 5（`--draw-start 100` で 800 フレーム）すべて期待通り。処理時間 30 分超 → 4.8 秒に短縮）
- **feat-046**: postprocess_pink_id.py のキーポイントベース ROI 対応（2026-05-13完了、`postprocess_pink_id.py` に `--roi-mode {bb, keypoint-rect}` / `--kpt-conf-min` / `--min-roi-area` を追加。`build_keypoint_rect_roi` 関数で HALPE26 胴体 4 点（5/6/11/12）から軸並行最小矩形 ROI を構築（K-2 方式 = 信頼点 2 個以上、F2 厳しめ = 構築失敗時 pink_ratio=0）。bb モードは既存 JSON と完全互換、keypoint-rect モード時のみ `roi_mode` / `roi_bbox` フィールドを追加。camSony1_S 全 900 フレームで AC-003-1 `diff -r` 差分 0 確認）
- **feat-047**: ROI モード比較・可視化ツール（2026-05-13完了、`scripts/compare_roi_modes.py` で α-1 散布図 + 不一致 CSV を出力、`scripts/visualize_disagreement_frames.py` で不一致フレームの目視確認 PNG を出力。CSV 経路は feat-048 v2 で JSON 直読みに刷新されたが本スクリプト自体は残置）
- **feat-048**: 不一致フレーム可視化の情報再設計（2026-05-15完了、`scripts/visualize_disagreement_frames.py` を全面書き直し。CSV 経路を廃止し bb / kp 両 JSON ディレクトリ直読みに刷新。`only_bb` ケースで bb 選択人物の `bb_index` を kp 側 JSON で線形検索して `roi_bbox` を取得 → 不一致 94% を占める only_bb ケースでも kp-rect ROI 描画可能に。`build_attempted_roi`（area チェック省略版）を新規追加し fail_area でも矩形を描画。状態別色分け（ok=黄、fail_area=オレンジ、fail_kpt=描画なし）、胴体 4 点に LS/RS/LH/RH ラベル + 高信頼=塗りつぶし円/低信頼=× マーク、idx ラベルを BB 右上角外側に配置してキーポイントとの重なり回避）
- **feat-050**: postprocess_pink_id.py に --min-pink-ratio CLI 引数追加（2026-05-14完了、`MIN_PINK_RATIO = 0.03` 定数を CLI 引数 `--min-pink-ratio`（値域 `[0.0, 1.0]`、デフォルト 0.03）で外部化。`select_pink_bbox` シグネチャに `min_pink_ratio: float` 引数追加。サマリに `Min pink ratio threshold: 0.XXX` を 1 行追加。`git stash` ベースで改修前後の `diff -r` 差分 0 を確認、AC-001-1 PASS）
- **feat-051**: selection_score 範囲によるフレーム抽出 PNG ツール（2026-05-15完了、`scripts/extract_score_range_frames.py` を新規作成。kp モード JSON と動画から、フレーム max selection_score が指定範囲 `[score-min, score-max]`（両端含む、`==` 許容）にあるフレームを抽出し PNG 出力。`selection_score=None` のときは `pink_ratio` で代替するローカルフォールバック規約（feat-041 の null 規約は JSON 形式不変）。出力 PNG は元動画フレームの上に高さ 60 px の黒帯バナーを `np.vstack` で積層し、その内側に Frame / effective_s / range / ROI 状態を白文字描画（BB ラベルと衝突しない構造、AC-004-5）。1 フレーム 1 person（max s）のみ描画。BB 上部ラベル `pink_id:` / `score:` は v2 で省略（診断ラベル `idx pid r iou s` と近接して可読性低下のため）。--min-pink-ratio 閾値検討用途で camSony1_L で動作確認、ピンク服 vs 灰色服の pink_ratio が同水準（~0.055）になる構造的問題が判明 → HSV レンジ調整 or 学習ベース移行の検討材料を提供）
- **feat-052**: 服パッチ静止画からの服色特徴量分析・HSVレンジ提案ツール（2026-05-26完了、`scripts/analyze_clothing_color.py` を新規作成。服パッチ静止画1枚から画像全体1BBで ViTPose 推論→HALPE26 胴体4点で ROI 切り出し→ROI内 HSV を測定し、`postprocess_pink_id.py` 用の推奨 `FIXED_HSV_RANGES`・S/V下限を提案する CLI 診断ツール。循環統計で色相環またぎに対応、S/V下限のみデータ駆動（上限255固定）。要求仕様・設計を Subagentレビュー3往復で高中ゼロ化、実装コードも Write前 Subagentレビュー。E0014-01.png（本番 pink_id 取りこぼし実例）で current pink_ratio=0.0099→proposed=0.6046（約61倍、推奨レンジ `[((153,21,125),(179,255,255)),((0,21,125),(12,255,255))]`）を確認。既存 merge_halpe26.py / postprocess_pink_id.py は無変更。推奨レンジの postprocess_pink_id.py への実反映は別案件）
- **feat-054**: analyze_clothing_color.py の HSV 設定ファイル（JSON）出力対応（2026-05-27完了、`scripts/analyze_clothing_color.py` に `--json-out` を追加し、`propose_hsv_ranges()` の推奨レンジを feat-053 互換 JSON（`fixed_hsv_ranges` + `min_pink_ratio`）として常時書き出す。案C の機能②＝手写経撲滅。`min_pink_ratio` は固定 0.03（`postprocess_pink_id.MIN_PINK_RATIO` を import、静止画では動画BB比率の適切値を決められないため実運用は `--min-pink-ratio` で再調整）。新規関数 `build_hsv_config_dict` / `write_hsv_config`。JSON は PNG 保存後に書き出し（書込失敗でも診断PNGを保全）、推奨レンジ空時は JSON 不出力＋`[WARN]`。整形は `scripts/conf/*.json` と同じ compact 形式（1レンジ=1行）。要求仕様・設計を Subagentレビュー2往復で高中ゼロ化、実装差分も Write前 Subagentレビュー。AC-001（2キーのみ・`load_hsv_config` 通過・整数維持・stdout一致）/ AC-002（デフォルトパス・INFOログ）/ AC-003（空レンジ時不出力）全PASS。E0014-01.png で生成 JSON が手写経の `scripts/conf/E0014.json` とバイト一致を確認。既存 stdout/PNG 出力・`postprocess_pink_id.py` / `merge_halpe26.py` は無変更）
- **feat-053**: postprocess_pink_id.py の HSV 設定ファイル読み込み対応（2026-05-27完了、`scripts/postprocess_pink_id.py` に `--hsv-config` を追加し、ハードコードの `FIXED_HSV_RANGES` / `min_pink_ratio` を JSON 設定ファイルから差し替え可能化（feat-052 推奨レンジを実運用へ反映する案C の機能①＝コア）。設定ファイルは `fixed_hsv_ranges` + `min_pink_ratio` の2キー必須（B-1）、`min_pink_ratio` 優先順位は CLI明示 > 設定ファイル > 既定0.03（A-1、`--min-pink-ratio` の default を None 化して明示判定）。`compute_pink_ratio(roi, ranges=None)` で後方互換維持、`FIXED_HSV_RANGES` / `MIN_PINK_RATIO` 定数は残置（analyze_clothing_color.py / plot_pink_ratio_timeline.py の import 互換）。要求仕様・設計を Subagentレビュー2往復で高中ゼロ化、実装差分も Write前 Subagentレビュー。AC-001-1（`git stash` で改修前と camSony1_S 900フレーム `diff -r` 差分0）/ AC-001-2 / AC-002（不正設定で exit 1）/ AC-003（優先順位）/ AC-005（サマリ表示）全PASS。サンプル `docs/issues/feat-053-pink-id-hsv-config/example_hsv_config.json`、患者向け設定 `scripts/conf/E0014.json` を配置。機能②（analyze_clothing_color.py の同スキーマ JSON 出力）は後続案件）
- **feat-055**: analyze_clothing_color.py の複数画像入力・プール提案・閾値検証対応（2026-05-28完了、`scripts/analyze_clothing_color.py` の位置引数を `nargs='+'` 化し、2枚以上で「複数画像モード」に分岐。全画像の胴体ROIクロマ画素を `np.concatenate` でプール（BGR往復変換なし＝画素脱落ゼロ）し循環統計で全画像を覆う単一レンジを提案、各画像 `pink_ratio` を `--threshold`（既定0.03、`ratio > threshold` でPASS・==はFAIL）と照合してレポート（表示のみ、exit 0）。`propose_hsv_ranges` の循環統計コアを `propose_ranges_from_chroma(Hc,Sc,Vc,percentile)` に抽出（pure refactor、戻り値4要素不変）。フェーズ順序＝1)全画像推論・ROI・stats収集 2)プール提案 3)閾値検証 4)画像ごとPNG 5)統合JSON。PNG/JSON出力は提案後なので読込/推論失敗時は出力ファイルなし。複数画像モードのPNGは画像ごと `<stem>_color_analysis.png`、JSONは統合1個（`--json-out` or `<first_stem>_pooled_hsv_config.json`、`min_pink_ratio`=0.03固定、`--out`は無視＋WARN）。1枚指定時は単一画像モードで feat-054 と完全一致（AC-001-1：`git stash` 突合で推奨/ratio行一致・JSONバイト一致）。要求仕様・設計を Subagentレビュー1往復で高1中5低1→高中ゼロ化、実装差分も Write前 Subagentレビュー。`testdata/E0014/` 3枚で全AC PASS（プール推奨 `[((0,21,117),(12,255,255)),((163,21,117),(179,255,255))]`、3枚 ratio=0.5928/0.7701/0.7049 全て>0.03でALL PASS、生成JSONは手書き `scripts/conf/E0014.json` と一致）。既存 merge_halpe26.py / postprocess_pink_id.py は無変更）
- **feat-056**: postprocess_pink_id.py への確認動画同時出力統合（--visualize）（2026-05-28完了、`scripts/postprocess_pink_id.py` に `--visualize` を追加し、pink_id 付与 JSON 書き出しと同時に確認用 MP4（BB・スケルトン・pink_id ラベルをオーバーレイ）を出力。描画は `visualize_patient_video.py` の `draw_person` / `filter_people` / `get_color_for_mode` / `draw_frame_number` を import 再利用し、`visualize_patient_video.py` は無変更。動画フルスキャンを 1 回に集約（従来の postprocess→visualize 別実行の 2 回読みを削減）。描画 ID は pink_id 固定、デフォルト filter モード（pink_id=1）。追加CLI: `--vis-out-dir` / `--vis-mode {filter,all}` / `--vis-filter-values` / `--vis-kpt-thr` / `--draw-start` / `--draw-end` / `--show-*` 5フラグ（visualize 互換）。`--visualize` 無指定時は完全後方互換（※bug-004 でデフォルトON化し、後方互換は `--no-visualize` 指定時に変更）。MP4名は `vis_pink_id_<mode>_<stem>.mp4`。pink_id 計算は描画範囲によらず常に全フレーム実行、`--draw-start/--draw-end` は MP4 書き込み範囲のみ制限（出力 JSON は常に全フレーム）。要求仕様・設計を Subagentレビュー1往復で高0中2低3→全反映、実装差分も Write前 Subagentレビューで高中ゼロ。camSony1_S 900フレームで AC 全PASS：後方互換 `git stash` diff -r 差分0、描画範囲 0-99 で MP4 100フレーム・出力 JSON 全900フレーム・JSON内容は後方互換版と一致、処理0.6秒（1493fps、描画100フレームのみ）。既存 visualize_patient_video.py / merge_halpe26.py は無変更）
- **feat-057**: postprocess_pink_id.py の --out-dir 自動導出（任意化）（2026-05-28完了、`scripts/postprocess_pink_id.py` の `--out-dir` を `required=True` から任意化し、未指定時は `os.path.normpath(args.json_dir) + "_pink_id"` を自動導出（INFOログ1行出力）。既存の上書き防止チェック（json-dir と out-dir 同一禁止）は維持、接尾辞付与により自動導出値は自然に非抵触。要求仕様・設計を Subagentレビュー（高中ゼロ）、実装差分も Write前 Subagentレビュー。後方互換: `--out-dir` 明示時は従来と完全一致。動画出力先 `--vis-out-dir` とは独立で連動しない）
- **bug-004**: postprocess_pink_id.py の確認動画がデフォルトで出力されない（feat-056 仕様漏れ）（2026-05-28完了、`scripts/postprocess_pink_id.py:381` の `--visualize` を `action="store_true"`（既定 False）から `argparse.BooleanOptionalAction` + `default=True` に変更し、確認動画 MP4 をデフォルトON化（`--no-visualize` で抑制）。feat-056 が確認動画をオプトイン設計にしていた仕様漏れの修正。分岐ロジック（`if args.visualize:`）・出力先 `--vis-out-dir`（既定 output）は不変。feat-056 の requirements.md / design.md を本文更新＋変更履歴追記、scripts/README.md 3箇所・CLAUDE.md を整合更新（方針: 過去案件ドキュメントは現行挙動に本文更新し末尾に変更履歴1行追記）。investigation.md を Subagentレビュー（高中ゼロ）。リグレッション注意: デフォルトで全フレーム描画になり大規模動画では処理時間増、`--no-visualize` で従来の JSON のみ高速処理に戻せる。feat-057 の手動テストはこの修正で動画出力を確認できるようになり完了）
- **feat-058**: postprocess_pink_id.py の確認動画保存先デフォルトを out-dir の親に変更（2026-05-28完了、`scripts/postprocess_pink_id.py` の `--vis-out-dir` を `default="output"` から `default=None` に変更し、未指定時は `os.path.dirname(os.path.normpath(args.out_dir)) or "."`（out-dir の親、末尾スラッシュは normpath で吸収・親なし相対パスは `.` フォールバック）を出力先とする。挿入位置は feat-057 の `--out-dir` 自動導出後・`os.makedirs(args.out_dir)` 直後。feat-056 の既定 `output` 固定がテスト用ディレクトリで本番動画と混ざる問題を解消。`--vis-out-dir` 明示時はその値を優先（後方互換）。`--no-visualize` 時は導出するが未使用で無害。要求仕様・設計を Subagentレビュー（高中ゼロ、低3反映）、実装差分も Write前 Subagentレビュー（高中ゼロ）。scripts/README.md / CLAUDE.md を整合更新）
- **feat-059**: analyze_clothing_color.py の色非依存レンジ提案（有彩色・白・黒・灰対応）（2026-06-01完了、`scripts/analyze_clothing_color.py` を有彩色専用から色非依存化。白服（E0049）で患者を追える特徴量を出せない問題に対し、ROIの chroma_ratio を `--chroma-regime-min`（既定0.4）で判定して chromatic / achromatic の2レジームに自動分岐。achromatic は新関数 `propose_achromatic_ranges` で色相H全域・S/V上下限を全画素percentileで囲む（白＝低S高V・黒＝低S低Vが分布に追従）。chromatic は既存 `propose_hsv_ranges` / `propose_ranges_from_chroma` を無変更で呼び後方互換維持（提案行の前に regime 行が1行増えるのみ）。新規関数 `extract_all_hsv` / `decide_color_regime` / `propose_achromatic_ranges`、`render_analysis_png` に `regime` / `all_hsv` 引数追加（achromatic時は全画素ヒストグラム＋S/V境界線、境界は proposed_ranges[0] から取得）。単一・複数画像モード両対応（複数はプール全体のchroma_ratioで1回判定し全画像同一レジーム）。方式B（分類せず分布から直接percentile包囲）を**消去法で**採用（方式A=有彩/白/黒/灰分類は信頼できる閾値を決められず前提が成立しないため却下）。デフォルト閾値0.4は実測（白E0049 chroma_ratio最大0.247 / ピンクE0014最小0.713）の両側マージンから決定、`--sat-min`/`--val-min` 依存をhelpに明記。要求仕様・設計を **Codexレビュー**（CLAUDE.md新ルール、`codex exec --dangerously-bypass-approvals-and-sandbox`）3往復で高1中2→中1→高中ゼロ化、実装差分も Subagentレビュー（高中ゼロ）。AC全PASS：ピンク単一/複数の後方互換 `git stash` 突合でJSONバイト一致・提案行一致、白服 achromatic で proposed_ratio 0.83〜0.98、閾値切替・help注記確認。既存 merge_halpe26.py / postprocess_pink_id.py は無変更。scripts/README.md / CLAUDE.md を整合更新。判別力（白服患者を他人・白い寝具と区別して動画で正しく選べるか）の検証は別案件）

## 関連リポジトリ

- **HuggingFace版**: `~/git/ViTPose_HuggingFace/` — HuggingFace Transformers経由のViTPose++推論。COCO 17キーポイントのみ対応。feat-001でHead/Neck取得不可と判明し、本リポジトリに移行
