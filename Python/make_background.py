"""Draw the artwork for the Power BI report (written to dashboard/assets/, colours from layout.json, which
06_build_powerbi_project.py writes):

    page_bg.png  the page background: cool paper with a fine "blueprint" grid and the navy rail on the right
    logo.png     the rail logo: two health records (nodes) joined by a link

Only things that do not depend on exact vertical position are drawn here. Power BI Desktop stretches a page image
over a slightly taller area than the one its visuals use, so cards, stripes and labels are visuals instead.
Rendered at 2x the 1280 x 720 page for sharp lines on high-DPI screens.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "dashboard" / "assets"
S = 2
W, H = 1280 * S, 720 * S


def rgb(h, a=255):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def page(c):
    """Paper fading from light at the top, a fine grid (minor every 16 px, major every 80 px), white rail."""
    yy = np.linspace(0, 1, H)[:, None, None]
    top, bottom = np.array(rgb(c["paper_top"])[:3], float), np.array(rgb(c["paper"])[:3], float)
    im = Image.fromarray((top * (1 - yy) + bottom * yy).repeat(W, axis=1).astype(np.uint8)).convert("RGBA")
    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(grid)
    for i, x in enumerate(range(0, W, 16 * S)):
        d.line([x, 0, x, H], fill=rgb(c["grid"], 150 if i % 5 == 0 else 70), width=1)
    for i, y in enumerate(range(0, H, 16 * S)):
        d.line([0, y, W, y], fill=rgb(c["grid"], 150 if i % 5 == 0 else 70), width=1)
    im = Image.alpha_composite(im, grid)
    d = ImageDraw.Draw(im)
    x0 = c["rail_x"] * S
    d.rectangle([x0, 0, W, H], fill=rgb(c["rail"]))
    return im


def logo(c, size=96):
    """Rounded cobalt square, two nodes joined by a line (one white, one mint)."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, size - 1, size - 1], size * 0.24, fill=rgb(c["cobalt"]))
    r = size * 0.15
    a, b = (size * 0.30, size * 0.64), (size * 0.70, size * 0.36)
    d.line([a, b], fill=(255, 255, 255, 255), width=round(size * 0.065))
    for (cx, cy), fill in ((a, (255, 255, 255, 255)), (b, rgb(c["mint"]))):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=(255, 255, 255, 255), width=round(size * 0.04))
    return im


def main():
    c = json.loads((ASSETS / "layout.json").read_text(encoding="utf-8"))["colors"]
    page(c).convert("RGB").save(ASSETS / "page_bg.png", optimize=True)
    logo(c).save(ASSETS / "logo.png", optimize=True)
    print(f"wrote page_bg.png and logo.png to {ASSETS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
