"""Light/dark theme for the Streamlit UI, switched by a toggle pinned bottom-left.

Streamlit's theme is a server-wide setting, so switching it at runtime would change
it for every open session. Instead the base theme is pinned to light
(.streamlit/config.toml) and, when the viewer turns dark mode on, a dark stylesheet
is injected into their session only. The choice is mirrored in the URL
(?theme=dark), so a page refresh keeps it.
"""
from __future__ import annotations

import streamlit as st

# Pins the toggle to the bottom-left corner of the window. It lives in the main area
# (not inside the sidebar), so it stays visible when the sidebar is collapsed.
TOGGLE_CSS = """
<style>
.st-key-theme_toggle_box {
    position: fixed; left: 1rem; bottom: 1rem; z-index: 1000000;
    width: auto !important; padding: 0.35rem 0.8rem 0.35rem 0.6rem;
    border-radius: 999px; border: 1px solid rgba(128,128,128,0.35);
    background: var(--theme-toggle-bg, #ffffff); box-shadow: 0 2px 10px rgba(0,0,0,0.15);
}
.st-key-theme_toggle_box label p { font-size: 0.85rem; white-space: nowrap; }
</style>
"""

# The dark palette. Plain class/attribute selectors so Streamlit's inline colours
# (e.g. :green[...] text) still win where they are set explicitly.
DARK_CSS = """
<style>
:root { --bg: #0e1117; --bg-2: #161b26; --bg-3: #1f2533; --fg: #e6e9ef; --fg-2: #a3acbd;
        --line: #2d3446; --theme-toggle-bg: #1f2533; }
.stApp, [data-testid="stHeader"], [data-testid="stBottomBlockContainer"], [data-testid="stBottom"] > div {
    background: var(--bg) !important; color: var(--fg); }
[data-testid="stSidebar"], [data-testid="stSidebarContent"] { background: var(--bg-2) !important; }
.stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5,
.stApp small, .stApp summary, [data-testid="stMetricValue"], [data-testid="stMetricLabel"] p,
[data-testid="stWidgetLabel"] p, [data-testid="stText"], .stApp [data-testid="stMarkdownContainer"] {
    color: var(--fg); }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p,
[data-testid="stMetricDelta"] { color: var(--fg-2) !important; }

/* inputs, selects, text areas, date and number inputs */
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"],
[data-baseweb="select"] > div, [data-testid="stNumberInputContainer"],
[data-testid$="RootElement"], [data-testid="stDateInputField"] {
    background: var(--bg-3) !important; border-color: var(--line) !important; box-shadow: none !important; }
[data-testid="stDateInputField"] input { border: none !important; }
[data-testid="stDateInputField"] svg { color: var(--fg-2); fill: var(--fg-2); }
[data-testid="stMetricDelta"] { background: var(--bg-3) !important; color: var(--fg-2) !important; }
[data-testid="stMetricDelta"] svg { fill: var(--fg-2); }
.stApp input, .stApp textarea { background: var(--bg-3) !important; color: var(--fg) !important;
    -webkit-text-fill-color: var(--fg) !important; caret-color: var(--fg); }
.stApp input::placeholder, .stApp textarea::placeholder { color: var(--fg-2) !important;
    -webkit-text-fill-color: var(--fg-2) !important; }
[data-baseweb="select"] span, [data-baseweb="select"] svg, [data-testid="stNumberInput"] button {
    color: var(--fg) !important; fill: var(--fg); }
[data-testid="stNumberInput"] button { background: var(--bg-3) !important; }
[data-baseweb="popover"] ul, [data-baseweb="popover"] li, [data-baseweb="menu"],
[data-baseweb="calendar"], [data-baseweb="calendar"] * { background: var(--bg-3) !important; color: var(--fg) !important; }
[data-baseweb="popover"] li:hover { background: var(--line) !important; }

/* buttons (primary keeps the accent colour) */
.stButton button[kind="secondary"], .stFormSubmitButton button[kind="secondaryFormSubmit"],
.stDownloadButton button { background: var(--bg-3); color: var(--fg); border-color: var(--line); }
.stButton button[kind="secondary"]:hover { border-color: #ff4b4b; color: #ff4b4b; }
.stButton button:disabled { background: var(--bg-2) !important; color: var(--fg-2) !important; }

/* containers: forms, expanders and status boxes, tabs, code, chat */
[data-testid="stForm"], [data-testid="stExpander"] details, [data-testid="stChatMessage"] {
    background: var(--bg-2); border-color: var(--line) !important; }
[data-testid="stExpander"] summary:hover p { color: #ff4b4b; }
button[data-baseweb="tab"] { background: transparent !important; }
button[data-baseweb="tab"] p { color: var(--fg-2); }
button[data-baseweb="tab"][aria-selected="true"] p { color: var(--fg); }
[data-baseweb="tab-border"] { background: var(--line) !important; }
[data-testid="stCode"] pre, .stApp pre, .stApp code { background: var(--bg-3) !important; color: var(--fg) !important; }
[data-testid="stChatInput"], [data-testid="stChatInput"] > div { background: var(--bg-3) !important;
    border-color: var(--line) !important; }
.stApp hr { border-color: var(--line) !important; }
[data-testid="stText"] span { color: var(--fg) !important; }

/* alerts: tinted dark backgrounds with light, kind-coloured text */
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) { background: rgba(59,130,246,0.16) !important; }
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) { background: rgba(34,197,94,0.16) !important; }
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) { background: rgba(234,179,8,0.16) !important; }
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) { background: rgba(239,68,68,0.18) !important; }
[data-testid="stAlertContentInfo"] p, [data-testid="stAlertContentInfo"] code { color: #a9c8ff !important; }
[data-testid="stAlertContentSuccess"] p, [data-testid="stAlertContentSuccess"] code { color: #8ee6a8 !important; }
[data-testid="stAlertContentWarning"] p, [data-testid="stAlertContentWarning"] code { color: #f5d77a !important; }
[data-testid="stAlertContentError"] p, [data-testid="stAlertContentError"] code { color: #ffaaaa !important; }
[data-testid="stToast"] { background: var(--bg-3) !important; color: var(--fg) !important; }

/* dataframes are drawn on a canvas, so CSS colours cannot reach the cells: invert them
   and rotate the hue back so accent colours stay recognisable */
[data-testid="stDataFrame"] { filter: invert(0.9) hue-rotate(180deg); }
</style>
"""


def _sync_url() -> None:
    if st.session_state.dark_mode:
        st.query_params["theme"] = "dark"
    elif "theme" in st.query_params:
        del st.query_params["theme"]


def render_theme_toggle() -> bool:
    """Draw the bottom-left toggle and apply the chosen theme. Returns True in dark mode."""
    if "dark_mode" not in st.session_state:
        st.session_state.dark_mode = st.query_params.get("theme") == "dark"
    st.markdown(TOGGLE_CSS, unsafe_allow_html=True)
    with st.container(key="theme_toggle_box"):
        st.toggle("🌙 Dark mode", key="dark_mode", on_change=_sync_url)
    if st.session_state.dark_mode:
        st.markdown(DARK_CSS, unsafe_allow_html=True)
    return st.session_state.dark_mode
