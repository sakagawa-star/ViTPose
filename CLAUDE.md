# CLAUDE.md

このファイルはClaude Codeがプロジェクトを理解するためのガイドです。

## セッション引き継ぎ

- セッション開始時にプロジェクトルートの `.claude/handovers/` ディレクトリを確認し、ファイルが存在すれば最新のものを読み込む
- セッション終了時や作業の区切りでは `/handover` の実行を促す

## プロジェクト概要

本プロジェクトは、ViTAE-Transformer/ViTPose（MMPoseベース）を使用して、室内の対象動画に対して2Dポーズ推定を行う。HuggingFace版ViTPose++ではデコーダヘッドがCOCO 17固定でHead/Neckキーポイントが取得できないため、MMPose版に移行した。

### 目標
- ViTPose++のMoEアーキテクチャを活用し、HALPE 26相当のキーポイント（COCO 17 + Head + Neck + Hip center + 足6点）を出力する
- 結果をPose2Simに渡せるOpenPose JSON形式で出力する

### 背景
- Pose2Sim付属のRTMPose + YOLOXでは、遮蔽物が多い室内環境で精度が不十分
- 遮蔽ベンチマーク(OCHuman)で高精度なViTPose++に切り替え
- HuggingFace版（`~/git/ViTPose_HuggingFace/`）で技術検証済み（feat-001）。dataset_indexを切り替えてもデコーダヘッドがCOCO 17固定のため、Head/Neck取得不可と判明
- MMPose版ではデータセットごとに別のデコーダヘッド（異なるnum_joints）を持つため、AIC 14点（Head/Neck含む）やCOCO-WholeBody 133点が取得可能

## 技術スタック

言語・パッケージ管理・ライブラリ一覧（バージョン・選定理由）・実行環境（GPU 等のハードウェア制約を含む）は `docs/TECH_STACK.md` を参照する。

## プロジェクト知識（データ・ディレクトリ構成・ドメイン知識）

データの所在と仕様、ディレクトリ構成、ドメイン知識（ViTPose++ MoE の構造・キーポイント定義・入力動画の特性・後処理パイプラインの構成・関連リポジトリ等）は **`docs/PROJECT_KNOWLEDGE.md`** に集約している。

- **必読**: 実作業・案件の調査に入る前に `docs/PROJECT_KNOWLEDGE.md` を全文読む（本ファイルには要約を置かない。知識は同ファイルのみで管理する）
- **更新の役割分担（非対称ルール）**:
  - `docs/PROJECT_KNOWLEDGE.md` の**内容**は、各案件の完了処理で更新する（feat/bug: 案件で得た知見・データの状態・ファイルの追加削除の反映。update: ファイルの追加削除の反映）。追記には出所の案件 ID を付す
  - `docs/PROJECT_KNOWLEDGE.md` の**構成**（分割・セクション再編）の変更は update 案件で扱う
  - **`CLAUDE.md`（本ファイル）の変更は update 案件でのみ行う。** feat/bug 案件の完了処理で本ファイルを更新することはない
- **暫定措置（update-002 の反映まで）**: 本ファイルには update 案件の手順（ドキュメント更新フロー）がまだない。update-002 の反映が完了するまで、update 案件は開発ドキュメントテンプレート `~/git/DEV_TEMPLATE/template/CLAUDE.md` の「ドキュメント更新フロー（update-XXX 案件）」に従う。本項目は update-002 で削除する

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
6. **実装** → ドキュメント（要求仕様書・機能設計書・CLAUDE.md・`docs/PROJECT_KNOWLEDGE.md`）を読んで実装する。実装完了後、「テスト」セクションのルールに従ってテストを実行する
7. **手動テスト** → ユーザーがテストする。以下の問題があれば `docs/BUGFIX_STANDARD.md` に従って修正計画を `docs/issues/{案件フォルダ}/investigation.md` に追記する（上書きしない。イテレーション番号を付けて履歴を残す）。**ユーザーの承認を得た上で、ステップ2〜7を繰り返す**（コード修正はステップ6で行う。ステップ7で直接コードを編集してはならない）
   - 不具合の発見
   - 要求通りに実装されていない
   - 要求仕様作成時のヒアリング漏れ
8. **完了** → `docs/BACKLOG.md` のステータスを Closed に更新する。`docs/CHANGELOG.md` に完了内容を記録する。`docs/PROJECT_KNOWLEDGE.md` を更新する（ファイルの追加・削除があった場合はディレクトリ構成を最新にし、案件で得た知見・データの状態の変化を該当セクションに追記する。追記には案件 ID を付す）。`CLAUDE.md` は更新しない（update 案件でのみ変更する）

### 不具合修正フロー（bug-XXX 案件）

既存機能の不具合を修正する場合、以下のフローを**厳守**する。

1. **案件作成** → `docs/issues/bug-{number}-{slug}/` フォルダを作成し、`docs/BACKLOG.md` に追加する。`README.md` に不具合の概要と再現手順を記録する
2. **調査・修正計画** → `docs/BUGFIX_STANDARD.md` に従い、既存コードを調査する。修正計画を `docs/issues/{案件フォルダ}/investigation.md` に記録する。**この時点でコードを編集してはならない**
3. **ドキュメント保存** → investigation.md の保存を確認する。**保存が完了するまで実装に進んではならない**
4. **レビュー（Codex + 人）** → 保存されたドキュメントを **Codex** でレビューする。実行方法は後述の「Codexによるレビューの実行方法」を参照。ユーザーも同時にレビューする。レビュー実行時は `docs/REVIEW_CRITERIA.md` の基準に従うこと
5. **修正（必要な場合）** → レビューで問題があれば、再調査してドキュメントを更新する。**ステップ2〜4を問題がなくなるまで繰り返す**
6. **実装** → 承認された修正計画に沿ってコードを修正する。計画にない変更が必要になった場合は中断して報告する
7. **手動テスト** → ユーザーがテストする。問題があれば `docs/BUGFIX_STANDARD.md` に従って investigation.md にイテレーション番号を付けて追記し、**ユーザーの承認を得た上で、ステップ2〜7を繰り返す**（コード修正はステップ6で行う。ステップ7で直接コードを編集してはならない）
8. **完了** → `docs/BACKLOG.md` のステータスを Closed に更新する。`docs/CHANGELOG.md` に完了内容を記録する。`docs/PROJECT_KNOWLEDGE.md` を更新する（ファイルの追加・削除があった場合はディレクトリ構成を最新にし、案件で得た知見・データの状態の変化を該当セクションに追記する。追記には案件 ID を付す）。`CLAUDE.md` は更新しない（update 案件でのみ変更する）

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

## 完了済み案件

詳細は `docs/BACKLOG.md`（一覧）および `docs/CHANGELOG.md`（リリース履歴）を参照。
