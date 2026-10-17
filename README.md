# MelodyExtractor: A Deep-Learning-Based Main-Melody Extractor for Piezoelectric Buzzers

A local Windows desktop app that extracts the **main melody** from a song and
exports a monophonic MIDI file plus a compact pitch/duration TXT file.

English | [简体中文](README.zh-CN.md)

![Melody Extractor UI](docs/screenshots/gui.png)

> **Status:** desktop app v1.0.0. This repository contains the inference app and
> packaging scripts. Model weights and the Windows installer are distributed as
> release assets; the training pipeline and datasets are not included.

## Why this model exists

A passive piezoelectric buzzer has a single diaphragm driven by one excitation
signal, so it can emit only one tone at a time; moreover, when the excitation
frequency steps, the diaphragm undergoes a mechanical transient response and
rings, which is perceived as noise. To make such a buzzer play a usable melody,
one must therefore first extract a stable single monophonic line from the
polyphonic audio — a task that has traditionally relied on manual transcription,
which is costly and hard to scale.

Existing automatic methods each fall short in some way. Monophonic pitch
estimators such as YIN and CREPE, as well as the Melodia predominant-melody
algorithm in Essentia, perform well on single-line input, but under polyphony
their frame-wise pitch estimates tend to jump among several concurrent voices,
so the estimation confidence stays consistently low; adding post-processing
constraints such as smoothing and continuity brings only limited improvement.
Viterbi-decoding and CNN-based methods for polyphonic melody, in turn, mostly
build on hand-crafted pitch-salience features and model only local temporal
context, so they struggle to capture the long-range structure of a melody and
cannot fundamentally resolve cross-voice interference.

Against this backdrop, and given the scarcity of aligned polyphonic-melody
datasets, we collected and built an aligned dataset from the harmonica community
of the game Delta Force, and propose MelodyExtractor: it employs a MERT
pre-trained encoder to extract music representations, a bidirectional GRU to
model temporal context, and chord detection as an auxiliary task that supplies
harmonic context, forming joint multi-task supervision with melody prediction and
trained end-to-end on the aligned data. At inference it applies no Viterbi/HMM
smoothing; the stable monophonic output relies on the model's own temporal
modeling, and only lightweight note segmentation (median filtering, gap closing
and a minimum note length) turns frame decisions into notes.

> **Note:** This project is experimental. The aligned dataset is small, and
> extraction quality is poor on some songs; treat the output as a starting
> point rather than a finished transcription.

## Highlights

- **Fully local** — audio never leaves the machine; no account, API key or
  network call is needed at runtime.
- **GPU or CPU** — ONNX Runtime DirectML when a DirectX 12 GPU is available,
  automatic CPU fallback otherwise. No CUDA installation.
- **Optional source separation** — htdemucs builds a melody-friendly
  `vocals + other` bed; separation can be skipped for speed.
- **Audition** — synthesized preview of the extracted melody with pitch-ratio
  changes applied in real time.
- **Pitch ratio** — 0.25×–4× slider plus a free input for 0.1×–10×; applied to
  the TXT frequencies and to the MIDI pitch (rounded to the nearest semitone).
- **Stable exports** — monophonic MIDI and a five-groups-per-line TXT format
  with integer Hz, integer milliseconds, explicit silence and a continuous
  timeline.
- **Reproducible separation** — the htdemucs random-shift seed is pinned, so
  repeated runs on the same machine give identical separation output.

## Requirements

- Windows 10/11 x64
- Microsoft Edge WebView2 Runtime (the installer checks and offers the
  official download page; Windows 11 usually has it)
- Python 3.12 x64 for running from source
- ~1 GB free disk space for the two model files
- 8 GB RAM recommended; a DirectX 12 GPU is optional but recommended

## Install

### Windows installer

Download `MelodyExtractor_Setup_v1.0.0.exe` from
[Releases](../../releases), run it, choose the install directory, and optionally
create a desktop shortcut. The installer registers an uninstaller.

### Run from source

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
pip install -r requirements.txt
python scripts/download_models.py
python main.py
```

If `download_models.py` cannot find a release asset, place the files manually
as described in [models/README.md](models/README.md). A headless end-to-end
check (synthetic tone → demucs → ONNX → TXT/MIDI) is available:

```bat
python main.py --selftest
```

## Model files

The weights are not stored in git:

| File | Size | SHA-256 |
| --- | ---: | --- |
| `models/melody_mert95.onnx` | 381 MiB | `cea1a8418f8c5e1e0b38335ad7b9a0c05dcdb0da7efd613a47983feb89d887ea` |
| `models/demucs/955717e8-8726e21a.th` | 80 MiB | `8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4` |

`models/demucs/htdemucs.yaml` is checked in. The download script reads the
latest GitHub Release when run from a clone with a GitHub `origin`, verifies
both checksums, and falls back to Meta's official htdemucs URL for the
checkpoint.

## How it works

1. **Decode** — PyAV/FFmpeg decodes any supported format to 44.1 kHz stereo
   (for separation) or 24 kHz mono (without separation).
2. **Separate** — htdemucs keeps `vocals + other` as a melody bed; a fixed
   random seed makes the result reproducible.
3. **Infer** — the melody bed is resampled to 24 kHz and z-normalized over the
   whole song, then fed to the ONNX model in 163,840-sample chunks with a
   163,520-sample step. The model emits 75 Hz frame logits for 60 pitch bins
   (MIDI 36–95) plus a silence class.
4. **Events** — argmax, 5-frame median filter, merge same-pitch gaps ≤50 ms,
   drop notes shorter than 60 ms; the result is monophonic by construction.
5. **Export** — MIDI and TXT, plus a synthesized audition track.

Model contract for the ONNX graph:

| | |
| --- | --- |
| Input | `wav` float32 `(1, T)`, 24 kHz, z-normalized, `T >= 400` |
| Output | `melody_logits` float32 `(1, F, 61)`, `F = (T - 400) // 320 + 1` |
| Classes | 0–59 → MIDI 36–95, 60 → silence |
| Hop | 1/75 s |

The exported graph was checked against PyTorch on a full song: frame-level
argmax agreement was 100% for both the DirectML and CPU execution providers on
the test machine.

## TXT format

Every group is `{frequency_hz, duration_ms}`. Frequencies are rounded integers;
durations are integer milliseconds. Five groups per line, a comma and a space
between groups, and a trailing comma at the end of every line. Silence is
written as `{0, duration}`; the timeline is continuous and covers the processed
duration. The file is UTF-8 without BOM, uses LF line endings, and ends with a
newline. The final line may contain fewer than five groups.

```text
{262, 480}, {330, 240}, {0, 120}, {392, 960}, {440, 120},
{494, 360}, {523, 240}, {0, 600}, {587, 480}, {659, 240},
```

MIDI export applies the pitch ratio and rounds each note to the nearest
semitone; the TXT export keeps the exact shifted frequency rounded to integer
Hz. Both outputs come from the same note events.

## Build

Install [Inno Setup 6.7.3](https://jrsoftware.org/isdl.php), then:

```bat
pip install -r requirements-build.txt
python scripts/download_models.py
pyinstaller pack/melody_extractor.spec --noconfirm --clean ^
  --distpath pack/dist --workpath pack/build
cd pack
iscc installer.iss
```

The PyInstaller bundle is written to `pack/dist/MelodyExtractor/`; the installer
is written to `pack/installer/MelodyExtractor_Setup_v1.0.0.exe`. The spec
bundles the app, WebUI, ONNX model, htdemucs checkpoint and the runtime
libraries; Inno Setup adds shortcuts, an uninstaller and a WebView2 check.

`pack/ChineseSimplified.isl` comes from the Inno Setup source tree. Keep its
header when redistributing.

## Repository layout

```text
app/                 pipeline, ORT session, decoders, exporters, server, bridge
webui/               the HTML/CSS/JS interface loaded by WebView2
main.py              desktop entry point and --selftest
pack/                PyInstaller spec, icon generator, Inno Setup script
scripts/             model downloader / verifier
models/              model placement instructions (weights are git-ignored)
docs/screenshots/    UI screenshots
```

## License

- **Source code:** MIT — see [LICENSE](LICENSE).
- **Model weights:** CC BY-NC 4.0, **non-commercial** — see
  [LICENSE-MODEL.md](LICENSE-MODEL.md).
- **Third-party components:** see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

The non-commercial restriction comes from the MERT-v1-95M backbone
(CC BY-NC 4.0) and from fine-tuning on MIR-1K (research use only). No MIR-1K
audio or labels, and no user audio or labels, are included in this repository.
If you need commercial rights to a melody model, use a commercially licensed
backbone and training data and retrain the model.

## Credits

- [MERT](https://huggingface.co/m-a-p/MERT-v1-95M) — acoustic music representation
- [Demucs](https://github.com/facebookresearch/demucs) — music source separation
- [ONNX Runtime](https://onnxruntime.ai/) and
  [DirectML](https://learn.microsoft.com/windows/ai/directml/) — local inference
- [PyAV](https://pyav.org/) / FFmpeg — decoding
- [pywebview](https://pywebview.flowrl.com/) — native window and bridge
- [pretty_midi](https://github.com/craffel/pretty-midi) — MIDI writer
- [Inno Setup](https://jrsoftware.org/isinfo.php) — installer

## Limitations

- It extracts one melody line, not a full transcription. Dense mixes may make
  the model follow an accompaniment or an inner voice.
- Octave errors and note-boundary errors are possible; the model is a research
  prototype, not a replacement for a trained transcriber.
- Demucs runs on CPU (roughly real time on a typical desktop CPU); DirectML
  accelerates the melody model, not separation.
- Windows-only, and the current UI is in Chinese.
- Model loading and the first inference take longer than subsequent runs.
