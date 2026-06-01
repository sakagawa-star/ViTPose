# feat-040: pink_ratio 時系列可視化グラフ

## ステータス

Closed（2026-04-29）

## 完了時メモ

- `scripts/plot_pink_ratio_timeline.py` を新規作成（4 パネル PNG 出力）
- `from postprocess_pink_id import MIN_PINK_RATIO` で定数を import（ハードコード重複なし）
- `_group_consecutive` 純関数で連続フレーム区間を 1 axvspan に集約
- 動作確認: camSony1_L（321,239 フレーム）を 37.4 秒で完走、PNG 516KB、`pink_id=1` フレーム数 235,296、際どい差分（< 0.05）フレーム数 4,108
- `--frame-start` / `--frame-end` の部分描画も動作確認（フレーム 47900–48000、101 フレームで 15.4 秒）

## 概要

feat-039 で `postprocess_pink_id.py` が出力 JSON に保存するようになった `pink_ratio`（HSV ピンク画素比率、float、値域 [0.0, 1.0]）を、フレーム軸の時系列 PNG グラフとして可視化する診断スクリプトを新規作成する。

`scripts/plot_pink_ratio_timeline.py` として実装予定。feat-037 の `plot_pink_track_timeline.py` と同じ「ポストプロセス出力 → PNG ダイアグラム」スタイル。

## 目的

- 閾値 `MIN_PINK_RATIO = 0.03` の妥当性を時系列で目視確認できるようにする
- feat-037 の時系列グラフで検出された「対象不在区間での `pink_id=1` 誤検出」が、`pink_ratio` の時系列上でどのような特徴（弱い比率の継続、複数候補の混在など）として現れているかを観察する
- 将来の閾値チューニング・色空間調整の判断材料を蓄積する

## スコープ

- 入力: feat-039 改修済み `postprocess_pink_id.py` の出力 JSON ディレクトリ
- 出力: 1 枚の PNG 時系列グラフ
- 描画想定パネル（詳細は requirements.md で確定）:
  - 全 BB の `pink_ratio` を散布図 / 細線で表示
  - `pink_id=1` の BB の `pink_ratio` を強調
  - `MIN_PINK_RATIO=0.03` の閾値ライン

## スコープ外

- 動画オーバーレイ可視化（feat-038 で対応済み）
- pink_id 選択ロジックの変更
- HSV レンジ・閾値の変更

## 親案件・関連案件

- feat-033: `postprocess_pink_id.py` 本体（pink_id 付与、HSV ピンク比率計算）
- feat-037: `plot_pink_track_timeline.py`（同種の時系列可視化、本案件の設計の参考）
- feat-039: `pink_ratio` フィールド追加（本案件の入力データを生成）
