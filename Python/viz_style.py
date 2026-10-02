"""Shared chart style for this project: cool light canvas, Corbel type, a thin cobalt line under each headline,
rounded bar ends, direct labels. The Power BI report uses the same palette.

Colour meanings (same in every chart, the dashboard and the README):
    MET      cobalt blue: hospitals that met the interoperability standards / connected
    SHORT    vermilion: hospitals that fell short
    NO_EHR   purple: hospitals that reported no certified EHR at all
    GREY     everything else
"""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter

MET, MET_L = "#2457D6", "#A9BFF2"
SHORT, SHORT_L = "#E8552B", "#F6B9A4"
NO_EHR, NO_EHR_L = "#6D28D9", "#C9B5F2"
GREY, GREY_L = "#8A93A3", "#D5DAE3"
PAPER, INK, INK_2, GRID = "#F6F8FC", "#141B2D", "#4E5A70", "#E3E8F1"
FONT = ["Corbel", "Segoe UI", "DejaVu Sans"]

IMAGE_DIR = Path(__file__).resolve().parents[1] / "Image"
IMAGE_DIR.mkdir(exist_ok=True)


def apply():
    plt.rcParams.update({
        "figure.facecolor": PAPER, "axes.facecolor": PAPER, "savefig.facecolor": PAPER,
        "figure.dpi": 110, "savefig.dpi": 150, "figure.figsize": (9, 4.8),
        "font.family": FONT, "font.size": 11.5, "text.color": INK,
        "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2,
        "axes.edgecolor": GREY_L, "axes.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.9,
        "axes.axisbelow": True, "legend.frameon": False, "lines.linewidth": 2.6,
        "xtick.major.size": 0, "ytick.major.size": 0,
    })


def title(ax, text, sub=None):
    ax.set_title(text, fontsize=17, fontweight="bold", loc="left", pad=34 if sub else 16, color=INK)
    if sub:
        ax.annotate(sub, (0, 1), xycoords="axes fraction", xytext=(0, 10), textcoords="offset points",
                    color=INK_2, fontsize=12, va="bottom")
    ax._underline = True


def pct(ax, axis="y"):
    fmt = FuncFormatter(lambda v, _: f"{v:.0f}%")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)


def source(fig, text="Source: CMS Promoting Interoperability (Hospital General Information 2019-2024; reporting year "
                     "2024), ONC Certified Health IT Product List. General acute care and critical access hospitals."):
    fig.text(0.01, -0.02, text, color=GREY, fontsize=8.5, ha="left", va="top")


def save(fig, name):
    fig.tight_layout()
    fig.canvas.draw()
    w, h = fig.get_size_inches() * fig.dpi
    for ax in fig.axes:          # short cobalt line under each headline block
        if getattr(ax, "_underline", False):
            top = ax.title.get_window_extent().y1 + 20 / 72 * fig.dpi
            x0 = ax.get_position().x0
            fig.add_artist(Line2D([x0, x0 + 46 / 72 * fig.dpi / w], [top / h] * 2, transform=fig.transFigure,
                                  color=MET, lw=4, solid_capstyle="round"))
    fig.savefig(IMAGE_DIR / f"{name}.png", bbox_inches="tight")
    plt.close(fig)
