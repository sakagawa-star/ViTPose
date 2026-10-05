# update-002 反映設計書: 開発テンプレート最新版の取り込み（2/2）— 開発フロー・Codex レビュー（Herdr 対話方式）・AGENTS.md・基準書の更新

対象案件: `docs/issues/update-002-adopt-template-process/`
調査記録: 同フォルダの `README.md`（候補 C1〜C19 の経緯と目的）

本書は**自己完結**している。`/clear` 後でも本書だけで反映作業ができる。

## 1. 概要

`CLAUDE.md` の統治部分（「## 開発方針」から「## コーディング規約」の直前まで）を、テンプレート `template/CLAUDE.md`（DEV_TEMPLATE コミット `ffd2c49`）の同じ範囲で置き換え、本リポジトリ向けの読み替え（S1〜S13）を適用する。あわせて、テンプレートの `AGENTS.md`・基準書・セットアップ文書を導入し、`.gitignore` を補い、update-001 の暫定措置を削除する。

| 変更 | 内容 | 章 |
|---|---|---|
| D1 | `CLAUDE.md` の統治部分をテンプレートで置き換え、読み替え S1〜S13 を適用する | 4 |
| D2 | `CLAUDE.md` の暫定措置（update-001 で追加）を削除する | 5 |
| D3 | `AGENTS.md`・`docs/HERDR_SETUP.md`・`docs/codex-exec-ubuntu24-bwrap-fix.md` をテンプレートから新規作成する（無改変） | 6 |
| D4 | `docs/BUGFIX_STANDARD.md`・`docs/DESIGN_STANDARD.md` をテンプレートの内容で置き換える（無改変） | 6 |
| D5 | `docs/REVIEW_CRITERIA.md` をテンプレートの内容で置き換え、本リポジトリ固有の例示を3箇所に併記する | 7 |
| D6 | `.gitignore` に `.claude/settings.local.json` を追加する | 8 |

- **反映元の取得方法**: テンプレートのファイルは、作業ツリーではなく固定コミットから取得する: `git -C /home/sakagawa/git/DEV_TEMPLATE show ffd2c49:{パス}`（例: `ffd2c49:template/CLAUDE.md`）。DEV_TEMPLATE の作業ツリーが更新されていても結果が変わらない
- **実装者**: テンプレート `template/CLAUDE.md`「ドキュメント更新フロー」ステップ5 に従い、Sonnet サブエージェントが本書に厳密に従って反映する（`CLAUDE.md`「プロジェクト知識」節の暫定措置による）
- **テスト**: コード変更がないため、自動テスト・手動テストとも不要。検証は 9章の静的確認で行う

### 設計の制約

1. **テンプレートの文面は無改変で取り込む**。変えてよいのは本書に列挙した読み替え（S1〜S13、R1〜R3、`.gitignore` の追加）だけ（README C1〜C16 の (d)）
2. **本リポジトリ固有の規定・例示を失わない**（README「本リポジトリ固有の規定・例示の保持」）
3. **`CLAUDE.md` の「## 開発方針」より前（D2 の1行を除く）と「## コーディング規約」以降は変更しない**
4. **自分で書く文にドメイン特定語を入れない**: 本書が定める新しい文面（S4〜S11・R1〜R3・`.gitignore` のコメント・10章の追記行）は本書のとおりにし、言い換え・補足を加えない

## 2. 変更対象ファイル

| # | ファイル | 変更方式 | 章 |
|---|---|---|---|
| 1 | `CLAUDE.md` | ブロック置換（1箇所）＋読み替え、1行削除 | 4・5 |
| 2 | `AGENTS.md` | 新規作成（テンプレートと同一） | 6 |
| 3 | `docs/HERDR_SETUP.md` | 新規作成（テンプレートと同一） | 6 |
| 4 | `docs/codex-exec-ubuntu24-bwrap-fix.md` | 新規作成（テンプレートと同一） | 6 |
| 5 | `docs/BUGFIX_STANDARD.md` | 全置換（テンプレートと同一） | 6 |
| 6 | `docs/DESIGN_STANDARD.md` | 全置換（テンプレートと同一） | 6 |
| 7 | `docs/REVIEW_CRITERIA.md` | 全置換（テンプレート＋3箇所の併記） | 7 |
| 8 | `.gitignore` | 行の挿入 | 8 |

完了処理（10章）で、本案件の `README.md`・`docs/BACKLOG.md`・`docs/CHANGELOG.md`・`docs/PROJECT_KNOWLEDGE.md` を Claude Code 本体が更新する。上記以外のファイルは一切変更しない。

## 3. 事前確認（反映の開始前。1つでも満たさなければ反映せず中断して報告する）

作業ディレクトリは `/home/sakagawa/git/ViTPose`。

| # | 確認内容 | 方法 | 期待 |
|---|---|---|---|
| P1 | 作業ツリーに本案件以外の未コミット変更がない | `git status --short` | 本案件フォルダ配下と `docs/BACKLOG.md`（update-002 の行の追加・更新のみ）以外に変更がない。`scripts/conf/` の未追跡 JSON は無関係なので許容する |
| P2 | テンプレートの固定コミットが取得できる | `git -C /home/sakagawa/git/DEV_TEMPLATE cat-file -t ffd2c49` | `commit` |
| P3 | `CLAUDE.md` の見出し構成 | `grep -n '^## ' CLAUDE.md` | 次の順で過不足なく並ぶ: `## セッション引き継ぎ`、`## プロジェクト概要`、`## 技術スタック`、`## プロジェクト知識（データ・ディレクトリ構成・ドメイン知識）`、`## 開発方針`、`## コーディング規約`、`## 完了済み案件` |
| P4 | 読み替えの旧文の出現回数 | 4.2 の各旧文を、テンプレートの置換範囲（4.1）の中で数える | 4.2 の表の「期待回数」と一致する |
| P5 | D2 の削除対象 | `grep -c '^- \*\*暫定措置（update-002 の反映まで）\*\*' CLAUDE.md` | `1` |
| P6 | D5 の旧文 | 7章の R1〜R3 の旧文を、テンプレートの `REVIEW_CRITERIA.md` で数える | すべて `1` |
| P7 | D6 の目印 | `grep -c '^\.claude/handovers/$' .gitignore`、`grep -c 'settings.local.json' .gitignore` | `1`、`0` |
| P8 | 新規作成するファイルが未存在 | `ls AGENTS.md docs/HERDR_SETUP.md docs/codex-exec-ubuntu24-bwrap-fix.md` | 3つとも存在しない |
| P9 | 反映元で経緯を確認できない候補のユーザー決定 | 本案件 `README.md` の「要ユーザー確認事項」と C8・C11 の「扱い」 | C8 は「取り込む」、C11 は「取り込まない」のユーザー決定（日付と発言）が記録されている。記録がない、または決定が本書の設計（C8 を含めて取り込み、C11 を S12・S13 で除く）と異なる場合は反映せず中断する |

## 4. D1: `CLAUDE.md` の統治部分の置き換え

### 4.1 置換範囲

- **置換される範囲（本リポジトリ）**: `CLAUDE.md` の `## 開発方針` の見出し行から、`## コーディング規約` の見出し行の直前の行まで（`## コーディング規約` の行は含まない）
- **差し込む内容（テンプレート）**: `git -C /home/sakagawa/git/DEV_TEMPLATE show ffd2c49:template/CLAUDE.md` の出力の、`## 開発方針` の見出し行から `## コーディング規約` の見出し行の直前の行まで（367行。`## Claude Code 運用ルール` 節を含む）に、4.2 の読み替えを適用したもの

置換範囲の直後に `## コーディング規約` が続く形（間に空行1行）は、テンプレート側の範囲の末尾が空行で終わるため自然に保たれる。

### 4.2 読み替え（テンプレートの範囲に対して、この順序で適用する）

各読み替えの前に、旧文がテンプレートの範囲内に「期待回数」だけ現れることを検査し、一致しなければ中断して報告する。正確な文字列は 4.3 の Python リテラルを正とする（表は要旨）。

| # | 対象 | 変更 | 期待回数 | 理由（README の候補） |
|---|---|---|---|---|
| S1 | レビューストリームの命名例 | `（例: 略称が \`myprj\` の場合 \`rev-myprj-update-001\`）` → `（例: \`rev-vitpose-update-001\`）` | 1 | プロジェクト略称を `vitpose` とする（update-001 と同じ） |
| S2 | 細分化時の命名例 | `（例: \`rev-myprj-feat-009-p1\`）` → `（例: \`rev-vitpose-feat-009-p1\`）` | 1 | 同上 |
| S3 | プロジェクト略称 | `{{プロジェクト略称}}` → `vitpose` | 3 | 同上 |
| S4 | 開発方針 | 「大きな機能を一度に作らない…」の行の直後に、本リポジトリの方針「MMPose版ViTPose++のコードは可能な限り変更せず、推論パイプラインを別途構築する」の行を挿入 | 1（目印の行） | P2 の保持 |
| S5 | 機能追加・不具合修正フロー ステップ8 の README 更新義務 | 更新対象を `scripts/README.md` にし、ルートの `README.md` を対象外と明記 | 2 | 採らなかった案 C |
| S6 | Sonnet 委任の禁止事項 | `README.md` → `scripts/README.md` | 1 | S5 と整合させる |
| S7 | 命名規則の例 | `（例: \`bug-001-input-validation\`）` → `（例: \`bug-001-dataset-index-type\`）` | 1 | C5 (d) |
| S8 | 「テスト」節の置き場と実行コマンド | `tests/` → `tests/scripts/`（MMPose 本体のテストを除く旨を明記）、実行コマンドを `uv run pytest tests/scripts -v` に | 1 | C12 |
| S9 | 「テスト」節の末尾 | テストがない間の記録方法と、実データ確認の所在の2行を追加 | 1（目印の行） | C12 |
| S10 | git 操作のコミットメッセージのトレーラー | 固定のモデル名（`Claude Opus 5`）を、Claude Code が指定する帰属行に従う形に | 1 | 下記 4.4 |
| S11 | 依頼の送り方 | `agent_prompt_stalled` の行の直後に、`/new` 後のダイアログと容量エラーの扱いの2行を追加 | 1（目印の行） | C13 |
| S12 | 「Bash 実行時のルール」節 | 見出しから次の見出しの直前までを削除 | 1 | C11（取り込まない。2026-10-05 ユーザー決定） |
| S13 | git 操作の委任指示の項目4「Bashルールの継承」 | 項目4 を削除し、項目5「失敗時の扱い」を項目4 に繰り上げる | 1 | C11 と同じ。項目番号を参照する記述はテンプレート内にない（`grep -n '項目[0-9]'` で確認。ヒットは Sonnet 委任の節の「項目3」のみ） |

### 4.3 読み替えの正確な文字列

```python
REPLACEMENTS = [
    # (旧文, 新文, 期待回数)
    ("（例: 略称が `myprj` の場合 `rev-myprj-update-001`）",
     "（例: `rev-vitpose-update-001`）", 1),  # S1
    ("（例: `rev-myprj-feat-009-p1`）",
     "（例: `rev-vitpose-feat-009-p1`）", 1),  # S2
    ("{{プロジェクト略称}}", "vitpose", 3),  # S3
    ("- 大きな機能を一度に作らない。小さく作って動作確認し、次の機能へ進む（feat 案件では、後述「マイルストーン分割（feat 案件の必須手順）」の分割基準で機械的に担保する）\n",
     "- 大きな機能を一度に作らない。小さく作って動作確認し、次の機能へ進む（feat 案件では、後述「マイルストーン分割（feat 案件の必須手順）」の分割基準で機械的に担保する）\n"
     "- MMPose版ViTPose++のコードは可能な限り変更せず、推論パイプラインを別途構築する\n", 1),  # S4
    ("`README.md` に記載済みの内容（コマンド、CLIオプション、入力/出力形式、既定値、実行環境・依存条件）に変更があった場合は `README.md` を最新に更新する。**リポジトリを公開する場合、`README.md` にはローカルの実パスを書かない**",
     "`scripts/README.md` に記載済みの内容（コマンド、CLIオプション、入力/出力形式、既定値、実行環境・依存条件）に変更があった場合は `scripts/README.md` を最新に更新する（ルートの `README.md` は ViTPose 本家のオリジナルであり、更新対象にしない）。**リポジトリを公開する場合、`scripts/README.md` にはローカルの実パスを書かない**", 2),  # S5
    ("BACKLOG.md / CHANGELOG.md / CLAUDE.md / README.md / docs/PROJECT_KNOWLEDGE.md の更新も行わせない",
     "BACKLOG.md / CHANGELOG.md / CLAUDE.md / scripts/README.md / docs/PROJECT_KNOWLEDGE.md の更新も行わせない", 1),  # S6
    ("（例: `bug-001-input-validation`）",
     "（例: `bug-001-dataset-index-type`）", 1),  # S7
    ("- テストは `tests/` ディレクトリに置く\n- テスト実行コマンド: {{例: `uv run pytest -v`}}\n",
     "- 自動テストは `tests/scripts/` に置く（`tests/` 直下の既存のテストは MMPose 本体のものであり、本リポジトリの案件のテストに含めない）\n- テスト実行コマンド: `uv run pytest tests/scripts -v`\n", 1),  # S8
    ("  - 内容：テストコマンドの出力をそのまま保存する\n",
     "  - 内容：テストコマンドの出力をそのまま保存する\n"
     "- `tests/scripts/` にテストが1件もない間（ディレクトリが未作成の場合を含む）は、テストを実行せず、テスト結果ファイルに「自動テストなし（tests/scripts/ にテストがない）」と記録する\n"
     "- GPU 推論・動画を伴う実データでの動作確認は、自動テストとは別に、各案件の design.md に定義した検証手順で行う\n", 1),  # S9
    ("末尾トレーラーは `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`",
     "末尾トレーラーは、Claude Code が指定する `Co-Authored-By:` 行（実行中のモデル名を含む。例: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`）", 1),  # S10
    ("- `agent_prompt_stalled` が返ったら、画面を読んで原因（ダイアログ・エージェント消滅等）を確認する\n",
     "- `agent_prompt_stalled` が返ったら、画面を読んで原因（ダイアログ・エージェント消滅等）を確認する\n"
     "- `/new` を送った後に「新しい会話の実行場所」を選ぶダイアログ（`1. Current checkout` / `2. New worktree`。codex v0.160.0 で確認）が表示された場合は、`herdr agent send-keys {ストリーム名} enter` で `1. Current checkout` を選ぶ（`2. New worktree` は別の作業ツリーを作り、レビュー対象の未コミットの文書が見えなくなるため選ばない）。`herdr agent read {ストリーム名} --source visible` で入力待ちに戻ったことを確認してから次の依頼を送る\n"
     "- 依頼が codex 側のエラー（例: 「Selected model is at capacity」）で回答前に中断した場合（「[AGENTS.md適用]」で始まる回答が出ていない場合）は、その回をレビュー結果として採用しない（`codex-NN.result.md` を作らず、連番を進めない）。同じ依頼を同一会話で再送してよい。同じ原因の中断が2回続いたら「行き詰まり検出」に従い、ユーザーに報告して指示を仰ぐ\n", 1),  # S11
    ("### Bash 実行時のルール\n\n"
     "- **`cd <path> && <command>` の連結は禁止。** Bashツールはプロジェクト作業ディレクトリで動くため `cd` は不要。連結すると先頭トークンが `cd` になり、`.claude/settings.json` / `.claude/settings.local.json` のallowlist（例: `Bash(herdr *)`、`Bash(git status)`）が一致せず、毎回パーミッションプロンプトが発生する\n"
     "- 別ディレクトリで実行する必要がある場合は、コマンド側のオプションを使う（例: `git -C <path> status`、`make -C <path> ...`）\n"
     "- どうしても複数コマンド連結が必要な場合も、先頭トークンが安全・許可済みであるかを確認してから書く\n"
     "\n",
     "", 1),  # S12
    ("4. **Bashルールの継承**: `cd <path> && <command>` 連結禁止、`git -C <path> ...` 形式を使う\n"
     "5. **失敗時の扱い**:",
     "4. **失敗時の扱い**:", 1),  # S13
]
```

S3 は S1・S2 の後に適用する（S1・S2 の旧文は `{{プロジェクト略称}}` を含まないため、順序による干渉はない）。S4・S9・S11 は目印の行を残したまま直後に行を加える置換である。S12 は節（見出し・空行・箇条書き3行・後続の空行）を丸ごと削除し、直後の「### git 操作の実行方法（Opusサブエージェント）」の見出しが「### 行き詰まり検出（全作業共通・必須）」節の後ろに空行1行を挟んで続く形になる。

### 4.4 S10 の理由

テンプレートのトレーラーは `Claude Opus 5` という特定のモデル名で固定されている。Claude Code は実行中のモデル名を含む帰属行をセッションごとに指定するため（本リポジトリの update-001 のコミット `9ca22a5` は `Claude Opus 5.5`）、固定のモデル名を規定に書くと、実行中のモデルと異なる名前を書かせることになる。トレーラーを付ける義務（README C8 (d) に関わる「末尾にトレーラーを付ける」）は保持し、名前だけを指定元に委ねる。テンプレートへの還元候補とする（10章 完了処理の後の検討事項）。

### 4.5 置き換え後の見出し構成

置き換え後の `grep -n '^## ' CLAUDE.md` は次の順になる: `## セッション引き継ぎ`、`## プロジェクト概要`、`## 技術スタック`、`## プロジェクト知識（データ・ディレクトリ構成・ドメイン知識）`、`## 開発方針`、`## Claude Code 運用ルール`、`## コーディング規約`、`## 完了済み案件`。

## 5. D2: 暫定措置の削除

`CLAUDE.md` の次の1行（`- **暫定措置（update-002 の反映まで）**:` で始まる行。update-001 で `## プロジェクト知識` 節の末尾に追加）を、行末の改行ごと削除する。前後の行は変えない。

```
- **暫定措置（update-002 の反映まで）**: 本ファイルには update 案件の手順（ドキュメント更新フロー）がまだない。update-002 の反映が完了するまで、update 案件は開発ドキュメントテンプレート `~/git/DEV_TEMPLATE/template/CLAUDE.md` の「ドキュメント更新フロー（update-XXX 案件）」に従う。本項目は update-002 で削除する
```

## 6. D3・D4: テンプレートと同一のファイル

次の5ファイルは、テンプレートの固定コミットの内容をバイト単位で同一に書き出す（既存のものは全置換、ないものは新規作成）。

| 本リポジトリのパス | 取得元（`git -C /home/sakagawa/git/DEV_TEMPLATE show ffd2c49:{パス}`） |
|---|---|
| `AGENTS.md` | `template/AGENTS.md` |
| `docs/HERDR_SETUP.md` | `template/docs/HERDR_SETUP.md` |
| `docs/codex-exec-ubuntu24-bwrap-fix.md` | `template/docs/codex-exec-ubuntu24-bwrap-fix.md` |
| `docs/BUGFIX_STANDARD.md` | `template/docs/BUGFIX_STANDARD.md` |
| `docs/DESIGN_STANDARD.md` | `template/docs/DESIGN_STANDARD.md` |

コマンド例: `git -C /home/sakagawa/git/DEV_TEMPLATE show ffd2c49:template/AGENTS.md > AGENTS.md`

## 7. D5: `docs/REVIEW_CRITERIA.md`

テンプレート `template/docs/REVIEW_CRITERIA.md`（`ffd2c49`）の内容を書き出したうえで、次の3箇所を置換する（各旧文はファイル内に1回だけ現れる）。

```python
REVIEW_REPLACEMENTS = [
    ("- 各機能の異常系（入力不正、外部リソース取得失敗、メモリ不足等）の振る舞いが定義されているか",
     "- 各機能の異常系（入力不正、外部リソース取得失敗、メモリ不足等。本リポジトリではモデル読み込み失敗・GPU メモリ不足を含む）の振る舞いが定義されているか"),  # R1
    ("- 境界値（0件入力、範囲外、空・上限値等）の扱いが明記されているか",
     "- 境界値（0件入力、範囲外、空・上限値等。本リポジトリでは0人検出・フレーム範囲外を含む）の扱いが明記されているか"),  # R2
    ("- モジュール間のデータ型・形式が明記されているか（型・スキーマ・単位・値域等）",
     "- モジュール間のデータ型・形式が明記されているか（型・スキーマ・単位・値域等。本リポジトリでは BGR/RGB・テンソル型・shape を含む）"),  # R3
]
```

R1〜R3 は、本リポジトリの現行版にある固有の例示（README C16 (d)）を保持するための併記である。現行版の「モデル名（HuggingFace Hub のリポジトリ名）が正確か」は保持せず、テンプレートの「外部依存（API・モデル・サービスの識別子やエンドポイント）が正確か」に包含させる（HuggingFace 版から MMPose 版へ移行済みのため）。

## 8. D6: `.gitignore`

`.gitignore` の `.claude/handovers/` の行の直後に、次の2行を挿入する（ファイル末尾の改行の有無は変えない。`.claude/handovers/` の行は現在ファイルの最終行で、末尾に改行がある）。

```
# Claude Code のローカル設定（公開しない）
.claude/settings.local.json
```

## 9. 反映直後の検証（完了処理の前）

すべて静的確認。1つでも満たさなければ反映をやり直す（原因を報告して中断する）。作業ディレクトリは `/home/sakagawa/git/ViTPose`。

| # | 確認内容 | 方法 | 期待 |
|---|---|---|---|
| V1 | 変更ファイル | `git status --short` | 2章の8ファイル（新規3・変更5）と本案件フォルダ配下・`docs/BACKLOG.md`（update-002 の行）のみ（`scripts/conf/` の未追跡 JSON は除く） |
| V2 | `CLAUDE.md` の全体が設計どおり | 下記スクリプト1 | 出力 `OK` |
| V3 | 見出し構成 | `grep -n '^## ' CLAUDE.md` | 4.5 のとおり |
| V4 | テンプレートのプレースホルダが残っていない | `grep -c '{{' CLAUDE.md` | `0` |
| V5 | 旧レビュー方式の記述が残っていない | `grep -c 'dangerously-bypass\|resume --last\|ユーザーも同時にレビュー' CLAUDE.md` | `0` |
| V6 | 同一ファイル5件 | 下記スクリプト2 | 出力 `OK 5` |
| V7 | `REVIEW_CRITERIA.md` | 下記スクリプト2 | 同上（スクリプト2 が併せて確認する） |
| V8 | `.gitignore` | `tail -4 .gitignore` | 末尾4行が `# Claude Code セッション引き継ぎノート（公開しない）`、`.claude/handovers/`、`# Claude Code のローカル設定（公開しない）`、`.claude/settings.local.json` |
| V9 | 本リポジトリ固有の規定の保持 | `grep -c 'MMPose版ViTPose++のコードは可能な限り変更せず' CLAUDE.md`、`grep -c 'bug-001-dataset-index-type' CLAUDE.md`、`grep -c 'uv run pytest tests/scripts -v' CLAUDE.md` | すべて `1` |
| V10 | 暫定措置の削除 | `grep -c '暫定措置' CLAUDE.md` | `0` |
| V11 | C11 を取り込んでいない | `grep -c 'Bash 実行時のルール\|Bashルールの継承' CLAUDE.md` | `0` |

スクリプト1（V2。反映前の `CLAUDE.md`〔`git show HEAD:CLAUDE.md`〕とテンプレートから、本書の手順どおりの期待値を組み立てて比較する）:

```python
import subprocess

def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout

old = git("show", "HEAD:CLAUDE.md")
tpl = git("-C", "/home/sakagawa/git/DEV_TEMPLATE", "show", "ffd2c49:template/CLAUDE.md")
new = open("CLAUDE.md", encoding="utf-8").read()

REPLACEMENTS = [...]  # 4.3 の REPLACEMENTS をそのまま貼る

s = tpl.index("\n## 開発方針\n") + 1
e = tpl.index("\n## コーディング規約\n") + 1
block = tpl[s:e]
for a, b, n in REPLACEMENTS:
    assert block.count(a) == n, a[:40]
    block = block.replace(a, b)

head = old[: old.index("\n## 開発方針\n") + 1]
tail = old[old.index("\n## コーディング規約\n") + 1 :]
line = [l for l in head.split("\n") if l.startswith("- **暫定措置（update-002 の反映まで）**")]
assert len(line) == 1
head = head.replace(line[0] + "\n", "")
assert new == head + block + tail
print("OK")
```

スクリプト2（V6・V7）:

```python
import subprocess

def tpl(path):
    return subprocess.run(["git", "-C", "/home/sakagawa/git/DEV_TEMPLATE", "show", f"ffd2c49:{path}"],
                          capture_output=True, text=True, check=True).stdout

same = {
    "AGENTS.md": "template/AGENTS.md",
    "docs/HERDR_SETUP.md": "template/docs/HERDR_SETUP.md",
    "docs/codex-exec-ubuntu24-bwrap-fix.md": "template/docs/codex-exec-ubuntu24-bwrap-fix.md",
    "docs/BUGFIX_STANDARD.md": "template/docs/BUGFIX_STANDARD.md",
    "docs/DESIGN_STANDARD.md": "template/docs/DESIGN_STANDARD.md",
}
for mine, theirs in same.items():
    assert open(mine, encoding="utf-8").read() == tpl(theirs), mine

REVIEW_REPLACEMENTS = [...]  # 7章の REVIEW_REPLACEMENTS をそのまま貼る
rc = tpl("template/docs/REVIEW_CRITERIA.md")
for a, b in REVIEW_REPLACEMENTS:
    assert rc.count(a) == 1, a[:40]
    rc = rc.replace(a, b)
assert open("docs/REVIEW_CRITERIA.md", encoding="utf-8").read() == rc
print("OK", len(same))
```

スクリプト1・2 は `uv run python` で実行する。反映のコミット前（`HEAD:CLAUDE.md` が反映前の版）に実行すること。`[...]` の箇所は、本書の該当する Python リテラルの内容をそのまま貼る。

本章の期待値は、設計時（2026-10-05）に本書の手順を作業用の写しへ試し反映して実測で確かめた。

## 10. 完了処理（9章の検証に合格し、人レビューを通過してから実施する）

Claude Code 本体が行う（反映後の `CLAUDE.md`「ドキュメント更新フロー」ステップ6 に従う）。

1. 本案件 `README.md` の `## ステータス` 節の本文を `Closed（2026-10-05 起票、{完了日} 完了）` に置き換え、`## 実施記録` に反映・検証・完了の記録を追記する
2. `docs/BACKLOG.md`: `## 案件一覧` の update-002 の行のステータスのセルを `Closed` にし、`## 完了日一覧` の表の末尾に `| update-002 | update | 開発テンプレート最新版の取り込み（2/2）: 開発フロー・Codex レビュー（Herdr 対話方式）・AGENTS.md・基準書の更新 | {完了日} |` を追加する
3. `docs/CHANGELOG.md`: `## リリース履歴` の直下（最初の日付見出しの前）に完了日の見出しと本案件の記録を追加する。完了日の見出しが既にあればその見出しの下の先頭に追加する。記録の文面:

   ```
   - **update-002**: 開発テンプレート最新版の取り込み（2/2）（{完了日}完了、`CLAUDE.md` の開発フロー・運用ルールをテンプレート〔DEV_TEMPLATE `ffd2c49`〕に更新: 機能追加フローのロードマップ・マイルストーン化、ドキュメント更新フロー・実験プロトコルの導入、Codex レビューを Herdr 対話方式〔1回ゲート型〕へ移行、実装の Sonnet 委任・git 操作の Opus 委任、行き詰まり検出。`AGENTS.md`・`docs/HERDR_SETUP.md`・`docs/codex-exec-ubuntu24-bwrap-fix.md` を導入し、`docs/BUGFIX_STANDARD.md`・`docs/DESIGN_STANDARD.md`・`docs/REVIEW_CRITERIA.md` を更新。自動テストの置き場を `tests/scripts/` に定めた。Codex レビュー {回数}回で高・中ゼロに収束）
   ```

4. `docs/PROJECT_KNOWLEDGE.md` のディレクトリ構成（ファイルの追加の反映。同ファイル「本ファイルの扱い」に従い、追記した行の注記に出所の案件 ID を付す）:
   - `├── CLAUDE.md               # 開発フロー・運用ルール（統治）` の行の直後に `├── AGENTS.md               # Codex が起動時に読む指示ファイル（レビュー定型指示と CLAUDE.md の規定への適合確認。update-002）` を挿入する
   - `│   ├── TECH_STACK.md` の行の直後に、`│   ├── HERDR_SETUP.md        # Herdr によるエージェント連携のセットアップ手順（update-002）` と `│   ├── codex-exec-ubuntu24-bwrap-fix.md  # Ubuntu 24 系での codex の bwrap エラー対策（update-002）` の2行をこの順で挿入する
5. Codex のレビューストリーム `rev-vitpose-update-002` に `/quit` を送って終了し、ペインを撤去する（`AGENTS.md` は codex の起動時にのみ読まれるため、次の案件のレビューは新しく起動したストリームで行う。その最初のレビューで「[AGENTS.md適用]」マーカーが依頼文の代替なしに出ることを確認する）
6. git 操作（コミット・push）はユーザーの指示を受けてから Opus サブエージェントに委任する。コミットに含めるのは2章の8ファイル・本案件フォルダ配下・完了処理で変更したファイル。`.claude/settings.local.json`・`.claude/handovers/`・`scripts/conf/` の未追跡 JSON は含めない

完了後の検討事項（本案件のスコープ外）: README C13（codex のダイアログ・容量エラーの扱い）と本書 S10（トレーラーのモデル名）を、テンプレート側の update 案件として還元するかをユーザーと検討する。

## 11. テスト

コード変更がないため、テスト（自動・手動とも）は不要。検証は9章の静的確認で行う。
