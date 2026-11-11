"""The UAE publication pair has one module-owned location."""
from pathlib import Path
import os
import subprocess
import sys

from htfa.monitoring.uae.contracts.paths import ASSETS_DIR, ASSETS_RELATIVE_PATH
from htfa.monitoring.uae.data.database import DEFAULT_DATABASE
from htfa.monitoring.energy_supply.data.storage import DB_PATH as ENERGY_DATABASE
from htfa.jobs.uae_data.paths import DATA_DIR, DB_PATH, WORKBOOK_PATH
from tooling.source_tree import python_sources

ROOT = Path(__file__).resolve().parents[1]


def test_publication_readers_and_jobs_share_the_module_assets():
    assert ASSETS_DIR == ROOT / ASSETS_RELATIVE_PATH
    assert ASSETS_RELATIVE_PATH == Path('htfa/monitoring/uae/assets')
    assert DEFAULT_DATABASE == ENERGY_DATABASE == ASSETS_DIR / 'uae.duckdb'
    if not os.environ.get('HTFA_UAE_DATA_DIR'):
        assert DATA_DIR == ASSETS_DIR
        assert DB_PATH == DEFAULT_DATABASE
        assert WORKBOOK_PATH == ASSETS_DIR / '\u963f\u8054\u914b.xlsx'


def test_worker_override_does_not_repoint_the_publication_reader(tmp_path):
    env = {**os.environ, 'HTFA_UAE_DATA_DIR': str(tmp_path)}
    code = (
        'from pathlib import Path; '
        'from htfa.jobs.uae_data.paths import DATA_DIR; '
        'from htfa.monitoring.uae.data.database import DEFAULT_DATABASE; '
        f'assert DATA_DIR == Path({str(tmp_path)!r}); '
        f'assert DEFAULT_DATABASE == Path({str(DEFAULT_DATABASE)!r})'
    )
    subprocess.run([sys.executable, '-B', '-c', code], env=env, cwd=ROOT, check=True)


def test_source_discovery_prunes_local_asset_code(tmp_path):
    domain = tmp_path / 'uae'
    source = domain / 'data/reader.py'
    evidence = domain / 'assets/raw/sample.py'
    source.parent.mkdir(parents=True)
    evidence.parent.mkdir(parents=True)
    source.write_text('value = 1', encoding='utf-8')
    evidence.write_text('not application Python', encoding='utf-8')
    assert list(python_sources(domain)) == [source]
