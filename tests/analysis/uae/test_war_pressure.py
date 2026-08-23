"""战争压力数据读取与图表测试。"""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from dashboard.analysis.uae.oil.charts import (
    build_war_pressure_index_figure,
    build_war_pressure_raw_figure,
)
from dashboard.analysis.uae.oil.war_pressure import (
    BALLISTIC_LABEL,
    CRUISE_LABEL,
    PRESSURE_LABEL,
    UAV_LABEL,
    WarPressureData,
    load_war_pressure_data,
)


WAM_INDICATOR_NAMES = [
    "阿联酋军事打击:弹道导弹数量(Ballistic Missiles)",
    "阿联酋军事打击:巡航导弹数量(Cruise Missiles)",
    "阿联酋军事打击:无人机数量(UAVs)",
    "阿联酋战争压力指标(强权重log1p之和,0-100归一化)",
]


def _wam_workbook_bytes() -> bytes:
    dates = pd.to_datetime(["2026-02-28", "2026-03-31", "2026-04-30"])
    ballistic = [0, 12, 3]
    cruise = [0, 1, 2]
    uavs = [0, 17, 4]
    pressure = [0.0, 100.0, 30.0]
    rows = [
        ["WAM / UAE official source registry", None, None, None, None],
        ["指标名称", *WAM_INDICATOR_NAMES],
        ["频率", "月", "月", "月", "月"],
        ["单位", "枚", "枚", "架", "指数"],
        ["来源", *(["WAM / UAE official source registry"] * 4)],
        ["更新时间", *([pd.Timestamp("2026-08-22")] * 4)],
    ]
    rows.extend(
        [date, b, c, u, p]
        for date, b, c, u, p in zip(dates, ballistic, cruise, uavs, pressure)
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(
            writer,
            sheet_name="月度_WAM",
            header=False,
            index=False,
        )
    return buffer.getvalue()


def _sample_values() -> pd.DataFrame:
    index = pd.to_datetime(["2026-02-28", "2026-03-31", "2026-04-30"])
    return pd.DataFrame(
        {
            BALLISTIC_LABEL: [0, 12, 3],
            CRUISE_LABEL: [0, 1, 2],
            UAV_LABEL: [0, 17, 4],
            PRESSURE_LABEL: [0.0, 10.0, 5.0],
        },
        index=index,
    )


def test_wam_loader_keeps_zero_counts_and_reads_metadata() -> None:
    data = load_war_pressure_data(_wam_workbook_bytes(), file_name="test.xlsx")

    assert data.values.columns.tolist() == [
        BALLISTIC_LABEL,
        CRUISE_LABEL,
        UAV_LABEL,
        PRESSURE_LABEL,
    ]
    assert data.values.loc["2026-02-28", BALLISTIC_LABEL] == 0
    assert data.values.loc["2026-03-31", UAV_LABEL] == 17
    assert data.values.loc["2026-03-31", PRESSURE_LABEL] == pytest.approx(100.0)
    assert data.values[PRESSURE_LABEL].between(0.0, 100.0).all()
    assert {item.source for item in data.metadata.values()} == {
        "WAM / UAE official source registry"
    }


def test_war_pressure_raw_chart_uses_three_series_on_one_left_axis() -> None:
    figure = build_war_pressure_raw_figure(
        _sample_values(),
        "WAM / UAE official source registry",
    )

    axis = figure.axes[0]
    assert axis.get_title() == "袭击手段"
    assert axis.get_ylabel() == "数量（枚/架）"
    assert len(axis.patches) == 9
    assert {
        text.get_text() for text in axis.get_legend().get_texts()
    } == {BALLISTIC_LABEL, CRUISE_LABEL, UAV_LABEL}
    assert len(axis.get_legend().get_texts()) == 3


def test_war_pressure_metrics_render_latest_month_four_cards() -> None:
    from dashboard.analysis.uae.oil import renderer

    st_obj = MagicMock()
    st_obj.columns.return_value = tuple(MagicMock() for _ in range(4))
    data = WarPressureData(
        values=_sample_values(),
        metadata={},
        source_name="test.xlsx",
    )

    renderer._render_war_pressure_metrics(st_obj, data)

    assert st_obj.metric.call_count == 4
    labels = [call.args[0] for call in st_obj.metric.call_args_list]
    assert labels == [
        "最新月弹道导弹",
        "最新月巡航导弹",
        "最新月无人机",
        "最新月战争压力指数",
    ]
    captions = [call.args[0] for call in st_obj.caption.call_args_list]
    assert len(captions) == 3
    assert all(text.startswith("战争以来累计：") for text in captions)


def test_war_pressure_index_chart_is_a_single_index_series() -> None:
    figure = build_war_pressure_index_figure(
        _sample_values(),
        "WAM / UAE official source registry",
    )

    axis = figure.axes[0]
    assert axis.get_title() == "战争压力指数"
    assert axis.get_ylabel() == "指数"
    assert [
        line.get_label()
        for line in axis.get_lines()
        if not line.get_label().startswith("_")
    ] == [PRESSURE_LABEL]


def test_oil_panel_places_war_pressure_before_revenue(monkeypatch) -> None:
    from dashboard.analysis.uae.oil import renderer

    events: list[str] = []
    st_obj = type("StubStreamlit", (), {})()
    monkeypatch.setattr(renderer, "_source_payload", lambda: (b"workbook", "test.xlsx"))
    monkeypatch.setattr(
        renderer,
        "_load_oil_market_cached",
        lambda *args: SimpleNamespace(prices=pd.DataFrame(), production=pd.Series()),
    )
    monkeypatch.setattr(renderer, "_render_oil_metrics", lambda *args: None)
    monkeypatch.setattr(
        renderer,
        "load_war_pressure_data",
        lambda *args, **kwargs: WarPressureData(
            values=_sample_values(),
            metadata={},
            source_name="test.xlsx",
        ),
    )
    monkeypatch.setattr(
        renderer,
        "_render_war_pressure_section",
        lambda *args: events.append("war"),
    )
    monkeypatch.setattr(
        renderer,
        "estimate_monthly_oil_revenue",
        lambda *args: pd.DataFrame(),
    )
    monkeypatch.setattr(
        renderer,
        "_render_revenue_metrics",
        lambda *args: events.append("revenue_metrics"),
    )
    monkeypatch.setattr(
        renderer,
        "_render_charts",
        lambda *args: events.append("charts"),
    )
    monkeypatch.setattr(
        "dashboard.analysis.uae.government_finance.render_government_finance_section",
        lambda *args: {"status": "success"},
    )
    monkeypatch.setattr(
        "dashboard.analysis.uae.real_estate.render_real_estate_section",
        lambda *args: {"status": "success"},
    )
    monkeypatch.setattr(
        "dashboard.analysis.uae.transport.render_transport_section",
        lambda *args: {"status": "success"},
    )
    st_obj.spinner = lambda *args, **kwargs: _NullContext()
    st_obj.expander = lambda *args, **kwargs: _NullContext()
    st_obj.subheader = lambda *args, **kwargs: None
    st_obj.markdown = lambda *args, **kwargs: None
    st_obj.columns = lambda *args, **kwargs: tuple(MagicMock() for _ in range(4))
    st_obj.metric = lambda *args, **kwargs: None
    st_obj.caption = lambda *args, **kwargs: None

    result = renderer.render_oil_fiscal_panel(st_obj)

    assert result["status"] == "success"
    assert events[:2] == ["war", "revenue_metrics"]


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False
