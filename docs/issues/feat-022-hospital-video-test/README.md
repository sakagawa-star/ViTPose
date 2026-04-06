# feat-022: 病室動画トラッキング・Re-ID検証

## ステータス: Closed

## 概要

病室動画で人物トラッキングとRe-ID（見切れ後の再同定）を検証する。

### イテレーション1（Closed）
BoxMOT + Deep OC-SORTの内蔵Re-ID（OSNet/MSMT17）が病室ドメインで機能しないことを確認した。

### イテレーション2（Closed）
ViTPose HALPE 26キーポイント + HSV色ヒストグラムを使ったカスタムRe-IDモジュールを実装。遅延Re-IDマッチ（N=180フレーム）により、camSony1_S.mp4で stable_id=1 に92.8%収束を確認。短時間出現（8フレーム以下）で遅延マッチが間に合わないケースは既知の制限事項。
