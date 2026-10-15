import streamlit as st

from fm_metrics import load_raw_interactive
from fm_views import render_daily_page, render_trends_page

st.set_page_config(
    page_title="FM NL Pickup",
    layout="wide",
    page_icon="📦",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        section[data-testid="stSidebar"] { display: none; }
        button[kind="headerNoPadding"] { display: none; }
        [data-testid="collapsedControl"] { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("FM — NL first-mile pickup")

view = st.radio(
    "View",
    options=["Client & hub (daily)", "Performance trends"],
    horizontal=True,
    label_visibility="collapsed",
)

raw = load_raw_interactive()
st.divider()

if view == "Client & hub (daily)":
    render_daily_page(raw)
else:
    render_trends_page(raw)
