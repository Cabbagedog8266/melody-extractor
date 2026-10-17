# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for 主旋律提取器 (onedir).

    pyinstaller pack/melody_extractor.spec --noconfirm --clean `
        --distpath pack/dist --workpath pack/build

Bundles: app package, webui, ONNX model, htdemucs weights (local repo),
CPU torch + demucs, onnxruntime-directml, pywebview.
"""
from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821  (repository root)
OUTNAME = "MelodyExtractor"

datas = [
    (str(ROOT / "models" / "melody_mert95.onnx"), "models"),
    (str(ROOT / "models" / "demucs" / "955717e8-8726e21a.th"), "models/demucs"),
    (str(ROOT / "models" / "demucs" / "htdemucs.yaml"), "models/demucs"),
    (str(ROOT / "webui"), "webui"),
]

hiddenimports = [
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "clr_loader",
    "sphn",
    "soxr",
    "mido",
    "pretty_midi",
    "demucs.api",
    "demucs.pretrained",
    "demucs.repo",
    "demucs.hdemucs",
    "demucs.htdemucs",
    "julius",
    "lameenc",
    "einops",
    # htdemucs checkpoint pickles numpy.core.multiarray; numpy>=2 shim module
    # is only importable at runtime, so the static analysis misses it.
    "numpy.core.multiarray",
]

excludes = [
    # training / large tooling not used by the desktop app
    # NOTE: cffi must NOT be excluded - clr_loader.ffi (pythonnet host for
    # pywebview's winforms/edgechromium backend) imports it at runtime.
    "transformers", "matplotlib", "pandas", "scipy", "sklearn",
    "IPython", "jupyter", "notebook", "tkinter", "torchaudio",
    "soundfile", "pytest", "dora", "omegaconf", "hydra",
]

a = Analysis(  # noqa: F821
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=OUTNAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ROOT / "pack" / "appicon.ico"),
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=OUTNAME,
)
