"""Platform-aware font selection shared by Matplotlib and Plotly charts.

The application is developed on Windows, while Streamlit Community Cloud
runs on Linux. Windows-only names such as Microsoft YaHei and SimHei are not
available in the cloud even when a CJK font package is installed, so chart
code must resolve a font that actually exists on the current host.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import subprocess

from matplotlib import font_manager


# Put Linux cloud fonts first and retain the Windows names for local use.
CJK_FONT_CANDIDATES = (
    "Noto Sans CJK SC",
    "Noto Sans CJK TC",
    "Noto Sans CJK JP",
    "Noto Sans CJK HK",
    "Source Han Sans CN",
    "WenQuanYi Zen Hei",
    "Microsoft YaHei",
    "SimHei",
    "Arial Unicode MS",
    # Last-resort Latin fallback. Streamlit deployments install Noto CJK via
    # packages.txt, so this is only used on hosts with no CJK font at all.
    "DejaVu Sans",
)


@lru_cache(maxsize=1)
def _register_fontconfig_cjk_fonts() -> None:
    """Register CJK fonts installed as TrueType collections.

    Debian's fonts-noto-cjk package commonly installs .ttc files. Matplotlib's
    default font scan filters those files out, while fontconfig can still find
    them. Register the fontconfig paths explicitly before resolving a family.
    """

    try:
        result = subprocess.run(
            ["fc-list", ":lang=zh", "file"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return

    paths = {
        line.split(":", 1)[0].strip()
        for line in result.stdout.splitlines()
        if line.strip()
    }
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            continue
        try:
            font_manager.fontManager.addfont(path)
        except (OSError, RuntimeError, ValueError):
            # Some fontconfig entries point to collections that this
            # Matplotlib build cannot load; other entries may still work.
            continue


def _font_is_available(family: str) -> bool:
    """Return whether Matplotlib can resolve a family without fallback."""

    _register_fontconfig_cjk_fonts()
    try:
        path = font_manager.findfont(family, fallback_to_default=False)
    except (OSError, ValueError):
        return False
    return bool(path) and Path(path).exists()


@lru_cache(maxsize=1)
def resolve_cjk_font() -> str:
    """Return the first installed CJK-capable family for this host."""

    for family in CJK_FONT_CANDIDATES:
        if _font_is_available(family):
            return family
    # This branch is defensive: Matplotlib always ships with DejaVu Sans.
    return "DejaVu Sans"


def matplotlib_font_family() -> list[str]:
    """Return a concrete Matplotlib family list for the current host."""

    return [resolve_cjk_font()]


def configure_matplotlib_fonts() -> str:
    """Configure Matplotlib and TsPlots with the resolved CJK family.

    TsPlots exposes its CJK candidates as module constants. Updating those
    candidates before the first chart is created keeps the shared plotting
    package and HTFA's post-processing on the same cloud-compatible font.
    """

    import matplotlib

    selected = resolve_cjk_font()
    latin = "Times New Roman" if _font_is_available("Times New Roman") else "DejaVu Sans"
    matplotlib.rcParams["font.family"] = [latin, selected]
    matplotlib.rcParams["font.sans-serif"] = [selected]
    matplotlib.rcParams["axes.unicode_minus"] = False

    try:
        from Ts.TsPlots import style as ts_style
    except ImportError:
        return selected

    candidates = [selected, *CJK_FONT_CANDIDATES]
    # Mutate the original list in place: TsPlots.apply_fonts binds its
    # candidate list as a default argument when the module is imported.
    original_candidates = getattr(ts_style, "CHINESE_FONT_CANDIDATES", None)
    if isinstance(original_candidates, list):
        original_candidates[:] = candidates
        candidates = original_candidates
    else:
        ts_style.CHINESE_FONT_CANDIDATES = candidates
    ts_style.HEITI_FONT_CANDIDATES = candidates
    ts_style.LATIN_FONT = latin
    ts_style.SELECTED_CHINESE_FONT = selected
    ts_style.SELECTED_HEITI_FONT = selected
    defaults = getattr(ts_style.apply_fonts, "__defaults__", None)
    if defaults and len(defaults) >= 2:
        ts_style.apply_fonts.__defaults__ = (latin, candidates, *defaults[2:])
    ts_style._fonts_initialized = False
    return selected


def plotly_font_family() -> str:
    """Return a CSS font-family value using the resolved CJK family."""

    return f"{resolve_cjk_font()}, sans-serif"


__all__ = [
    "CJK_FONT_CANDIDATES",
    "configure_matplotlib_fonts",
    "matplotlib_font_family",
    "plotly_font_family",
    "resolve_cjk_font",
]
