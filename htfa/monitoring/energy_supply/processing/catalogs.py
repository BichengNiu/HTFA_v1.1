"""Catalog enrichment and published snapshot identity services."""

from htfa.monitoring.energy_supply.data import storage
from htfa.monitoring.energy_supply.processing.entity_names import enrich_catalog
from htfa.monitoring.energy_supply.processing.port_metadata import apply_port_metadata


def load_catalog(kind):
    rows = storage.load_catalog(kind)
    return apply_port_metadata(rows) if kind == "ports" else rows


def save_catalog(kind, rows, key="portid"):
    if kind in {"assets", "ports", "chokepoints"}:
        rows = enrich_catalog(
            kind, rows, storage.read_json("data/bilingual_names.json")
        )
    if kind == "ports":
        rows = apply_port_metadata(rows)
    storage.save_catalog(kind, rows, key)


def cached_catalog(kind, max_age_seconds=86400, allow_stale=False):
    rows = storage.cached_catalog(kind, max_age_seconds, allow_stale)
    return apply_port_metadata(rows) if kind == "ports" and rows is not None else rows


def snapshot_identity():
    """Database and all persisted families identify a published view."""
    versions = storage.revisions(("ports", "chokepoints", "ais", "sea", "assets"))
    return (*storage.database_identity(), *versions.values())


def database_path():
    return storage.database_path()


def revisions(kinds):
    return storage.revisions(kinds)


def read_only():
    return storage.read_only()


def backup_bytes():
    return storage.backup_bytes()
