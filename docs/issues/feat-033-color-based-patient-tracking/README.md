# feat-033: 服装の色による対象同定（ポストプロセス）

## ステータス

Closed（2026-04-15）

## 完了結果サマリ

- `scripts/postprocess_pink_id.py` を実装し、camSony1_S（900フレーム）および camSony1_L（321,239フレーム）に適用完了
- camSony1_L 処理時間: 125.4 秒（2561 fps）
- camSony1_L での pink_id=1 付与率: 235,296 / 321,239 フレーム（73.2%、人物検出ありフレームの 94.1%）
- `stable_id` との比較: `stable_id` 空間は同一対象を444個のIDに断片化していた（top9で累積91.7%）のに対し、`pink_id` は色ベースで一貫して同じ対象を選択。stable_id=59/33/7/79 のいずれも pink_id=1 一致率 93-99% で、`custom_reid.py` の HSV ヒストグラム EMA 汚染によるID断片化が広範に発生していたことを定量的に確認
- 上記結果を受けて feat-034「pink_id + Deep OC-SORT による新トラッキング方式」を立ち上げ、`stable_id` / `custom_reid.py` 関連案件（feat-026/027/030/031/032）は凍結に移行

## 概要

別研究者が作成した `pink_tracker_jhub.py`（対象衣服のHSVピンク比率で対象BBを選択する方式）のロジックを参考に、本リポジトリの `run_halpe26_pipeline_yolo11.py` が出力したHALPE 26 OpenPose JSON + 元動画に適用し、対象同定の結果を検証する。

本案件では既存JSONに新フィールド `pink_id`（選択 = 1 / 非選択 = -1）を付与するポストプロセススクリプトを作成し、feat-028で付与される `stable_id`（Deep OC-SORT + カスタムRe-IDベース）とは別枠のIDとして両方式の性能差を比較可能にする。

## 背景

feat-032（ポーズ誘導外観特徴量の独立検証）の前段として、より単純な外観ベース（衣服色）の対象同定がどの程度機能するかを先に確認しておくと、feat-032で観測する「ポーズ誘導外観特徴量」の評価基準を決めやすい。色ベース方式はロジックが明瞭で汚染メカニズムの観察も容易なため、比較ベースラインとして有用と判断した。

参考元の `pink_tracker_jhub.py` はHSVレンジ・閾値がハードコードされている（「色の情報を固定化している」）。本案件でも初回は色パラメータを固定のまま評価し、可変化は結果を見てから判断する。

## 目的

- HALPE 26 OpenPose JSON + 元動画を入力とし、各フレームの各BBについてHSVピンクマスク比率を計算する
- 閾値超のBBから「比率 + 前フレームBBとのIoU連続性ボーナス」が最大のBBを対象として選択する
- 既存JSONに `pink_id` フィールド（1 = 選択、-1 = 非選択）を付与するポストプロセススクリプトを作成する
- `stable_id`（feat-028）と `pink_id` の一致・不一致を観察し、色ベース方式の限界と有効範囲を把握する

## 対象動画と段取り

- **フェーズ1（本案件内で実施）**: `testdata/camSony1_S.mp4`（960×540、30fps、445フレーム、camSony1_L から切り出した短縮版）で動作確認・定性評価する。短いため反復検証に適する
- **フェーズ2（本案件実装完了後、ユーザー指示を受けて実施）**: `experiments/input/camSony1_L.mp4`（約321Kフレーム）に適用し、feat-028の `stable_id` との定量比較を行う

初回テスト用の入力JSONは `experiments/results/camSony1_S_json/`（445フレーム、`stable_id` なし）を使う。S版では `stable_id` が付与されていないため、フェーズ1は `pink_id` 付与処理自体の動作検証が中心となる。両IDの比較は、`stable_id` が付与済みの `experiments/results/camSony1_L_reid_json/` を入力に使うフェーズ2で行う。

## スコープ外

- HSVレンジ・閾値のCLI引数化 / 設定ファイル化（初回は `pink_tracker_jhub.py` の値を固定流用。色パラメータはスクリプト内の定数として定義）
- 色以外の外観特徴量（テクスチャ、深層特徴量など）
- トラッキング本体（Deep OC-SORT）の変更、`stable_id` の上書き
- 可視化スクリプトの作成・修正（`visualize_tracking.py` への `pink_id` 対応も含めて本案件のスコープ外。数値比較・目視確認はCSVおよび既存ツールで対応）
- フェーズ2（L版への適用）の実行。本案件ではスクリプトが L 版でも動作する設計にはするが、実行はユーザーからの指示後

## 前提

- 入力動画は `testdata/camSony1_S.mp4`、入力JSONディレクトリは `experiments/results/camSony1_S_json/`
- `camSony1_S.mp4` は `camSony1_L.mp4` から切り出した動画であり、対象衣服色は `pink_tracker_jhub.py` が動作した原動画と同系統のピンクであると報告されている
- feat-032は本案件完了まで凍結

## 完了条件・feat-032との関係

- 色ベース対象同定ポストプロセスが動作し、`pink_id` 付与JSONがフェーズ1対象（camSony1_S）に対して生成されること
- フェーズ1の `pink_id` 付与結果をユーザーが目視確認し、機能的に想定通り動作していることを承認すること
- 本案件完了後、ユーザー指示のもとフェーズ2（L版への適用）を実行し、その結果を踏まえて feat-032（ポーズ誘導外観特徴量の独立検証）の方針（続行 / スキップ / 目的変更）を再決定し、feat-032のステータス（Frozen → Open or Cancelled）を更新する

## 次のステップ

1. 要求仕様書 `requirements.md` の作成
2. 機能設計書 `design.md` の作成
3. サブエージェントレビュー + ユーザーレビュー
4. 実装（ポストプロセススクリプト + JSONスキーマ拡張）
5. `testdata/camSony1_S.mp4` + `experiments/results/camSony1_S_json/` での動作確認・定性評価

## 参考スクリプト

`/home/sakagawa/Downloads/pink_tracker_jhub.py` — 別プロジェクトで作成された原版。入力形式（Ultralytics YOLO pose txtラベル）・描画スケルトン（COCO 17）が本リポジトリと異なるため、ロジック部分（HSVマスク生成、ピンク比率計算、IoU連続性ボーナスによるBB選択）のみを参考にする。

## 関連案件

- 前提: feat-028（JSONに `stable_id` 記録）— 色ベースIDと比較する対象
- 前提: feat-024（YOLO11x検出器）— 入力JSONを生成するパイプライン
- 後続: feat-032（ポーズ誘導外観特徴量の独立検証、本案件完了後に方針再決定）

## 関連ファイル

- `scripts/run_halpe26_pipeline_yolo11.py` — 入力JSONを生成するパイプライン
- `scripts/postprocess_reid.py` — `stable_id` を付与する既存ポストプロセス（本案件のスクリプトはこれと同じ流儀で作成）
- `testdata/camSony1_S.mp4` — フェーズ1の検証対象動画
- `experiments/results/camSony1_S_json/` — フェーズ1の入力JSONディレクトリ
- `experiments/input/camSony1_L.mp4` — フェーズ2の対象動画
- `experiments/results/camSony1_L_reid_json/` — フェーズ2の入力JSONディレクトリ（`stable_id` 付与済み）
- `/home/sakagawa/Downloads/pink_tracker_jhub.py` — 参考スクリプト（リポジトリ外）
