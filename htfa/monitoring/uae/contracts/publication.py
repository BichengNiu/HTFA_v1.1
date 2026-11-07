from dataclasses import dataclass


@dataclass(frozen=True)
class PublishedUAEData:
    """A small, hashable reference to one validated database publication."""

    path: str
    version: str
    published_at: str
    name: str = "uae.duckdb"
