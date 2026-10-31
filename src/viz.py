"""Style graphique commun (palette validée du skill dataviz, figures sobres).

Règles : une couleur par entité, ordre fixe ; mise en avant d'un élément sur fond
gris ; grilles fines et discrètes ; séquentiel = une seule teinte ; divergent =
bleu ↔ rouge avec milieu gris.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

from . import config as C  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
NEUTRAL = "#c3c2b7"      # barres « non mises en avant »

# Palette catégorielle (ordre fixe validé)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = SERIES

# Une couleur fixe par modèle (la couleur suit le modèle, jamais son rang)
MODEL_COLORS = {"M1": BLUE, "M2": ORANGE, "M3": AQUA, "M4": YELLOW, "M5": MAGENTA,
                "M5_sansFiLM": GREEN, "M5_sansCout": VIOLET, "M5_dropClin": RED}

SEQ_BLUE = LinearSegmentedColormap.from_list(
    "seq_blue", ["#fcfcfb", "#cde2fb", "#86b6ef", "#3987e5", "#256abf", "#184f95", "#0d366b"])
DIVERGING = LinearSegmentedColormap.from_list("div_br", ["#256abf", "#f0efec", "#e34948"])


def setup() -> None:
    """Applique le style à matplotlib (à appeler une fois)."""
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.titlecolor": INK,
        "axes.titlesize": 11, "axes.titleweight": "bold", "axes.labelsize": 9.5,
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "grid.linestyle": "-",
        "axes.spines.top": False, "axes.spines.right": False, "axes.axisbelow": True,
        "legend.frameon": False, "legend.fontsize": 8.5, "font.size": 9.5,
        "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
        "lines.linewidth": 2.0, "figure.dpi": 110, "savefig.dpi": 160, "savefig.bbox": "tight",
    })


def save(fig, name: str) -> None:
    """Enregistre une figure PNG dans resultats/figures."""
    fig.savefig(C.FIG_DIR / f"{name}.png")
    plt.close(fig)


def emphasis_colors(labels, highlight="mel"):
    """Couleur d'accent pour l'élément mis en avant, gris pour les autres."""
    return [BLUE if lab == highlight else NEUTRAL for lab in labels]
