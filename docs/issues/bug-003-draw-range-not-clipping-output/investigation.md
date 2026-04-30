# bug-003: --draw-start / --draw-end が出力動画範囲を制限しない — 修正計画

## イテレーション1 (2026-04-29)

### 1.1 不具合の特定

- **現在の動作**: `scripts/visualize_patient_video.py` で `--draw-start 29519 --draw-end 30915` を指定すると、フレーム 29519–30915 にのみオーバーレイ（BB / スケルトン / ID テキスト / 診断ラベル / Frame番号）が描画される。しかし、その範囲外のフレームも素のフレームとして出力 MP4 に書き込まれるため、出力 MP4 は入力と同じ 321239 フレームとなる。
- **再現手順**: README.md「再現手順」を参照。camSony1_L.mp4（321239 フレーム）に対し `--draw-start 29519 --draw-end 30915` を指定 → 出力 MP4 に全 321239 フレームが含まれる。
- **期待する動作**: 指定範囲のフレームのみが出力 MP4 に含まれる（出力フレーム数 = `draw_end - draw_start + 1`、本例では 1397 フレーム）。範囲外のフレームはデコード・エンコードとも行われず、処理時間が短縮される。
- **エラーメッセージ**: なし（クラッシュではなく挙動の不一致）

### 1.2 原因分析

- **原因箇所**: `scripts/visualize_patient_video.py` 280–304 行（フレームループ）
  ```python
  280:    while True:
  281:        ret, frame = cap.read()
  282:        if not ret:
  283:            break
  284:
  285:        draw_frame_number(frame, frame_idx)
  286:
  287:        in_draw_range = (frame_idx >= args.draw_start) and (
  288:            draw_end == -1 or frame_idx <= draw_end
  289:        )
  290:
  291:        if in_draw_range:
  292:            json_path = os.path.join(...)
  293:            people = load_frame_json(json_path)
  294:            ...（描画処理）...
  302:                draw_person(frame, person, color, args.id_type, args.kpt_thr, debug_flags)
  303:
  304:        writer.write(frame)  # ← in_draw_range の外
  ```
- **原因の説明**: `writer.write(frame)` が `if in_draw_range:` ブロックの**外**にあるため、描画範囲外のフレームでも `writer.write` が毎フレーム呼ばれ、出力 MP4 に書き込まれる。さらに `cap.read()` も毎フレーム呼ばれるため、`draw_start` までの全フレームと `draw_end` 以降の全フレームをデコードする処理時間も発生する。
- **根本原因**: `writer.write` の配置が `if in_draw_range` の外にあり、`--draw-start` / `--draw-end` の意味が「描画範囲」のみで「出力範囲」を兼ねていない設計（feat-038 で導入）。
- **症状か根本か**: 根本原因（フレームループの構造そのもの）。

### 1.3 修正内容

#### 1.3.1 採用案

**案 A（採用）: `cap.set(CAP_PROP_POS_FRAMES, draw_start)` で開始フレームへシーク + ループで `draw_end` 到達時に break**

- 開始フレームへシークし、`draw_end + 1` に到達した時点でループを抜ける
- `draw_end == -1`（末尾まで）の場合は EOF まで処理
- 出力 MP4 は指定範囲のフレームのみ含む
- `frame_idx` は実際のフレーム番号を保持（既存の `draw_frame_number` 表示と JSON ファイル名 `{stem}_{N:06d}.json` ルックアップが既存挙動のまま）

#### 1.3.2 却下案

**案 B（却下）: `writer.write(frame)` を `if in_draw_range:` 配下へ移動**

- 採用案より修正は最小（1 行移動のみ）
- 却下理由: `cap.read()` は全フレーム呼ばれ続けるため、`draw_start` 到達まで・`draw_end` 後の全フレームのデコード時間が無駄。本ケースでは入力 321239 フレームに対し描画 1397 フレームで、無駄なデコードが 99.6% を占める

#### 1.3.3 変更対象ファイル

- `scripts/visualize_patient_video.py` のみ

#### 1.3.4 修正前・修正後コード

**修正前 (267 行 + 280–304 行)**:
```python
    json_stem = detect_json_stem(args.json_dir)
    draw_end = args.draw_end
    ...
    frame_idx = 0
    start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        draw_frame_number(frame, frame_idx)

        in_draw_range = (frame_idx >= args.draw_start) and (
            draw_end == -1 or frame_idx <= draw_end
        )

        if in_draw_range:
            json_path = os.path.join(...)
            ...（描画処理）...

        writer.write(frame)
        ...
        frame_idx += 1
```

**修正後**:
```python
    json_stem = detect_json_stem(args.json_dir)
    draw_end = args.draw_end
    ...
    # 開始フレームへシーク
    if args.draw_start > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, args.draw_start)

    frame_idx = args.draw_start
    start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if draw_end != -1 and frame_idx > draw_end:
            break

        draw_frame_number(frame, frame_idx)

        json_path = os.path.join(
            args.json_dir, f"{json_stem}_{frame_idx:06d}.json"
        )
        people = load_frame_json(json_path)
        visible_people = filter_people(
            people, args.id_type, args.mode, args.filter_values
        )
        for person in visible_people:
            id_value = person.get(args.id_type, -1)
            color = get_color_for_mode(id_value, args.mode)
            draw_person(frame, person, color, args.id_type, args.kpt_thr, debug_flags)

        writer.write(frame)
        ...
        frame_idx += 1
```

修正の要点:
1. ループ前に `cap.set(cv2.CAP_PROP_POS_FRAMES, args.draw_start)` で開始フレームへシーク
2. `frame_idx = args.draw_start` で開始（実フレーム番号と一致）
3. ループ冒頭で `draw_end` 到達チェックして break
4. `in_draw_range` フラグを廃止（範囲内のみがループに入るため、常に描画する）
5. `writer.write(frame)` は変わらず毎反復呼ばれるが、ループ内のフレーム = 描画対象のみ

#### 1.3.5 既存印字メッセージへの注記

既存の進捗表示 `Processing frame {frame_idx:06d}/{total_frames}` は `if frame_idx % PROGRESS_INTERVAL_FRAMES == 0:` で発火するため、`frame_idx` が `args.draw_start` から始まる場合、初回表示は `frame_idx` が `PROGRESS_INTERVAL_FRAMES`（既存値 3000）の倍数に到達した時点となる。`total_frames` は引き続き入力動画の総フレーム数（変更なし）。**本案件のスコープでは進捗表示の追加・変更は行わず、既存メッセージのまま**とする（要求された不具合のみ対応、§2.2 ついでのリファクタリング禁止）。

### 1.4 影響範囲

- **他の機能への影響**:
  - 既存呼び出し（`--draw-start 0 --draw-end -1` のデフォルト） → 全フレーム処理（既存挙動維持）
  - 既存呼び出し（`--draw-start N` のみ指定） → N から末尾まで（既存は 0 から末尾まで全部処理して N-1 までは素のフレーム + N 以降は描画。改修後は N から末尾まで）。**挙動変更**だが、本来期待される挙動と一致
  - 既存呼び出し（`--draw-end M` のみ指定） → 0 から M まで（既存は全フレーム処理。改修後は 0 から M で停止）。**挙動変更**だが、本来期待される挙動と一致
- **リグレッションリスク**:
  - **R-1**: `cap.set(CAP_PROP_POS_FRAMES, N)` のシークが正確でない動画コンテナ（一部の MP4 / VFR / B フレーム多用）の場合、シーク後に隣接フレームから始まる可能性がある。camSony1_L.mp4（30 fps CFR）では問題ない見込み。検証は §1.5 テスト項目2-3（冒頭・末尾フレームの一致確認）で兼ねる
  - **R-2**: `frame_idx` の初期値が 0 ではなくなるため、進捗表示の % が `args.draw_start / total_frames * 100` から始まる（マイナーな見た目の変化）
  - **R-3**: 出力 MP4 のフレーム数が変わるため、過去に同名ファイルを再生していたユーザーが「動画が短い」と気づくが、これは要求された不具合修正そのもの

### 1.5 確認方法

- **テスト項目1**: `--draw-start 29519 --draw-end 30915` で出力 MP4 のフレーム数が 1397 になる
- **テスト項目2**: 出力 MP4 の冒頭フレームが入力動画のフレーム 29519 と一致する（描画あり）
- **テスト項目3**: 出力 MP4 の最終フレームが入力動画のフレーム 30915 と一致する
- **テスト項目4**: `--draw-start 0 --draw-end -1`（デフォルト）で出力 MP4 が入力と同じフレーム数になる（リグレッション確認）
- **テスト項目5**: `--draw-start 100` のみ指定（`--draw-end` デフォルト -1）で出力が 100 フレームから入力末尾まで含まれる
- **テストコマンド**:
  既存 argparse 定義（`scripts/visualize_patient_video.py` 206–207 行）で `--draw-start` のデフォルト値は `0`、`--draw-end` のデフォルト値は `-1` を確認済み。

  ```bash
  cd /home/sakagawa/git/ViTPose

  # テスト項目1-3: 範囲指定（フレーム 29519–30915）
  uv run python scripts/visualize_patient_video.py \
    --video experiments/input/camSony1_L.mp4 \
    --json-dir experiments/results/camSony1_L_pink_json \
    --out-dir /tmp/bug003_test \
    --id-type pink_id --mode all \
    --draw-start 29519 --draw-end 30915

  # 出力フレーム数確認（テスト項目1）
  uv run python -c "
  import cv2
  cap = cv2.VideoCapture('/tmp/bug003_test/vis_pink_id_all_camSony1_L.mp4')
  print('frames:', int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))  # 期待: 1397
  "

  # 冒頭・末尾フレームと入力フレーム 29519 / 30915 の一致確認（テスト項目2-3、R-1 シーク精度検証も兼ねる）
  uv run python -c "
  import cv2, numpy as np
  cap_in = cv2.VideoCapture('experiments/input/camSony1_L.mp4')
  cap_out = cv2.VideoCapture('/tmp/bug003_test/vis_pink_id_all_camSony1_L.mp4')
  cap_in.set(cv2.CAP_PROP_POS_FRAMES, 29519); _, f_in_first = cap_in.read()
  cap_out.set(cv2.CAP_PROP_POS_FRAMES, 0); _, f_out_first = cap_out.read()
  print('first frame diff (mean abs):', float(np.abs(f_in_first.astype(int) - f_out_first.astype(int)).mean()))
  # 期待: 描画オーバーレイ分の差のみ。BB / スケルトンが入っていない領域では 0 に近い
  "

  # テスト項目4: リグレッション（範囲未指定 = デフォルト全フレーム、処理時間が長いため camSony1_S で代替）
  uv run python scripts/visualize_patient_video.py \
    --video testdata/camSony1.mp4 \
    --json-dir experiments/results/camSony1_S_pink_json \
    --out-dir /tmp/bug003_test \
    --id-type pink_id --mode all

  # テスト項目5: --draw-start のみ指定（--draw-end はデフォルト -1）
  uv run python scripts/visualize_patient_video.py \
    --video testdata/camSony1.mp4 \
    --json-dir experiments/results/camSony1_S_pink_json \
    --out-dir /tmp/bug003_test_start_only \
    --id-type pink_id --mode all \
    --draw-start 100
  # 期待: 出力フレーム数 = (camSony1_S の総フレーム数 - 100)
  ```
- **期待される出力**:
  - テスト項目1: 出力 MP4 のフレーム数 = 1397
  - テスト項目2-3 / R-1 検証: 冒頭フレームの mean abs 差が描画オーバーレイ分のみで微小（背景領域は 0）
  - テスト項目4: 出力 MP4 のフレーム数 = 入力フレーム数（camSony1_S の総フレーム数）
  - テスト項目5: 出力 MP4 のフレーム数 = (camSony1_S の総フレーム数 - 100)

### 1.6 対象外（スコープ外）

以下は本案件では対応しない:

- 既存挙動と紛らわしい進捗表示の改善（`Processing frame N/total` の `total` 表示変更等）
- `--draw-start` / `--draw-end` のヘルプ文言改善
- 同種の問題が他スクリプト（`visualize_tracking.py` 等）にあるかの調査・横展開

これらは別案件として必要に応じて起票する。
