"""Platform-aware font selection shared by Matplotlib and Plotly charts.

The application is developed on Windows, while Streamlit Community Cloud
runs on Linux. Windows-only names such as Microsoft YaHei and SimHei are not
available in the cloud even when a CJK font package is installed, so chart
code must resolve a font that actually exists on the current host.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

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


def _font_is_available(family: str) -> bool:
    """Return whether Matplotlib can resolve a family without fallback."""

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


def plotly_font_family() -> str:
    """Return a CSS font-family value using the resolved CJK family."""

    return f"{resolve_cjk_font()}, sans-serif"


__all__ = [
    "CJK_FONT_CANDIDATES",
    "matplotlib_font_family",
    "plotly_font_family",
    "resolve_cjk_font",
]
