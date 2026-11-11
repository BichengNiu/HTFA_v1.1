"""全项目三层架构的可执行约束。"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

from tooling.source_tree import python_sources

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'htfa'


def imports(path):
    package = '.'.join(path.relative_to(ROOT).parts[:-1])
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            name = node.module or ''
            if node.level:
                name = importlib.util.resolve_name('.' * node.level + name, package)
            yield name


def test_foundation_processing_and_contracts_have_no_presentation_dependency():
    for path in python_sources(PACKAGE):
        parts = path.relative_to(PACKAGE).parts
        if parts[0] in {'jobs', 'app', 'ui_shared'} or 'ui' in parts:
            continue
        if not {'data', 'processing', 'contracts'}.intersection(parts):
            continue
        for name in imports(path):
            assert not name.startswith(('streamlit', 'matplotlib', 'plotly', 'htfa.ui_shared', 'htfa.app')), (path, name)
            assert '.ui.' not in name and not name.endswith('.ui'), (path, name)
            assert not name.startswith('Ts.TsPlots'), (path, name)
            if 'processing' in parts:
                assert not name.startswith(('duckdb', 'sqlite3', 'requests', 'urllib.request')), (path, name)
            if 'contracts' in parts or ('data' in parts and 'processing' not in parts):
                assert '.processing' not in name, (path, name)


def test_processing_does_not_execute_storage_or_transport_operations():
    forbidden = {'read_excel', 'read_csv', 'ExcelWriter', 'to_excel', 'to_csv', 'executemany', 'urlopen'}
    for path in python_sources(PACKAGE):
        if 'processing' not in path.relative_to(PACKAGE).parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if not isinstance(node, ast.Call):
                continue
            assert not (isinstance(node.func, ast.Name) and node.func.id == 'open'), path
            assert not (isinstance(node.func, ast.Attribute) and node.func.attr in forbidden), (path, ast.unparse(node.func))


def test_migrated_domains_do_not_keep_legacy_package_implementations():
    retired = [
        'htfa/preview/data/economic_workbook/shared',
        'htfa/preview/data/economic_workbook/core',
        'htfa/preview/data/economic_workbook/domain',
        'htfa/preview/data/economic_workbook/modules',
        'htfa/monitoring/industrial/utils',
        'htfa/monitoring/industrial/charts',
        'htfa/exploration/core',
        'htfa/exploration/analysis',
        'htfa/exploration/metrics',
        'htfa/exploration/preprocessing',
        'htfa/models/univariate/sarimax/core',
    ]
    retired.extend('htfa/models/dfm/' + name for name in ['prep', 'train', 'decomp', 'results', 'utils'])
    for relative in retired:
        assert not list(python_sources((ROOT / relative))), relative


def test_internal_imports_resolve_to_existing_source_modules():
    """Deleted facades must not leave broken imports inside page functions."""
    modules = {
        '.'.join(path.relative_to(ROOT).with_suffix('').parts).removesuffix('.__init__')
        for path in python_sources(PACKAGE)
    }
    for path in python_sources(PACKAGE):
        for name in imports(path):
            if name.startswith('htfa.'):
                assert name in modules, (path, name)
