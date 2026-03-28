# 機能設計書: feat-002 MoEチェックポイントDL・分割

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001 | 4.1 ダウンロード手順 |
| FR-002 | 4.2 モデル分割 |
| FR-003 | 4.3 検証 |

## 2. システム構成

新規ファイルの作成・既存ファイルの変更はなし。すべて既存の `tools/model_split.py` と手動コマンドで完結する。

### ディレクトリ構成（変更後）

```
checkpoints/
├── vitpose-h-multi-coco.pth   # MoE統合（DL後リネーム）
├── coco.pth                   # 分割: COCO 17kp
├── aic.pth                    # 分割: AIC 14kp
├── mpii.pth                   # 分割: MPII 16kp
├── ap10k.pth                  # 分割: AP10K 17kp
├── apt36k.pth                 # 分割: APT36K 17kp
└── wholebody.pth              # 分割: WholeBody 133kp
```

## 3. 技術スタック

既存の技術スタックのみ使用。追加ライブラリなし。

- Python 3.10.16
- PyTorch 2.11.0+cu128（`torch.load`, `torch.save` のみ使用。CPUで動作）

## 4. 各機能の詳細設計

### 4.1 ダウンロード手順 (FR-001)

#### データフロー

- **入力**: OneDrive共有URL（文字列）
- **出力**: `checkpoints/vitpose-h-multi-coco.pth`（PyTorch checkpoint dict を `torch.save()` で保存した `.pth` ファイル。ファイルサイズ: 1GB以上。FR-001受け入れ基準参照）

#### 処理ロジック

1. `checkpoints/` ディレクトリが存在しない場合は作成する: `mkdir -p checkpoints`
2. OneDrive共有URLからチェックポイントをダウンロードする

ダウンロード方法:

- ブラウザでOneDriveのURL `https://1drv.ms/u/s!AimBgYV7JjTlgccoXv8rCUgVe7oD9Q?e=ZBw6gR` を開き、手動でダウンロードして `checkpoints/` に配置する（CLIダウンロードは使用しない。設計判断セクション8参照）

3. ダウンロードしたファイル名が `vitpose-h-multi-coco.pth` でない場合、リネームする:
   ```bash
   # ダウンロードされたファイル名は ls checkpoints/ で確認する
   mv checkpoints/<ダウンロードされたファイル名> checkpoints/vitpose-h-multi-coco.pth
   ```
4. ファイルの存在とサイズを確認する:
   ```bash
   ls -lh checkpoints/vitpose-h-multi-coco.pth
   ```

#### エラーハンドリング

- ダウンロード失敗時: ブラウザを変更して再試行する。URLが無効な場合は要求仕様書の制約条件に従いViTPose公式リポジトリからリンクを再取得する
- ファイル破損時（`torch.load()` でエラー）: 再ダウンロードを実施する

### 4.2 モデル分割 (FR-002)

#### データフロー

- **入力**: `checkpoints/vitpose-h-multi-coco.pth`（MoE統合チェックポイント）
  - 型: PyTorch checkpoint dict, キー `state_dict` に全パラメータを含む
  - MoEエキスパート: `state_dict` 内の `mlp.experts.{0-5}` キーに格納（6データセット分）
  - デコーダヘッド: `keypoint_head.*`（COCO用）+ `associate_keypoint_heads.{0-4}.*`（他5データセット用）
- **出力**: 6つの `.pth` ファイル（`checkpoints/` ディレクトリ内）

#### 処理ロジック

既存の `tools/model_split.py` をそのまま使用する。カレントディレクトリは `/home/sakagawa/git/ViTPose` で実行すること。コマンド:

```bash
cd /home/sakagawa/git/ViTPose
python tools/model_split.py --source checkpoints/vitpose-h-multi-coco.pth
```

`--target` を省略すると、`--source` のパスからファイル名を除いたディレクトリに出力される。上記コマンドでは `checkpoints/` に出力される。`--source` にはディレクトリを含むパスを指定すること（ファイル名のみを指定するとtargetが空文字列となり、カレントディレクトリに出力されてしまう）。

#### model_split.py の内部動作（理解のため記載、コード変更はしない）

**COCO（expert 0）の処理:**
1. `copy.deepcopy(ckpt)` で全体をコピー
2. 各 `mlp.fc2` の重みに `mlp.experts.0` を concat する
3. そのまま `coco.pth` として保存する
4. **注意**: COCO処理では `associate_keypoint_heads` や `experts` のキーは除去されない。`keypoint_head.final_layer` のトリミングも行われない。そのため `coco.pth` は以下の特徴を持つ:
   - `keypoint_head.final_layer.weight` の shape[0] は17（実測で確認済み。MoEモデルのCOCO用デコーダヘッドは元から17チャネル）
   - 不要なキー（`associate_keypoint_heads.*`, `mlp.experts.*`）が残存する
   - 推論時にはconfigの `num_output_channels=17` により先頭17チャネルのみ使用される。不要キーは `strict=False` で無視される

**AIC〜WholeBody（expert 1〜5）の処理:**
1. `copy.deepcopy(ckpt)` で全体をコピー
2. 各 `mlp.fc2` の重みに対応する `mlp.experts.{i}` を concat する
3. `associate_keypoint_heads.{i}` の全重みを `keypoint_head` に上書きコピーする
4. `keypoint_head.final_layer.weight` と `.bias` を先頭 `num_keypoints[i]` 行に切り詰める
5. `associate_keypoint_heads.{0-4}` のキーを除去する
6. **注意**: `mlp.experts.*` のキーは除去処理にバグ（98行目: `if 'expert' in keys:` が `if 'expert' in key:` であるべき）があり、実際には除去されない。分割後ファイルにexpertキーが残存するが、推論には影響しない

**出力ファイルとエキスパートの対応:**

全データセット共通で、バックボーンの各 `mlp.fc2` に対応する `mlp.experts.{expert番号}` を concat する処理が行われる。デコーダヘッドの処理はデータセットにより異なる:

| ファイル | expert | num_keypoints | デコーダヘッドの処理 |
|----------|--------|---------------|---------------------|
| coco.pth | 0 | 17（トリミングなし） | 元の keypoint_head をそのまま使用（トリミング・置換なし） |
| aic.pth | 1 | 14 | associate_keypoint_heads.0 → keypoint_head にコピー後トリミング |
| mpii.pth | 2 | 16 | associate_keypoint_heads.1 → keypoint_head にコピー後トリミング |
| ap10k.pth | 3 | 17 | associate_keypoint_heads.2 → keypoint_head にコピー後トリミング |
| apt36k.pth | 4 | 17 | associate_keypoint_heads.3 → keypoint_head にコピー後トリミング |
| wholebody.pth | 5 | 133 | associate_keypoint_heads.4 → keypoint_head にコピー後トリミング |

#### エラーハンドリング

- `--source` のファイルが存在しない場合: `torch.load()` が `FileNotFoundError` を発生。ダウンロード手順を再確認する
- メモリ不足: MoEモデルは大容量。`deepcopy` を複数回行うため、RAM 16GB以上を推奨

#### 境界条件

- MoEモデルのエキスパート数がmodel_split.pyの期待（6エキスパート: expert 0〜5）と異なる場合、スクリプトが `exist_range = False` で途中終了し、一部ファイルのみ生成される。ViTPose++ Huge MoEは6エキスパートを持つため、この問題は発生しない

### 4.3 検証 (FR-003)

#### データフロー

- **入力**: 分割済み6ファイル（`checkpoints/{coco,aic,mpii,ap10k,apt36k,wholebody}.pth`）
- **出力**: コンソールに各ファイルのキーポイント数を表示

#### 処理ロジック

Pythonワンライナーで検証する（ファイルとして保存しない、使い捨ての検証用）:

```python
import torch

files = {
    'coco.pth': 17,
    'aic.pth': 14,
    'mpii.pth': 16,
    'ap10k.pth': 17,
    'apt36k.pth': 17,
    'wholebody.pth': 133,
}

for name, expected_kp in files.items():
    ckpt = torch.load(f'checkpoints/{name}', map_location='cpu', weights_only=False)
    actual_kp = ckpt['state_dict']['keypoint_head.final_layer.weight'].shape[0]
    status = 'OK' if actual_kp == expected_kp else 'MISMATCH'
    print(f'{name}: keypoints={actual_kp} (expected={expected_kp}) [{status}]')
```

全ファイルで期待キーポイント数との完全一致で判定する（COCOも実測で17と確認済み）。

#### エラーハンドリング

- ファイルが見つからない場合: 分割が正常に完了していない。FR-002を再実行する
- キーポイント数が不一致の場合: MoEモデルのバージョン違いの可能性。ダウンロードしたモデルを確認する

## 5. インターフェース定義

該当なし（新規コード作成なし。既存の `tools/model_split.py` をCLIから実行するのみ）

## 6. ファイル・ディレクトリ設計

セクション2のディレクトリ構成を参照。設定ファイルの新規作成はない。

## 7. ログ・デバッグ設計

該当なし（新規コード作成なし）

## 8. 設計判断

### DL方法: ブラウザ手動DL vs CLIダウンロード

- **採用案**: ブラウザでの手動ダウンロードを推奨（方法A）
- **却下案**: wget/curlによるCLI自動ダウンロード
- **理由**: OneDriveの共有リンクは認証リダイレクトやJavaScript依存があり、CLI直接ダウンロードが安定しない。1回限りのダウンロードのためブラウザで手動取得が確実

### 検証方法: スクリプトファイル vs ワンライナー

- **採用案**: コマンドラインで直接実行（ファイル保存しない）
- **却下案**: `tools/verify_split.py` として保存
- **理由**: 1回限りの検証であり、保存する必要がない

### model_split.py のバグ修正: する vs しない

- **採用案**: 修正しない
- **却下案**: 98行目の `if 'expert' in keys:` を `if 'expert' in key:` に修正
- **理由**: CLAUDE.mdの方針「MMPose版ViTPose++のコードは可能な限り変更せず」に従う。expertキーの残存は推論に影響せず、ファイルサイズが大きくなるのみ
