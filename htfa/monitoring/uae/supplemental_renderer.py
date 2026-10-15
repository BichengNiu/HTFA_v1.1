"""在现有板块内追加图表，以及独立的物价板块。"""

from typing import Any

from htfa.monitoring.uae.downloads import render_chart_download
from htfa.monitoring.uae.metrics import source_text_from_metadata
from htfa.monitoring.uae.supplemental_charts import build_supplemental_figure
from htfa.monitoring.uae.supplemental_data import ChartSpec, PRICE_CHARTS, load_chart_data
from htfa.ui_shared.chart_legend import render_pyplot_figure


def render_supplemental_charts(
    st_obj: Any, content: Any, file_name: str, specs: tuple[ChartSpec, ...],
) -> dict[str, str]:
    """追加双列图表，不新增小节；缺失数据或单图错误独立提示。"""
    loaded = []
    for spec in specs:
        try:
            values, metadata, units = load_chart_data(content, file_name, spec)
            loaded.append((spec, values, metadata, units))
        except (KeyError, TypeError, ValueError, FileNotFoundError) as exc:
            st_obj.warning(f"{spec.title}未加载：{exc}")
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
                cell.caption(f"数据截至 {as_of}")
                rendered[spec.key] = as_of
            except (KeyError, TypeError, ValueError) as exc:
                cell.warning(f"{spec.title}未加载：{exc}")
    return rendered


def render_prices_section(st_obj: Any, payload: tuple[Any, str]) -> dict[str, Any]:
    """新增物价 Part，仅展示钢材报价图。"""
    st_obj.divider()
    st_obj.subheader("物价")
    rendered = render_supplemental_charts(st_obj, *payload, PRICE_CHARTS)
    st_obj.caption("钢材报价为CFR/CPT阿联酋进口报价区间中值，用于观察投入成本，不代表CPI。")
    return {"status": "success" if rendered else "no_data", "charts": rendered}
