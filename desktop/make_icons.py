"""Generate the application icon (icon.png + icon.ico) from code.

Run after changing the brand colours:  python desktop/make_icons.py
Requires Pillow (`pip install pillow`) - build-time only, not shipped.
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).resolve().parent
SIZE = 1024

PURPLE_LIGHT = (107, 63, 255)     # #6B3FFF
PURPLE_DARK = (75, 14, 255)       # #4B0EFF
WHITE = (255, 255, 255)


def _gradient(size):
    img = Image.new("RGB", (size, size), PURPLE_DARK)
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size)
            px[x, y] = tuple(
                round(PURPLE_LIGHT[i] + (PURPLE_DARK[i] - PURPLE_LIGHT[i]) * t)
                for i in range(3)
            )
    return img


def build():
    img = _gradient(SIZE).convert("RGBA")

    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=int(SIZE * 0.22), fill=255)
    img.putalpha(mask)

    d = ImageDraw.Draw(img)
    # Evidence "folder" body with a check mark: audit evidence, packaged.
    left, top, right, bottom = SIZE * 0.20, SIZE * 0.30, SIZE * 0.80, SIZE * 0.76
    d.rounded_rectangle((left, SIZE * 0.22, left + SIZE * 0.24, SIZE * 0.36), radius=SIZE * 0.03, fill=WHITE)
    d.rounded_rectangle((left, top, right, bottom), radius=SIZE * 0.05, fill=WHITE)
    w = int(SIZE * 0.05)
    check = [(SIZE * 0.36, SIZE * 0.53), (SIZE * 0.46, SIZE * 0.63), (SIZE * 0.65, SIZE * 0.43)]
    d.line(check, fill=PURPLE_DARK, width=w, joint="curve")
    for x, y in (check[0], check[-1]):
        d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=PURPLE_DARK)
    return img


if __name__ == "__main__":
    icon = build()
    icon.save(OUT_DIR / "icon.png")
    icon.save(
        OUT_DIR / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("Wrote icon.png and icon.ico in", OUT_DIR)
