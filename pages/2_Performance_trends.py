import streamlit as st

from fm_metrics import agg_table, build_metrics, date_bounds, load_raw_interactive, period_label

st.title("FM — performance trends")

raw = load_raw_interactive()
min_d, max_d = date_bounds(raw)
clients = sorted(raw["seller_type"].dropna().unique())

st.subheader("1. Client")
client = st.selectbox(
    "Client",
    options=[None] + clients,
    format_func=lambda c: "Select a client…" if c is None else c,
    label_visibility="collapsed",
)
if client is None:
    st.info("Choose a client to unlock date range and performance table.")
    st.stop()

st.subheader("2. Range & granularity")
c1, c2, c3 = st.columns([2, 2, 1])
with c1:
    range_pick = st.date_input(
        "Date range",
        value=(min_d, max_d),
        min_value=min_d,
        max_value=max_d,
        format="DD/MM/YYYY",
    )
with c2:
    grain = st.radio(
        "Compare",
        options=["Day", "Week", "Month"],
        horizontal=True,
        help="Day-on-day, week-on-week (Mon start), or month-on-month rows.",
    )
with c3:
    show_pct = st.toggle("Show %", value=True)

if not isinstance(range_pick, tuple) or len(range_pick) != 2:
    st.warning("Select a full start and end date.")
    st.stop()

start_d, end_d = range_pick
if start_d > end_d:
    st.warning("Start date must be on or before end date.")
    st.stop()

load = st.button("Load performance", type="primary")
if not load:
    st.caption("Set options above, then click **Load performance**.")
    st.stop()

mask = (
    (raw["seller_type"] == client)
    & (raw["reporting_date"].dt.date >= start_d)
    & (raw["reporting_date"].dt.date <= end_d)
)
slice_df = raw.loc[mask]
enriched = build_metrics(slice_df)
if enriched.empty:
    st.warning("No rows for this client and date range.")
    st.stop()

enriched = enriched.copy()
enriched["Period"] = period_label(enriched["reporting_date"], grain)
tbl = agg_table(enriched, ["Period"], show_pct, sort_by_period=True)

st.subheader("3. Performance")
st.caption(
    f"**{client}** · {start_d.strftime('%d %b %Y')} – {end_d.strftime('%d %b %Y')} · "
    f"**{grain}** view · D0 = same-day PH-in"
)
st.dataframe(tbl, use_container_width=True, hide_index=True)
