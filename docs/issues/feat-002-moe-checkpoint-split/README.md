# feat-002: MoEチェックポイントDL・分割

## ステータス: Closed (2026-03-28)

## 概要

ViTPose++ Huge MoEモデルのチェックポイントをOneDriveからダウンロードし、`tools/model_split.py` で6データセット分に分割した。

## 成果物

```
checkpoints/
├── vitpose-h-multi-coco.pth   # MoE統合 (3.5GB)
├── coco.pth                   # COCO 17kp (3.7GB)
├── aic.pth                    # AIC 14kp (3.6GB)
├── mpii.pth                   # MPII 16kp (3.6GB)
├── ap10k.pth                  # AP10K 17kp (3.6GB)
├── apt36k.pth                 # APT36K 17kp (3.6GB)
└── wholebody.pth              # WholeBody 133kp (3.6GB)
```

## 検証結果

全6ファイルのキーポイント数が期待値と一致:

```
coco.pth: keypoints=17 (expected=17) [OK]
aic.pth: keypoints=14 (expected=14) [OK]
mpii.pth: keypoints=16 (expected=16) [OK]
ap10k.pth: keypoints=17 (expected=17) [OK]
apt36k.pth: keypoints=17 (expected=17) [OK]
wholebody.pth: keypoints=133 (expected=133) [OK]
```
