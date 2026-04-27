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
COUNTRY_ALIASES = {
    "usa": "United States",
    "u.s.a.": "United States",
    "united states": "United States",
    "united states of america": "United States",
    "us": "United States",
    "u.s.": "United States",
    "england": "United Kingdom",
    "scotland": "United Kingdom",
    "wales": "United Kingdom",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "great britain": "United Kingdom",
    "ireland": "Ireland",
    "canada": "Canada",
    "mexico": "Mexico",
    "australia": "Australia",
    "new zealand": "New Zealand",
    "japan": "Japan",
    "germany": "Germany",
    "france": "France",
    "belgium": "Belgium",
    "netherlands": "Netherlands",
    "denmark": "Denmark",
    "italy": "Italy",
    "spain": "Spain",
    "austria": "Austria",
    "ukraine": "Ukraine",
    "czechia": "Czech Republic",
    "czech republic": "Czech Republic",
    "brazil": "Brazil",
    "chile": "Chile",
}


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


def normalize_country(value):
    if pd.isna(value):
        return None
    value = str(value).strip()
    if not value:
        return None
    lowered = value.lower()
    return COUNTRY_ALIASES.get(lowered)


def create_state_map(df: pd.DataFrame):
    if "country_name" not in df.columns or df["country_name"].isna().all():
        return None

    country_summary = (
        df.dropna(subset=["country_name"])
        .groupby("country_name")
        .agg(checkins=("checkin_date", "count"), unique_places=("place_name", "nunique"))
        .reset_index()
    )
    if country_summary.empty:
        return None

    chart = px.choropleth(
        country_summary,
        locations="country_name",
        locationmode="country names",
        color="checkins",
        hover_name="country_name",
        hover_data={"checkins": True, "unique_places": True, "country_name": False},
        color_continuous_scale="viridis",
        labels={"checkins": "Check-ins"},
    )
    chart.update_layout(margin=dict(l=0, r=0, t=30, b=0))
    return chart


def create_us_state_map(df: pd.DataFrame):
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
