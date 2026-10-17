"""Local HTTP server for the webui + tokenized media streaming (Range).

Serves only whitelisted static files from webui_dir() and audio streams for
paths registered via MediaStore.register — filesystem paths never reach the
page.
"""
import json
import logging
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import config as C

_CTYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}
_AUDIO_CTYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wma": "audio/x-ms-wma",
}
_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


class MediaStore:
    def __init__(self):
        self._map = {}
        self._lock = threading.Lock()

    def register(self, path: Path) -> str:
        token = uuid.uuid4().hex
        with self._lock:
            self._map[token] = str(Path(path))
        return token

    def resolve(self, token: str):
        with self._lock:
            p = self._map.get(token)
        if p is None:
            return None
        path = Path(p)
        return path if path.is_file() else None


class _Handler(BaseHTTPRequestHandler):
    server_version = "MelodyExtractor"
    media: MediaStore = None  # set per-server
    webui: Path = None

    def log_message(self, fmt, *args):  # keep console clean
        logging.getLogger("webui").debug(fmt, *args)

    # ---- helpers ----

    def _send_json(self, code: int, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, rel: str):
        rel = rel.lstrip("/") or "index.html"
        if "/" in rel or ".." in rel:
            self.send_error(404)
            return
        path = self.webui / rel
        if not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type",
                         _CTYPES.get(path.suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _media(self, token: str, head_only: bool = False):
        path = self.media.resolve(token)
        if path is None:
            self.send_error(404)
            return
        ctype = _AUDIO_CTYPES.get(path.suffix.lower(), "application/octet-stream")
        size = path.stat().st_size
        start, end = 0, size - 1
        code = 200
        rng = self.headers.get("Range")
        if rng:
            m = _RANGE_RE.match(rng.strip())
            if m:
                if m.group(1):
                    start = int(m.group(1))
                    if m.group(2):
                        end = min(int(m.group(2)), size - 1)
                elif m.group(2):  # suffix range: last N bytes
                    start = max(0, size - int(m.group(2)))
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                code = 206
        length = end - start + 1
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if head_only:
            return
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(262144, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    return
                remaining -= len(chunk)

    # ---- routes ----

    def do_GET(self):  # noqa: N802
        try:
            route = unquote(urlparse(self.path).path)
            if route.startswith("/media/"):
                self._media(route[len("/media/"):])
            elif route == "/api/health":
                self._send_json(200, {"ok": True, "app": C.APP_ID, "version": C.VERSION})
            else:
                self._static(route)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:  # noqa: BLE001
            logging.getLogger("webui").warning("GET %s failed: %r", self.path, e)
            try:
                self.send_error(500)
            except Exception:  # noqa: BLE001
                pass

    def do_HEAD(self):  # noqa: N802
        route = unquote(urlparse(self.path).path)
        if route.startswith("/media/"):
            self._media(route[len("/media/"):], head_only=True)
        else:
            self.send_error(405)


def start_server(media: MediaStore, host: str = "127.0.0.1", port: int = 0):
    """Returns (ThreadingHTTPServer, base_url). Runs serve_forever in a thread."""
    handler = type("Handler", (_Handler,), {"media": media, "webui": C.webui_dir()})
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, name="webui-http", daemon=True).start()
    return httpd, f"http://{host}:{httpd.server_address[1]}"
