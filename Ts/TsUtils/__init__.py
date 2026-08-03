"""Time-series preprocessing utilities.

The package owns decomposition and data-cleaning helpers that prepare series
for modelling without estimating predictive models.
"""

from ._difference import difference
from ._interpolation import InterpolationResult, interpolate_missing
from ._stl import STL, STLResult
from ._summary import TimeSeriesSummary

__all__ = [
    "STL",
    "InterpolationResult",
    "STLResult",
    "TimeSeriesSummary",
    "difference",
    "interpolate_missing",
]
