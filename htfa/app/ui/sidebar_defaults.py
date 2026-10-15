"""Apply the sidebar opening policy once per browser document."""

from pathlib import Path

import streamlit as st


def initialize_sidebar_visibility() -> None:
    """Close a restored sidebar on page load, preserving later user toggles.

    Streamlit 1.64 restores localStorage before applying initial_sidebar_state.
    Use its own collapse button so the layout and persisted state stay in sync.
    A browser flag, rather than session_state, also covers a full page refresh.
    """
    st.sidebar.html(
        Path(__file__).parent / "static" / "sidebar_defaults.html",
        unsafe_allow_javascript=True,
        width="content",
    )
