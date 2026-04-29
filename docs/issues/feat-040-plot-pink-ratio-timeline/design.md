# feat-040 機能設計書: pink_ratio 時系列可視化グラフ

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001（タイムラインデータ収集） | §4.1 |
| FR-002（Panel 1 散布図） | §4.2 |
| FR-003（Panel 2 pink_id=1 タイムライン） | §4.3 |
| FR-004（Panel 3 BB 数） | §4.4 |
| FR-005（Panel 4 差分） | §4.5 |
| FR-006（次点 BB 決定ロジック） | §4.6 |
| FR-007（CLI） | §4.7 |
| NFR-001（パフォーマンス） | §6 |
| NFR-002（対応環境） | §3 |
| NFR-003（出力品質） | §4.7 / §5 |

## 2. システム構成

### 2.1 モジュール構成

新規スクリプト 1 ファイル `scripts/plot_pink_ratio_timeline.py` を作成する。新規モジュール / クラス階層は導入しない。

```
scripts/plot_pink_ratio_timeline.py
├─ import
│   ├─ argparse / json / os / re / sys
│   ├─ pathlib.Path
│   ├─ dataclasses (dataclass, field)
│   ├─ matplotlib (Agg backend) / matplotlib.pyplot
│   └─ from postprocess_pink_id import MIN_PINK_RATIO
├─ データ構造
│   └─ TimelineData (dataclass)
├─ I/O
│   └─ load_json_frames(json_dir) -> dict[int, tuple[str, dict]]
├─ データ収集
│   ├─ extract_runner_up_ratio(people: list[dict]) -> float | None
│   └─ collect_timeline_data(frame_to_json, frame_start, frame_end) -> TimelineData
├─ 描画関数
│   ├─ plot_ratio_scatter(ax, data) -> None              # Panel 1
│   ├─ plot_pink_id_presence(ax, data) -> None           # Panel 2
│   ├─ plot_bb_count_breakdown(ax, data) -> None         # Panel 3
│   └─ plot_selected_minus_runnerup(ax, data) -> None    # Panel 4
└─ main()
```

### 2.2 依存関係

- `from postprocess_pink_id import MIN_PINK_RATIO` のため `sys.path.insert(0, os.path.dirname(__file__))` をファイル先頭に置く（前例: `visualize_patient_video.py`）
- `matplotlib.use("Agg")` を `import matplotlib.pyplot` より前に呼び、ヘッドレス環境で動作させる
- 循環依存なし（`postprocess_pink_id.py` は本スクリプトを import しない）

### 2.3 ディレクトリ構成

新規ファイル: `scripts/plot_pink_ratio_timeline.py` のみ。他ファイルの新規追加なし。

## 3. 技術スタック

| 項目 | 値 | 選定理由 |
|------|-----|----------|
| 言語 | Python 3.10.16 | プロジェクト既定 |
| パッケージ管理 | uv | プロジェクト既定 |
| 描画 | matplotlib（既存依存） | プロジェクト既存利用、追加導入なし |
| バックエンド | Agg | ヘッドレス環境で PNG 出力するため。X サーバ不要 |

追加ライブラリの導入は行わない。

## 4. 各機能の詳細設計

### 4.1 FR-001: タイムラインデータ収集

#### 4.1.1 データ構造

```python
@dataclass
class TimelineData:
    frames: list[int] = field(default_factory=list)

    # Panel 1 用: 全 BB のフラットリスト
    scatter_frames_selected: list[int] = field(default_factory=list)
    scatter_ratios_selected: list[float] = field(default_factory=list)
    scatter_frames_candidate: list[int] = field(default_factory=list)
    scatter_ratios_candidate: list[float] = field(default_factory=list)
    scatter_frames_noncand: list[int] = field(default_factory=list)
    scatter_ratios_noncand: list[float] = field(default_factory=list)

    # Panel 2 用
    has_pink_id: list[int] = field(default_factory=list)

    # Panel 3 用
    count_selected: list[int] = field(default_factory=list)
    count_candidate_other: list[int] = field(default_factory=list)
    count_non_candidate: list[int] = field(default_factory=list)

    # Panel 4 用
    selected_ratios: list[float | None] = field(default_factory=list)
    runnerup_ratios: list[float | None] = field(default_factory=list)
```

`frames` 系列とそれ以外（has_pink_id / count_* / selected_ratios / runnerup_ratios）は **同じ長さ N**（描画対象フレーム数）。`scatter_*` 系列は描画用フラットリストでフレーム数とは独立。

上記コードスニペットは意図の伝達目的であり、実装時はフィールド名・型を遵守する。

#### 4.1.2 データフロー

入力:
- `frame_to_json: dict[int, tuple[filename: str, content_dict: dict]]`（feat-037 と同形式）
- `frame_start: int`（描画開始フレーム、0 以上）
- `frame_end: int`（描画終了フレーム、-1 で最終）

出力:
- `TimelineData`

処理ステップ:
1. `sorted(frame_to_json.keys())` で昇順ループ
2. `frame_start <= frame_idx <= frame_end_resolved`（frame_end が -1 のときは最大値）の範囲のみ処理対象とする
3. 各フレームの `people` を取得し、各 BB について以下を仕分け:
   - `pink_id == 1` → Panel 1 selected 系列、`count_selected` インクリメント
   - `pink_id != 1 かつ ratio >= MIN_PINK_RATIO` → Panel 1 candidate 系列、`count_candidate_other` インクリメント
   - `pink_id != 1 かつ ratio < MIN_PINK_RATIO` → Panel 1 noncand 系列、`count_non_candidate` インクリメント
4. `selected_ratios[fi]`: 選択 BB の `pink_ratio`（無いフレームは None）
5. `runnerup_ratios[fi]`: §4.6 のロジックで決定
6. `has_pink_id[fi]`: 選択 BB が存在すれば 1、無ければ 0

#### 4.1.3 エラーハンドリング

- `pink_ratio` キー欠落: 0.0 として扱う（FR-001 AC-001-3、後方互換）
- `pink_id` キー欠落: -1 として扱う
- JSON 解析失敗 / `people` キー欠落: `load_json_frames` で WARNING ログを出して空 people として処理（feat-037 と同じ規約）

#### 4.1.4 境界条件

- `people == []` のフレーム: 全 count = 0、selected_ratios=None、runnerup_ratios=None、has_pink_id=0、scatter には何も追加しない。frames リストには追加する（描画パネルの x 軸を連続させるため）
- `frame_start > 利用可能な最大フレーム番号`: フレームゼロで PNG を出力する（タイトルに "0 frames drawn" と表示）。エラー終了はしない（CLI バリデーションは Must だが空グラフ出力でも要件は満たせる）
- `frame_end < frame_start`: ERROR ログ出して `sys.exit(1)`
- **JSON ディレクトリ内の `*_{6 桁}.json` ファイルが 0 件**: `load_json_frames` が `feat-037` 由来の規約として `print("ERROR: No JSON files found in {json_dir}")` 後 `sys.exit(1)` で異常終了する。本スクリプトもこの規約をそのまま流用する

### 4.2 FR-002: Panel 1 散布図

#### 4.2.1 描画ロジック

```python
def plot_ratio_scatter(ax: plt.Axes, data: TimelineData) -> None:
    ax.scatter(data.scatter_frames_noncand, data.scatter_ratios_noncand,
               s=1, c="lightgray", alpha=0.2, label="non-candidate (<0.03)")
    ax.scatter(data.scatter_frames_candidate, data.scatter_ratios_candidate,
               s=2, c="black", alpha=0.4, label="candidate (>=0.03, pink_id=-1)")
    ax.scatter(data.scatter_frames_selected, data.scatter_ratios_selected,
               s=4, c="magenta", alpha=0.7, label="selected (pink_id=1)")
    ax.axhline(MIN_PINK_RATIO, color="red", linestyle="--",
               linewidth=0.7, label=f"threshold={MIN_PINK_RATIO}")
    ax.set_ylabel("pink_ratio")
    ax.set_ylim(0.0, 1.05)
    ax.legend(loc="upper right", fontsize="small")
```

描画順は **noncand → candidate → selected** の順で重ね、選択点が必ず最前面に来るようにする。意図の伝達目的のスニペット。

#### 4.2.2 境界条件

- 全系列が空（フレームゼロ）: scatter は何も描画しない、閾値ラインのみ表示
- 値が 1.0 を超える ratio が万一存在: 縦軸 ylim=1.05 でクリップ表示（`pink_ratio` の値域は [0,1] のためあり得ないが防御的に固定）

### 4.3 FR-003: Panel 2 pink_id=1 タイムライン

```python
def plot_pink_id_presence(ax: plt.Axes, data: TimelineData) -> None:
    ax.fill_between(data.frames, data.has_pink_id,
                    step="mid", color="hotpink", alpha=0.7)
    ax.set_ylabel("pink_id=1\n(0/1)")
    ax.set_ylim(-0.1, 1.3)
```

feat-037 の `plot_pink_id_presence` と同等の見た目にする。

### 4.4 FR-004: Panel 3 BB 数

```python
def plot_bb_count_breakdown(ax: plt.Axes, data: TimelineData) -> None:
    ax.plot(data.frames, data.count_selected,
            linewidth=0.5, color="magenta", label="pink_id=1")
    ax.plot(data.frames, data.count_candidate_other,
            linewidth=0.5, color="black", label="pink_id=-1, ratio>=0.03")
    ax.plot(data.frames, data.count_non_candidate,
            linewidth=0.5, color="gray", label="pink_id=-1, ratio<0.03")
    ax.set_ylabel("BB count")
    ax.legend(loc="upper right", fontsize="small")
```

### 4.5 FR-005: Panel 4 差分

#### 4.5.1 描画ロジック

```python
def plot_selected_minus_runnerup(ax: plt.Axes, data: TimelineData) -> None:
    diffs_x, diffs_y = [], []
    close_x = []  # frames where |diff| < 0.05
    for f, s, r in zip(data.frames, data.selected_ratios, data.runnerup_ratios):
        if s is None or r is None:
            continue
        d = s - r
        diffs_x.append(f); diffs_y.append(d)
        if d < 0.05:
            close_x.append(f)
    # 赤背景帯: 連続区間にまとめて axvspan
    for x_start, x_end in _group_consecutive(close_x):
        ax.axvspan(x_start - 0.5, x_end + 0.5, color="red", alpha=0.15)
    ax.scatter(diffs_x, diffs_y, s=2, c="blue", alpha=0.5)
    ax.axhline(0.0, color="black", linestyle="--",
               linewidth=0.5, alpha=0.5)
    ax.set_ylabel("selected − runner-up\nratio")
    ax.set_ylim(-0.5, 1.05)
```

`_group_consecutive` は連続するフレーム番号を `(start, end)` の区間にまとめる純関数。仕様:

- 入力: 昇順ソート済みの整数リスト（フレーム番号）
- 「連続」の判定基準: **隣接要素の差が 1 のもの**（`values[k+1] - values[k] == 1`）を同一区間にまとめる。差が 2 以上空けば区間を分割する
- 出力: `(start, end)` の整数タプルのリスト。単独要素は `(v, v)` として返す
- 例: `[5, 6, 7, 10, 11, 20] -> [(5,7), (10,11), (20,20)]`

`axvspan(x_start - 0.5, x_end + 0.5, ...)` の範囲指定の意図: フレーム番号は離散整数だが axvspan は連続範囲を塗るため、各フレームを「中心 ± 0.5」の幅 1.0 の帯として描き、隣接フレーム同士で隙間なく塗られるようにする（matplotlib の `step="mid"` と同じ視覚規約）。

1000 個の連続フレームをそれぞれ axvspan するとパフォーマンスが落ちるため、連続区間にまとめてから 1 回の axvspan 呼び出しに集約する最適化を兼ねる。

#### 4.5.2 「際どい差分」の定義

条件は `selected_ratio − runner_up_ratio < 0.05`（負値含む）。すなわち「選択 BB の `pink_ratio` 優位性が 0.05 未満、または選択 BB が ratio 上で 1 位ですらない（差分が負）」状態を指す。連続性ボーナスで反転して選ばれたケース（差分が負またはゼロに近い）も自動的に強調対象となる。コード `if d < 0.05:` で実装する。

#### 4.5.3 境界条件

- 選択 BB なしのフレーム: 描画なし
- BB が 1 個のフレーム: 次点なし、描画なし

### 4.6 FR-006: 次点 BB 決定ロジック

#### 4.6.1 ロジック（採用案: a-2）

```python
def extract_runner_up_ratio(people: list[dict]) -> float | None:
    """全 BB の pink_ratio を降順ソートし、2 位の値を返す。

    案 a-2: 選択 BB を含めた全体ランキングでの 2 位。
    BB が 0–1 個のフレームでは None。
    """
    ratios = [p.get("pink_ratio", 0.0) for p in people]
    if len(ratios) < 2:
        return None
    ratios_sorted = sorted(ratios, reverse=True)
    return ratios_sorted[1]
```

#### 4.6.2 設計判断の記録（ADR）

- **採用案 a-2 (全体での 2 位)**: 連続性ボーナス（`pink_ratio + 0.05*IoU`）により選択 BB が ratio 1 位でない場合、誤選択の温床として「2 位 ratio が選択 ratio より大きい」事象を直接観察したい。「選択 BB を除いた中で 1 位」(案 a-1) では選択 BB が 1 位の通常ケースと選択 BB が 2 位以下の異常ケースが同じ計算結果になり区別不能
- **却下案 a-1 (選択 BB を除いた最大)**: 上記の理由で却下

#### 4.6.3 境界条件

- BB 0 個 / 1 個: None を返す
- 同値タイ: Python `sorted` の安定性により、入力順（= `people` の順）が後の方の要素が後方に置かれる。同値の 2 位はどちらが返ってもグラフへの影響は無視できる
- 全 BB が同一値: 2 位の値 = 1 位の値、差分は 0

### 4.7 FR-007 CLI

#### 4.7.1 引数定義

```python
parser.add_argument("--json-dir", required=True,
                    help="Input JSON directory (pink_id / pink_ratio assigned)")
parser.add_argument("--out-path", required=True,
                    help="Output PNG file path")
parser.add_argument("--frame-start", type=int, default=0,
                    help="Frame number (6-digit suffix in JSON filename) "
                         "to start drawing. Default: 0")
parser.add_argument("--frame-end", type=int, default=-1,
                    help="Frame number (6-digit suffix in JSON filename) "
                         "to end drawing. -1 = max frame in input. Default: -1")
```

#### 4.7.2 main() の流れ

1. 引数パース
2. `--json-dir` の存在確認、無ければ ERROR で `sys.exit(1)`
3. `frame_end != -1 and frame_end < frame_start` のときは ERROR で `sys.exit(1)`
4. `load_json_frames` で全 JSON を読む
5. `frame_end == -1` のとき、`max(frame_to_json.keys())` を frame_end に解決
6. `collect_timeline_data(frame_to_json, frame_start, frame_end)`
7. `plt.subplots(4, 1, figsize=(16, 12), sharex=True)`
8. 各 `plot_*` 呼び出し
9. タイトル: `"pink_ratio timeline — {dir_name} ({n_drawn} frames drawn / {n_total} total)"`
10. 親ディレクトリ自動作成
11. `fig.savefig(args.out_path, dpi=150)`、`plt.close(fig)`
12. ログ出力: 入力フレーム数、描画フレーム数、出力パス、選択 BB ありフレーム数、際どい差分フレーム数

#### 4.7.3 ログ仕様

```
Loaded {N_total} frames from JSON
Draw range: {frame_start} - {frame_end} ({N_drawn} frames)
Frames with pink_id=1: {count}
Frames with close margin (selected − runner-up < 0.05): {count}
Saved: {out_path}
```

## 5. ファイル・ディレクトリ設計

### 5.1 入力

`--json-dir` 配下の `*_{6 桁}.json`。スキーマは feat-039 改修済み `postprocess_pink_id.py` の出力（各 `people[i]` に `pink_id`, `pink_ratio` を含む）。

### 5.2 出力

`--out-path` で指定された PNG 1 枚。命名は呼び出し側の自由（例: `experiments/results/camSony1_L_pink_ratio_timeline.png`）。

### 5.3 想定ディレクトリ配置例

```
experiments/results/
├─ camSony1_L_pink_json/                # 入力（feat-039 出力）
│   └─ camSony1_L_*.json
└─ camSony1_L_pink_ratio_timeline.png   # 本スクリプトの出力
```

## 6. ログ・デバッグ設計

- ログレベル: 標準出力に `print` のみ（feat-037 と統一）
- WARNING: JSON 解析失敗、`pink_ratio` フィールド欠落の検出（最初の 3 件まで個別出力、それ以降は集計）
- ERROR: `--json-dir` 不在、`frame_end < frame_start` の不正引数
- INFO: ロード件数、描画件数、出力パス、`pink_id=1` のフレーム数、際どい差分のフレーム数

## 7. インターフェース定義

### 7.1 公開関数シグネチャ

| 関数 | シグネチャ |
|------|-----------|
| `load_json_frames` | `(json_dir: str) -> dict[int, tuple[str, dict]]` |
| `extract_runner_up_ratio` | `(people: list[dict]) -> float \| None` |
| `collect_timeline_data` | `(frame_to_json: dict[int, tuple[str, dict]], frame_start: int, frame_end: int) -> TimelineData` |
| `plot_ratio_scatter` | `(ax: plt.Axes, data: TimelineData) -> None` |
| `plot_pink_id_presence` | `(ax: plt.Axes, data: TimelineData) -> None` |
| `plot_bb_count_breakdown` | `(ax: plt.Axes, data: TimelineData) -> None` |
| `plot_selected_minus_runnerup` | `(ax: plt.Axes, data: TimelineData) -> None` |
| `_group_consecutive` | `(values: list[int]) -> list[tuple[int, int]]`（プライベート） |
| `main` | `() -> None` |

### 7.2 モジュール間の呼び出し方向

- 本スクリプト → `postprocess_pink_id`（`MIN_PINK_RATIO` 定数のみ参照）
- 逆方向の依存なし

## 8. 設計判断の記録（全体 ADR サマリ）

- **§4.6 次点 BB の定義**: 案 a-2（全体 2 位）採用。選択 BB が ratio 1 位でない事象（連続性ボーナスによる反転）を直接観察可能にするため
- **際どい差分の閾値 0.05**: `IOU_CONT_WEIGHT = 0.05` と整合。連続性ボーナス 1 ステップ分の効果に相当し、「ボーナスで順位が逆転し得る範囲」を可視化する根拠ある値として選定
- **`MIN_PINK_RATIO` を import**: ハードコード重複を避ける。前例 `merge_halpe26.HALPE26_SKELETON` を `visualize_patient_video.py` で import している
- **CLI フラグでパネル選択を可能にしない**: 4 パネル固定。デバッグ用途のため複雑化を避ける（YAGNI）
- **動画ファイルを参照しない**: pink_ratio は JSON に保存済み、再計算不要。OpenCV 依存を持ち込まず軽量に保つ
- **Panel 4 の縦軸下限 -0.5**: 選択 BB が ratio 1 位ではないケース（差分が負）も視覚化するため、0 下限ではなく負側にも余裕を取る

## 9. 実装完了後のチェックリスト

- [ ] `scripts/plot_pink_ratio_timeline.py` を新規作成
- [ ] `from postprocess_pink_id import MIN_PINK_RATIO` で定数を import している
- [ ] 4 パネル PNG が `--out-path` に出力される
- [ ] camSony1_S（小規模）で実行し PNG を目視確認
- [ ] camSony1_L（大規模、321K フレーム）で実行し処理時間が 120 秒以内、PNG が破綻なく出力される
- [ ] `--frame-start` / `--frame-end` で部分描画ができる
- [ ] `scripts/README.md` に新スクリプトの使い方を追記
- [ ] CLAUDE.md のディレクトリ構成に新ファイルを追加
- [ ] CLAUDE.md の「完了済み案件」に feat-040 を追記
- [ ] `docs/BACKLOG.md` の Open テーブルを Closed に変更、Closed テーブルに追記
- [ ] `docs/issues/feat-040-plot-pink-ratio-timeline/README.md` のステータスを Closed に更新
