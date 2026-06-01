# 要求仕様書: feat-010 OpenPose JSON出力

## 1. プロジェクト概要

- **何を作るか**: HALPE 26キーポイントの結合結果をPose2Sim互換のOpenPose JSONフォーマットで出力するスクリプトを作成する
- **なぜ作るか**: 最終目的はPose2Simに渡して3Dポーズ推定を行うこと。Pose2SimはOpenPose JSON形式の入力を期待するため、HALPE 26の結合結果をこの形式に変換する必要がある
- **誰が使うか**: 開発者（自分自身）
- **どこで使うか**: ローカルGPU環境（RTX 5060 Ti, CUDA 12.8）

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| OpenPose JSON | OpenPoseが出力するJSON形式。Pose2Simが入力として期待するフォーマット |
| pose_keypoints_2d | OpenPose JSONのキー。[x, y, confidence] × キーポイント数の平坦化リスト |
| Pose2Sim互換 | Pose2Simの `personAssociation.py` が読み込めるJSON形式とファイル命名規則に従うこと |

## 3. 機能要求一覧

### FR-001: OpenPose JSON出力スクリプトの作成

- **機能名**: HALPE 26 → OpenPose JSON変換・出力スクリプト
- **概要**: 入力動画の各フレームに対してHALPE 26推定を行い、フレームごとにOpenPose JSON形式のファイルを出力する
- **入力**:
  - 動画ファイル（コマンドライン引数で指定）
  - 人物検出モデル、WholeBodyモデル、AICモデル（feat-009と同じ）
- **出力**: `{out-dir}/{動画名}_json/` ディレクトリに、フレームごとのJSONファイルを出力
  - ファイル命名: `{動画名}_{フレーム番号:06d}.json`
  - 例: `cam05520129_000000.json`, `cam05520129_000001.json`, ...
- **受け入れ基準**:
  - スクリプト `scripts/halpe26_to_openpose.py` が存在する
  - スクリプトがエラーなく実行完了する
  - 出力ディレクトリにフレーム数と同じ数のJSONファイルが存在する
  - 各JSONファイルが以下の構造を持つ:
    - `version` キーが 1.3 である
    - `people` キーがリストである
    - 各personの `pose_keypoints_2d` が78要素（26キーポイント × 3）の平坦化リストである
    - `person_id`, `face_keypoints_2d`, `hand_left_keypoints_2d`, `hand_right_keypoints_2d`, `pose_keypoints_3d`, `face_keypoints_3d`, `hand_left_keypoints_3d`, `hand_right_keypoints_3d` キーが存在する（2D以外は空リスト）

### FR-002: 室内テスト動画でのJSON出力と検証

- **機能名**: 室内動画のOpenPose JSON出力
- **概要**: 室内テスト動画に対してFR-001のスクリプトを実行し、JSON出力の正しさを検証する
- **入力**: `/home/sakagawa/git/ViTPose_HuggingFace/input/cam05520129.mp4`（902フレーム）
- **出力**: `output/feat-010/cam05520129_json/` ディレクトリに902個のJSONファイル
- **受け入れ基準**:
  - `output/feat-010/cam05520129_json/` ディレクトリが存在する
  - ディレクトリ内に902個のJSONファイルが存在する
  - 先頭のJSONファイル（`cam05520129_000000.json`）のフォーマットが正しい
  - 末尾のJSONファイル（`cam05520129_000901.json`）のフォーマットが正しい

## 4. 非機能要求

- **処理時間**: 902フレームの処理が30分以内に完了する
- **GPU使用**: CUDA対応GPUで推論する
- **信頼性**: 出力ファイルは再実行により再生成可能

## 5. 制約条件

- feat-009の `merge_to_halpe26()` 関数を再利用する
- Pose2Simの命名規則に従う: ディレクトリ名は `{動画名}_json`、ファイル名は `{動画名}_{フレーム番号:06d}.json`
- JSONの `version` は 1.3（Pose2SimのposeEstimation.pyに合わせる）
- ネットワーク接続は不要

## 6. 優先順位

| ID | 優先度 | 備考 |
|----|--------|------|
| FR-001 | Must | スクリプト作成 |
| FR-002 | Must | 実データでの動作確認 |

MVP: FR-001〜FR-002すべて
