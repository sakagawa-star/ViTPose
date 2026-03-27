# 要求仕様書: feat-001 MMPose環境構築・動作確認

## 1.1 プロジェクト概要

- **何を作るか**: ViTPose++（MMPose版）を推論実行できるPython環境をuvで構築する
- **なぜ作るか**: 後続のfeat-002以降でViTPose++の推論を行うための前提環境が必要
- **誰が使うか**: 開発者（sakagawa）
- **どこで使うか**: Ubuntu Linux, NVIDIA GeForce RTX 5060 Ti (Blackwell, compute capability 12.0), CUDA 12.6

## 1.2 用語定義

| 用語 | 定義 |
|------|------|
| mmcv-full | OpenMMLab共通基盤ライブラリ（CUDA ops付きビルド版） |
| MMDetection | OpenMMLab物体検出ライブラリ。人物検出に使用 |
| uv | Pythonパッケージマネージャ。仮想環境の作成と依存関係管理に使用 |
| MoE | Mixture of Experts。ViTPose++のアーキテクチャ |

## 1.3 機能要求一覧

### FR-001: uv仮想環境の作成

- **機能名**: Python仮想環境の作成
- **概要**: uvを使い、ViTPose++の依存関係が動作するPythonバージョンの仮想環境を作成する
- **入力**: なし
- **出力**: プロジェクトルートに `.venv/` ディレクトリが作成される
- **受け入れ基準**: `uv run python --version` でPythonバージョンが表示される

### FR-002: コア依存関係のインストール

- **機能名**: PyTorch + mmcv + MMPose + MMDetection のインストール
- **概要**: ViTPose++推論に必要なコア依存関係をインストールする
- **入力**: なし
- **出力**: 以下のパッケージがインポート可能になる
  - `torch`（CUDA対応、RTX 5060 Ti sm_120で動作）
  - `mmcv`（CUDA ops付き、バージョン >= 1.3.8, <= 1.5.0 を目標。互換性調査の結果次第で変更可）
  - `mmpose`（本リポジトリ、editable install）
  - `mmdet`（人物検出用、バージョン >= 2.14.0, < 3.0.0）
  - `timm == 0.4.9`
  - `einops`
- **受け入れ基準**: 以下のPythonコードがエラーなく実行できる
  ```python
  import torch; print(torch.cuda.is_available())  # True
  import mmcv; print(mmcv.__version__)
  import mmpose; print(mmpose.__version__)
  import mmdet; print(mmdet.__version__)
  import timm; print(timm.__version__)  # 0.4.9
  ```

### FR-003: 既存デモスクリプトの動作確認

- **機能名**: MMPoseデモスクリプトの実行確認
- **概要**: MMPose付属のHRNet-W32モデルでデモスクリプトが動作することを確認する。HRNet-W32が動作しない場合はMMPose付属の他の軽量モデルで代替する。ViTPose++チェックポイントはfeat-002で扱うため、ここでは環境の動作確認のみ行う
- **入力**: テスト用動画 `/home/sakagawa/git/ViTPose_HuggingFace/input/cam05520129.mp4` の1フレーム目を画像として抽出したもの。動画ファイルが存在しない場合は、任意の人物が写った画像で代替する
- **出力**: ポーズ推定結果が描画された画像ファイル（`output/feat-001/test_frame_result.jpg`）
- **受け入れ基準**: デモスクリプトがエラーなく完了し、出力画像にキーポイントが描画されている

## 1.4 非機能要求

- **パフォーマンス**: 環境構築に要する時間に制約なし（初回のみの作業）
- **対応環境**: Ubuntu Linux, NVIDIA GeForce RTX 5060 Ti, CUDA 12.6
- **信頼性**: 環境が再現可能であること（pyproject.toml / uv.lock で固定）

## 1.5 制約条件

- **パッケージ管理**: uvを使用する（pipではなく）
- **GPU**: NVIDIA GeForce RTX 5060 Ti（Blackwell, compute capability 12.0, CUDA 12.6）
- **既知の互換性リスク**:
  - mmcv-full <= 1.5.0 はCUDA 12.6 / Blackwell GPUに対応していない可能性がある
  - 対応策の調査・検証が本案件のスコープに含まれる
  - mmcv 2.x は MMPose 1.x 用であり、本リポジトリ（MMPose 0.x）とは非互換
- **timm**: バージョン 0.4.9 に固定（ViTPoseバックボーンが依存）

## 1.6 優先順位

| ID | 優先度 | 理由 |
|----|--------|------|
| FR-001 | Must | 全ての後続作業の前提 |
| FR-002 | Must | 推論実行の前提 |
| FR-003 | Should | 環境の動作確認として有用だが、ViTPose++自体の確認はfeat-002以降 |
