import os
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
SCHEMA_REV = 11
BUNDLED_CSV_NAMES = (
    "fm_nl_bundled_export.csv",
    "af502da717f8f1c350e1c4a91c56afaf.csv",
    "8a296c1ba2cacc19409c6fb7a2d79640.csv",
)


def find_bundled_csv() -> Path | None:
    for name in BUNDLED_CSV_NAMES:
        p = APP_DIR / name
        if p.is_file() and p.stat().st_size > 0:
            return p
    csvs = [p for p in APP_DIR.glob("*.csv") if p.stat().st_size > 1_000_000]
    return max(csvs, key=lambda p: p.stat().st_size) if csvs else None

COHORT_DENOM = ("total_shipments", "cal_created_volume", "created_volume", "fm_created")
D0_COLS = ("d0_shipments", "cal_d0_picked")
D1_COLS = ("d1_shipments", "cal_d1_picked")
D2_COLS = ("d2_shipments", "cal_d2_plus_picked")
PENDING_COLS = ("pending_shipments", "cal_no_phin")
PICKED_COLS = ("total_picked",)

NP_AGE_MAP = (
    ("np_age_1", "NP ≤1d"),
    ("np_age_2", "NP 2d"),
    ("np_age_3", "NP 3d"),
    ("np_age_4", "NP 4d"),
    ("np_age_5_plus", "NP 5d+"),
)

TEXT_DIMS = frozenset({
    "seller_type",
    "merchant_code",
    "payment_type",
    "pickup_hub_name",
    "pickup_hub_city",
    "pickup_hub_zone",
})


def default_csv_path() -> str:
    """Optional override path for the text box; bundled file is auto-detected."""
    env = os.environ.get("FM_DASHBOARD_CSV", "").strip()
    if env and Path(env).is_file():
        return env
    return ""


def resolve_csv_path(user_path: str) -> Path | None:
    env = os.environ.get("FM_DASHBOARD_CSV", "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p
    bundled = find_bundled_csv()
    if bundled:
        return bundled
    if user_path.strip():
        p = Path(user_path.strip())
        if p.is_file():
            return p
        rel = APP_DIR / user_path.strip()
        if rel.is_file():
            return rel
    return None


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
def load_data(csv_path: str, _schema_rev: int = SCHEMA_REV) -> pd.DataFrame:
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
    for src, label in NP_AGE_MAP:
        if src in out.columns:
            out[label] = as_numeric(out[src])
    return out


def measure_columns(df: pd.DataFrame) -> list[str]:
    base = ["Created", "Pending", "D0", "D1", "D2+"]
    age = [label for _, label in NP_AGE_MAP if label in df.columns]
    return base + age


def hub_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in ("pickup_hub_name", "pickup_hub_city", "pickup_hub_zone") if c in df.columns]


def agg_table(
    df: pd.DataFrame,
    keys: list[str],
    as_pct: bool,
    *,
    sort_by_period: bool = False,
) -> pd.DataFrame:
    measures = [m for m in measure_columns(df) if m in df.columns]
    t = df.groupby(keys, as_index=False)[measures].sum(numeric_only=True)
    if as_pct:
        t["D0 %"] = safe_pct(t["D0"], t["Created"])
        t["D1 %"] = safe_pct(t["D1"], t["Created"])
        t["D2+ %"] = safe_pct(t["D2+"], t["Created"])
        t["Pending %"] = safe_pct(t["Pending"], t["Created"])
        show = keys + ["D0 %", "D1 %", "D2+ %", "Pending %", "Created"]
        t = t[show]
    if sort_by_period:
        sort_cols = [keys[0]]
        if len(keys) > 1 and "Created" in t.columns:
            sort_cols.append("Created")
            return t.sort_values(sort_cols, ascending=[True, False])
        return t.sort_values(keys[0], ascending=True)
    return t.sort_values("Created", ascending=False)


def period_label(series: pd.Series, grain: str) -> pd.Series:
    if grain == "Day":
        return series.dt.strftime("%Y-%m-%d")
    if grain == "Week":
        monday = series - pd.to_timedelta(series.dt.dayofweek, unit="D")
        return monday.dt.strftime("%Y-%m-%d") + " (wk)"
    if grain == "Month":
        return series.dt.strftime("%Y-%m")
    raise ValueError(grain)


def load_raw_interactive() -> pd.DataFrame:
    with st.expander("Data source", expanded=False):
        st.caption(
            "NL externalisation FM pickup export (3-month create cohort). "
            "D0 % = cal_d0_picked / cal_created_volume (PH-in on create day or earlier). "
            "NP age buckets = not-picked ageing as of export run. Bundled CSV or `FM_DASHBOARD_CSV`."
        )
        bundled = find_bundled_csv()
        if bundled:
            st.caption(f"Bundled export: `{bundled.name}`")
        csv_path_input = st.text_input(
            "CSV path override (optional)",
            value=default_csv_path(),
            key=f"fm_csv_path_{SCHEMA_REV}",
        )
        upload = st.file_uploader("Or upload FDP export (.csv)", type=["csv"])

    if upload is not None:
        load_data.clear()
        raw = normalize_export(pd.read_csv(upload, dtype=str))
    else:
        resolved = resolve_csv_path(csv_path_input)
        if resolved is None:
            tried = ", ".join(BUNDLED_CSV_NAMES)
            st.error(
                f"No CSV found under `{APP_DIR}`. Expected one of: {tried}. "
                "Upload above, set `FM_DASHBOARD_CSV`, or redeploy with the bundled file."
            )
            st.stop()
        try:
            raw = load_data(str(resolved))
        except FileNotFoundError:
            st.error(f"File not found: {resolved}")
            st.stop()

    if raw.empty or raw["reporting_date"].isna().all():
        st.error("No data — need reporting_date, seller_type, and metric columns.")
        st.stop()
    return raw


def date_bounds(raw: pd.DataFrame) -> tuple[date, date]:
    available = sorted(raw["reporting_date"].dropna().dt.date.unique())
    return available[0], available[-1]
