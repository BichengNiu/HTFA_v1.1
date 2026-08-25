"""Tests for the CBUAE government and government-related entity panel."""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from dashboard.analysis.uae.government_finance import renderer
from dashboard.analysis.uae.government_finance.charts import (
    YOY_SERIES,
    build_government_finance_yoy_figure,
)
from dashboard.analysis.uae.government_finance.data import (
    GOVERNMENT_CREDIT,
    GOVERNMENT_DEPOSITS,
    GRE_CREDIT,
    GRE_DEPOSITS,
    calculate_calendar_yoy,
    load_government_finance_data,
)
from dashboard.analysis.uae.government_finance.ded import (
    ENTERPRISES_DISPLAY,
    LICENCES_DISPLAY,
)
from dashboard.analysis.uae.government_finance.credit import (
    BUSINESS_INDUSTRIAL_DISPLAY,
    FOREIGN_CURRENCIES_DISPLAY,
    FOREIGN_LIABILITIES_DISPLAY,
    INDIVIDUAL_DISPLAY,
    NONRESIDENT_DEPOSITS,
    PRIVATE_CORPORATE_DISPLAY,
)
from dashboard.analysis.uae.foreign_labor import (
    BANGLADESH_CLEARANCES,
    NEPAL_APPROVALS,
)
from dashboard.analysis.uae.government_finance.pmi import PMI_LABEL
from dashboard.analysis.uae.government_finance.payments import (
    CHEQUES_AMOUNT_DISPLAY,
    CHEQUES_NUMBER_DISPLAY,
    CUSTOMER_TRANSFERS_AMOUNT_DISPLAY,
    CUSTOMER_TRANSFERS_NUMBER_DISPLAY,
)
from dashboard.analysis.uae.government_finance.rates import (
    EIBOR_ONEYEAR_DISPLAY,
    EIBOR_OVERNIGHT_DISPLAY,
    US_OVERNIGHT_DISPLAY,
    US_SOFR_12M_DISPLAY,
)
from dashboard.analysis.uae.government_finance.search_index import (
    WORK_DUBAI_COLUMN,
    WORK_UAE_COLUMN,
)
from dashboard.analysis.uae.government_finance.renderer import _render_charts


def _data_lines(axis):
    """轴上带标签的真实数据线（排除模板占位/参考线，如空标签的 0 参考线）。"""
    return [
        line
        for line in axis.get_lines()
        if line.get_label() and not line.get_label().startswith("_")
    ]


def _workbook_bytes() -> bytes:
    dates = pd.date_range("2024-05-31", periods=13, freq="ME")
    frame = pd.DataFrame(
        {
            "日期": dates,
            GOVERNMENT_DEPOSITS: [100_000.0] * 12 + [110_000.0],
            GRE_DEPOSITS: [200_000.0] * 12 + [240_000.0],
            GOVERNMENT_CREDIT: [300_000.0] * 12 + [390_000.0],
            GRE_CREDIT: [400_000.0] * 12 + [500_000.0],
        }
    )
    future = pd.DataFrame(
        {
            "日期": pd.to_datetime(["2025-06-30", "2025-07-31"]),
            GOVERNMENT_DEPOSITS: [0, 0],
            GRE_DEPOSITS: [0, 0],
            GOVERNMENT_CREDIT: [0, 0],
            GRE_CREDIT: [0, 0],
        }
    )
    data = pd.concat([future, frame.iloc[::-1]], ignore_index=True)
    metadata = pd.DataFrame(
        [
            ["CBUAE", None, None, None, None],
            [
                "指标名称",
                GOVERNMENT_DEPOSITS,
                GRE_DEPOSITS,
                GOVERNMENT_CREDIT,
                GRE_CREDIT,
            ],
            ["频率", "月", "月", "月", "月"],
            ["单位", *("百万迪拉姆",) * 4],
            ["来源", *("CBUAE",) * 4],
            ["更新时间", *("2026-08-12",) * 4],
        ]
    )
    rows = pd.concat(
        [
            metadata,
            data.rename(columns={"日期": 0}).set_axis(range(5), axis=1),
        ],
        ignore_index=True,
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        rows.to_excel(
            writer,
            sheet_name="月度_CBUAE",
            header=False,
            index=False,
        )
    return buffer.getvalue()


def test_loader_reads_four_cbuae_indicators_and_ignores_zero_placeholders() -> None:
    data = load_government_finance_data(
        _workbook_bytes(),
        file_name="test.xlsx",
    )

    assert data.values.columns.tolist() == [
        GOVERNMENT_DEPOSITS,
        GOVERNMENT_CREDIT,
        GRE_DEPOSITS,
        GRE_CREDIT,
    ]
    assert data.values.index.max() == pd.Timestamp("2025-05-31")
    assert data.values.loc["2025-05-31", GOVERNMENT_DEPOSITS] == 110_000
    assert {item.source for item in data.metadata.values()} == {"CBUAE"}


def test_calendar_yoy_uses_the_matching_month_when_an_observation_is_missing() -> None:
    dates = pd.date_range("2024-04-30", "2025-05-31", freq="ME").difference(
        pd.DatetimeIndex(["2024-06-30"])
    )
    observations = pd.Series(200.0, index=dates)
    observations.loc["2024-04-30"] = 50.0
    observations.loc["2024-05-31"] = 100.0
    observations.loc["2025-05-31"] = 110.0
    values = observations.to_frame("指标")

    yoy = calculate_calendar_yoy(values)

    assert yoy.loc["2025-05-31", "指标"] == pytest.approx(10.0)


def test_yoy_chart_renders_two_government_credit_growth_lines() -> None:
    data = load_government_finance_data(
        _workbook_bytes(),
        file_name="test.xlsx",
    )

    figure = build_government_finance_yoy_figure(
        data.values,
        title="政府贷款与政府控股企业贷款同比",
        source_text="CBUAE",
    )

    assert len(figure.axes) == 1
    axis = figure.axes[0]
    lines = _data_lines(axis)
    assert [line.get_label() for line in lines] == [
        spec[1] for spec in YOY_SERIES
    ]
    # 模板色板与线型循环接管：黑/深蓝，实/虚
    assert [line.get_color() for line in lines] == ["#141414", "#1f4e79"]
    assert [line.get_linestyle() for line in lines] == ["-", "--"]
    # 政府信贷 300k→390k = +30%；政府控制企业信贷 400k→500k = +25%
    assert [line.get_ydata()[-1] for line in lines] == pytest.approx(
        [30.0, 25.0]
    )
    assert axis.get_ylabel() == "%"
    assert axis.get_title() == "政府贷款与政府控股企业贷款同比"
    # 模板 style_axes 隐藏上/右脊线
    assert not axis.spines["top"].get_visible()
    assert not axis.spines["right"].get_visible()
    assert {text.get_text() for text in axis.get_legend().get_texts()} == {
        spec[1] for spec in YOY_SERIES
    }
    assert any(text.get_text() == "数据来源：阿联酋央行" for text in figure.texts)


def test_yoy_chart_calculates_yoy_before_applying_three_year_window() -> None:
    dates = pd.date_range("2021-01-31", periods=49, freq="ME")
    values = pd.DataFrame(
        {
            GOVERNMENT_DEPOSITS: range(100_000, 149_000, 1_000),
            GOVERNMENT_CREDIT: range(200_000, 249_000, 1_000),
            GRE_DEPOSITS: range(300_000, 349_000, 1_000),
            GRE_CREDIT: range(400_000, 449_000, 1_000),
        },
        index=dates,
    )

    figure = build_government_finance_yoy_figure(
        values,
        title="政府贷款与政府控股企业贷款同比",
        source_text="CBUAE",
    )

    lines = _data_lines(figure.axes[0])
    assert {len(line.get_xdata()) for line in lines} == {37}
    assert all(pd.notna(line.get_ydata()[0]) for line in lines)


def test_chart_row_renders_one_yoy_view_and_downloads_only_yoy_data() -> None:
    data = load_government_finance_data(
        _workbook_bytes(),
        file_name="test.xlsx",
    )
    st_obj = MagicMock()

    _render_charts(st_obj, data, pd.Timestamp("2025-05-31"))

    assert st_obj.pyplot.call_count == 1
    assert st_obj.download_button.call_count == 1
    chart_data = st_obj.download_button.call_args.kwargs["data"].decode("utf-8-sig")
    assert "同比（%）" in chart_data
    assert "百万迪拉姆" not in chart_data
    figure = st_obj.pyplot.call_args.args[0]
    assert st_obj.pyplot.call_args.kwargs["bbox_inches"] is None
    assert len(figure.axes) == 1
    assert {
        len(line.get_xdata())
        for line in _data_lines(figure.axes[0])
    } == {13}


def test_section_renders_quad_business_and_labor_employment_subsections(
    monkeypatch,
) -> None:
    data = load_government_finance_data(
        _workbook_bytes(),
        file_name="test.xlsx",
    )
    monkeypatch.setattr(
        renderer,
        "_load_government_finance_cached",
        lambda content, file_name: data,
    )
    for loader_name in (
        "_load_rates_cached",
        "_load_foreign_inflow_cached",
        "_load_private_credit_cached",
        "_load_ded_cached",
        "_load_pmi_cached",
        "_load_payment_cached",
        "_load_foreign_labor_cached",
        "_load_search_index_cached",
    ):
        monkeypatch.setattr(renderer, loader_name, lambda *args: object())
    render_mocks: dict[str, MagicMock] = {}
    for render_name in (
        "_render_rates_chart",
        "_render_foreign_inflow_chart",
        "_render_private_credit_chart",
        "_render_charts",
        "_render_ded_chart",
        "_render_pmi_chart",
        "_render_customer_transfers_chart",
        "_render_cheques_chart",
        "_render_foreign_labor_chart",
        "_render_search_index_chart",
        "_render_finance_metrics",
        "_render_business_metrics",
        "_render_labor_metrics",
    ):
        render_mocks[render_name] = MagicMock()
        monkeypatch.setattr(renderer, render_name, render_mocks[render_name])
    st_obj = MagicMock()
    st_obj.columns.return_value = (MagicMock(), MagicMock())

    result = renderer.render_government_finance_section(
        st_obj,
        b"workbook",
        "test.xlsx",
    )

    assert result["status"] == "success"
    st_obj.container.assert_called_once_with(key="uae-finance-part")
    calls = [call[0] for call in st_obj.method_calls]
    assert calls.count("divider") == 3
    assert calls.count("subheader") == 3
    assert calls.index("divider") < calls.index("subheader")
    assert [call.args[0] for call in st_obj.subheader.call_args_list] == [
        "财政金融",
        "企业活动",
        "劳动就业",
    ]
    # 2×2 四图 + 企业活动两行 + 劳动就业一行共 5 次 columns（指标行被 mock 不计）
    assert st_obj.columns.call_count == 5
    assert render_mocks["_render_rates_chart"].call_count == 1
    assert render_mocks["_render_foreign_inflow_chart"].call_count == 1
    assert render_mocks["_render_charts"].call_count == 1
    assert render_mocks["_render_private_credit_chart"].call_count == 1
    assert render_mocks["_render_ded_chart"].call_count == 1
    assert render_mocks["_render_pmi_chart"].call_count == 1
    assert render_mocks["_render_customer_transfers_chart"].call_count == 1
    assert render_mocks["_render_cheques_chart"].call_count == 1
    assert render_mocks["_render_foreign_labor_chart"].call_count == 1
    assert render_mocks["_render_search_index_chart"].call_count == 1
    # 三个 part 的指标行各渲染一次
    assert render_mocks["_render_finance_metrics"].call_count == 1
    assert render_mocks["_render_business_metrics"].call_count == 1
    assert render_mocks["_render_labor_metrics"].call_count == 1


def test_quad_cell_failure_warns_cell_and_keeps_section(monkeypatch) -> None:
    """某个格子的渲染 KeyError 只能让该格警告，不能拖垮整个区块。"""

    from dashboard.analysis.uae.government_finance.rates import (
        EIBOR_OVERNIGHT_DISPLAY,
    )

    missing_key = EIBOR_OVERNIGHT_DISPLAY

    data = load_government_finance_data(
        _workbook_bytes(),
        file_name="test.xlsx",
    )
    monkeypatch.setattr(
        renderer,
        "_load_government_finance_cached",
        lambda content, file_name: data,
    )
    for loader_name in (
        "_load_rates_cached",
        "_load_foreign_inflow_cached",
        "_load_private_credit_cached",
        "_load_ded_cached",
        "_load_pmi_cached",
        "_load_payment_cached",
        "_load_foreign_labor_cached",
        "_load_search_index_cached",
    ):
        monkeypatch.setattr(renderer, loader_name, lambda *args: object())

    render_mocks: dict[str, MagicMock] = {}
    for render_name in (
        "_render_foreign_inflow_chart",
        "_render_private_credit_chart",
        "_render_charts",
        "_render_ded_chart",
        "_render_pmi_chart",
        "_render_customer_transfers_chart",
        "_render_cheques_chart",
        "_render_foreign_labor_chart",
        "_render_search_index_chart",
        "_render_finance_metrics",
        "_render_business_metrics",
        "_render_labor_metrics",
    ):
        render_mocks[render_name] = MagicMock()
        monkeypatch.setattr(renderer, render_name, render_mocks[render_name])

    def _fail_rate_chart(*args, **kwargs):
        raise KeyError(missing_key)

    monkeypatch.setattr(renderer, "_render_rates_chart", _fail_rate_chart)

    st_obj = MagicMock()
    cells: list[MagicMock] = []

    def columns(n, gap="small"):
        row = [MagicMock() for _ in range(n)]
        cells.extend(row)
        return tuple(row)

    st_obj.columns.side_effect = columns

    result = renderer.render_government_finance_section(
        st_obj,
        b"workbook",
        "test.xlsx",
    )

    assert result["status"] == "success"
    # 其他九张图照常渲染
    for name in render_mocks:
        assert render_mocks[name].call_count == 1, name
    # 区块级错误不出现；而是某个格子出现警告
    assert st_obj.error.call_count == 0
    assert any(cell.warning.call_count >= 1 for cell in cells)


def test_payment_chart_failure_warns_only_its_business_cell(monkeypatch) -> None:
    """支付图单独失败时，另一张支付图和其它分区仍继续渲染。"""

    data = load_government_finance_data(
        _workbook_bytes(),
        file_name="test.xlsx",
    )
    monkeypatch.setattr(
        renderer,
        "_load_government_finance_cached",
        lambda content, file_name: data,
    )
    for loader_name in (
        "_load_rates_cached",
        "_load_foreign_inflow_cached",
        "_load_private_credit_cached",
        "_load_ded_cached",
        "_load_pmi_cached",
        "_load_payment_cached",
        "_load_foreign_labor_cached",
        "_load_search_index_cached",
    ):
        monkeypatch.setattr(renderer, loader_name, lambda *args: object())

    render_mocks: dict[str, MagicMock] = {}
    for render_name in (
        "_render_rates_chart",
        "_render_foreign_inflow_chart",
        "_render_private_credit_chart",
        "_render_charts",
        "_render_ded_chart",
        "_render_pmi_chart",
        "_render_cheques_chart",
        "_render_foreign_labor_chart",
        "_render_search_index_chart",
        "_render_finance_metrics",
        "_render_business_metrics",
        "_render_labor_metrics",
    ):
        render_mocks[render_name] = MagicMock()
        monkeypatch.setattr(renderer, render_name, render_mocks[render_name])

    def _fail_customer_transfers(*args, **kwargs):
        raise KeyError("FTS 客户转账指标缺失")

    monkeypatch.setattr(
        renderer,
        "_render_customer_transfers_chart",
        _fail_customer_transfers,
    )

    st_obj = MagicMock()
    cells: list[MagicMock] = []

    def columns(n, gap="small"):
        row = [MagicMock() for _ in range(n)]
        cells.extend(row)
        return tuple(row)

    st_obj.columns.side_effect = columns

    result = renderer.render_government_finance_section(
        st_obj,
        b"workbook",
        "test.xlsx",
    )

    assert result["status"] == "success"
    assert render_mocks["_render_cheques_chart"].call_count == 1
    assert st_obj.error.call_count == 0
    assert any(cell.warning.call_count >= 1 for cell in cells)


def test_finance_metrics_row_falls_back_to_warning(monkeypatch) -> None:
    """财政金融指标行 loader 失败 → 只在该行出警告，不抛出异常。"""

    def _explode(*args, **kwargs):
        raise ValueError("日度_Wind 利率列缺失")

    monkeypatch.setattr(renderer, "_load_rates_cached", _explode)
    st_obj = MagicMock()
    st_obj.columns.return_value = (MagicMock(), MagicMock(), MagicMock(), MagicMock())

    renderer._render_finance_metrics(
        st_obj,
        MagicMock(),
        b"workbook",
        "test.xlsx",
    )

    assert st_obj.warning.call_count == 1
    assert st_obj.metric.call_count == 0


def test_finance_metrics_cover_all_absolute_series_with_mom_and_yoy(
    monkeypatch,
) -> None:
    dates = pd.date_range("2025-01-31", periods=14, freq="ME")

    def _metadata(columns):
        return {
            column: SimpleNamespace(
                frequency="月",
                source="测试来源",
                updated_at="2026-08-20",
            )
            for column in columns
        }

    rates_values = pd.DataFrame(
        {
            EIBOR_OVERNIGHT_DISPLAY: [1.0] * 12 + [1.1, 1.2],
            EIBOR_ONEYEAR_DISPLAY: [2.0] * 12 + [2.1, 2.2],
            US_OVERNIGHT_DISPLAY: [3.0] * 12 + [3.1, 3.2],
            US_SOFR_12M_DISPLAY: [4.0] * 12 + [4.1, 4.2],
        },
        index=dates,
    )
    foreign_values = pd.DataFrame(
        {
            FOREIGN_LIABILITIES_DISPLAY: [100.0] * 12 + [110.0, 121.0],
            FOREIGN_CURRENCIES_DISPLAY: [200.0] * 12 + [220.0, 242.0],
            NONRESIDENT_DEPOSITS: [300.0] * 12 + [330.0, 363.0],
        },
        index=dates,
    )
    private_values = pd.DataFrame(
        {
            PRIVATE_CORPORATE_DISPLAY: [400.0] * 12 + [440.0, 484.0],
            INDIVIDUAL_DISPLAY: [500.0] * 12 + [550.0, 605.0],
            BUSINESS_INDUSTRIAL_DISPLAY: [600.0] * 12 + [660.0, 726.0],
        },
        index=dates,
    )
    monkeypatch.setattr(
        renderer,
        "_load_rates_cached",
        lambda content, file_name: SimpleNamespace(
            values=rates_values,
            metadata=_metadata(rates_values.columns),
        ),
    )
    monkeypatch.setattr(
        renderer,
        "_load_foreign_inflow_cached",
        lambda content, file_name: SimpleNamespace(
            values=foreign_values,
            metadata=_metadata(
                [
                    FOREIGN_LIABILITIES_DISPLAY,
                    FOREIGN_CURRENCIES_DISPLAY,
                    "非居民私人企业存款",
                ]
            ),
        ),
    )
    monkeypatch.setattr(
        renderer,
        "_load_private_credit_cached",
        lambda content, file_name: SimpleNamespace(
            values=private_values,
            metadata=_metadata(private_values.columns),
        ),
    )

    data = load_government_finance_data(_workbook_bytes(), file_name="test.xlsx")
    st_obj = MagicMock()
    st_obj.columns.side_effect = lambda n: tuple(
        MagicMock() for _ in range(n)
    )

    renderer._render_finance_metrics(
        st_obj,
        data,
        b"workbook",
        "test.xlsx",
    )

    assert st_obj.metric.call_count == 12
    assert [call.args[0] for call in st_obj.metric.call_args_list] == [
        "阿联酋隔夜拆借利率",
        "阿联酋1年期拆借利率",
        "美国隔夜拆借利率",
        "美国1年期拆借利率",
        "银行外债",
        "外币存款",
        "外国主体存款",
        "政府贷款",
        "政府控股企业贷款",
        "私人企业信贷",
        "个人信贷",
        "工商业贷款",
    ]
    assert all(
        "环比" in call.kwargs["delta"] and "同比" in call.kwargs["delta"]
        for call in st_obj.metric.call_args_list
    )
    assert all(
        any(
            unit in call.args[1]
            for unit in ("百亿迪拉姆", "十亿迪拉姆", "亿迪拉姆", "百万迪拉姆")
        )
        and "百万迪拉姆" not in call.args[1]
        for call in st_obj.metric.call_args_list[4:]
    )


def test_business_metrics_row_falls_back_to_warning(monkeypatch) -> None:
    """企业活动指标行 loader 失败 → 只在该行出警告，不抛出异常。"""

    def _explode(*args, **kwargs):
        raise KeyError("PMI 序列缺失")

    monkeypatch.setattr(renderer, "_load_pmi_cached", _explode)
    st_obj = MagicMock()

    renderer._render_business_metrics(
        st_obj,
        pd.Timestamp("2026-06-30"),
        b"workbook",
        "test.xlsx",
    )

    assert st_obj.warning.call_count == 1
    assert st_obj.metric.call_count == 0


def test_labor_metrics_row_falls_back_to_warning(monkeypatch) -> None:
    """劳动就业指标行 loader 失败 → 只在该行出警告，不抛出异常。"""

    def _explode(*args, **kwargs):
        raise FileNotFoundError("工作搜索热度.csv 缺失")

    monkeypatch.setattr(renderer, "_load_foreign_labor_cached", _explode)
    st_obj = MagicMock()

    renderer._render_labor_metrics(
        st_obj,
        b"workbook",
        "test.xlsx",
    )

    assert st_obj.warning.call_count == 1
    assert st_obj.metric.call_count == 0


def test_business_and_labor_metrics_show_mom_and_yoy(monkeypatch) -> None:
    dates = pd.date_range("2025-01-31", periods=14, freq="ME")

    def _metadata(columns):
        return {
            column: SimpleNamespace(
                frequency="月",
                source="测试来源",
                updated_at="2026-08-20",
            )
            for column in columns
        }

    pmi_values = pd.DataFrame(
        {PMI_LABEL: [50.0] * 12 + [51.0, 52.0]}, index=dates
    )
    ded_values = pd.DataFrame(
        {
            ENTERPRISES_DISPLAY: [100.0] * 12 + [110.0, 121.0],
            LICENCES_DISPLAY: [50.0] * 12 + [55.0, 60.0],
        },
        index=dates,
    )
    labor_values = pd.DataFrame(
        {
            NEPAL_APPROVALS: [100.0] * 12 + [110.0, 121.0],
            BANGLADESH_CLEARANCES: [200.0] * 12 + [220.0, 242.0],
        },
        index=dates,
    )
    search_values = pd.DataFrame(
        {
            WORK_DUBAI_COLUMN: [100.0] * 12 + [110.0, 121.0],
            WORK_UAE_COLUMN: [200.0] * 12 + [220.0, 242.0],
        },
        index=dates,
    )
    payment_values = pd.DataFrame(
        {
            CUSTOMER_TRANSFERS_NUMBER_DISPLAY: range(100, 156, 4),
            CUSTOMER_TRANSFERS_AMOUNT_DISPLAY: range(200, 256, 4),
            CHEQUES_NUMBER_DISPLAY: range(300, 356, 4),
            CHEQUES_AMOUNT_DISPLAY: range(400, 456, 4),
        },
        index=dates,
    )
    monkeypatch.setattr(
        renderer,
        "_load_pmi_cached",
        lambda content, file_name: SimpleNamespace(
            values=pmi_values,
            metadata=_metadata([PMI_LABEL]),
        ),
    )
    monkeypatch.setattr(
        renderer,
        "_load_ded_cached",
        lambda content, file_name: SimpleNamespace(
            values=ded_values,
            metadata=_metadata([ENTERPRISES_DISPLAY, LICENCES_DISPLAY]),
        ),
    )
    monkeypatch.setattr(
        renderer,
        "_load_foreign_labor_cached",
        lambda content, file_name: SimpleNamespace(
            values=labor_values,
            metadata=_metadata([NEPAL_APPROVALS, BANGLADESH_CLEARANCES]),
        ),
    )
    monkeypatch.setattr(
        renderer,
        "_load_search_index_cached",
        lambda content, file_name: search_values,
    )
    monkeypatch.setattr(
        renderer,
        "_load_payment_cached",
        lambda content, file_name: SimpleNamespace(
            values=payment_values,
            metadata=_metadata(
                [
                    CUSTOMER_TRANSFERS_NUMBER_DISPLAY,
                    CUSTOMER_TRANSFERS_AMOUNT_DISPLAY,
                    CHEQUES_NUMBER_DISPLAY,
                    CHEQUES_AMOUNT_DISPLAY,
                ]
            ),
        ),
    )

    business_st = MagicMock()
    business_st.columns.side_effect = lambda n: tuple(
        MagicMock() for _ in range(n)
    )
    renderer._render_business_metrics(
        business_st,
        dates[-1],
        b"workbook",
        "test.xlsx",
    )
    assert business_st.metric.call_count == 7
    assert business_st.metric.call_args_list[0].args[0] == (
        "非油私营部门采购经理指数（PMI）"
    )
    business_st.caption.assert_not_called()
    assert all(
        "环比" in call.kwargs["delta"] and "同比" in call.kwargs["delta"]
        for call in business_st.metric.call_args_list
    )

    labor_st = MagicMock()
    labor_st.columns.return_value = tuple(MagicMock() for _ in range(4))
    renderer._render_labor_metrics(labor_st, b"workbook", "test.xlsx")
    assert labor_st.metric.call_count == 4
    assert all(
        "环比" in call.kwargs["delta"] and "同比" in call.kwargs["delta"]
        for call in labor_st.metric.call_args_list
    )
