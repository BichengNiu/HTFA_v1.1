"""Standard GARCH / IGARCH process simulation.

Provides :func:`simulate_garch` and :func:`simulate_igarch` for generating
synthetic time series with time-varying conditional volatility.

For GJR-GARCH, EGARCH, and GARCH-M, see :mod:`._garch_ext`.
"""

from __future__ import annotations

from ._garch_core import (
    _to_list,
    _normalize_coef,
    _make_standard_variance_fn,
    _run_garch_simulation,
)
from ._garch_result import SimGARCHResult
from ._validation import validate_choice, validate_int, validate_real, validate_sample


def simulate_garch(
    n: int = 200,
    p: int = 1,
    q: int = 1,
    omega: float = 0.4,
    alpha: list[float] | None = None,
    beta: list[float] | None = None,
    mean_model: str = "constant",
    mean_ar: list[float] | None = None,
    mean_const: float = 0.0,
    dist: str = "normal",
    dist_params: dict | None = None,
    seed: int | None = None,
    burn: int = 100,
) -> SimGARCHResult:
    """Simulate a GARCH(p,q) time series.

    Handles both pure ARCH (q = 0) and GARCH (q >= 1) processes.

    The GARCH(p,q) model:
        y_t = mu_t + eps_t
        eps_t = sigma_t * u_t,    u_t ~ D(0,1)
        sigma2_t = omega + sum_{i=1}^{p} alpha_i * eps2_{t-i}
                  + sum_{j=1}^{q} beta_j * sigma2_{t-j}

    Parameters
    ----------
    n : int
        Number of observations to generate (after burn-in).
    p : int
        ARCH order.
    q : int
        GARCH order. Use ``q = 0`` for pure ARCH(p).
    omega : float
        Constant term in the variance equation (omega > 0).
    alpha : float or list of float, optional
        ARCH coefficients [alpha_1, ..., alpha_p].  A single float is
        automatically wrapped.  Defaults to ``[0.2] * p``.
    beta : float or list of float, optional
        GARCH coefficients [beta_1, ..., beta_q].  A single float is
        automatically wrapped.  Defaults to ``[0.5] * q``.
    mean_model : str
        Mean equation: ``"constant"``, ``"zero"``, or ``"ar"``.
    mean_ar : float or list of float, optional
        AR coefficients for the mean equation.  A single float is
        automatically wrapped.
    mean_const : float
        Constant term in the mean equation.
    dist : str
        Innovation distribution: ``"normal"`` or ``"t"``.
    dist_params : dict, optional
        Additional distribution parameters.
    seed : int, optional
        Random seed for reproducibility.
    burn : int
        Number of burn-in observations to discard.

    Returns
    -------
    SimGARCHResult
        Container with ``.data``, ``.residuals``, ``.conditional_volatility``,
        ``.params`` and methods ``.get_data()``, ``.get_params()``,
        ``.summary()``, ``.plot()``, ``.to_dataframe()``.
    """
    n, burn = validate_sample(n, burn)
    p = validate_int("p", p, minimum=1)
    q = validate_int("q", q, minimum=0)
    omega = validate_real("omega", omega, positive=True)
    validate_choice("mean_model", mean_model, ("constant", "zero", "ar"))
    validate_choice("dist", dist, ("normal", "t"))
    alpha = _normalize_coef(alpha, 0.2, p, name="alpha", nonnegative=True)
    beta = _normalize_coef(beta, 0.5, q, name="beta", nonnegative=True)
    mean_ar = _to_list(mean_ar)

    model_type = "ARCH" if q == 0 else "GARCH"

    return _run_garch_simulation(
        n=n,
        p=p,
        q=q,
        omega=omega,
        alpha=alpha,
        beta=beta,
        variance_fn=_make_standard_variance_fn(omega, alpha, beta, p, q),
        mean_model=mean_model,
        mean_const=mean_const,
        mean_ar=mean_ar,
        dist=dist,
        dist_params=dist_params,
        seed=seed,
        burn=burn,
        model_type=model_type,
    )


def simulate_igarch(
    n: int = 200,
    p: int = 1,
    q: int = 1,
    omega: float = 0.10,
    alpha: list[float] | None = None,
    beta: list[float] | None = None,
    mean_model: str = "constant",
    mean_const: float = 0.0,
    dist: str = "normal",
    dist_params: dict | None = None,
    seed: int | None = None,
    burn: int = 100,
) -> SimGARCHResult:
    """Simulate an IGARCH(p,q) time series with sum(alpha) + sum(beta) = 1.

    The IGARCH constraint is enforced by construction: the last beta
    coefficient is adjusted so that sum(alpha) + sum(beta) = 1.

    Parameters
    ----------
    n : int
        Number of observations to generate (after burn-in).
    p : int
        ARCH order (>= 1).
    q : int
        GARCH order (>= 1). IGARCH requires q >= 1.
    omega : float
        Constant term in the variance equation (omega > 0).
    alpha : float or list of float, optional
        ARCH coefficients. Defaults to ``[0.2] * p``.
    beta : float or list of float, optional
        GARCH coefficients. Defaults to ``[0.5] * q``.
        The last element is auto-adjusted to satisfy the IGARCH constraint.
    mean_model : str
        Mean equation: ``"constant"`` or ``"zero"``.
    mean_const : float
        Constant term in the mean equation.
    dist : str
        Innovation distribution: ``"normal"`` or ``"t"``.
    dist_params : dict, optional
        Additional distribution parameters.
    seed : int, optional
        Random seed for reproducibility.
    burn : int
        Number of burn-in observations to discard.

    Returns
    -------
    SimGARCHResult
    """
    n, burn = validate_sample(n, burn)
    p = validate_int("p", p, minimum=1)
    q = validate_int("q", q, minimum=1)
    omega = validate_real("omega", omega, positive=True)
    validate_choice("mean_model", mean_model, ("constant", "zero"))
    validate_choice("dist", dist, ("normal", "t"))

    alpha = _normalize_coef(alpha, 0.2, p, name="alpha", nonnegative=True)
    beta = _normalize_coef(beta, 0.5, q, name="beta", nonnegative=True)

    alpha_sum = sum(alpha)
    beta_free_sum = sum(beta[:-1]) if q > 1 else 0.0
    beta[-1] = 1.0 - alpha_sum - beta_free_sum

    if beta[-1] <= 0:
        raise ValueError(
            f"IGARCH constraint sum(alpha)+sum(beta)=1 cannot be satisfied: "
            f"sum(alpha)={alpha_sum:.4f}, "
            f"sum(beta[0:q-1])={beta_free_sum:.4f}, "
            f"derived beta[{q}]={beta[-1]:.4f} <= 0"
        )

    return _run_garch_simulation(
        n=n,
        p=p,
        q=q,
        omega=omega,
        alpha=alpha,
        beta=beta,
        variance_fn=_make_standard_variance_fn(omega, alpha, beta, p, q),
        mean_model=mean_model,
        mean_const=mean_const,
        mean_ar=[],
        dist=dist,
        dist_params=dist_params,
        seed=seed,
        burn=burn,
        model_type="IGARCH",
        extra_params={"igarch": True},
    )
