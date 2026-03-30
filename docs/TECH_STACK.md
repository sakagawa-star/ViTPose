# 技術スタック定義書

最終更新: 2026-03-30

---

## プロジェクト基盤

| 項目 | 値 | 根拠 |
|------|-----|------|
| 言語 | Python 3.8+ | MMPose 0.24.0 の対応範囲（setup.py: 3.5〜3.9）。実環境は3.10 |
| パッケージ管理 | pip | MMPose公式の推奨。setup.py + requirements/ で管理 |
| 対象OS | Ubuntu Linux | 開発環境 |
| GPU | NVIDIA GeForce RTX 5060 Ti (CUDA 13.0) | ViTPose++ Huge の推論に必要 |

---

## コア依存関係

| ライブラリ名 | バージョン要件 | 用途 | 備考 |
|-------------|--------------|------|------|
| mmcv | >= 1.3.8, <= 1.5.0 | OpenMMLab共通基盤（画像処理、モデル登録等） | `MMCV_WITH_OPS=1` でビルドが必要 |
| torch | >= 1.3 | テンソル演算、GPU推論 | 推奨: PyTorch 1.9.0+ |
| torchvision | — | 画像変換 | torch に合わせたバージョン |
| timm | == 0.4.9 | Vision Transformer実装 | **バージョン固定**（ViTPoseが依存） |
| einops | — | テンソル操作 | ViTPoseのMoE実装で使用 |

## トラッキング依存関係

| ライブラリ名 | バージョン | 用途 | 備考 |
|-------------|----------|------|------|
| boxmot | 16.0.11 | Deep OC-SORTによる人物トラッキング（Phase 5） | feat-019の調査結果に基づき採用。PyTorch 2.11.0互換、OpenMMLab依存なし、活発にメンテナンス。AGPL-3.0ライセンス |

## ランタイム依存関係

| ライブラリ名 | 用途 |
|-------------|------|
| numpy | 数値計算 |
| opencv-python | 画像・動画処理 |
| pillow | 画像変換 |
| scipy | 数値計算 |
| matplotlib | 可視化 |
| xtcocotools >= 1.8 | COCO形式データセット操作 |
| json_tricks | JSON入出力 |
| munkres | ハンガリアン法（マルチパーソン対応） |

---

## モデル

| モデル名 | 設定ディレクトリ | 用途 | 備考 |
|---------|----------------|------|------|
| ViTPose++ Huge | configs/body/.../coco/, aic/ 等 | ポーズ推定 | MoE (6 experts)。`tools/model_split.py` でデータセット別に分割可能 |

### チェックポイント

ViTPose++のチェックポイントはREADME.mdのOneDriveリンクからダウンロードする。

---

## セットアップ手順（README.mdより）

```bash
# 1. MMCV 1.3.9 インストール
git clone https://github.com/open-mmlab/mmcv.git
cd mmcv && git checkout v1.3.9
MMCV_WITH_OPS=1 pip install -e .

# 2. ViTPose インストール
cd ~/git/ViTPose
pip install -v -e .

# 3. 追加依存関係
pip install timm==0.4.9 einops
```

---

## 制約・禁止事項

### 技術上の必須条件

| 制約 | 内容 | 根拠 |
|------|------|------|
| NVIDIA GPU 必須 | ViTPose++ Huge の推論に必要 | モデルサイズ |
| mmcv バージョン厳守 | >= 1.3.8, <= 1.5.0 の範囲内 | MMPose 0.24.0 との互換性 |
| timm バージョン固定 | == 0.4.9 | ViTPoseバックボーンが依存 |

### 非要件（実装対象外）

- リアルタイム推論（バッチ処理のみ）
- モデルの学習・ファインチューニング（推論のみ）
- マルチGPU分散推論
