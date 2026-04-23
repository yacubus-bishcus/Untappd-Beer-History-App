import streamlit as st
import pandas as pd
from pathlib import Path

from untapped import (
    PREFERRED_COLUMNS,
    create_checkin_chart,
    create_rating_serving_chart,
    create_state_map,
    create_style_chart,
    find_column,
    format_count,
    get_timeframe,
    load_data,
    parse_dataframe,
)
from untapped_api import (
    authenticate,
    fetch_user_checkins,
    get_user_info,
    load_credentials,
    validate_token,
)
from untapped_scraper import (
    login as scraper_login,
    fetch_checkins as scraper_fetch_checkins,
    get_user_info as scraper_get_user_info,
    save_credentials as scraper_save_credentials,
    load_credentials as scraper_load_credentials,
)

st.set_page_config(page_title="Untappd Drinks Dashboard", layout="wide")

st.title("🍺 Untappd Drinks Dashboard")
st.markdown(
    "Explore where you've checked in drinks, top beer styles, and serving-style ratings with interactive visualizations."
)

# Sidebar for input selection
st.sidebar.header("Data Source")
data_source = st.sidebar.radio("Choose data source:", ["Upload CSV/JSON", "Web Scraping", "Untappd API"])

df = None
df_raw = None

if data_source == "Upload CSV/JSON":
    st.sidebar.header("Upload & Field Mapping")
    uploaded_file = st.sidebar.file_uploader("Upload Untappd export CSV or JSON", type=["csv", "json"])

    if uploaded_file is not None:
        try:
            df_raw = load_data(uploaded_file)
            if not df_raw.empty:
                st.success(f"Loaded {len(df_raw)} records from file")
            else:
                st.error("Uploaded file contains no rows")
        except Exception as e:
            st.error(f"Error loading file: {e}")

elif data_source == "Web Scraping":
    st.sidebar.header("Untappd Web Scraping (No API Key Needed)")

    scraper_creds = scraper_load_credentials()
    has_scraper_creds = bool(scraper_creds.get("username") and scraper_creds.get("password"))

    if has_scraper_creds:
        st.sidebar.info(f"✓ Logged in as {scraper_creds['username']}")

        if st.sidebar.button("📥 Fetch My Check-ins (Web Scraping)"):
            try:
                with st.spinner("Authenticating and fetching your check-ins..."):
                    session = scraper_login(scraper_creds["username"], scraper_creds["password"])
                    df_raw = scraper_fetch_checkins(session, scraper_creds["username"])
                st.success(f"✓ Downloaded {len(df_raw)} check-ins")
            except Exception as e:
                st.error(f"Error fetching check-ins: {e}")

        if st.sidebar.button("🚪 Logout (Web Scraping)"):
            scraper_save_credentials("", "")
            st.rerun()

    else:
        st.sidebar.info("Login using web scraping to fetch your check-ins without needing an API key.")

        username = st.sidebar.text_input("Untappd Username")
        password = st.sidebar.text_input("Untappd Password", type="password")

        if st.sidebar.button("🔐 Login with Web Scraping"):
            if username and password:
                try:
                    with st.spinner("Logging in..."):
                        session = scraper_login(username, password)
                    scraper_save_credentials(username, password)
                    st.sidebar.success("✓ Successfully logged in!")
                    st.rerun()
                except Exception as e:
                    st.sidebar.error(f"Login failed: {e}")
            else:
                st.sidebar.warning("Please enter both username and password")

else:  # Untappd API
    st.sidebar.header("Untappd API Authentication")

    creds = load_credentials()
    has_token = bool(creds.get("access_token"))

    if has_token:
        if st.sidebar.button("🔄 Refresh Token"):
            if validate_token(creds["access_token"]):
                st.sidebar.success("✓ Token is valid")
            else:
                st.sidebar.error("Token is invalid. Please login again.")
                creds = {}

    if not creds.get("access_token"):
        st.sidebar.info(
            """To authenticate with Untappd API:
1. Register an app at https://untappd.com/api/dashboard
2. Click 'Login to Untappd' below to authenticate

⚠️ Note: Untappd API is limited to commercial accounts.
Use "Web Scraping" for personal use instead!
"""
        )

        col1, col2 = st.sidebar.columns(2)
        with col1:
            client_id = st.text_input("Client ID", type="password")
        with col2:
            client_secret = st.text_input("Client Secret", type="password")

        if st.sidebar.button("🔐 Login to Untappd API"):
            if client_id and client_secret:
                try:
                    with st.spinner("Authenticating with Untappd..."):
                        access_token = authenticate(client_id, client_secret)
                    st.sidebar.success("✓ Successfully authenticated!")
                    st.rerun()
                except Exception as e:
                    st.sidebar.error(f"Authentication failed: {e}")
            else:
                st.sidebar.warning("Please provide both Client ID and Client Secret")

    else:
        try:
            user_info = get_user_info(creds["access_token"])
            st.sidebar.success(f"✓ Logged in as {user_info['username']}")

            if st.sidebar.button("📥 Fetch My Check-ins (API)"):
                with st.spinner("Fetching your check-ins from Untappd..."):
                    try:
                        df_raw = fetch_user_checkins(creds["access_token"])
                        st.success(f"✓ Downloaded {len(df_raw)} check-ins")
                    except Exception as e:
                        st.error(f"Error fetching check-ins: {e}")

            if st.sidebar.button("🚪 Logout"):
                # Clear credentials
                from untapped_api import save_credentials

                save_credentials("", "", None)
                st.rerun()

        except Exception as e:
            st.sidebar.error(f"Token validation failed: {e}")
            if st.sidebar.button("🔄 Login Again"):
                from untapped_api import save_credentials

                save_credentials("", "", None)
                st.rerun()


# Process and display data
if df_raw is not None and not df_raw.empty:
    columns = list(df_raw.columns)

    st.sidebar.header("Column Mapping")

    detected_date = find_column(df_raw, PREFERRED_COLUMNS["date"])
    detected_state = find_column(df_raw, PREFERRED_COLUMNS["state"])
    detected_style = find_column(df_raw, PREFERRED_COLUMNS["style"])
    detected_serving = find_column(df_raw, PREFERRED_COLUMNS["serving"])
    detected_rating = find_column(df_raw, PREFERRED_COLUMNS["rating"])
    detected_place = find_column(df_raw, PREFERRED_COLUMNS["place"])

    date_col = st.sidebar.selectbox(
        "Check-in date column",
        columns,
        index=columns.index(detected_date) if detected_date in columns else 0,
    )
    state_col = st.sidebar.selectbox(
        "State column (optional)",
        ["None"] + columns,
        index=(["None"] + columns).index(detected_state) if detected_state in columns else 0,
    )
    style_col = st.sidebar.selectbox(
        "Beer style column",
        ["None"] + columns,
        index=(["None"] + columns).index(detected_style) if detected_style in columns else 0,
    )
    serving_col = st.sidebar.selectbox(
        "Serving style column",
        ["None"] + columns,
        index=(["None"] + columns).index(detected_serving) if detected_serving in columns else 0,
    )
    rating_col = st.sidebar.selectbox(
        "Rating column",
        ["None"] + columns,
        index=(["None"] + columns).index(detected_rating) if detected_rating in columns else 0,
    )
    place_col = st.sidebar.selectbox(
        "Place / venue column",
        ["None"] + columns,
        index=(["None"] + columns).index(detected_place) if detected_place in columns else 0,
    )

    state_col = None if state_col == "None" else state_col
    style_col = None if style_col == "None" else style_col
    serving_col = None if serving_col == "None" else serving_col
    rating_col = None if rating_col == "None" else rating_col
    place_col = None if place_col == "None" else place_col

    try:
        df = parse_dataframe(df_raw, date_col, state_col, style_col, serving_col, rating_col, place_col)
    except Exception as e:
        st.error(f"Error parsing data: {e}")
        df = None

if df is not None and not df.empty:
    st.sidebar.header("Filters")
    timeframe = st.sidebar.radio("Time range", ["Week", "Month", "Year", "Year to date"], index=1)
    filtered_df, cutoff, max_date = get_timeframe(df, timeframe)

    if filtered_df.empty:
        st.warning("No check-ins found in the selected timeframe.")
    else:
        total_checkins = filtered_df.shape[0]
        unique_places = filtered_df["place_name"].nunique()
        average_rating = (
            filtered_df["rating"].dropna().mean() if "rating" in filtered_df.columns else None
        )
        states_visited = filtered_df["state_code"].dropna().nunique()

        st.subheader(f"Summary: {timeframe}")
        metric_cols = st.columns(4)
        metric_cols[0].metric("Check-ins", format_count(total_checkins))
        metric_cols[1].metric("Unique places", format_count(unique_places))
        metric_cols[2].metric(
            "Average rating", f"{average_rating:.2f}" if pd.notna(average_rating) else "—"
        )
        metric_cols[3].metric("States visited", format_count(states_visited))

        st.markdown("---")
        map_chart = create_state_map(filtered_df)
        if map_chart is not None:
            st.plotly_chart(map_chart, use_container_width=True)
        else:
            st.info("No valid state data to display on map.")

        st.markdown("---")
        col1, col2 = st.columns([2, 1])
        with col1:
            checkin_chart = create_checkin_chart(filtered_df, timeframe)
            if checkin_chart is not None:
                st.plotly_chart(checkin_chart, use_container_width=True)
            else:
                st.info("Not enough data to create a check-in trend chart.")

        with col2:
            style_chart = create_style_chart(filtered_df)
            if style_chart is not None:
                st.plotly_chart(style_chart, use_container_width=True)
            else:
                st.info("Not enough data to create a beer style chart.")

        st.markdown("---")
        rating_chart = create_rating_serving_chart(filtered_df)
        if rating_chart is not None:
            st.plotly_chart(rating_chart, use_container_width=True)
        else:
            st.info("Not enough serving-style or rating data to create the chart.")

        st.markdown("---")
        st.subheader("Recent check-ins")
        st.dataframe(
            filtered_df.sort_values("checkin_date", ascending=False)
            .loc[
                :,
                ["checkin_date", "place_name", "state_code", "beer_style", "serving_style", "rating"],
            ]
            .head(25),
            use_container_width=True,
        )

elif data_source == "Upload CSV/JSON":
    st.info("👆 Upload a CSV or JSON file from Untappd to get started!")
elif data_source == "Web Scraping":
    st.info("👆 Click 'Login with Web Scraping' in the sidebar and fetch your check-ins (no API key needed)!")
else:
    st.info("👆 Click 'Login to Untappd API' in the sidebar and fetch your check-ins!")
