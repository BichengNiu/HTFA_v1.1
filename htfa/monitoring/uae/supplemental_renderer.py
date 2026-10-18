"""在现有板块内追加图表，以及独立的物价板块。"""

from typing import Any

from htfa.monitoring.uae.database import PublishedUAEData
from htfa.monitoring.uae.downloads import render_chart_download
from htfa.monitoring.uae.metrics import (
    _source_note_from_metadata,
    change_in_points,
    latest_month_value,
    month_and_year_delta_text,
    points_delta_text,
    render_metric_cards,
    source_text_from_metadata,
)
from htfa.monitoring.uae.supplemental_charts import build_supplemental_figure
from htfa.monitoring.uae.supplemental_data import ChartSpec, PRICE_CHARTS, load_chart_data
from htfa.ui_shared.chart_legend import render_pyplot_figure


def _load_charts(
    st_obj: Any, content: PublishedUAEData, specs: tuple[ChartSpec, ...],
) -> list:
    """独立加载各图数据，供指标卡和图表使用同一份展示序列。"""
    loaded = []
    for spec in specs:
        try:
            values, metadata, units = load_chart_data(content, spec)
            loaded.append((spec, values, metadata, units))
        except (KeyError, TypeError, ValueError, FileNotFoundError) as exc:
            st_obj.warning(f"{spec.title}未加载：{exc}")
    return loaded


def _render_loaded_charts(st_obj: Any, loaded: list) -> dict[str, str]:
    """渲染双列图表与下载按钮，单图错误独立提示。"""
    rendered = {}
    for offset in range(0, len(loaded), 2):
        cells = st_obj.columns(2, gap="small")
        for cell, (spec, values, metadata, units) in zip(cells, loaded[offset:offset + 2]):
            try:
                figure = build_supplemental_figure(
                    values, spec=spec, units=units,
                    source_text=source_text_from_metadata(metadata),
                )
                render_pyplot_figure(cell, figure, bbox_inches=None, place_legend_bottom=False)
                render_chart_download(
                    cell, values, title=spec.title,
                    key=f"analysis.uae.supplemental.{spec.key}.download",
                )
                as_of = values.index.max().strftime("%Y-%m-%d")
                rendered[spec.key] = as_of
            except (KeyError, TypeError, ValueError) as exc:
                cell.warning(f"{spec.title}未加载：{exc}")
    return rendered


def render_supplemental_charts(
    st_obj: Any, content: PublishedUAEData, specs: tuple[ChartSpec, ...],
) -> dict[str, str]:
    """追加双列图表，不新增小节；缺失数据或单图错误独立提示。"""
    loaded = _load_charts(st_obj, content, specs)
    return _render_loaded_charts(st_obj, loaded)


def _render_price_metrics(st_obj: Any, loaded: list) -> None:
    """物价指标卡：钢材报价及涨跌、CPI 同比及百分点变化。"""
    cards = []
    for spec, values, metadata, units in loaded:
        for label in values:
            series = values[label]
            value, as_of = latest_month_value(series)
            if spec.key == "cpi":
                metric_label = label
                value_text = None if value is None else f"{value:.2f}%"
                delta = points_delta_text(change_in_points(series))
            else:
                metric_label = f"{label}报价"
                number = (
                    None if value is None
                    else f"{value:,.2f}".rstrip("0").rstrip(".")
                )
                value_text = None if number is None else f"{number} {units[label]}"
                delta = month_and_year_delta_text(series)
            cards.append((
                metric_label,
                value_text,
                delta,
                _source_note_from_metadata(metadata, label, as_of),
            ))
    if cards:
        render_metric_cards(st_obj, cards)


def render_prices_section(st_obj: Any, payload: tuple[Any, str]) -> dict[str, Any]:
    """渲染物价 Part 的最新完整月指标卡、钢材报价与 CPI 图。"""
    st_obj.divider()
    st_obj.subheader("物价")
    loaded = _load_charts(st_obj, payload[0], PRICE_CHARTS)
    _render_price_metrics(st_obj, loaded)
    rendered = _render_loaded_charts(st_obj, loaded)
    return {"status": "success" if rendered else "no_data", "charts": rendered}
