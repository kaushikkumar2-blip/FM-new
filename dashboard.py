import calendar
import os
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="FM Client / Hub",
    layout="wide",
    page_icon="📦",
    initial_sidebar_state="collapsed",
)

APP_DIR = Path(__file__).resolve().parent
BUNDLED_CSV = APP_DIR / "8a296c1ba2cacc19409c6fb7a2d79640.csv"


def default_csv_path() -> str:
    env = os.environ.get("FM_DASHBOARD_CSV", "").strip()
    if env and Path(env).is_file():
        return env
    if BUNDLED_CSV.is_file():
        return str(BUNDLED_CSV)
    return ""


def resolve_csv_path(user_path: str) -> Path | None:
    if user_path.strip():
        p = Path(user_path.strip())
        if p.is_file():
            return p
    env = os.environ.get("FM_DASHBOARD_CSV", "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p
    if BUNDLED_CSV.is_file():
        return BUNDLED_CSV
    return None

# Prefer e2e / query2 PU columns (final_ph_in_date_key logic), then ext L1 dashboard export
COHORT_DENOM = ("total_shipments", "cal_created_volume", "created_volume")
D0_COLS = ("d0_shipments", "cal_d0_picked", "created_d0_attempt", "created_bd_d0_picked")
D1_COLS = ("d1_shipments", "cal_d1_picked", "created_d1_attempt", "created_bd_d1_picked")
D2_COLS = ("d2_shipments", "cal_d2_plus_picked", "created_d1_plus_attempt", "created_bd_d2_plus_picked")
PENDING_COLS = ("pending_shipments", "cal_no_phin", "created_bd_no_phin")
PICKED_COLS = ("total_picked",)


def pick_col(df, *candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def normalize_export(df: pd.DataFrame) -> pd.DataFrame:
    if "merchant_code" in df.columns and "seller_type" not in df.columns:
        df["seller_type"] = df["merchant_code"]
    df["reporting_date"] = pd.to_datetime(df["reporting_date"], errors="coerce")
    num_like = [
        "total_shipments", "total_picked", "d0_shipments", "d1_shipments", "d2_shipments", "pending_shipments",
        "created_volume", "cal_created_volume",
        "cal_d0_picked", "cal_d1_picked", "cal_d2_plus_picked", "cal_no_phin",
        "created_bd_d0_picked", "created_bd_d1_picked", "created_bd_d2_plus_picked", "created_bd_no_phin",
        "created_d0_attempt", "created_d1_attempt", "created_d1_plus_attempt",
    ]
    for c in num_like:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    for c in ("pickup_hub_name", "pickup_hub_city", "pickup_hub_zone"):
        if c in df.columns:
            df[c] = df[c].fillna("Unknown")
    return df


@st.cache_data(show_spinner="Loading FDP export…")
def load_data(csv_path: str) -> pd.DataFrame:
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    return normalize_export(pd.read_csv(path, dtype=str))


def safe_pct(num, den):
    return np.where(den > 0, (num / den * 100).round(1), 0.0)


def daily_created_totals(df: pd.DataFrame, clients: list[str]) -> dict[date, float]:
    created_c = pick_col(df, *COHORT_DENOM)
    if not created_c:
        return {}
    sub = df[df["seller_type"].isin(clients)] if clients else df
    g = sub.groupby(sub["reporting_date"].dt.date)[created_c].sum()
    return {k: float(v) for k, v in g.items()}


def render_month_calendar(
    daily_map: dict[date, float],
    year: int,
    month: int,
    selected: date,
    in_range: set[date],
):
    st.markdown(f"**{date(year, month, 1).strftime('%B %Y')}** — click a day (numbers = created for selected clients)")
    header = st.columns(7)
    for i, label in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
        header[i].markdown(f"**{label}**")

    cal = calendar.Calendar(firstweekday=0)
    for week in cal.monthdayscalendar(year, month):
        cols = st.columns(7)
        for i, day_num in enumerate(week):
            if day_num == 0:
                cols[i].write("")
                continue
            d = date(year, month, day_num)
            vol = int(daily_map.get(d, 0))
            has_data = d in in_range
            label = f"{day_num}\n{vol:,}" if vol else str(day_num)
            btn_type = "primary" if d == selected else "secondary"
            disabled = not has_data
            if cols[i].button(
                label,
                key=f"cal_{year}_{month}_{day_num}",
                use_container_width=True,
                type=btn_type,
                disabled=disabled,
            ):
                st.session_state.sel_date = d
                st.rerun()


def build_metrics(df: pd.DataFrame) -> pd.DataFrame:
    created_c = pick_col(df, *COHORT_DENOM)
    d0_c, d1_c, d2_c, pend_c, picked_c = (
        pick_col(df, *D0_COLS),
        pick_col(df, *D1_COLS),
        pick_col(df, *D2_COLS),
        pick_col(df, *PENDING_COLS),
        pick_col(df, *PICKED_COLS),
    )
    if not created_c:
        return pd.DataFrame()

    out = df.copy()
    out["Created"] = out[created_c]
    out["D0 PH-in"] = out[d0_c] if d0_c else 0
    out["D1 PH-in"] = out[d1_c] if d1_c else 0
    out["D2+ PH-in"] = out[d2_c] if d2_c else 0
    if pend_c:
        out["Pending PH-in"] = out[pend_c]
    elif picked_c:
        out["Pending PH-in"] = out[created_c] - out[picked_c]
    else:
        out["Pending PH-in"] = 0
    return out


def agg_table(df: pd.DataFrame, keys: list[str], as_pct: bool) -> pd.DataFrame:
    measures = ["Created", "Pending PH-in", "D0 PH-in", "D1 PH-in", "D2+ PH-in"]
    t = df.groupby(keys, as_index=False)[measures].sum()
    if as_pct:
        t["D0 %"] = safe_pct(t["D0 PH-in"], t["Created"])
        t["D1 %"] = safe_pct(t["D1 PH-in"], t["Created"])
        t["D2+ %"] = safe_pct(t["D2+ PH-in"], t["Created"])
        t["Pending %"] = safe_pct(t["Pending PH-in"], t["Created"])
        show = keys + ["D0 %", "D1 %", "D2+ %", "Pending %", "Created"]
        return t[show].sort_values("Created", ascending=False)
    return t.sort_values("Created", ascending=False)


# ── Data ──────────────────────────────────────────────────────────
with st.expander("Data source", expanded=False):
    st.caption(
        "FDP: `QUERY_FM_PU_E2E.txt` (NL query2 PU). Cloud uses bundled CSV or upload; override with `FM_DASHBOARD_CSV`."
    )
    csv_path_input = st.text_input("CSV path (local / server)", value=default_csv_path())
    upload = st.file_uploader("Or upload FDP export (.csv)", type=["csv"])

if upload is not None:
    load_data.clear()
    raw = normalize_export(pd.read_csv(upload, dtype=str))
else:
    resolved = resolve_csv_path(csv_path_input)
    if resolved is None:
        st.error(
            "No CSV found. On Streamlit Cloud use the bundled file in the repo, upload a file above, "
            "or set secret/env `FM_DASHBOARD_CSV`."
        )
        st.stop()
    try:
        raw = load_data(str(resolved))
    except FileNotFoundError:
        st.error(f"File not found: {resolved}")
        st.stop()

if raw.empty or raw["reporting_date"].isna().all():
    st.error("No data — check CSV columns (need reporting_date, seller_type, metrics).")
    st.stop()

available_dates = sorted(raw["reporting_date"].dropna().dt.date.unique())
date_set = set(available_dates)
min_d, max_d = available_dates[0], available_dates[-1]

if "sel_date" not in st.session_state:
    st.session_state.sel_date = max_d
if "cal_year" not in st.session_state:
    st.session_state.cal_year = st.session_state.sel_date.year
if "cal_month" not in st.session_state:
    st.session_state.cal_month = st.session_state.sel_date.month

st.title("FM — client & hub pickup")

# ── Filters (main page) ─────────────────────────────────────────
clients = sorted(raw["seller_type"].dropna().unique())
f1, f2, f3 = st.columns([3, 2, 1])
with f1:
    sel_clients = st.multiselect(
        "Client(s)",
        clients,
        default=[c for c in ("FCY", "AIL") if c in clients] or list(clients[:1]),
    )
with f2:
    picked = st.date_input(
        "Date",
        value=st.session_state.sel_date,
        min_value=min_d,
        max_value=max_d,
        format="DD/MM/YYYY",
    )
    if picked != st.session_state.sel_date:
        st.session_state.sel_date = picked
        st.session_state.cal_year = picked.year
        st.session_state.cal_month = picked.month
with f3:
    show_pct = st.toggle("Show %", value=False)

sel_date = st.session_state.sel_date
daily_map = daily_created_totals(raw, sel_clients)

# ── Calendar ──────────────────────────────────────────────────────
nav_l, nav_m, nav_r = st.columns([1, 6, 1])
with nav_l:
    if st.button("◀ Prev month", use_container_width=True):
        m, y = st.session_state.cal_month, st.session_state.cal_year
        m -= 1
        if m < 1:
            m, y = 12, y - 1
        st.session_state.cal_month, st.session_state.cal_year = m, y
        st.rerun()
with nav_r:
    if st.button("Next month ▶", use_container_width=True):
        m, y = st.session_state.cal_month, st.session_state.cal_year
        m += 1
        if m > 12:
            m, y = 1, y + 1
        st.session_state.cal_month, st.session_state.cal_year = m, y
        st.rerun()

with nav_m:
    render_month_calendar(
        daily_map,
        st.session_state.cal_year,
        st.session_state.cal_month,
        sel_date,
        date_set,
    )

st.divider()

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
    "D0/D1/D2+ = query2 PU lag (final PH-in vs create on NL L1) · D0 % = d0_shipments / created"
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
