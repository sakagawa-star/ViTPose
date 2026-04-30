# feat-044: pink → blue 動画変換ツール

## ステータス

Open（requirements.md / design.md 作成中、レビュー待ち、コード未作成）

## 概要

`scripts/convert_pink_to_blue_video.py` を新規作成する。既存のピンク患者動画（病院着がピンクの研究員撮影データ）の HSV 空間でピンク領域を青に置換し、合成「青患者」テスト動画を生成する。NDA により本物の青患者動画を入手できないため、青色対応パイプライン（feat-045 以降）の動作検証用の合成データソースとして利用する。

## なぜ作るのか

- 本物の青患者動画は NDA により入手不可。青色対応パイプラインの開発・検証に使う代替データが必要
- ピンク患者動画は既に `experiments/input/camSony1_L.mp4` / `testdata/camSony1_S.mp4` 等で利用可能で、`postprocess_pink_id.py` の HSV 範囲でピンク領域を高精度で抽出できる
- ピンク領域の色を青に変換することで、エンドツーエンドのパイプラインテスト（HSV 検出 → BB 選択 → 連続性ボーナス → 後段の `pink_track_id` 相当の青版計算）が可能になる
- Blue2.png の HSV 分析（S 中央値 25、`H=90-140` で 94.2% が含まれる、二峰性: 低 S グレー + 中 S ネイビー）に基づき、変換ターゲットは「彩度を下げた青」とする

## スコープ

- `scripts/convert_pink_to_blue_video.py` のみ新規作成
- L2 レベルの変換: ピンク領域の H 置換 + S 圧縮（V は変更なし）
- HSV 範囲・変換パラメータは CLI 引数化
- 入力ピンク範囲のデフォルトは `postprocess_pink_id.py` の `FIXED_HSV_RANGES` と同一

## スコープ外

- L1（H 置換のみ、S/V 変更なし）/ L3（ネイビーストラップ模擬）レベルの実装
- 患者シルエット境界の検出・特殊処理
- `postprocess_blue_id.py` 本体（feat-045 で対応）
- 第三者向けの実行ガイド（feat-046 で対応）

## 親案件・関連案件

- 親: feat-033（pink_id 検出ロジック、HSV 範囲を流用）
- 兄弟: feat-045（青用 postprocess、本案件の出力動画で検証する）
- 後続: feat-045 / feat-046
