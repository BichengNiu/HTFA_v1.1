"""Base class for all simulation result containers in TsSims.

Provides :class:`BaseSimResult` — a common dataclass that defines the
uniform interface shared by :class:`SimSARIMAResult`, :class:`SimGARCHResult`,
and :class:`SimTSDSResult`.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class BaseSimResult:
    """Common result container for all TsSims simulation output.

    Subclasses override :meth:`summary` and :meth:`plot` to provide
    model-specific formatting and visualisation.

    Parameters
    ----------
    data : np.ndarray
        Generated time series of length *n*.
    residuals : np.ndarray
        Innovations (or residuals) used in generation.
    params : dict
        All parameters used for simulation.
    """

    data: np.ndarray
    residuals: np.ndarray
    params: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Concrete methods — shared across all simulation result types
    # ------------------------------------------------------------------

    def get_data(self) -> pd.Series | pd.DataFrame:
        """Return the generated time series.

        Returns a :class:`pd.Series` for univariate data or a
        :class:`pd.DataFrame` with columns ``"y0"``, ``"y1"``, ...
        for multivariate data.

        Returns
        -------
        pd.Series or pd.DataFrame
        """
        if self.data.ndim == 1:
            return pd.Series(self.data, name="y")
        cols = [f"y{i}" for i in range(self.data.shape[1])]
        return pd.DataFrame(self.data, columns=cols)

    def get_params(self) -> dict:
        """Return a deep copy of the simulation parameters.

        Returns
        -------
        dict
        """
        return copy.deepcopy(self.params)

    # ------------------------------------------------------------------
    # Override points — subclasses provide model-specific output
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """Return a formatted parameter summary string.

        Subclasses override this to include model-type headers and
        coefficient detail.

        Returns
        -------
        str
        """
        return f"{type(self).__name__}(n={len(self.data)})"

    def plot(self, title=None, **kwargs):
        """Plot the generated time series.

        Subclasses override this for model-specific visualisation (e.g.
        multi-panel volatility plots).

        Parameters
        ----------
        title : str, optional
            Chart title.
        **kwargs
            Forwarded to the underlying plotting function.

        Returns
        -------
        fig : matplotlib.figure.Figure
        ax : matplotlib.axes.Axes or numpy.ndarray of Axes
        """
        from Ts.TsPlots import plot_series

        if title is None:
            title = f"{type(self).__name__} Simulation"
        fig, ax = plot_series(
            self.data,
            title=title,
            ytitle="Value",
            xtitle="Time",
            show_legend=False,
            **kwargs,
        )
        return fig, ax
