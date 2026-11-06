"""Local temporary artifact lifecycle for historical exports."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path


def export_directory() -> Path:
    path = Path(tempfile.gettempdir()) / "oil-field-map-exports"
    path.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.now(timezone.utc).timestamp() - 6 * 3600
    for artifact in path.glob("portwatch-*.zip"):
        try:
            if artifact.stat().st_mtime < cutoff:
                artifact.unlink()
        except OSError:
            pass
    return path
