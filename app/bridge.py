"""pywebview js_api bridge: dialogs, pipeline control, previews, exports.

All methods return JSON-serializable dicts; failures come back as
{"ok": false, "error": "..."} so the frontend never has to catch.
"""
import json
import math
import os
import subprocess
import sys
from pathlib import Path

from . import config as C, decode, exporters
from .pipeline import Pipeline

DEFAULT_SETTINGS = {
    "ratio": 1.0,
    "demucs": True,
    "gpu": True,
    "out_midi": True,
    "out_txt": True,
    "out_dir": "",
    "last_dir": "",
}

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def midi_name(m: float) -> str:
    i = int(round(m))
    return NOTE_NAMES[i % 12] + str(i // 12 - 1)


class Api:
    def __init__(self, pipeline: Pipeline, media, log=print):
        self.pipe = pipeline
        self.media = media
        self.log = log

    # ---------------- helpers ----------------

    @staticmethod
    def _ok(**kw):
        return {"ok": True, **kw}

    @staticmethod
    def _err(e):
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def _result(self):
        st = self.pipe.state()
        if not st.get("done") or not st.get("result"):
            raise RuntimeError("尚无处理结果")
        return st["result"]

    # ---------------- dialogs ----------------

    def pick_file(self):
        try:
            import webview
            win = webview.windows[0]
            s = self.load_settings()
            res = win.create_file_dialog(
                webview.FileDialog.OPEN,
                directory=s.get("last_dir") or "",
                allow_multiple=False,
                file_types=("音频文件 (*.flac;*.wav;*.mp3;*.m4a;*.ogg;*.aac;*.wma;*.opus)",
                            "所有文件 (*.*)"),
            )
            if not res:
                return self._ok(cancelled=True)
            path = str(Path(res[0]).resolve())
            s["last_dir"] = str(Path(path).parent)
            self.save_settings(s)
            return self.probe(path)
        except Exception as e:  # noqa: BLE001
            return self._err(e)

    def pick_folder(self):
        try:
            import webview
            win = webview.windows[0]
            res = win.create_file_dialog(webview.FileDialog.FOLDER)
            if not res:
                return self._ok(cancelled=True)
            return self._ok(dir=str(Path(res[0]).resolve()))
        except Exception as e:  # noqa: BLE001
            return self._err(e)

    # ---------------- probing ----------------

    def probe(self, path: str):
        try:
            p = Path(path)
            if not p.is_file():
                return {"ok": False, "error": "文件不存在"}
            info = decode.probe(p)
            token = self.media.register(p)
            return self._ok(
                path=str(p),
                name=p.name,
                size_mb=round(p.stat().st_size / 1e6, 1),
                duration_s=round(info["duration_s"], 1),
                sr=info["sr"],
                channels=info["channels"],
                codec=info["codec"],
                media="/media/" + token,
            )
        except Exception as e:  # noqa: BLE001
            return self._err(e)

    def sysinfo(self):
        try:
            import onnxruntime as ort
            provs = ort.get_available_providers()
            has_onnx_model = C.model_path().is_file()
            return self._ok(
                providers=provs,
                dml="DmlExecutionProvider" in provs,
                onnxruntime=ort.__version__,
                version=C.VERSION,
                model_ready=has_onnx_model,
            )
        except Exception as e:  # noqa: BLE001
            return self._err(e)

    # ---------------- pipeline ----------------

    def start(self, path: str, demucs: bool, gpu: bool):
        try:
            if self.pipe.busy():
                return {"ok": False, "error": "已有任务在运行"}
            if not C.model_path().is_file():
                return {"ok": False, "error": f"模型文件缺失：{C.model_path()}"}
            media = self.media.register(Path(path))
            started = self.pipe.start({"path": path, "demucs": bool(demucs),
                                       "gpu": bool(gpu)})
            if not started:
                return {"ok": False, "error": "已有任务在运行"}
            return self._ok(media="/media/" + media)
        except Exception as e:  # noqa: BLE001
            return self._err(e)

    def progress(self):
        try:
            st = self.pipe.state()
            st.pop("result", None)
            return self._ok(state=st)
        except Exception as e:  # noqa: BLE001
            return self._err(e)

    def cancel(self):
        try:
            self.pipe.cancel()
            return self._ok()
        except Exception as e:  # noqa: BLE001
            return self._err(e)

    # ---------------- results & previews ----------------

    def result(self):
        try:
            r = dict(self._result())
            r["hop_s"] = C.HOP_S
            return self._ok(result=r)
        except Exception as e:  # noqa: BLE001
            return self._err(e)

    def txt_preview(self, ratio: float, head_lines: int = 12):
        try:
            r = self._result()
            notes = [tuple(n) for n in r["notes"]]
            text = exporters.format_txt(notes, C.HOP_S, float(ratio), r["frames"])
            lines = text.splitlines()
            groups = sum(ln.count("{") for ln in lines)
            last_len = lines[-1].count("{") if lines else 0
            return self._ok(
                head=lines[:head_lines],
                total_lines=len(lines),
                total_groups=groups,
                last_len=last_len,
                shown=min(head_lines, len(lines)),
            )
        except Exception as e:  # noqa: BLE001
            return self._err(e)

    def midi_preview(self, ratio: float):
        try:
            r = self._result()
            notes = [tuple(n) for n in r["notes"]]
            if not notes:
                return self._ok(names=[], example=None)
            shift = 12 * math.log2(float(ratio))
            head = [midi_name(n[2] + C.FMIN_MIDI + shift) for n in notes[:6]]
            s, _e, q = notes[0]
            midi = q + C.FMIN_MIDI
            ex_freq = exporters.freq_hz(midi, float(ratio))
            nearest = int(round(midi + shift))
            quant = exporters.freq_hz(nearest)
            cents = 1200 * math.log2(ex_freq / quant) if ex_freq > 0 else 0.0
            return self._ok(names=head, example={
                "name": midi_name(midi),
                "base_hz": round(exporters.freq_hz(midi), 2),
                "ratio_hz": round(ex_freq, 2),
                "nearest": midi_name(nearest),
                "quant_hz": round(quant, 2),
                "cents": round(cents, 1),
            })
        except Exception as e:  # noqa: BLE001
            return self._err(e)

    # ---------------- export ----------------

    def export(self, ratio: float, midi: bool, txt: bool, out_dir: str):
        try:
            r = self._result()
            st = self.pipe.state()
            src = Path(st.get("input") or "audio")
            out = Path(out_dir) if out_dir else self._default_out_dir()
            out.mkdir(parents=True, exist_ok=True)
            stem = src.stem
            notes = [tuple(n) for n in r["notes"]]
            written = {}
            if midi:
                p = out / f"{stem}_melody.mid"
                exporters.write_midi(p, notes, C.HOP_S, float(ratio))
                written["midi"] = str(p)
            if txt:
                p = out / f"{stem}_melody.txt"
                exporters.write_txt(p, notes, C.HOP_S, float(ratio), r["frames"])
                written["txt"] = str(p)
            s = self.load_settings()
            s["out_dir"] = str(out)
            self.save_settings(s)
            return self._ok(**written, dir=str(out))
        except Exception as e:  # noqa: BLE001
            return self._err(e)

    def open_folder(self, path: str = ""):
        try:
            p = Path(path) if path else self._default_out_dir()
            if p.is_file():
                p = p.parent
            if not p.is_dir():
                return {"ok": False, "error": f"目录不存在：{p}"}
            if sys.platform == "win32":
                os.startfile(str(p))  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p)])
            return self._ok()
        except Exception as e:  # noqa: BLE001
            return self._err(e)

    # ---------------- settings ----------------

    @staticmethod
    def _default_out_dir() -> Path:
        base = Path.home() / "Music"
        if not base.is_dir():
            base = Path.home()
        return base / "MelodyExtractor"

    def load_settings(self) -> dict:
        s = dict(DEFAULT_SETTINGS)
        try:
            raw = json.loads(C.settings_path().read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                s.update({k: v for k, v in raw.items() if k in DEFAULT_SETTINGS})
        except FileNotFoundError:
            pass
        except Exception as e:  # noqa: BLE001
            self.log(f"[settings] read failed: {e}")
        if not s.get("out_dir"):
            s["out_dir"] = str(self._default_out_dir())
        return s

    def save_settings(self, settings: dict):
        try:
            cur = self.load_settings()
            cur.update({k: v for k, v in (settings or {}).items() if k in DEFAULT_SETTINGS})
            C.settings_path().write_text(
                json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
            return self._ok(settings=cur)
        except Exception as e:  # noqa: BLE001
            return self._err(e)

    def get_settings(self):
        try:
            return self._ok(settings=self.load_settings())
        except Exception as e:  # noqa: BLE001
            return self._err(e)
