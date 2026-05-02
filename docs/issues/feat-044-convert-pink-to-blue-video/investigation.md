# feat-044 不具合調査・修正計画

本案件は機能追加だが、手動テスト（CLAUDE.md feat フロー ステップ 7）で不具合が確認されたため、`docs/BUGFIX_STANDARD.md` に従い調査・修正計画を本ファイルに記録する。

---

## イテレーション 1 (2026-04-30): ピクセル分離可能性の調査計画

### 1.1 不具合の特定

#### 現在の動作
`scripts/convert_pink_to_blue_video.py` をデフォルトパラメータ（`target-h=110, s-scale=0.35, s-max=80`）で `testdata/camSony1_S.mp4` に対して実行した結果、出力 `experiments/results/feat-044_test/camSony1_S_blue.mp4` で以下の症状を確認:

- **服のほとんどがピンクのまま**（変換漏れ）
- **服の一部が青に変換されている**（部分的に正しく変換）
- **人の肌が青に変換されている**（誤変換）

#### 期待する動作
- 服のすべてのピクセルが青に変換される
- 人の肌は元の肌色のまま保持される
- 背景・他の物体も変化なし

#### エラーメッセージ
なし（クラッシュではなく挙動の不一致）。

#### 再現手順
```bash
mkdir -p experiments/results/feat-044_test
uv run python scripts/convert_pink_to_blue_video.py \
  --input testdata/camSony1_S.mp4 \
  --out-dir experiments/results/feat-044_test
# 出力: experiments/results/feat-044_test/camSony1_S_blue.mp4 を再生して確認
```

### 1.2 原因の仮説

`postprocess_pink_id.py` の `FIXED_HSV_RANGES` を**ピクセル単位の色変換用途**にそのまま流用したことが原因の上位仮説。`FIXED_HSV_RANGES` は元来「BB 内のピンク比率」を計算する用途で設計されており、肌などの混入があっても比率が高ければ患者選択は機能する設計。ピクセル単位の判定では肌の混入が直接見える。

仮説は 2 通りに分岐し、本イテレーションでこのどちらかを確定する:

#### 仮説 A: HSV 空間で服と肌が分離可能
- 肌: `H≈0-15, S≈60-150, V≈80-220`
- ピンク服: `H≈140-179, S≈80-200, V≈80-230`
- 両者は H 軸で十分離れており、`H` 範囲を狭めれば（`H=0-10` を削除して `H=140-179` のみ使う等）肌を除外しつつ服を捕捉可能
- 観察事実「服の一部が青」は単に S>=60 を満たした服画素が捕捉されたという解釈

#### 仮説 B: HSV 空間で服と肌が重なる
- 肌のシャドウ・血色濃い部分が `H≈170, S≈80` まで回り込む
- 服のハイライトや特定の織り目が `H≈10, S≈80` に流れる
- 両者の HSV 分布が**重なる**ため、どんな HSV 範囲を組んでも分離できない
- 観察事実「服の一部が青」は肌と同じ HSV 範囲に偶然落ちた服画素が捕捉されたという解釈

仮説 A なら HSV 範囲の調整で済む。仮説 B なら**色情報だけでは原理的に分離不可**で、空間情報（キーポイント、BB 制約）の併用が必要となり設計が大きく変わる。

#### 根本原因 / 表面的原因
- 表面的: HSV 範囲が用途に合っていない
- 根本: 入力動画 `testdata/camSony1_S.mp4` の **実 HSV 分布を要求仕様作成時に調査せず、`postprocess_pink_id.py` の既存範囲を流用した**こと。Blue1-4.png では「青色側の HSV 分布」を実測したのに、変換元の「ピンク色側の HSV 分布」を実測しなかった非対称な調査不備

### 1.3 調査計画（BUGFIX_STANDARD §1.3 「修正内容」は本イテレーションでは保留）

本イテレーションでは BUGFIX_STANDARD §1.3「修正内容（変更対象ファイル / 修正前後コード）」を**保留**し、代わりに本セクションを「調査計画」として記述する。修正内容はイテレーション 2 以降で本調査の結果に基づき具体化する。コード変更は本イテレーションでは行わない。

#### 1.3.1 調査の目的
仮説 A / B のどちらが事実かを実データで確定する。

#### 1.3.2 入力データ
- 動画: `testdata/camSony1_S.mp4`（900 フレーム、960×540、30 fps）
- JSON: `experiments/results/camSony1_S_pink_json/`（feat-039 / feat-041 改修済み、`pink_id` / `pose_keypoints_2d` / `bbox` を含む）
- HALPE26 キーポイント定義: 0=Nose, 1=LEye, 2=REye, 3=LEar, 4=REar, 5=LShoulder, 6=RShoulder, 9=LWrist, 10=RWrist, 11=LHip, 12=RHip

#### 1.3.3 サンプリング戦略
全 900 フレームではなく**代表 5〜10 フレーム**で HSV 分布を集計する。理由:
- 同一の服・同一の照明条件下では HSV 分布はフレーム間で大きく変動しない
- フレーム前半は患者があまり映っていない（先の分析で frame 100 / 700 / 850 は H=160-179 が 1% 未満）
- 5〜10 サンプルで中央値・ピークは収束する（Blue1-4.png は 4 枚で照明変動を含めた知見が得られた前例）

#### サンプリング条件
以下を満たすフレームを選ぶ:
1. `pink_id == 1` の人物が存在
2. その人物の `bbox_score >= 0.7`
3. 鼻 / 両肩 / 両腰の HALPE26 キーポイント信頼度 `>= 0.3`
4. 両肩・両腰の内接矩形が**面積 1000 px 以上**（小さすぎる胴体は HSV 統計が不安定）

候補フレーム: 200, 300, 400, 500, 600, 700, 800 から条件を満たすものを選定。条件を満たさない場合、**そのスロットの ±20 フレーム以内**でずらして再選定する。±20 フレーム以内に条件を満たすフレームがなければそのスロットを破棄。最終的に**最低 5 枚、最大 10 枚**を確保する（5 枚未満になった場合は調査計画を見直し、サンプリング戦略をイテレーション 2 で再設計する）。先の分析（本調査前の探索的観察）で frame 100 / 700 / 850 は H=160-179 が 1% 未満だったため、これらのスロットが破棄される可能性がある。

#### 1.3.4 ROI 抽出
各サンプルフレームで、以下 2 種類の ROI を取得:

##### ROI-A: 肌サンプル（鼻パッチ）
- 中心: HALPE26 keypoint 0 (Nose) の `(x, y)`
- サイズ: 8×8 px（合計 64 px / フレーム × 5-10 = 320-640 px）
- 採用理由: 鼻周辺はほぼ確実に肌で、髪・服・背景が混入しにくい

##### ROI-B: 服サンプル（胴体内接矩形の中央 50%）
- まず両肩・両腰の内接矩形を計算:
  - `x_min0 = min(LShoulder.x, RShoulder.x)`
  - `x_max0 = max(LShoulder.x, RShoulder.x)`
  - `y_min0 = min(LShoulder.y, RShoulder.y, LHip.y, RHip.y)`
  - `y_max0 = max(LHip.y, RHip.y)`
- 中央 50% に縮小する（腕・首・背景の混入を抑える）:
  - `cx = (x_min0 + x_max0) / 2`、`cy = (y_min0 + y_max0) / 2`
  - `w = x_max0 - x_min0`、`h = y_max0 - y_min0`
  - ROI-B 矩形 = `(cx - w*0.25, cy - h*0.25, cx + w*0.25, cy + h*0.25)`
- 矩形範囲を画像境界でクリップし、画素を取得
- **二段階フィルタ（肌色除外）**: ROI-A の `H` の P25 と P75 を計算し、その帯（例: P25=2, P75=12 なら H=2-12）に該当する ROI-B 画素を ROI-B 統計から除外。これにより ROI-B の純度を担保する
- 注意: 中央 50% 縮小と肌色除外を行ってもなお背景・小物の混入は残りうる。ただし「服と肌の HSV 重なり」を測るための ROI-B として、ROI-A 由来の肌色帯が事前除外されているため、判定 1.3.6 の「重なり」値は服側の真の混入率を反映する

#### 1.3.5 HSV 統計の集計
- ROI-A の全画素を BGR → HSV 変換し、(H, S, V) を集計
- ROI-B の全画素を BGR → HSV 変換し、(H, S, V) を集計
- 各 ROI ごとに以下を出力:
  - 中央値 / 平均 / P25 / P75 (H, S, V それぞれ)
  - H ヒストグラム（10 度刻み 18 bin）
  - 2D 散布図 PNG: 横軸 H、縦軸 S、ROI-A を赤、ROI-B を青で重ねる
  - 出力先: `experiments/results/feat-044_test/diagnostics/` 配下に PNG 保存（`/tmp` ではなく永続領域を使用）

#### 1.3.6 判定基準

3 分岐で判定する。事実から事実を導くため、各分岐は閾値を明示する:

##### 仮説 A 確定（HSV 範囲調整で解決可能）
**両条件を同時に満たす**:
- ROI-A の H 中央値と ROI-B の H 中央値の差が **30 以上**（H は OpenCV の 0-179 表現、円環距離で計算）
- 重なり領域（両者の P25-P75 範囲が交差する H 帯）の画素が ROI-B 全体（肌色除外後）の **5% 未満**

##### 仮説 B 確定（空間制約の併用が必要）
**いずれか一方を満たす**:
- ROI-A の H 中央値と ROI-B の H 中央値の差が **15 未満**
- 重なり領域の画素が ROI-B 全体の **15% 以上**

仮説 B 確定時に検討すべき事項（イテレーション 2 で詳細化）:
- **臥位対応**: CLAUDE.md「病室動画の特性」より患者は臥位がほとんど。横向き胴体では肩腰内接矩形が極端に細く・低くなる、または完全に縮退する。閾値（例: 内接矩形の幅 or 高さが 20 px 未満）以下の場合の代替 ROI 定義（例: BB の中央 60%）が必要
- **複数人時の挙動**: BB 内に他人物（看護師等）が部分的に映り込むケース。`pink_id == 1` の人物の BB のみを使うので原則影響なしだが、BB 重複時の処理を要確認
- **キーポイント低信頼時のフォールバック**: 上記 1.3.3 の信頼度 0.3 未満のフレームは ROI-B 構築不能。これらのフレームは変換対象外とするか、BB 全体を使う代替策が必要か
- **顔・手領域マスクの定義**: HALPE26 keypoint 0-4（顔）の凸包 / 半径 30 px の円、9-10（手首）周辺 30×30 px の根拠と精度

##### グレーゾーン（追加調査必要）
仮説 A / B のいずれの確定条件も満たさない場合、または **A 条件と B 条件が同時に成立する矛盾ケース**（例: H 中央値差 35 で A の閾値以上、しかし重なり 20% で B の閾値以上、という両立シナリオ）の場合:
- サンプル数を 10 枚から 20 枚に増やして再集計
- それでもグレーゾーンに留まる場合は、調査計画自体（ROI 定義・サンプリング戦略）をイテレーション 2 で再設計

矛盾ケース（H 中央値は離れているのに重なりが大きい）は ROI-B の純度不足や ROI-A の代表性問題を示唆するため、自動的にどちらか一方の仮説に倒さず、追加調査として扱う。

##### 判定の優先順序（実装観点）
1. A 条件と B 条件を独立に評価する
2. **A 条件成立 かつ B 条件成立 → GRAY**（矛盾ケース）
3. A 条件のみ成立 → A 確定
4. B 条件のみ成立 → B 確定
5. どちらも成立せず → GRAY（グレーゾーン中間帯）

#### 1.3.7 調査スクリプトの構造

**配置**: `scripts/diagnose_pink_skin_separation.py` として新規作成（feat-044 の本体スクリプトとは別）。一回限りの調査用ツールだが、再現性のためファイル化する。

**CLI**:
```bash
uv run python scripts/diagnose_pink_skin_separation.py \
  --video testdata/camSony1_S.mp4 \
  --json-dir experiments/results/camSony1_S_pink_json \
  --out-dir experiments/results/feat-044_test/diagnostics \
  --candidate-frames 200 300 400 500 600 700 800 \
  --frame-tolerance 20 \
  --min-samples 5 --max-samples 10 \
  --skin-patch-size 8 \
  --torso-shrink 0.5
```

**関数構成**:
```python
def select_sample_frames(video, json_dir, candidate_frames, tolerance,
                        min_samples, max_samples) -> list[int]:
    """1.3.3 のサンプリング条件 1-4 を満たすフレームを選定。±tolerance 内でずらす。"""

def extract_roi_a_skin(frame_bgr, kpts, patch_size) -> np.ndarray:
    """鼻 keypoint 中心 patch_size×patch_size の HSV 配列を返す。shape=(N, 3)"""

def extract_roi_b_torso_raw(frame_bgr, kpts, shrink) -> np.ndarray:
    """肩腰内接矩形を中央 shrink 倍に縮小した HSV 配列を返す。肌色除外は未適用。
    shape=(N, 3)。重なり率計算（§1.3.8 の compute_h_overlap_ratio）はこの生配列を使う。"""

def filter_skin_h_band(roi_b_raw, h_skin_lo, h_skin_hi) -> np.ndarray:
    """ROI-B 生配列から ROI-A の H P25-P75 帯（円環考慮、§1.3.8 in_h_band）に該当する
    画素を除外した配列を返す。中央値・P25/P75・mean などの統計用。"""

def compute_stats(hsv_pixels: np.ndarray) -> dict:
    """median/P25/P75/mean を H/S/V それぞれで計算し dict で返す。"""

def hue_circular_distance(h1: float, h2: float) -> float:
    """OpenCV H (0-179) の円環距離を計算。max は 90。"""

def compute_h_overlap_ratio(roi_b_hsv, roi_a_p25, roi_a_p75) -> float:
    """ROI-A の H P25-P75 帯（円環考慮）に該当する ROI-B 画素の比率（0.0-1.0）。
    生 ROI-B（中央 50% 縮小は適用、肌色除外は未適用）を使って独立性を保つ。"""

def classify_hypothesis(h_diff: float, overlap: float) -> str:
    """1.3.6 の閾値で 'A'/'B'/'GRAY' を返す。"""

def plot_scatter(roi_a_all, roi_b_all, out_path) -> None:
    """H-S 散布図 PNG を保存。ROI-A=赤、ROI-B=青。"""

def plot_h_histograms(roi_a_all, roi_b_all, out_path) -> None:
    """ROI-A と ROI-B の H ヒストグラムを並べた PNG を保存。"""

def main() -> None:
    """フレーム選定 → ROI 抽出 → 統計集計 → 判定 → PNG 出力 → サマリ表示。"""
```

##### main の処理順序（明示）

ROI-A の H 帯を ROI-B の肌色除外フィルタに使うため、main の処理は以下の順番で行う:

1. 候補フレーム選定（`select_sample_frames`）
2. **全選定フレームで ROI-A を抽出して連結**（`roi_a_all`、shape=(N_A, 3)）
3. ROI-A の H P25 / P75 を計算（`compute_stats(roi_a_all)['H_P25']`, `'H_P75'`）
4. **全選定フレームで ROI-B 生配列を抽出して連結**（`roi_b_raw_all`、shape=(N_B, 3)）— 重なり率計算用
5. `roi_b_filtered_all = filter_skin_h_band(roi_b_raw_all, A_p25, A_p75)` — 統計用
6. `compute_stats(roi_a_all)` / `compute_stats(roi_b_filtered_all)` で中央値・P25/P75・mean 計算
7. `compute_h_overlap_ratio(roi_b_raw_all, A_p25, A_p75)` で重なり率計算（**生 ROI-B を使う**ことで肌色除外による評価バイアスを回避）
8. `classify_hypothesis(h_diff, overlap)` で A / B / GRAY を判定
9. 散布図・H ヒストグラムを PNG 出力（散布図は `roi_b_raw_all` を使う、ヒストグラムは raw / filtered の両方を出す）
10. サマリを標準出力

#### 1.3.8 「重なり領域」の数式定義

OpenCV の H は 0-179 の円環値（H=179 と H=0 は近接）。生の差分計算では赤系（H=170-179）と肌色（H=0-15）が「遠い」と誤判定されるため、**円環距離**で計算する:

```
hue_circular_distance(h1, h2) = min(|h1 - h2|, 180 - |h1 - h2|)
```

仮説判定で使う `H 中央値差` はこの円環距離を使う。`重なり領域` は以下の通り:

```
def in_h_band(h, lo, hi):
    # lo / hi は ROI-A の H P25 / P75（円環区間として解釈）
    if lo <= hi:
        return lo <= h <= hi
    else:  # 区間が 179-0 をまたぐ場合（例: lo=170, hi=10）
        return h >= lo or h <= hi

overlap = sum(in_h_band(h_b, roi_a_p25, roi_a_p75) for h_b in ROI_B 全画素) / len(ROI_B)
```

ROI-A の P25/P75 が円環をまたぐかどうかは、ROI-A の H 中央値が 0 や 179 付近にあれば発生しうる（肌色が H=170-15 にまたがるケース）。

#### 1.3.9 出力フォーマットの具体例

##### 標準出力（テキストサマリ）
```
=== feat-044 pink/skin separation diagnosis ===
Selected frames: [205, 312, 408, 503, 605, 711]  (6 samples)

ROI-A (skin, nose patch 8x8):
  total pixels: 384
  H median=4, P25=2, P75=8, mean=5.1
  S median=78, P25=62, P75=98, mean=80.3
  V median=145, P25=128, P75=170, mean=147.0

ROI-B (gown, torso center 50%, skin-H excluded):
  total pixels (raw): 12480
  total pixels (skin-H excluded): 11930
  H median=170, P25=165, P75=175, mean=170.2
  S median=130, P25=95, P75=170, mean=131.5
  V median=180, P25=140, P75=215, mean=182.0

H circular distance (ROI-A median vs ROI-B median): 14
H overlap ratio (raw ROI-B in ROI-A P25-P75 band [2-8]): 18.5%

=== Hypothesis classification ===
H median diff: 14 (< 15 threshold)  -> HYPOTHESIS B
Overlap ratio: 18.5% (>= 15% threshold) -> HYPOTHESIS B
Final: HYPOTHESIS B (HSV alone cannot separate)

Saved: experiments/results/feat-044_test/diagnostics/skin_vs_gown_scatter.png
Saved: experiments/results/feat-044_test/diagnostics/h_histograms.png
```

##### `skin_vs_gown_scatter.png`
- 横軸: H (0-179)、縦軸: S (0-255)
- 赤点: ROI-A 全画素
- 青点: ROI-B 全画素（肌色除外前）
- 図サイズ: 1200×800、dpi=80

##### `h_histograms.png`
- 上下 2 段
- 上段: ROI-A の H ヒストグラム（10 度刻み 18 bin、赤）
- 下段: ROI-B の H ヒストグラム（同、青）
- 縦軸はそれぞれ画素数

#### 1.3.10 期待アウトプット
本調査の成果物:

1. `scripts/diagnose_pink_skin_separation.py`（新規スクリプト、調査専用、本案件クローズ後の扱いはイテレーション 2 で決定）
2. `experiments/results/feat-044_test/diagnostics/skin_vs_gown_scatter.png`
3. `experiments/results/feat-044_test/diagnostics/h_histograms.png`
4. `experiments/results/feat-044_test/diagnostics/summary.txt`（標準出力をリダイレクトしたテキスト）
5. **本ファイルへのイテレーション 2 セクション追記**: 上記サマリの転記、仮説 A / B / GRAY のいずれに確定したか、それに基づく修正方針

### 1.4 調査の影響範囲

#### コード変更
**本イテレーションでは一切行わない**。調査用の一時 Python スニペットを実行するのみ。

#### ドキュメント変更
- 本ファイル `investigation.md` の作成（このコミット）
- 調査結果を踏まえた `requirements.md` / `design.md` の修正は**イテレーション 2 以降**

#### リグレッションリスク
本イテレーションは調査のみのため、リグレッションリスクなし。

### 1.5 調査の確認方法

#### テスト項目
- T-1: 5〜10 サンプルフレームの選定が §1.3.3 の条件 1-4 を満たすこと（標準出力で選定 frame 番号と各キーポイント信頼度を確認）
- T-2: ROI-A / ROI-B が画像上の正しい位置から取得されていること（H-S 散布図 PNG 上で目視確認）
- T-3: 仮説 A / B / GRAY のいずれかが §1.3.6 の判定基準で確定すること（標準出力に classification 行が出ること）
- T-4: 調査結果ファイル 4 種が `experiments/results/feat-044_test/diagnostics/` 配下に保存されること（`/tmp` 禁止ルール準拠）

#### テストコマンド
```bash
mkdir -p experiments/results/feat-044_test/diagnostics
uv run python scripts/diagnose_pink_skin_separation.py \
  --video testdata/camSony1_S.mp4 \
  --json-dir experiments/results/camSony1_S_pink_json \
  --out-dir experiments/results/feat-044_test/diagnostics \
  | tee experiments/results/feat-044_test/diagnostics/summary.txt
```

期待される終了コード: 0（仮説 A / B / GRAY のいずれでも正常終了。エラー時のみ非ゼロ）。

### 1.6 スコープ限定（BUGFIX_STANDARD §2.2 準拠）

本調査では以下を対象外とする:
- ピンク患者検出ロジック (`postprocess_pink_id.py`) 自体の変更
- HALPE26 推論パイプライン (`run_halpe26_pipeline_yolo11.py`) の変更
- `FIXED_HSV_RANGES` の本体修正（`postprocess_pink_id.py` 側）
- Blue1-4.png に基づく青検出側 (`feat-045`) の方針変更

これらが必要になった場合は別案件として起票する。

### 1.7 ユーザー承認待ち事項

本イテレーションは調査計画のみ。以下を確認してから次に進む:

- [x] サンプリング条件（信頼度 0.3、内接矩形 1000 px 以上、N=5-10）
- [x] ROI-A サイズ 8×8 px、ROI-B が胴体内接矩形
- [x] 仮説判定基準（H 中央値差 30 以上、重なり 5% 未満）
- [x] 出力先 `experiments/results/feat-044_test/diagnostics/`
- [x] **調査スクリプトの実行可否**（`scripts/diagnose_pink_skin_separation.py` として作成、ユーザー承認済みで 2026-04-30 に実行）

---

## イテレーション 2 (2026-04-30): 調査結果と仮説 B 確定後の修正方針

### 2.1 イテレーション 1 調査結果

`scripts/diagnose_pink_skin_separation.py` を以下のコマンドで実行:

```bash
mkdir -p experiments/results/feat-044_test/diagnostics
uv run python scripts/diagnose_pink_skin_separation.py \
  --video testdata/camSony1_S.mp4 \
  --json-dir experiments/results/camSony1_S_pink_json \
  --out-dir experiments/results/feat-044_test/diagnostics \
  | tee experiments/results/feat-044_test/diagnostics/summary.txt
```

#### 2.1.1 数値結果

```
Selected frames: [203, 300, 400, 500, 719, 784]  (6 samples)

ROI-A (skin, nose patch 8x8):
  total pixels: 384
  H median=27, P25=7, P75=173, mean=65.5
  S median=67, P25=36, P75=90, mean=65.6
  V median=119, P25=82, P75=156, mean=122.0

ROI-B (gown, torso center 50%, skin-H excluded):
  total pixels (raw): 55871
  total pixels (skin-H excluded): 30177
  H median=176, P25=1, P75=178, mean=115.9
  S median=81, P25=73, P75=93, mean=86.4
  V median=127, P25=107, P75=143, mean=129.1

H circular distance (ROI-A median vs ROI-B median): 31
H overlap ratio (raw ROI-B in ROI-A P25-P75 band [7-173]): 46.0%

A condition (h_diff>=30.0 AND overlap<0.05): False
B condition (h_diff<15.0 OR overlap>=0.15): True
Final: HYPOTHESIS B
```

#### 2.1.2 出力成果物

- `experiments/results/feat-044_test/diagnostics/summary.txt`
- `experiments/results/feat-044_test/diagnostics/skin_vs_gown_scatter.png`
- `experiments/results/feat-044_test/diagnostics/h_histograms.png`

### 2.2 仮説 B 確定の解釈

#### 2.2.1 散布図・ヒストグラムから読み取れる事実

- **肌（ROI-A）の H 分布が円環の両極端に分散**: ヒストグラム上段で H=0-10 と H=170-179 の両方に明確なピーク。鼻周辺の影・色温度・微妙な凹凸で同一肌でも H 値が両側に流れる
- **服（ROI-B raw）の H 分布も両側に分布**: ヒストグラム中段で H=0-10 に約 10500 px、H=160-179 に約 45000 px のピーク。`postprocess_pink_id.py` の `FIXED_HSV_RANGES` が H=0-10 と H=140-179 を含めた理由はここ
- **ROI-A P25-P75 = [7, 173]**: 肌の中央 50% が H=7-173 という極めて広い帯になり、これは「H 軸のほぼ全域から H=7-173 の中間部を除いた両端領域」を意味する（散布図で目視可能）。この帯に raw ROI-B 全体の **46%** が該当 → 服画素のうち約半分が肌と同じ H 帯にある

#### 2.2.2 結論

色（H/S/V）のみで「服画素」と「肌画素」を分離するのは**原理的に不可能**。重なり率 46% は閾値 15% を遥かに超えており、HSV 範囲をどう切っても両者を分離する範囲は存在しない。

この事実は単に「`FIXED_HSV_RANGES` が悪い」のではなく、**HSV 空間の性質**（赤系の色が H=0/180 円環の両端にまたがる）と**人体の物理特性**（肌のシャドウ・ハイライトが広い H 範囲をカバー）の組み合わせによる構造的問題。

### 2.3 修正方針

仮説 B 確定により、investigation.md §1.3.6「仮説 B 確定時の検討事項」を具体化する。色だけでは分離できないため、**空間制約**（キーポイント・BB 内位置）の併用が必須。

#### 2.3.1 採用する空間制約方式の比較

| 方式 | 概要 | メリット | デメリット |
|---|---|---|---|
| **(α) 顔・手マスク除外** | HSV ピンクマスク AND NOT (顔キーポイント周辺 ∪ 手周辺) | 服全体を変換対象にできる、現行の HSV 範囲を流用可能 | 露出した腕（袖からの肌）の除外が困難、首・耳の境界が雑、複数人時に他人の顔も除外する必要あり |
| **(β) 胴体内接矩形限定** | 両肩・両腰の内接矩形内 AND HSV ピンクマスク | 肌混入が最小（鼻・耳・手は矩形外）、ユーザー先行提案 | 横たわる患者で内接矩形が縮退するケースあり、袖の服は変換されない（胴体本体のみ） |
| **(γ) BB 全体 + キーポイント周辺除外** | 患者 BB 内 AND HSV ピンクマスク AND NOT (顔・手周辺) | 服全体を変換、肌除外も狙える | (α) と同じ境界問題、複雑化 |

#### 2.3.2 採用案: (β) 胴体内接矩形限定

理由:
- ユーザーが先行提案した方式
- 肌混入リスクが最小（顔・手・首・耳が確実に矩形外）
- 検証が単純（4 キーポイントから矩形 1 つ）
- 「変換対象は患者の体幹中心部のみ」という挙動が理解しやすい
- 袖が変換されない問題は本案件のスコープ（合成テスト動画生成）では許容範囲。胴体中心が青に変われば feat-045 の検出ロジック検証には十分

却下理由:
- (α): 腕の肌除外が困難（露出した腕は袖の外でも HSV 的には肌）
- (γ): (α) の問題に加えて複雑化

#### 2.3.3 採用案 (β) の懸念事項と対処

investigation.md §1.3.6 仮説 B 確定時の検討事項に基づく:

| 懸念 | 対処方針 |
|---|---|
| **臥位で内接矩形が縮退** | 矩形面積が閾値（例: 1000 px）未満なら当該フレームの変換をスキップ（フレーム単位フォールバック） |
| **複数人時の挙動** | 入力 JSON の `pink_id == 1` 人物のキーポイントのみ使用（他人物は無視）。複数人 `pink_id == 1` は仕様上発生しないが、念のため最初の 1 人のみを採用 |
| **キーポイント低信頼時** | `LShoulder`/`RShoulder`/`LHip`/`RHip` の信頼度が `KP_CONF_MIN`（例: 0.3）未満なら当該フレームの変換をスキップ |
| **JSON 欠損フレーム** | 当該フレームの変換をスキップ |
| **スキップ時の挙動** | 元フレームをそのまま出力動画に書き出す（ピンクのまま）。サマリで「変換対象 X / 全 Y フレーム」を表示 |

### 2.4 修正計画（コード・ドキュメント変更）

本イテレーションは方針確定までで、コード変更はイテレーション 3 以降で行う。事前に以下のドキュメント修正が必要:

#### 2.4.1 requirements.md 修正項目

- §1.1「何を作るのか」: 「ピンク領域」を「ピンク患者の胴体内接矩形内のピンク領域」に変更
- §1.2「なぜ作るのか」: 仮説 B 確定の経緯を追記（HSV 単独では分離不可、空間制約併用）
- §2 用語定義: 「胴体内接矩形」を追加（4 キーポイントから算出）
- §3 機能要求:
  - FR-001 を改訂（HSV マスク AND 胴体内接矩形マスク）
  - 新 FR-007「キーポイント JSON 入力」を追加（`--json-dir` 引数）
  - 新 FR-008「フレーム単位フォールバック」（キーポイント信頼度・矩形面積条件）
- §5 制約条件: 入力 JSON の必須化、HALPE26 keypoint 形式

#### 2.4.2 design.md 修正項目

- §2.1 モジュール構成に新関数を追加（`build_torso_rect_mask`、`load_kpts_for_pink_patient` など）
- §4 詳細設計に FR-007 / FR-008 のセクション追加
- §5.2 推奨実行コマンドに `--json-dir` 引数追加
- §7.1 CLI 引数に `--json-dir`（必須）、`--torso-min-area`、`--kpt-conf-min` を追加
- ADR 追記: 「(α) (β) (γ) 比較で (β) を採用、却下理由」を §10 に追加

### 2.5 影響範囲

#### コード変更（イテレーション 3 以降）
- `scripts/convert_pink_to_blue_video.py`: 主要書き換え（HSV マスクのみ → HSV マスク AND 胴体内接矩形マスク）
- `scripts/diagnose_pink_skin_separation.py`: 変更なし（調査用ツールとして残置）

#### ドキュメント変更（イテレーション 2 で議論、イテレーション 3 で実施）
- `docs/issues/feat-044-convert-pink-to-blue-video/requirements.md` 主要修正
- `docs/issues/feat-044-convert-pink-to-blue-video/design.md` 主要修正
- `docs/issues/feat-044-convert-pink-to-blue-video/README.md` 概要を空間制約付きに更新

#### CLI 後方互換
本変更で `--json-dir` が必須になるため、既存実行コマンドは動かなくなる（後方互換ブレーク）。本案件は未クローズかつ手動テスト未通過のため後方互換考慮不要。

### 2.6 ユーザー承認待ち事項

イテレーション 3 着手前に以下の決定が必要:

- [ ] 採用案 (β) 胴体内接矩形限定で進めることの承認
- [ ] 矩形縮退時のフォールバック方針（スキップ → 元フレームそのまま、で OK か）
- [ ] requirements.md / design.md の主要修正に着手してよいか（再度レビュー 2 巡実施）
- [ ] イテレーション 3 のスコープ確認（ドキュメント修正のみか、コード修正までまとめてか）
