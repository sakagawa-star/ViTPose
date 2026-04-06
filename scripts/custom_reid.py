"""カスタム Re-ID モジュール (feat-022 イテレーション2)

ViTPose HALPE 26 キーポイントと HSV 色ヒストグラムを使い、
トラッカー後段で stable_id を維持するカスタム Re-ID。
"""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class PersonFeature:
    """人物の特徴量（頭部・上半身の HSV ヒストグラム）"""

    head_hist: np.ndarray | None  # shape=(68,) float32 or None
    torso_hist: np.ndarray | None  # shape=(68,) float32 or None


class CustomReID:
    """カスタム Re-ID: track_id → stable_id のマッピングを管理する"""

    # HALPE 26 キーポイントインデックス
    HEAD_INDICES = [0, 1, 2, 3, 4, 17, 18]  # Nose, LEye, REye, LEar, REar, Head, Neck
    TORSO_INDICES = [5, 6, 11, 12]  # LShoulder, RShoulder, LHip, RHip

    def __init__(
        self,
        alpha: float = 0.1,
        sim_threshold: float = 0.3,
        kpt_conf_thr: float = 0.3,
        head_expand_px: int = 20,
        delay_frames: int = 180,
    ) -> None:
        self._alpha = alpha
        self._sim_threshold = sim_threshold
        self._kpt_conf_thr = kpt_conf_thr
        self._head_expand_px = head_expand_px
        self._delay_frames = delay_frames

        self._active_features: dict[int, PersonFeature] = {}
        self._active_stable: dict[int, int] = {}
        self._disappeared: dict[int, PersonFeature] = {}
        self._prev_track_ids: set[int] = set()
        self._next_stable_id: int = 1
        self._pending: dict[int, tuple[int, int]] = {}

    def update(
        self,
        frame: np.ndarray,
        track_ids: list[int],
        keypoints_map: dict[int, np.ndarray | None],
        frame_idx: int,
    ) -> dict[int, int]:
        """フレームごとの stable_id 更新

        Args:
            frame: (H, W, 3) uint8 BGR
            track_ids: Deep OC-SORT のアクティブ track_id 一覧
            keypoints_map: {track_id: kpts(26,3) or None}

        Returns:
            {track_id: stable_id}
        """
        curr = set(track_ids)
        prev = self._prev_track_ids

        lost_ids = prev - curr
        new_ids = curr - prev
        existing_ids = curr & prev

        # ステップ1: 消失した ID を _disappeared へ移動
        for tid in lost_ids:
            sid = self._active_stable[tid]
            self._disappeared[sid] = self._active_features[tid]
            del self._active_stable[tid]
            del self._active_features[tid]
            # 保留中に消失した場合は保留解除
            if tid in self._pending:
                del self._pending[tid]

        # ステップ2: 新しい ID に stable_id を割り当て（track_id 昇順）
        for tid in sorted(new_ids):
            new_feat = self._build_feature(frame, keypoints_map.get(tid))

            matched_sid = self._match(new_feat)
            if matched_sid is not None:
                # 即座マッチ成功: 消失IDのstable_idを引き継ぐ
                sid = matched_sid
                del self._disappeared[matched_sid]
            else:
                # 即座マッチ失敗: 仮stable_idを発番
                sid = self._next_stable_id
                self._next_stable_id += 1
                # 消失IDがある場合のみ保留状態にする（初回出現は対象外）
                if len(self._disappeared) > 0:
                    self._pending[tid] = (sid, frame_idx)

            self._active_stable[tid] = sid
            self._active_features[tid] = new_feat

        # ステップ3: 継続する ID の EMA 更新
        for tid in existing_ids:
            new_feat = self._build_feature(frame, keypoints_map.get(tid))
            self._active_features[tid] = self._ema_update(
                self._active_features[tid], new_feat
            )

        # ステップ4: 遅延マッチ処理
        resolved: list[int] = []
        for tid, (temp_sid, appear_frame) in self._pending.items():
            if tid not in curr:
                # 保留中に消失: ステップ1で既に処理済みだが念のためガード
                resolved.append(tid)
                continue

            # EMA更新後の特徴量で再マッチ試行
            current_feat = self._active_features[tid]
            matched_sid = self._match(current_feat)

            if matched_sid is not None:
                # マッチ成功: stable_id を再割り当て
                old_sid = self._active_stable[tid]
                self._active_stable[tid] = matched_sid
                del self._disappeared[matched_sid]
                print(
                    f"Delayed Re-ID: track_id={tid} reassigned "
                    f"stable_id {old_sid}\u2192{matched_sid} "
                    f"at frame {frame_idx} (offset={frame_idx - appear_frame})"
                )
                resolved.append(tid)
            elif frame_idx - appear_frame >= self._delay_frames:
                # N フレーム経過: 仮stable_idを確定
                print(
                    f"Delayed Re-ID timeout: track_id={tid} "
                    f"keeping stable_id={self._active_stable[tid]} "
                    f"at frame {frame_idx} (offset={frame_idx - appear_frame})"
                )
                resolved.append(tid)

        for tid in resolved:
            del self._pending[tid]

        self._prev_track_ids = curr
        return dict(self._active_stable)

    def _build_feature(
        self, frame: np.ndarray, kpts: np.ndarray | None
    ) -> PersonFeature:
        """キーポイントからPersonFeatureを構築する"""
        if kpts is not None:
            head_region = self._extract_head(frame, kpts)
            torso_region = self._extract_torso(frame, kpts)
            return PersonFeature(
                head_hist=self._compute_hist(head_region),
                torso_hist=self._compute_hist(torso_region),
            )
        return PersonFeature(head_hist=None, torso_hist=None)

    def _extract_head(
        self, frame: np.ndarray, kpts: np.ndarray
    ) -> np.ndarray | None:
        """FR-001: 頭部領域抽出"""
        h, w = frame.shape[:2]
        visible = [
            kpts[i] for i in self.HEAD_INDICES if kpts[i][2] > self._kpt_conf_thr
        ]
        if len(visible) == 0:
            return None

        x1 = max(0, min(p[0] for p in visible) - self._head_expand_px)
        y1 = max(0, min(p[1] for p in visible) - self._head_expand_px)
        x2 = min(w, max(p[0] for p in visible) + self._head_expand_px)
        y2 = min(h, max(p[1] for p in visible) + self._head_expand_px)

        if x2 <= x1 or y2 <= y1:
            return None

        return frame[int(y1):int(y2), int(x1):int(x2)]

    def _extract_torso(
        self, frame: np.ndarray, kpts: np.ndarray
    ) -> np.ndarray | None:
        """FR-002: 上半身領域抽出"""
        h, w = frame.shape[:2]
        visible = [
            kpts[i] for i in self.TORSO_INDICES if kpts[i][2] > self._kpt_conf_thr
        ]
        if len(visible) < 2:
            return None

        x1 = max(0, min(p[0] for p in visible))
        y1 = max(0, min(p[1] for p in visible))
        x2 = min(w, max(p[0] for p in visible))
        y2 = min(h, max(p[1] for p in visible))

        if x2 <= x1 or y2 <= y1:
            return None

        return frame[int(y1):int(y2), int(x1):int(x2)]

    def _compute_hist(self, region: np.ndarray | None) -> np.ndarray | None:
        """FR-003: HSV ヒストグラム計算"""
        if region is None:
            return None

        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

        h_hist = cv2.calcHist([hsv], [0], None, [36], [0, 180])  # (36, 1)
        s_hist = cv2.calcHist([hsv], [1], None, [32], [0, 256])  # (32, 1)

        hist = np.concatenate([h_hist.flatten(), s_hist.flatten()])  # (68,)
        total = hist.sum()

        if total < 1e-6:
            return None

        hist = hist / total
        return hist.astype(np.float32)

    def _ema_update(
        self, current: PersonFeature, new_frame: PersonFeature
    ) -> PersonFeature:
        """FR-004: EMA 特徴量更新"""
        return PersonFeature(
            head_hist=self._ema_single(current.head_hist, new_frame.head_hist),
            torso_hist=self._ema_single(current.torso_hist, new_frame.torso_hist),
        )

    def _ema_single(
        self, current_h: np.ndarray | None, new_h: np.ndarray | None
    ) -> np.ndarray | None:
        """単一ヒストグラムの EMA 更新"""
        if current_h is None:
            return new_h
        if new_h is None:
            return current_h
        return self._alpha * new_h + (1.0 - self._alpha) * current_h

    def _compute_similarity(self, f1: PersonFeature, f2: PersonFeature) -> float:
        """FR-005: ヒストグラム交差による類似度計算"""
        sims: list[float] = []
        if f1.head_hist is not None and f2.head_hist is not None:
            sims.append(float(np.minimum(f1.head_hist, f2.head_hist).sum()))
        if f1.torso_hist is not None and f2.torso_hist is not None:
            sims.append(float(np.minimum(f1.torso_hist, f2.torso_hist).sum()))
        if len(sims) == 0:
            return 0.0
        return sum(sims) / len(sims)

    def _match(self, feature: PersonFeature) -> int | None:
        """FR-005: 消失 ID 照合による stable_id 決定"""
        disappeared = self._disappeared
        if len(disappeared) == 0:
            return None

        if len(disappeared) == 1:
            stable_id, feat = next(iter(disappeared.items()))
            sim = self._compute_similarity(feature, feat)
            return stable_id if sim > self._sim_threshold else None

        # 2件以上: 最高類似度を選択（同点時は stable_id 最小を優先）
        best_id, best_sim = None, 0.0
        for stable_id, feat in disappeared.items():
            sim = self._compute_similarity(feature, feat)
            # sim > best_sim: より高い類似度を優先
            # sim == best_sim: 同点時は stable_id が小さい方を優先（FR-005 同点処理）
            # best_id is not None: best_sim == 0.0 で未設定の場合はスキップ
            if sim > best_sim or (
                sim == best_sim and best_id is not None and stable_id < best_id
            ):
                best_sim = sim
                best_id = stable_id
        return best_id if best_sim > self._sim_threshold else None

    @property
    def active_features(self) -> dict[int, PersonFeature]:
        """アクティブな track_id → EMA 特徴量（読み取り専用）"""
        return self._active_features

    @property
    def disappeared(self) -> dict[int, PersonFeature]:
        """消失した stable_id → EMA 特徴量（読み取り専用）"""
        return self._disappeared
