# 調査記録: feat-001 MMPose環境構築・動作確認

## イテレーション1: 初回環境構築（2026-03-27〜28）

### 設計書からの差分と対応

#### 1. PyTorch CUDA バージョン: cu126 → cu128

- **問題**: PyTorch 2.11.0+cu126 は sm_120（RTX 5060 Ti, Blackwell）をサポートしていない。サポートされるcompute capabilityは sm_50〜sm_90 のみ
- **エラー**: `CUDA error: no kernel image is available for execution on the device`
- **対応**: cu128 版に切り替え。`pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128`
- **結果**: PyTorch 2.11.0+cu128 で RTX 5060 Ti を正常に認識

#### 2. mmcv バージョン: 1.5.0 → 1.7.2

- **問題**: mmcv-full 1.5.0 のC++ソースが PyTorch 2.11 のヘッダ（Float8型等）と非互換でビルドエラー
- **試行経緯**:
  - 方針A（プリビルドwheel）: wheelは見つかるがCUDA ops（`_ext.so`）が含まれない
  - 方針A'（`--no-binary --no-cache`でソースビルド強制）: v1.5.0はPyTorch 2.11のC++ APIと非互換でコンパイルエラー
  - **解決**: mmcv-full 1.7.2（1.x系の最終版）をソースからビルド → 成功
- **ビルド方法**: `/tmp/mmcv` に v1.7.2 をgit clone し、`MMCV_WITH_OPS=1 FORCE_CUDA=1 python setup.py develop` でインストール
  - `pip install .` はwheel作成時にファイルパスエラーが出るため、`setup.py develop` を使用
- **結果**: mmcv 1.7.2, CUDA ops compiled with 12.6

#### 3. mmpose バージョンチェック緩和

- **問題**: `mmpose/__init__.py` の `mmcv_maximum_version = '1.5.0'` により mmcv 1.7.2 で AssertionError
- **対応**: `mmcv_maximum_version` を `'1.8.0'` に変更（mmcv 1.7.x は 1.5.0 と後方互換）
- **変更ファイル**: `mmpose/__init__.py` 20行目

#### 4. pyproject.toml の構成変更

- **問題**: `uv init --no-readme` が生成する `[project]` セクションが既存の `setup.py` と競合し、editable install 時に `AttributeError: 'NoneType' object has no attribute 'get'` エラー
- **対応**: `[project]` セクションを削除し、`[tool.uv]` セクションのみ保持。setup.py は MMPose の editable install 用にそのまま残す
- **依存関係の再現性**: pyproject.toml の `[project.dependencies]` による管理は断念。`uv pip freeze` で記録する方針に変更

#### 5. xtcocotools の numpy 非互換

- **問題**: PyTorch が numpy 2.x を要求するが、xtcocotools のプリビルドwheelは numpy 1.x 向けにビルドされており、`ValueError: numpy.dtype size changed` エラー
- **対応**: `pip install --force-reinstall --no-binary xtcocotools --no-build-isolation xtcocotools` で numpy 2.x 向けに再ビルド

#### 6. MMDetection バージョン

- **設計**: mmdet 2.28.2
- **結果**: 設計通り問題なくインストール

### 最終的な環境構成

| パッケージ | バージョン | 備考 |
|-----------|-----------|------|
| Python | 3.10.16 | uv でインストール |
| torch | 2.11.0+cu128 | Blackwell sm_120 対応 |
| torchvision | 0.26.0+cu128 | |
| mmcv-full | 1.7.2 | CUDA ops compiled with 12.6, setup.py develop |
| mmpose | 0.24.0 | editable install, mmcv上限チェック緩和済み |
| mmdet | 2.28.2 | |
| timm | 0.4.9 | |
| einops | 0.8.2 | |
| openmim | 0.3.9 | チェックポイントDL用 |

### デモ動作確認結果

- **検出器**: Faster R-CNN R50-FPN（checkpoints/faster_rcnn_r50_fpn_1x_coco_20200130-047c8118.pth）
- **ポーズ推定**: HRNet-W32 COCO 256x192（checkpoints/hrnet_w32_coco_256x192-c78dce93_20200708.pth）
- **入力**: テスト動画の1フレーム目（1920x1080）
- **結果**: 人物1名を検出し、COCO 17キーポイントが正しく描画された
