"""Streamlit caching keyed by the complete published snapshot identity."""

import hashlib
import marshal
from functools import wraps

import streamlit as st

from htfa.monitoring.energy_supply.processing.catalogs import snapshot_identity


def snapshot_cache(**options):
    def decorate(function):
        version = hashlib.sha256(marshal.dumps(function.__code__)).hexdigest()

        def evaluate(identity, service_version, *args, **kwargs):
            return function(*args, **kwargs)

        # Streamlit identifies functions by module, qualified name and source.
        # Each adapter must own its cache even when the callable arguments match.
        evaluate.__module__ = function.__module__
        evaluate.__qualname__ = function.__qualname__ + "__snapshot_cache"
        cached = st.cache_data(show_spinner=False, **options)(evaluate)

        @wraps(function)
        def invoke(*args, **kwargs):
            return cached(snapshot_identity(), version, *args, **kwargs)

        invoke.clear = cached.clear
        return invoke

    return decorate
