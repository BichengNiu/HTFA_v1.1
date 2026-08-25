"""Shared fixtures for UAE analysis tests."""

from collections.abc import Generator

import matplotlib.pyplot as plt
import pytest


@pytest.fixture(autouse=True)
def close_matplotlib_figures() -> Generator[None, None, None]:
    """Close figures after each test so chart tests do not leak pyplot state."""

    yield
    plt.close("all")
