"""PNG chart presentation using the existing Ts rendering contract."""

from __future__ import annotations

import io
import threading
from contextlib import contextmanager

from htfa.monitoring.energy_supply.processing import port_charts, vessel_charts

from .cache_policy import snapshot_cache

_PLOT_LOCK = threading.RLock()


@contextmanager
def _preserve_ts_fonts(style):
    names = ("LATIN_FONT", "SELECTED_CHINESE_FONT", "SELECTED_HEITI_FONT")
    saved = {name: getattr(style, name) for name in names}
    try:
        yield
    finally:
        for name, value in saved.items():
            setattr(style, name, value)


def render_chart_images(
    aggregated: list[dict],
    labels: dict[str, str],
    aggregation="日度",
    ytitle="艘次",
    point_markers=False,
    date_only=False,
) -> tuple[bytes, ...]:
    """Shared figure layout for port activity and observed vessel counts."""
    if not aggregated:
        return ()
    # Lazy import: opening the map never imports matplotlib or scans its fonts.
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd
    from matplotlib.dates import AutoDateLocator, ConciseDateFormatter, DateFormatter
    from matplotlib.ticker import MaxNLocator
    from Ts.TsPlots import plot_series, style
    from Ts.TsPlots.style import _ensure_fonts, apply_fonts

    frame = pd.DataFrame(aggregated).set_index("date")[list(labels)].astype(float)
    frame.index = pd.to_datetime(frame.index)
    frame = frame.rename(columns=labels)
    images = []
    span = (frame.index[-1] - frame.index[0]).days
    annual = aggregation == "年度"
    year_ruler = not annual and not date_only and 60 <= span <= 550
    if annual:
        frame.index = frame.index.strftime("%Y")
    # Matplotlib's font state is global; serialize rendering across sessions.
    with _PLOT_LOCK, plt.rc_context(), _preserve_ts_fonts(style):
        _ensure_fonts()
        chinese_font = apply_fonts(
            latin="DejaVu Sans",
            chinese_candidates=[
                "Microsoft YaHei",
                "SimHei",
                "Noto Sans CJK SC",
                "Noto Sans CJK JP",
            ],
        )
        style.LATIN_FONT = "DejaVu Sans"
        style.SELECTED_CHINESE_FONT = chinese_font
        style.SELECTED_HEITI_FONT = chinese_font
        for label in labels.values():
            fig = None
            try:
                fig, ax = plot_series(
                    frame[[label]],
                    facet=False,
                    auto_dual_y=False,
                    figsize=(6.2, 4.6),
                    xtitle="",
                    ytitle=ytitle,
                    ytitle_position="side",
                    ymin=0,
                    grid=False,
                    year_ruler=year_ruler,
                    monthly_ticks=span <= 100,
                    linewidth=1.5,
                    markersize=5
                    if aggregation in ("周度", "月度")
                    else 4
                    if (point_markers or len(frame) == 1) and not annual
                    else 0,
                    marker_edge_width=1,
                    bar_series=[label] if annual else None,
                    bar_face_color=style.GRAY if annual else None,
                    bar_edge_color=style.GRAY if annual else None,
                    show_legend=False,
                    max_ticks=6,
                    note=None,
                )
                if aggregation in ("周度", "月度"):
                    for line in ax.lines:
                        line.set_markerfacecolor("white")
                if annual:
                    ax.set_xlabel(
                        ""
                        if date_only
                        else f"{aggregated[0]['period_start']:%Y-%m-%d}—{aggregated[-1]['period_end']:%Y-%m-%d}"
                    )
                elif date_only:
                    # Sampled days can be sparse. Never let the auto locator
                    # turn these UTC calendar dates into misleading hour ticks.
                    observed_dates = frame.index[frame[label].notna()]
                    tick_dates = observed_dates if len(observed_dates) else frame.index
                    gap = max(1, (span + 3) // 4)
                    ticks = [tick_dates[0]]
                    for stamp in tick_dates[1:]:
                        if (stamp - ticks[-1]).days >= gap:
                            ticks.append(stamp)
                    if ticks[-1] != tick_dates[-1]:
                        if len(ticks) > 1 and (tick_dates[-1] - ticks[-1]).days < gap:
                            ticks.pop()
                        ticks.append(tick_dates[-1])
                    ax.set_xticks(ticks)
                    ax.xaxis.set_major_formatter(DateFormatter("%Y-%m-%d"))
                    ax.xaxis.get_offset_text().set_visible(False)
                    ax.tick_params(axis="x", rotation=25)
                    ax.set_xlabel("")
                    if len(frame) == 1:
                        point = frame.index[0]
                        ax.set_xlim(
                            point - pd.Timedelta(days=1), point + pd.Timedelta(days=1)
                        )
                elif len(frame) == 1:
                    point = frame.index[0]
                    ax.set_xlim(
                        point - pd.Timedelta(days=1), point + pd.Timedelta(days=1)
                    )
                    ax.set_xticks([point])
                    ax.xaxis.set_major_formatter(
                        DateFormatter("%Y-%m" if aggregation == "月度" else "%Y-%m-%d")
                    )
                elif not year_ruler:
                    if span > 550:
                        first_year, last_year = (
                            frame.index[0].year,
                            frame.index[-1].year,
                        )
                        step = max(1, (last_year - first_year + 4) // 5)
                        years = list(range(first_year, last_year + 1, step))
                        if years[-1] != last_year:
                            years.append(last_year)
                        ax.set_xticks(
                            [pd.Timestamp(year=year, month=1, day=1) for year in years]
                        )
                        ax.xaxis.set_major_formatter(DateFormatter("%Y"))
                    else:
                        locator = AutoDateLocator(minticks=2, maxticks=3)
                        ax.xaxis.set_major_locator(locator)
                        ax.xaxis.set_major_formatter(ConciseDateFormatter(locator))
                    ax.tick_params(axis="x", rotation=0)
                ax.yaxis.set_major_locator(MaxNLocator(nbins=4, integer=True))
                # Keep chart labels readable and use the installed CJK family.
                from matplotlib.text import Text

                for text in fig.findobj(Text):
                    text.set_fontfamily([chinese_font])
                    text.set_fontsize(16)
                if date_only and not annual:
                    ticks = ax.get_xticklabels()
                    for tick in ticks:
                        tick.set_fontsize(14)
                    if len(ticks) > 1:
                        ticks[0].set_ha("left")
                        ticks[-1].set_ha("right")
                ax.set_title(label, fontsize=18, fontfamily=[chinese_font], pad=12)
                # Ts lays out its template before this application font pass.
                # Reserve room again for the readable type and the year ruler.
                fig.subplots_adjust(
                    left=0.21 if annual else 0.16,
                    right=0.97,
                    top=0.86,
                    bottom=0.30 if year_ruler or date_only else 0.17,
                )
                if year_ruler:
                    # Measure the final fonts, including the year label's white
                    # background, before separating both rows. Move the ruler
                    # and its labels together; leave the vendored Ts unchanged.
                    from matplotlib.transforms import ScaledTranslation

                    fig.canvas.draw()
                    renderer = fig.canvas.get_renderer()
                    years = [
                        text
                        for text in ax.texts
                        if text.get_text().strip().removesuffix("年").isdigit()
                        and text.get_text().strip().endswith("年")
                    ]
                    months = [
                        text
                        for text in ax.get_xticklabels()
                        if text.get_visible() and text.get_text()
                    ]
                    if years and months:
                        year_top = max(
                            text.get_bbox_patch().get_window_extent(renderer).y1
                            for text in years
                        )
                        month_bottom = min(
                            text.get_window_extent(renderer).y0 for text in months
                        )
                        shift_pixels = max(
                            0, year_top - month_bottom + 8 * fig.dpi / 72
                        )
                        shift = ScaledTranslation(
                            0, -shift_pixels / fig.dpi, fig.dpi_scale_trans
                        )
                        for text in years:
                            text.set_transform(text.get_transform() + shift)
                        for collection in ax.collections:
                            if (
                                not collection.get_clip_on()
                                and collection.get_transform()
                                == ax.get_xaxis_transform()
                            ):
                                collection.set_transform(
                                    collection.get_transform() + shift
                                )
                buffer = io.BytesIO()
                fig.savefig(buffer, format="png", dpi=140, facecolor="white")
                images.append(buffer.getvalue())
            finally:
                if fig is not None:
                    plt.close(fig)
    return tuple(images)


@snapshot_cache(max_entries=12)
def port_chart_images(rows, first_day, aggregation="日度"):
    return render_chart_images(
        port_charts.aggregate_rows(rows, first_day, aggregation),
        port_charts.series_labels(aggregation),
        aggregation,
    )


@snapshot_cache(max_entries=12)
def vessel_chart_images(rows, aggregation):
    records = [dict(zip(vessel_charts.CHART_FIELDS, row)) for row in rows]
    return render_chart_images(
        records,
        vessel_charts.series_labels(),
        aggregation,
        ytitle="艘",
        point_markers=True,
        date_only=True,
    )
