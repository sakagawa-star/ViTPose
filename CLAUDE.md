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
│   └── postprocess_reid.py           # Re-IDポストプロセス：JSONにstable_id付与（feat-028）
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
4. **レビュー（Subagent + 人）** → 保存されたドキュメントをSubagent（Agentツール）でレビューする。ユーザーも同時にレビューする。レビュー実行時は `docs/REVIEW_CRITERIA.md` の基準に従うこと
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
4. **レビュー（Subagent + 人）** → 保存されたドキュメントをSubagent（Agentツール）でレビューする。ユーザーも同時にレビューする。レビュー実行時は `docs/REVIEW_CRITERIA.md` の基準に従うこと
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

## 現在進行中の案件

- **feat-026**: 見切れ再同定の検証（feat-028完了により再開可能。stable_id付きJSON生成済み。次ステップ: stable_idごとのスケルトン可視化で目視検証）

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
- **feat-025**: BB重複除去方式の比較（2026-04-04完了、案A採用。OKS中央値0.926で案Eも実用レベルだが、案Aの方がconf>0.3キーポイントが3%多い）
- **feat-028**: JSONにトラッキングID記録（2026-04-07完了、postprocess_reid.pyで既存JSONにstable_idを付与するポストプロセス。camSony1_L 321Kフレーム、845ユニークstable_id）

## 関連リポジトリ

- **HuggingFace版**: `~/git/ViTPose_HuggingFace/` — HuggingFace Transformers経由のViTPose++推論。COCO 17キーポイントのみ対応。feat-001でHead/Neck取得不可と判明し、本リポジトリに移行
