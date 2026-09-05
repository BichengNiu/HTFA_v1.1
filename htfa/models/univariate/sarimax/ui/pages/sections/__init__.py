"""SARIMAX model page workflow section entry points."""

from __future__ import annotations

from htfa.models.univariate.sarimax.ui.pages.sections.analysis_section import (
    render_analysis_section,
)
from htfa.models.univariate.sarimax.ui.pages.sections.forecast_section import (
    render_forecast_section,
)
from htfa.models.univariate.sarimax.ui.pages.sections.training_section import (
    render_training_section,
)

__all__ = [
    "render_analysis_section",
    "render_forecast_section",
    "render_training_section",
]
