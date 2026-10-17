"""ONNX Runtime session for the melody model.

DirectML execution provider when a compatible GPU is present, silent CPU
fallback otherwise. Chunked inference mirrors infer_melody_v3.predict_frames
(whole-song z-normalize, CHUNK/STEP constants, tail chunk >= 400 samples).
"""
import numpy as np
import onnxruntime as ort

from . import config as C


class MelodyModel:
    def __init__(self, model_path, prefer_gpu: bool = True, log=print):
        avail = ort.get_available_providers()
        attempts = []
        if prefer_gpu and "DmlExecutionProvider" in avail:
            attempts.append(["DmlExecutionProvider", "CPUExecutionProvider"])
        attempts.append(["CPUExecutionProvider"])
        last_err = None
        self.sess = None
        for provs in attempts:
            try:
                so = ort.SessionOptions()
                so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                self.sess = ort.InferenceSession(str(model_path), sess_options=so,
                                                 providers=provs)
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                log(f"[ort] session with {provs} failed: {e}")
        if self.sess is None:
            raise RuntimeError(f"无法创建 ONNX 推理会话：{last_err}")
        self.providers = self.sess.get_providers()

    @property
    def using_gpu(self) -> bool:
        return bool(self.providers) and self.providers[0] == "DmlExecutionProvider"

    def n_chunks(self, n_samples: int) -> int:
        k, s0 = 0, 0
        while n_samples - s0 >= C.MERT_RF:
            k += 1
            s0 += C.STEP
        return k

    def predict(self, y: np.ndarray, progress=None, cancel=None) -> np.ndarray:
        """(F, 61) logits for a float32 mono 24 kHz track."""
        y = np.asarray(y, dtype=np.float32)
        y = (y - y.mean()) / (y.std() + 1e-7)
        total = max(1, self.n_chunks(y.shape[0]))
        outs, s0, k = [], 0, 0
        while True:
            if cancel and cancel():
                raise InterruptedError("已取消")
            seg = y[s0:s0 + C.CHUNK]
            if seg.shape[0] < C.MERT_RF:
                break
            outs.append(self.sess.run(["melody_logits"], {"wav": seg[None]})[0][0])
            s0 += C.STEP
            k += 1
            if progress:
                progress(min(1.0, k / total))
        if not outs:
            return np.zeros((0, C.N_CLASSES), dtype=np.float32)
        return np.concatenate(outs, axis=0)
