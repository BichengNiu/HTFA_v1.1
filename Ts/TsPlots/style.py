"""Shared styling configuration for the TsPlots package.

This module is the single source of truth for typography, colour palette,
marker/line-style cycles, and the small cosmetic helpers shared by
:mod:`TsPlots.ts_plot` and :mod:`TsPlots.sc_plot`. Importing it configures
matplotlib fonts so Latin text uses Times New Roman and Chinese text uses
FangSong.

Contents
--------
Constants
    ``LATIN_FONT``, ``CHINESE_FONT_CANDIDATES``, ``HEITI_FONT_CANDIDATES``,
    ``DEFAULT_PALETTE``,
    ``DEFAULT_LINESTYLES``, ``DEFAULT_MARKERS`` plus cosmetic size constants
    (figure size, font sizes, unit colour).
Functions
    ``apply_fonts``, ``style_axes``, ``draw_shade``, ``draw_vlines``,
    ``draw_hlines``, ``draw_legend``, ``draw_unit_label``,
    ``draw_note_and_bottom_title``.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

# --- Fonts -----------------------------------------------------------------
# Preferred fonts: Times New Roman for Latin glyphs, FangSong (GB2312) for CJK.
# matplotlib (>=3.6) performs per-glyph fallback through the family list, so
# Latin characters render in Times New Roman and Chinese falls back to FangSong.
LATIN_FONT = "Times New Roman"
# The genuine "仿宋_GB2312" (FSGB2312) is often not installed; we list it first
# and fall back to the standard Windows FangSong (simfang.ttf) if absent.
CHINESE_FONT_CANDIDATES = ["FangSong_GB2312", "FZFangSong-Z02", "FangSong"]
# For captions and titles, use SimHei (黑体) instead of FangSong
HEITI_FONT_CANDIDATES = ["SimHei", "Microsoft YaHei"]


def apply_fonts(latin=LATIN_FONT, chinese_candidates=CHINESE_FONT_CANDIDATES):
    """Configure matplotlib so Latin text uses Times New Roman and Chinese
    text uses FangSong (GB2312 if available).

    Parameters
    ----------
    latin : str
        Font family used for Latin glyphs. Defaults to ``"Times New Roman"``.
    chinese_candidates : sequence of str
        Candidate CJK font family names, tried in order; the first one that is
        installed is used, otherwise the last entry is used as a fallback.

    Returns
    -------
    str
        The Chinese font family name that was actually selected.
    """
    available = {f.name for f in font_manager.fontManager.ttflist}
    chinese = next(
        (name for name in chinese_candidates if name in available),
        chinese_candidates[-1],
    )
    # Family fallback list: Latin first, CJK second.
    plt.rcParams["font.family"] = [latin, chinese]
    plt.rcParams["axes.unicode_minus"] = False
    # Math text in a matching serif style.
    plt.rcParams["mathtext.fontset"] = "stix"
    return chinese


# --- Lazy font initialisation ------------------------------------------------
# Fonts are not loaded at import time — _ensure_fonts() is called at the top of
# every public plotting function. This avoids front-loading the font-scan cost
# (scanning ~1800 TTF files on Windows) when all the user wants is a constant.
_fonts_initialized = False
SELECTED_CHINESE_FONT = "FangSong"  # placeholder; replaced after first _ensure_fonts()


def _ensure_fonts():
    """Lazy-load fonts on first call; no-op afterwards.

    Call this at the top of every public plotting function that creates or
    styles a figure (plot_series, plot_scatter, plot_acf, plot_pacf).
    """
    global _fonts_initialized, SELECTED_CHINESE_FONT
    if not _fonts_initialized:
        SELECTED_CHINESE_FONT = apply_fonts(LATIN_FONT, CHINESE_FONT_CANDIDATES)
        _fonts_initialized = True


# --- Palette and cycles ----------------------------------------------------
# Colorblind-friendly palette (Okabe-Ito inspired)
DEFAULT_PALETTE = [
    "#1f4e79",  # deep blue
    "#888888",  # medium gray
    "#2e7d32",  # green
    "#8e44ad",  # purple
    "#c0392b",  # red
    "#16a085",  # teal
    "#d4ac0d",  # gold
    "#566573",  # slate gray
]

# Distinct line styles so series remain distinguishable in grayscale / B&W print
DEFAULT_LINESTYLES = [
    "-",  # solid
    "--",  # dashed
    "-.",  # dash-dot
    ":",  # dotted
    (0, (3, 1, 1, 1)),  # dash-dot-dot
    (0, (5, 1)),  # long dash
    (0, (1, 1)),  # dense dots
    (0, (3, 1, 1, 1, 1, 1)),  # dash-dot-dot-dot
]

# Distinct marker shapes to reinforce B&W distinction
DEFAULT_MARKERS = ["o", "o", "^", "D", "v", "P", "X", "*"]

# --- Cosmetic size constants ----------------------------------------------
FIGSIZE = (10, 5.5)
TITLE_FONTSIZE = 14
AXIS_LABEL_FONTSIZE = 15
TICK_LABELSIZE = 14
LEGEND_FONTSIZE = 14
NOTE_FONTSIZE = 9
# (removed UNIT_FONTSIZE and UNIT_COLOR — unused)


def _resolve_colors(colors, series_count):
    """Return one color per series or reject an ambiguous override."""
    if colors is None:
        return None
    if isinstance(colors, str):
        raise TypeError("colors must be a sequence of color strings, not a string")
    resolved = list(colors)
    if len(resolved) != series_count:
        raise ValueError(
            f"colors has {len(resolved)} entries but there are {series_count} series"
        )
    return resolved


def _validate_positive_step(name, value, *, integer=False):
    """Validate an optional positive tick step."""
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be a positive number")
    if integer and not isinstance(value, (int, np.integer)):
        raise TypeError(f"{name} must be a positive integer")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise TypeError(f"{name} must be a positive number") from error
    if not np.isfinite(numeric) or numeric <= 0:
        raise ValueError(f"{name} must be positive")
    return int(value) if integer else numeric


def style_axes(ax, *, grid=False, tick_labelsize=TICK_LABELSIZE):
    """Apply the shared axes cosmetics: hide the top and right spines, set the
    tick label size, and optionally draw a dashed grid on both axes.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Axes to style.
    grid : bool
        Whether to show a dashed grid on both axes. Defaults to ``False``.
    tick_labelsize : float
        Font size of the tick labels. Defaults to ``14``.
    """
    if grid:
        ax.grid(axis="both", alpha=0.4, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", labelsize=tick_labelsize)


def draw_shade(ax, shade, color, alpha):
    """Draw one or more shaded vertical regions behind the data.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    shade : tuple or list of tuple
        A single ``(xmin, xmax)`` interval or a list of such intervals.
    color : str
        Fill colour of the shaded regions.
    alpha : float
        Opacity of the shaded regions (0–1).
    """
    if shade is None:
        return
    regions = [shade] if isinstance(shade, tuple) else list(shade)
    for xmin, xmax in regions:
        ax.axvspan(
            xmin,
            xmax,
            color=color,
            alpha=alpha,
            linewidth=0,
            zorder=0,
        )


def draw_vlines(ax, vlines, color, linestyle, linewidth):
    """Draw one or more vertical reference lines.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    vlines : float or list of float
        One or more x-axis positions at which to draw a vertical line.
    color : str
        Colour of the vertical lines.
    linestyle : str
        Line style of the vertical lines.
    linewidth : float
        Width of the vertical lines.
    """
    if vlines is None:
        return
    positions = [vlines] if np.isscalar(vlines) else list(vlines)
    for xpos in positions:
        ax.axvline(
            xpos,
            color=color,
            linestyle=linestyle,
            linewidth=linewidth,
            zorder=1,
        )


def draw_hlines(ax, hlines, color, linestyle, linewidth):
    """Draw one or more horizontal reference lines.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    hlines : float or list of float
        One or more y-axis positions at which to draw a horizontal line.
    color : str
        Colour of the horizontal lines.
    linestyle : str
        Line style of the horizontal lines.
    linewidth : float
        Width of the horizontal lines.
    """
    if hlines is None:
        return
    positions = [hlines] if np.isscalar(hlines) else list(hlines)
    for ypos in positions:
        ax.axhline(
            ypos,
            color=color,
            linestyle=linestyle,
            linewidth=linewidth,
            zorder=1,
        )


def draw_legend(
    ax,
    *,
    show_legend=True,
    legend_labels=None,
    legend_loc="best",
    legend_bbox=None,
    fontsize=LEGEND_FONTSIZE,
):
    """Draw a frameless legend, optionally overriding the entry text.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    show_legend : bool
        Whether to display the legend at all. Defaults to ``True``.
    legend_labels : sequence of str, optional
        Override the text of the legend entries. Must match the number of
        plotted handles.
    legend_loc : str
        Legend location passed to ``ax.legend(loc=...)``.
    legend_bbox : tuple, optional
        ``bbox_to_anchor`` for the legend.
    fontsize : float
        Legend font size. Defaults to ``14``.
    """
    if not show_legend:
        return
    handles, auto_labels = ax.get_legend_handles_labels()
    final_labels = legend_labels if legend_labels is not None else auto_labels
    if legend_labels is not None and len(legend_labels) != len(handles):
        raise ValueError(
            f"legend_labels has {len(legend_labels)} entries but there are "
            f"{len(handles)} series."
        )
    ax.legend(
        handles,
        final_labels,
        frameon=False,
        fontsize=fontsize,
        loc=legend_loc,
        bbox_to_anchor=legend_bbox,
    )


def draw_unit_label(ax, unit, *, axis="y"):
    """Place a Chinese unit label ``（单位：XX）`` next to an axis.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    unit : str or None
        The unit text. If ``None``, nothing is drawn.
    axis : str
        ``"y"`` (default) appends the label to the existing y-axis label text.
        ``"x"`` appends it to the x-axis label text.
    """
    if unit is None:
        return
    text = f"（单位：{unit}）"
    if axis == "y":
        current = ax.get_ylabel()
        ax.set_ylabel(f"{current}{text}" if current else text)
    elif axis == "x":
        current = ax.get_xlabel()
        ax.set_xlabel(f"{current}{text}" if current else text)
    else:
        raise ValueError(f"axis={axis!r} is not valid. Choose 'x' or 'y'.")


def draw_note_and_bottom_title(
    fig,
    *,
    note=None,
    title=None,
    title_position="top",
):
    """Place a bottom title and/or a lower-left note in figure coordinates.

    This must be called after ``fig.tight_layout()`` because it reserves extra
    bottom margin and positions text relative to the figure.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
    note : str, optional
        Free-text note placed at the lower-left of the figure. When a bottom
        title is also present the note is positioned below it; otherwise it
        sits just below the x-axis area.
    title : str, optional
        Title text. Only used here when ``title_position == "bottom"``.
    title_position : str
        ``"top"`` (default) or ``"bottom"``. Only ``"bottom"`` draws a title.
    """
    bottom_title = title is not None and title_position == "bottom"
    if not (bottom_title or note is not None):
        return

    # Reserve just enough extra space below the subplot for the caption/note.
    # The free band from 0 → extra (figure coordinates) sits below the x-axis
    # label area; we position text near the *top* of that band so it appears
    # close to the axis rather than at the very bottom of the figure.
    has_both = bottom_title and note is not None
    extra = 0.06 + (0.05 if has_both else 0.0)
    fig.subplots_adjust(bottom=fig.subplotpars.bottom + extra)

    if bottom_title:
        # Place directly below the x-axis label (centered)
        # Positioned closer to the x-axis than the note
        y_title = extra - 0.008
        fig.text(
            0.5,
            y_title,
            title,
            fontsize=TITLE_FONTSIZE,
            color="#000000",
            ha="center",
            va="top",
            family=HEITI_FONT_CANDIDATES,
        )

    if note is not None:
        # When a bottom title is present, the note sits below it.
        # When there is no bottom title, the note appears just below the xlabel.
        y_note = (extra - 0.025 - 0.04) if bottom_title else (extra - 0.025)
        fig.text(
            0.04,
            y_note,
            note,
            fontsize=NOTE_FONTSIZE,
            color="#000000",
            ha="left",
            va="top",
            family=HEITI_FONT_CANDIDATES,
        )


class _FigureContext:
    """Shared figure/axes manager for plot_series and plot_scatter.

    Encapsulates the common boilerplate: figure creation, title handling,
    axis labels, legend drawing, unit labels, tight_layout, and note rendering.
    """

    def __init__(self, ax=None, figsize=None):
        if figsize is None:
            figsize = FIGSIZE
        if ax is None:
            self.fig, self.ax = plt.subplots(figsize=figsize)
        else:
            self.ax = ax
            self.fig = ax.figure

    def finalize(
        self,
        *,
        title=None,
        xtitle=None,
        ytitle=None,
        title_position="top",
        title_loc="center",
        title_pad=12,
        note=None,
        grid=False,
        show_legend=True,
        legend_labels=None,
        legend_loc="best",
        legend_bbox=None,
        labels=None,
        unit=None,
        x_unit=None,
        y_unit=None,
    ):
        """Apply common post-plot styling."""
        _ensure_fonts()

        if title and title_position == "top":
            self.ax.set_title(
                title,
                fontsize=TITLE_FONTSIZE,
                fontweight="bold",
                loc=title_loc,
                pad=title_pad,
            )

        if xtitle:
            self.ax.set_xlabel(xtitle, fontsize=AXIS_LABEL_FONTSIZE)
        if ytitle:
            self.ax.set_ylabel(ytitle, fontsize=AXIS_LABEL_FONTSIZE)

        style_axes(self.ax, grid=grid, tick_labelsize=TICK_LABELSIZE)

        if show_legend and labels:
            draw_legend(
                self.ax,
                show_legend=show_legend,
                legend_labels=legend_labels,
                legend_loc=legend_loc,
                legend_bbox=legend_bbox,
            )

        if unit is not None:
            draw_unit_label(self.ax, unit, axis="y")
        if x_unit is not None:
            draw_unit_label(self.ax, x_unit, axis="x")
        if y_unit is not None:
            draw_unit_label(self.ax, y_unit, axis="y")

        self.fig.tight_layout(pad=1.5)

        if note or (title and title_position == "bottom"):
            draw_note_and_bottom_title(
                self.fig,
                note=note,
                title=title,
                title_position=title_position,
            )
