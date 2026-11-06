"""Environment and Streamlit secret resolution for presentation adapters."""

import os

import streamlit as st


def sea_history_config():
    config = {}
    for key in (
        "SEA_HISTORY_ARCHIVE_PATH",
        "SEA_HISTORY_BUNDLE_PATH",
        "SEA_HISTORY_BUNDLE_URL",
        "SEA_HISTORY_BEARER_TOKEN",
        "SEA_HISTORY_IMPORT_TOKEN",
    ):
        try:
            secret = st.secrets.get(key)
        except Exception:
            secret = None
        config[key] = str(secret or os.environ.get(key) or "").strip()
    return config
