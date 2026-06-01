# feat-010: OpenPose JSON出力

## ステータス: Closed (2026-03-28)

## 概要

HALPE 26キーポイントの結合結果をPose2Sim互換のOpenPose JSONフォーマットで出力するスクリプト `scripts/halpe26_to_openpose.py` を作成した。

## 出力仕様

- ディレクトリ: `{video_stem}_json/`
- ファイル命名: `{video_stem}_{frame:06d}.json`
- JSON version: 1.3（Pose2Sim互換）
- pose_keypoints_2d: 78要素（HALPE 26 × 3）

## 確認結果

- 室内動画（902フレーム）に対してエラーなく実行完了
- 902個のJSONファイルが正しいフォーマットで出力された
- 先頭・末尾ファイルのフォーマット検証済み（version=1.3, 78要素, 全キー存在）
