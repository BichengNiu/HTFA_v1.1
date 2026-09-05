# SARIMAX Preview Ts Options Expansion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the SARIMAX data-preview advanced options for the user-facing `Ts.TsPlots.plot_series` settings that apply to the current time-series preview.

**Architecture:** Keep the existing five tabs and extend them through the current path `widget controls → session state → build_chart_options → draw_series_plot → Ts.plot_series`. Every new control will have one state key, one normalized option, one Ts keyword, and a focused regression assertion. Data plumbing (`data`, `x`, `y`, `ax`) remains internal to the preview adapter.

**Tech Stack:** Python, Streamlit, Matplotlib, Ts.TsPlots, pytest.

---

## Proposed parameter placement

### 画布

- `sharex`: 分面共享 X 轴。
- Existing `figsize`, `facet`, `facet_rows`, `facet_cols`, `sharey` remain here.

### 标题

- `title_pad`: 标题与绘图区的间距。
- Existing title, X/Y title, title positions remain here.

### 坐标轴

- `max_ticks`: 自动 X 轴刻度上限。
- `auto_dual_y`: 自动多纵轴开关；与手动第二/第三纵轴互斥。
- `scale_ratio_threshold`: 自动轴分组的尺度比阈值。
- `max_y_axes`: 自动/手动纵轴总数上限。
- `axis_groups`: 可选文本映射，格式为 `变量=组名,变量=组名`，解析为 Ts mapping。
- `unit`: 主 Y 轴单位。
- `units`: 可选变量单位映射，格式为 `变量=单位,变量=单位`。
- Existing `ymin`, `xmin`, tick counts, `year_ruler`, `log_vars`, manual second/third axes remain here.

### 线条样式

- `colors`: 每个选中变量的颜色映射/选择。
- Existing line width, marker settings, grid settings remain here.

### 图例与图注

- `legend_labels`: 自定义图例标签，按选中变量顺序输入。
- `legend_bbox`: 图例锚点 X/Y；仅在显式图例位置时生效。
- `vline_linewidth`: 参考线宽度。
- Existing legend, title, note, vline, shade and value annotation settings remain here.

## Deliberate boundary requiring confirmation

- `data`, `x`, `y`, and `ax` are adapter internals, not user-facing advanced controls.
- `labels` is input-label plumbing; `legend_labels` is the appropriate user-facing control for this preview.
- `bar_series`, `bar_width`, `bar_edge_color`, `bar_edge_linewidth`, `bar_alpha`, and `bar_face_color` would change the current line preview into a mixed bar/line chart. They should remain out of this pass unless the user explicitly wants a bar/line mode added.

## Implementation tasks after scope confirmation

1. Add constants and parsing helpers for new enum, numeric, color, and mapping inputs.
2. Add controls to the five existing tabs with conditional visibility and help text.
3. Add widget keys and extend `build_chart_options` with normalized Ts keyword values and validation errors.
4. Extend `draw_series_plot` to forward every newly supported Ts keyword while preserving the existing fixed data/index handling.
5. Add tests for option defaults, mapping/alias normalization, invalid mapping input, exact Ts signature coverage, and AppTest rendering.
6. Run component tests, SARIMAX UI/boundary tests, and the static UI-to-Ts parameter consistency check.

## Validation commands

```powershell
D:\HTFA_v1.1\runtime\python.exe -B -m pytest -c D:\HTFA_v1.1\tooling\pytest.ini D:\HTFA_v1.1\tests\ui_shared\data_overview -q
D:\HTFA_v1.1\runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_ui_flow.py tests\models\test_sarimax_boundaries.py -q
```
