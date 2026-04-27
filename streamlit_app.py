from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from untapped import create_state_map, create_us_state_map, normalize_country, normalize_state

DEFAULT_DATA_PATH = Path("my_beers.csv")
REQUIRED_COLUMNS = [
    "Beer Name",
    "Producer",
    "Location",
    "Beer Type",
    "My Rating",
    "Global Rating",
    "First Date",
    "Recent Date",
]


def load_beer_history(source):
    df = pd.read_csv(source)
    if "Producer" not in df.columns and "Location" in df.columns:
        # Backward compatibility for older exports where Location held the producer name.
        df["Producer"] = df["Location"]
        df["Location"] = None
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    df["My Rating"] = pd.to_numeric(df["My Rating"], errors="coerce")
    df["Global Rating"] = pd.to_numeric(df["Global Rating"], errors="coerce")
    df["First Date"] = pd.to_datetime(df["First Date"], errors="coerce")
    df["Recent Date"] = pd.to_datetime(df["Recent Date"], errors="coerce")
    return df


def extract_country_name_from_location(value):
    if pd.isna(value):
        return None

    parts = [part.strip() for part in str(value).split(",") if part.strip()]
    candidates = []
    if parts:
        candidates.extend(reversed(parts))
    candidates.append(str(value).strip())

    for candidate in candidates:
        country_name = normalize_country(candidate)
        if country_name:
            return country_name
        state_code = normalize_state(candidate)
        if state_code:
            return "United States"
    return None


def build_beer_location_map(df):
    df_map = df.copy()
    df_map["country_name"] = df_map["Location"].map(extract_country_name_from_location)
    df_map["state_code"] = df_map["Location"].map(extract_state_code_from_location)
    df_map["checkin_date"] = df_map["Recent Date"].fillna(df_map["First Date"])
    df_map["place_name"] = df_map["Location"].fillna("Unknown")
    return df_map


def extract_state_code_from_location(value):
    if pd.isna(value):
        return None

    parts = [part.strip() for part in str(value).split(",") if part.strip()]
    candidates = []
    if parts:
        candidates.extend(reversed(parts))
    candidates.append(str(value).strip())

    for candidate in candidates:
        state_code = normalize_state(candidate)
        if state_code:
            return state_code
    return None


st.set_page_config(page_title="Untappd Beer History", layout="wide")

st.title("Untappd Beer History")
st.markdown("Review your exported beer list, ratings, styles, and recent activity.")

st.sidebar.header("Beer Data")
source_mode = st.sidebar.radio("Source", ["Use my_beers.csv", "Upload CSV"])
show_map = st.sidebar.checkbox("Show drink-location map", value=True)
map_view = st.sidebar.radio("Map View", ["Global", "US States"], index=0) if show_map else None

df = None
error_message = None
map_chart = None
map_message = None

if source_mode == "Use my_beers.csv":
    if DEFAULT_DATA_PATH.exists():
        try:
            df = load_beer_history(DEFAULT_DATA_PATH)
            st.sidebar.success(f"Loaded {len(df)} rows from {DEFAULT_DATA_PATH.name}")
        except Exception as exc:
            error_message = str(exc)
    else:
        st.sidebar.info("Run `python run.py` first to create `my_beers.csv`.")
else:
    uploaded_file = st.sidebar.file_uploader("Upload beer history CSV", type=["csv"])
    if uploaded_file is not None:
        try:
            df = load_beer_history(uploaded_file)
            st.sidebar.success(f"Loaded {len(df)} rows from uploaded file")
        except Exception as exc:
            error_message = str(exc)

if show_map:
    try:
        if df is not None and not df.empty:
            df_map = build_beer_location_map(df)
            if map_view == "US States":
                map_chart = create_us_state_map(df_map)
                if map_chart is None:
                    map_message = "The `Location` values in `my_beers.csv` did not contain enough U.S. state information to build the U.S. map."
            else:
                map_chart = create_state_map(df_map)
                if map_chart is None:
                    map_message = "The `Location` values in `my_beers.csv` did not contain enough country information to build the global map."
    except Exception as exc:
        map_message = f"Could not build map from `my_beers.csv`: {exc}"

if error_message:
    st.error(error_message)

if df is not None and not df.empty:
    beer_type_options = sorted(value for value in df["Beer Type"].dropna().unique() if str(value).strip())
    producer_options = sorted(value for value in df["Producer"].dropna().unique() if str(value).strip())
    location_options = sorted(value for value in df["Location"].dropna().unique() if str(value).strip())

    selected_types = st.sidebar.multiselect("Beer Type", beer_type_options)
    selected_producers = st.sidebar.multiselect("Producer", producer_options)
    selected_locations = st.sidebar.multiselect("Location", location_options)
    minimum_my_rating = st.sidebar.slider("Minimum My Rating", 0.0, 5.0, 0.0, 0.25)

    filtered_df = df.copy()
    if selected_types:
        filtered_df = filtered_df[filtered_df["Beer Type"].isin(selected_types)]
    if selected_producers:
        filtered_df = filtered_df[filtered_df["Producer"].isin(selected_producers)]
    if selected_locations:
        filtered_df = filtered_df[filtered_df["Location"].isin(selected_locations)]
    filtered_df = filtered_df[
        filtered_df["My Rating"].fillna(0) >= minimum_my_rating
    ]

    metric_cols = st.columns(4)
    metric_cols[0].metric("Unique Beers", f"{len(filtered_df):,}")
    metric_cols[1].metric("Producers", f"{filtered_df['Producer'].fillna('').replace('', pd.NA).dropna().nunique():,}")
    metric_cols[2].metric(
        "Avg My Rating",
        f"{filtered_df['My Rating'].dropna().mean():.2f}" if filtered_df["My Rating"].dropna().any() else "—",
    )
    metric_cols[3].metric(
        "Avg Global Rating",
        f"{filtered_df['Global Rating'].dropna().mean():.2f}" if filtered_df["Global Rating"].dropna().any() else "—",
    )

    st.markdown("---")

    if show_map:
        st.subheader("Where Your Beer is Brewed")
        if map_chart is not None:
            st.plotly_chart(map_chart, use_container_width=True)
        elif map_message:
            st.info(map_message)
        st.markdown("---")

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        style_summary = (
            filtered_df["Beer Type"]
            .fillna("Unknown")
            .value_counts()
            .head(15)
            .rename_axis("Beer Type")
            .reset_index(name="Count")
        )
        if not style_summary.empty:
            st.plotly_chart(
                px.bar(style_summary, x="Count", y="Beer Type", orientation="h", title="Top Beer Types"),
                use_container_width=True,
            )

    with chart_col2:
        producer_summary = (
            filtered_df["Producer"]
            .fillna("Unknown")
            .value_counts()
            .head(15)
            .rename_axis("Producer")
            .reset_index(name="Count")
        )
        if not producer_summary.empty:
            st.plotly_chart(
                px.bar(producer_summary, x="Count", y="Producer", orientation="h", title="Top Producers"),
                use_container_width=True,
            )

    st.markdown("---")

    recent_timeline = filtered_df.dropna(subset=["Recent Date"]).copy()
    recent_timeline["Month"] = recent_timeline["Recent Date"].dt.to_period("M").astype(str)
    recent_timeline = (
        recent_timeline.groupby("Month")
        .size()
        .reset_index(name="Beers")
    )
    if not recent_timeline.empty:
        st.plotly_chart(
            px.line(recent_timeline, x="Month", y="Beers", markers=True, title="Recent Date Timeline"),
            use_container_width=True,
        )

    st.markdown("---")
    st.subheader("Beer Table")
    st.dataframe(
        filtered_df.sort_values("Recent Date", ascending=False, na_position="last"),
        use_container_width=True,
    )
else:
    st.info("Load `my_beers.csv` or upload a beer-history CSV to get started.")
