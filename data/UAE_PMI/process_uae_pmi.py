"""Run UAE PMI validation and workbook processing from this data folder."""

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.data_sources.uae_pmi.process_uae_pmi import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
