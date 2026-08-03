"""Small, shared validators for simulation public APIs."""

from __future__ import annotations

from collections.abc import Iterable
from numbers import Integral, Real

import numpy as np


def validate_int(name: str, value: object, *, minimum: int) -> int:
    """Return *value* as an int after enforcing an inclusive lower bound."""
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer, got {type(value).__name__}")
    result = int(value)
    if result < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {result}")
    return result


def validate_real(
    name: str,
    value: object,
    *,
    positive: bool = False,
    nonnegative: bool = False,
) -> float:
    """Return a finite float and optionally enforce its sign."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number, got {type(value).__name__}")
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"{name} must be finite, got {result}")
    if positive and result <= 0:
        raise ValueError(f"{name} must be > 0, got {result}")
    if nonnegative and result < 0:
        raise ValueError(f"{name} must be >= 0, got {result}")
    return result


def validate_choice(name: str, value: object, choices: tuple[str, ...]) -> str:
    """Return a string that is one of *choices*."""
    if not isinstance(value, str) or value not in choices:
        allowed = ", ".join(repr(choice) for choice in choices)
        raise ValueError(f"{name} must be one of {allowed}, got {value!r}")
    return value


def validate_sample(n: object, burn: object = 0) -> tuple[int, int]:
    """Validate requested and burn-in sample sizes."""
    return (
        validate_int("n", n, minimum=1),
        validate_int("burn", burn, minimum=0),
    )


def validate_order(name: str, value: object, *, length: int) -> tuple[int, ...]:
    """Validate a fixed-length tuple of nonnegative integer model orders."""
    if not isinstance(value, tuple) or len(value) != length:
        raise ValueError(f"{name} must be a tuple of length {length}, got {value!r}")
    return tuple(
        validate_int(f"{name}[{index}]", item, minimum=0)
        for index, item in enumerate(value)
    )


def normalize_coefficients(
    name: str,
    value: Real | Iterable[Real] | None,
    *,
    length: int | None = None,
    default: float | None = None,
    nonnegative: bool = False,
) -> list[float]:
    """Normalize scalar/iterable coefficients and validate shape and values."""
    if value is None:
        values = [] if length is None or default is None else [default] * length
    elif isinstance(value, bool):
        raise TypeError(f"{name} coefficients must be real numbers")
    elif isinstance(value, Real):
        values = [float(value)]
    else:
        try:
            values = list(value)
        except TypeError as exc:
            raise TypeError(f"{name} must be a real number or iterable") from exc

    if length is not None and len(values) != length:
        raise ValueError(
            f"{name} must contain exactly {length} coefficient(s), got {len(values)}"
        )

    return [
        validate_real(f"{name}[{index}]", item, nonnegative=nonnegative)
        for index, item in enumerate(values)
    ]
