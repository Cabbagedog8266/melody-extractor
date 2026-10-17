"""Processing pipeline: decode -> (demucs) -> ONNX infer -> events -> previews.

Runs in a worker thread; the UI polls state(). Cooperative cancel: demucs
callback raises KeyboardInterrupt, and the chunk loop checks a flag.
"""
import threading
import time
import traceback

import numpy as np

from . import config as C, decode, events, exporters, model_ort


class Pipeline:
    STAGES = ["解码与重采样", "人声分离", "旋律提取", "生成预览"]

    def __init__(self, log=print):
        self.log = log
        self._lock = threading.Lock()
        self._thread = None
        self._cancel = False
        self._model = None
        self._model_gpu = None
        self._state = {
            "running": False, "stage": 0, "stage_pct": 0.0, "done": False,
            "cancelled": False, "error": None, "input": "", "demucs": True,
            "result": None,
        }

    # ---------------- state access ----------------

    def state(self):
        with self._lock:
            return dict(self._state)

    def _set(self, **kw):
        with self._lock:
            self._state.update(kw)

    def busy(self):
        with self._lock:
            return bool(self._state["running"])

    def cancel(self):
        self._cancel = True

    def _cancel_check(self):
        return self._cancel

    def _check_cancel(self):
        if self._cancel:
            raise InterruptedError("已取消")

    # ---------------- model cache ----------------

    def get_model(self, prefer_gpu: bool):
        if self._model is None or self._model_gpu != prefer_gpu:
            t0 = time.time()
            self._model = model_ort.MelodyModel(C.model_path(), prefer_gpu=prefer_gpu,
                                                log=self.log)
            self._model_gpu = prefer_gpu
            self.log(f"[ort] session ready in {time.time() - t0:.1f}s "
                     f"providers={self._model.providers}")
        return self._model

    # ---------------- run ----------------

    def start(self, opts: dict) -> bool:
        if self.busy():
            return False
        self._cancel = False
        self._set(running=True, done=False, cancelled=False, error=None, stage=1,
                  stage_pct=0.0, result=None,
                  input=opts.get("path", ""), demucs=bool(opts.get("demucs", True)))
        self._thread = threading.Thread(target=self._run, args=(opts,), daemon=True)
        self._thread.start()
        return True

    def _run(self, opts: dict):
        try:
            t_all = time.time()
            path = opts["path"]
            demucs_on = bool(opts.get("demucs", True))
            gpu = bool(opts.get("gpu", True))
            timings = {}

            # ---- stage 1: decode ----
            t0 = time.time()
            info = decode.probe(path)
            y44 = None
            if demucs_on:
                y44 = decode.decode(path, 44100, 2)
                y = y44.mean(0)
            else:
                y = decode.decode(path, 24000, 1)[0]
            if y.shape[0] < 4096:
                raise ValueError("音频太短或为空")
            peaks_orig = exporters.peaks_of(y, 220)
            timings["decode"] = time.time() - t0
            self._set(stage=1, stage_pct=1.0)
            self._check_cancel()

            # ---- stage 2: separation ----
            if demucs_on:
                import soxr
                from . import separator
                self._set(stage=2, stage_pct=0.0)
                t0 = time.time()
                bed44 = separator.separate_melodybed(
                    y44, sr=44100,
                    progress=lambda p: self._set(stage_pct=p),
                    cancel=self._cancel_check)
                y = soxr.resample(bed44, 44100, 24000).astype(np.float32)
                timings["separate"] = time.time() - t0
                del y44, bed44
                self._set(stage=2, stage_pct=1.0)
                self._check_cancel()
            else:
                timings["separate"] = 0.0
                self._set(stage=2, stage_pct=1.0)

            # ---- stage 3: melody inference ----
            self._set(stage=3, stage_pct=0.0)
            t0 = time.time()
            model = self.get_model(gpu)
            logits = model.predict(y, progress=lambda p: self._set(stage_pct=p),
                                   cancel=self._cancel_check)
            timings["infer"] = time.time() - t0
            pred = logits.argmax(-1)
            voiced = pred != (C.N_CLASSES - 1)
            pitch_idx = np.where(voiced, pred, -1000)
            notes = events.events_from_frames(pitch_idx, voiced, hop_s=C.HOP_S,
                                              median=C.MEDIAN, min_note_s=C.MIN_NOTE_S,
                                              min_gap_s=C.MIN_GAP_S)
            self._set(stage=3, stage_pct=1.0)
            self._check_cancel()

            # ---- stage 4: previews ----
            self._set(stage=4, stage_pct=0.0)
            t0 = time.time()
            frames = int(len(pred))
            midis = [q + C.FMIN_MIDI for _, _, q in notes]
            timings["preview"] = time.time() - t0
            result = {
                "notes": [[int(s), int(e), int(q)] for s, e, q in notes],
                "frames": frames,
                "duration_ms": int(round(frames * C.HOP_S * 1000)),
                "n_notes": len(notes),
                "voiced_pct": float(voiced.mean() * 100) if frames else 0.0,
                "midi_min": min(midis) if midis else None,
                "midi_max": max(midis) if midis else None,
                "peaks_orig": peaks_orig,
                "peaks_melody": exporters.synth_peaks(notes, C.HOP_S, frames),
                "info": info,
                "demucs": demucs_on,
                "ep": model.providers[0] if model.providers else "CPUExecutionProvider",
                "timings": timings,
                "total_s": time.time() - t_all,
            }
            self._set(stage=4, stage_pct=1.0, result=result, done=True, running=False)
        except (InterruptedError, KeyboardInterrupt):
            self._set(running=False, cancelled=True, error=None)
        except Exception as e:  # noqa: BLE001
            self.log("ERROR " + traceback.format_exc())
            self._set(running=False, error=f"{type(e).__name__}: {e}")
