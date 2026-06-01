# feat-024: YOLO11x検出器検証 — 要求仕様書

## 1. プロジェクト概要

- **何を作るか**: YOLO11x（ultralytics）を検出器として使用する検証用パイプラインスクリプト
- **なぜ作るか**: feat-023でYOLOX-l（mAP 49.4）に差し替えたが、cam05520125.mp4ではBB重複問題が残存した。より高精度なYOLO11x（mAP 54.7）で改善するか検証する
- **誰が使うか**: 開発者（検証用）
- **どこで使うか**: RTX 5060 Ti搭載マシン、CUDA環境

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| YOLO11x | Ultralytics YOLO v11のExtra Largeモデル。COCO val2017でmAP 54.7、56.9Mパラメータ |
| YOLOX-l | feat-023で検証済み。COCO val2017でmAP 49.4。camSony1_SではBB重複解消、cam05520125では重複残存 |
| BB重複問題 | 臥位の人物に対して1つの体に複数のBBが出力される問題 |
| ultralytics | YOLO11xを提供するPythonパッケージ |
| process_yolo11_results | YOLO11xの出力をMMPose互換のperson_results形式に変換する関数（本案件で新規作成） |

## 3. 機能要求一覧

### FR-001: ultralyticsパッケージのインストール

- **機能名**: ultralytics パッケージのインストール
- **概要**: `uv pip install ultralytics==8.4.33` でYOLO11xの実行環境を構築する
- **入力**: なし
- **出力**: ultralytics 8.4.33 がインストールされた状態
- **受け入れ基準**: `uv run python -c "from ultralytics import YOLO; print('OK')"` がエラーなく実行できること

### FR-002: YOLO11x検証用パイプラインスクリプトの作成

- **機能名**: YOLO11x検出器を使用する検証用パイプラインスクリプト
- **概要**: `scripts/run_halpe26_pipeline_yolox.py`（feat-023）をベースに、検出器をYOLO11xに差し替えたスクリプトを作成する。YOLO11xの出力はMMDetと異なるため、MMPose互換の変換関数を作成する
- **入力**: `--video`（動画パス）、`--out-dir`（出力ディレクトリ）、`--device`（ポーズ推定モデルのデバイス。YOLO11xにも同じデバイスを明示指定する）、`--mode`、`--bbox-thr`（デフォルト0.3）、`--kpt-thr`、`--profile`
- **出力**: 既存パイプラインと同じ出力（可視化動画、OpenPose JSON）
- **受け入れ基準**:
  1. `testdata/cam05520129.mp4`（室内動画）で実行が完了し、可視化動画が出力されること
  2. YOLO11xの出力がMMPose互換のperson_results形式に正しく変換されること（各要素が`{'bbox': ndarray([x1, y1, x2, y2, score])}`の形式）
  3. `--bbox-thr 0.5` で実行した場合、`--bbox-thr 0.3` よりBB数が減ること（フィルタリングが機能していること）

### FR-003: 室内動画での検出精度の比較確認

- **機能名**: 検出結果の目視比較
- **概要**: 室内動画に対してYOLO11x版パイプラインを実行し、BB描画結果を目視で確認する
- **入力**: `testdata/cam05520129.mp4`
- **出力**: BB描画付き可視化動画
- **受け入れ基準**: 出力動画が生成され、ユーザーがBBの重複問題の改善有無を目視で判断できること

## 4. 非機能要求

- **パフォーマンス**: 処理速度の要件なし（検証用スクリプトのため）。ただし`--profile`で速度を計測可能であること
- **対応環境**: RTX 5060 Ti + CUDA

## 5. 制約条件

- **使用必須**: ultralytics パッケージのYOLO11x（`checkpoints/yolo11x.pt`）を使用する
- **コード変更方針**: `scripts/run_halpe26_pipeline.py`、`scripts/run_halpe26_pipeline_yolox.py`、`scripts/merge_halpe26.py` を直接変更しない。新規スクリプトを作成する
- **チェックポイント**: YOLO11xのモデル（`checkpoints/yolo11x.pt`）はプロジェクトのcheckpoints/ディレクトリに配置する
- **MMPose互換**: YOLO11xの出力を`inference_top_down_pose_model`が受け取れる形式に変換する必要がある
- **TECH_STACK.md更新**: インストール後、`docs/TECH_STACK.md`にultralytics 8.4.33（用途: YOLO11x人物検出）を追記すること

## 6. 優先順位

| ID | 優先度 | 備考 |
|----|--------|------|
| FR-001 | Must | パッケージがないと検証不可 |
| FR-002 | Must | 検証用スクリプトの本体 |
| FR-003 | Must | 検証の目的そのもの |

MVP: FR-001〜FR-003すべて。
