# feat-022 イテレーション2: カスタムRe-IDモジュール 要求仕様書

## 1.1 プロジェクト概要

### 何を作るのか
室内固定カメラ映像で人物が画面外に出た後（最低1分）に再登場した際、同一IDで追跡を継続するカスタムRe-IDモジュール。ViTPose HALPE 26キーポイントと HSV 色ヒストグラムを使い、トラッカー後段で独立して動作する。

### データ処理の流れ
本モジュールは ViTPose/MMPose によるキーポイント推定を行わない。既存パイプライン（`run_halpe26_pipeline.py` 等）が出力済みの HALPE 26 OpenPose JSON と動画ファイルを入力として受け取り、以下の順序で処理する:

1. JSON から人物の bbox とキーポイントを読み込む（推論なし）
2. bbox を検出結果として Deep OC-SORT に渡し、track_id を取得する
3. track_id の bbox と JSON の bbox を IoU で対応付け、キーポイントを取得する
4. キーポイントから頭部・上半身領域を切り出し、HSV ヒストグラムで特徴量を計算する
5. 消失 ID の特徴量と照合し、stable_id（見切れ後も維持される ID）を決定する

### なぜ作るのか
Deep OC-SORT の内蔵 Re-ID（OSNet/MSMT17）が室内ドメインで機能しないことがイテレーション1で確認された。OSNet は街中歩行者データセットで訓練されており、臥位対象・病院着・低解像度の室内環境とドメインが大きく異なるため、パラメータ調整では解決できない。

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
| 消失 ID | 前フレームにあったが現フレームにない track_id に対応する stable_id |
| 特徴量 | 頭部・上半身の各領域から計算した HSV ヒストグラム（H + S チャネルのみ） |
| EMA | 指数移動平均。α=0.1 で毎フレーム更新する（新フレームの影響 10%、過去の蓄積 90%） |
| HALPE 26 | 本パイプラインで出力する 26 キーポイント形式 |
| 見切れ | 人物が画面外に出て検出・追跡が途切れる状態 |
| 消去法 | 消失 ID が 1 件のみの場合に使う手法。類似度 > 0.3 を満たせば同一人物と判定する。満たさなければ新規人物として扱う |
| ヒストグラム交差 | `sum(min(h1[i], h2[i]))` で計算する類似度指標。正規化済みヒストグラムで範囲は 0〜1 |
| confidence 閾値 | キーポイントの可視判定に使用する閾値。値は 0.3（コンストラクタ引数 `kpt_conf_thr` で変更可能） |
| 類似度閾値 | Re-ID 判定で同一人物と見なす最低類似度。値は 0.3（コンストラクタ引数 `sim_threshold` で変更可能） |

---

## 1.3 機能要求一覧

### FR-001: 頭部領域抽出

- **機能名**: HALPE 26 キーポイントによる頭部領域切り出し
- **概要**: 顔・頭部に対応するキーポイントから頭部画像領域を切り出す
- **入力**:
  - 動画フレーム（numpy.ndarray, shape=(H, W, 3), dtype=uint8, BGR 色空間）
  - HALPE 26 キーポイント（numpy.ndarray, shape=(26, 3), [x, y, confidence]）
- **出力**: 頭部領域画像（numpy.ndarray, BGR）または None
- **処理**: インデックス {0:Nose, 1:LEye, 2:REye, 3:LEar, 4:REar, 17:Head, 18:Neck} のうち confidence > 0.3 のキーポイントを使用。それらの bounding box（min_x, min_y, max_x, max_y）を計算し、上下左右 20px 拡張する（固定値。解像度による動的変更は行わない。コンストラクタ引数 `head_expand_px` で変更可能）。画面端でクリップした後、フレームから切り出す。
- **受け入れ基準**:
  - confidence > 0.3 のキーポイントが 1 点以上あれば領域を返す
  - confidence > 0.3 のキーポイントが 0 点ならば None を返す
  - 拡張・クリップ後に x2 <= x1 または y2 <= y1 となる場合は None を返す。判定は float 値のまま行う。float 判定で x2 > x1 かつ y2 > y1 を通過した場合でも、差が 1.0 未満なら int 変換後に幅 0 が生じ得る。この場合は空配列となるが、FR-003 で合計 < 1e-6 により None を返すため後続処理に影響しない
  - 切り出し後の最小サイズは設けない（1px × 1px 以上であれば有効な領域とする）。ヒストグラムの品質は FR-003 の正規化処理で担保する

### FR-002: 上半身領域抽出

- **機能名**: HALPE 26 キーポイントによる上半身領域切り出し
- **概要**: 肩・股関節に対応するキーポイントから上半身画像領域を切り出す
- **入力**:
  - 動画フレーム（numpy.ndarray, shape=(H, W, 3), dtype=uint8, BGR 色空間）
  - HALPE 26 キーポイント（numpy.ndarray, shape=(26, 3), [x, y, confidence]）
- **出力**: 上半身領域画像（numpy.ndarray, BGR）または None
- **処理**: インデックス {5:LShoulder, 6:RShoulder, 11:LHip, 12:RHip} のうち confidence > 0.3 のキーポイントを使用。それらの bounding box を計算し、画面端でクリップした後、拡張なしで切り出す。
- **受け入れ基準**:
  - confidence > 0.3 のキーポイントが 2 点以上あれば領域を返す
  - confidence > 0.3 のキーポイントが 1 点以下ならば None を返す
  - クリップ後に x2 <= x1 または y2 <= y1 となる場合は None を返す。判定は float 値のまま行う。float 判定で x2 > x1 かつ y2 > y1 を通過した場合でも、差が 1.0 未満なら int 変換後に幅 0 が生じ得る。この場合は空配列となるが、FR-003 で合計 < 1e-6 により None を返すため後続処理に影響しない。visible が 2 点で x 座標または y 座標が完全一致（float 比較で ==）する場合は x2 == x1 または y2 == y1 となるため x2 <= x1 判定で None を返す
  - 切り出し後の最小サイズは設けない（1px × 1px 以上であれば有効な領域とする）

### FR-003: HSV ヒストグラム計算

- **機能名**: 領域画像からの色特徴量計算
- **概要**: 切り出した領域画像から H + S チャネルのヒストグラムを計算する
- **入力**: 領域画像（numpy.ndarray, BGR）または None
- **出力**: ヒストグラムベクトル（numpy.ndarray, shape=(68,), dtype=float32）または None
- **処理**:
  1. BGR → HSV 変換
  2. H チャネル: 36 ビン（範囲 0-180）
  3. S チャネル: 32 ビン（範囲 0-256）
  4. H と S のヒストグラムを結合（shape=(68,)）
  5. 合計が 1.0 になるよう正規化（float32 精度での演算で可）
  6. 入力が None または合計が < 1e-6 の場合は None を返す
- **V チャネル除外理由**: 照明変化による輝度変動の影響を避けるため V は使用しない
- **受け入れ基準**:
  - 正規化後の合計値が `np.isclose(hist.sum(), 1.0, atol=1e-4)` を満たすこと（float32 精度での許容誤差）
  - 入力 None または合計 < 1e-6 では None を返す

### FR-004: EMA 特徴量更新

- **機能名**: 指数移動平均による特徴量蓄積
- **概要**: 毎フレームの特徴量を EMA で蓄積し、照明変化・ノイズの影響を平滑化する
- **入力**:
  - 既存 EMA 特徴量（PersonFeature または None（初回））
  - 新フレームの特徴量（PersonFeature）
  - α = 0.1（固定）
- **出力**: 更新後の PersonFeature
- **処理（頭部・上半身それぞれに適用）**:
  - 既存 EMA ヒストグラムが None（初回）: 新フレームのヒストグラムをそのまま使用
  - 新フレームのヒストグラムが None（部位が見えない）: 既存 EMA をそのまま使用
  - 両方ある場合: `ema = 0.1 * new + 0.9 * ema`
- **受け入れ基準**: 上記 3 ケースすべてで正しい値を返す

### FR-005: Re-ID 判定

- **機能名**: 消失 ID 照合による stable_id 決定
- **概要**: 新しい track_id が出現した際、消失 ID 一覧と特徴量を比較して stable_id を決定する
- **入力**:
  - 新 ID の PersonFeature
  - 消失 ID 一覧（dict: stable_id → PersonFeature）
- **出力**: マッチした stable_id（int）または None（新規人物）
- **処理**:
  - 消失 ID が 0 件: None を返す
  - 消失 ID が 1 件（消去法）: 類似度を計算し > 0.3 なら その stable_id を返す。≤ 0.3 なら None を返す
  - 消失 ID が 2 件以上: 全 ID と類似度を計算し、最大値が > 0.3 ならその stable_id を返す。≤ 0.3 なら None を返す
- **類似度計算**: 頭部と上半身のヒストグラム交差の均等平均（重み 0.5:0.5）。比較する 2 人のうちいずれか一方でも該当部位が None であればその部位は比較不能として除外する。片方の部位のみ有効な場合、その部位のヒストグラム交差値をそのまま最終類似度とする（重み付けなし）。両部位とも比較不能なら 0.0
- **閾値 0.3 について**: 暫定値。消去法（1件）と多候補（2件以上）で閾値を共通にする理由: 実装をシンプルにするため。閾値の変更が必要な場合は別案件で対応する
- **同点処理**: 消失 ID が 2 件以上で類似度が同点の場合、stable_id の数値が最小（最初に発番された）ものを優先する
- **消去法専用閾値**: Won't（今回スコープ外）。今後の検証結果で必要になれば別途対応する
- **受け入れ基準**:
  - 3 ケース（0件・1件・2件以上）すべてで正しい判定をする
  - 新 ID の PersonFeature の head_hist・torso_hist がともに None の場合、類似度 0.0 として扱い None を返す（新規人物として発番される）

### FR-006: stable_id 状態管理

- **機能名**: フレームごとの stable_id 管理
- **概要**: track_id と stable_id のマッピング、各 ID の EMA 特徴量を管理する
- **入力**: 各フレームの track_id 一覧（list[int]）と対応するキーポイント・フレーム画像
- **出力**: `{track_id: stable_id}` の辞書（現フレームのアクティブ track_id のみ）
- **入力の前提**: `keypoints_map` は `match_by_iou`（IoU 閾値 0.5）により生成された辞書であり、キー集合は `track_ids` と一致することを前提とする。`match_by_iou` は `test_custom_reid_offline.py` に定義する関数で、Deep OC-SORT が出力する tracked BB（xyxy）と JSON people の BB（xyxy）を IoU で照合し、各 track_id に対応するキーポイント（shape=(26,3)）または None を返す。マッチングアルゴリズムは貪欲法（各 track_id に対し IoU 最大の JSON 人物を割り当て）。ハンガリアン法による最適割り当ては行わない（室内の人数は最大 2〜3 人のため貪欲法で十分）。詳細は機能設計書 1.4.7 を参照
- **処理**:
  - 前フレームのアクティブ track_id 集合に含まれない track_id が出現（新規と判定）: FR-005 で即座にマッチを試みる。マッチ成功なら消失 ID の stable_id を引き継ぐ。マッチ失敗なら仮の新 stable_id を発番し、FR-009 の遅延マッチ（保留状態）に移行する。Deep OC-SORT は消失した track_id を再利用しないため、過去に存在した track_id が再出現することはない
  - 既存 track_id が継続: FR-004 で EMA 特徴量を更新。`keypoints_map[track_id]` が None になる場合は以下の2ケースに限定する: (1) そのフレームで json_people が 0 件（0人検出）の場合、(2) IoU < 0.5 でマッチする JSON 人物が存在しない場合。この場合 PersonFeature の head_hist・torso_hist をともに None として EMA 更新する（FR-004 の仕様上、既存 EMA が維持される）
  - 前フレームにあった track_id が消えた: アクティブから消失 ID リストへ移動（EMA 特徴量を保持）
  - 消失 ID の保持期間: 無制限（1セッション中は削除しない）。マッチして再同定された時点でのみ消失リストから除去する。本仕様は同一セッション中の登場人物が最大 3 人以下であることを前提とする。4 人以上の場合、消失 ID リストが増大し Re-ID 精度が低下するが、処理は継続する（クラッシュしない）
- **受け入れ基準**:
  - 新 track_id が出現し、消失 ID リストが空の場合: 新 stable_id が発番される
  - 新 track_id が出現し、消失 ID リストにマッチする ID がある場合: その stable_id が引き継がれ、消失リストから除去される
  - 前フレームの track_id が消えた場合: `_active_features` から `_disappeared` へ移動し EMA 特徴量が保持される
  - 同一 stable_id が複数の track_id に同時に割り当てられないこと
  - 同一フレームで複数の new_ids が同一 stable_id にマッチしようとした場合: new_ids を track_id 昇順にソートし、数値最小の track_id を優先して stable_id を割り当て、後続は新規 stable_id として発番される。この競合は仕様として受け入れる（室内では同一フレームで複数の新 ID が出現するケースは稀）

### FR-008: Re-ID 遅延マッチ実験

- **機能名**: 再出現後の類似度推移ログ
- **概要**: 新 track_id 出現後、フレームごとに EMA 特徴量が蓄積される過程で、消失 ID との類似度がどう変化するかを記録する。Re-ID マッチの判定ロジックは変更しない（ログ出力のみ）
- **目的**: 「映り始めは体の一部しか映らず特徴量が不十分」という仮説を検証し、何フレーム後に類似度が閾値（0.3）を超えるかを把握する
- **入力**: FR-007 と同一（既存の `--video`, `--json-dir`, `--device`）。追加 CLI 引数なし
- **出力（標準出力）**: 新 track_id 出現後、その track_id がアクティブな間、毎フレーム以下を出力:
  `Re-ID sim: frame=NNNN offset=MM track_id=T disappeared_sid=S sim=X.XXX`
  - `frame`: 現在のフレーム番号
  - `offset`: 新 track_id 出現からのフレーム数（0始まり）
  - `track_id`: 新しい track_id
  - `disappeared_sid`: 比較対象の消失 stable_id
  - `sim`: ヒストグラム交差による類似度（小数3桁）
  - 消失 ID が複数ある場合は全消失 ID に対して1行ずつ出力する
  - 消失 ID が 0 件の場合（初回の人物出現）は出力しない
  - sim が 0.000（両部位とも比較不能）の場合も出力する。`f"{sim:.3f}"` 形式
- **処理**: CustomReID の update() 呼び出し後、テストスクリプト側で以下を実行:
  1. 新 track_id が出現したフレームから追跡を開始し、その track_id がアクティブでなくなった（track_ids に含まれなくなった）フレームで追跡を終了する
  2. 追跡中の track_id について、CustomReID の内部状態（EMA 特徴量と消失 ID 特徴量）を取得する
  3. FR-005 の `_compute_similarity` メソッドで類似度を計算し、ログ出力する
- **CustomReID への変更**: 内部状態の参照用プロパティを追加する（ロジック変更なし）:
  - `active_features` プロパティ: `_active_features` の読み取り専用ビュー。戻り値型: `dict[int, PersonFeature]`（key は track_id）
  - `disappeared` プロパティ: `_disappeared` の読み取り専用ビュー。戻り値型: `dict[int, PersonFeature]`（key は stable_id）
  - `_compute_similarity` メソッドはプライベート（アンダースコア1つ prefix）のまま維持する。テストスクリプトから `reid._compute_similarity(feat1, feat2)` の形式で直接呼び出す。実験用コードとしての使用であり、実験終了後の除去は別案件で判断する
- **受け入れ基準**:
  - camSony1_S.mp4 で実行し、各再出現イベント（track_id=1消失→track_id=2出現 等）で offset=0 から類似度が出力されること
  - 出力から「何フレーム後に類似度 > 0.3 を超えるか」が読み取れること
  - 既存の FR-001〜FR-007 の動作が変更されないこと

### FR-007: オフライン検証スクリプト

- **機能名**: カスタム Re-ID オフライン検証
- **概要**: 既存の動画ファイルと HALPE 26 JSON を使い、カスタム Re-ID の動作をオフラインで検証する
- **入力**:
  - `--video`: 動画ファイルパス（必須）
  - `--json-dir`: HALPE 26 OpenPose JSON ディレクトリ（必須）。`halpe26_to_openpose.py` が出力した形式に限定する。ファイル命名規則: `{video_name}_{frame_idx:06d}.json`。`video_name` は動画ファイル名から拡張子を除いた部分（例: `camSony1_S.mp4` → `camSony1_S`、`cam05520129.mp4` → `cam05520129`）。欠番の定義: ファイル名末尾の 6桁数値（frame_idx）が動画フレームに対して存在しない場合。欠番フレームは 0 人検出として補完する（サイレント処理）。load_data() はファイル名から frame_idx を抽出し `{frame_idx: list[dict]}` 形式の辞書で返す。main() はこの辞書を使い動画の各フレームに対応する JSON を引く。辞書に存在しないフレームは `[]`（0人）として扱う
  - `--device`: 推論デバイス（デフォルト: `cuda:0`）。受け付ける値: `cuda:N`（N は 0 以上の整数）または `cpu`。不正な文字列が渡された場合、または CUDA デバイスが利用できない場合（GPU なし環境でデフォルト値 `cuda:0` が使われるケース含む）は、BoxMOT / PyTorch が送出する例外をキャッチせずに伝播させ、スタックトレースを表示して終了する（バリデーション不要）
  - Deep OC-SORT の `reid_weights` にはプロジェクトルート直下の `osnet_x0_25_msmt17.pt` を使用する（`test_boxmot_offline.py` と同一のパス解決方法）。CLI 引数には露出しない
- **出力（標準出力）**:
  - 10 フレームごと: `Processing frame NNNN: track_ids=[...], stable_ids={track_id: stable_id, ...}` 形式で出力
  - 最終サマリー: `=== Re-ID Summary ===` ヘッダーの後に、Total frames、Stable ID counts（stable_id ごとのフレーム数辞書）、Unique stable IDs（unique 数）、Processing time（秒と FPS）を出力。出力例: `Total frames: 900` / `Stable ID counts: {1: 704}` / `Unique stable IDs: 1` / `Processing time: 12.3 sec (73.2 fps)`
- **テストデータ**:
  - 動画: `testdata/camSony1_S.mp4`（室内の対象動画、低解像度、900フレーム）
  - JSON: `experiments/results/camSony1_S_json/`（HALPE 26 OpenPose JSON、900ファイル）
  - 実行例: `uv run python scripts/test_custom_reid_offline.py --video testdata/camSony1_S.mp4 --json-dir experiments/results/camSony1_S_json/`
- **受け入れ基準**:
  - **クラッシュ耐性（必須）**: camSony1_S.mp4（900 フレーム、78フレーム・数フレーム・93フレームの検出途切れが各1回）を処理して例外が発生しないこと
  - **クラッシュ耐性（必須）**: 0 人検出フレームが存在しても途中終了しないこと
  - **クラッシュ耐性（必須）**: JSON ファイルに欠番がある場合、欠番フレームは 0 人検出として補完し処理を継続すること。欠番フレームの個別通知は行わない（サイレント処理）。最終サマリーにも欠番数は出力しない
  - **クラッシュ耐性（必須）**: `DeepOcSort` コンストラクタが `w_association_emb` を受け付けない場合（`TypeError`）は以下のパラメータでフォールバック初期化してクラッシュしないこと。フォールバック発生時は WARNING を標準出力に出力すること。フォールバック時のパラメータ: `reid_weights=reid_path, device=args.device, half="cuda" in args.device, max_age=30`（`w_association_emb` は渡さない）
  - **Re-ID 精度（観察）**: 900 フレーム完了後、stable_id の unique 数を記録し目視確認する。類似度閾値 0.3 は暫定値のため初回実行では unique 数の目標値を設けない。人物が映っている区間で stable_id が単一 ID に収束することを確認する
  - **フォールバック時（観察）**: フォールバック発生時は Deep OC-SORT の内蔵 Re-ID が有効になるため stable_id unique 数 = 1 を保証しない。受け入れ基準は「クラッシュしないこと」のみ

---

## 1.4 非機能要求

- **処理速度**: 全フレーム処理の総時間と平均 FPS を標準出力の最終サマリーに出力する。下限は設けない。Re-ID モジュール自体は CPU で動作。Deep OC-SORT は GPU を使用する。
- **対応環境**: Ubuntu Linux、Python 3.10.16、uv 管理環境、NVIDIA RTX 5060 Ti（Deep OC-SORT 用）
- **信頼性**: 900 フレームの全処理で途中クラッシュなし。検出が 0 件のフレームでも正常に処理する。

### FR-009: 遅延 Re-ID マッチ

- **機能名**: 遅延 Re-ID マッチによる stable_id 再割り当て
- **概要**: 新 track_id 出現時の即座マッチ（FR-005）が失敗した場合、最大 N フレーム（デフォルト 180）の間、毎フレーム EMA 特徴量の蓄積に伴いマッチを再試行する。マッチ成功時に仮の stable_id を消失 ID の stable_id に再割り当てする
- **背景**: FR-008 の実験で、映り始めは体の一部しか映らず特徴量が不十分であり、約 28 フレーム後に類似度が閾値（0.3）を超えることが確認された
- **入力**: FR-006 の update() と同一。追加引数として `frame_idx: int`（現在のフレーム番号）を update() に追加する
- **出力**: FR-006 の update() 戻り値に反映される（再割り当て後の stable_id が返る）
- **パラメータ**: `delay_frames`（コンストラクタ引数、デフォルト 180）
- **処理**:
  1. 新 track_id 出現時に FR-005 でマッチ失敗: 仮の新 stable_id を発番し、保留状態に登録する。保留状態は `{track_id: (仮stable_id, 出現フレーム番号)}` で管理する。消失 ID が 0 件の場合（初回出現）は保留状態にしない
  2. 保留中の track_id について、毎フレーム EMA 更新後に FR-005 の `_match()` で再試行する
  3. マッチ成功: 仮 stable_id を消失 ID の stable_id に再割り当てする。`_active_stable[track_id]` を上書きし、消失 ID を `_disappeared` から除去する。保留状態から解除する
  4. N フレーム経過してもマッチ失敗: 仮 stable_id をそのまま確定し、保留状態から解除する
  5. 保留中に track_id が消失（Deep OC-SORT がトラッキングを失った場合）: 保留状態から解除し、現在の stable_id（仮 or 再割り当て済み）で消失 ID リストに移動する
- **保留中の処理順序**: 保留中の複数 track_id が同一フレームで遅延マッチを試行する際の処理順序: `_pending` の挿入順（track_id 出現順）でイテレーションし、先にマッチした track_id が消失 ID を消費する。後続の track_id は次フレームで再試行する
- **消失 ID との関係**: 保留中の再マッチ試行では、`_disappeared` の現在の状態を参照する。保留開始後に新たに消失した ID も比較対象に含まれる。ステップ2の即座マッチで消失IDが全て消費された場合、保留中の track_id はステップ4で `_match()` が None を返し、delay_frames 経過まで再試行を続ける（新たに消失するIDが出現すれば比較対象に含まれる）
- **保留中の消失**: 保留中（遅延マッチ未完了）に track_id が消失した場合、仮 stable_id のまま `_disappeared` に移動する。この仮 stable_id は後続の新 track_id との Re-ID マッチ対象になり得る（その人物の特徴量は蓄積されているため再同定に有用）。これは意図した動作である
- **受け入れ基準**:
  - camSony1_S.mp4 で最終フレーム時点のアクティブ + 消失のユニーク stable_id 数が 1 に近づくこと（理想は 1）。Stable ID counts 辞書のキー数には遅延マッチ成功前の仮 stable_id も含まれるため、ユニーク数の評価は最終サマリーとは別に目視で行う
  - 即座マッチが成功するケース（特徴量が十分な場合）は遅延なく stable_id が確定すること
  - 保留中の track_id が消失した場合、クラッシュせず正常に処理が継続すること
  - N=180 フレーム経過後に仮 stable_id が確定すること
  - 既存の FR-001〜FR-008 の動作が破壊されないこと（遅延マッチは FR-006 の拡張として実装）
  - 最終サマリーの Stable ID counts はフレーム時点の stable_id で集計する（遅延マッチ成功前の仮 stable_id のフレーム数もそのまま計上される。遡及修正は行わない）

---

## 1.5 制約条件

- Deep OC-SORT は BoxMOT 16.0.11 を使用する（既存環境、変更禁止）
- Deep OC-SORT の内蔵 Re-ID は無効化する（w_association_emb=0.0 相当）
- HALPE 26 キーポイントは既存の OpenPose JSON 形式（`halpe26_to_openpose.py` 出力形式）から読み込む
- 新規ライブラリの追加は禁止（既存環境の OpenCV、NumPy のみで実装）
- MMPose・MMDet のモデル推論はオフライン検証スクリプトでは不要（JSON から読み込む）

---

## 1.6 優先順位

| ID | 機能名 | MoSCoW |
|----|--------|--------|
| FR-001 | 頭部領域抽出 | Must |
| FR-002 | 上半身領域抽出 | Must |
| FR-003 | HSV ヒストグラム計算 | Must |
| FR-004 | EMA 特徴量更新 | Must |
| FR-005 | Re-ID 判定 | Must |
| FR-006 | stable_id 状態管理 | Must |
| FR-007 | オフライン検証スクリプト | Must |
| FR-008 | Re-ID 遅延マッチ実験 | Must |
| FR-009 | 遅延 Re-ID マッチ | Must |

**MVP**: FR-001〜009 すべて（すべてが揃って初めて検証が可能）
