# update-001 反映設計書: 開発テンプレート最新版の取り込み（1/2）— プロジェクト知識・完了履歴・技術スタック・BACKLOG の分離と整理

対象案件: `docs/issues/update-001-split-project-knowledge/`
調査記録: 同フォルダの `README.md`（候補 K1〜K5 の経緯と目的、本リポジトリの現状の実測）

本書は**自己完結**している。`/clear` 後でも本書だけで反映作業ができる。

## 1. 概要

`CLAUDE.md` から知識・記録・環境の記述を外へ移し、`CLAUDE.md` には統治（開発フロー等）と参照だけを残す。

| 変更 | 内容 | 章 |
|---|---|---|
| D1 | `docs/PROJECT_KNOWLEDGE.md` を新規作成し、`CLAUDE.md` の知識節を無改変で転記する | 4 |
| D2 | `docs/CHANGELOG.md` を新規作成し、`CLAUDE.md`「完了済み案件」の各項目を無改変で日付別に転記する | 5 |
| D3 | `docs/TECH_STACK.md` を実環境に合わせて全面的に書き直す | 6 |
| D4 | `CLAUDE.md` の知識節・技術スタック節・凍結中の案件節・完了済み案件節を置換・削除し、参照2種3箇所を付け替える | 7 |
| D5 | `docs/BACKLOG.md` にステータス凡例を新設し、節名・凡例外表記・完了日一覧の欠落を是正する | 8 |
| D6 | On Hold にする6案件の案件フォルダ README.md を更新または新規作成する | 9 |

- **変更方式**: 新規ファイル作成（`docs/PROJECT_KNOWLEDGE.md`・`docs/CHANGELOG.md`・案件 README 3件）、全面書き直し（`docs/TECH_STACK.md`）、見出しを目印にしたブロックの移動・置換と文字列置換（`CLAUDE.md`・`docs/BACKLOG.md`・案件 README 3件）。全置換に伴う後処理はない
- **実装者**: テンプレート `~/git/DEV_TEMPLATE/template/CLAUDE.md`「ドキュメント更新フロー」ステップ5 に従い、Sonnet サブエージェントが本書に厳密に従って反映する（本案件の進め方は `README.md`「本案件の進め方（ブートストラップ）」）
- **テスト**: コード変更がないため、自動テスト・手動テストとも不要。検証は 10章の静的確認で行う

### 設計の制約

1. **転記は無改変**: `CLAUDE.md` から `docs/PROJECT_KNOWLEDGE.md`・`docs/CHANGELOG.md` へ移す本文は1文字も変えない。例外は本書に「変更」として列挙した箇所（見出しレベル・見出し名・ディレクトリ構成ツリーの3行）のみ
2. **`CLAUDE.md` に知識の要約を残さない**（README K1 (d)）
3. **`CLAUDE.md` の統治部分（「開発方針」〜「コーディング規約」）は、7.4 の文字列置換3箇所以外を変更しない**
4. **行番号を目印にしない**: 本書の初版作成（2026-10-05）の後、feat-062 の完了処理（`6bab026`）と feat-061 の記録漏れの補完（`8623a99`）が `CLAUDE.md`・`docs/BACKLOG.md` を編集した。反映までの間にさらに編集される可能性もある。目印は見出し行・表の行の先頭（`| {ID} |`）とし、件数は 3章の事前確認で実測する
5. **自分で書く文にドメイン特定語を入れない**: 本書が定める新しい文面（見出し・注記・凡例・README 本文）は本書のとおりにし、言い換え・補足を加えない

## 2. 変更対象ファイル

| # | ファイル | 変更方式 | 章 |
|---|---|---|---|
| 1 | `docs/PROJECT_KNOWLEDGE.md` | 新規作成 | 4 |
| 2 | `docs/CHANGELOG.md` | 新規作成 | 5 |
| 3 | `docs/TECH_STACK.md` | 全面書き直し | 6 |
| 4 | `CLAUDE.md` | ブロック置換・削除、文字列置換 | 7 |
| 5 | `docs/BACKLOG.md` | 見出し置換、セル置換、行挿入、節追加 | 8 |
| 6 | `docs/issues/feat-026-occlusion-reid-verification/README.md` | 1行置換 | 9 |
| 7 | `docs/issues/feat-032-appearance-feature-verification/README.md` | 1行置換 | 9 |
| 8 | `docs/issues/feat-044-convert-pink-to-blue-video/README.md` | 1行置換 | 9 |
| 9 | `docs/issues/feat-027-deepocsort-halpe26-integration/README.md` | 新規作成（フォルダも新規） | 9 |
| 10 | `docs/issues/feat-030-target-id-identification/README.md` | 新規作成（フォルダも新規） | 9 |
| 11 | `docs/issues/feat-031-target-filtering/README.md` | 新規作成（フォルダも新規） | 9 |

完了処理（11章）で、本案件の `README.md`・`docs/BACKLOG.md`・`docs/CHANGELOG.md` を Claude Code 本体が更新する。上記以外のファイルは一切変更しない（`scripts/README.md`・ルート `README.md`・`docs/` 直下の基準書・他案件のフォルダ・`.gitignore` を含む）。

## 3. 事前確認（反映の開始前。1つでも満たさなければ反映せず中断して報告する）

作業ディレクトリは `/home/sakagawa/git/ViTPose`。

| # | 確認内容 | 方法 | 期待 |
|---|---|---|---|
| P1 | feat-062 が完了している | `grep -E '^\| feat-062 \| feat \|' docs/BACKLOG.md` | ステータスのセルが `Closed` で始まる |
| P2 | 作業ツリーに本案件以外の未コミット変更がない | `git status --short` | 本案件フォルダ配下と `docs/BACKLOG.md`（update-001 の行の追加のみ）以外に変更がない。`scripts/conf/` 配下の未追跡 JSON は無関係なので許容する |
| P3 | `CLAUDE.md` の見出し構成が想定どおり | `grep -n '^## ' CLAUDE.md` | 次の順で過不足なく並ぶ: `## セッション引き継ぎ`、`## プロジェクト概要`、`## 技術スタック`、`## テストデータ`、`## ディレクトリ構成（主要部分）`、`## ViTPose++ MoEモデルの仕組み`、`## 室内動画の特性（ドメイン知識）`、`## 開発方針`、`## コーディング規約`、`## 4ステージパイプライン（feat-034 ロードマップ、全ステージ完了）`、`## 凍結中の案件`、`## 完了済み案件`、`## 関連リポジトリ` |
| P4 | 「完了済み案件」の全項目が転記規則に合う | 5.2 の検査 | 全項目が `- **` で始まり、`（YYYY-MM-DD完了` を含む。件数を記録する（2026-10-05 の feat-062 完了処理後の再確認で 55件） |
| P5 | 文字列置換の旧文の出現回数 | 7.4 の表の各旧文を `grep -cF` | R1 = 1、R2 = 2 |
| P6 | `docs/BACKLOG.md` の目印 | `grep -c '^## Open$' docs/BACKLOG.md`、`grep -c '^## Closed$' docs/BACKLOG.md`、8.4 の目印行を `grep -cF`。8.3 の6行は、行の目印 `\| {ID} \| feat \|` で始まる行を `grep -cF` で数え、その行の末尾が8.3 の表の旧セルの中身に ` \|` を付けたもので終わることを確認する | 見出し2つ・8.4 の目印行・8.3 の各行の目印はいずれも 1。8.3 の各行の末尾は旧セルと一致する（旧セルの文自体は案件間で同一のものがあるため、ファイル全体での出現回数は数えない） |
| P7 | ライブラリのバージョン | `uv pip list`・`uv run python --version` | 6章「ライブラリ一覧」の全行のバージョンと、「実行環境」の Python 3.10.16 に一致する |
| P8 | 実行環境の情報 | 下表の4コマンド | 下表の期待値と一致する |

P8 のコマンドと期待値（2026-10-05 実測。6章「実行環境」の記載の典拠）:

| 項目 | コマンド | 期待値 | 6章で対応する記載 |
|---|---|---|---|
| OS | `lsb_release -ds` | `Ubuntu 24.04.3 LTS` | OS |
| GPU・ドライバ・compute capability | `nvidia-smi --query-gpu=name,driver_version,compute_cap --format=csv,noheader` | `NVIDIA GeForce RTX 5060 Ti, 580.95.05, 12.0` | GPU |
| PyTorch とそのビルドの CUDA | `uv run python -c "import torch;print(torch.__version__, torch.version.cuda)"` | `2.11.0+cu128 12.8` | CUDA（PyTorch は CUDA 12.8 ビルド） |
| mmcv-full と CUDA ops のコンパイル CUDA | `uv run python -c "import mmcv; from mmcv.ops import get_compiling_cuda_version; print(mmcv.__version__, get_compiling_cuda_version())"` | `1.7.2 12.6` | CUDA（mmcv-full の CUDA ops は CUDA 12.6 でコンパイル） |

P7・P8 で1つでも不一致があった場合は、反映を始めずに中断し、不一致の項目と実測値をユーザーに報告する。再開するには、Claude Code 本体が6章の該当値（および本表の期待値）を実測値に更新して本書を改版し、Codex の解消確認（B）で重要度「高・中」ゼロを確認してから反映をやり直す。

## 4. D1: `docs/PROJECT_KNOWLEDGE.md` の新規作成

### 4.1 移動元のブロック（`CLAUDE.md`）

ブロックは「開始の見出し行から、終了の見出し行の直前の行まで」とする。

| 記号 | 開始の見出し行（含む） | 終了の見出し行（含まない） | 中身 |
|---|---|---|---|
| B-data | `## テストデータ` | `## ディレクトリ構成（主要部分）` | テストデータの説明 |
| B-dir | `## ディレクトリ構成（主要部分）` | `## ViTPose++ MoEモデルの仕組み` | ディレクトリ構成ツリー |
| B-moe | `## ViTPose++ MoEモデルの仕組み` | `## 室内動画の特性（ドメイン知識）` | MoE の仕組み、`### AIC 14キーポイント定義`、`### HALPE 26キーポイント定義（ターゲット）` |
| B-video | `## 室内動画の特性（ドメイン知識）` | `## 開発方針` | 入力動画の特性 |
| B-pipe | `## 4ステージパイプライン（feat-034 ロードマップ、全ステージ完了）` | `## 凍結中の案件` | 4ステージパイプラインの構成 |
| B-repo | `## 関連リポジトリ` | ファイル末尾 | 関連リポジトリ |

各ブロックの**本文**とは、開始の見出し行を除いた残りの行から、先頭と末尾の空行を取り除いたものをいう。

### 4.2 作成するファイルの構成

次の順に連結してファイルを作る。各要素の間は空行1行で区切り、ファイル末尾は改行1つで終える。

1. 4.3 の冒頭部（固定文）
2. 見出し `## データ`、続けて B-data の本文
3. 見出し `## ディレクトリ構成（主要部分）`、続けて B-dir の本文に 4.4 の変更を加えたもの
4. 見出し `## ドメイン知識`
5. 見出し `### ViTPose++ MoEモデルの仕組み`、続けて B-moe の本文。ただし本文中の `### AIC 14キーポイント定義` を `#### AIC 14キーポイント定義` に、`### HALPE 26キーポイント定義（ターゲット）` を `#### HALPE 26キーポイント定義（ターゲット）` に変える（見出しレベルを1段下げる。文言は変えない）
6. 見出し `### 室内動画の特性`、続けて B-video の本文（見出し名から「（ドメイン知識）」を除くのは、親見出し `## ドメイン知識` と重複するため）
7. 見出し `### 4ステージパイプライン（feat-034 ロードマップ、全ステージ完了）`、続けて B-pipe の本文
8. 見出し `### 関連リポジトリ`、続けて B-repo の本文
9. 4.5 の末尾部（固定文）

コードブロック（バッククォート3個の囲み）の中身は本文の一部としてそのまま転記する。

### 4.3 冒頭部（固定文）

囲みの扱い: 次の開始行（バッククォート4個に markdown と付したもの）と閉じ行（バッククォート4個）は本書の囲みであり、ファイルには含めない。

````markdown
# PROJECT_KNOWLEDGE

本リポジトリ（ViTPose）の**プロジェクト知識**（データの所在と仕様・ディレクトリ構成・ドメイン知識）を集約したファイル。
開発フロー・レビュー手順・運用ルールなどの**統治**は `CLAUDE.md` にあり、本ファイルには含めない。

## 本ファイルの扱い

- **必読**: 実作業・案件の調査に入る前に本ファイルを全文読む（`CLAUDE.md`「プロジェクト知識」参照）
- **更新**: 各案件の完了処理で更新する（feat/bug: 案件で得た知見・データの状態・ファイルの追加削除の反映。update: ファイルの追加削除の反映）。更新内容は案件の設計書等に定義しレビューを通したものに限る。追記には出所の案件 ID を付す（例: 「（feat-016）」）
- **構成の変更**（分割・セクション再編）は update 案件で扱う
- **分割の目安**: **本ファイルが 500 行を超えたら分割を検討する。分割しない判断をしてもよいが、その判断と理由を記録する**（記録先は末尾の「分割検討の記録」）。行数は `wc -l docs/PROJECT_KNOWLEDGE.md` で確認する
````

「本ファイルの扱い」の4項目はテンプレート `template/docs/PROJECT_KNOWLEDGE.md` と同一の文面である（README K1 (d)）。変えたのは1行目の `{{プロジェクト名}}` を「本リポジトリ（ViTPose）」にした箇所のみ。

### 4.4 ディレクトリ構成ツリーの変更（3行）

B-dir の本文のコードブロック内で、次の変更だけを行う。

| # | 変更 | 変更前 | 変更後 |
|---|---|---|---|
| T1 | 置換 | `├── CLAUDE.md               # 本ファイル` | `├── CLAUDE.md               # 開発フロー・運用ルール（統治）` |
| T2 | 挿入（`│   ├── BACKLOG.md` の行の直前） | — | `│   ├── PROJECT_KNOWLEDGE.md  # 本ファイル（プロジェクト知識）` |
| T3 | 挿入（`│   ├── BACKLOG.md` の行の直後） | — | `│   ├── CHANGELOG.md          # 完了履歴` |

T1 の理由: 転記先では「本ファイル」が `docs/PROJECT_KNOWLEDGE.md` を指すため。T2・T3 は本案件で追加するファイル。

### 4.5 末尾部（固定文）

囲みの扱いは 4.3 と同じ。

````markdown
## 分割検討の記録

<!-- 500 行を超えた時点で行を追加する。記入例: | 2026-09-02 | 512 | 分割しない | セクション間の相互参照が多く、分割すると読む手数が増えるため | -->

| 日付 | 行数 | 判断 | 理由 |
|---|---|---|---|
````

## 5. D2: `docs/CHANGELOG.md` の新規作成

### 5.1 作成するファイルの構成

1. 次の冒頭部（固定文。囲みの扱いは 4.3 と同じ）

````markdown
# CHANGELOG

## リリース履歴

案件完了ごとに、日付見出しの下へ完了内容を記録する。新しい日付を上に置く。

update-001 より前に完了した案件の記録は、update-001 で `CLAUDE.md`「完了済み案件」節から移したものである。移動元に記述がなかった完了案件（bug-001・bug-002・bug-005）は記載していない。完了案件の一覧は `docs/BACKLOG.md` を参照する。
````

2. 続けて、5.2 の規則で並べた日付別の記録

### 5.2 日付別の記録の作り方

移動元は `CLAUDE.md` の `## 完了済み案件` の見出し行の次の行から `## 関連リポジトリ` の見出し行の直前の行まで（以下「C ブロック」）。

1. C ブロックの空でない各行を1項目とする。全項目が `- **` で始まることを確認する（そうでなければ中断）
2. 各項目の完了日を、項目内で最初に現れる `（YYYY-MM-DD完了` の `YYYY-MM-DD` とする（正規表現 `（(\d{4}-\d{2}-\d{2})完了`）。見つからない項目があれば中断する
3. 完了日の降順に日付見出し `### YYYY-MM-DD` を作り、その下に該当項目を置く。同じ日付の項目は C ブロックでの出現順を保つ
4. 項目の行は**無改変**で置く（行頭の `- ` を含め1文字も変えない）
5. 日付見出しの前後に空行1行を置く。日付見出しと最初の項目の間にも空行1行を置く。同じ日付の項目同士の間には空行を置かない

参考実装（この処理と同じ結果になれば、手段は問わない）:

```python
import re
from collections import OrderedDict

text = open("CLAUDE.md", encoding="utf-8").read()
start = text.index("\n## 完了済み案件\n") + len("\n## 完了済み案件\n")
end = text.index("\n## 関連リポジトリ\n")
items = [l for l in text[start:end].split("\n") if l.strip()]
assert all(l.startswith("- **") for l in items)
groups = OrderedDict()
for l in items:
    m = re.search(r"（(\d{4}-\d{2}-\d{2})完了", l)
    assert m is not None, l
    groups.setdefault(m.group(1), []).append(l)
parts = []
for d in sorted(groups, reverse=True):
    parts.append(f"### {d}\n\n" + "\n".join(groups[d]))
dated = "\n\n".join(parts) + "\n"
```

## 6. D3: `docs/TECH_STACK.md` の全面書き直し

既存の内容をすべて次の全文に置き換える。`{反映日}` は反映を行った日付（`YYYY-MM-DD`）に置き換える。囲みの扱いは 4.3 と同じ（内側のバッククォート3個の行はファイルに含める）。

````markdown
# TECH_STACK

最終更新: {反映日}（update-001 で実環境に合わせて全面更新）

## 実行環境

- **OS**: Ubuntu 24.04.3 LTS
- **言語**: Python 3.10.16（uv で導入）
- **パッケージ管理**: uv。PyTorch は `pyproject.toml` の `[tool.uv]` に定義した cu128 インデックスから取得する。MMPose 本体（本リポジトリ）は `setup.py` による editable install
- **GPU**: NVIDIA GeForce RTX 5060 Ti（Blackwell、compute capability 12.0、ドライバ 580.95.05）。ViTPose++ Huge の推論に必須
- **CUDA**: PyTorch は CUDA 12.8 ビルド（cu128）。mmcv-full の CUDA ops は CUDA 12.6 でコンパイルしている

## ライブラリ一覧

| ライブラリ | バージョン | 用途 | 選定理由 |
|---|---|---|---|
| torch | 2.11.0+cu128 | テンソル演算・GPU 推論 | cu126 版は sm_120（Blackwell）に対応しないため cu128 版を使う（feat-001） |
| torchvision | 0.26.0+cu128 | 画像変換 | torch に合わせる |
| mmcv-full | 1.7.2 | OpenMMLab 共通基盤（CUDA ops 付き） | 1.5.0 以下は PyTorch 2.11 の C++ API と非互換でビルドできないため、1.x 系の最終版を使う（feat-001）。mmcv 2.x は MMPose 1.x 用で本リポジトリ（MMPose 0.x）とは非互換 |
| mmpose | 0.24.0 | ViTPose++ 推論（本リポジトリ） | ViTPose 公式実装のベース |
| mmdet | 2.28.2 | 人物検出（Faster R-CNN 等） | MMPose 0.x + mmcv 1.x と互換の最終安定版（feat-001） |
| timm | 0.4.9 | Vision Transformer 実装 | ViTPose バックボーンが依存するためバージョン固定 |
| einops | 0.8.2 | テンソル操作 | ViTPose の MoE 実装で使用 |
| openmim | 0.3.9 | チェックポイントのダウンロード | OpenMMLab のモデル取得ツール（feat-001） |
| boxmot | 16.0.11 | Deep OC-SORT による人物トラッキング（Phase 5） | feat-019の調査結果に基づき採用。PyTorch 2.11.0互換、OpenMMLab依存なし、活発にメンテナンス。AGPL-3.0ライセンス |
| ultralytics | 8.4.33 | YOLO11x による人物検出（feat-024） | COCO val2017 mAP 54.7で最高精度クラス。Faster R-CNN/YOLOX-lで解消しないBB重複問題の検証用 |
| numpy | 2.2.6 | 数値計算 | MMPose の依存（`requirements/runtime.txt`）。torch が numpy 2.x を要求する |
| opencv-python | 4.13.0.92 | 画像・動画処理 | MMPose の依存（`requirements/runtime.txt`） |
| pillow | 12.2.0 | 画像変換 | MMPose の依存（`requirements/runtime.txt`） |
| scipy | 1.15.3 | 数値計算 | MMPose の依存（`requirements/runtime.txt`） |
| matplotlib | 3.10.9 | 可視化 | MMPose の依存（`requirements/runtime.txt`） |
| xtcocotools | 1.14.3 | COCO 形式データセット操作 | MMPose の依存（`requirements/runtime.txt`、>= 1.8）。numpy 2.x 向けにソースから再ビルドしている（feat-001） |
| json-tricks | 3.17.3 | JSON 入出力 | MMPose の依存（`requirements/runtime.txt`） |
| munkres | 1.1.4 | ハンガリアン法（マルチパーソン対応） | MMPose の依存（`requirements/runtime.txt`） |

運用ルール:

- ライブラリの追加・変更・削除を行ったら本表を更新する（`CLAUDE.md`「ドキュメント作成ルール」参照）
- 新規導入時は用途・選定理由・バージョンを必ず記入する
- バージョンは固定して記載する（未固定のまま残さない）

## モデル

| モデル名 | 設定ディレクトリ | 用途 | 備考 |
|---------|----------------|------|------|
| ViTPose++ Huge | configs/body/.../coco/, aic/ 等 | ポーズ推定 | MoE (6 experts)。`tools/model_split.py` でデータセット別に分割可能 |

### チェックポイント

ViTPose++のチェックポイントはREADME.mdのOneDriveリンクからダウンロードする。

## 環境構築手順

実際の構築手順と試行の経緯は `docs/issues/feat-001-mmpose-env-setup/investigation.md` に記録している。要点:

1. uv で Python 3.10.16 の仮想環境を作る
2. PyTorch を cu128 インデックスから入れる（cu126 版は RTX 5060 Ti で `no kernel image is available` になる）
3. mmcv-full 1.7.2 をソースからビルドする: v1.7.2 を git clone し、`MMCV_WITH_OPS=1 FORCE_CUDA=1 python setup.py develop`（`pip install .` は wheel 作成時にファイルパスエラーになる）
4. `mmpose/__init__.py` の `mmcv_maximum_version` を `'1.8.0'` に緩和する（mmcv 1.7.x は 1.5.0 と後方互換）
5. mmdet 2.28.2、本リポジトリ（editable install）、`timm==0.4.9`・einops を入れる
6. xtcocotools を numpy 2.x 向けに再ビルドする: `pip install --force-reinstall --no-binary xtcocotools --no-build-isolation xtcocotools`

## 制約・禁止事項

### 技術上の必須条件

| 制約 | 内容 | 根拠 |
|------|------|------|
| NVIDIA GPU 必須 | ViTPose++ Huge の推論に必要 | モデルサイズ |
| mmcv バージョン | mmcv-full 1.7.2（1.x 系）。`mmpose/__init__.py` の上限チェックを 1.8.0 に緩和済み。2.x は使わない | MMPose 0.24.0 との互換性（feat-001） |
| timm バージョン固定 | == 0.4.9 | ViTPoseバックボーンが依存 |

### 非要件（実装対象外）

- リアルタイム推論（バッチ処理のみ）
- モデルの学習・ファインチューニング（推論のみ）
- マルチGPU分散推論
````

**情報の対応（旧ファイルからの引き継ぎ）**: 旧 `docs/TECH_STACK.md` の各節は次のとおり新ファイルへ移る。

| 旧の節・項目 | 新での所在 | 扱い |
|---|---|---|
| プロジェクト基盤（言語・パッケージ管理・OS・GPU） | 実行環境 | 実測値に更新 |
| コア依存関係（mmcv・torch・torchvision・timm・einops） | ライブラリ一覧 | バージョンを実測値に更新。mmcv の「`MMCV_WITH_OPS=1` でビルドが必要」は環境構築手順3へ |
| トラッキング依存関係（boxmot・ultralytics） | ライブラリ一覧 | 用途・選定理由の文面は旧の「用途」「備考」を無改変で転記 |
| ランタイム依存関係（8件） | ライブラリ一覧 | 実測バージョンを追加 |
| モデル・チェックポイント | モデル | 無改変 |
| セットアップ手順（pip・mmcv 1.3.9） | 環境構築手順 | 実際の手順（feat-001 investigation.md）に置き換え |
| 制約・禁止事項（必須条件3件・非要件3件） | 制約・禁止事項 | mmcv の行のみ実環境に更新、他は無改変 |
| `CLAUDE.md` 技術スタック節の要約（mmdet・mmcv 上限緩和を含む） | 実行環境・ライブラリ一覧・環境構築手順4・制約 | すべて新ファイルに含まれる（7.1 で `CLAUDE.md` から削除するため） |

## 7. D4: `CLAUDE.md` の変更

7.1〜7.3 のブロック操作を先に行い、最後に 7.4 の文字列置換を行う。ブロックの定義は 4.1 と同じ（開始の見出し行を含み、終了の見出し行を含まない）。

### 7.1 技術スタック節の置換

`## 技術スタック` から `## テストデータ` の直前までのブロックを、次の全文に置き換える（ブロックの直後に空行1行を置いて `## テストデータ` が続く形を保つ。テストデータ節は 7.2 で置き換わる）。

```markdown
## 技術スタック

言語・パッケージ管理・ライブラリ一覧（バージョン・選定理由）・実行環境（GPU 等のハードウェア制約を含む）は `docs/TECH_STACK.md` を参照する。
```

この文はテンプレート `template/CLAUDE.md` の同節と同一の文面である（README K2 (c)）。

### 7.2 知識節の置換

`## テストデータ` から `## 開発方針` の直前までのブロック（B-data・B-dir・B-moe・B-video を合わせた範囲）を、次の全文に置き換える（ブロックの直後に空行1行を置いて `## 開発方針` が続く形を保つ）。

```markdown
## プロジェクト知識（データ・ディレクトリ構成・ドメイン知識）

データの所在と仕様、ディレクトリ構成、ドメイン知識（ViTPose++ MoE の構造・キーポイント定義・入力動画の特性・後処理パイプラインの構成・関連リポジトリ等）は **`docs/PROJECT_KNOWLEDGE.md`** に集約している。

- **必読**: 実作業・案件の調査に入る前に `docs/PROJECT_KNOWLEDGE.md` を全文読む（本ファイルには要約を置かない。知識は同ファイルのみで管理する）
- **更新の役割分担（非対称ルール）**:
  - `docs/PROJECT_KNOWLEDGE.md` の**内容**は、各案件の完了処理で更新する（feat/bug: 案件で得た知見・データの状態・ファイルの追加削除の反映。update: ファイルの追加削除の反映）。追記には出所の案件 ID を付す
  - `docs/PROJECT_KNOWLEDGE.md` の**構成**（分割・セクション再編）の変更は update 案件で扱う
  - **`CLAUDE.md`（本ファイル）の変更は update 案件でのみ行う。** feat/bug 案件の完了処理で本ファイルを更新することはない
- **暫定措置（update-002 の反映まで）**: 本ファイルには update 案件の手順（ドキュメント更新フロー）がまだない。update-002 の反映が完了するまで、update 案件は開発ドキュメントテンプレート `~/git/DEV_TEMPLATE/template/CLAUDE.md` の「ドキュメント更新フロー（update-XXX 案件）」に従う。本項目は update-002 で削除する
```

テンプレートとの差分は2点: (1) 括弧内のプレースホルダ `{{プロジェクト固有の知識の例を1〜2語で…}}` を本リポジトリの知識の例に置き換えた (2) 「暫定措置」の項目を追加した。「必読」「更新の役割分担」の3項目はテンプレートと同一の文面である（README K1 (d) の制約を保つ）。暫定措置を置く理由は README K1「本リポジトリ向けの読み替え」の3点目（「update 案件でのみ行う」の参照先が本リポジトリにない期間の扱い）。

### 7.3 末尾の節の置換・削除

`## 4ステージパイプライン（feat-034 ロードマップ、全ステージ完了）` からファイル末尾までのブロック（B-pipe・凍結中の案件・完了済み案件・B-repo を合わせた範囲）を、次の全文に置き換える。ファイルは改行1つで終える。

```markdown
## 完了済み案件

詳細は `docs/BACKLOG.md`（一覧）および `docs/CHANGELOG.md`（リリース履歴）を参照。
```

この2行はテンプレート `template/CLAUDE.md` の同節と同一の文面である（README K3 (d)）。置き換えで消える内容の行き先は次のとおり（情報の喪失がないことの対応表）。

| 消える節 | 行き先 |
|---|---|
| 4ステージパイプライン | `docs/PROJECT_KNOWLEDGE.md`「ドメイン知識」の同名の小節（4.2 の7） |
| 凍結中の案件（冒頭の段落と6項目） | `docs/BACKLOG.md` 案件一覧の6行のステータス（8.3）。冒頭の段落の内容（新トラッキング方式への移行が凍結の理由であること）は各行の理由に含まれる |
| 完了済み案件（全項目） | `docs/CHANGELOG.md`（5章） |
| 関連リポジトリ | `docs/PROJECT_KNOWLEDGE.md`「ドメイン知識」の同名の小節（4.2 の8） |

### 7.4 文字列置換（2種3箇所）

7.1〜7.3 の後に、次の順で適用する。各置換の前に旧文の出現回数が期待回数と一致することを検査し、一致しなければ中断して報告する。

| # | 対象 | 旧文 | 新文 | 期待回数 |
|---|---|---|---|---|
| R1 | 機能追加フロー ステップ6（実装時の必読） | `ドキュメント（要求仕様書・機能設計書・CLAUDE.md）を読んで実装する。` | ``ドキュメント（要求仕様書・機能設計書・CLAUDE.md・`docs/PROJECT_KNOWLEDGE.md`）を読んで実装する。`` | 1 |
| R2 | 機能追加・不具合修正フロー ステップ8（完了処理） | ``ファイルの追加・削除があった場合は `CLAUDE.md` のディレクトリ構成を最新に更新する`` | ```docs/CHANGELOG.md` に完了内容を記録する。`docs/PROJECT_KNOWLEDGE.md` を更新する（ファイルの追加・削除があった場合はディレクトリ構成を最新にし、案件で得た知見・データの状態の変化を該当セクションに追記する。追記には案件 ID を付す）。`CLAUDE.md` は更新しない（update 案件でのみ変更する）`` | 2 |

表のセル内のバッククォートの扱い: 旧文・新文は、セルの外側の囲み（バッククォート1個または2個とその内側の空白1個）を除いた中身である。正確な文字列は次の Python リテラルを正とする。

```python
REPLACEMENTS = [
    # (旧文, 新文, 期待回数)
    ("ドキュメント（要求仕様書・機能設計書・CLAUDE.md）を読んで実装する。",
     "ドキュメント（要求仕様書・機能設計書・CLAUDE.md・`docs/PROJECT_KNOWLEDGE.md`）を読んで実装する。", 1),
    ("ファイルの追加・削除があった場合は `CLAUDE.md` のディレクトリ構成を最新に更新する",
     "`docs/CHANGELOG.md` に完了内容を記録する。`docs/PROJECT_KNOWLEDGE.md` を更新する（ファイルの追加・削除があった場合はディレクトリ構成を最新にし、案件で得た知見・データの状態の変化を該当セクションに追記する。追記には案件 ID を付す）。`CLAUDE.md` は更新しない（update 案件でのみ変更する）", 2),
]
```

R2 の旧文はステップ8 の行末にあり、直前は「`docs/BACKLOG.md` のステータスを Closed に更新する。」である。置換後のステップ8 は「BACKLOG を Closed に更新 → CHANGELOG に記録 → PROJECT_KNOWLEDGE を更新 → CLAUDE.md は更新しない」の順になり、テンプレートのステップ8 の前半と同じ並びになる（テンプレートのステップ8 後半の README.md 更新義務は update-002 で扱う）。

### 7.5 変更しない箇所

7.1〜7.4 以外は変更しない。特に次は差分に現れてはならない: `# CLAUDE.md` の見出しと冒頭の1文、「セッション引き継ぎ」「プロジェクト概要」（目標・背景を含む）、「開発方針」から「コーディング規約」までの全行のうち R1・R2 の置換箇所以外。

### 7.6 変更後の見出し構成

変更後の `grep -n '^## ' CLAUDE.md` は次の順になる: `## セッション引き継ぎ`、`## プロジェクト概要`、`## 技術スタック`、`## プロジェクト知識（データ・ディレクトリ構成・ドメイン知識）`、`## 開発方針`、`## コーディング規約`、`## 完了済み案件`。

## 8. D5: `docs/BACKLOG.md` の変更

### 8.1 節名の変更（2箇所）

| # | 変更前（行全体） | 変更後（行全体） | 理由 |
|---|---|---|---|
| H1 | `## Open` | `## 案件一覧` | この節の表は全案件の一覧で、ステータス Closed の行が大半を占める。凡例のステータス名と同じ節名だと矛盾する |
| H2 | `## Closed` | `## 完了日一覧` | この節の表は完了案件の完了日の一覧。H1 と同じ理由 |

### 8.2 凡例外表記の扱い

- `Frozen（…）` の6行は 8.3 で On Hold に置き換える
- feat-062 は完了処理（`6bab026`）で既に Closed になっている（3章 P1 で確認する）ため、本案件では変更しない
- `Closed (効果なし、コード戻し)`（feat-015）・`Open（要件再ヒアリング中、…）`（feat-049）は凡例のステータス名に注記を付けた形であり、変更しない

### 8.3 Frozen → On Hold（6セル）

`## 案件一覧` の表で、次の各行のステータスのセル（最後のセル）の中身を置き換える。行の目印は先頭の `| {ID} | feat |`。凍結日の典拠は README K4「本リポジトリの現状」。理由は `CLAUDE.md`「凍結中の案件」の各項目と旧セルの文を合わせたもの、再開点は旧セル・同項目・案件 README に記録されたものに限る（記録がないものは「記録なし」と書く）。

| ID | 旧セルの中身 | 新セルの中身 |
|---|---|---|
| feat-044 | `Frozen（HSV 単独では服と肌が分離不可と判明、独自実装中断。既存ツール活用へ方針転換）` | `On Hold（2026-04-30 凍結。理由: HSV 分析でピンク服と肌が HSV 空間で本質的に重なる（H 円環距離 31、重なり率 46%）と確定。独自実装で空間制約（胴体内接矩形限定）を入れる方向で進められたが、ユーザー判断により既存ツール（ffmpeg / DaVinci Resolve / G'MIC 等）の活用へ方針転換し、独自実装は中断。再開点: 既存ツールでの代替実装が困難と判明し、独自実装を再検討する場合）` |
| feat-032 | `Frozen（feat-034 への移行により当面再開予定なし）` | `On Hold（2026-04-15 凍結。理由: feat-033 で色ベース方式の優位性が確認され、custom_reid.py HSVヒストグラム経路の修正動機が薄れたため。feat-034 への移行により当面再開予定なし。再開点: 記録なし）` |
| feat-031 | `Frozen（feat-034 の ID 体系確定後に再設計）` | `On Hold（2026-04-15 凍結。理由: feat-030 の後続で、feat-030 と同じ理由。再開点: feat-034 の ID 体系確定後に再設計）` |
| feat-030 | `Frozen（feat-034 の ID 体系確定後に再設計）` | `On Hold（2026-04-15 凍結。理由: stable_id の最長出現を前提とするため。再開点: feat-034 の ID 体系確定後に再設計）` |
| feat-027 | `Frozen（feat-034 への移行により当面再開予定なし）` | `On Hold（2026-04-15 凍結。理由: 旧 custom_reid.py 経路を前提とするため。新方式が feat-034 で統合パイプライン化される。当面再開予定なし。再開点: 記録なし）` |
| feat-026 | `Frozen（feat-034 への移行により当面再開予定なし）` | `On Hold（2026-04-15 凍結。理由: stable_id 前提のため。feat-034 への移行により当面再開予定なし。再開点: feat-034 の ID 体系確定後に再評価）` |

旧セルの文は、feat-030 と feat-031、feat-026 と feat-027 でそれぞれ同一であるため、置換は「行の目印で行を特定してから、その行のセルを置き換える」こと（ファイル全体への文字列置換をしない）。

### 8.4 完了日一覧への欠落行の挿入（8行）

`## 完了日一覧` の表で、行 `| feat-040 | feat | pink_ratio 時系列可視化グラフ | 2026-04-29 |` の直後に、次の8行をこの順で挿入する。名称は `## 案件一覧` の表の同じ ID の Title セル、完了日は `CLAUDE.md`「完了済み案件」の各項目の完了日である（README K3「移動元の現状」）。並びは完了日の昇順、同日は ID の昇順。

```
| bug-003 | bug | visualize_patient_video.py の --draw-start/--draw-end が出力動画範囲を制限しない | 2026-04-30 |
| feat-041 | feat | postprocess_pink_id.py に選択スコア診断フィールド追加 | 2026-04-30 |
| feat-042 | feat | visualize_patient_video.py に pink 選択診断フィールド描画拡張 | 2026-04-30 |
| feat-046 | feat | postprocess_pink_id.py のキーポイントベース ROI 対応 | 2026-05-13 |
| feat-047 | feat | ROI モード比較・可視化ツール（compare_roi_modes.py + visualize_disagreement_frames.py） | 2026-05-13 |
| feat-050 | feat | postprocess_pink_id.py に --min-pink-ratio CLI 引数追加（MIN_PINK_RATIO ハードコードの外部化） | 2026-05-14 |
| feat-048 | feat | 不一致フレーム可視化の情報再設計（JSON 直読み + idx ラベル / ROI 矩形 / 胴体 4 点描画 + ROI 状態表示） | 2026-05-15 |
| feat-051 | feat | selection_score 範囲によるフレーム抽出 PNG ツール（閾値検討用） | 2026-05-15 |
```

### 8.5 ステータス凡例の新設

ファイル末尾に、空行1行を挟んで次の節を追加する（ファイルは改行1つで終える）。文面はテンプレート `template/docs/BACKLOG.md` の同節と同一である（README K4 (d)）。

```markdown
## ステータス凡例

- **Open**: 起票済み・未着手
- **In Progress**: 調査・実装中
- **Review**: レビュー中
- **On Hold**: 一時中止（凍結）。再開する場合も、そのまま中止する場合もある。On Hold にする際は、本表の備考に日付・理由・再開点を記録し、案件フォルダの README.md のステータスも On Hold に更新する（README.md が未作成の案件では、概要と現在のステータスを記した README.md を作成して記録する）
- **Closed**: 完了
- **Cancelled**: 取りやめ・破棄（ドキュメントは履歴として残す）
```

本リポジトリの案件一覧の表には「備考」列がなく、日付・理由・再開点はステータスのセルの括弧内に書いている（8.3）。凡例の「本表の備考に」は、本リポジトリではこのセルの括弧内を指す。凡例の文面はテンプレートと同一に保つため変更しない。

## 9. D6: On Hold にする案件の README.md

### 9.1 既存の README.md（3件、各1行置換）

| ファイル | 変更前（行全体） | 変更後（行全体） |
|---|---|---|
| `docs/issues/feat-026-occlusion-reid-verification/README.md` | `## ステータス: Open` | `## ステータス: On Hold（2026-04-15 凍結。理由・再開点は docs/BACKLOG.md の該当行を参照）` |
| `docs/issues/feat-032-appearance-feature-verification/README.md` | `Open（調査・設計フェーズ）` | `On Hold（2026-04-15 凍結。理由・再開点は docs/BACKLOG.md の該当行を参照）` |
| `docs/issues/feat-044-convert-pink-to-blue-video/README.md` | `Frozen（2026-04-30、ユーザー判断により凍結）。` | `On Hold（2026-04-30、ユーザー判断により凍結）。` |

各ファイルで変更前の行がちょうど1回現れることを確認してから置換する。feat-044 の README は理由・凍結時点の成果物・凍結解除条件を既に持つため、ステータス名だけを変える。

### 9.2 新規作成する README.md（3件）

feat-027・feat-030・feat-031 には案件フォルダがない（起票のみで着手前に凍結された）。凡例の On Hold の規定に従い、フォルダと README.md を作成する。フォルダ名は命名規則（英語）に従い本書で定める。

**`docs/issues/feat-027-deepocsort-halpe26-integration/README.md`**（囲みの扱いは 4.3 と同じ）:

````markdown
# feat-027: Deep OC-SORT + HALPE 26統合

## ステータス

On Hold（2026-04-15 凍結。理由・再開点は docs/BACKLOG.md の該当行を参照）

## 概要

パイプラインにDeep OC-SORTを統合する（docs/BACKLOG.md ロードマップ Phase 5 の記載）。

着手前に凍結したため、本 README 以外の案件文書はない。本 README は update-001 で BACKLOG のステータス凡例（On Hold）に従って作成した。
````

**`docs/issues/feat-030-target-id-identification/README.md`**:

````markdown
# feat-030: 対象ID特定スクリプト

## ステータス

On Hold（2026-04-15 凍結。理由・再開点は docs/BACKLOG.md の該当行を参照）

## 概要

最長出現IDを対象として特定する（docs/BACKLOG.md ロードマップ Phase 5 の記載）。

着手前に凍結したため、本 README 以外の案件文書はない。本 README は update-001 で BACKLOG のステータス凡例（On Hold）に従って作成した。
````

**`docs/issues/feat-031-target-filtering/README.md`**:

````markdown
# feat-031: 対象フィルタリング

## ステータス

On Hold（2026-04-15 凍結。理由・再開点は docs/BACKLOG.md の該当行を参照）

## 概要

指定IDのキーポイントのみ抽出する（docs/BACKLOG.md ロードマップ Phase 5 の記載）。

着手前に凍結したため、本 README 以外の案件文書はない。本 README は update-001 で BACKLOG のステータス凡例（On Hold）に従って作成した。
````

各 README の名称と概要は `docs/BACKLOG.md` ロードマップ Phase 5 の表の Title・概要セル（凍結注記の括弧を除く）を基にした。

## 10. 反映直後の検証（完了処理の前）

すべて静的確認。1つでも満たさなければ反映をやり直す。作業ディレクトリは `/home/sakagawa/git/ViTPose`。件数の期待値のうち `N` は 3章 P4 で実測した「完了済み案件」の項目数。

| # | 確認内容 | 方法 | 期待 |
|---|---|---|---|
| V1 | 変更ファイル | `git status --short` | 2章の11ファイル（新規5・変更6）と本案件フォルダ配下のみ（`scripts/conf/` の未追跡 JSON は除く） |
| V2 | `CLAUDE.md` の見出し構成 | `grep -n '^## ' CLAUDE.md` | 7.6 のとおり |
| V3 | 知識の転記が無改変 | 下記スクリプト1 | 出力 `OK` |
| V4 | 完了履歴の転記が無改変・全件 | 下記スクリプト2 | 出力 `OK N`（N は P4 の件数） |
| V5 | `CLAUDE.md` に知識・履歴が残っていない | `grep -c -E '^## (テストデータ\|ディレクトリ構成\|ViTPose\+\+ MoE\|室内動画\|4ステージ\|凍結中\|関連リポジトリ)' CLAUDE.md`、`grep -c '^- \*\*feat-001\*\*' CLAUDE.md` | どちらも `0` |
| V6 | 参照の付け替え | `grep -c 'PROJECT_KNOWLEDGE' CLAUDE.md` | `7`（7.2 の節に4行、R1 に1行、R2 に2行） |
| V7 | 冒頭部と統治部分の非変更 | 下記スクリプト3 | 出力 `OK` |
| V8 | TECH_STACK の全文 | 目視 | 6章の全文と一致（`{反映日}` のみ置換済み） |
| V9 | BACKLOG の凡例外表記の解消 | `grep -c 'Frozen' docs/BACKLOG.md`、`grep -c '^## ステータス凡例$' docs/BACKLOG.md`、`grep -c '^## Open$\|^## Closed$' docs/BACKLOG.md` | `0`、`1`、`0` |
| V10 | On Hold の行 | `grep -c '| On Hold（' docs/BACKLOG.md` | `6` |
| V11 | 完了日一覧の補完 | `sed -n '/^## 完了日一覧/,$p' docs/BACKLOG.md \| grep -cE '^\| (bug-003\|feat-041\|feat-042\|feat-046\|feat-047\|feat-048\|feat-050\|feat-051) '` | `8` |
| V12 | 案件 README | `grep -l 'On Hold' docs/issues/feat-0{26,27,30,31,32,44}-*/README.md \| wc -l` | `6` |
| V13 | PROJECT_KNOWLEDGE の行数 | `wc -l docs/PROJECT_KNOWLEDGE.md` | 500 未満（分割検討は不要） |

スクリプト1（V3。`git show HEAD:CLAUDE.md` を移動前の正とし、4.2 の規則で期待される本文を組み立てて比較する）:

```python
import subprocess

old = subprocess.run(["git", "show", "HEAD:CLAUDE.md"], capture_output=True, text=True, check=True).stdout
new = open("docs/PROJECT_KNOWLEDGE.md", encoding="utf-8").read()

def block_body(text, start, end):
    s = text.index("\n" + start + "\n") + len("\n" + start + "\n")
    e = text.index("\n" + end + "\n", s) if end else len(text)
    return text[s:e].strip("\n")

checks = [
    ("## テストデータ", "## ディレクトリ構成（主要部分）", lambda b: b),
    ("## ディレクトリ構成（主要部分）", "## ViTPose++ MoEモデルの仕組み",
     lambda b: b.replace("├── CLAUDE.md               # 本ファイル", "├── CLAUDE.md               # 開発フロー・運用ルール（統治）")
                .replace("│   ├── BACKLOG.md\n", "│   ├── PROJECT_KNOWLEDGE.md  # 本ファイル（プロジェクト知識）\n│   ├── BACKLOG.md\n│   ├── CHANGELOG.md          # 完了履歴\n")),
    ("## ViTPose++ MoEモデルの仕組み", "## 室内動画の特性（ドメイン知識）",
     lambda b: b.replace("### AIC 14キーポイント定義", "#### AIC 14キーポイント定義")
                .replace("### HALPE 26キーポイント定義（ターゲット）", "#### HALPE 26キーポイント定義（ターゲット）")),
    ("## 室内動画の特性（ドメイン知識）", "## 開発方針", lambda b: b),
    ("## 4ステージパイプライン（feat-034 ロードマップ、全ステージ完了）", "## 凍結中の案件", lambda b: b),
    ("## 関連リポジトリ", None, lambda b: b),
]
for start, end, f in checks:
    expected = f(block_body(old, start, end))
    assert expected in new, start
print("OK")
```

スクリプト2（V4）:

```python
import re, subprocess

old = subprocess.run(["git", "show", "HEAD:CLAUDE.md"], capture_output=True, text=True, check=True).stdout
s = old.index("\n## 完了済み案件\n") + len("\n## 完了済み案件\n")
e = old.index("\n## 関連リポジトリ\n")
items = [l for l in old[s:e].split("\n") if l.strip()]
log = open("docs/CHANGELOG.md", encoding="utf-8").read().split("\n")
date = None
pos = {}
for i, l in enumerate(log):
    m = re.fullmatch(r"### (\d{4}-\d{2}-\d{2})", l)
    if m:
        date = m.group(1)
    elif l.startswith("- **"):
        pos[l] = (date, i)
for l in items:
    assert l in pos, l[:40]
    assert pos[l][0] == re.search(r"（(\d{4}-\d{2}-\d{2})完了", l).group(1), l[:40]
dates = [re.fullmatch(r"### (\d{4}-\d{2}-\d{2})", l).group(1) for l in log if re.fullmatch(r"### \d{4}-\d{2}-\d{2}", l)]
assert dates == sorted(dates, reverse=True) and len(dates) == len(set(dates))
print("OK", len(items))
```

スクリプト3（V7。`## 技術スタック` より前の冒頭部が完全に一致し、`## 開発方針` から統治部分の末尾までが R1・R2 の置換を除いて完全に一致することを確かめる）:

```python
import subprocess

old = subprocess.run(["git", "show", "HEAD:CLAUDE.md"], capture_output=True, text=True, check=True).stdout
new = open("CLAUDE.md", encoding="utf-8").read()
REPLACEMENTS = [
    ("ドキュメント（要求仕様書・機能設計書・CLAUDE.md）を読んで実装する。",
     "ドキュメント（要求仕様書・機能設計書・CLAUDE.md・`docs/PROJECT_KNOWLEDGE.md`）を読んで実装する。"),
    ("ファイルの追加・削除があった場合は `CLAUDE.md` のディレクトリ構成を最新に更新する",
     "`docs/CHANGELOG.md` に完了内容を記録する。`docs/PROJECT_KNOWLEDGE.md` を更新する（ファイルの追加・削除があった場合はディレクトリ構成を最新にし、案件で得た知見・データの状態の変化を該当セクションに追記する。追記には案件 ID を付す）。`CLAUDE.md` は更新しない（update 案件でのみ変更する）"),
]
head_old = old[:old.index("\n## 技術スタック\n")]
head_new = new[:new.index("\n## 技術スタック\n")]
assert head_old == head_new, "head"
gov_old = old[old.index("\n## 開発方針\n"):old.index("\n## 4ステージパイプライン（feat-034 ロードマップ、全ステージ完了）\n")]
gov_new = new[new.index("\n## 開発方針\n"):new.index("\n## 完了済み案件\n")]
for a, b in REPLACEMENTS:
    gov_old = gov_old.replace(a, b)
assert gov_old == gov_new, "governance"
print("OK")
```

スクリプト1〜3 は `uv run python` で実行する。反映のコミット前（`HEAD:CLAUDE.md` が移動前の版）に実行すること。

本章の期待値（V2〜V7・V9〜V13 とスクリプト1〜3）は、設計時（2026-10-05）に本書の手順を作業用の写しへ試し反映して実測で確かめた（初版は「完了済み案件」53件の時点、改版1 で feat-062 完了処理後の55件の状態に対して再実施。V4 の件数は反映時の P4 の実測値に読み替える）。

## 11. 完了処理（10章の検証に合格し、人レビューを通過してから実施する）

Claude Code 本体が行う。

1. 本案件 `README.md` の `## ステータス` 節の本文を `Closed（2026-10-05 起票、{完了日} 完了）` に置き換え、`## 実施記録` に反映・検証・完了の記録を追記する
2. `docs/BACKLOG.md` の `## 案件一覧` の update-001 の行のステータスのセルを `Closed` にし、`## 完了日一覧` の表の末尾に `| update-001 | update | 開発テンプレート最新版の取り込み（1/2）: プロジェクト知識・完了履歴・技術スタック・BACKLOG の分離と整理 | {完了日} |` を追加する
3. `docs/CHANGELOG.md` の `## リリース履歴` の直下（最初の日付見出しの前）に、完了日の見出しと本案件の記録を追加する。完了日の見出しが既にあればその見出しの下の先頭に追加する。記録の文面:

   ```
   - **update-001**: 開発テンプレート最新版の取り込み（1/2）（{完了日}完了、`docs/PROJECT_KNOWLEDGE.md` と `docs/CHANGELOG.md` を新設し、`CLAUDE.md` の知識節・完了済み案件節をそれぞれへ無改変で転記。`docs/TECH_STACK.md` を実環境に合わせて全面更新し、`CLAUDE.md` の技術スタック節をポインタ化。`docs/BACKLOG.md` にステータス凡例を導入し、凍結6案件を On Hold に統一、完了日一覧の欠落8行を補完。Codex レビュー {回数}回で高・中ゼロに収束）
   ```

4. `docs/PROJECT_KNOWLEDGE.md` のディレクトリ構成: 本案件で追加したファイル（`docs/PROJECT_KNOWLEDGE.md`・`docs/CHANGELOG.md`）は 4.4 で反映済み。案件フォルダ（`docs/issues/` 配下）はツリーに個別に載せていないため追加しない
5. Codex のレビューストリーム `rev-vitpose-update-001` に `/quit` を送って終了し、ペインを撤去する
6. git 操作（コミット）は Opus サブエージェントに委任する。コミットに含めるのは2章の11ファイル・本案件フォルダ配下・完了処理で変更したファイル。`.claude/settings.local.json`・`.claude/handovers/`・`scripts/conf/` の未追跡 JSON は含めない

## 12. テスト

コード変更がないため、テスト（自動・手動とも）は不要。検証は10章の静的確認で行う。

## 改訂履歴

| 版 | 日付 | 内容 |
|---|---|---|
| 初版 | 2026-10-05 | 作成。codex-01（A）の中1に対応して 3章に P8 を追加。codex-03（C）で収束、人レビュー承認 |
| 改版1 | 2026-10-05 | 反映前の事前確認で前提の変化が判明したため改版（README「実施記録」参照）。(1) feat-062 の完了処理と feat-061 の記録漏れ補完により「完了済み案件」が55件になり feat-061 が移動元に含まれたため、5.1 の CHANGELOG 冒頭文の「移動元に記述がなかった完了案件」から feat-061 を除いた。P4 の件数の注記を55件に更新 (2) P6 の旧セルの確認方法を、行の目印で行を特定して末尾を照合する方法に改めた（旧セルの文が案件間で同一のため、ファイル全体での出現回数は 1 にならない） |
| 改版2 | 2026-10-05 | 改版1 のレビュー（codex-04、A）の中1に対応。feat-062 を「計画中・完了処理で Closed になる見込み」とする記述が残っていたため、8.2 と設計の制約4 を完了後の事実（Closed 済み・`6bab026`・`8623a99`）に更新した。README の K4 現状・実施の前提も同様に過去形へ統一した |
