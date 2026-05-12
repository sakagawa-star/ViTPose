# feat-046: postprocess_pink_id.py のキーポイントベース ROI 対応

## ステータス

Open（requirements.md / design.md 作成中、レビュー待ち、コード未着手）

## 概要

`scripts/postprocess_pink_id.py` の pink_ratio 計算 ROI を、現状の「BB 全体の矩形領域」に加えて「HALPE26 の 4 キーポイント（両肩・両腰）の min/max 軸並行矩形」を選択可能にする。CLI `--roi-mode {bb,keypoint-rect}` で切替（デフォルト bb、既存挙動を維持）。

論理的には背景・四肢・顔の HSV ノイズが ROI に含まれなくなるため、ピンク領域の純度が上がり以下の効果が期待される:

- 患者フレームの `pink_ratio` 値が上がる（背景画素が分母から減る）
- 他人物との `pink_ratio` 差が広がり、誤選択が減る
- 色非依存（青患者など）への拡張時にも、同じ ROI 切り出し戦略が流用可能

ただし臥位・遮蔽・キーポイント低信頼時に ROI が縮退するリスクがあるため、F2 厳しめフォールバック（ROI 構築不能なら pink_ratio=0）を採用する。

## なぜ作るのか

- 現状の BB 全体 ROI ではシーツ・寝具・医療機器・肌・髪などが HSV 比率計算に混入し、ピンク患者と非ピンク患者のマージンが狭い
- feat-044 の HSV 分離不可確定（H 円環距離 31、重なり率 46%）から、ピクセル単位での色分離は困難と分かったが、**領域を絞れば**ピンク濃度のコントラストは改善できる可能性が高い
- 青患者対応にも同じ枠組み（ROI 絞り込み + 色判定）が転用可能で、feat-044 の代替路にもなり得る

## スコープ

- `scripts/postprocess_pink_id.py` のみ修正
- CLI 引数 3 つ追加: `--roi-mode`, `--kpt-conf-min`, `--min-roi-area`
- keypoint-rect モードのロジック追加（K-2 採用、信頼できる点のみで min/max 矩形構築、F2 厳しめフォールバック）
- 既存挙動（bb モード）は完全に維持

## スコープ外

- HALPE26 推論パイプライン (`run_halpe26_pipeline_yolo11.py`) の変更
- 多角形 ROI（I）/ 回転矩形 ROI（II-b）の実装
- 検証・比較スクリプト（feat-047 で対応）
- pink_id 選択ロジック (`select_pink_bbox`) 自体の変更
- 青色対応への横展開（別案件で検討）

## 親案件・関連案件

- 親: feat-033（pink_id 検出ロジック本体）
- 兄弟: feat-047（本案件の検証ツール、`compare_roi_modes.py` + `visualize_disagreement_frames.py`）
- 関連: feat-044 凍結（HSV 単独分離不可確定が本案件の動機の一つ）
