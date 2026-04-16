"""patient_id ポストプロセス: 既存 HALPE 26 JSON に pink_track_id を付与する (feat-036)

feat-034 ロードマップの Stage 4 に対応。pink_id（種）と track_id（拡張手段）を
階層構造で組み合わせ、各人物エントリに `pink_track_id: int` を付与する。

入力:
  - HALPE 26 OpenPose JSON ディレクトリ（feat-035 の track_id と
    feat-033 の pink_id が両方付与済み）

出力:
  指定した出力ディレクトリに、入力と同じ命名規約で JSON を書き出す。
  各 people エントリに pink_track_id: int を追加（生 dict 保持設計）。

値域:
  1  : 患者（pink_id=1 の種、または patient_track_ids に含まれる track_id の BB）
  -1 : 非患者
  -2 : 重複 BB（同一フレームに複数の pink_id=1 が出た場合の bbox_score 最大以外）
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path


# ---------------- Constants ----------------
PINK_TRACK_ID_PATIENT: int = 1
PINK_TRACK_ID_NOT_PATIENT: int = -1
PINK_TRACK_ID_DUPLICATE: int = -2
PROGRESS_INTERVAL_FRAMES: int = 3000


# ---------------- 純関数 ----------------
def _is_number(v) -> bool:
    """数値判定。bool は int のサブクラスだが除外する。"""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _score_for_selection(person: dict, frame_idx: int, person_idx: int) -> float:
    """bbox_score を取り出す。欠損/非数値なら -inf を返し WARNING を出す。"""
    score = person.get("bbox_score")
    if not _is_number(score):
        print(
            f"WARNING: Invalid bbox_score in frame {frame_idx} person {person_idx}"
            f" with pink_id=1, treating as score=-inf"
        )
        return float("-inf")
    return float(score)


def classify_frame_pink(
    people: list[dict],
    frame_idx: int,
) -> tuple[int | None, int | None, set[int]]:
    """1 フレームの pink_id=1 候補から有効 BB と重複 BB を特定する (FR-002)。

    Returns:
        (valid_pink_idx, valid_track_id, duplicate_person_idxs)

        - valid_pink_idx: 有効 pink_id=1 BB の people 内インデックス
          （該当なしなら None）
        - valid_track_id: 有効 BB の track_id（無効/欠損/<=0 の場合は None）
        - duplicate_person_idxs: 重複 pink_id=1 BB のインデックス集合
    """
    pink_candidates: list[int] = [
        i for i, p in enumerate(people) if p.get("pink_id") == 1
    ]
    if not pink_candidates:
        return None, None, set()

    best_idx = pink_candidates[0]
    best_score = _score_for_selection(people[best_idx], frame_idx, best_idx)
    for i in pink_candidates[1:]:
        score = _score_for_selection(people[i], frame_idx, i)
        if score > best_score:
            best_score = score
            best_idx = i

    valid_person = people[best_idx]
    tid = valid_person.get("track_id")
    if _is_number(tid) and int(tid) >= 1:
        valid_track_id: int | None = int(tid)
    else:
        valid_track_id = None

    duplicate_person_idxs: set[int] = {i for i in pink_candidates if i != best_idx}
    return best_idx, valid_track_id, duplicate_person_idxs


def build_patient_state(
    frame_to_json: dict[int, tuple[str, dict]],
) -> tuple[set[int], dict[int, tuple[int | None, set[int]]]]:
    """全フレーム走査でパス 1 の結果を構築する (FR-003)。"""
    patient_track_ids: set[int] = set()
    frame_classification: dict[int, tuple[int | None, set[int]]] = {}

    for frame_idx in sorted(frame_to_json.keys()):
        _, content_dict = frame_to_json[frame_idx]
        people = content_dict.get("people", [])

        valid_pink_idx, valid_track_id, duplicate_person_idxs = classify_frame_pink(
            people, frame_idx
        )
        if valid_track_id is not None:
            patient_track_ids.add(valid_track_id)
        frame_classification[frame_idx] = (valid_pink_idx, duplicate_person_idxs)

        if frame_idx % PROGRESS_INTERVAL_FRAMES == 0:
            print(f"Pass 1 processing frame {frame_idx:06d}")

    return patient_track_ids, frame_classification


def _score_for_dedup(person: dict) -> float:
    """デデュプ用 bbox_score 取得。欠損/非数値なら -inf。WARNING は出さない。"""
    score = person.get("bbox_score")
    if not _is_number(score):
        return float("-inf")
    return float(score)


def assign_pink_track_ids(
    people: list[dict],
    valid_pink_idx: int | None,
    duplicate_person_idxs: set[int],
    patient_track_ids: set[int],
) -> list[int]:
    """各 BB に pink_track_id を割り当てる (FR-004)。

    処理ステップ A〜D（requirements.md FR-004 と対応）:
      ステップ A: result を初期化
      ステップ B: 各 BB を階層 1〜4 で判定
        階層 1) 重複除外: -2
        階層 2) 種（pink_id=1 直接判定）: 1
        階層 3) 拡張（track_id 経由の伝播）: 1
        階層 4) 非患者: -1
      ステップ C: 後処理デデュプ（要求 E）
      ステップ D: result を返す
    """
    # ステップ A: 初期化
    result: list[int] = [PINK_TRACK_ID_NOT_PATIENT] * len(people)
    # ステップ B: 階層 1〜4 で判定
    for i, person in enumerate(people):
        # 階層 1) 重複除外
        if i in duplicate_person_idxs:
            result[i] = PINK_TRACK_ID_DUPLICATE
            continue
        # 階層 2) 種: pink_id=1 による直接判定（track_id の状態に依存しない）
        if i == valid_pink_idx:
            result[i] = PINK_TRACK_ID_PATIENT
            continue
        # 階層 3) 拡張: 種が付いた track_id を時間方向へ伝播
        tid = person.get("track_id")
        if _is_number(tid) and int(tid) >= 1 and int(tid) in patient_track_ids:
            result[i] = PINK_TRACK_ID_PATIENT
        # 階層 4) 非患者: 初期値 -1 のまま

    # ステップ C: 後処理デデュプ（要求 E）
    patient_indices = [i for i, v in enumerate(result) if v == PINK_TRACK_ID_PATIENT]
    if len(patient_indices) >= 2:
        best_i = patient_indices[0]
        best_score = _score_for_dedup(people[best_i])
        for i in patient_indices[1:]:
            score = _score_for_dedup(people[i])
            if score > best_score:
                best_score = score
                best_i = i
        for i in patient_indices:
            if i != best_i:
                result[i] = PINK_TRACK_ID_DUPLICATE

    # ステップ D: 返却
    return result


# ---------------- I/O ----------------
def load_json_frames(json_dir: str) -> dict[int, tuple[str, dict]]:
    """JSON ディレクトリから全フレームの生 dict を読み込む (FR-001)。

    Returns:
        {frame_idx: (original_filename, content_dict)}
    """
    json_path = Path(json_dir)
    json_files = sorted(json_path.glob("*.json"))
    if not json_files:
        print(f"ERROR: No JSON files found in {json_dir}")
        sys.exit(1)

    pattern = re.compile(r"_(\d{6})\.json$")
    out: dict[int, tuple[str, dict]] = {}
    for jf in json_files:
        m = pattern.search(jf.name)
        if m is None:
            continue
        fidx = int(m.group(1))
        try:
            with open(jf) as f:
                content = json.load(f)
        except json.JSONDecodeError:
            print(f"WARNING: Failed to parse {jf.name}, treating as empty")
            content = {"version": 1.3, "people": []}
        out[fidx] = (jf.name, content)
    return out


def write_json_frame(out_path: str, data: dict) -> None:
    with open(out_path, "w") as f:
        json.dump(data, f)


def print_summary(
    total_frames: int,
    patient_track_ids: set[int],
    frames_patient: int,
    frames_duplicate: int,
    elapsed: float,
    out_dir: str,
) -> None:
    fps = total_frames / elapsed if elapsed > 0 else 0.0
    print()
    print(f"Total frames: {total_frames}")
    print(f"Unique patient track_ids: {len(patient_track_ids)}")
    print(f"Frames with pink_track_id=1 (patient): {frames_patient}")
    print(f"Frames with pink_track_id=-2 (duplicate): {frames_duplicate}")
    print(f"Processing time: {elapsed:.1f} sec ({fps:.1f} fps)")
    print(f"Output directory: {out_dir}")


# ---------------- Main ----------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Add pink_track_id (patient id) to HALPE 26 JSON "
            "by combining pink_id and track_id"
        )
    )
    parser.add_argument(
        "--json-dir", required=True, help="Input HALPE 26 JSON directory"
    )
    parser.add_argument(
        "--out-dir", required=True,
        help="Output JSON directory (must differ from --json-dir)",
    )
    args = parser.parse_args()

    # 上書き防止
    if os.path.realpath(args.json_dir) == os.path.realpath(args.out_dir):
        print("ERROR: --out-dir must differ from --json-dir to prevent overwriting")
        sys.exit(1)

    os.makedirs(args.out_dir, exist_ok=True)
    start_time = time.time()

    frame_to_json = load_json_frames(args.json_dir)
    print(f"Loaded {len(frame_to_json)} frames from JSON")

    # パス 1: patient_track_ids 集合と frame_classification を構築
    print("Pass 1: Scanning frames to build patient_track_ids...")
    patient_track_ids, frame_classification = build_patient_state(frame_to_json)
    print(
        f"Pass 1 done: patient_track_ids = {len(patient_track_ids)} unique track_ids"
    )

    # パス 2: pink_track_id を付与して出力
    print("Pass 2: Assigning pink_track_id...")
    frames_patient = 0
    frames_duplicate = 0
    for frame_idx in sorted(frame_to_json.keys()):
        filename, content_dict = frame_to_json[frame_idx]
        people = content_dict.get("people", [])
        valid_pink_idx, duplicate_person_idxs = frame_classification[frame_idx]

        assigned = assign_pink_track_ids(
            people,
            valid_pink_idx,
            duplicate_person_idxs,
            patient_track_ids,
        )

        for i, person in enumerate(people):
            person["pink_track_id"] = assigned[i]

        if any(v == PINK_TRACK_ID_PATIENT for v in assigned):
            frames_patient += 1
        if any(v == PINK_TRACK_ID_DUPLICATE for v in assigned):
            frames_duplicate += 1

        out_path = os.path.join(args.out_dir, filename)
        write_json_frame(out_path, content_dict)

        if frame_idx % PROGRESS_INTERVAL_FRAMES == 0:
            print(f"Pass 2 processing frame {frame_idx:06d}")

    elapsed = time.time() - start_time
    print_summary(
        total_frames=len(frame_to_json),
        patient_track_ids=patient_track_ids,
        frames_patient=frames_patient,
        frames_duplicate=frames_duplicate,
        elapsed=elapsed,
        out_dir=args.out_dir,
    )


if __name__ == "__main__":
    main()
