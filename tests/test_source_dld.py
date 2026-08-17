"""source_dld 周度指标纯函数测试。

只测 build_rows / 数值公式 / 常量完整性，不触碰真实 DuckDB 库、
网络下载或 Excel 工作簿（符合模块约定与 pip 环境约束）。
"""

from datetime import date, timedelta
import math
import sys
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "UAE"
if str(DATA_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_DIR))

import source_dld as dld  # noqa: E402


def _week(offset: int) -> date:
    """以 2015-01-05（周一）为原点生成模拟周起始日。"""

    return date(2015, 1, 5) + timedelta(weeks=offset)


def _raw_row(offset: int, **overrides) -> dict:
    """构造 RAW_WEEKLY_SQL 的一行输入，默认值是稳定的静态口径。"""

    row = {
        "week_start": _week(offset),
        "week_end": _week(offset) + timedelta(days=6),
        "source_data_through": _week(offset) + timedelta(days=6),
        "initial_new_projects": 5,
        "confirmed_new_projects": 4,
        "confirmed_new_projects_28d": 200 + offset,
        "offplan_sales_28d": 900 + offset,
        "offplan_sales_value_28d": 500000.0,
        "active_projects_28d": 100 + offset,
        "offplan_sales_per_active_project_28d": round(
            (900 + offset) / (100 + offset), 6
        ),
        "project_number_coverage_pct_28d": 99.5,
        "commercial_transition_projects": 2,
        "commercial_transition_projects_13w": 50 + offset,
    }
    row.update(overrides)
    return row


def _series(count: int, offset_start: int = 0, **overrides) -> list[dict]:
    """生成连续的模拟原始行列表。"""

    return [
        _raw_row(offset_start + index, **overrides) for index in range(count)
    ]


# ---------------------------------------------------------------------------
# 纯函数基础
# ---------------------------------------------------------------------------

def test_parse_float_handles_strings_none_and_numbers() -> None:
    assert dld.parse_float(None) is None
    assert dld.parse_float("") is None
    assert dld.parse_float("12.5") == 12.5
    assert dld.parse_float("0") == 0.0
    assert dld.parse_float(7) == 7.0
    assert dld.parse_float(2.25) == 2.25


def test_log_momentum_formula_and_guards() -> None:
    assert dld.log_momentum(9.0, 2.0) == math.log1p(9.0) - math.log1p(2.0)
    assert dld.log_momentum(0.0, 0.0) == 0.0
    assert dld.log_momentum(None, 2.0) is None
    assert dld.log_momentum(5.0, None) is None
    assert dld.log_momentum(-1.0, 2.0) is None
    assert dld.log_momentum(5.0, -1.0) is None


def test_rolling_robust_z_needs_104_observations() -> None:
    # 只有 103 个（含缺失）历史点，永远达不到 MIN_BASELINE_OBSERVATIONS
    values = [float(index % 7) for index in range(103)]
    assert dld.rolling_robust_z(values) == [None] * 103


def test_rolling_robust_z_uses_prior_window_only() -> None:
    # 前 104 个观测为 100..203 的等差序列（median=151.5, MAD=26.0），
    # 第 104 个位置的值 300 之外的任何未来数据不影响该点的 z。
    values = [float(value) for value in range(100, 204)]
    values.append(300.0)
    values.append(100000.0)  # 未来值（对前一点的 z 无影响）
    z_at_104 = dld.rolling_robust_z(values)[104]
    expected = (300.0 - 151.5) / (1.4826 * 26.0)
    assert z_at_104 == pytest.approx(expected, rel=1e-9)
    # 更靠后的点被截断到 ±5
    assert dld.rolling_robust_z(values)[105] == 5.0


def test_rolling_robust_z_flat_history_is_none() -> None:
    # MAD 为 0 时无法给出稳健尺度，返回 None
    values = [5.0] * 200
    result = dld.rolling_robust_z(values)
    assert all(value is None for value in result)


def test_score_from_z_mapping_and_clamps() -> None:
    assert dld.score_from_z(None) is None
    assert dld.score_from_z(0.0) == 50.0
    assert dld.score_from_z(2.0) == 70.0
    assert dld.score_from_z(-3.0) == 20.0
    assert dld.score_from_z(5.0) == 100.0
    assert dld.score_from_z(9.0) == 100.0
    assert dld.score_from_z(-5.0) == 0.0
    assert dld.score_from_z(-20.0) == 0.0


def test_formatted_matches_legacy_csv_formatting() -> None:
    assert dld.formatted(None) == ""
    assert dld.formatted(5) == "5"
    assert dld.formatted(5.0) == "5.000000"
    assert dld.formatted(61.2345674) == "61.234567"


# ---------------------------------------------------------------------------
# build_rows 行为
# ---------------------------------------------------------------------------

def test_build_rows_preserves_input_and_adds_derived_keys() -> None:
    rows = _series(10)
    built = dld.build_rows(rows)
    assert len(built) == 10
    derived = {
        "confirmed_launch_yoy_log_momentum",
        "confirmed_launch_z",
        "confirmed_launch_score",
        "absorption_count_yoy_log_momentum",
        "absorption_breadth_yoy_log_momentum",
        "absorption_velocity_yoy_log_momentum",
        "absorption_count_z",
        "absorption_breadth_z",
        "absorption_velocity_z",
        "offplan_absorption_z",
        "offplan_absorption_score",
        "commercial_transition_yoy_log_momentum",
        "commercial_transition_z",
        "commercial_transition_score",
        "dld_investment_pipeline_score",
        "quality_flag",
    }
    assert derived.issubset(built[0].keys())
    # 原字段原样保留（含 week_start / week_end 等）
    assert built[0]["week_start"] == _week(0)
    assert built[0]["confirmed_new_projects_28d"] == 200.0


def test_build_rows_momentum_window_none_before_yoy_weeks() -> None:
    rows = _series(dld.YOY_WEEKS + 5)
    built = dld.build_rows(rows)
    for index in range(dld.YOY_WEEKS):
        assert built[index]["confirmed_launch_yoy_log_momentum"] is None
        assert built[index]["absorption_count_yoy_log_momentum"] is None
        assert built[index]["commercial_transition_yoy_log_momentum"] is None
    # 第 52 周起出现动量
    assert built[dld.YOY_WEEKS]["confirmed_launch_yoy_log_momentum"] is not None
    # 动量不足 52 周时 z 恒为 None（历史基线不足 104 条）
    for index in range(dld.YOY_WEEKS + 5):
        assert built[index]["confirmed_launch_z"] is None
        assert built[index]["confirmed_launch_score"] is None


def test_build_rows_numeric_parsing_converts_strings() -> None:
    # 模拟旧 CSV 流程：数值带字符串类型
    plain = _raw_row(0)
    string_row = {key: str(value) for key, value in plain.items()}
    built = dld.build_rows([string_row])
    assert built[0]["confirmed_new_projects_28d"] == 200.0
    assert built[0]["active_projects_28d"] == 100.0


def test_build_rows_z_becomes_available_after_104_observations() -> None:
    rows = _series(200)
    built = dld.build_rows(rows)
    # 动量从第 52 周开始，z 从第 52 + 104 = 156 周开始
    assert built[155]["confirmed_launch_z"] is None
    assert built[156]["confirmed_launch_z"] is not None
    assert -5.0 <= built[156]["confirmed_launch_z"] <= 5.0


def test_build_rows_absorption_blend_and_composite_formula() -> None:
    rows = _series(200)
    built = dld.build_rows(rows)
    index = 180
    row = built[index]
    # 吸收指数 z = 0.4*数量 + 0.3*广度 + 0.3*速度
    expected_absorption_z = (
        0.4 * row["absorption_count_z"]
        + 0.3 * row["absorption_breadth_z"]
        + 0.3 * row["absorption_velocity_z"]
    )
    assert row["offplan_absorption_z"] == pytest.approx(
        expected_absorption_z, rel=1e-9
    )
    # 指数 = 50 + 10z，且吸收指数与各分量的 score 一致
    assert row["offplan_absorption_score"] == pytest.approx(
        dld.score_from_z(row["offplan_absorption_z"]), rel=1e-9
    )
    # 综合 = 0.3*启动 + 0.5*吸收 + 0.2*转化
    expected_composite = (
        0.3 * row["confirmed_launch_score"]
        + 0.5 * row["offplan_absorption_score"]
        + 0.2 * row["commercial_transition_score"]
    )
    assert row["dld_investment_pipeline_score"] == pytest.approx(
        expected_composite, rel=1e-9
    )
    assert 0.0 <= row["dld_investment_pipeline_score"] <= 100.0


def test_build_rows_score_clamps_to_unit_interval() -> None:
    # 剧烈跳变产生大 z，指数应被限制在 [0, 100]
    rows = _series(200)
    boost = _raw_row(150, confirmed_new_projects_28d=20000.0)
    rows[150] = boost
    built = dld.build_rows(rows)
    for index in range(156, len(built)):
        for key in (
            "confirmed_launch_score",
            "offplan_absorption_score",
            "commercial_transition_score",
        ):
            value = built[index][key]
            if value is not None:
                assert 0.0 <= value <= 100.0


def test_build_rows_none_propagation_when_velocity_missing() -> None:
    # 速度动量始终缺失 → 吸收三因子不全 → 吸收指数与综合指数全为 None
    rows = _series(200, offplan_sales_per_active_project_28d=None)
    built = dld.build_rows(rows)
    for index in range(156, len(built)):
        assert built[index]["offplan_absorption_z"] is None
        assert built[index]["offplan_absorption_score"] is None
        assert built[index]["dld_investment_pipeline_score"] is None


def test_quality_flag_rules() -> None:
    low = _series(3, project_number_coverage_pct_28d=98.5)
    good = _series(3, project_number_coverage_pct_28d=99.0)
    none_coverage = _series(3, project_number_coverage_pct_28d=None)
    assert dld.build_rows(low)[0]["quality_flag"] == "low_project_coverage"
    assert dld.build_rows(good)[0]["quality_flag"] == "ok"
    assert dld.build_rows(none_coverage)[0]["quality_flag"] == "low_project_coverage"


# ---------------------------------------------------------------------------
# 入库映射 / 常量契约
# ---------------------------------------------------------------------------

def test_to_weekly_table_rows_filters_and_maps() -> None:
    # 负偏移在 2015-01-05 之前，正偏移在发布起点之后
    rows = _series(16, offset_start=-10)
    built = dld.build_rows(rows)
    mapped = dld.to_weekly_table_rows(built)
    expected_kept = [row for row in built if row["week_start"] >= dld.PUBLICATION_START]
    assert len(mapped) == len(expected_kept)
    assert mapped[0]["week_end"] == expected_kept[0]["week_end"]
    # 入库列名与库表设计完全对应
    assert set(mapped[0].keys()) == {
        "week_end",
        "confirmed_new_projects_28d",
        "offplan_sales_28d",
        "active_projects_28d",
        "project_launch_index",
        "offplan_absorption_index",
        "project_commercial_transition_index",
    }
    # 计数列是整数、指数列保留 6 位小数；早期周指数为 None
    assert isinstance(mapped[0]["confirmed_new_projects_28d"], int)
    assert mapped[0]["project_launch_index"] is None
    assert mapped[0]["offplan_absorption_index"] is None


def test_to_weekly_table_rows_drops_pre_publication_weeks() -> None:
    rows = _series(5, offset_start=-60)  # 全部早于 2015-01-05
    mapped = dld.to_weekly_table_rows(dld.build_rows(rows))
    assert mapped == []


def test_raw_weekly_sql_targets_unified_schema() -> None:
    assert dld.RAW_WEEKLY_SQL.count("dld.transactions") >= 6
    assert "FROM transactions" not in dld.RAW_WEEKLY_SQL
    assert "FROM dld.transactions" in dld.RAW_WEEKLY_SQL


def test_indicator_dictionary_contract() -> None:
    assert len(dld.INDICATOR_DICTIONARY) == 6
    assert [row[0] for row in dld.INDICATOR_DICTIONARY] == list(
        dld.WEEKLY_CSV_HEADERS[1:]
    )
    assert all(row[1] == "周" for row in dld.INDICATOR_DICTIONARY)
    assert all(row[3] == "Dubai Land Department" for row in dld.INDICATOR_DICTIONARY)
    assert all(row[5] == "房地产" for row in dld.INDICATOR_DICTIONARY)
    # 7 列表头与旧 ps1 的期望完全一致
    assert dld.WEEKLY_CSV_HEADERS == (
        "截止日期",
        "经确认新期房项目数_近28天",
        "期房销售笔数_近28天",
        "活跃期房项目数_近28天",
        "项目启动指数",
        "期房销售吸收指数",
        "项目商业转化指数",
    )


def test_column_dictionary_contract() -> None:
    assert len(dld.COLUMN_DICTIONARY) == 79
    assert all(len(row) == 7 for row in dld.COLUMN_DICTIONARY)
    object_names = {row[0] for row in dld.COLUMN_DICTIONARY}
    assert object_names == {"dld.transactions", "dld.land_registry"}


def test_column_dictionary_matches_legacy_metadata_rows() -> None:
    # 迁移旧库后，meta_column_dictionary 应包含与内置常量一致的行；
    # 此测试只做常量间的自洽检查（旧库内容在真实迁移验证中比对）
    by_object: dict[str, dict[str, tuple]] = {}
    for row in dld.COLUMN_DICTIONARY:
        by_object.setdefault(row[0], {})[row[1]] = row
    assert len(by_object["dld.transactions"]) == 47
    assert len(by_object["dld.land_registry"]) == 32
    assert by_object["dld.transactions"]["transaction_id"][2] == "VARCHAR"
    assert by_object["dld.land_registry"]["property_id"][2] == "BIGINT"