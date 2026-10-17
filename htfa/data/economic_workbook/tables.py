"""Table sources that share the economic workbook validation contract."""

from abc import ABC, abstractmethod
from collections.abc import Callable

import pandas as pd


class EconomicTableSource(ABC):
    """A named, versioned source of economic tables, without Excel I/O."""

    name: str

    @abstractmethod
    def open(self):
        """Return a context manager yielding a TableWorkbook."""


class TableWorkbook:
    """Expose named raw tables through the reader's existing parse contract."""

    def __init__(
        self, sheet_names: list[str], read_sheet: Callable[[str], pd.DataFrame]
    ):
        self.sheet_names = sheet_names
        self._read_sheet = read_sheet

    def parse(self, sheet_name: str, *, header: int | None = 0) -> pd.DataFrame:
        """Read a raw table or promote its selected row to column headings."""
        if sheet_name not in self.sheet_names:
            raise ValueError(f"Missing economic table: {sheet_name}")
        raw = self._read_sheet(sheet_name)
        if header is None:
            return raw.copy()
        if not isinstance(header, int) or header < 0 or header >= len(raw):
            raise ValueError(f"Invalid table header: {header}")
        result = raw.iloc[header + 1:].copy().reset_index(drop=True)
        result.columns = raw.iloc[header].tolist()
        return result
