"""Draw the Windows shortcut icons (biome, demo, risk) as multi-size .ico files.

Usage: python tools/build_icons.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

TARGET = Path(__file__).resolve().parents[1] / "src" / "evolution_sim" / "assets"
SIZE = 256
TEAL, GOLD, ROSE = (123, 224, 194), (240, 205, 138), (241, 160, 124)
INK, NIGHT = (238, 244, 239), (6, 34, 42)


def _base(colours: tuple[tuple[int, int, int], ...]) -> Image.Image:
    """Rounded tile with a conic gradient through ``colours``."""
    tile = Image.new("RGBA", (SIZE, SIZE))
    pixels = tile.load()
    centre = SIZE / 2
    stops = [*colours, colours[0]]
    for y in range(SIZE):
        for x in range(SIZE):
            angle = (math.atan2(y - centre, x - centre) + math.pi) / (2 * math.pi)
            position = angle * (len(stops) - 1)
            index = min(int(position), len(stops) - 2)
            mix = position - index
            a, b = stops[index], stops[index + 1]
            pixels[x, y] = (*(round(a[i] + (b[i] - a[i]) * mix) for i in range(3)), 255)
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((8, 8, SIZE - 8, SIZE - 8), radius=58, fill=255)
    out = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    out.paste(tile, mask=mask)
    return out


def _shadowed(icon: Image.Image, glyph: Image.Image) -> Image.Image:
    shadow = Image.new("RGBA", icon.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 110), mask=glyph.split()[3])
    icon.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(6)), (0, 4))
    icon.alpha_composite(glyph)
    return icon


def biome() -> Image.Image:
    icon = _base((TEAL, GOLD, ROSE))
    glyph = Image.new("RGBA", icon.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(glyph)
    draw.polygon([(70, 74), (128, 196), (186, 74), (160, 74), (128, 146), (96, 74)], fill=NIGHT)
    draw.ellipse((168, 48, 204, 84), fill=INK)
    return _shadowed(icon, glyph)


def demo() -> Image.Image:
    icon = _base((GOLD, ROSE, GOLD))
    glyph = Image.new("RGBA", icon.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(glyph)
    draw.ellipse((52, 52, 204, 204), fill=NIGHT)
    draw.polygon([(106, 88), (106, 168), (172, 128)], fill=GOLD)
    return _shadowed(icon, glyph)


def risk() -> Image.Image:
    icon = _base((TEAL, (90, 170, 220), TEAL))
    glyph = Image.new("RGBA", icon.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(glyph)
    draw.ellipse((56, 56, 200, 200), outline=NIGHT, width=16)
    draw.arc((56, 56, 200, 200), start=200, end=340, fill=ROSE, width=16)
    draw.line([(128, 128), (176, 92)], fill=NIGHT, width=14)
    draw.ellipse((114, 114, 142, 142), fill=NIGHT)
    return _shadowed(icon, glyph)


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    for name, painter in (("vikasa-biome", biome), ("vikasa-demo", demo), ("vikasa-risk", risk)):
        image = painter()
        image.save(TARGET / f"{name}.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                                   (64, 64), (128, 128), (256, 256)])
        image.save(TARGET / f"{name}.png")
        print(TARGET / f"{name}.ico")


if __name__ == "__main__":
    main()
