"""主旋律提取器 — desktop entry point.

Starts the local webui HTTP server (127.0.0.1, ephemeral port), wires the
pywebview js_api bridge, and opens the WebView2 window. Run directly
(python main.py) or packaged by PyInstaller.

`--selftest` runs a headless end-to-end probe (synthetic 6 s stereo tone ->
demucs -> ORT -> TXT/MIDI -> format checks) and exits 0/1; used to validate
frozen builds.
"""
import logging
import os
import sys
import time
from pathlib import Path


def _bootstrap_path():
    if getattr(sys, "frozen", False):
        root = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        root = Path(__file__).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_bootstrap_path()

from app import config as C  # noqa: E402


def _setup_logging():
    log_file = C.log_path()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    try:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:  # noqa: BLE001
        pass
    if sys.stderr is not None:  # absent in windowed frozen builds
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        root.addHandler(sh)
    logging.info("app start v%s frozen=%s base=%s", C.VERSION, C.is_frozen(), C.base_dir())


def _selftest() -> int:
    import re
    import tempfile
    import wave

    import numpy as np

    log = logging.getLogger("selftest")

    def fail(msg):
        log.error("SELFTEST FAIL %s", msg)
        return 1

    try:  # GUI stack (clr/pythonnet/cffi) is not exercised by the pipeline alone
        import clr_loader  # noqa: F401
        import webview.platforms.winforms  # noqa: F401
        log.info("selftest: webview winforms stack import OK")
    except Exception as e:  # noqa: BLE001
        return fail(f"webview stack import: {e!r}")

    tmp = Path(tempfile.mkdtemp(prefix="melody_selftest_"))
    wav = tmp / "tone.wav"
    sr, dur = 44100, 6.0
    t = np.arange(int(sr * dur)) / sr
    tone = 0.4 * np.sin(2 * np.pi * 440.0 * t) * (1 + 0.5 * np.sin(2 * np.pi * 3 * t))
    pcm = (np.clip(np.stack([tone, np.roll(tone, 53)], 1), -1, 1) * 32767).astype("<i2")
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    log.info("selftest: wav %s (%.1fs stereo)", wav, dur)

    from app import config as C, exporters as EX
    from app.pipeline import Pipeline

    pipe = Pipeline(log=log.info)
    if not pipe.start({"path": str(wav), "demucs": True, "gpu": True}):
        return fail("pipeline refused to start")
    deadline = time.time() + 600
    while time.time() < deadline:
        st = pipe.state()
        if st["done"] or st["error"] or st["cancelled"]:
            break
        time.sleep(0.5)
    st = pipe.state()
    if st["error"]:
        return fail("pipeline error: " + st["error"])
    if not st["done"]:
        return fail("timeout after 600s")
    r = st["result"]
    log.info("selftest: pipeline done in %.1fs ep=%s frames=%d notes=%d voiced=%.1f%%",
             r["total_s"], r["ep"], r["frames"], r["n_notes"], r["voiced_pct"])

    exp = tmp / "export"
    exp.mkdir()
    notes = [tuple(n) for n in r["notes"]]
    txt = EX.write_txt(exp / "m.txt", notes, C.HOP_S, 1.0, r["frames"])
    mid = EX.write_midi(exp / "m.mid", notes, C.HOP_S, 1.0)

    raw = (exp / "m.txt").read_bytes()
    if raw[:3] == b"\xef\xbb\xbf":
        return fail("txt has BOM")
    if b"\r" in raw:
        return fail("txt has CR")
    if not txt.endswith("\n"):
        return fail("txt missing trailing newline")
    total_ms = int(round(r["frames"] * C.HOP_S * 1000))
    group_re = re.compile(r"\{(\d+), (\d+)\}")
    lines = txt.split("\n")[:-1]
    got_ms = 0
    for i, line in enumerate(lines):
        if not line.endswith(","):
            return fail(f"line {i + 1} missing trailing comma")
        body = line[:-1]
        groups = group_re.findall(body)
        if ", ".join("{%s, %s}" % g for g in groups) != body:
            return fail(f"line {i + 1} malformed: {line!r}")
        if len(groups) != 5 and i != len(lines) - 1:
            return fail(f"line {i + 1} has {len(groups)} groups")
        if not 1 <= len(groups) <= 5:
            return fail(f"last line has {len(groups)} groups")
        got_ms += sum(int(ms) for _, ms in groups)
    if abs(got_ms - total_ms) > 5:
        return fail(f"timeline sum {got_ms}ms != {total_ms}ms")

    import pretty_midi
    pm = pretty_midi.PrettyMIDI(mid)
    n_mid = sum(len(inst.notes) for inst in pm.instruments)
    if n_mid != len(notes):
        return fail(f"midi notes {n_mid} != {len(notes)}")

    log.info("SELFTEST PASS ep=%s lines=%d groups_ms=%d(match %d) midi_notes=%d "
             "timings=%s", r["ep"], len(lines), got_ms, total_ms, n_mid,
             {k: round(v, 1) for k, v in r["timings"].items()})
    return 0


def main():
    _setup_logging()
    log = logging.getLogger("app")
    os.environ.setdefault("TORCH_HOME", str(C.torch_home()))

    from app.server import MediaStore, start_server
    from app.pipeline import Pipeline
    from app.bridge import Api

    media = MediaStore()
    httpd, url = start_server(media)
    log.info("webui serving at %s (static: %s)", url, C.webui_dir())

    pipeline = Pipeline(log=log.info)
    api = Api(pipeline, media, log=log.info)

    import webview
    webview.create_window(
        C.APP_NAME,
        url,
        js_api=api,
        width=1180,
        height=860,
        min_size=(980, 680),
        background_color="#eef0f3",
    )
    debug = bool(os.environ.get("MELODY_DEBUG"))
    webview.start(gui="edgechromium", debug=debug)
    httpd.shutdown()


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        _setup_logging()
        os.environ.setdefault("TORCH_HOME", str(C.torch_home()))
        sys.exit(_selftest())
    main()
