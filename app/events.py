"""Frame-level pitch/voicing -> monophonic note events.

Port of infer_melody.events_from_frames with a numpy median filter that
matches scipy.ndimage.median_filter(size, mode='reflect') exactly.
"""
import numpy as np


def _median_filter_reflect(x: np.ndarray, size: int) -> np.ndarray:
    # scipy.ndimage mode='reflect' repeats the edge pixel == np.pad 'symmetric'
    pad = size // 2
    xp = np.pad(x, pad, mode="symmetric")
    wins = np.stack([xp[k:k + x.shape[0]] for k in range(size)], axis=0)
    return np.median(wins, axis=0).astype(x.dtype)


def events_from_frames(pitch, voiced, hop_s=0.013333, median=5,
                       min_note_s=0.06, min_gap_s=0.05):
    """(start_frame, end_frame, pitch_index) monophonic notes."""
    p = pitch.astype(np.int32).copy()
    v = voiced.astype(bool)
    p = np.where(v, _median_filter_reflect(p, median), -1)
    min_gap = max(1, int(round(min_gap_s / hop_s)))
    min_note = max(1, int(round(min_note_s / hop_s)))

    runs = []
    i, n = 0, len(p)
    while i < n:
        j = i
        while j < n and p[j] == p[i]:
            j += 1
        runs.append([bool(p[i] >= 0), i, j, int(p[i])])
        i = j
    merged = []
    for r in runs:
        if (merged and r[0] and merged[-1][0] and r[3] == merged[-1][3]
                and r[1] - merged[-1][2] <= min_gap):
            merged[-1][2] = r[2]
        else:
            merged.append(r)
    return [(s, e, q) for vo, s, e, q in merged if vo and (e - s) >= min_note]
