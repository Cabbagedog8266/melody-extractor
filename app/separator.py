"""htdemucs melodybed separation (vocals + other), CPU, offline-capable.

The legacy AWS checkpoint (955717e8-8726e21a.th) is bundled under
models/demucs/ together with an htdemucs.yaml bag file, so get_model()
resolves locally with no network. In the dev tree (weights absent) demucs'
own resolution is used instead.
"""
import random

import numpy as np

from . import config as C

_MODEL_NAME = "htdemucs"
_SIG = "955717e8"


def _repo_dir():
    d = C.base_dir() / "models" / "demucs"
    return d if (d / f"{_MODEL_NAME}.yaml").exists() else None


def separate_melodybed(y: np.ndarray, sr: int = 44100, progress=None,
                       cancel=None) -> np.ndarray:
    """float32 (2, N) at sr -> mono melodybed float32 (N,) at the same sr."""
    import torch
    from demucs.api import Separator

    callback = None
    if progress is not None or cancel is not None:
        def callback(info):
            if cancel is not None and cancel():
                raise KeyboardInterrupt("cancelled")
            if progress is not None and info.get("state") == "end":
                total = float(info.get("audio_length") or 1)
                progress(min(1.0, float(info.get("segment_offset", 0)) / total))

    sep = Separator(model=_MODEL_NAME, repo=_repo_dir(), device="cpu",
                    callback=callback, progress=False)
    wav = torch.from_numpy(np.ascontiguousarray(y, dtype=np.float32))
    # apply_model draws a random shift offset from python's random module on
    # every call (shifts=1 path); pin the seed so separations are reproducible.
    random.seed(0)
    with torch.no_grad():
        _, stems = sep.separate_tensor(wav, sr=sr)
    out = (stems["vocals"] + stems["other"]).mean(dim=0).numpy()
    return np.ascontiguousarray(out, dtype=np.float32)
