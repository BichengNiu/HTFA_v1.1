"""Shared dataset source used by the univariate data overview page."""

from __future__ import annotations

import pandas as pd

from htfa.data.tabular import TabularFileSnapshot, build_dataframe_from_rows
from htfa.app.state import shared_dataset


class SharedDatasetSource:
    """Expose the global shared dataset through the data overview protocol."""

    def __init__(self, *, uploader_enabled: bool = True) -> None:
        self.uploader_enabled = bool(uploader_enabled)

    def render_uploader(self, st_obj, *, compact: bool = False) -> dict:
        if not self.uploader_enabled:
            snapshot = self.snapshot()
            return {
                "has_data": snapshot is not None,
                "file_name": snapshot.file_name if snapshot else "",
            }
        return shared_dataset.render_shared_dataset_uploader(
            st_obj,
            compact=compact,
        )

    def snapshot(self) -> TabularFileSnapshot | None:
        return shared_dataset.get_shared_dataset_snapshot()

    def load_data(
        self,
        *,
        variable_name_row: int = 0,
        data_start_row: int = 1,
        time_column: str | None = None,
    ) -> pd.DataFrame | None:
        """Load the selected worksheet using the current overview settings."""
        snapshot = self.snapshot()
        if snapshot is None:
            return None
        return build_dataframe_from_rows(
            snapshot.raw_rows,
            variable_name_row=variable_name_row,
            data_start_row=data_start_row,
            time_column=time_column,
        )

    def select_sheet(self, sheet: str) -> None:
        shared_dataset.select_shared_dataset_sheet(sheet)


__all__ = ["SharedDatasetSource"]
