"""ViTPose backbone 高速化モジュール（feat-062）。

MMPose の TopDown モデルの ``model.backbone`` を :class:`AcceleratedBackbone` に差し替え、
(1) backbone のみ fp16 実行、(2) 入力形状ごとの CUDA Graph 再生、を行う。
head / decode / flip test / 前処理は MMPose の既存経路のまま（fp32）で、MMPose 本体は変更しない。

依存は torch と標準ライブラリのみ。``run_halpe26_pipeline_yolo11.py`` から import される。
"""
import sys
from typing import NamedTuple

import torch


class _GraphEntry(NamedTuple):
    graph: torch.cuda.CUDAGraph
    static_in: torch.Tensor
    static_out: torch.Tensor


class AcceleratedBackbone(torch.nn.Module):
    """backbone ラッパー。

    forward の入出力は元の backbone と同じ（入力 float32 ``(N, 3, H, W)``、出力 float32）。
    fp16=True のとき内部で fp16 変換して推論し、出力を float32 に戻す。
    cuda_graph=True のとき入力形状ごとに CUDA Graph をキャプチャして再生する
    （N > max_batch の形状は eager 実行）。キャプチャ失敗は致命エラー（exit 1、ADR-8）。
    """

    def __init__(self, inner: torch.nn.Module, fp16: bool, cuda_graph: bool,
                 max_batch: int, name: str) -> None:
        super().__init__()
        self.inner = inner.half() if fp16 else inner
        self.fp16 = fp16
        self.cuda_graph = cuda_graph
        self.max_batch = max_batch
        self.name = name
        self.device = next(self.inner.parameters()).device
        self._graphs: dict[tuple[int, ...], _GraphEntry] = {}
        self._over_max_logged: set[tuple[int, ...]] = set()
        self.eval()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.fp16:
            x = x.half()
        out = self._run(x)
        # fp16: .float() が新規テンソル（コピー）を返すので静的出力バッファの別名参照にならない
        return out.float() if self.fp16 else out

    def precapture(self, shape: tuple[int, int, int, int]) -> None:
        """指定形状の CUDA Graph を事前にキャプチャする（ゼロ入力で _run を 1 回呼ぶ）。"""
        dtype = torch.float16 if self.fp16 else torch.float32
        zeros = torch.zeros(shape, dtype=dtype, device=self.device)
        with torch.no_grad():
            self._run(zeros)

    def _run(self, x: torch.Tensor) -> torch.Tensor:
        if not self.cuda_graph:
            return self.inner(x)
        shape = tuple(x.shape)
        if shape[0] > self.max_batch:
            if shape not in self._over_max_logged:
                print(f'[INFO] Pose accel ({self.name}): batch {shape[0]} > max_batch '
                      f'{self.max_batch}, eager')
                self._over_max_logged.add(shape)
            return self.inner(x)
        if shape not in self._graphs:
            self._graphs[shape] = self._capture(x)
        entry = self._graphs[shape]
        entry.static_in.copy_(x)
        entry.graph.replay()
        # fp32 のときは呼び出し元でコピーされないため clone して静的バッファの別名参照を防ぐ
        return entry.static_out if self.fp16 else entry.static_out.clone()

    def _capture(self, x: torch.Tensor) -> _GraphEntry:
        static_in = x.clone()
        try:
            with torch.no_grad():
                side = torch.cuda.Stream()
                side.wait_stream(torch.cuda.current_stream())
                with torch.cuda.stream(side):
                    for _ in range(3):   # warmup: cuBLAS / cudnn 初期化をキャプチャ外で済ませる
                        self.inner(static_in)
                torch.cuda.current_stream().wait_stream(side)
                graph = torch.cuda.CUDAGraph()
                with torch.cuda.graph(graph):
                    static_out = self.inner(static_in)
        except RuntimeError as e:   # torch.cuda.OutOfMemoryError を含む
            print(f'[ERROR] Pose accel ({self.name}): CUDA Graph capture failed for shape '
                  f'{tuple(static_in.shape)}: {e}. Use --no-cuda-graph')
            sys.exit(1)
        print(f'[INFO] Pose accel ({self.name}): CUDA Graph captured for shape '
              f'{tuple(static_in.shape)}')
        return _GraphEntry(graph, static_in, static_out)


def accelerate_pose_model(model: torch.nn.Module, fp16: bool, cuda_graph: bool,
                          max_batch: int = 8, name: str = 'pose') -> bool:
    """``model.backbone`` を AcceleratedBackbone に差し替える。

    fp16 と cuda_graph が両方 False のときは何もせず False を返す（モデル無変更、後方互換）。
    cuda_graph=True のとき N=1 の形状（``(1, 3, H, W)``、H/W は ``model.cfg.data_cfg['image_size']``）を
    事前キャプチャする。戻り値は差し替えたか否か。
    """
    if not fp16 and not cuda_graph:
        return False
    wrapper = AcceleratedBackbone(model.backbone, fp16=fp16, cuda_graph=cuda_graph,
                                  max_batch=max_batch, name=name)
    model.backbone = wrapper
    if cuda_graph:
        width, height = model.cfg.data_cfg['image_size']   # 設定は [W, H] の順
        wrapper.precapture((1, 3, int(height), int(width)))
    return True
