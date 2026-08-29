"""Shared helpers for UAE analysis tests."""


def data_lines(axis):
    """Return labelled data lines and exclude Matplotlib placeholder lines."""

    return [
        line
        for line in axis.get_lines()
        if line.get_label() and not line.get_label().startswith("_")
    ]
