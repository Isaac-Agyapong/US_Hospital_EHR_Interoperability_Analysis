"""Draw the artwork for the Power BI report (written to dashboard/assets/, colours from layout.json, which
06_build_powerbi_project.py writes):

    page_bg.png  the page background: deep navy page with the darker rail on the right
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
    """Deep blue to indigo diagonal gradient, two soft glows (sky blue lower left, violet upper right),
    a faint dot texture, and the dark rail on the right."""
    yy, xx = np.mgrid[0:H, 0:W].astype(float)
    t = ((xx / W) * 0.55 + (yy / H) * 0.45)[..., None]
    a, b = np.array(rgb(c["paper"])[:3], float), np.array(rgb(c["paper_top"])[:3], float)
    img = a * (1 - t) + b * t
    for (cx, cy, rx, ry, col, k) in []:          # no glows: a calm, neutral page
        g = np.exp(-(((xx - W * cx) / (W * rx)) ** 2 + ((yy - H * cy) / (H * ry)) ** 2))[..., None]
        img = img + g * (np.array(rgb(col)[:3], float) - img) * k
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")
    dots = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(dots)
    for y in range(12 * S, H, 24 * S):
        for x in range(12 * S, W, 24 * S):
            pass
    im = Image.alpha_composite(im, dots)
    d = ImageDraw.Draw(im)
    x0 = c["rail_x"] * S
    d.rectangle([x0, 0, W, H], fill=rgb(c["rail"]))
    d.line([x0, 0, x0, H], fill=rgb(c["line"]), width=S)
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
