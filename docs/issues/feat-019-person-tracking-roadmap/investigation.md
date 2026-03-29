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

**結論**: 要件を満たす唯一の手法。ただしRe-IDの病室環境での精度は技術検証が必要。

### 3.4 手法比較まとめ

| | 見切れ数秒 | 2人接近 | 遮蔽 | 実装コスト | 追加依存 | 判定 |
|--|:--:|:--:|:--:|:--:|:--:|:--:|
| IoU (MMPose内蔵) | NG | NG | 弱 | ゼロ | なし | 不採用 |
| OKS (MMPose内蔵) | NG | 中 | やや弱 | ほぼゼロ | なし | 不採用 |
| ByteTrack | NG | 良 | 良 | 中 | scipy | 単独では不足 |
| **DeepSORT** | **OK** | **最良** | **良** | **高** | **mmtrack** | **採用候補** |

## 4. 現在のパイプラインとの統合ポイント

### 4.1 現在のパイプライン構成

```
Faster R-CNN (人物検出)
    ↓ person_results (bbox)
ViTPose++ WholeBody (133点推定)
ViTPose++ AIC (14点推定)
    ↓ wb_results, aic_results
merge_to_halpe26 (結合)
    ↓ all_halpe26 (26点)
halpe26_to_openpose_json (JSON出力)
    ↓ OpenPose JSON (person_id: [-1])
```

### 4.2 トラッキング統合後の構成（案）

```
[案A: MMTracking統合 — 検出とトラッキングを一体化]

DeepSORT (人物検出 + トラッキング)
    ↓ person_results (bbox + track_id)
ViTPose++ WholeBody (133点推定)
ViTPose++ AIC (14点推定)
    ↓ wb_results, aic_results
merge_to_halpe26 (結合)
    ↓ all_halpe26 (26点) + track_ids
halpe26_to_openpose_json (JSON出力)
    ↓ OpenPose JSON (person_id: [track_id])
```

```
[案B: 後付けトラッキング — 既存パイプラインを変えず、結果にトラッキングを適用]

Faster R-CNN (人物検出) ← 既存のまま
    ↓ person_results (bbox)
ViTPose++ WholeBody / AIC ← 既存のまま
    ↓ all_halpe26 (26点)
DeepSORT (bbox + Re-ID特徴量でトラッキング)
    ↓ track_ids
halpe26_to_openpose_json (JSON出力)
    ↓ OpenPose JSON (person_id: [track_id])
```

**案Aの利点**: MMTrackingのデモスクリプトがそのまま参考になる。検出とトラッキングが一体なのでID割り当てが自然。
**案Aの欠点**: 現在のFaster R-CNNをDeepSORT内蔵の検出器に置き換える必要がある。パイプライン構成が大きく変わる。

**案Bの利点**: 既存パイプラインを変更せず、トラッキングを後付けできる。段階的導入しやすい。
**案Bの欠点**: 検出とトラッキングが分離しており、Kalmanフィルタの予測を検出に反映できない。

**推奨**: 案A（MMTracking統合）。リポジトリ内に既存のデモスクリプトとDeepSORT設定があり、参考実装が豊富。

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

### Phase 5A: 技術検証

| 順番 | 案件案 | 概要 | 依存 | 目的 |
|:--:|--------|------|------|------|
| 1 | MMTracking環境構築 | mmtrackのインストール、バージョン互換性確認、DeepSORTデモの動作確認 | - | MMTrackingが現環境で動くか確認 |
| 2 | DeepSORT病室動画検証 | 病室動画（testdata/cam05520129.mp4）でDeepSORTを実行し、トラッキング精度を目視確認 | 1 | Re-IDが病室環境で機能するか確認 |
| 3 | 見切れ再同定の検証 | 患者が見切れる場面でIDが維持されるか確認。num_frames_retain等のパラメータ調整 | 2 | 数秒の見切れ後の再同定精度を確認 |

**Phase 5Aの判定基準**:
- DeepSORTが病室動画で実用的なトラッキング精度を示す → Phase 5Bへ進む
- 精度不足 → ViTPose以外の方法を検討（本ロードマップ外）

### Phase 5B: パイプライン統合

| 順番 | 案件案 | 概要 | 依存 | 目的 |
|:--:|--------|------|------|------|
| 4 | DeepSORT + HALPE 26統合パイプライン | 既存の `run_halpe26_pipeline.py` にDeepSORTトラッキングを統合。人物検出をDeepSORT経由に切り替え | 3 | トラッキングIDをキーポイントに紐付ける |
| 5 | JSONにトラッキングID記録 | `halpe26_to_openpose_json()` の `person_id` にtrack_idを記録 | 4 | トラッキング結果をJSON出力に反映 |
| 6 | トラッキング付き動画可視化 | 可視化動画にトラッキングID（人物ごとに色分け）を描画 | 4 | トラッキング結果の目視確認手段 |

### Phase 5C: 後処理（患者特定）

| 順番 | 案件案 | 概要 | 依存 | 目的 |
|:--:|--------|------|------|------|
| 7 | 患者ID特定スクリプト | JSON群からトラッキングIDごとの出現フレーム数を集計し、最長時間のIDを患者として出力 | 5 | 患者のトラッキングIDを自動特定 |
| 8 | 患者フィルタリング | 指定したトラッキングIDのキーポイントのみを抽出したJSONを出力 | 7 | 患者のキーポイントのみを後段に渡す |

### 実装順序の根拠

- **Phase 5A（技術検証）を最優先**: DeepSORTの病室動画での精度が未知であり、精度不足なら以降のPhaseは不要。最小コストで判断材料を得る
- **Phase 5B（統合）は検証後**: 技術検証で精度が確認できてから統合に着手する。案件4が最も工数が大きい
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

### 6.2 選択肢A: MMTracking（mmtrack）

**概要**: OpenMMLab公式のトラッキングパッケージ。ViTPoseリポジトリ内にデモスクリプトと設定ファイルが用意されている。

**リポジトリ内の既存資産**:
- デモスクリプト（呼び出し側のみ）: `demo/top_down_pose_tracking_demo_with_mmtracking.py`
- DeepSORT設定ファイル: `demo/mmtracking_cfg/deepsort_faster-rcnn_fpn_4e_mot17-private-half.py`
- **DeepSORTの実装本体は含まれていない**。`mmtrack` パッケージに依存しており、現環境にはインストールされていない

**インストールに必要なもの**:
- `mmtrack` パッケージ（MMTracking v0.14.0、最終リリース2022年）
- Re-IDモデルチェックポイント: `tracktor_reid_r50_iter25245-a452f51f.pth`（ResNet50ベース、推定100MB前後）
  - URL: `https://download.openmmlab.com/mmtracking/mot/reid/tracktor_reid_r50_iter25245-a452f51f.pth`

**現環境との互換性**:

| 依存 | MMTracking要件 | 現環境 | 判定 |
|------|---------------|--------|------|
| Python | >=3.6 | 3.10.16 | OK |
| PyTorch | >=1.3 | 2.11.0+cu128 | **リスク大** |
| mmcv-full | >=1.3.17, <2.0.0 | 1.7.2 | OK |
| mmdet | >=2.19.1, <3.0.0 | 2.28.2 | OK |

**PyTorch互換性リスク**: MMTracking v0.14.0は2022年のコードでPyTorch 1.x〜2.0程度を想定。torch 2.11.0での動作は保証されない。ただし、同じOpenMMLab v1のmmpose 0.24.0 + mmcv-full 1.7.2が現環境で動作しているため、動く可能性もある。試してみないと分からないレベル。

**メンテナンス状況**: 最終リリースは2022年（v0.14.0）。OpenMMLab v2（MMEngine ベース）への移行が完了しており、v1系は実質EOL。新規バグ修正・PyTorch対応は期待できない。

**利点**:
- リポジトリ内にデモスクリプトと設定ファイルが揃っている
- MMPoseとの統合方法が確立されている（`inference_mot()` → `process_mmtracking_results()` → `inference_top_down_pose_model()`）

**欠点**:
- PyTorch 2.11.0での動作が未知
- 実質EOLで長期的なメンテナンスが期待できない
- Re-IDモデルはMOT17（街中の歩行者）で学習されており、病室環境での精度は未知

### 6.3 選択肢B: deep-sort-realtime（スタンドアロンDeepSORT）

**概要**: MMTrackingに依存しないスタンドアロンのDeepSORT実装。PyPIからインストール可能。

**インストール**: `uv pip install deep-sort-realtime`

**依存パッケージ**: NumPy, SciPy, OpenCV（すべて現環境に既存）。PyTorch/TorchvisionはRe-IDのembedder使用時のみ必要（オプション）。

**Re-IDモデル**:
- MobileNetV2（デフォルト、重み同梱。追加ダウンロード不要）
- Torchreid（osnet_ain_x1_0、重み同梱）
- 外部embedding対応: `tracker.update_tracks(bbs, embeds=embeds)` で独自embedder使用可能

**メンテナンス状況**: 最終更新2023年。安定しており広く利用されている。

**現環境との互換性**: 高い。mmcv/mmdet/mmposeに一切依存しない。既存の検出結果（bbox）をそのまま渡せる設計。

**利点**:
- インストールが簡単で、現環境との互換性問題がほぼない
- Re-IDモデルが同梱されており、追加ダウンロード不要
- mmcv/mmdet/mmposeに依存しないため、OpenMMLab v1のEOLに影響されない

**欠点**:
- MMPoseとの統合コードは自分で書く必要がある（ただしAPIはシンプル）
- Re-IDモデル（MobileNetV2）はMMTrackingのResNet50より軽量だが精度は劣る可能性
- 最終更新2023年

### 6.4 その他の選択肢

| パッケージ | Re-ID | 依存の軽さ | メンテナンス | 備考 |
|-----------|:--:|:--:|:--:|------|
| **Norfair** | 対応可（embedder自前） | 最軽量 | 2025年更新あり | 柔軟だがRe-IDモデルは自分で用意する必要がある |
| **bytetracker** | なし | 最軽量 | - | Re-IDなしのため見切れ後の再同定は不可。要件を満たさない |
| **nwojke/deep_sort** | あり（TF依存） | 重い | 長期停止 | TensorFlow依存が不便。現環境にそぐわない |

### 6.5 選択肢の比較まとめ

| | PyTorch互換性 | Re-ID | 統合コード | メンテナンス | インストール容易性 |
|--|:--:|:--:|:--:|:--:|:--:|
| MMTracking | **リスク大** | ResNet50（高精度） | 既存デモあり | EOL | 中 |
| deep-sort-realtime | **問題なし** | MobileNetV2（同梱） | 自作が必要 | 2023年停止 | 簡単 |
| Norfair | **問題なし** | 自前で用意 | 自作が必要 | 活発 | 簡単 |

### 6.6 環境構築の推奨方針

**Phase 5A（技術検証）では以下の順で試す**:

1. **まずMMTrackingを試す**: リポジトリ内にデモ・設定が揃っており、動けば最も統合が容易。`uv pip install mmtrack` でインストールし、PyTorch 2.11.0で動作するか確認する
2. **MMTrackingが非互換なら deep-sort-realtime に切り替え**: インストールは確実に成功する。統合コードの自作が必要だが、APIがシンプルなので工数は中程度

## 7. 依存パッケージまとめ

**DeepSORTの実装は本リポジトリ（ViTPose）には含まれていない。** リポジトリ内にあるのはデモスクリプト（呼び出し側）と設定ファイル（パラメータ定義）のみ。

### MMTracking経由の場合

| パッケージ | 用途 | インストール方法 |
|-----------|------|----------------|
| mmtrack (v0.14.0) | DeepSORT実装本体 | `uv pip install mmtrack` |
| Re-IDチェックポイント | 人物再同定モデル | OpenMMLab公式URLからダウンロード |

### deep-sort-realtime経由の場合

| パッケージ | 用途 | インストール方法 |
|-----------|------|----------------|
| deep-sort-realtime | DeepSORT実装本体 + Re-IDモデル同梱 | `uv pip install deep-sort-realtime` |

## 8. リスクと対策

| リスク | 影響 | 対策 |
|--------|------|------|
| MMTrackingがPyTorch 2.11.0と非互換 | Phase 5A失敗 | deep-sort-realtimeに切り替え |
| Re-IDが病室環境で精度不足 | 見切れ後の再同定失敗 | Re-IDモデルのfine-tuning、またはByteTrack + 簡易ルールへ切り替え |
| GPU メモリ不足 | Re-IDモデル追加でOOM | 2Dキーポイント推定とトラッキングを分離実行（オフライン処理） |
| 処理速度低下 | パイプライン全体が遅くなる | Re-ID推論のバッチ化、または推論済み結果へのオフライントラッキング |

## 9. 備考

- 現在の計算機はViTPoseの2Dキーポイント推定でGPUが飽和しているため、技術検証（Phase 5A）は推定が動いていない時間帯に行う必要がある
- 1時間動画の処理時間は現状で未計測。トラッキング追加による処理時間増加も検証項目に含める
