import numpy as np
import pandas as pd

from dashboard.explore.ui.result_presenters import (
    encode_csv_with_bom,
    format_dtw_results,
    prepare_dtw_display,
    prepare_lead_lag_display,
)


def test_dtw_results_are_normalized_sorted_and_arrow_safe():
    params = {
        "enable_window_constraint": True,
        "radius": 4,
    }
    backend_results = [
        {"对比变量": "far", "DTW距离": 10.0},
        {"对比变量": "near", "DTW距离": 2.0},
        {"对比变量": "failed", "DTW距离": np.nan},
    ]
    paths = {
        "far": {"path": [(0, 0), (1, 1)]},
        "near": {"path": [(0, 0), (1, 1), (2, 2), (3, 3)]},
    }

    formatted = format_dtw_results(backend_results, paths, params)
    display, valid = prepare_dtw_display(formatted)

    assert formatted[0]["标准化DTW距离"] == 5.0
    assert formatted[1]["标准化DTW距离"] == 0.5
    assert display["变量名"].tolist() == ["near", "far", "failed"]
    assert valid["变量名"].tolist() == ["near", "far"]
    assert all(
        str(display[column].dtype) == "object"
        for column in ["DTW距离", "对齐路径长度", "标准化DTW距离"]
    )


def test_dtw_distance_without_path_preserves_existing_partial_result_contract():
    formatted = format_dtw_results(
        [{"对比变量": "candidate", "DTW距离": 3.0}],
        {},
        {"enable_window_constraint": False, "radius": None},
    )

    assert formatted == [
        {
            "变量名": "candidate",
            "窗口约束": "禁用",
            "Radius": "N/A",
            "DTW距离": 3.0,
            "对齐路径长度": "N/A",
            "标准化DTW距离": "Error",
            "分析状态": "计算成功",
        }
    ]


def test_lead_lag_display_removes_internal_objects_and_sorts_nan_last():
    results = pd.DataFrame(
        [
            {
                "target_variable": "target",
                "candidate_variable": "late",
                "k_kl": 2,
                "kl_at_k_kl": np.nan,
                "full_kl_divergence_df": pd.DataFrame(),
                "notes": "",
            },
            {
                "target_variable": "target",
                "candidate_variable": "early",
                "k_kl": -1,
                "kl_at_k_kl": 1.23456,
                "full_kl_divergence_df": pd.DataFrame(),
                "notes": "",
            },
        ]
    )

    display = prepare_lead_lag_display(results)

    assert "full_kl_divergence_df" not in display.columns
    assert display["候选变量"].tolist() == ["early", "late"]
    assert display.loc[0, "最小KL散度"] == 1.2346


def test_csv_export_contains_exactly_one_utf8_bom():
    payload = encode_csv_with_bom(pd.DataFrame({"变量": ["指标"]}))
    bom = b"\xef\xbb\xbf"

    assert payload.startswith(bom)
    assert not payload[len(bom):].startswith(bom)
    assert "指标" in payload.decode("utf-8-sig")
