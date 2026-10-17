#!/usr/bin/env python3
"""Download and verify the model files used by Melody Extractor.

The ONNX model is distributed as a GitHub Release asset. When this script is
run from a clone with a GitHub ``origin`` it looks up the latest release. You
can also pass an explicit URL. The htdemucs checkpoint falls back to the
official Meta download URL if the release does not carry it.

    python scripts/download_models.py
    python scripts/download_models.py --onnx-url https://host/melody_mert95.onnx
    python scripts/download_models.py --skip-demucs
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
DEMUCS_DIR = MODELS / "demucs"

ONNX_NAME = "melody_mert95.onnx"
ONNX_SHA256 = "cea1a8418f8c5e1e0b38335ad7b9a0c05dcdb0da7efd613a47983feb89d887ea"
DEMUCS_NAME = "955717e8-8726e21a.th"
DEMUCS_SHA256 = "8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4"
DEMUCS_FALLBACK = (
    "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th"
)

USER_AGENT = "melody-extractor-model-loader"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def github_slug() -> tuple[str, str] | None:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(ROOT), "remote", "get-url", "origin"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", out)
    return (m.group(1), m.group(2)) if m else None


def latest_asset(name: str) -> str | None:
    slug = github_slug()
    if slug is None:
        return None
    url = f"https://api.github.com/repos/{slug[0]}/{slug[1]}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            release = json.load(r)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"  release lookup failed: {e}")
        return None
    for asset in release.get("assets", []):
        if asset.get("name") == name:
            return asset.get("browser_download_url")
    return None


def download(url: str, dest: Path, label: str) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, part.open("wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(
                        f"\r  {label}: {done / 1e6:.1f}/{total / 1e6:.1f} MB "
                        f"({done * 100 / total:5.1f}%)",
                        end="",
                        flush=True,
                    )
        if total:
            print()
        part.replace(dest)
        return True
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        part.unlink(missing_ok=True)
        print(f"\n  download failed: {e}")
        return False


def ensure(label: str, dest: Path, sha: str, url: str | None) -> bool:
    if dest.is_file():
        got = sha256(dest)
        if got == sha:
            print(f"[ok] {label} already present ({dest.stat().st_size / 1e6:.0f} MB)")
            return True
        print(f"[warn] {label} checksum mismatch, replacing")
    if not url:
        print(f"[missing] {label}: no download URL for this clone")
        return False
    print(f"[get] {label} <- {url}")
    if not download(url, dest, label):
        return False
    got = sha256(dest)
    if got != sha:
        print(f"[fail] {label} sha256 mismatch\n  expected {sha}\n  got      {got}")
        return False
    print(f"[ok] {label} ({dest.stat().st_size / 1e6:.0f} MB)")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--onnx-url", help="explicit melody_mert95.onnx URL")
    ap.add_argument("--demucs-url", help="explicit htdemucs checkpoint URL")
    ap.add_argument("--skip-demucs", action="store_true",
                    help="do not download the htdemucs checkpoint")
    a = ap.parse_args()

    MODELS.mkdir(exist_ok=True)
    DEMUCS_DIR.mkdir(exist_ok=True)

    onnx_url = a.onnx_url or latest_asset(ONNX_NAME)
    if onnx_url is None:
        print(
            "The ONNX model is attached to the GitHub Release. If this clone has\n"
            "no GitHub origin, pass --onnx-url <asset-url> or copy the file to\n"
            f"  {MODELS / ONNX_NAME}\n"
        )
    ok = ensure(ONNX_NAME, MODELS / ONNX_NAME, ONNX_SHA256, onnx_url)

    if not a.skip_demucs:
        demucs_url = a.demucs_url or latest_asset(DEMUCS_NAME) or DEMUCS_FALLBACK
        ok = ensure(DEMUCS_NAME, DEMUCS_DIR / DEMUCS_NAME, DEMUCS_SHA256,
                    demucs_url) and ok

    if ok:
        print("Models are ready. Launch with: python main.py")
        return 0
    print("Some model files are missing; see models/README.md.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
