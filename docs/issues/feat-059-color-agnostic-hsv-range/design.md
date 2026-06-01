# feat-059 機能設計書: analyze_clothing_color.py の色非依存レンジ提案

## 1.1 対応要求マッピング

| 要求ID | 設計セクション |
|---|---|
| FR-001 色レジーム判定 | 4.1（`decide_color_regime`） |
| FR-002 無彩色レンジ提案 | 4.2（`propose_achromatic_ranges`） |
| FR-003 有彩色後方互換 | 4.3（既存 `propose_ranges_from_chroma` を変更せず分岐で呼ぶ） |
| FR-004 PNG 無彩色対応 | 4.4（`render_analysis_png` 改修） |
| FR-005 閾値 CLI 引数化 | 4.5（`--chroma-regime-min`） |
| FR-006 複数画像モード対応 | 4.6（`run_multi_image` 改修） |

## 1.2 システム構成

- 対象ファイル: `scripts/analyze_clothing_color.py`（**本ファイルのみ変更**）
- 依存（変更しない）:
  - `scripts/merge_halpe26.py`: ViTPose 推論・HALPE26 結合
  - `scripts/postprocess_pink_id.py`: `compute_pink_ratio` / `FIXED_HSV_RANGES` / `MIN_PINK_RATIO`
- 呼び出し方向: `main` → `run_single_image` / `run_multi_image` → 提案系関数（本案件で追加・改修）。循環依存なし。

## 1.3 技術スタック

- Python 3.10.16 / numpy / OpenCV (cv2) / matplotlib。**新規ライブラリ追加なし**。
- パッケージ管理: uv（実行は `uv run python scripts/analyze_clothing_color.py ...`、プロジェクトルートから）。

## 1.4 各機能の詳細設計

### 4.0 全体方針（方式B）

色を「白／黒／灰／有彩色」の名前で**分類しない**。chroma_ratio という1つの連続量を1つの閾値で評価して `chromatic` / `achromatic` の2レジームに分け、各レジームで主要画素クラスタを HSV 空間で percentile 包囲する。

- `chromatic`: 既存の色相クラスタ提案（H を色相環で絞り、S/V 下限のみデータ駆動・上限255）。**既存コードを変更せず流用**＝有彩色の後方互換を保証。
- `achromatic`: H を全域 `[0,179]` に開き、S・V を全画素分布の percentile で**上下限とも**囲む。これにより白（低S・高V）・黒（低S・低V）・灰（低S・中V）が、分布に追従して自動的に表現される。

#### ADR-1: 方式B（分類しない）を消去法で採用
- 採用案: 方式B（分類せず分布から直接包囲）。
- 却下案: 方式A（有彩/白/黒/灰に分類してから種類別ロジック）。却下理由＝有彩色・白・黒を信頼性高く区別する閾値を決められず、方式Aの前提（信頼できる分類）が成り立たない。
- **重要**: 方式Bは「優れているから」ではなく「方式Aが成立しないから」消去法で選んだ。将来 B の出力が直感的でなくても、A の分類が信頼できるか再検証せずに A へ戻さないこと。

#### ADR-2: レジーム判定指標に chroma_ratio を採用、デフォルト閾値 0.4
- 採用案: 既存 `extract_chroma_hsv` が返す chroma_ratio（S≥sat_min & V≥val_min の画素割合）を閾値判定。デフォルト閾値 = **0.4**。
- 却下案: 全画素の S 中央値で判定。却下理由＝肌・背景が混じった有彩色ROIで S 中央値が下がり、有彩色画像が誤って achromatic に振れ後方互換（FR-003）を壊すリスクがある。chroma_ratio は「色相で区別できる画素がどれだけあるか」を直接表し、有彩色（高 chroma_ratio）と無彩色（低 chroma_ratio）を分けやすい。
- **デフォルト 0.4 の実測根拠**（`--sat-min`=20 / `--val-min`=60 で測定）:
  - 白服 E0049 4枚: chroma_ratio = 0.044 / 0.082 / 0.101 / **0.247**（最大0.247）
  - ピンク服 E0014 3枚: chroma_ratio = **0.713** / 0.765 / 0.905（最小0.713）
  - 白の最大0.247 と ピンクの最小0.713 の間に 0.4 を置くことで、両側にマージン（白側 0.4−0.247=0.153、ピンク側 0.713−0.4=0.313）を確保する。当初案の 0.15 では白の0.247を誤って chromatic に分類してしまうため不可。
- **依存性の明示**: chroma_ratio は `extract_chroma_hsv` 内の `mask = (S>=sat_min)&(V>=val_min)` で決まるため、`--sat-min`/`--val-min` に依存する。デフォルト閾値 0.4 はデフォルト sat_min=20 / val_min=60 を前提とする。ユーザーが `--sat-min`/`--val-min` を変える場合は `--chroma-regime-min` も再調整が必要。**この依存関係を利用者が認知できるよう、`--chroma-regime-min` の help 文に「default 0.4 assumes --sat-min=20 / --val-min=60」を明記する（4.5 参照）。** sat/val を変えたまま閾値を再調整しないと、誤判定したレジームで設定 JSON が生成されるリスクがあるため。

#### ADR-3: 無彩色レジームは S/V とも上下限をデータ駆動
- 採用案: achromatic では S_hi/V_hi も percentile（100−p）で決める。
- 却下案: 既存 chromatic と同じく上限を255固定。却下理由＝白の本質は「S が低い」ことであり、S 上限を255にすると有彩色画素まで含み白特徴が崩れる。黒の本質は「V が低い」ことで、V 上限255では黒を表現できない。よって無彩色は上下限ともデータ駆動が必須。

### 4.1 色レジーム判定（FR-001）

新規関数:
```python
def decide_color_regime(chroma_ratio: float, chroma_regime_min: float) -> str:
    """chroma_ratio を閾値判定して 'chromatic' / 'achromatic' を返す。"""
    return 'chromatic' if chroma_ratio >= chroma_regime_min else 'achromatic'
```
- 入力: chroma_ratio（float [0.0,1.0]、`extract_chroma_hsv` の第4戻り値）、chroma_regime_min（float [0.0,1.0]、CLI、デフォルト 0.4）。chroma_ratio は `--sat-min`/`--val-min` に依存する（ADR-2 の依存性の明示を参照）。
- 出力: `'chromatic'` または `'achromatic'`。
- 分岐: `chroma_ratio >= chroma_regime_min` → `'chromatic'`、それ以外 → `'achromatic'`。閾値判定のみで例外分岐は持たない（`chroma_ratio==0.0` を特別扱いするコードは入れない）。
- 境界: chroma_ratio==0.0（有彩色画素皆無）は、デフォルト閾値 0.4 では `0.0 < 0.4` で `'achromatic'` になる。ただし `--chroma-regime-min 0.0` を指定した場合のみ `0.0 >= 0.0` で `'chromatic'` となる（全入力が chromatic 扱い）。これは閾値0を指定した利用者の明示的選択であり仕様どおり。

### 4.2 無彩色レンジ提案（FR-002）

新規ヘルパ（全画素抽出）:
```python
def extract_all_hsv(roi_bgr: np.ndarray) -> tuple:
    """ROIの全画素 H,S,V を1次元配列で返す（マスクなし）。空ROIなら空配列3つ。"""
```
- 空ROI（`roi_bgr.size == 0`）→ `(empty, empty, empty)`（dtype=uint8）。

新規提案関数:
```python
def propose_achromatic_ranges(
    H_all: np.ndarray, S_all: np.ndarray, V_all: np.ndarray, percentile: float,
) -> tuple:
    """全画素 S/V の percentile で H全域・S/V上下限を囲む achromatic レンジを返す。
    戻り値: (proposed_ranges, s_lo, s_hi, v_lo, v_hi)。空配列なら ([], 0, 0, 0, 0)。"""
```
- データフロー:
  - 入力: 全画素 H_all/S_all/V_all（uint8、値域 H[0,179]・S/V[0,255]）、percentile（float [0,50]）。
  - 処理:
    1. `len(S_all)==0` なら `([], 0, 0, 0, 0)` を返す。
    2. `p_lo, p_hi = percentile, 100.0 - percentile`。
    3. `s_lo = int(round(float(np.percentile(S_all, p_lo))))`、`s_hi = int(round(float(np.percentile(S_all, p_hi))))`（`np.percentile` を使う。引数名 `percentile` と区別すること）。
    4. `v_lo = int(round(float(np.percentile(V_all, p_lo))))`、`v_hi = int(round(float(np.percentile(V_all, p_hi))))`。
    5. `proposed = [((0, s_lo, v_lo), (179, s_hi, v_hi))]`。
  - 出力: 上記 proposed と s_lo/s_hi/v_lo/v_hi。
- 境界: 全画素が同一値（分散0）の場合 s_lo==s_hi 等になりうるが、`lo <= hi` は保たれるため `cv2.inRange` で有効（H_lo=0 <= H_hi=179 も常に成立）。反転チェック不要。
- H は色相環をまたがない（0〜179固定）ため、chromatic のような2レンジ分割は発生しない。

### 4.3 有彩色レジームの後方互換（FR-003）

- 既存 `propose_ranges_from_chroma` / `extract_chroma_hsv` / `propose_hsv_ranges` は**シグネチャ・中身とも変更しない**。
- 単一画像モードの提案呼び出しを、レジームで分岐する形に置き換える（4.5 参照）。`chromatic` のときは従来どおり `propose_hsv_ranges(roi_bgr, sat_min, val_min, percentile)` を呼ぶ。
- これにより chromatic 経路は計算・出力が従来と完全一致する（FR-003 受け入れ基準のバイト一致を担保）。

### 4.4 PNG 可視化の無彩色対応（FR-004）

`render_analysis_png` を改修。新引数 `regime: str` と全画素配列を受け取れるようにする。
- 上段（input+ROI / current mask / proposed mask）: 既存どおり。`proposed mask` は `build_mask_for_ranges(roi_bgr, proposed_ranges)` で再計算（achromatic レンジでも動作）。
- 下段ヒストグラム:
  - `regime == 'chromatic'`: 既存どおりクロマ画素 Hc/Sc/Vc を表示し、H レンジ境界・S_lo/V_lo 線を引く。
  - `regime == 'achromatic'`: 全画素 H_all/S_all/V_all を表示。S/V の境界線は提案レンジから取得する＝`s_lo=proposed_ranges[0][0][1]`、`s_hi=proposed_ranges[0][1][1]`、`v_lo=proposed_ranges[0][0][2]`、`v_hi=proposed_ranges[0][1][2]`。S パネルに s_lo/s_hi、V パネルに v_lo/v_hi の境界線（破線）を引く。`proposed_ranges == []`（提案不可）の場合は境界線を描かない。境界値をローカル変数経由で別途渡さない（`render_analysis_png` のシグネチャを `regime` と `all_hsv` のみで保てる根拠＝境界は proposed_ranges に内包されている）。H パネルは全域提案のため境界線なし（タイトルに `H (all px, full range)` と明記）。無彩色では H はノイズ的で意味が薄いため、H パネルは参考表示の位置づけ。
- パネルタイトルはレジームに応じて `(chroma px)` / `(all px)` を切り替える。

### 4.5 CLI 引数化とディスパッチ（FR-005）

`parse_args` に追加:
```python
parser.add_argument('--chroma-regime-min', type=_check_ratio, default=0.4,
    help='chroma_ratio がこの値以上なら chromatic、未満なら achromatic として'
         'レンジを提案する ([0.0,1.0], default 0.4)。default 0.4 は '
         '--sat-min=20 / --val-min=60 前提。sat/val を変えたらこの値も再調整すること')
```
- `_check_ratio` は既存（[0.0,1.0] 検証）を流用。

単一画像モードの提案ディスパッチ（`run_single_image` 内、既存 `propose_hsv_ranges` 呼び出し部を置換）:
```
chroma_ratio = stats['chroma_ratio']  # 既存 compute_hsv_stats が返す
regime = decide_color_regime(chroma_ratio, args.chroma_regime_min)
print(f'[INFO] regime = {regime} (chroma_ratio={chroma_ratio:.3f}, thr={args.chroma_regime_min:.2f})')
if regime == 'chromatic':
    proposed, s_lo, v_lo, proposed_ratio = propose_hsv_ranges(roi_bgr, args.sat_min, args.val_min, args.percentile)
    # 既存どおりの stdout（proposed S_low/V_low 等）
else:  # achromatic
    H_all, S_all, V_all = extract_all_hsv(roi_bgr)
    proposed, s_lo, s_hi, v_lo, v_hi = propose_achromatic_ranges(H_all, S_all, V_all, args.percentile)
    proposed_ratio = compute_ratio_for_ranges(roi_bgr, proposed)
    # achromatic 用 stdout（proposed S=[s_lo,s_hi] V=[v_lo,v_hi]）
```
- stdout は両分岐とも「`proposed FIXED_HSV_RANGES = ...`」「`pink_ratio: current=... -> proposed=...`」の行を出す。achromatic では `proposed S_low/V_low` の代わりに `proposed S=[s_lo,s_hi], V=[v_lo,v_hi]` を出す。
- 以降の PNG・JSON 出力ロジック（既存）は `proposed` をそのまま使うため共通。JSON 形式は不変（FR 制約）。

### 4.6 複数画像モードの色非依存対応（FR-006）

`run_multi_image` を改修。`compute_hsv_stats` は変更しない（クロマ画素プール用に従来どおり使う）。全画素プールは `extract_all_hsv` を各画像で別途呼んで収集する。
- フェーズ1（収集）: 各画像のループ内で、既存の `pooled_H/S/V`（= stats['Hc'/'Sc'/'Vc']、クロマ画素）に加え以下を収集する（変数名つきで明記）:
  ```
  Ha, Sa, Va = extract_all_hsv(roi_bgr_from(frame, roi_box))
  pooled_all_H.append(Ha); pooled_all_S.append(Sa); pooled_all_V.append(Va)
  total_px += int(Ha.size)            # 全画素数の累積
  chroma_px += int(len(stats['Hc']))  # クロマ画素数の累積
  ```
- フェーズ2（提案）: `pooled_ratio = chroma_px / total_px if total_px > 0 else 0.0` を算出し `regime = decide_color_regime(pooled_ratio, args.chroma_regime_min)`。
  - `chromatic`: 既存どおり `propose_ranges_from_chroma(np.concatenate(pooled_H), np.concatenate(pooled_S), np.concatenate(pooled_V), percentile)`（現状の処理と完全一致 → 後方互換）。
  - `achromatic`: `propose_achromatic_ranges(np.concatenate(pooled_all_H), np.concatenate(pooled_all_S), np.concatenate(pooled_all_V), percentile)`。
- フェーズ3〜5（閾値検証・PNG・JSON）: 既存どおり。`render_analysis_png` には全画像共通の `regime`（プール判定結果）と、各画像の全画素配列を渡す。
- レジームは stdout に1行表示する（`[INFO] pooled regime = <...> (chroma_ratio=X.XXX, thr=X.XX)`）。

#### ADR-4: 複数画像のレジーム判定はプール全体で1回
- 採用案: プールした全画素のクロマ比率で1回だけ判定し、全画像に同じレジームを適用。
- 却下案: 画像ごとに判定。却下理由＝統合レンジは1個（既存仕様）なので、画像ごとにレジームが割れると統合レンジの型を一意に決められない。プール全体で1回判定すれば統合レンジの型が一意に定まる。

## 4.7 エラーハンドリング

| エラー | 検出 | 動作 |
|---|---|---|
| 画像読み込み失敗 | `cv2.imread` が None | `[ERROR]` 表示し exit 1（既存どおり） |
| 推論結果が空 | 既存 `estimate_halpe26_fullframe` | `[ERROR]` 表示し exit 1（既存どおり） |
| 提案レンジが空（空ROI 等で全画素0） | `proposed == []` | `[WARN]` 表示、JSON 出力しない（既存どおり）。PNG は proposed=[] で `proposed: N/A` 表示 |
| PNG / JSON 保存失敗 | 例外捕捉 | `[ERROR]` 表示し exit 1、書きかけ PNG は削除（既存どおり） |

## 4.8 境界条件

- 空ROI（`build_torso_roi` が fullframe フォールバック後も実質空になることは通常ない。万一 size==0）: `extract_all_hsv` が空配列を返し、`propose_achromatic_ranges` が `[]` を返す → `[WARN]` で JSON 非出力。
- chroma_ratio がちょうど閾値と等しい: `>=` 判定により `chromatic`。これは `--chroma-regime-min 0.0` かつ chroma_ratio==0.0 の場合も同様（全入力 chromatic、4.1 境界参照）。
- 全画素が単色（分散0）: s_lo==s_hi 等になるが `lo<=hi` で `cv2.inRange` 有効。提案レンジは1点的だが破棄しない。

## 1.6 ファイル・ディレクトリ設計

- 入力: 服の静止画パス（位置引数、既存どおり 1枚=単一画像モード / 2枚以上=複数画像モード）。
- 出力（既存と同一の規約・命名）:
  - PNG: 単一 `<stem>_color_analysis.png` / 複数 画像ごと `<stem>_color_analysis.png`。
  - JSON: 単一 `<stem>_hsv_config.json` / 複数 `<first_stem>_pooled_hsv_config.json`（`--json-out` で上書き可）。
  - JSON スキーマ: `{"fixed_hsv_ranges": [[[H_lo,S_lo,V_lo],[H_hi,S_hi,V_hi]], ...], "min_pink_ratio": <float>}`（compact 整形、`min_pink_ratio` は `MIN_PINK_RATIO`=0.03 固定、既存どおり）。

## 1.7 インターフェース定義（新規・改修関数）

- `extract_all_hsv(roi_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]` （新規）
- `decide_color_regime(chroma_ratio: float, chroma_regime_min: float) -> str` （新規）
- `propose_achromatic_ranges(H_all, S_all, V_all, percentile: float) -> tuple[list, int, int, int, int]` （新規、戻り値 `(proposed, s_lo, s_hi, v_lo, v_hi)`）
- `render_analysis_png(..., regime: str, all_hsv: tuple | None)` （改修：引数追加。`chromatic` 時は `all_hsv=None` 許容）
- 既存 `propose_hsv_ranges` / `propose_ranges_from_chroma` / `extract_chroma_hsv` / `compute_hsv_stats` / `build_mask_for_ranges` / `compute_ratio_for_ranges` / `write_hsv_config`: **変更なし**。

## 1.8 ログ・デバッグ設計

- ログは既存どおり `print('[INFO]/[WARN]/[ERROR] ...')` 方式（logging 未使用、既存に合わせる）。
- 追加ログ:
  - `[INFO] regime = <chromatic|achromatic> (chroma_ratio=X.XXX, thr=X.XX)`（単一）
  - `[INFO] pooled regime = <...>`（複数）
  - achromatic 提案行: `[INFO] proposed FIXED_HSV_RANGES = [...]` / `[INFO] proposed S=[s_lo,s_hi], V=[v_lo,v_hi]`
- 既存の `[NOTE] MIN_PINK_RATIO ...`（静止画比率は動画上限の注意書き）は両レジームで維持する。
