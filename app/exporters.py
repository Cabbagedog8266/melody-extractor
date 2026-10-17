"""MIDI + TXT writers.

TXT format is locked against the user's reference file (song2_melody.txt):
  {freq, ms}, comma separated, 5 groups per line, trailing comma on every
  line; integer Hz (base freq x ratio, rounded); integer milliseconds;
  silence written as {0, ms}; continuous timeline covering the processed
  duration (all groups sum to it). LF line endings, trailing newline.
"""
import math

import numpy as np

FMIN_MIDI = 36


def freq_hz(midi: int, ratio: float = 1.0) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12) * ratio


def _ms(frame: int, hop_s: float) -> int:
    return int(round(frame * hop_s * 1000))


def format_txt(notes, hop_s: float, ratio: float, total_frames: int,
               fmin_midi: int = FMIN_MIDI) -> str:
    """notes: iterable of (start_frame, end_frame, pitch_index)."""
    events = []
    cur = 0
    for s, e, q in notes:
        e = min(int(e), total_frames)
        s = max(0, int(s))
        if e <= s:
            continue
        s_ms, e_ms = _ms(s, hop_s), _ms(e, hop_s)
        if s_ms > cur:
            events.append((0, s_ms - cur))
            cur = s_ms
        dur = e_ms - cur
        if dur > 0:
            events.append((int(round(freq_hz(q + fmin_midi, ratio))), dur))
            cur = e_ms
    total_ms = _ms(total_frames, hop_s)
    if total_ms > cur:
        events.append((0, total_ms - cur))
    lines = []
    for i in range(0, len(events), 5):
        lines.append(", ".join("{%d, %d}" % ev for ev in events[i:i + 5]) + ",")
    return "\n".join(lines) + "\n" if lines else ""


def write_txt(path, notes, hop_s, ratio, total_frames, fmin_midi=FMIN_MIDI):
    text = format_txt(notes, hop_s, ratio, total_frames, fmin_midi)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return text


def write_midi(path, notes, hop_s, ratio: float = 1.0, fmin_midi=FMIN_MIDI):
    """MIDI notes are rounded to the nearest semitone after the ratio shift."""
    import pretty_midi
    shift = 12 * math.log2(ratio)
    pm = pretty_midi.PrettyMIDI(initial_tempo=120)
    inst = pretty_midi.Instrument(program=0, name="melody")
    for s, e, q in notes:
        pitch = int(round(q + fmin_midi + shift))
        pitch = max(0, min(127, pitch))
        inst.notes.append(pretty_midi.Note(
            velocity=100, pitch=pitch, start=s * hop_s, end=e * hop_s))
    pm.instruments.append(inst)
    pm.write(str(path))
    return str(path)


def synth_peaks(notes, hop_s, total_frames, sr=24000, n_bars=220):
    """abs-max envelope of a sine+harmonics synth of the notes (melody waveform)."""
    n = max(1, total_frames) * 320
    y = np.zeros(n, dtype=np.float32)
    nf = int(0.006 * sr)
    for s, e, q in notes:
        a = int(round(int(s) * hop_s * sr))
        b = min(int(round(int(e) * hop_s * sr)), n)
        if b <= a:
            continue
        f = freq_hz(q + FMIN_MIDI)
        t = np.arange(b - a) / sr
        env = np.ones_like(t)
        if len(t) > 2 * nf:
            env[:nf] = np.linspace(0.0, 1.0, nf)
            env[-nf:] = np.linspace(1.0, 0.0, nf)
        tone = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t)
                + 0.12 * np.sin(6 * np.pi * f * t))
        y[a:b] = (0.28 * env * tone).astype(np.float32)
    return peaks_of(y, n_bars)


def peaks_of(y: np.ndarray, n_bars: int) -> list:
    if y.size == 0:
        return [0.0] * n_bars
    idx = np.linspace(0, y.size, n_bars + 1).astype(np.int64)
    bars = []
    for i in range(n_bars):
        a, b = idx[i], max(idx[i] + 1, idx[i + 1])
        seg = np.abs(y[a:b])
        bars.append(float(seg.max()) if seg.size else 0.0)
    m = max(bars) or 1.0
    return [round(v / m, 3) for v in bars]
