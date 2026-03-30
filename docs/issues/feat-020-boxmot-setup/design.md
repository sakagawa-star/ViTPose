# feat-020: BoxMOT環境構築 — 機能設計書

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|--------------|
| FR-1 | 手順1〜3（インストールと差分確認） |
| FR-2 | 手順4（インポート確認） |
| FR-3 | 手順5（トラッカー初期化確認） |
| — | 手順6（.gitignore追記） |
| — | 手順7（TECH_STACK.md更新） |

## 2. 概要

BoxMOTパッケージのインストールと動作確認。コード変更は不要で、パッケージインストールとドキュメント更新のみ。

## 3. 実装手順

### 手順1: インストール前のパッケージ状態記録

```bash
uv pip list > /tmp/before_boxmot.txt
```

### 手順2: BoxMOTインストール

```bash
uv pip install boxmot==16.0.11
```

**エラー時の対処**: 依存関係の競合でインストールが失敗した場合、エラーメッセージから競合パッケージを特定し、ユーザーに報告する。既存パッケージのバージョン変更による解決は行わない。

### 手順3: インストール後のパッケージ差分確認

```bash
uv pip list > /tmp/after_boxmot.txt
diff /tmp/before_boxmot.txt /tmp/after_boxmot.txt
```

確認事項:
- torch, torchvision, mmcv-full, mmdet, mmpose のバージョンが変わっていないこと

**判定基準**: 差分に既存パッケージのバージョン変更が含まれていなければ合格。新規追加パッケージのみであれば問題なし。

**ロールバック手順**（既存パッケージに影響があった場合）:
```bash
uv pip uninstall boxmot
# 要求仕様書セクション7「現環境」テーブルのバージョンに戻す
# 例:
# uv pip install torch==2.11.0+cu128
# uv pip install mmcv-full==1.7.2
```

### 手順4: インポート確認

```bash
uv run python -c "from boxmot import DeepOcSort; print('Import OK')"
```

注意: クラス名は `DeepOcSort`（キャメルケース）。調査時のWeb情報では `DeepOCSORT` と記載されていたが、v16.0.11の実際のAPIは `DeepOcSort`。

**エラー時の対処**: ImportErrorが発生した場合、`uv pip show boxmot` でインストール状態を確認する。パッケージが正しくインストールされていなければ手順2からやり直す。

### 手順5: トラッカー初期化確認

プロジェクトルート（`/home/sakagawa/git/ViTPose/`）で実行する。

```bash
uv run python -c "
from boxmot import DeepOcSort
from pathlib import Path
tracker = DeepOcSort(
    reid_weights=Path('osnet_x0_25_msmt17.pt'),
    device='cuda:0',
    half=True,
)
print(f'Tracker initialized: {type(tracker).__name__}')
"
```

Re-IDモデル（OSNet, 約3MB）が初回実行時にGoogle Driveから自動ダウンロードされる。ダウンロード先はカレントディレクトリ（プロジェクトルート: `/home/sakagawa/git/ViTPose/osnet_x0_25_msmt17.pt`）。

**エラー時の対処**:
- CUDAエラー（GPU利用不可）の場合: `device='cpu'` で再試行する
- ダウンロード失敗の場合: ネットワーク接続を確認し再実行する

### 手順6: .gitignoreへの追記

Re-IDモデルファイルがプロジェクトルートにダウンロードされるため、`.gitignore` に以下を追記する:

```
osnet_x0_25_msmt17.pt
```

### 手順7: ドキュメント更新

`docs/TECH_STACK.md` に以下を追記する:

- パッケージ名: boxmot
- バージョン: 16.0.11
- 用途: Deep OC-SORTによる人物トラッキング（Phase 5）
- 選定理由: feat-019の調査結果に基づく。PyTorch 2.11.0互換、OpenMMLab依存なし、活発にメンテナンス

## 4. 該当なしのセクション

本案件はパッケージインストールのみでコード変更を伴わないため、以下のセクションは該当なし:

- **1.2 システム構成**: コード変更なし
- **1.5 状態遷移**: GUI/ステートフル処理なし
- **1.6 ファイル・ディレクトリ設計**: 入出力ファイルなし
- **1.7 インターフェース定義**: 公開関数の追加・変更なし
- **1.8 ログ・デバッグ設計**: コード変更なし

## 5. 影響範囲

- コード変更: なし
- 新規ファイル: なし
- パッケージ追加: boxmot 16.0.11（+ 依存パッケージ14個: beautifulsoup4, filterpy, ftfy, gdown, joblib, lapx, loguru, pysocks, regex, scikit-learn, soupsieve, threadpoolctl, wcwidth, yacs）
- ドキュメント更新: `docs/TECH_STACK.md`, `.gitignore`

## 6. リスク

| リスク | 対策 |
|--------|------|
| 依存パッケージの競合 | dry-runで確認済み（既存パッケージのバージョン変更なし）。万一の場合は手順3のロールバック手順で復旧 |
| Re-IDモデルのダウンロード失敗 | ネットワーク接続を確認し再実行。手動ダウンロードも可能 |

## 7. 設計判断

| 判断 | 採用案 | 却下案と理由 |
|------|--------|------------|
| バージョン指定 | 16.0.11（固定） | 最新版（非固定）→ 再現性を確保するためバージョン固定を採用 |
| Re-IDモデル | osnet_x0_25_msmt17 | CLIPReID（重量級で初回検証には過剰）、MobileNetV2（OSNetより精度が劣る） |

## 8. テスト方法

手順4〜5のコマンドが正常に完了すれば合格。
