"""Audio decoding via PyAV (any format ffmpeg reads) to float32 numpy."""
import av
import numpy as np


def probe(path) -> dict:
    with av.open(str(path)) as c:
        st = next((s for s in c.streams if s.type == "audio"), None)
        if st is None:
            raise ValueError("文件不包含音频流")
        dur = 0.0
        if c.duration:
            dur = c.duration / av.time_base
        elif st.duration:
            dur = float(st.duration * st.time_base)
        return {
            "codec": st.codec_context.name,
            "sr": st.codec_context.sample_rate,
            "channels": st.codec_context.channels,
            "duration_s": dur,
        }


def decode(path, sr: int, channels: int = 1) -> np.ndarray:
    """Decode audio file to float32 (channels, N) resampled to `sr`."""
    out = []
    with av.open(str(path)) as c:
        st = next((s for s in c.streams if s.type == "audio"), None)
        if st is None:
            raise ValueError("文件不包含音频流")
        layout = "mono" if channels == 1 else "stereo"
        res = av.AudioResampler(format="fltp", layout=layout, rate=sr)
        for frame in c.decode(st):
            for rf in res.resample(frame):
                out.append(rf.to_ndarray())
        for rf in res.resample(None):
            out.append(rf.to_ndarray())
    if not out:
        return np.zeros((channels, 0), dtype=np.float32)
    return np.concatenate(out, axis=1).astype(np.float32)
