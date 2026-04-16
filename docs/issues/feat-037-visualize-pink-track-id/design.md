# feat-037: pink_track_id 時系列可視化グラフ — 機能設計書

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001（入力 JSON 読み込み） | §4.1 |
| FR-002（パネル 1: pink_track_id=1 有無） | §4.2 |
| FR-003（パネル 2: BB 数内訳） | §4.3 |
| FR-004（パネル 3: track_id 推移） | §4.4 |
| FR-005（パネル 4: bbox_score 推移） | §4.5 |
| FR-006（パネル 5: pink_id=1 有無） | §4.6 |
| FR-007（グラフ出力） | §4.7 |
| FR-008（CLI インタフェース） | §4.8 |

## 2. システム構���

### 2.1 モジュール構成

```
scripts/plot_pink_track_timeline.py
├─ 定数
│   └─ (描画色等)
├─ データ収集
│   ├─ load_json_frames(json_dir) → dict[int, tuple[str, dict]]    (FR-001)
│   └─ collect_timeline_data(frame_to_json) → TimelineData          (FR-001 後処理)
├─ 描画関数
│   ├─ plot_patient_presence(ax, data)       (FR-002)
│   ├─ plot_bb_count_breakdown(ax, data)     (FR-003)
│   ├─ plot_patient_track_id(ax, data)       (FR-004)
│   ├─ plot_patient_bbox_score(ax, data)     (FR-005)
│   └─ plot_pink_id_presence(ax, data)       (FR-006)
├─ 出力
│   └─ save_figure(fig, out_path)            (FR-007)
└─ エントリポイント
    └─ main()                                 (FR-008)
```

### 2.2 データ構造

`collect_timeline_data` が返すデータ構造（`TimelineData` は NamedTuple ���たは dataclass）:

```python
class TimelineData:
    frames: list[int]                    # フレーム番号の昇順リスト
    has_patient: list[int]               # 各フレームで pink_track_id=1 があるか (0/1)
    has_pink_id: list[int]               # 各フレームで pink_id=1 があるか (0/1)
    count_patient: list[int]             # 各フレームの pink_track_id=1 の BB 数
    count_not_patient: list[int]         # 各フレームの pink_track_id=-1 の BB 数
    count_duplicate: list[int]           # 各フレームの pink_track_id=-2 の BB 数
    patient_track_ids: list[int | None]  # 各フレームの pink_track_id=1 BB の track_id��なければ None）
    patient_bbox_scores: list[float | None]  # 各フレームの pink_track_id=1 BB の bbox_score（なければ None）
```

## 3. 技術スタック

| 項目 | 値 | 選定理由 |
|------|-----|----------|
| 言語 | Python 3.10.16 | プロジェクト既定 |
| matplotlib | 既存 uv 環境 | 標準的なグラフ描画ライブラリ |
| 標準ライブラリ | `argparse`, `json`, `os`, `re`, `sys`, `pathlib` | JSON 読み込み・CLI |

numpy は matplotlib が内部で使用するが、本スクリプトでは明示的に import しない。

## 4. 各機能の詳細設計

### 4.1 FR-001: 入力 JSON 読��込みとデータ収集

#### load_json_frames

feat-035/036 と同一の `load_json_frames` パターンを流用する。

#### collect_timeline_data

```python
def collect_timeline_data(
    frame_to_json: dict[int, tuple[str, dict]],
) -> TimelineData:
    frames = []
    has_patient = []
    has_pink_id = []
    count_patient = []
    count_not_patient = []
    count_duplicate = []
    patient_track_ids = []
    patient_bbox_scores = []

    for frame_idx in sorted(frame_to_json.keys()):
        _, content_dict = frame_to_json[frame_idx]
        people = content_dict.get("people", [])

        frames.append(frame_idx)

        # pink_track_id 集計
        n_patient = 0
        n_not_patient = 0
        n_duplicate = 0
        p_track_id = None
        p_bbox_score = None
        found_pink_id = False

        for person in people:
            ptid = person.get("pink_track_id")
            # pink_track_id が未付与（None）の BB は non-patient として扱う
            if ptid == 1:
                n_patient += 1
                p_track_id = person.get("track_id")
                p_bbox_score = person.get("bbox_score")
            elif ptid == -2:
                n_duplicate += 1
            else:
                n_not_patient += 1
            if person.get("pink_id") == 1:
                found_pink_id = True

        has_patient.append(1 if n_patient > 0 else 0)
        has_pink_id.append(1 if found_pink_id else 0)
        count_patient.append(n_patient)
        count_not_patient.append(n_not_patient)
        count_duplicate.append(n_duplicate)
        patient_track_ids.append(p_track_id)
        patient_bbox_scores.append(p_bbox_score)

    return TimelineData(
        frames=frames,
        has_patient=has_patient,
        has_pink_id=has_pink_id,
        count_patient=count_patient,
        count_not_patient=count_not_patient,
        count_duplicate=count_duplicate,
        patient_track_ids=patient_track_ids,
        patient_bbox_scores=patient_bbox_scores,
    )
```

### 4.2 FR-002: パネル 1 — `pink_track_id=1` の有無

```python
def plot_patient_presence(ax, data: TimelineData) -> None:
    ax.fill_between(data.frames, data.has_patient, step="mid", alpha=0.7, color="green")
    ax.set_ylabel("Patient\n(0/1)")
    ax.set_ylim(-0.1, 1.3)
    # タイトルは main() 側で入力ディレクトリ名を���めて設定する（AC-007-3）
```

### 4.3 FR-003: パネル 2 — BB 数の内訳

```python
def plot_bb_count_breakdown(ax, data: TimelineData) -> None:
    ax.plot(data.frames, data.count_patient, linewidth=0.5, color="green", label="=1 (patient)")
    ax.plot(data.frames, data.count_not_patient, linewidth=0.5, color="gray", label="=-1 (not patient)")
    ax.plot(data.frames, data.count_duplicate, linewidth=0.5, color="orange", label="=-2 (duplicate)")
    ax.set_ylabel("BB count")
    ax.legend(loc="upper right", fontsize="small")
```

### 4.4 FR-004: パネル 3 — `track_id` 推移

```python
def plot_patient_track_id(ax, data: TimelineData) -> None:
    xs = [f for f, t in zip(data.frames, data.patient_track_ids) if t is not None]
    ys = [t for t in data.patient_track_ids if t is not None]
    ax.scatter(xs, ys, s=1, color="blue", alpha=0.5)
    ax.set_ylabel("track_id\n(patient)")
```

`patient_track_ids` が `None`（そのフレームに pink_track_id=1 が存在しない）のフレームはプロットしない。散布図（`scatter`）で `s=1`（小さい点）にし、321K フレームでも描画可能にする。

### 4.5 FR-005: パネル 4 — `bbox_score` 推移

```python
def plot_patient_bbox_score(ax, data: TimelineData) -> None:
    xs = [f for f, s in zip(data.frames, data.patient_bbox_scores) if s is not None]
    ys = [s for s in data.patient_bbox_scores if s is not None]
    ax.scatter(xs, ys, s=1, color="purple", alpha=0.5)
    ax.set_ylabel("bbox_score\n(patient)")
    ax.set_ylim(0.0, 1.05)
```

### 4.6 FR-006: パネル 5 — `pink_id=1` の有無

```python
def plot_pink_id_presence(ax, data: TimelineData) -> None:
    ax.fill_between(data.frames, data.has_pink_id, step="mid", alpha=0.7, color="hotpink")
    ax.set_ylabel("pink_id=1\n(0/1)")
    ax.set_ylim(-0.1, 1.3)
    ax.set_xlabel("Frame index")
```

### 4.7 FR-007: グラフ出力

```python
def main():
    # ...
    import matplotlib
    matplotlib.use("Agg")  # ヘッドレス環境でのクラッシュ防止
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(5, 1, figsize=(16, 12), sharex=True)

    plot_patient_presence(axes[0], data)
    plot_bb_count_breakdown(axes[1], data)
    plot_patient_track_id(axes[2], data)
    plot_patient_bbox_score(axes[3], data)
    plot_pink_id_presence(axes[4], data)

    # タイトルに入力ディレクトリ名とフレーム数を含める（AC-007-3）
    dir_name = os.path.basename(os.path.normpath(args.json_dir))
    axes[0].set_title(f"pink_track_id timeline — {dir_name} ({len(data.frames)} frames)")

    plt.tight_layout()
    # 出力先ディレクトリが存在しない場合は自動作成（AC-008-2）
    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f"Saved: {out_path}")
```

**ヘッドレス環境対応**: `matplotlib.use("Agg")` を `import matplotlib.pyplot as plt` より前に呼ぶことで、`TkAgg` 等の GUI バックエンドに依存せず `savefig` が動作する。実装時はスクリプト先頭で `matplotlib.use("Agg")` を呼ぶ（`import matplotlib.pyplot as plt` より上に配置）。

### 4.8 FR-008: CLI インタフェース

```python
parser = argparse.ArgumentParser(
    description="Plot pink_track_id timeline from HALPE 26 JSON"
)
parser.add_argument("--json-dir", required=True, help="Input JSON directory")
parser.add_argument("--out-path", required=True, help="Output PNG file path")
```

## 5. インターフェース定義（関数シグネチャ）

```python
def load_json_frames(json_dir: str) -> dict[int, tuple[str, dict]]: ...
def collect_timeline_data(frame_to_json: dict[int, tuple[str, dict]]) -> TimelineData: ...
def plot_patient_presence(ax, data: TimelineData) -> None: ...
def plot_bb_count_breakdown(ax, data: TimelineData) -> None: ...
def plot_patient_track_id(ax, data: TimelineData) -> None: ...
def plot_patient_bbox_score(ax, data: TimelineData) -> None: ...
def plot_pink_id_presence(ax, data: TimelineData) -> None: ...
def main() -> None: ...
```

## 6. 設計判断の記録（ADR）

### ADR-001: 散布図を使用（折れ線ではなく）

- **採用案**: パネル 3/4 で `scatter(s=1)` を使用
- **却下案**: 折れ線グラフ (`plot`)
- **理由**: 321K フレームの折れ線は描画コストが高く、`pink_track_id=1` が存在しないフレーム（=`None`）で線が途切れる処理も必要。散布図なら `None` を除外するだけでよく、大量点でも `alpha=0.5` で傾向が視認可能

### ADR-002: 1 ファイル完結

- **採用案**: `scripts/plot_pink_track_timeline.py` 1 ファイルで完��
- **理由**: feat-035/036 と同じ流儀。`load_json_frames` の重複は将来の共通化で対応
