"""Paint the MSI wizard chrome from the SpellVision mark and ArcaneGlass tokens.

WelcomeDlg draws black text, transparent, starting at x=135 of 370 dialog units.
That is 36% across the 493px dialog bitmap, so the brand panel stops before it.
The banner title is also black and only covers the left half, so the mark sits
on the right.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MARK = ROOT / "qt_ui" / "icons" / "SpellVision.png"
OUT = ROOT / "installer" / "chrome"

SURFACE0 = (10, 11, 18)
SURFACE1 = (19, 22, 31)
TEXT_MID = (157, 163, 184)
ACCENT = (124, 92, 255)
PAPER = (247, 246, 251)
PAPER_EDGE = (236, 234, 244)
HAIR = (196, 201, 220)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = Path(r"C:/Windows/Fonts") / ("segoeuib.ttf" if bold else "segoeui.ttf")
    if path.is_file():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def mark(size: int) -> Image.Image:
    src = Image.open(MARK).convert("RGBA")
    pixels = src.load()
    for y in range(src.height):
        for x in range(src.width):
            r, g, b, a = pixels[x, y]
            if r > 200 and g > 200 and b > 200 and abs(r - g) < 12 and abs(g - b) < 12:
                pixels[x, y] = (r, g, b, 0)
    return src.resize((size, size), Image.Resampling.LANCZOS)


def dialog() -> Image.Image:
    image = Image.new("RGB", (493, 312), PAPER)
    draw = ImageDraw.Draw(image)
    for y in range(312):
        t = y / 311
        draw.line(
            [(168, y), (492, y)],
            fill=tuple(int(PAPER[i] * (1 - t) + PAPER_EDGE[i] * t) for i in range(3)),
        )
    panel = Image.new("RGB", (168, 312), SURFACE0)
    panel_draw = ImageDraw.Draw(panel)
    for y in range(312):
        t = y / 311
        panel_draw.line(
            [(0, y), (167, y)],
            fill=tuple(int(SURFACE0[i] * (1 - t * 0.35) + SURFACE1[i] * t * 0.35) for i in range(3)),
        )
    glow = Image.new("RGBA", (168, 312), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((24, 70, 144, 190), fill=(*ACCENT, 55))
    glow = glow.filter(ImageFilter.GaussianBlur(18))
    panel = Image.alpha_composite(panel.convert("RGBA"), glow).convert("RGB")
    icon = mark(92)
    panel_rgba = panel.convert("RGBA")
    panel_rgba.alpha_composite(icon, (38, 78))
    image.paste(panel_rgba.convert("RGB"), (0, 0))
    draw = ImageDraw.Draw(image)
    draw.line([(167, 0), (167, 311)], fill=HAIR)
    draw.line([(168, 0), (168, 311)], fill=ACCENT)
    label = "SPELLVISION"
    face = font(11, bold=True)
    box = draw.textbbox((0, 0), label, font=face)
    width = box[2] - box[0]
    draw.text(((168 - width) / 2, 188), label, font=face, fill=TEXT_MID)
    return image


def banner() -> Image.Image:
    image = Image.new("RGB", (493, 58), PAPER)
    draw = ImageDraw.Draw(image)
    icon = mark(36)
    image.paste(icon, (440, 11), icon)
    draw.line([(0, 56), (492, 56)], fill=ACCENT)
    draw.line([(0, 57), (492, 57)], fill=HAIR)
    return image


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dialog().save(OUT / "dialog.png")
    banner().save(OUT / "banner.png")
    print(OUT)


if __name__ == "__main__":
    main()
