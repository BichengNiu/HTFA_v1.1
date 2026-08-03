"""GARCH-family model estimation entry point.

Provides :class:`GARCH` — the public API for GARCH / GJR-GARCH / EGARCH
estimation via the ``arch`` library.
"""

from __future__ import annotations

from Ts.TsModels._garch_base import _BaseVolModel


class GARCH(_BaseVolModel):
    """GARCH / GJR-GARCH / EGARCH model estimation.

    Handles pure ARCH (q = 0), GARCH (q >= 1), GJR-GARCH (o >= 1), and
    EGARCH (vol = "EGARCH") volatility models, with optional GARCH-M
    (ARCH-in-mean) and exogenous regressors.

    Parameters
    ----------
    data : array-like
        Time series data (1-D).
    p : int
        ARCH order (>= 1).
    q : int
        GARCH order (>= 0).  Use ``q = 0`` for pure ARCH(p).
    o : int
        Asymmetric (GJR) order (>= 0).  Use ``o >= 1`` for GJR-GARCH(p,o,q)
        or asymmetric EGARCH(p,o,q).  When ``o = 0`` (default), the model
        is symmetric.
    vol : str
        Volatility model type: ``"GARCH"`` (default, covers ARCH/GARCH/
        GJR-GARCH) or ``"EGARCH"`` (Exponential GARCH).
    mean : str
        Mean model: ``"Constant"``, ``"Zero"``, ``"AR"``, etc.
    dist : str
        Innovation distribution: ``"normal"``, ``"t"``, ``"skewt"``, ``"ged"``.
    garch_m : bool
        Enable GARCH-in-Mean. When ``True``, conditional volatility enters
        the mean equation. Not supported with vol="EGARCH".
    garch_m_form : str
        Form of conditional variance in the mean equation: ``"vol"`` (sigma_t),
        ``"var"`` (sigma2_t), or ``"log"`` (log sigma2_t). Default ``"vol"``.
    ar_lags : int or list, optional
        AR lags for the mean equation (only effective with ``garch_m=True``).
    exog : array-like, optional
        Exogenous regressors for the mean equation, shape (nobs,) or
        (nobs, k).
    igarch : bool
        IGARCH constraint estimation (``sum(alpha)+sum(beta)=1``).
        Not supported with vol="EGARCH" or garch_m=True.
    compare_lags : bool
        For pure ARCH models with ``p > 1``, fit lower-order ARCH models to
        report their AIC/BIC values. Default ``True``.
    dates : datetime-like sequence, optional
        Strict sample dates. A Series DatetimeIndex is inferred automatically.
        Array inputs may provide dates explicitly.
    missing : {"raise", "drop"}
        Joint non-finite policy for data and exog. ``"drop"`` records removed
        zero-based rows in :attr:`dropped_positions`. Default ``"raise"``.
    """

    def __init__(
        self,
        data,
        p=1,
        q=1,
        o=0,
        vol="GARCH",
        mean="Constant",
        dist="normal",
        garch_m=False,
        garch_m_form="vol",
        ar_lags=None,
        exog=None,
        dates=None,
        igarch=False,
        compare_lags=True,
        missing="raise",
    ):
        super().__init__(
            data=data,
            p=p,
            q=q,
            o=o,
            vol=vol,
            mean=mean,
            dist=dist,
            garch_m=garch_m,
            garch_m_form=garch_m_form,
            ar_lags=ar_lags,
            exog=exog,
            dates=dates,
            igarch=igarch,
            compare_lags=compare_lags,
            missing=missing,
        )
