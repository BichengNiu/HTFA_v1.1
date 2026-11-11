"""Maintenance jobs are owned by their business and never invoked by pages."""
import ast
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

from htfa.monitoring.uae.jobs.paths import PROJECT_ROOT, PACKAGE_DIR
from tooling.source_tree import python_sources

ROOT = Path(__file__).resolve().parents[2]
BUSINESSES = ('uae', 'energy_supply')


def test_jobs_have_business_owners_and_no_top_level_entry():
    assert not (ROOT / 'htfa/jobs').exists()
    assert importlib.util.find_spec('htfa.jobs') is None
    assert PROJECT_ROOT == ROOT
    assert PACKAGE_DIR == ROOT / 'htfa/monitoring/uae/jobs'
    for business in BUSINESSES:
        assert (ROOT / 'htfa/monitoring' / business / 'jobs/__init__.py').is_file()
    for path in python_sources(ROOT / 'htfa'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            modules = [node.module or ''] if isinstance(node, ast.ImportFrom) else (
                [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
            )
            assert not any(m == 'htfa.jobs' or m.startswith('htfa.jobs.') for m in modules), path


def test_update_launchers_resolve_the_repository_root():
    for name in ('update_data', 'merge_workbook'):
        batch = PACKAGE_DIR / (name + '.bat')
        assert (batch.parent / '../../../..').resolve() == ROOT
        text = batch.read_text(encoding='utf-8-sig')
        assert '%~dp0..\\..\\..\\..' in text
        assert '-m htfa.monitoring.uae.jobs.' + name in text


def test_job_imports_do_not_connect_to_database_or_network():
    modules = []
    for business in BUSINESSES:
        for path in python_sources(ROOT / 'htfa/monitoring' / business / 'jobs'):
            if path.name != '__init__.py':
                modules.append('.'.join(path.relative_to(ROOT).with_suffix('').parts))
    code = f'''
import importlib
from unittest.mock import patch
import duckdb
import requests
from urllib import request

def forbidden(*args, **kwargs):
    raise AssertionError('Maintenance import attempted database/network I/O')
with patch.object(duckdb, 'connect', forbidden), patch.object(requests.sessions.Session, 'request', forbidden), patch.object(request, 'urlopen', forbidden):
    for name in {sorted(modules)!r}:
        importlib.import_module(name)
'''
    result = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT,
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('module', [
    'htfa.monitoring.uae.jobs.update_data',
    'htfa.monitoring.uae.jobs.merge_workbook',
    'htfa.monitoring.uae.jobs.daily_refresh',
    'htfa.monitoring.energy_supply.jobs.publish',
])
def test_business_command_entrypoints_accept_help(module):
    result = subprocess.run([sys.executable, '-B', '-m', module, '--help'], cwd=ROOT,
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert result.returncode == 0, result.stderr
    assert 'usage:' in result.stdout


def test_customs_downloader_can_run_from_raw_working_directory(tmp_path):
    script = PACKAGE_DIR / 'download_dubai_customs_air.py'
    tree = ast.parse(script.read_text(encoding='utf-8'))
    assert not any(isinstance(node, ast.ImportFrom) and (node.module or '').startswith('htfa.')
                   for node in ast.walk(tree))
    result = subprocess.run([sys.executable, '-B', str(script), '--help'], cwd=tmp_path,
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert result.returncode == 0, result.stderr


def test_runtime_does_not_import_maintenance_jobs():
    maintenance = ('htfa.monitoring.uae.jobs', 'htfa.monitoring.energy_supply.jobs')
    for path in python_sources(ROOT / 'htfa'):
        if 'jobs' in path.relative_to(ROOT / 'htfa').parts:
            continue
        package = '.'.join(path.relative_to(ROOT).parts[:-1])
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                if node.level:
                    module = importlib.util.resolve_name('.' * node.level + module, package)
                modules = [module, *(module + '.' + alias.name for alias in node.names)]
            else:
                continue
            assert not any(module == prefix or module.startswith(prefix + '.')
                           for module in modules for prefix in maintenance), path
