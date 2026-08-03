"""Critical value tables and interpolation for structural break unit root tests.

Sources
-------
- Perron (1989) Table IV.B — finite-sample critical values
- Zivot & Andrews (1992) Table 2 — asymptotic critical values
"""

from __future__ import annotations

import numpy as np
from scipy import interpolate

from ._utils import _validate_model

# ---------------------------------------------------------------------------
# Perron (1989) Table IV.B — finite-sample critical values
# ---------------------------------------------------------------------------

# Model A (intercept break)
_PERRON_MODEL_INTERCEPT_CRIT = {
    50: {0.01: -4.32, 0.025: -4.02, 0.05: -3.76, 0.10: -3.46},
    100: {0.01: -4.14, 0.025: -3.87, 0.05: -3.65, 0.10: -3.38},
    200: {0.01: -4.07, 0.025: -3.82, 0.05: -3.60, 0.10: -3.34},
    np.inf: {0.01: -4.00, 0.025: -3.77, 0.05: -3.56, 0.10: -3.31},
}

# Model B (slope/trend break)
_PERRON_MODEL_SLOPE_CRIT = {
    50: {0.01: -4.08, 0.025: -3.79, 0.05: -3.55, 0.10: -3.27},
    100: {0.01: -3.93, 0.025: -3.68, 0.05: -3.47, 0.10: -3.20},
    200: {0.01: -3.88, 0.025: -3.62, 0.05: -3.41, 0.10: -3.16},
    np.inf: {0.01: -3.81, 0.025: -3.56, 0.05: -3.36, 0.10: -3.12},
}

# Model C (both intercept and slope break)
_PERRON_MODEL_BOTH_CRIT = {
    50: {0.01: -4.90, 0.025: -4.58, 0.05: -4.33, 0.10: -4.00},
    100: {0.01: -4.68, 0.025: -4.40, 0.05: -4.17, 0.10: -3.87},
    200: {0.01: -4.59, 0.025: -4.32, 0.05: -4.10, 0.10: -3.81},
    np.inf: {0.01: -4.51, 0.025: -4.25, 0.05: -4.04, 0.10: -3.76},
}

_PERRON_CRIT_MAP = {
    "intercept": _PERRON_MODEL_INTERCEPT_CRIT,
    "slope": _PERRON_MODEL_SLOPE_CRIT,
    "both": _PERRON_MODEL_BOTH_CRIT,
}

# ---------------------------------------------------------------------------
# Zivot & Andrews (1992) Table 2 — asymptotic critical values
# ---------------------------------------------------------------------------

# Model A (intercept)
_ZA_MODEL_INTERCEPT_CRIT = {
    0.01: -5.34,
    0.025: -5.04,
    0.05: -4.80,
    0.10: -4.58,
}

# Model B (trend/slope)
_ZA_MODEL_SLOPE_CRIT = {
    0.01: -4.93,
    0.025: -4.67,
    0.05: -4.42,
    0.10: -4.11,
}

# Model C (both)
_ZA_MODEL_BOTH_CRIT = {
    0.01: -5.57,
    0.025: -5.30,
    0.05: -5.08,
    0.10: -4.82,
}

_ZA_CRIT_MAP = {
    "intercept": _ZA_MODEL_INTERCEPT_CRIT,
    "slope": _ZA_MODEL_SLOPE_CRIT,
    "both": _ZA_MODEL_BOTH_CRIT,
}


# ---------------------------------------------------------------------------
# Interpolation helpers
# ---------------------------------------------------------------------------


def _interpolate_crit(crit_dict: dict, T: int) -> dict[float, float]:
    """Linearly interpolate critical values for sample size *T*.

    Parameters
    ----------
    crit_dict : dict
        Keys are sample sizes (int or np.inf), values are dicts mapping
        significance levels to critical values.
    T : int
        Actual sample size.

    Returns
    -------
    dict[float, float]
        Interpolated critical values for each significance level.
    """
    sizes = sorted(k for k in crit_dict if k != np.inf)
    if sizes[0] >= T:
        return crit_dict[sizes[0]]
    if sizes[-1] < T:
        # Use asymptotic (inf) values if available, otherwise largest table entry
        if np.inf in crit_dict:
            return crit_dict[np.inf]
        return crit_dict[sizes[-1]]

    levels = list(crit_dict[sizes[0]].keys())
    result = {}
    for lev in levels:
        x = np.array(sizes, dtype=float)
        y = np.array([crit_dict[s][lev] for s in sizes], dtype=float)
        f = interpolate.interp1d(x, y, kind="linear", fill_value="extrapolate")
        result[lev] = float(f(T))
    return result


def _perron_crit(model: str, T: int, significance: float) -> float:
    """Return the Perron (1989) critical value for a given model, sample
    size, and significance level.

    Raises
    ------
    KeyError
        If *model* is not one of ``"intercept"``, ``"slope"``, or ``"both"``.
    """
    crit_dict = _PERRON_CRIT_MAP[model]
    interp = _interpolate_crit(crit_dict, T)
    sigs = sorted(interp.keys())
    idx = np.searchsorted(sigs, significance, side="right") - 1
    idx = max(0, min(idx, len(sigs) - 1))
    return interp[sigs[idx]]


def _za_crit(model: str, significance: float) -> float:
    """Return the Zivot-Andrews (1992) asymptotic critical value.

    Raises
    ------
    ValueError
        If *model* is not one of ``"intercept"``, ``"slope"``, or ``"both"``.
    """
    _validate_model(model)
    return _ZA_CRIT_MAP[model][significance]
