import streamlit as st

from fm_metrics import agg_table, build_metrics, date_bounds, hub_columns, period_label, render_kpi_row


def render_daily_page(raw) -> None:
    min_d, max_d = date_bounds(raw)
    clients = sorted(raw["seller_type"].dropna().unique())
    top1, top2, top3 = st.columns([4, 2, 1], vertical_alignment="bottom")
    with top1:
        all_clients = st.checkbox("All clients", value=False)
    with top2:
        sel_date = st.date_input(
            "Date",
            value=max_d,
            min_value=min_d,
            max_value=max_d,
            format="DD/MM/YYYY",
        )
    with top3:
        show_pct = st.toggle("Show %", value=False)

    if all_clients:
        sel_clients = list(clients)
    else:
        sel_clients = st.multiselect(
            "Client(s)",
            clients,
            default=[c for c in ("FCY", "AIL") if c in clients] or list(clients[:1]),
        )

    day = raw[raw["reporting_date"].dt.date == sel_date]
    if sel_clients:
        day = day[day["seller_type"].isin(sel_clients)]

    enriched = build_metrics(day)
    if enriched.empty:
        st.warning("No rows for this date / client filter.")
        return

    client_label = (
        f"All ({len(sel_clients)})"
        if len(sel_clients) == len(clients)
        else ", ".join(sel_clients)
    )
    st.caption(
        f"**Selected:** {sel_date.strftime('%d %b %Y')} · **Clients:** {client_label} · "
        "D0 = PH-in on create day or earlier · **Pending** = no PH-in and no MH-in"
    )
    render_kpi_row(enriched)

    st.subheader("By client")
    client_tbl = agg_table(enriched, ["seller_type"], show_pct)
    st.dataframe(
        client_tbl.rename(columns={"seller_type": "Client"}),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("By hub")
    hub_keys = [
        k
        for k in ("pickup_hub_name", "pickup_hub_city", "pickup_hub_zone", "seller_type")
        if k in enriched.columns
    ]
    hub_tbl = agg_table(enriched, hub_keys, show_pct)
    st.dataframe(
        hub_tbl.rename(
            columns={
                "pickup_hub_name": "Hub",
                "pickup_hub_city": "City",
                "pickup_hub_zone": "Zone",
                "seller_type": "Client",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


def render_trends_page(raw) -> None:
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
        return

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
        return

    start_d, end_d = range_pick
    if start_d > end_d:
        st.warning("Start date must be on or before end date.")
        return

    if not st.button("Load performance", type="primary"):
        st.caption("Set options above, then click **Load performance**.")
        return

    mask = (
        (raw["seller_type"] == client)
        & (raw["reporting_date"].dt.date >= start_d)
        & (raw["reporting_date"].dt.date <= end_d)
    )
    slice_df = raw.loc[mask]
    enriched = build_metrics(slice_df)
    if enriched.empty:
        st.warning("No rows for this client and date range.")
        return

    enriched = enriched.copy()
    enriched["Period"] = period_label(enriched["reporting_date"], grain)
    st.caption(
        f"**{client}** · {start_d.strftime('%d %b %Y')} – {end_d.strftime('%d %b %Y')} · **{grain}**"
    )
    render_kpi_row(enriched)

    st.subheader("3. Client total")
    tbl = agg_table(enriched, ["Period"], show_pct, sort_by_period=True)
    st.dataframe(tbl, use_container_width=True, hide_index=True)

    hubs = hub_columns(enriched)
    if not hubs:
        st.info("No hub columns in this export.")
        return

    st.divider()
    st.subheader("4. Hub breakdown")
    hub_view = st.radio(
        "Hub view",
        options=["By hub over time", "Client total only"],
        horizontal=True,
        index=0,
    )
    if hub_view == "Client total only":
        return

    hub_labels = enriched["pickup_hub_name"].fillna("Unknown") + " · " + enriched["pickup_hub_city"].fillna("")
    hub_options = sorted(hub_labels.unique())
    picked_hubs = st.multiselect("Hubs (empty = all)", options=hub_options, default=[])
    hub_df = enriched
    if picked_hubs:
        hub_df = enriched[hub_labels.isin(picked_hubs)]

    hub_keys = ["Period"] + hubs
    hub_tbl = agg_table(hub_df, hub_keys, show_pct, sort_by_period=True)
    st.dataframe(
        hub_tbl.rename(
            columns={
                "pickup_hub_name": "Hub",
                "pickup_hub_city": "City",
                "pickup_hub_zone": "Zone",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
