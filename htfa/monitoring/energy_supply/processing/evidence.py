"""Review documents scoped to a single explicit catalog build."""

from contextlib import contextmanager
from contextvars import ContextVar

from htfa.monitoring.energy_supply.data.storage import read_json as _read_json

_DOCUMENTS = ContextVar("energy_review_documents", default=None)


@contextmanager
def evidence_scope():
    token = _DOCUMENTS.set({})
    try:
        yield
    finally:
        _DOCUMENTS.reset(token)


def read_json(path):
    documents = _DOCUMENTS.get()
    if documents is None:
        return _read_json(path)
    if path not in documents:
        documents[path] = _read_json(path)
    return documents[path]
