# feat-020: BoxMOT環境構築 — 要求仕様書

## 1. 目的

BoxMOTパッケージを現環境にインストールし、Deep OC-SORTトラッカーがインポート・初期化できる状態にする。

- **何を作るか**: BoxMOTパッケージのインストールと動作確認
- **なぜ作るか**: feat-019で採用決定したDeep OC-SORTトラッカーの実行基盤を準備する
- **誰が使うか**: 開発者（ポーズ推定パイプラインの拡張）
- **どこで使うか**: ViTPoseリポジトリの既存Python環境（uv管理）

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| BoxMOT | 複数のSOTAマルチオブジェクトトラッキングアルゴリズムをプラグイン形式で利用できるPythonパッケージ（PyPI: boxmot） |
| Deep OC-SORT | OC-SORTにRe-IDを適応的に統合したトラッキング手法。BoxMOTのクラス名は `DeepOcSort` |
| Re-ID | Re-Identification（再同定）。見た目の特徴量で同一人物を識別する技術 |
| OSNet | Omni-Scale Network。Re-ID用の軽量CNN（2.2Mパラメータ）。BoxMOTのデフォルトRe-IDモデル |

## 3. 機能要件

### FR-1: BoxMOTのインストール [Must]

- `uv pip install boxmot==16.0.11` でBoxMOTをインストールする
- 既存パッケージ（torch, torchvision, mmcv-full, mmdet, mmpose, numpy, opencv-python）のバージョンがインストール前後で変わらないこと
- **受け入れ基準**: インストールコマンドが正常終了し、`uv pip list` の差分が新規追加のみであること

### FR-2: インポート確認 [Must]

- `from boxmot import DeepOcSort` が正常にインポートできることを確認する
- **受け入れ基準**: 上記のimport文がImportErrorなく完了すること

### FR-3: トラッカー初期化確認 [Must]

- `DeepOcSort(reid_weights=Path('osnet_x0_25_msmt17.pt'), device='cuda:0', half=True)` でインスタンスが生成できることを確認する
- Re-IDモデル（OSNet, osnet_x0_25_msmt17.pt, 約3MB）が初回実行時にGoogle Driveから自動ダウンロードされることを確認する
- **受け入れ基準**: インスタンス生成が成功し、Re-IDモデルファイルがダウンロードされること

### 優先順位

全機能要件（FR-1〜FR-3）が Must。MVP = 全3要件の達成。

## 4. 非機能要件

- 既存のViTPoseパイプライン（`scripts/run_halpe26_pipeline.py`）が引き続き正常に動作すること
- インストールによって既存パッケージのバージョンが変更されないこと

## 5. 制約条件

- パッケージ管理は `uv` を使用すること（`pip` 直接実行は不可）
- Re-IDモデルの初回ダウンロードにインターネット接続が必要

## 6. スコープ外

- トラッキングの実行テスト（feat-021で実施）
- パイプラインへの統合（feat-024で実施）

## 7. 現環境

| パッケージ | バージョン |
|-----------|----------|
| Python | 3.10.16 |
| torch | 2.11.0+cu128 |
| torchvision | 0.26.0+cu128 |
| mmcv-full | 1.7.2 |
| mmdet | 2.28.2 |
| mmpose | 0.24.0 |
| numpy | 2.2.6 |
| opencv-python | 4.13.0.92 |
| パッケージ管理 | uv |

## 8. 受け入れ基準

1. `uv pip install boxmot==16.0.11` が正常に完了する
2. `from boxmot import DeepOcSort` がエラーなくインポートできる
3. `DeepOcSort(reid_weights=..., device='cuda:0', half=True)` のインスタンス生成が成功する
4. 既存パッケージのバージョンが変更されていない（特にtorch, mmcv-full, mmdet, mmpose）
5. `docs/TECH_STACK.md` にboxmotの情報が追記されている
