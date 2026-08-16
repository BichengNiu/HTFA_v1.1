"""SARIMAX 单页工作流的四环节组件。"""

from dashboard.models.SARIMAX.ui.pages.sections.analysis_section import (
    render_analysis_section,
)
from dashboard.models.SARIMAX.ui.overview import render_data_overview_section
from dashboard.models.SARIMAX.ui.pages.sections.forecast_section import (
    render_forecast_section,
)
from dashboard.models.SARIMAX.ui.pages.sections.training_section import (
    render_training_section,
)

__all__ = [
    "render_analysis_section",
    "render_data_overview_section",
    "render_forecast_section",
    "render_training_section",
]
