# 要求仕様書: feat-002 MoEチェックポイントDL・分割

## 1. プロジェクト概要

- **何を作るか**: ViTPose++ Huge MoEモデルのチェックポイントをダウンロードし、データセットごとに分割する
- **なぜ作るか**: MoEモデルは全データセット分のエキスパートと複数デコーダヘッドを含む統合ファイルであり、個別データセットで推論するには `model_split.py` で分割が必要
- **誰が使うか**: 開発者（自分自身）。後続のfeat-003〜008で分割済みチェックポイントを使用する
- **どこで使うか**: ローカルGPU環境（RTX 5060 Ti, CUDA 12.8）

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| MoEモデル | Mixture of Experts。バックボーンの各Transformerブロックに複数のエキスパート（FFN分岐）を持つアーキテクチャ |
| model_split.py | MoEモデルを各データセット専用のチェックポイントに分割するスクリプト（`tools/model_split.py`） |
| チェックポイント | PyTorchの `state_dict` を含む `.pth` ファイル |
| associate_keypoint_heads | MoEモデル内の各データセット用デコーダヘッド（COCO以外のデータセット用） |

## 3. 機能要求一覧

### FR-001: MoEチェックポイントのダウンロード

- **機能名**: ViTPose++ Huge MoE チェックポイントのダウンロード
- **概要**: OneDriveからViTPose++ Huge MoEの統合チェックポイントをダウンロードする
- **入力**: OneDrive共有URL `https://1drv.ms/u/s!AimBgYV7JjTlgccoXv8rCUgVe7oD9Q?e=ZBw6gR`
- **出力**: `checkpoints/vitpose-h-multi-coco.pth`（ダウンロード後のファイル名が異なる場合はこの名前にリネームする）
- **受け入れ基準**:
  - `checkpoints/vitpose-h-multi-coco.pth` が存在する
  - ファイルサイズが1GB以上である（ViT-Hugeバックボーン + 6データセット分のMoEエキスパート + デコーダヘッドを含むため、最低でも1GB以上になる。実際のサイズはダウンロード後に確定する）
  - `torch.load()` でエラーなく読み込め、`state_dict` キーが存在する

### FR-002: MoEモデルの分割

- **機能名**: MoEモデルのデータセット別分割
- **概要**: `tools/model_split.py` を使用してMoEチェックポイントを6つのデータセット用に分割する
- **入力**: `checkpoints/vitpose-h-multi-coco.pth`（FR-001の出力）
- **出力**: 以下の6つの分割済みチェックポイントが `checkpoints/` に生成される
  - `coco.pth` — COCO 17キーポイント
  - `aic.pth` — AIC 14キーポイント
  - `mpii.pth` — MPII 16キーポイント
  - `ap10k.pth` — AP10K 17キーポイント
  - `apt36k.pth` — APT36K 17キーポイント
  - `wholebody.pth` — COCO-WholeBody 133キーポイント
- **受け入れ基準**:
  - 6つのファイルがすべて `checkpoints/` に生成されている
  - 各ファイルが `torch.load()` でエラーなく読み込める
  - AIC〜WholeBody（COCO以外の5ファイル）の `keypoint_head.final_layer.weight` の shape[0] が各データセットのキーポイント数と一致する:
    - aic: 14, mpii: 16, ap10k: 17, apt36k: 17, wholebody: 133
  - COCOについては `keypoint_head.final_layer.weight` が存在し、shape[0] が17であること（実測で確認済み。MoEモデルのCOCO用デコーダヘッドは元から17チャネル）
  - 分割後の各ファイルには `mlp.experts.*` キーが残存する（model_split.py 98行目のバグにより除去されない）。推論時には不要キーは無視されるため許容する

### FR-003: 分割結果の検証

- **機能名**: 分割済みチェックポイントの整合性検証
- **概要**: 分割結果が正しいことをプログラムで確認する
- **入力**: FR-002の出力ファイル6つ
- **出力**: 各ファイルのキーポイント数がコンソールに表示される
- **受け入れ基準**:
  - 全6ファイルの `keypoint_head.final_layer.weight` の shape[0] をコンソール出力で確認できる
  - AIC〜WholeBodyの5ファイルが期待キーポイント数と一致する
  - COCOは shape[0] が17であること

## 4. 非機能要求

- **ディスク容量**: MoEチェックポイント + 分割後6ファイルで最低15GBの空きディスク容量が必要
- **処理時間**: 分割処理はCPUで完結し、10分以内に完了する
- **信頼性**: ダウンロードまたは分割処理が中断された場合、中間状態のファイルを手動で削除し、FR-001から再実行する

## 5. 制約条件

- OneDriveの共有リンクはCLIで直接ダウンロードできない可能性がある。ブラウザでの手動ダウンロードを許容する
- OneDriveの共有URLが無効になった場合は、ViTPose公式リポジトリ（ViTAE-Transformer/ViTPose）のREADMEからViTPose++ HugeモデルのOneDriveダウンロードリンクを再取得する
- `tools/model_split.py` は既存コードをそのまま使用する（コード変更しない）
- チェックポイントは `checkpoints/` ディレクトリに保存する（`.gitignore` に含まれている）

## 6. 優先順位

| ID | 優先度 | 備考 |
|----|--------|------|
| FR-001 | Must | 後続全案件の前提 |
| FR-002 | Must | 後続全案件の前提 |
| FR-003 | Must | 分割の正しさを確認するため必須 |

MVP: FR-001〜FR-003すべて
