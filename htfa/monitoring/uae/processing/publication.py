"""Publication discovery for the read-only report use case."""

from htfa.monitoring.uae.data import database


def published_source(database_path=None):
    """Resolve the current validated report publication."""
    return database.published_source(database_path)
