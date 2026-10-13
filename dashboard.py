import streamlit as st

from fm_metrics import agg_table, build_metrics, date_bounds, load_raw_interactive

st.set_page_config(
    page_title="FM Client / Hub",
    layout="wide",
    page_icon="📦",
    initial_sidebar_state="collapsed",
)

raw = load_raw_interactive()
min_d, max_d = date_bounds(raw)

st.title("FM — client & hub pickup")

clients = sorted(raw["seller_type"].dropna().unique())
f1, f2, f3 = st.columns([3, 2, 1])
with f1:
    sel_clients = st.multiselect(
        "Client(s)",
        clients,
        default=[c for c in ("FCY", "AIL") if c in clients] or list(clients[:1]),
    )
with f2:
    sel_date = st.date_input(
        "Date",
        value=max_d,
        min_value=min_d,
        max_value=max_d,
        format="DD/MM/YYYY",
    )
with f3:
    show_pct = st.toggle("Show %", value=False)

day = raw[raw["reporting_date"].dt.date == sel_date]
if sel_clients:
    day = day[day["seller_type"].isin(sel_clients)]

enriched = build_metrics(day)
if enriched.empty:
    st.warning("No rows for this date / client filter.")
    st.stop()

st.caption(
    f"**Selected:** {sel_date.strftime('%d %b %Y')} · "
    f"**Clients:** {', '.join(sel_clients)} · "
    "D0 = PH-in on same day as create · D1/D2+ = PH-in lag +1 / +2 days"
)

st.subheader("By client")
client_tbl = agg_table(enriched, ["seller_type"], show_pct)
st.dataframe(client_tbl.rename(columns={"seller_type": "Client"}), use_container_width=True, hide_index=True)

st.subheader("By hub")
hub_keys = [k for k in ("pickup_hub_name", "pickup_hub_city", "pickup_hub_zone", "seller_type") if k in enriched.columns]
hub_tbl = agg_table(enriched, hub_keys, show_pct)
st.dataframe(
    hub_tbl.rename(columns={
        "pickup_hub_name": "Hub",
        "pickup_hub_city": "City",
        "pickup_hub_zone": "Zone",
        "seller_type": "Client",
    }),
    use_container_width=True,
    hide_index=True,
)
