from __future__ import annotations

import matplotlib.pyplot as plt

from htfa.ui_shared.chart_legend import MATPLOTLIB_CJK_FONTS, _apply_cjk_fonts


def test_pyplot_renderer_selects_cjk_fallbacks_for_all_text() -> None:
    figure, axis = plt.subplots()
    title = axis.set_title("阿联酋高频数据")

    _apply_cjk_fonts(figure)

    assert "Noto Sans CJK SC" in MATPLOTLIB_CJK_FONTS
    assert any("Noto Sans CJK" in family for family in title.get_fontfamily())
    assert plt.rcParams["axes.unicode_minus"] is False
    plt.close(figure)