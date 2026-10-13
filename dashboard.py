import os
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

# D0 = PH-in date equals create date (NL: shipment_received_at_origin_date_key = shipment_created_at_date_key)
COHORT_DENOM = ("total_shipments", "cal_created_volume", "created_volume", "fm_created")
D0_COLS = ("d0_shipments", "cal_d0_picked")
D1_COLS = ("d1_shipments", "cal_d1_picked")
D2_COLS = ("d2_shipments", "cal_d2_plus_picked")
PENDING_COLS = ("pending_shipments", "cal_no_phin")
PICKED_COLS = ("total_picked",)

# Columns kept as text; everything else in the export is coerced to numeric for sums.
TEXT_DIMS = frozenset({
    "seller_type",
    "merchant_code",
    "payment_type",
    "pickup_hub_name",
    "pickup_hub_city",
    "pickup_hub_zone",
})


def pick_col(df, *candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def as_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0)


def normalize_export(df: pd.DataFrame) -> pd.DataFrame:
    if "merchant_code" in df.columns and "seller_type" not in df.columns:
        df["seller_type"] = df["merchant_code"]
    df["reporting_date"] = pd.to_datetime(df["reporting_date"], errors="coerce")
    for c in df.columns:
        if c in TEXT_DIMS or c == "reporting_date":
            continue
        df[c] = as_numeric(df[c])
    for c in ("pickup_hub_name", "pickup_hub_city", "pickup_hub_zone"):
        if c in df.columns:
            df[c] = df[c].fillna("Unknown")
    return df


@st.cache_data(show_spinner="Loading FDP export…")
def load_data(csv_path: str, _schema_rev: int = 7) -> pd.DataFrame:
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    return normalize_export(pd.read_csv(path, dtype=str))


def safe_pct(num, den):
    return np.where(den > 0, (num / den * 100).round(1), 0.0)


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
    created = as_numeric(out[created_c])
    out["Created"] = created
    out["D0"] = as_numeric(out[d0_c]) if d0_c else 0
    out["D1"] = as_numeric(out[d1_c]) if d1_c else 0
    out["D2+"] = as_numeric(out[d2_c]) if d2_c else 0
    if pend_c:
        out["Pending"] = as_numeric(out[pend_c])
    elif picked_c:
        out["Pending"] = created - as_numeric(out[picked_c])
    else:
        out["Pending"] = 0
    return out


def agg_table(df: pd.DataFrame, keys: list[str], as_pct: bool) -> pd.DataFrame:
    measures = ["Created", "Pending", "D0", "D1", "D2+"]
    t = df.groupby(keys, as_index=False)[measures].sum(numeric_only=True)
    if as_pct:
        t["D0 %"] = safe_pct(t["D0"], t["Created"])
        t["D1 %"] = safe_pct(t["D1"], t["Created"])
        t["D2+ %"] = safe_pct(t["D2+"], t["Created"])
        t["Pending %"] = safe_pct(t["Pending"], t["Created"])
        show = keys + ["D0 %", "D1 %", "D2+ %", "Pending %", "Created"]
        return t[show].sort_values("Created", ascending=False)
    return t.sort_values("Created", ascending=False)


# ── Data ──────────────────────────────────────────────────────────
with st.expander("Data source", expanded=False):
    st.caption(
        "FDP: `QUERY_FM_PU_E2E.txt` — D0 when PH-in date = create date. Bundled CSV or upload; env `FM_DASHBOARD_CSV`."
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
min_d, max_d = available_dates[0], available_dates[-1]

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
