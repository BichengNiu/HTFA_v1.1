"""Tests for the DLD Dubai real-estate monthly sales panel (期房/现房)."""

from io import BytesIO
from unittest.mock import MagicMock

import pandas as pd
import pytest

from htfa.monitoring.uae.real_estate import renderer
from htfa.monitoring.uae.real_estate.charts import (
    AMOUNT_LABEL,
    COUNT_LABEL,
    MARKET_CONFIG,
    PROPERTY_CONFIG,
    build_sales_figure,
)
from htfa.monitoring.uae.real_estate.data import (
    OFFPLAN_AMOUNT,
    OFFPLAN_COUNT,
    READY_AMOUNT,
    READY_COUNT,
    latest_complete_month,
    load_real_estate_data,
)

_OFFPLAN_RESIDENTIAL_COUNT = "迪拜:期房销售-住宅笔数"
_OFFPLAN_RESIDENTIAL_AMOUNT = "迪拜:期房销售-住宅金额(百万AED)"
_READY_RESIDENTIAL_COUNT = "迪拜:现房销售-住宅笔数"
_READY_RESIDENTIAL_AMOUNT = "迪拜:现房销售-住宅金额(百万AED)"
_OFFPLAN_COMMERCIAL_COUNT = "迪拜:期房销售-商业笔数"
_OFFPLAN_COMMERCIAL_AMOUNT = "迪拜:期房销售-商业金额(百万AED)"
_READY_COMMERCIAL_COUNT = "迪拜:现房销售-商业笔数"
_READY_COMMERCIAL_AMOUNT = "迪拜:现房销售-商业金额(百万AED)"

_INDICATOR_HEADERS = [
    _OFFPLAN_RESIDENTIAL_COUNT,
    _OFFPLAN_RESIDENTIAL_AMOUNT,
    _READY_RESIDENTIAL_COUNT,
    _READY_RESIDENTIAL_AMOUNT,
    _OFFPLAN_COMMERCIAL_COUNT,
    _OFFPLAN_COMMERCIAL_AMOUNT,
    _READY_COMMERCIAL_COUNT,
    _READY_COMMERCIAL_AMOUNT,
]


def _series_values(base: int = 0, *, zero_at: int | None = None) -> list[float]:
    values = [float(base + offset) for offset in range(13)]
    if zero_at is not None:
        values[zero_at] = 0.0
    return values


def _workbook_bytes() -> bytes:
    """构造含 13 个月（2024-05 至 2025-05，新→旧排列）销量的模拟工作簿。

    2025-01 期房商业金额置 0，验证 0 掩码与合计「降级为住宅金额」。
    """

    dates = pd.date_range("2024-05-31", periods=13, freq="ME")
    frame = pd.DataFrame(
        {
            "日期": dates[::-1],
            _OFFPLAN_RESIDENTIAL_COUNT: _series_values(100)[::-1],
            _OFFPLAN_RESIDENTIAL_AMOUNT: _series_values(1_000)[::-1],
            _READY_RESIDENTIAL_COUNT: _series_values(400)[::-1],
            _READY_RESIDENTIAL_AMOUNT: _series_values(4_000)[::-1],
            _OFFPLAN_COMMERCIAL_COUNT: _series_values(10)[::-1],
            _OFFPLAN_COMMERCIAL_AMOUNT: _series_values(100, zero_at=8)[::-1],
            _READY_COMMERCIAL_COUNT: _series_values(30)[::-1],
            _READY_COMMERCIAL_AMOUNT: _series_values(300)[::-1],
        }
    )
    metadata = pd.DataFrame(
        [
            ["Dubai Land Department", None, None, None, None, None, None, None, None],
            # 与 source_dld 写表器一致：A2 为「日期」而非「指标名称」标签
            ["日期", *_INDICATOR_HEADERS],
            ["频率", *("月",) * 8],
            ["单位", "笔", "百万AED", "笔", "百万AED", "笔", "百万AED", "笔", "百万AED"],
            ["来源", *("Dubai Land Department",) * 8],
            ["更新时间", *("2026-08-12",) * 8],
        ]
    )
    rows = pd.concat(
        [
            metadata,
            frame.rename(columns={"日期": 0}).set_axis(range(9), axis=1),
        ],
        ignore_index=True,
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        rows.to_excel(
            writer,
            sheet_name="月度_DLD",
            header=False,
            index=False,
        )
    return buffer.getvalue()


def test_loader_aggregates_offplan_and_ready_sales() -> None:
    data = load_real_estate_data(_workbook_bytes(), file_name="test.xlsx")

    assert data.values.columns.tolist() == [
        OFFPLAN_COUNT,
        OFFPLAN_AMOUNT,
        READY_COUNT,
        READY_AMOUNT,
    ]
    assert data.values.index.max() == pd.Timestamp("2025-05-31")
    # 最新月：期房笔数 112 + 22 = 134；期房金额 1012 + 112 = 1124
    assert data.values.loc["2025-05-31", OFFPLAN_COUNT] == 134
    assert data.values.loc["2025-05-31", OFFPLAN_AMOUNT] == 1_124
    # 现房：笔数 412 + 42 = 454；金额 4012 + 312 = 4324
    assert data.values.loc["2025-05-31", READY_COUNT] == 454
    assert data.values.loc["2025-05-31", READY_AMOUNT] == 4_324
    # 2025-01 期房商业金额为 0（掩码为缺失）→ 合计降级为住宅金额 1008
    assert data.values.loc["2025-01-31", OFFPLAN_AMOUNT] == 1_008
    # 同期笔数不受影响：108 + 18 = 126
    assert data.values.loc["2025-01-31", OFFPLAN_COUNT] == 126
    assert {item.source for item in data.metadata.values()} == {
        "Dubai Land Department"
    }


def test_latest_complete_month_requires_all_four_aggregates() -> None:
    data = load_real_estate_data(_workbook_bytes(), file_name="test.xlsx")

    assert latest_complete_month(data.values) == pd.Timestamp("2025-05-31")

    partial = data.values.copy()
    partial.loc["2025-05-31", OFFPLAN_AMOUNT] = float("nan")
    assert latest_complete_month(partial) == pd.Timestamp("2025-04-30")


def test_anchor_last_month_skips_the_in_progress_month() -> None:
    """最新月若恰为当前自然月（尚未过完）→ 回退一个月；否则取数据最新月。"""

    from htfa.monitoring.uae.real_estate.data import anchor_last_month

    data = load_real_estate_data(_workbook_bytes(), file_name="test.xlsx")

    # 数据最新月（2025-05）正是“今天”所在月 → 尚未过完，锚定 2025-04
    assert anchor_last_month(
        data.values, today=pd.Timestamp("2025-05-18")
    ) == pd.Period("2025-04", freq="M")
    # 月度数据已完整（今天已进入 2025-06）→ 直接取 2025-05
    assert anchor_last_month(
        data.values, today=pd.Timestamp("2025-06-01")
    ) == pd.Period("2025-05", freq="M")
    # 数据滞后（今天 2025-07）→ 保持 2025-05
    assert anchor_last_month(
        data.values, today=pd.Timestamp("2025-07-15")
    ) == pd.Period("2025-05", freq="M")


def test_build_sales_figure_renders_bar_and_amount_line_for_both_markets() -> None:
    """两张图都按 Ts 默认模板绘制：双轴、柱+线、网格、中文来源。"""

    from matplotlib.colors import to_rgb

    from Ts.TsPlots.style import DEFAULT_PALETTE, GRAY

    data = load_real_estate_data(_workbook_bytes(), file_name="test.xlsx")
    last_month = data.values.index.max().to_period("M")

    for market in ("期房", "现房"):
        figure = build_sales_figure(
            data.values,
            market=market,
            title=renderer.DEFAULT_TITLES[market],
            source_text="Dubai Land Department",
            last_month=last_month,
        )
        count_col, amount_col = MARKET_CONFIG[market]
        assert len(figure.axes) == 2
        axis, amount_axis = figure.axes
        assert axis.get_title() == renderer.DEFAULT_TITLES[market]
        assert axis.get_ylabel() == "笔"
        assert amount_axis.get_ylabel() == "亿迪拉姆"
        # 默认模板：网格开启、柱自 0 起
        assert len(axis.get_ygridlines()) > 0
        assert axis.get_ylim()[0] == 0
        assert amount_axis.get_ylim()[0] == 0
        # 柱色统一为灰色（bar_face_color 覆盖模板首色），线色遵循模板色板（次色线）
        assert axis.patches[0].get_facecolor()[:3] == pytest.approx(
            to_rgb(GRAY)
        )
        amount_line = next(
            line
            for line in amount_axis.get_lines()
            if not line.get_label().startswith("_")
        )
        assert amount_line.get_color() == DEFAULT_PALETTE[1]
        assert len(axis.patches) == 13  # 窗口内 13 个月的真实数据
        # 金额线按亿 AED 展示（百万 AED ÷ 100）
        assert amount_line.get_ydata()[-1] == pytest.approx(
            data.values.loc["2025-05-31", amount_col] / 100
        )
        # 模板图例挂在参考轴（主轴）上，双轴叠加自动追加（左轴/右轴）后缀
        assert {
            text.get_text() for text in axis.get_legend().get_texts()
        } == {f"{COUNT_LABEL}（左轴）", f"{AMOUNT_LABEL}（右轴）"}
        # 数据来源已译为中文
        assert any("迪拜土地局" in text.get_text() for text in figure.texts)


def test_build_sales_figure_renders_each_property_segment() -> None:
    data = load_real_estate_data(_workbook_bytes(), file_name="test.xlsx")
    last_month = data.values.index.max().to_period("M")

    assert data.raw_values is not None
    for market, (count_col, amount_col) in PROPERTY_CONFIG.items():
        figure = build_sales_figure(
            data.raw_values,
            market=market,
            title=renderer.DEFAULT_TITLES[market],
            source_text="Dubai Land Department",
            last_month=last_month,
        )

        axis, amount_axis = figure.axes
        assert axis.get_title() == renderer.DEFAULT_TITLES[market]
        assert len(axis.patches) == 13
        assert amount_axis.get_lines()[0].get_ydata()[-1] == pytest.approx(
            data.raw_values.loc["2025-05-31", amount_col] / 100
        )
        assert axis.patches[-1].get_height() == pytest.approx(
            data.raw_values.loc["2025-05-31", count_col]
        )


def test_sales_display_values_converts_amount_to_yi_aed() -> None:
    """展示表金额由百万 AED 折算为亿 AED，笔数不变。"""

    from htfa.monitoring.uae.real_estate.charts import sales_display_values

    data = load_real_estate_data(_workbook_bytes(), file_name="test.xlsx")
    last_month = data.values.index.max().to_period("M")

    frame = sales_display_values(data.values, last_month=last_month)

    assert frame.loc["2025-05-31", OFFPLAN_COUNT] == 134
    assert frame.loc["2025-05-31", OFFPLAN_AMOUNT] == pytest.approx(1_124 / 100)
    assert frame.loc["2025-05-31", READY_AMOUNT] == pytest.approx(4_324 / 100)


def test_section_renders_four_cross_segment_charts_and_explanation(
    monkeypatch,
) -> None:
    data = load_real_estate_data(_workbook_bytes(), file_name="test.xlsx")
    monkeypatch.setattr(
        renderer,
        "_load_real_estate_cached",
        lambda content, file_name: data,
    )
    st_obj = MagicMock()
    metric_columns = tuple(MagicMock() for _ in range(4))
    first_row = (MagicMock(), MagicMock())
    second_row = (MagicMock(), MagicMock())
    chart_rows = [
        first_row,
        second_row,
    ]
    left, right = first_row

    def _columns(n, gap=None):
        if n == 4:
            return metric_columns
        return chart_rows.pop(0)

    st_obj.columns.side_effect = _columns
    markets = []
    original_render = renderer._render_sales_chart

    def _record_market(st_obj, data, last_month, market):
        markets.append((st_obj, market))
        return original_render(st_obj, data, last_month, market=market)

    monkeypatch.setattr(renderer, "_render_sales_chart", _record_market)

    result = renderer.render_real_estate_section(
        st_obj,
        b"workbook",
        "test.xlsx",
    )

    assert result["status"] == "success"
    assert result["as_of"] == "2025-05"
    calls = [call[0] for call in st_obj.method_calls]
    assert calls.count("divider") == 1
    assert calls.count("subheader") == 1
    assert st_obj.subheader.call_args.args[0] == "房地产"
    assert st_obj.metric.call_count == 4
    assert [call.args[0] for call in st_obj.metric.call_args_list] == [
        "现房销售笔数",
        "现房销售金额",
        "期房销售笔数",
        "期房销售金额",
    ]
    assert all(
        "环比" in call.kwargs["delta"] and "同比" in call.kwargs["delta"]
        for call in st_obj.metric.call_args_list
    )
    assert st_obj.columns.call_args.kwargs["gap"] == "small"
    assert st_obj.columns.call_count == 3
    assert markets == [
        (left, "现房住宅"),
        (right, "现房商业"),
        (second_row[0], "期房住宅"),
        (second_row[1], "期房商业"),
    ]
    assert all(
        column.pyplot.call_count == 1
        for row in (first_row, second_row)
        for column in row
    )
    assert all(
        column.download_button.call_count == 1
        for row in (first_row, second_row)
        for column in row
    )
    assert st_obj.pyplot.call_count == 0
    assert st_obj.expander.call_count == 1
    # 说明正文渲染在 expander 的 with 体内（直接调用的 st_obj.markdown）
    assert st_obj.markdown.call_count == 1


def test_section_loader_failure_shows_error_and_returns_error_status(
    monkeypatch,
) -> None:
    def _explode(*args, **kwargs):
        raise ValueError("月度_DLD 缺少期房销售指标")

    monkeypatch.setattr(renderer, "_load_real_estate_cached", _explode)
    st_obj = MagicMock()

    result = renderer.render_real_estate_section(
        st_obj,
        b"workbook",
        "test.xlsx",
    )

    assert result["status"] == "error"
    assert st_obj.error.call_count == 1
    assert st_obj.pyplot.call_count == 0


def test_cell_failure_warns_cell_and_keeps_other_charts(monkeypatch) -> None:
    data = load_real_estate_data(_workbook_bytes(), file_name="test.xlsx")
    monkeypatch.setattr(
        renderer,
        "_load_real_estate_cached",
        lambda content, file_name: data,
    )
    st_obj = MagicMock()
    metric_columns = tuple(MagicMock() for _ in range(4))
    first_row = (MagicMock(), MagicMock())
    second_row = (MagicMock(), MagicMock())
    chart_rows = [first_row, second_row]

    def _columns(n, gap=None):
        return metric_columns if n == 4 else chart_rows.pop(0)

    st_obj.columns.side_effect = _columns

    original_render = renderer._render_sales_chart

    def _fail_offplan(st_obj, data, last_month, market):
        if market == "期房商业":
            raise KeyError("期房金额列缺失")
        return original_render(st_obj, data, last_month, market=market)

    monkeypatch.setattr(renderer, "_render_sales_chart", _fail_offplan)

    result = renderer.render_real_estate_section(
        st_obj,
        b"workbook",
        "test.xlsx",
    )

    assert result["status"] == "success"
    assert second_row[1].warning.call_count == 1
    rendered_columns = [first_row[0], first_row[1], second_row[0]]
    assert all(column.pyplot.call_count == 1 for column in rendered_columns)
    assert all(
        column.download_button.call_count == 1
        for column in rendered_columns
    )
    assert second_row[1].pyplot.call_count == 0
    assert st_obj.error.call_count == 0
