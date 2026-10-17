"""Generate the app .ico: accent rounded square + white waveform bars."""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "appicon.ico"
ACCENT = (47, 111, 237, 255)
S = 256


def draw(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = size * 0.22
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=ACCENT)
    # four bars, heights relative
    heights = [0.34, 0.62, 0.46, 0.78]
    bw = size * 0.115
    gap = (size - 4 * bw) / 5
    for i, h in enumerate(heights):
        x0 = gap + i * (bw + gap)
        bh = size * h
        y0 = (size - bh) / 2
        d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=bw / 2, fill=(255, 255, 255, 255))
    return img


def main():
    base = draw(S)
    base.save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", OUT, OUT.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
