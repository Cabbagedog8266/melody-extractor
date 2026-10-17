"""Paths and model constants for dev tree and frozen (PyInstaller) app."""
import sys
from pathlib import Path

APP_NAME = "主旋律提取器"
APP_ID = "MelodyExtractor"
VERSION = "1.0.0"

SR = 24000
CONV_STRIDE = 320            # 24 kHz -> 75 Hz
MERT_RF = 400
SEG_FRAMES = 512
N_CLASSES = 61               # 60 pitch bins (idx -> MIDI 36+idx) + silence
FMIN_MIDI = 36
HOP_S = CONV_STRIDE / SR     # 1/75 s per frame

CHUNK = SEG_FRAMES * CONV_STRIDE                     # 163840 samples


def mert_frames(samples: int) -> int:
    return max(0, (samples - MERT_RF) // CONV_STRIDE + 1)


STEP = mert_frames(CHUNK) * CONV_STRIDE              # 163520 samples

MEDIAN = 5
MIN_NOTE_S = 0.06
MIN_GAP_S = 0.05


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def base_dir() -> Path:
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1]        # repository root


def model_path() -> Path:
    return base_dir() / "models" / "melody_mert95.onnx"


def webui_dir() -> Path:
    return base_dir() / "webui"


def torch_home() -> Path:
    """Bundled torch hub cache holding htdemucs weights (hub/checkpoints/...)."""
    return base_dir() / "torch_home"


def settings_path() -> Path:
    from os import environ
    root = Path(environ.get("APPDATA", str(Path.home()))) / APP_ID
    root.mkdir(parents=True, exist_ok=True)
    return root / "settings.json"


def log_path() -> Path:
    from os import environ
    root = Path(environ.get("APPDATA", str(Path.home()))) / APP_ID / "logs"
    root.mkdir(parents=True, exist_ok=True)
    return root / "app.log"
