"""Executable dependency and import-safety contracts for the energy layers."""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

from tooling.source_tree import python_sources

PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT / "htfa/monitoring/energy_supply"
PREFIX = "htfa.monitoring.energy_supply"


def _imports(path):
    package = ".".join(path.relative_to(PROJECT).parts[:-1])
    modules = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = importlib.util.resolve_name("." * node.level + module, package)
            modules.add(module)
            modules.update(module + "." + alias.name for alias in node.names)
    return modules


def test_energy_dependencies_only_point_down_the_three_layers():
    forbidden = {
        "data": (PREFIX + ".processing", PREFIX + ".ui", "htfa.monitoring.uae.jobs", "htfa.monitoring.energy_supply.jobs", "streamlit"),
        "processing": (
            "htfa.monitoring.uae.jobs",
            "htfa.monitoring.energy_supply.jobs",
            PREFIX + ".ui",
            "streamlit",
            "duckdb",
            "requests",
            "urllib.request",
            "Ts",
            "matplotlib",
        ),
        "ui": (PREFIX + ".data", "duckdb", "requests", "urllib.request", "htfa.monitoring.uae.jobs", "htfa.monitoring.energy_supply.jobs"),
        "contracts": (
            "htfa.monitoring.uae.jobs",
            "htfa.monitoring.energy_supply.jobs",
            PREFIX + ".data",
            PREFIX + ".processing",
            PREFIX + ".ui",
            "streamlit",
        ),
    }
    for layer, banned in forbidden.items():
        for path in python_sources((ROOT / layer)):
            for module in _imports(path):
                assert not any(
                    module == name or module.startswith(name + ".") for name in banned
                ), (path, module)
            if layer in {"processing", "ui"}:
                tree = ast.parse(path.read_text(encoding="utf-8"))
                assert not any(
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"execute", "executemany", "urlopen"}
                    for node in ast.walk(tree)
                ), path


def test_energy_layers_have_no_import_cycles():
    sources = {
        ".".join(path.relative_to(PROJECT).with_suffix("").parts): path
        for path in python_sources(ROOT)
        if path.name != "__init__.py" and "jobs" not in path.relative_to(ROOT).parts
    }
    visited, active = set(), set()

    def visit(module):
        assert module not in active, module
        if module in visited:
            return
        active.add(module)
        for dependency in _imports(sources[module]) & sources.keys():
            visit(dependency)
        active.remove(module)
        visited.add(module)

    for module in sources:
        visit(module)


def test_energy_imports_do_not_access_a_database_or_network():
    modules = sorted(
        ".".join(path.relative_to(PROJECT).with_suffix("").parts)
        for path in python_sources(ROOT)
        if path.name != "__init__.py" and "jobs" not in path.relative_to(ROOT).parts
    )
    script = f"""
import importlib
import sys
from unittest.mock import patch
import duckdb
import requests
from urllib import request
def forbidden(*args, **kwargs):
    raise AssertionError('Database/network access during module import')
with patch.object(duckdb, 'connect', forbidden), patch.object(request, 'urlopen', forbidden), patch.object(requests, 'get', forbidden):
    for module in {modules!r}:
        importlib.import_module(module)
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=PROJECT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_energy_callers_have_no_old_flat_imports():
    for folder in (PROJECT / "htfa", PROJECT / "tests", PROJECT / "scripts"):
        for path in python_sources(folder):
            for module in _imports(path):
                if module.startswith(PREFIX + "."):
                    layer = module[len(PREFIX) + 1 :].split(".")[0]
                    assert layer in {"contracts", "data", "processing", "ui", "jobs"}, (
                        path,
                        module,
                    )
