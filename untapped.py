import os
from pathlib import Path

import pandas as pd
import plotly.express as px

STATE_NAME_TO_CODE = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "District of Columbia": "DC",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
    "Puerto Rico": "PR",
}
STATE_CODES = set(STATE_NAME_TO_CODE.values())

PREFERRED_COLUMNS = {
    "date": ["checkin_date", "created_at", "date", "timestamp", "checkin_time", "time", "datetime"],
    "state": ["state", "venue_state", "brewery_state", "location_state", "place_state"],
    "style": ["beer_style", "style", "beer_style_name", "style_name"],
    "serving": ["serving_style", "serving_type", "serving", "beer_serving", "glass_type", "glass"],
    "rating": ["rating", "rating_score", "rating_overall", "beer_rating"],
    "place": ["venue_name", "brewery_name", "place_name", "location_name", "venue"],
}


def find_column(df: pd.DataFrame, candidates):
    for col in candidates:
        if col in df.columns:
            return col
    return None


def load_data(source):
    if isinstance(source, (str, Path)):
        source = str(source)
        file_name = source.lower()
        if file_name.endswith(".csv"):
            return pd.read_csv(source)
        if file_name.endswith(".json"):
            try:
                return pd.read_json(source)
            except ValueError:
                return pd.read_json(source, lines=True)
    elif hasattr(source, "read"):
        file_name = str(getattr(source, "name", "")).lower()
        if file_name.endswith(".csv"):
            return pd.read_csv(source)
        if file_name.endswith(".json"):
            try:
                return pd.read_json(source)
            except ValueError:
                return pd.read_json(source, lines=True)
    raise ValueError("Unsupported file type. Please provide CSV or JSON data.")


def normalize_state(value):
    if pd.isna(value):
        return None
    value = str(value).strip()
    if not value:
        return None
    upper = value.upper()
    if upper in STATE_CODES:
        return upper
    title = value.title()
    if title in STATE_NAME_TO_CODE:
        return STATE_NAME_TO_CODE[title]
    for state_name, code in STATE_NAME_TO_CODE.items():
        if state_name.lower() == value.lower() or state_name.lower().startswith(value.lower()):
            return code
    return None


def parse_dataframe(df: pd.DataFrame, date_col, state_col, style_col, serving_col, rating_col, place_col):
    df = df.copy()

    if date_col is None:
        raise ValueError("No date column selected. Please choose the column that contains your check-in timestamp.")

    df["checkin_date"] = pd.to_datetime(df[date_col], errors="coerce")
    if df["checkin_date"].isna().all():
        df["checkin_date"] = pd.to_datetime(df[date_col].astype(str).str.replace("T", " "), errors="coerce")

    if state_col is not None:
        df["state_code"] = df[state_col].map(normalize_state)
    else:
        df["state_code"] = None

    df["beer_style"] = df[style_col].astype(str) if style_col is not None else "Unknown"
    df["serving_style"] = df[serving_col].astype(str) if serving_col is not None else "Unknown"
    df["rating"] = pd.to_numeric(df[rating_col], errors="coerce") if rating_col is not None else pd.NA
    df["place_name"] = df[place_col].astype(str) if place_col is not None else "Unknown"

    df = df.dropna(subset=["checkin_date"])
    df["checkin_date"] = pd.to_datetime(df["checkin_date"]).dt.tz_localize(None)
    df["year"] = df["checkin_date"].dt.year
    df["month_name"] = df["checkin_date"].dt.strftime("%Y-%m")
    df["week_start"] = df["checkin_date"].dt.to_period("W").apply(lambda r: r.start_time)
    df["day_name"] = df["checkin_date"].dt.strftime("%a")
    return df


def get_timeframe(df: pd.DataFrame, selection: str):
    max_date = df["checkin_date"].max()
    if selection == "Week":
        cutoff = max_date - pd.Timedelta(days=7)
    elif selection == "Month":
        cutoff = max_date - pd.Timedelta(days=30)
    elif selection == "Year":
        cutoff = max_date - pd.Timedelta(days=365)
    else:
        cutoff = pd.Timestamp(year=max_date.year, month=1, day=1)
    return df[df["checkin_date"] >= cutoff], cutoff, max_date


def create_state_map(df: pd.DataFrame):
    if "state_code" not in df.columns or df["state_code"].isna().all():
        return None

    state_summary = (
        df.dropna(subset=["state_code"])
        .groupby("state_code")
        .agg(checkins=("checkin_date", "count"), unique_places=("place_name", "nunique"))
        .reset_index()
    )
    if state_summary.empty:
        return None

    chart = px.choropleth(
        state_summary,
        locations="state_code",
        locationmode="USA-states",
        color="checkins",
        hover_name="state_code",
        hover_data={"checkins": True, "unique_places": True, "state_code": False},
        scope="usa",
        color_continuous_scale="viridis",
        labels={"checkins": "Check-ins"},
    )
    chart.update_layout(margin=dict(l=0, r=0, t=30, b=0))
    return chart


def create_checkin_chart(df: pd.DataFrame, timeframe: str):
    if df.empty:
        return None
    if timeframe == "Week":
        agg = df.set_index("checkin_date").resample("D").size().rename("checkins").reset_index()
        title = "Daily check-ins"
    elif timeframe == "Month":
        agg = df.set_index("checkin_date").resample("W-MON").size().rename("checkins").reset_index()
        title = "Weekly check-ins"
    else:
        agg = df.set_index("checkin_date").resample("M").size().rename("checkins").reset_index()
        title = "Monthly check-ins"

    chart = px.line(
        agg,
        x="checkin_date",
        y="checkins",
        markers=True,
        title=title,
        labels={"checkin_date": "Date", "checkins": "Check-ins"},
    )
    chart.update_layout(xaxis=dict(tickformat="%b %d, %Y"))
    return chart


def create_style_chart(df: pd.DataFrame):
    summary = (
        df.groupby("beer_style")
        .size()
        .reset_index(name="checkins")
        .sort_values("checkins", ascending=False)
        .head(12)
    )
    if summary.empty:
        return None
    chart = px.bar(
        summary,
        x="checkins",
        y="beer_style",
        orientation="h",
        title="Top Beer Styles",
        labels={"checkins": "Check-ins", "beer_style": "Beer Style"},
    )
    chart.update_layout(yaxis={"categoryorder": "total descending"}, margin=dict(l=0, r=0, t=35, b=0))
    return chart


def create_rating_serving_chart(df: pd.DataFrame):
    summary = (
        df.groupby("serving_style")
        .agg(count=("rating", "count"), avg_rating=("rating", "mean"))
        .reset_index()
        .sort_values(["count", "avg_rating"], ascending=[False, False])
        .head(12)
    )
    if summary.empty:
        return None
    chart = px.bar(
        summary,
        x="serving_style",
        y="avg_rating",
        color="count",
        title="Average Rating by Serving Style",
        labels={"serving_style": "Serving Style", "avg_rating": "Avg Rating", "count": "Check-ins"},
        color_continuous_scale="tealrose",
    )
    chart.update_layout(xaxis_tickangle=-45, margin=dict(l=0, r=0, t=35, b=0))
    return chart


def format_count(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    return f"{int(value):,}"


def save_plotly_chart(chart, html_path):
    if chart is None:
        return None
    path = Path(html_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    chart.write_html(str(path))
    return str(path)

