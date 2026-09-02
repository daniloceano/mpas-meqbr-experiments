"""Shared figure style and map helpers.

One style module so that every figure in the repo — validation, selection,
exploration — is legible in the same way and can be put side by side without a
visual seam. Colours are chosen so the experiments keep a fixed identity across
every figure: a reader who learns the colours once reads every plot faster.
"""

from __future__ import annotations

import numpy as np

# Fixed identity per experiment, used in every figure.
EXPERIMENT_COLORS = {
    "CTL":   "#4C4C4C",   # grey — the baseline
    "EXP01": "#1F77B4",   # blue
    "EXP02": "#D62728",   # red
    "ERA5":  "#7F7F7F",   # light grey, dashed where lines are drawn
    "OBS":   "#000000",
}
EXPERIMENT_ORDER = ["CTL", "EXP01", "EXP02"]

SITE_MARKERS = {"P0": "o", "LPI": "s"}

# Sequential map for wind speed; diverging for differences. Both are
# perceptually uniform and survive greyscale printing reasonably.
CMAP_SPEED = "viridis"
CMAP_DIFF = "RdBu_r"


def use_style(scale: float = 1.0) -> None:
    """Apply the repo's matplotlib defaults. Call once at the top of a script."""
    import matplotlib as mpl

    mpl.rcParams.update({
        "figure.dpi": 110,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
        "font.size": 9 * scale,
        "axes.titlesize": 10 * scale,
        "axes.labelsize": 9 * scale,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "grid.linewidth": 0.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "lines.linewidth": 1.4,
    })


def coastlines(ax, *, resolution: str = "10m", lw: float = 0.6, color: str = "0.25"):
    """Add cartopy coastlines if available; degrade gracefully if it is not.

    Figures should not fail to be produced because a mapping dependency is
    missing on the machine that happens to be running the batch.
    """
    try:
        import cartopy.feature as cfeature
        ax.add_feature(cfeature.COASTLINE.with_scale(resolution),
                       linewidth=lw, edgecolor=color)
        ax.add_feature(cfeature.BORDERS.with_scale(resolution),
                       linewidth=lw * 0.6, edgecolor=color, alpha=0.6)
        return True
    except Exception:
        return False


def add_site_markers(ax, sites, *, transform=None, fontsize=8):
    """Mark the LiDAR sites on a map, always the same way."""
    kw = {"transform": transform} if transform is not None else {}
    for key, site in sites.items():
        ax.plot(site.lon, site.lat, marker=SITE_MARKERS.get(key, "o"),
                ms=6, mfc="none", mec="k", mew=1.4, zorder=6, **kw)
        ax.annotate(key, (site.lon, site.lat), textcoords="offset points",
                    xytext=(7, 4), fontsize=fontsize, zorder=6,
                    bbox=dict(fc="white", ec="none", alpha=0.7, pad=1.0), **kw)


def symmetric_limits(values, percentile: float = 99.0) -> float:
    """A symmetric colour limit for a difference field, robust to outliers."""
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return 1.0
    return float(np.percentile(np.abs(v), percentile))


def provenance_footer(fig, text: str, *, fontsize: float = 6.0,
                      layout: bool = True) -> None:
    """Stamp a figure with what produced it and over what period.

    Every figure in this repo carries one. A figure that ends up in a slide deck
    six months from now should still be able to say which script, which
    experiment and which window it came from.
    """
    # Lay the axes out first so the tick and axis labels are inside the figure
    # box, then place the footer a fixed 0.35 in below it. With
    # savefig.bbox="tight" the saved image grows to include the footer, so it
    # never collides with the x label however tall the figure is.
    if layout:
        try:
            fig.tight_layout()
        except Exception:                              # some polar/GridSpec layouts
            pass
    fig.text(0.0, -0.35 / fig.get_figheight(), text, fontsize=fontsize,
             color="0.45", ha="left", va="top")
