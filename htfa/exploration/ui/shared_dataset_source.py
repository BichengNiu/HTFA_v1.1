"""Shared dataset source used by the univariate data overview page."""

from __future__ import annotations

import pandas as pd

from components.data_overview.core.file_parsing import load_dataframe
from htfa.app.state import shared_dataset


class SharedDatasetSource:
    """Expose the global shared dataset through the data overview protocol."""

    def __init__(self, *, uploader_enabled: bool = True) -> None:
        self.uploader_enabled = bool(uploader_enabled)

    def render_uploader(self, st_obj, *, compact: bool = False) -> dict:
        if not self.uploader_enabled:
            fingerprint = self.current_fingerprint()
            return {
                "has_data": bool(fingerprint),
                "file_name": self.current_name(),
            }
        return shared_dataset.render_shared_dataset_uploader(
            st_obj,
            compact=compact,
        )

    def current_data(self) -> pd.DataFrame | None:
        return shared_dataset.get_shared_dataset_data()

    def load_data(
        self,
        *,
        variable_name_row: int = 0,
        data_start_row: int = 1,
        time_column: str | None = None,
    ) -> pd.DataFrame | None:
        """Load the selected worksheet using the current overview settings."""
        uploaded_file = shared_dataset.get_shared_dataset_file()
        if uploaded_file is None:
            return None
        return load_dataframe(
            uploaded_file.getvalue(),
            uploaded_file.name,
            sheet_name=self.current_sheet(),
            variable_name_row=variable_name_row,
            data_start_row=data_start_row,
            time_column=time_column,
            raw_rows=shared_dataset.get_shared_dataset_raw_rows(),
        )

    def row_count(self) -> int:
        return shared_dataset.get_shared_dataset_row_count()

    def current_fingerprint(self) -> str:
        return shared_dataset.get_shared_dataset_fingerprint()

    def current_name(self) -> str:
        return shared_dataset.get_shared_dataset_name()

    def sheets(self) -> list[str] | None:
        return shared_dataset.get_shared_dataset_sheets()

    def current_sheet(self) -> str | None:
        return shared_dataset.get_shared_dataset_sheet()

    def select_sheet(self, sheet: str) -> None:
        shared_dataset.select_shared_dataset_sheet(sheet)


__all__ = ["SharedDatasetSource"]
