"""Excel COM 写表脚本共享的 PowerShell 调用基础设施。"""

from __future__ import annotations

import json
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

_POWERSHELL_BASE = (
    "powershell.exe",
    "-NoProfile",
    "-NonInteractive",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
)


def records_latest_first(observations: Iterable) -> list[dict[str, object]]:
    """按 period 倒序序列化观测记录。"""

    return [
        {
            "period": observation.period,
            "values": [
                None if value is None else float(value)
                for value in observation.values
            ],
        }
        for observation in sorted(
            observations,
            key=lambda item: item.period,
            reverse=True,
        )
    ]


@contextmanager
def payload_json_file(
    payload: dict[str, Any],
    *,
    prefix: str,
    directory: Path,
) -> Iterator[Path]:
    """创建临时 payload JSON 并在退出时删除。"""

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            prefix=prefix,
            suffix=".json",
            dir=directory,
            encoding="utf-8",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, ensure_ascii=True)
        yield temporary_path
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def run_powershell_sheet_writer(
    helper_path: Path,
    workbook_path: Path,
    payload_path: Path,
    sheet_name: str,
) -> None:
    """调用 PowerShell 写表助手并统一处理失败消息。"""

    completed = subprocess.run(
        _POWERSHELL_BASE
        + (
            str(helper_path),
            "-WorkbookPath",
            str(workbook_path),
            "-DataPath",
            str(payload_path),
            "-SheetName",
            sheet_name,
        ),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode:
        message = (completed.stderr or "").strip() or (
            completed.stdout or ""
        ).strip()
        raise RuntimeError(f"Excel sheet update failed: {message}")
