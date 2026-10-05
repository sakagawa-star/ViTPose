# TECH_STACK

最終更新: 2026-10-05（update-001 で実環境に合わせて全面更新）

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
