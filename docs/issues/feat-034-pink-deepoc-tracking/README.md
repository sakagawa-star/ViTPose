# feat-034: pink_id + Deep OC-SORT による新トラッキング方式（ロードマップ）

## ステータス

Closed（2026-04-16、ロードマップ meta 案件として設計・発番計画を確定。実装は子案件 feat-035 / feat-036 で行う）

## 種別

ロードマップ案件（feat-019 と同じ meta 型）。本案件は設計上の全体像と発番の根拠のみを記録し、個別の実装は feat-035 / feat-036 で進める。

## 概要

feat-033 で確認された色ベース患者同定（`pink_id`）の優位性を踏まえ、`stable_id` / `custom_reid.py` に代わる新トラッキング方式を構築する。方式はハイブリッド: Deep OC-SORT の生 `track_id`（動き + 外観で継続性を保つ）と、色ベースの `pink_id`（患者識別シグナル）を組み合わせ、患者 ID `pink_track_id` を算出する。

## 背景・動機

### stable_id 方式の限界（feat-033 で定量確認）

- feat-033 の camSony1_L 分析で、`stable_id` 空間は同一患者を **444 個の ID に断片化**していた（top9 累積 91.7%）
- `custom_reid.py` のポーズ誘導 HSV ヒストグラム EMA 汚染が原因で、ID スイッチ時に別人外見で EMA が汚染され、患者追跡が長時間途切れる（feat-026 で観測した「42 分途切れ」は氷山の一角）
- 一方、色ベース（`pink_id`、feat-033）は EMA を使わず各フレーム独立計算のため汚染せず、94.1%（人物検出ありフレーム中）で一貫して同じ患者を選択できた

### pink_id 単独の限界

- pink_id は **服（ピンク部分）が見えているフレームでしか**患者 BB を割り当てられない
- 画面端で体の一部だけ見える状況、布団で服が隠れた状況では候補から外れる
- Deep OC-SORT の track_id は動き + 外観で continuous に track を保つため、**服が見えていない区間でも**「直前まで患者だった track」を追跡できる

### ハイブリッド方式の狙い

2方式を組み合わせることで補完関係を作る:

1. **服が見える区間**: `pink_id=1` で患者 BB を確定し、その BB の `track_id` を「現在の患者 track_id」として記憶
2. **服が見えない区間**: 記憶した patient track_id を持つ BB を患者とみなして `pink_track_id=1` を付与
3. **patient track が Deep OC-SORT 上で消滅**: 次に `pink_id=1` が観測されるまで `pink_track_id=-1`
4. **新しい `pink_id=1` 観測**: その BB の track_id を新しい patient track_id として更新

これにより「腕だけ見える → 服も見える → 布団で隠れる → 再び見える」の一連の状況で、患者追跡が継続する。

## パイプライン全体像（4ステージ、β採用）

β案: パイプラインを「単一責任のスクリプト」に分離し、中間 JSON を段階ごとに検証可能にする。

```
┌─ Stage 1: 推論 ───────────────────────────────────────┐
│ run_halpe26_pipeline_yolo11.py  (既存, feat-012/024)    │
│   入力: MP4 動画                                          │
│   出力: JSON (bbox, keypoints, bbox_score)                │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─ Stage 2: 純粋トラッキング ──────────────────────────┐
│ postprocess_track.py  (新規, feat-035)                  │
│   入力: JSON + MP4                                        │
│   出力: JSON + track_id  (Deep OC-SORT 単独)              │
│   特徴: custom_reid.py を使わない、生 track_id のみ       │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─ Stage 3: 色ベース患者選択 ──────────────────────────┐
│ postprocess_pink_id.py  (既存, feat-033)                │
│   入力: JSON(+track_id) + MP4                             │
│   出力: JSON + pink_id  (track_id は通過)                 │
│   特徴: feat-033 の実装をそのまま再利用（修正不要）        │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─ Stage 4: ハイブリッド患者追跡 ─────────────────────┐
│ postprocess_pink_track_id.py  (新規, feat-036)          │
│   入力: JSON(+track_id + pink_id)                          │
│        動画は不要（アルゴリズム上 JSON のみで完結）         │
│   出力: JSON + pink_track_id                              │
│   特徴: pink_id=1 の BB から patient track_id を記憶し、  │
│         track_id ベースで患者追跡を延長する結合ロジック    │
└─────────────────────────────────────────────────────────┘
```

## 発番計画

| 管理番号 | 内容 | ステータス |
|---------|-------|-----------|
| feat-034 | 本案件（ロードマップ） | Planned |
| **feat-035** | Stage 2 実装 `postprocess_track.py`（Deep OC-SORT 単独の track_id 付与ポストプロセス） | Planned |
| **feat-036** | Stage 4 実装 `postprocess_pink_track_id.py`（pink_id + track_id ハイブリッド患者追跡） | Planned |

Stage 1 (`run_halpe26_pipeline_yolo11.py`) と Stage 3 (`postprocess_pink_id.py`) は既存資産のため新規発番なし。

## 実施順序と依存関係

1. **feat-034**: ロードマップ確定（本案件、BACKLOG と CLAUDE.md 更新を含む）
2. **feat-035**: `postprocess_track.py` 実装 → 独立に動作確認
3. **feat-036**: `postprocess_pink_track_id.py` 実装 → feat-035 と feat-033 の出力を前提に結合ロジック検証

feat-036 は feat-035 が存在しないと動作確認できないため、feat-035 が先に完了する必要がある。

## 設計上の合意事項（確定済み）

- **新出力フィールド名**:
  - Stage 2: `track_id`（int、Deep OC-SORT 付与）
  - Stage 4: `pink_track_id`（int、-1 = 未割り当て / 患者非該当）
- **既存 `postprocess_pink_id.py` の扱い**: 修正不要。feat-033 `design.md` §10 ADR-001 で明文化されている「生 dict 保持設計」により、Stage 2 の `track_id` フィールドを含む任意の入力 JSON フィールドが読み込み時にそのまま保持され、出力時に `pink_id` のみが追加される。さらに feat-033 `requirements.md` AC-003-3 が「入力JSONの既存フィールドは変更されない」ことを受け入れ基準として保証している
- **パイプライン分離の理由**: 切り分け容易性。各段階の中間 JSON が独立に検証可能
- **トレードオフ（承知）**:
  - 中間ディレクトリが増える（camSony1_L で 4 段 ≈ 約 5 GB）
  - 動画読み込みパスが増える: Stage 1 は既存、Stage 2（`postprocess_track.py`）と Stage 3（`postprocess_pink_id.py`）がそれぞれ 1 回ずつ動画を読み込む。Stage 4 は動画不要
  - 処理時間の見込み: feat-033 の camSony1_L 実測値（321,239 フレーム、`postprocess_pink_id.py` 単体で 125.4 秒 = 約 2 分 / パス）を基準とすると、Stage 2 + Stage 3 + Stage 4 合計で **数分〜10 分オーダー**。Stage 2 は Deep OC-SORT の計算コストが追加されるため Stage 3 より時間がかかる可能性がある。本見積もりはロードマップ時点の粗見積もりであり、feat-035 / feat-036 の実装完了後に実測値で更新する
- **Deep OC-SORT の性質**: オンライン1方向処理、過去フレームに遡らない。2パス処理は不要（全ステージが単一方向ループで完結）

## ヒアリングで却下した選択肢

- **α案（3ステージ構成、pink_id を Stage 4 内部で再計算）**: 却下。切り分け性が低く、feat-033 の既存実装を流用できない
- **案X（feat-034 単独で全実装）**: 却下。案件が大きくなりすぎ、段階的動作確認が難しい
- **Stage 2 と Stage 4 の結合**: 却下。単一責任原則を崩す
- **Stage 3（pink_id）の再実装**: 却下。feat-033 の生 dict 保持設計により、既存実装がそのまま流用可能

## 残論点（feat-036 の要求仕様書作成時に詰める）

Stage 4 の結合ロジックの詳細は feat-036 のヒアリングで決定する。現時点の仮案:

- patient track_id の初期化・更新規則
- patient track が一時消失した場合の猶予フレーム数（`max_age` 相当）
- 複数の pink_id=1 BB が同時に別 track_id にマッピングされた場合の扱い
- 新しい pink_id=1 が既存 patient track_id と別 track_id にマッピングされた場合の切り替え条件

これらは feat-036 で個別に決定する。

## スコープ外（本ロードマップ案件では扱わない）

- 実装コード（feat-035 / feat-036 で行う）
- `run_halpe26_pipeline_yolo11.py` の変更
- `postprocess_pink_id.py`（feat-033）の修正
- 可視化スクリプトの作成
- `custom_reid.py` / `postprocess_reid.py` / `stable_id` 関連スクリプトの削除（当面並存）

## 関連案件

- 前提: feat-033（色ベース患者同定の検証・実装）
- 前提: feat-020（BoxMOT 環境構築）
- 子案件: feat-035（本案件のロードマップに基づく Stage 2 実装）
- 子案件: feat-036（本案件のロードマップに基づく Stage 4 実装）
- 凍結中（本案件への移行により再開予定なし）: feat-026, feat-027, feat-030, feat-031, feat-032

## 関連ファイル

- `scripts/run_halpe26_pipeline_yolo11.py` — Stage 1（既存）
- `scripts/postprocess_pink_id.py` — Stage 3（既存、feat-033）
- `scripts/postprocess_reid.py` — 旧 Re-ID ポストプロセス（Stage 2 実装時に CLI / JSON I/O の流儀元として参照）
- `scripts/custom_reid.py` — 旧カスタム Re-ID（Stage 2 では使用しない、参照のみ）
