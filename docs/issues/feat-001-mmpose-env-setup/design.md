# 機能設計書: feat-001 MMPose環境構築・動作確認

## 1.1 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001 | 1.4.1 uv仮想環境の作成 |
| FR-002 | 1.4.2 コア依存関係のインストール |
| FR-003 | 1.4.3 デモスクリプトの動作確認 |

## 1.2 システム構成

本案件はコード実装ではなく環境構築のため、モジュール構成図は不要。
成果物はプロジェクトルートに以下のファイルが追加される:

```
ViTPose/
├── pyproject.toml          # uv プロジェクト設定（新規作成）
├── uv.lock                 # 依存関係ロック（自動生成）
├── .venv/                  # 仮想環境（gitignore対象）
└── .python-version         # Pythonバージョン固定（新規作成）
```

## 1.3 技術スタック

| 項目 | 値 | 選定理由 |
|------|-----|---------|
| Python | 3.10 | MMPose 0.24.0（setup.py: 3.5〜3.9表記だが実質3.10動作）。TECH_STACK.mdに「実環境は3.10」と記載済み |
| パッケージ管理 | uv >= 0.9（現行 0.9.30） | ユーザー指定 |
| PyTorch | 2.7.x + CUDA 12.6 | RTX 5060 Ti（Blackwell sm_120）対応に必要。PyTorch 2.6以降がBlackwell対応 |
| mmcv | 要調査（後述） | CUDA ops付きビルドの互換性調査が必要 |

## 1.3.1 pyproject.toml テンプレート

```toml
[project]
name = "vitpose"
version = "0.1.0"
requires-python = ">=3.10,<3.11"

[tool.uv]
# PyTorchはCUDA 12.6用インデックスから取得
[[tool.uv.index]]
url = "https://download.pytorch.org/whl/cu126"
name = "pytorch-cu126"
```

インストール時は `uv pip install` で個別にインストールする（mmcv-fullの互換性調査が必要なため、段階的にインストールする方針）。全てのインストールが完了し動作確認できた後、確定したバージョンを `pyproject.toml` の `[project.dependencies]` に記載し、`uv lock` で `uv.lock` を生成する。これにより環境の再現性を担保する。

## 1.4 各機能の詳細設計

### 1.4.1 uv仮想環境の作成（FR-001）

#### 処理手順

1. プロジェクトルートで `uv init --no-readme` を実行（既存プロジェクトに追加）
   - 既存の `setup.py` はMMPoseのeditable install用にそのまま残す
   - `pyproject.toml` はuv環境管理用に新規作成し、build-system設定は含めない（setup.pyに委譲）
2. `.python-version` に `3.10` を記載
3. `uv venv` で仮想環境を作成
4. `.gitignore` に `.venv/` を追記する（存在しない場合は新規作成）

#### 設計判断: Pythonバージョン

- **採用案**: Python 3.10
- **却下案**: Python 3.8（mmcv-fullのCUDA 12.6対応ビルドが存在しない可能性が高い）、Python 3.12（mmcv-full 1.x系との互換性が不明）
- **理由**: TECH_STACK.mdに「実環境は3.10」と記載済み。PyTorch 2.7のCUDA 12.6ビルドがPython 3.10をサポートしている

### 1.4.2 コア依存関係のインストール（FR-002）

#### インストール順序

依存関係の制約上、以下の順序でインストールする:

1. **PyTorch + torchvision**（CUDA 12.6対応版）
2. **mmcv**（CUDA ops付き）
3. **MMDetection**
4. **ViTPose（本リポジトリ）** — editable install
5. **timm == 0.4.9, einops**

#### 1. PyTorch インストール

```bash
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
```

#### 2. mmcv インストール — 互換性調査が必要

**既知の問題**: mmcv-full <= 1.5.0 は古いパッケージで、CUDA 12.6 / Blackwell GPU向けのプリビルドwheelが存在しない可能性が高い。

**調査・対応方針**（以下を上から順に試行する）:

- **方針A**: `mmcv-full==1.5.0` のプリビルドwheelが存在するか確認
  - `uv pip install mmcv-full==1.5.0 --dry-run` でCUDA 12.6 / Python 3.10向けwheelを検索
  - 存在すればそのままインストール

- **方針B**: openmim 経由でインストール
  - `uv pip install openmim && mim install mmcv-full==1.5.0`
  - openmimがCUDA 12.6向けの適切なwheelを自動選択する可能性がある

- **方針C**: mmcv-full をソースからビルド
  - `git clone https://github.com/open-mmlab/mmcv.git && git checkout v1.5.0`
  - `MMCV_WITH_OPS=1 uv pip install -e .`
  - CUDA 12.6でのビルドエラーが出た場合、パッチが必要か調査

- **方針D**: mmcv 2.x（mmcv >= 2.0）を使用する
  - MMPose 0.x との互換性に問題がある可能性が高い
  - APIの差異を調査し、必要最小限の修正で動作するか確認
  - **リスクが高いため、方針A〜Cが全て失敗した場合の最終手段**

**調査中に判明した事項は `docs/issues/feat-001-mmpose-env-setup/investigation.md` に記録する。**

#### 3. MMDetection インストール

まず `uv pip install mmdet==2.28.2` を試行する。失敗した場合は openmim 経由（`mim install mmdet==2.28.2`）で試す。バージョン 2.28.2 はMMPose 0.x + mmcv 1.x と互換性のある最終安定版。

#### 4. ViTPose editable install

```bash
cd /home/sakagawa/git/ViTPose
uv pip install -v -e .
```

#### 5. timm + einops

```bash
uv pip install timm==0.4.9 einops
```

#### エラーハンドリング

| エラー | 検出方法 | 対応 |
|--------|---------|------|
| mmcv-full のビルド失敗 | pip install 時のコンパイルエラー | 方針A→B→C→Dの順に試行。結果をinvestigation.mdに記録 |
| MMDetection のインストール失敗 | pip install 時のエラー | uv pip → openmim の順に試行 |
| PyTorchがCUDAを認識しない | `torch.cuda.is_available()` が False | PyTorchのCUDAバージョンとドライバの互換性を確認 |
| timm 0.4.9 と PyTorch 2.7 の非互換 | import時のエラー | エラー内容を確認し、パッチまたは代替バージョンを検討 |

### 1.4.3 デモスクリプトの動作確認（FR-003）

#### 処理手順

1. 出力ディレクトリを作成する
   ```bash
   mkdir -p output/feat-001
   ```

2. テスト動画の1フレーム目を画像として抽出する
   ```bash
   uv run python -c "
   import cv2
   cap = cv2.VideoCapture('/home/sakagawa/git/ViTPose_HuggingFace/input/cam05520129.mp4')
   ret, frame = cap.read()
   cv2.imwrite('output/feat-001/test_frame.jpg', frame)
   cap.release()
   "
   ```

3. MMDetection + MMPose のモデルでデモを実行する。使用するモデルとコマンド:
   - 人物検出: Faster R-CNN（R-50-FPN）
   - ポーズ推定: HRNet-W32（COCO 256x192）
   - チェックポイントはmim経由またはURLから事前にダウンロードする
   ```bash
   # チェックポイントのダウンロード（uv run経由でvenv内のmimを使用）
   mkdir -p checkpoints
   uv run mim download mmdet --config faster_rcnn_r50_fpn_1x_coco --dest checkpoints/
   uv run mim download mmpose --config hrnet_w32_coco_256x192 --dest checkpoints/

   # デモ実行
   uv run python demo/top_down_img_demo_with_mmdet.py \
       checkpoints/faster_rcnn_r50_fpn_1x_coco.py \
       checkpoints/faster_rcnn_r50_fpn_1x_coco_20200130-047c8118.pth \
       configs/body/2d_kpt_sview_rgb_img/topdown_heatmap/coco/hrnet_w32_coco_256x192.py \
       checkpoints/hrnet_w32_coco_256x192-c78dce93_20200708.pth \
       --img-root output/feat-001/ \
       --img test_frame.jpg \
       --out-img-root output/feat-001/
   ```
   注: チェックポイントの正確なファイル名は `mim download` の出力で確認する。上記のファイル名は暫定値であり、実際のファイル名に読み替える。

4. 出力画像 `output/feat-001/test_frame.jpg`（上書き）にキーポイントが描画されていることを確認

#### 設計判断: デモに使うモデル

- **採用案**: HRNet-W32（COCO 256x192）を第一候補とする。動作しない場合はMMPose付属の他の軽量モデルで代替する
- **却下案**: ViTPose++ Huge（チェックポイントDLはfeat-002のスコープ）
- **理由**: 環境が正しく構築されたことの確認が目的。大きなモデルは不要

#### 境界条件

- デモスクリプトが人物を検出できなかった場合: 出力画像にキーポイントが描画されないが、スクリプト自体がエラーなく完了すれば環境構築は成功と判断する

## 1.5 状態遷移

該当なし（バッチ処理のみ）

## 1.6 ファイル・ディレクトリ設計

| ファイル | 用途 | git管理 |
|---------|------|---------|
| `pyproject.toml` | uv プロジェクト設定・依存関係定義 | する |
| `uv.lock` | 依存関係ロック | する |
| `.python-version` | Pythonバージョン固定 | する |
| `.venv/` | 仮想環境 | しない（.gitignoreに追記） |
| `output/` | デモ出力ディレクトリ | しない（.gitignoreに追記） |
| `checkpoints/` | モデルチェックポイント | しない（.gitignoreに追記） |

.gitignoreに追記するエントリ:
```
.venv/
output/
checkpoints/
```

## 1.7 インターフェース定義

該当なし（環境構築のみ、コード実装なし）

## 1.8 ログ・デバッグ設計

- 各インストールステップの実行結果（成功/失敗）をターミナル出力で確認
- mmcv互換性調査の過程と結果は `investigation.md` に記録
