# feat-019: 人物トラッキング調査レポート＋ロードマップ

## 1. 目的

HALPE 26パイプラインに人物トラッキング機能を追加し、フレーム間で同一人物にIDを維持する。トラッキングIDをOpenPose JSONに記録し、後処理で「最も長時間映っているID＝患者」として特定可能にする。

## 2. 要件

### 2.1 動画の特性

- 病室の固定カメラ映像（1時間単位のファイル、1週間連続記録）
- 通常1人の患者＋看護師等が出入りして2-3人になることがある
- 患者はてんかん患者でベッド上で自由に動く（位置固定ではない）
- 患者がカメラから見切れることがある（数秒以上）
- 布団、チューブ、医療機器による遮蔽が頻繁
- 画面外で着替えることがあり、その場合はIDが変わることを許容する（人間が紐付ける）

### 2.2 トラッキングに求められる精度

- 1時間の動画内で同一人物にIDを維持する
- 数秒の見切れ後に同一人物として再同定できる（Re-ID）
- 動画間（ファイル跨ぎ）のID継続は不要（各動画で独立に患者を特定する）
- 画面外での着替え後にIDが変わるのは許容

## 3. トラッキング手法の調査

### 3.1 MMPose内蔵トラッキング（IoU / OKS）

**場所**: `mmpose/apis/inference_tracking.py` の `get_track_id()`

**概要**: 前フレームと現フレームのbbox IoUまたはキーポイントOKSで同一人物を対応付ける貪欲法マッチング。

**API**:
```python
results, next_id = get_track_id(
    results,           # 現フレームのポーズ結果
    results_last,      # 前フレームのポーズ結果（track_id付き）
    next_id,           # 次に割り当てるID
    use_oks=False,     # True: OKS, False: IoU
    tracking_thr=0.3,  # マッチング閾値
    use_one_euro=False, # 時間方向スムージング
    fps=None,          # 動画FPS（OneEuroFilter用）
)
```

**アルゴリズム**:
- 貪欲法（全体最適ではない）
- 動き予測なし（前フレームとの類似度のみ）
- 1フレームでも検出が消えるとIDが切れる（再割り当ての仕組みなし）

**OKS使用時の制約**:
- `oks_iou()` のsigmasはCOCO 17キーポイント用がデフォルト
- HALPE 26で使う場合、26個のsigmas値への拡張が必要
- `_track_by_oks()` はsigmasを外部から渡せない設計（要修正）

**デモスクリプト**: `demo/top_down_pose_tracking_demo_with_mmdet.py`

**評価**:
| 項目 | 評価 |
|------|------|
| 見切れ（数フレーム） | NG — 1フレームの欠落でID喪失 |
| 見切れ（数秒） | NG — 再同定の仕組みなし |
| 2人接近時 | IoU: NG（ID swap）、OKS: 中（ポーズで区別可能） |
| 遮蔽（布団等） | IoU: 弱、OKS: やや弱（キーポイント不足時） |
| 実装コスト | ゼロ（既存API） |
| 追加依存 | なし |

**結論**: 見切れが数秒以上ある本ユースケースでは精度不足。

### 3.2 ByteTrack

**概要**: SORTの改良版。Kalmanフィルタによる動き予測＋ハンガリアン法による最適マッチング＋低スコア検出の二段階マッチング。

**特徴**:
- Kalmanフィルタで位置を予測し続けるため、数フレームの見切れならID維持可能（設定次第で30フレーム程度）
- 低スコアの部分検出も二段階目で拾うため、遮蔽に強い
- ハンガリアン法（全体最適）でID swap耐性が高い
- Re-ID特徴量を持たないため、長時間の見切れ後は再同定不可

**評価**:
| 項目 | 評価 |
|------|------|
| 見切れ（数フレーム） | OK — Kalmanフィルタで予測 |
| 見切れ（数秒） | NG — Re-IDなしでは再同定不可 |
| 2人接近時 | 良 — ハンガリアン法で全体最適 |
| 遮蔽（布団等） | 良 — 低スコア検出の二段階マッチング |
| 実装コスト | 中（スタンドアロン実装可能、100行程度） |
| 追加依存 | scipy（既存）のみ |

**結論**: 数秒の見切れに対応できないため、単独では不足。

### 3.3 DeepSORT

**概要**: Kalmanフィルタ＋Re-ID特徴量＋ハンガリアン法。見た目の特徴ベクトルで人物を識別するため、長時間の見切れ後も再同定可能。

**リポジトリ内の既存資産**:
- 設定ファイル: `demo/mmtracking_cfg/deepsort_faster-rcnn_fpn_4e_mot17-private-half.py`
- デモスクリプト: `demo/top_down_pose_tracking_demo_with_mmtracking.py`
- MMTracking (`mmtrack`) パッケージ経由で使用する設計

**DeepSORT設定の主要パラメータ**:
- Detector: FasterRCNN (R50+FPN)
- Motion: KalmanFilter
- ReID: ResNet50 → 128次元特徴ベクトル
- Tracker: `num_frames_retain=100`（追跡保持フレーム数）

**評価**:
| 項目 | 評価 |
|------|------|
| 見切れ（数フレーム） | OK — Kalmanフィルタ |
| 見切れ（数秒） | OK — Re-ID特徴量で再同定 |
| 2人接近時 | 最良 — Re-ID + 動き予測 |
| 遮蔽（布団等） | 良 |
| 実装コスト | 高（MMTracking導入が必要） |
| 追加依存 | mmtrack + Re-IDモデルチェックポイント |

**懸念点**:
- MMTracking (mmtrack) はMMPose 0.24.0と同世代のOpenMMLab v1ベース。バージョン互換性の確認が必要
- Re-IDモデルはMOT17（街中の歩行者）で学習されており、病室環境（病院着、臥位）でのRe-ID精度は未知
- 追加のGPUメモリ消費（Re-IDモデル分）

**結論**: ~~要件を満たす唯一の手法。ただしRe-IDの病室環境での精度は技術検証が必要。~~ → BoxMOT + Deep OC-SORTの発見により、より優れた選択肢が見つかった（3.5節参照）。

### 3.4 ~~手法比較まとめ~~ 初回調査時点の比較（2026-03-29）

| | 見切れ数秒 | 2人接近 | 遮蔽 | 実装コスト | 追加依存 | 判定 |
|--|:--:|:--:|:--:|:--:|:--:|:--:|
| IoU (MMPose内蔵) | NG | NG | 弱 | ゼロ | なし | 不採用 |
| OKS (MMPose内蔵) | NG | 中 | やや弱 | ほぼゼロ | なし | 不採用 |
| ByteTrack | NG | 良 | 良 | 中 | scipy | 単独では不足 |
| DeepSORT | OK | 最良 | 良 | 高 | mmtrack | ~~採用候補~~ → 3.5で上位互換あり |

### 3.5 BoxMOT + Deep OC-SORT（2026-03-30 追加調査）

#### 3.5.1 BoxMOTの概要

**BoxMOT** は複数のSOTAマルチオブジェクトトラッキングアルゴリズムをプラグイン形式で利用できるPythonパッケージ。任意の物体検出器と組み合わせ可能。

| 項目 | 内容 |
|------|------|
| リポジトリ | https://github.com/mikel-brostrom/boxmot |
| 最新バージョン | 16.0.11（2026年2月更新） |
| ライセンス | AGPL-3.0（研究・社内利用は問題なし。サービス提供時はソース公開義務あり） |
| インストール | `uv pip install boxmot` |
| OpenMMLab依存 | **なし**（mmcv/mmdet/mmposeと競合しない） |
| メンテナンス | 活発（2026年2月時点で更新あり） |

**対応トラッカー一覧**:

| トラッカー | Re-ID | 特徴 |
|-----------|:-----:|------|
| **DeepOCSORT** | **あり** | **OC-SORTにRe-IDを適応的に統合。遮蔽に強い** |
| StrongSORT | あり | DeepSORTの改良版。EMAによる特徴量更新 |
| BoTSORT | あり | カメラモーション補正 + Re-ID |
| BoostTrack | あり | 最新のトラッキング手法 |
| HybridSORT | あり | モーション + 外見のハイブリッド |
| ByteTrack | なし | 低スコア検出の二段階マッチング |
| OCSort | なし | 観測中心のモーション予測 |
| SFSort | なし | 軽量トラッカー |

**Python/PyTorch互換性**:

| 項目 | BoxMOT要件 | 現環境 | 判定 |
|------|-----------|--------|------|
| Python | >=3.9, <3.13 | 3.10.16 | **OK** |
| PyTorch | >=2.2.1, <3.0.0 | 2.11.0+cu128 | **OK** |

**依存関係**: numpy, opencv-python>=4.7.0, scikit-learn>=1.3.0, filterpy>=1.4.5, lapx>=0.5.5, gdown, huggingface-hub。OpenMMLab依存は一切なく、既存環境との競合リスクは極めて低い。

#### 3.5.2 Deep OC-SORTの仕組み

**論文**: "Deep OC-SORT: Multi-Pedestrian Tracking by Adaptive Re-Identification" (arxiv: 2302.11813, ICIP 2023)

OC-SORTをベースに、Re-ID特徴量を適応的に統合した手法。以下の3モジュールで構成される。

1. **Camera Motion Compensation (CMC)**: カメラ移動をフレーム間で補正し、物体位置推定を改善
2. **Dynamic Appearance (DA)**: 検出信頼度に基づいてRe-ID特徴量の重みを適応的に調整。遮蔽やブラーで汚れたembeddingを自動的に無視する
3. **Adaptive Weighting (AW)**: 外見特徴の識別力に応じて重みを動的にブースト。1対1で明確にマッチする場合に外見情報を強く使う

**OC-SORTから継承した遮蔽耐性**:
- **Observation-Centric Recovery (ORU)**: 遮蔽中は仮想軌跡（等速仮定）で位置を予測し続け、再出現時にKalmanフィルタの蓄積誤差を補正する

**Re-IDモデル（BoxMOT経由）**:
- デフォルト: OSNet (osnet_x0_25_msmt17) — 2.2Mパラメータの軽量モデル
- その他: CLIPReID（重量級・高精度）、LightMBN、MobileNetV2
- **全て初回使用時に自動ダウンロード**（手動設定不要）

**ベンチマーク比較**:

| 指標 | OC-SORT | Deep OC-SORT |
|------|---------|-------------|
| MOT17 HOTA | 63.2 | **64.9** |
| MOT20 HOTA | 62.1 | **63.9** |
| DanceTrack HOTA | 54.6 | **61.3 (+6.7)** |

#### 3.5.3 DeepSORTとの比較

| 項目 | DeepSORT | Deep OC-SORT |
|------|----------|-------------|
| ベースアルゴリズム | SORT + Re-ID | OC-SORT + 適応的Re-ID |
| モーション予測 | 標準Kalmanフィルタ | Kalman + ORU（観測中心リカバリ） |
| Re-ID統合方法 | 固定重みでコスト関数に加算 | Dynamic Appearance（信頼度に応じた適応的重み付け） |
| 遮蔽中の振る舞い | Re-ID特徴量を更新（汚れたembeddingが混入） | 低信頼度のembeddingを自動無視 |
| 遮蔽後のKalman補正 | なし（誤差が蓄積） | ORUで仮想軌跡から補正 |
| カメラモーション | 非対応 | CMCで補正 |
| MOT17 HOTA | ~45-50（推定） | **64.9** |
| ID Switch | 類似外見・重遮蔽時に頻発 | 大幅に低減 |

**病室環境で重要な優位点**:
- 布団やチューブによる遮蔽中、低品質なRe-ID特徴量を自動的に無視し、クリーンな特徴量を維持
- 見切れ後もORU + Re-IDの組み合わせで再同定が可能
- DeepSORTの遮蔽時embedding汚染問題を根本的に解決

#### 3.5.4 評価

| 項目 | 評価 |
|------|------|
| 見切れ（数フレーム） | OK — Kalmanフィルタ + ORU |
| 見切れ（数秒） | OK — Re-ID特徴量で再同定 + ORUでKalman誤差補正 |
| 2人接近時 | 最良 — 適応的Re-ID + 動き予測 |
| 遮蔽（布団等） | 最良 — Dynamic Appearanceで低品質embedding排除 |
| 実装コスト | 低（pip installのみ、外部検出器対応） |
| 追加依存 | boxmot（OpenMMLab依存なし） |
| PyTorch互換性 | 問題なし（>=2.2.1, <3.0.0を公式サポート） |
| メンテナンス | 活発（2026年2月更新） |

**結論**: DeepSORTの上位互換であり、全ての評価軸で同等以上。インストールも容易で現環境との互換性問題がない。**採用候補として最も適切**。

### 3.6 手法比較まとめ（最終版 2026-03-30）

| | 見切れ数秒 | 2人接近 | 遮蔽 | 実装コスト | 追加依存 | PyTorch互換 | 判定 |
|--|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| IoU (MMPose内蔵) | NG | NG | 弱 | ゼロ | なし | - | 不採用 |
| OKS (MMPose内蔵) | NG | 中 | やや弱 | ほぼゼロ | なし | - | 不採用 |
| ByteTrack | NG | 良 | 良 | 中 | scipy | - | 単独では不足 |
| DeepSORT (MMTracking) | OK | 最良 | 良 | 高 | mmtrack (EOL) | リスク大 | 不採用（上位互換あり） |
| DeepSORT (deep-sort-realtime) | OK | 最良 | 良 | 中 | deep-sort-realtime | OK | 不採用（上位互換あり） |
| **Deep OC-SORT (BoxMOT)** | **OK** | **最良** | **最良** | **低** | **boxmot** | **OK** | **採用** |

## 4. 現在のパイプラインとの統合ポイント

### 4.1 現在のパイプライン構成

```
Faster R-CNN (人物検出)
    ↓ person_results (bbox: ndarray [x1, y1, x2, y2, score])
ViTPose++ WholeBody (133点推定)
ViTPose++ AIC (14点推定)
    ↓ wb_results, aic_results
merge_to_halpe26 (結合)
    ↓ all_halpe26 (26点)
halpe26_to_openpose_json (JSON出力)
    ↓ OpenPose JSON (person_id: [-1])
```

### 4.2 トラッキング統合後の構成（BoxMOT + Deep OC-SORT）

```
Faster R-CNN (人物検出) ← 既存のまま
    ↓ person_results (bbox: ndarray [x1, y1, x2, y2, score])
    ↓
BoxMOT DeepOCSORT tracker.update(dets, frame)
    ↓ track_ids (フレーム画像からRe-ID特徴量を抽出してマッチング)
    ↓
ViTPose++ WholeBody / AIC ← 既存のまま
    ↓ wb_results, aic_results
merge_to_halpe26 (結合)
    ↓ all_halpe26 (26点) + track_ids
halpe26_to_openpose_json (JSON出力)
    ↓ OpenPose JSON (person_id: [track_id])
```

**統合方針**: 既存パイプラインを変更せず、Faster R-CNNの検出結果をBoxMOTに渡してトラッキングIDを取得する。BoxMOTは外部検出器からのbbox入力に完全対応しており、パイプライン構成の変更は最小限。

**BoxMOT APIの使い方**:
```python
from boxmot import DeepOcSort
from pathlib import Path
import numpy as np

tracker = DeepOcSort(
    reid_weights=Path('osnet_x0_25_msmt17.pt'),  # Re-IDモデル（初回自動DL）
    device='cuda:0',
    half=True,
)

# 既存のbbox結果をBoxMOT形式に変換
# BoxMOT入力: ndarray shape (N, 6) = [x1, y1, x2, y2, confidence, class]
# 既存のbbox: ndarray shape (5,) = [x1, y1, x2, y2, score]
dets = np.column_stack([bboxes_array, np.zeros(len(bboxes_array))])  # class=0追加

# トラッキング更新（フレーム画像が必要: Re-IDのcrop→特徴量抽出に使用）
tracks = tracker.update(dets, frame)
# 出力: ndarray shape (M, 8) = [x1, y1, x2, y2, track_id, confidence, class, index]

if len(tracks) > 0:
    track_ids = tracks[:, 4].astype(int)
```

**注意点**:
- `tracker.update()` にはフレーム画像（`frame`）も渡す必要がある（Re-IDモデルがcropから特徴量を抽出するため）
- Re-IDモデル（OSNet x0.25, 2.2Mパラメータ）は軽量でGPUメモリ追加負荷は小さい

### 4.3 JSON出力の変更点

現在の `person_id` フィールド:
```json
"person_id": [-1]
```

トラッキング後:
```json
"person_id": [0]
```

既存の `halpe26_to_openpose_json()` 関数で `person_id` が `[-1]` にハードコードされている箇所を、`track_id` パラメータで上書きするだけで対応可能。

## 5. ロードマップ（段階的実装計画）

以下の順番で小さな機能ごとに実装する。各ステップは独立した案件（feat-XXX）として管理する。

> **2026-03-30 更新**: MMTracking/DeepSORT方針から BoxMOT + Deep OC-SORT 方針に変更。理由: PyTorch互換性リスクなし、OpenMMLab依存なし、DeepSORTより高精度、活発にメンテナンスされている。

### Phase 5A: 技術検証

| 順番 | 案件案 | 概要 | 依存 | 目的 |
|:--:|--------|------|------|------|
| 1 | BoxMOT環境構築 | `uv pip install boxmot` でインストール | - | BoxMOTが現環境にインストールできるか確認 |
| 2 | 既存JSON+動画でBoxMOT動作検証 | パイプライン出力済みのOpenPose JSON（bbox + bbox_score）と元動画を使い、ViTPose推論なしでDeep OC-SORTの動作を確認 | 1 | 最小コストでBoxMOTの動作・トラッキングIDの付与を確認。ViTPose推論不要のためGPU負荷なし |
| 3 | Deep OC-SORT病室動画検証 | 病室動画（testdata/cam05520129.mp4）でDeep OC-SORTを実行し、トラッキング精度を目視確認 | 2 | Re-IDが病室環境で機能するか確認 |
| 4 | 見切れ再同定の検証 | 患者が見切れる場面でIDが維持されるか確認。パラメータ調整 | 3 | 数秒の見切れ後の再同定精度を確認 |

**Phase 5Aの判定基準**:
- Deep OC-SORTが病室動画で実用的なトラッキング精度を示す → Phase 5Bへ進む
- 精度不足 → BoxMOT内の他トラッカー（StrongSORT, BoTSORT等）を試す、またはRe-IDモデルの変更を検討

### Phase 5B: パイプライン統合

| 順番 | 案件案 | 概要 | 依存 | 目的 |
|:--:|--------|------|------|------|
| 5 | Deep OC-SORT + HALPE 26統合パイプライン | 既存の `run_halpe26_pipeline.py` にBoxMOT DeepOCSORT を統合。既存のFaster R-CNN検出結果をトラッカーに渡してtrack_idを取得 | 4 | トラッキングIDをキーポイントに紐付ける |
| 6 | JSONにトラッキングID記録 | `halpe26_to_openpose_json()` の `person_id` にtrack_idを記録 | 5 | トラッキング結果をJSON出力に反映 |
| 7 | トラッキング付き動画可視化 | 可視化動画にトラッキングID（人物ごとに色分け）を描画 | 5 | トラッキング結果の目視確認手段 |

### Phase 5C: 後処理（患者特定）

| 順番 | 案件案 | 概要 | 依存 | 目的 |
|:--:|--------|------|------|------|
| 8 | 患者ID特定スクリプト | JSON群からトラッキングIDごとの出現フレーム数を集計し、最長時間のIDを患者として出力 | 6 | 患者のトラッキングIDを自動特定 |
| 9 | 患者フィルタリング | 指定したトラッキングIDのキーポイントのみを抽出したJSONを出力 | 8 | 患者のキーポイントのみを後段に渡す |

### 実装順序の根拠

- **Phase 5A（技術検証）を最優先**: Deep OC-SORTの病室動画での精度が未知であり、精度不足なら以降のPhaseは不要。最小コストで判断材料を得る
- **順番2（既存JSONでの動作検証）を早期に実施**: ViTPose推論を再実行せず、既に出力済みのJSONと元動画だけでBoxMOTの動作を確認できる。GPU負荷ゼロで最速の動作確認が可能
- **Phase 5B（統合）は検証後**: 技術検証で精度が確認できてから統合に着手する。案件5が最も工数が大きい
- **Phase 5C（後処理）は独立性が高い**: JSON出力さえあれば実装可能。Phase 5Bと並行して着手することも可能

## 6. 環境構築の調査

### 6.1 現環境

| パッケージ | バージョン |
|-----------|----------|
| Python | 3.10.16 |
| torch | 2.11.0+cu128 |
| mmcv-full | 1.7.2 |
| mmdet | 2.28.2 |
| mmpose | 0.24.0 |
| パッケージ管理 | uv |

### ~~6.2 選択肢A: MMTracking（mmtrack）~~ 不採用

> 2026-03-30: BoxMOT + Deep OC-SORTの発見により不採用。理由: PyTorch 2.11.0互換性リスク大、実質EOL、DeepSORTよりDeep OC-SORTが高精度。

<details>
<summary>初回調査時の詳細（折りたたみ）</summary>

**概要**: OpenMMLab公式のトラッキングパッケージ。ViTPoseリポジトリ内にデモスクリプトと設定ファイルが用意されている。

**リポジトリ内の既存資産**:
- デモスクリプト（呼び出し側のみ）: `demo/top_down_pose_tracking_demo_with_mmtracking.py`
- DeepSORT設定ファイル: `demo/mmtracking_cfg/deepsort_faster-rcnn_fpn_4e_mot17-private-half.py`
- **DeepSORTの実装本体は含まれていない**。`mmtrack` パッケージに依存しており、現環境にはインストールされていない

**現環境との互換性**:

| 依存 | MMTracking要件 | 現環境 | 判定 |
|------|---------------|--------|------|
| Python | >=3.6 | 3.10.16 | OK |
| PyTorch | >=1.3 | 2.11.0+cu128 | **リスク大** |
| mmcv-full | >=1.3.17, <2.0.0 | 1.7.2 | OK |
| mmdet | >=2.19.1, <3.0.0 | 2.28.2 | OK |

</details>

### ~~6.3 選択肢B: deep-sort-realtime（スタンドアロンDeepSORT）~~ 不採用

> 2026-03-30: BoxMOT + Deep OC-SORTの発見により不採用。理由: DeepSORTよりDeep OC-SORTが高精度、最終更新2023年で停止。

<details>
<summary>初回調査時の詳細（折りたたみ）</summary>

**概要**: MMTrackingに依存しないスタンドアロンのDeepSORT実装。PyPIからインストール可能。

**インストール**: `uv pip install deep-sort-realtime`

**依存パッケージ**: NumPy, SciPy, OpenCV（すべて現環境に既存）。

**Re-IDモデル**: MobileNetV2（デフォルト、重み同梱）

</details>

### 6.4 採用: BoxMOT + Deep OC-SORT（2026-03-30 決定）

**概要**: 複数のSOTAトラッカーをプラグイン形式で利用できるパッケージ。Deep OC-SORTを使用する。

**インストール**: `uv pip install boxmot`

**依存パッケージ**: numpy, opencv-python>=4.7.0, scikit-learn>=1.3.0, filterpy>=1.4.5, lapx>=0.5.5, gdown, huggingface-hub。**OpenMMLab依存は一切なし**。

**現環境との互換性**:

| 項目 | BoxMOT要件 | 現環境 | 判定 |
|------|-----------|--------|------|
| Python | >=3.9, <3.13 | 3.10.16 | **OK** |
| PyTorch | >=2.2.1, <3.0.0 | 2.11.0+cu128 | **OK** |

**Re-IDモデル**: OSNet (osnet_x0_25_msmt17) がデフォルト。初回使用時に自動ダウンロード。2.2Mパラメータの軽量モデル。

**選択肢の最終比較**:

| | PyTorch互換性 | トラッキング精度 | 遮蔽耐性 | インストール | メンテナンス | OpenMMLab依存 |
|--|:--:|:--:|:--:|:--:|:--:|:--:|
| MMTracking | リスク大 | DeepSORT相当 | 中 | 困難（EOL） | EOL | あり |
| deep-sort-realtime | OK | DeepSORT | 中 | 簡単 | 2023年停止 | なし |
| **BoxMOT + DeepOCSORT** | **OK** | **Deep OC-SORT（SOTA）** | **高** | **簡単** | **活発** | **なし** |

## 7. 依存パッケージまとめ

| パッケージ | 用途 | インストール方法 |
|-----------|------|----------------|
| boxmot | Deep OC-SORT実装本体 + 複数トラッカー対応 | `uv pip install boxmot` |
| Re-IDモデル (OSNet) | 人物再同定モデル | 初回使用時に自動ダウンロード |

## 8. リスクと対策

| リスク | 影響 | 対策 |
|--------|------|------|
| Re-IDが病室環境で精度不足 | 見切れ後の再同定失敗 | BoxMOT内の他Re-IDモデル（CLIPReID等）に変更、または他トラッカー（StrongSORT, BoTSORT）を試す |
| GPU メモリ不足 | Re-IDモデル追加でOOM | OSNetは2.2Mパラメータで軽量。問題が出ればCPU推論（`device='cpu'`）に切り替え |
| 処理速度低下 | パイプライン全体が遅くなる | Re-ID推論のバッチ化、またはfp16有効化（デフォルトで対応） |
| AGPL-3.0ライセンス | サービス提供時にソース公開義務 | 研究・社内利用では問題なし。外部サービス化時に再検討 |

## 9. 備考

- 現在の計算機はViTPoseの2Dキーポイント推定でGPUが飽和しているため、技術検証（Phase 5A）は推定が動いていない時間帯に行う必要がある
- 1時間動画の処理時間は現状で未計測。トラッキング追加による処理時間増加も検証項目に含める
