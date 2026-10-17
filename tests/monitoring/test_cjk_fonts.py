from __future__ import annotations

import matplotlib.pyplot as plt

from htfa.ui_shared.chart_legend import _apply_cjk_fonts
from htfa.ui_shared.fonts import configure_matplotlib_fonts, matplotlib_font_family


def test_pyplot_renderer_selects_available_cjk_fonts_without_findfont_warnings(caplog) -> None:
    configure_matplotlib_fonts()
    figure, axis = plt.subplots()
    title = axis.set_title("阿联酋高频数据")

    _apply_cjk_fonts(figure)
    with caplog.at_level("WARNING", logger="matplotlib.font_manager"):
        figure.canvas.draw()

    assert title.get_fontfamily() == matplotlib_font_family()
    assert not any("Font family" in record.message for record in caplog.records)
    assert plt.rcParams["axes.unicode_minus"] is False
    plt.close(figure)
