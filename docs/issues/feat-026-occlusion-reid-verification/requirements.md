# feat-026: 見切れ再同定の検証 要求仕様書

feat-028（JSONにトラッキングID記録）およびfeat-029（トラッキング付き動画可視化）は2026-04-07に完了済み。FR-001〜FR-004は実装完了・テスト済み。FR-005（目視検証）を追加し、stable_id付きJSONと`visualize_tracking.py`を使った検証手法を定義する。

## 1.1 プロジェクト概要

### 何を作るのか
camSony1_L（長尺動画、321,239フレーム、約178分）でカスタムRe-ID（遅延マッチN=180）を実行し、見切れ再同定の精度を検証するための長尺動画対応スクリプト。既存の `test_custom_reid_offline.py` を長尺動画向けに拡張する。

### 前提条件
- feat-028（JSONにトラッキングID記録）が完了していること。検証にはJSONに保存されたstable_idを使い、stable_idごとのスケルトン可視化で目視確認を行う

### なぜ作るのか
feat-022ではcamSony1_S（900フレーム、見切れ区間のクリップ）で検証したが、以下の観点が未検証である:
1. **同一人物の再同定**: 見切れ後に戻ってきた同一人物に同じstable_idを割り当てるか
2. **別人物の誤同定防止**: 異なる人物（看護師等）に患者と同じstable_idを割り当てないか
3. **長時間安定性**: 3時間の動画で stable_id の管理が破綻しないか

camSony1_Lは同一人物の見切れと複数人物の出入りを含む動画であり、上記3点の検証に適している。

### 誰が使うのか
ViTPose パイプラインの開発・検証を行う研究者（ユーザー自身）。CLI スクリプトとしてオフライン検証に使用する。

### どこで使うのか
GPU 搭載ワークステーション（NVIDIA RTX 5060 Ti, Ubuntu Linux）。Python 3.10.16, uv 管理環境。

---

## 1.2 用語定義

| 用語 | 定義 |
|------|------|
| track_id | Deep OC-SORT が各フレームで割り当てる ID。見切れ復帰後は新しい ID が付与される |
| stable_id | カスタム Re-ID が維持する安定 ID。見切れ後も同一人物には同じ ID を付与する |
| 見切れ | 人物が画面外に出て検出・追跡が途切れる状態 |
| 再同定 | 見切れ後に再出現した人物を以前の stable_id に紐づけること |
| 誤同定 | 異なる人物に同じ stable_id を誤って割り当てること |
| Re-IDイベント | track_id の出現・消失・再同定に関するイベントの総称 |
| 即座マッチ | 新 track_id 出現時に消失 ID との類似度が閾値（0.3）を超え、即座に stable_id を引き継ぐこと |
| 遅延マッチ | 即座マッチ失敗後、最大180フレームの間 EMA 蓄積しながら再試行し、マッチに成功すること |
| タイムアウト | 遅延マッチが180フレーム経過しても成功せず、仮 stable_id が確定すること |

---

## 1.3 機能要求一覧

### FR-001: 長尺動画向け出力調整

- **機能名**: 進捗ログの出力間隔制御
- **概要**: 321Kフレームの処理中に適切な間隔で進捗を出力する
- **変更対象**: `test_custom_reid_offline.py`
- **入力**: 既存の CLI 引数に加え、以下を追加:
  - `--print-interval N`: 進捗ログの出力間隔（フレーム数）。デフォルト: 10（従来互換）。既存のハードコード `frame_idx % 10 == 0` をこの引数で置き換える。camSony1_L では `3000` を推奨する
  - `--no-sim-log`: Re-ID類似度ログ（FR-008出力）を抑制するフラグ。指定時は `Re-ID sim:` 行を出力しない。デフォルト: 抑制しない（従来互換）
- **出力（標準出力）**: `--print-interval` で指定した間隔で以下を出力:
  `Processing frame NNNNNN/TTTTTT (PP.P%): track_ids=[...], stable_ids={...}`
  - `NNNNNN`: 現在のフレーム番号（6桁ゼロ埋め `{frame_idx:06d}`）。既存の4桁（`{frame_idx:04d}`）から変更
  - `TTTTTT`: 総フレーム数（動画から `CAP_PROP_FRAME_COUNT` で取得）。取得できない場合（0以下を返す場合）は `?` を表示し、パーセンテージは出力しない
- **受け入れ基準**:
  - `--print-interval 3000` 指定時、321Kフレームの動画で約107行の進捗ログが出力されること
  - `--no-sim-log` 指定時、`Re-ID sim:` 行が一切出力されないこと
  - 引数未指定時（デフォルト10）、出力間隔は従来と同一。フォーマットは総フレーム数とパーセンテージが追加され、フレーム番号が6桁ゼロ埋めに変わる。出力される情報（track_ids, stable_ids）と間隔は維持される

### FR-002: Re-IDイベント収集

- **機能名**: Re-IDイベントの構造化記録
- **概要**: 処理中に発生する Re-ID 関連イベントをメモリ上に記録し、FR-003のサマリーレポートに使用する
- **変更対象**: `test_custom_reid_offline.py`
- **記録対象イベント**:
  1. **消失（disappear）**: track_id が前フレームから消えた。記録: frame_idx, track_id, stable_id
  2. **出現（appear）**: 新しい track_id が出現した。記録: frame_idx, track_id, assigned_stable_id, match_type（"instant" / "new" / "pending"）
     - "instant": 即座マッチ成功（消失IDのstable_idを引き継ぎ）
     - "new": 新規stable_id発番（`_disappeared` が空のため保留なし）。典型的なシナリオは動画冒頭での最初の人物出現
     - "pending": 仮stable_id発番で遅延マッチ保留中（`_disappeared` に消失IDがあるが即座マッチ失敗）
  3. **遅延マッチ成功（delayed_match）**: 遅延マッチが成功した。記録: frame_idx, track_id, old_stable_id（仮）, new_stable_id（再割り当て先）, offset（出現からのフレーム数）
  4. **遅延マッチタイムアウト（delayed_timeout）**: 遅延マッチが180フレーム経過しても成功しなかった。記録: frame_idx, track_id, stable_id（確定した仮ID）
- **イベント検出方法**:
  - **消失**: テストスクリプト側で前フレームの track_id 集合と現フレームの track_id 集合の差分から検出する。消失した track_id に対応する stable_id は、前フレームの `reid.update()` 戻り値（`prev_stable_map`）から取得する。テストスクリプトは毎フレーム末尾で `prev_stable_map = dict(stable_ids)` と `prev_track_set = set(track_ids)` を更新し、次フレームの差分検出で使用する。保留中（pending）の track_id が消失した場合も、通常の disappear イベントとして記録する
  - **出現・match_type判定**: テストスクリプト側で track_id 集合の差分から新規 track_id を検出する。match_type の判定は FR-004 の `last_events` のみを使用する（`update()` 内で `_disappeared` の状態が変化するため、`update()` 完了後に外部から `_disappeared` を参照して判定することはしない）。`last_events` に対応する track_id のイベントが `instant_match` なら "instant"、`new_id` なら "new"、`pending` なら "pending" と判定する
  - **遅延マッチ成功・タイムアウト**: FR-004 の `last_events` から `delayed_match` / `delayed_timeout` イベントを取得する
- **メモリ使用量**: 各イベントは辞書で保持する。321Kフレームで最大数百件程度のイベントが見込まれるため、メモリ問題は発生しない
- **受け入れ基準**:
  - camSony1_L.mp4（321,239フレーム）の全フレーム処理で、消失・出現・遅延マッチ・タイムアウトの各イベントが記録されること
  - 全イベントがFR-003のサマリーで出力されること

### FR-003: Re-IDサマリーレポート

- **機能名**: 見切れ再同定の結果サマリー
- **概要**: 処理完了後に Re-ID イベントの統計情報と時系列を出力する
- **変更対象**: `test_custom_reid_offline.py`
- **出力（標準出力）**: 既存の `=== Re-ID Summary ===` の後に以下を追加出力する:

  ```
  === Re-ID Event Log ===
  [disappear] frame=000150 track_id=1 stable_id=1
  [appear]    frame=000151 track_id=2 stable_id=2 (instant match from sid=1)
  [appear]    frame=000151 track_id=3 stable_id=3 (new)
  [appear]    frame=000151 track_id=4 stable_id=4 (pending)
  [delayed]   frame=000179 track_id=4 old_sid=4 new_sid=1 (offset=28)
  [timeout]   frame=000331 track_id=5 stable_id=5 (confirmed)
  ...

  === Re-ID Statistics ===
  Total appear events: N
    Instant match: N
    New (no disappeared): N
    New (pending → delayed match): N
    New (pending → timeout): N
    New (pending → disappeared): N
  Total disappear events: N
  Delayed match success rate: N/M (PP.P%)
  Unique stable IDs (final): N
  Active stable IDs at last frame: {sid: track_id, ...}
  ```

- **各項目の定義**:
  - `Total appear events`: 新 track_id の出現回数の合計
  - `Instant match`: 出現時に即座マッチが成功した回数
  - `New (no disappeared)`: 消失 ID がなく新規 stable_id が発番された回数
  - `New (pending → delayed match)`: pending の appear イベントのうち、同一 track_id の `delayed_match` イベントが後続フレームで発生したもののカウント
  - `New (pending → timeout)`: pending の appear イベントのうち、同一 track_id の `delayed_timeout` イベントが後続フレームで発生したもののカウント
  - `New (pending → disappeared)`: pending の appear イベントのうち、`delayed_match` も `delayed_timeout` も発生せず track_id が消失したもののカウント（保留中消失）。`Total appear events` の内訳合計は `Instant match` + `New (no disappeared)` + `New (pending → delayed match)` + `New (pending → timeout)` + `New (pending → disappeared)` と一致する
  - `Total disappear events`: track_id が消失した回数の合計
  - `Delayed match success rate`: 遅延マッチ対象のうち成功した割合。分母は `pending → delayed match` + `pending → timeout` の合計。保留中消失は分母に含まない（delayed/timeout イベントが発生しないため）。分母が0の場合は `0/0 (N/A)` と表示
  - `Unique stable IDs (final)`: 最終フレーム時点で `update()` 戻り値の values と `reid.disappeared` の keys のユニオンから算出したユニーク数。遅延マッチ成功時に仮 stable_id は `_active_stable` から新しい stable_id に置き換わるため、自動的に除外される。ただし、保留中に消失した track_id の仮 stable_id は `_disappeared` のキーとして残るため、`Unique stable IDs (final)` に含まれる
  - `Active stable IDs at last frame`: 最終フレームでアクティブな {stable_id: track_id} の辞書（`update()` 戻り値の逆引き）
- **Re-ID Event Log の出力順**: フレーム番号の昇順。同一フレーム内では disappear → appear → delayed → timeout の固定順序
- **受け入れ基準**:
  - camSony1_L.mp4 で処理完了後、上記フォーマットのサマリーが出力されること
  - Event Log の各行から、いつ・誰が・何をしたか（消失/出現/再同定）が読み取れること

### FR-004: CustomReIDクラスへのイベント通知機能追加

- **機能名**: Re-IDイベントの外部通知
- **概要**: `CustomReID.update()` 内で発生した全イベント（新規ID発番、即座マッチ、保留開始、遅延マッチ成功、タイムアウト）をテストスクリプトから取得可能にする。`update()` 内で `_disappeared` の状態が変化するため（先行する即座マッチで消費される等）、イベントの記録は状態変化が起きた時点で `update()` 内部で行う
- **変更対象**: `scripts/custom_reid.py`
- **追加インターフェース**:
  - `last_events` プロパティ: 直前の `update()` 呼び出しで発生したイベントのリスト。戻り値型: `list[dict]`。`update()` 呼び出しごとにリセットされる
  - 各イベントの辞書形式:
    - 即座マッチ: `{"type": "instant_match", "track_id": int, "stable_id": int, "from_disappeared_sid": int, "frame_idx": int}`
    - 新規ID発番: `{"type": "new_id", "track_id": int, "stable_id": int, "frame_idx": int}` — `_disappeared` が空のため保留なしで新 stable_id を発番
    - 保留開始: `{"type": "pending", "track_id": int, "stable_id": int, "frame_idx": int}` — `_disappeared` に消失IDがあるが即座マッチ失敗、遅延マッチ保留状態に入る
    - 遅延マッチ成功: `{"type": "delayed_match", "track_id": int, "old_stable_id": int, "new_stable_id": int, "offset": int, "frame_idx": int}`
    - タイムアウト: `{"type": "delayed_timeout", "track_id": int, "stable_id": int, "frame_idx": int}`
- **既存動作への影響**: `update()` の戻り値（`dict[int, int]`）は変更しない。print文（`Delayed Re-ID:` 等）も維持する
- **受け入れ基準**:
  - `reid.update()` 呼び出し後に `reid.last_events` でイベントを取得できること
  - 次の `update()` 呼び出しで `last_events` がリセット（空リスト）されること
  - イベントが発生しないフレームでは空リストが返ること

---

## 1.4 非機能要求

- **処理速度**: 321Kフレームの処理が完了すること。下限FPSは設けない。最終サマリーに処理時間とFPSを出力する（既存機能）
- **メモリ使用量**: 321Kフレームの処理中にメモリ不足で異常終了しないこと。イベントログは最大数百件程度のため問題ない。`_disappeared` 辞書は同一セッション中に削除しない仕様（feat-022 FR-006）のため、登場人物数に比例するのみ
- **対応環境**: Ubuntu Linux、Python 3.10.16、uv 管理環境、NVIDIA RTX 5060 Ti
- **信頼性**: 321,239フレームの全処理で途中クラッシュなし

---

## 1.5 制約条件

- **feat-028（JSONにトラッキングID記録）が完了していること**: 検証にはJSONに保存されたstable_idとキーポイントの対応が必要。統計サマリーのみでは検証不十分
- `custom_reid.py` への変更は FR-004 の `last_events` プロパティと `_last_events` イベント記録の追加のみ。既存ロジック（feat-022 FR-001〜FR-009）は変更しない
- 新規ライブラリの追加は禁止（既存環境の OpenCV、NumPy、BoxMOT のみ使用）
- 321,239フレームは6桁ゼロ埋め（最大999,999）の範囲内であるため、既存の JSON ファイル名パターン `_(\d{6})\.json$` に変更は不要
- テストデータ:
  - 動画: `experiments/input/camSony1_L.mp4`（321,239フレーム、30fps、約178分）
  - JSON: `experiments/results/camSony1_L_json/`（321,239ファイル）
  - 実行例: `uv run python scripts/test_custom_reid_offline.py --video experiments/input/camSony1_L.mp4 --json-dir experiments/results/camSony1_L_json/ --print-interval 3000 --no-sim-log`

### FR-005: 目視検証

- **機能名**: stable_idごとのスケルトン可視化による目視検証
- **概要**: `visualize_tracking.py`（feat-029）を使い、特定のstable_idのスケルトンを動画上に描画して、見切れ前後で同一人物に同じstable_idが維持されているか、異なる人物に同じstable_idが割り当てられていないかを目視で確認する
- **入力**:
  - stable_id付きJSON: `experiments/results/camSony1_L_reid_json/`（321,239ファイル）
  - 元動画: `experiments/input/camSony1_L.mp4`
  - 検証対象stable_id: 統計データから選定（下記参照）
- **検証対象の選定基準**:
  - 出現フレーム数が多い上位5つのstable_id（長期間出現する人物の安定性確認）
  - stable_id=1（全期間出現、362回の出現/消失イベント、患者と推定）
  - stable_id=-1を含む全体モード（未割当人物の確認）
- **検証手順**:
  1. **個別検証**: `visualize_tracking.py --ids {sid}` で上位stable_idを個別に描画し、見切れ前後で同一人物のスケルトンが同じ色で表示されるか確認する
  2. **全体検証**: `visualize_tracking.py`（全体モード）で全stable_idを色分け描画し、同一フレーム内で異なる人物が異なる色で表示されるか確認する
  3. **見切れ区間の重点確認**: FR-003のRe-ID Event Logからstable_id=1の消失→再出現の時系列を確認し、代表的な見切れ区間を選定して重点的に確認する
- **検証の判定基準**:
  - **合格**: 見切れ後の再出現時に同一人物が同じstable_idで描画される。異なる人物に同一stable_idが割り当てられていない
  - **不合格**: 見切れ後に別のstable_idが割り当てられる、または異なる人物が同じstable_idで描画される
- **出力**: 検証結果をユーザーが目視で判定する。スクリプトによる自動判定は行わない
- **受け入れ基準**:
  - 上位5つのstable_idの個別描画動画が生成されること
  - 全体モードの描画動画が生成されること
  - ユーザーが目視で合否判定できること

---

## 1.6 優先順位

| ID | 機能名 | MoSCoW | 実装状態 |
|----|--------|--------|----------|
| FR-001 | 長尺動画向け出力調整 | Must | 実装済み |
| FR-002 | Re-IDイベント収集 | Must | 実装済み |
| FR-003 | Re-IDサマリーレポート | Must | 実装済み |
| FR-004 | CustomReIDクラスへのイベント通知機能追加 | Must | 実装済み |
| FR-005 | 目視検証 | Must | 未実施 |

**MVP**: FR-001〜FR-005 すべて
