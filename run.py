import argparse
import shutil
import subprocess
import webbrowser
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
    save_plotly_chart,
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
from untapped_selenium import (
    login as selenium_login,
    fetch_checkins as selenium_fetch_checkins,
    get_user_info as selenium_get_user_info,
    save_credentials as selenium_save_credentials,
    load_credentials as selenium_load_credentials,
    quit_driver,
)

TIMEFRAME_CHOICES = ["Week", "Month", "Year", "Year to date"]


def choose_column(df, provided_column, candidate_columns, display_name):
    if provided_column:
        if provided_column not in df.columns:
            raise ValueError(f"Provided {display_name} column '{provided_column}' was not found in the dataset.")
        return provided_column
    return find_column(df, candidate_columns)


def make_output_path(base_dir, filename):
    output_path = Path(base_dir) / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def write_summary_file(metrics, output_dir, timeframe, date_range):
    output_path = make_output_path(output_dir, "summary.txt")
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write("Untappd Drinks Dashboard summary\n")
        handle.write(f"Timeframe: {timeframe}\n")
        handle.write(f"Date range: {date_range[0].date()} to {date_range[1].date()}\n")
        handle.write(f"Total check-ins: {metrics['checkins']}\n")
        handle.write(f"Unique places: {metrics['unique_places']}\n")
        if metrics["average_rating"] is not None:
            handle.write(f"Average rating: {metrics['average_rating']:.2f}\n")
        else:
            handle.write("Average rating: —\n")
        handle.write(f"States visited: {metrics['states_visited']}\n")
    return output_path


def open_html_files(paths):
    for path in paths:
        webbrowser.open_new_tab(str(path))


def run_streamlit_app():
    streamlit_executable = shutil.which("streamlit")
    if streamlit_executable is None:
        raise RuntimeError("Streamlit is not installed or not available in PATH.")
    subprocess.run([streamlit_executable, "run", "streamlit_app.py"], check=True)


def cli_main(args):
    df_raw = load_data(args.file)
    if df_raw.empty:
        raise ValueError("Loaded dataset contains no rows.")

    date_col = choose_column(df_raw, args.date_col, PREFERRED_COLUMNS["date"], "date")
    state_col = choose_column(df_raw, args.state_col, PREFERRED_COLUMNS["state"], "state")
    style_col = choose_column(df_raw, args.style_col, PREFERRED_COLUMNS["style"], "style")
    serving_col = choose_column(df_raw, args.serving_col, PREFERRED_COLUMNS["serving"], "serving")
    rating_col = choose_column(df_raw, args.rating_col, PREFERRED_COLUMNS["rating"], "rating")
    place_col = choose_column(df_raw, args.place_col, PREFERRED_COLUMNS["place"], "place")

    df = parse_dataframe(df_raw, date_col, state_col, style_col, serving_col, rating_col, place_col)
    if df.empty:
        raise ValueError("No valid check-in records were found after parsing the selected date column.")

    filtered_df, cutoff, max_date = get_timeframe(df, args.timeframe)
    if filtered_df.empty:
        raise ValueError("No check-ins found in the selected timeframe.")

    metrics = {
        "checkins": filtered_df.shape[0],
        "unique_places": filtered_df["place_name"].nunique(),
        "average_rating": filtered_df["rating"].dropna().mean() if "rating" in filtered_df.columns else None,
        "states_visited": filtered_df["state_code"].dropna().nunique(),
    }

    print(f"Rendered charts for {args.timeframe} timeframe")
    print(f"  Check-ins: {metrics['checkins']}")
    print(f"  Unique places: {metrics['unique_places']}")
    print(f"  States visited: {metrics['states_visited']}")
    if metrics["average_rating"] is not None:
        print(f"  Average rating: {metrics['average_rating']:.2f}")

    charts = {
        "state_map": create_state_map(filtered_df),
        "checkins": create_checkin_chart(filtered_df, args.timeframe),
        "styles": create_style_chart(filtered_df),
        "ratings": create_rating_serving_chart(filtered_df),
    }

    saved_paths = []
    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for label, chart in charts.items():
            if chart is not None:
                html_path = output_dir / f"{label}.html"
                save_plotly_chart(chart, html_path)
                saved_paths.append(html_path)
        summary_path = write_summary_file(metrics, output_dir, args.timeframe, (cutoff, max_date))
        print(f"Saved charts and summary to {output_dir}")
        print(f"Summary saved to {summary_path}")

    if not args.no_open:
        for chart in charts.values():
            if chart is not None:
                chart.show()
        if args.output_dir and saved_paths:
            open_html_files(saved_paths)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Untappd visualizations: login, fetch data, and create dashboards",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Login using web scraping (no API key needed)
  python run.py scrape-login --username YOUR_USERNAME --password YOUR_PASSWORD

  # Fetch data using scraper
  python run.py scrape-fetch --timeframe Month --output checkins.csv

  # Login using Selenium with Firefox or Chrome
  python run.py selenium-login --username YOUR_USERNAME --password YOUR_PASSWORD --browser firefox
  python run.py selenium-fetch --browser chrome --output checkins.csv

  # Login to Untappd API (if you have a commercial account)
  python run.py login --client-id YOUR_ID --client-secret YOUR_SECRET

  # Render charts from CSV/JSON file
  python run.py render --file data.csv --timeframe Year --output-dir ./charts

  # Launch interactive Streamlit dashboard
  python run.py streamlit
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Scraper login command (NO API KEY NEEDED)
    scraper_login_parser = subparsers.add_parser(
        "scrape-login",
        help="Login using web scraping (no API key required)",
    )
    scraper_login_parser.add_argument(
        "--username",
        required=True,
        help="Your Untappd username",
    )
    scraper_login_parser.add_argument(
        "--password",
        required=True,
        help="Your Untappd password",
    )

    # Scraper fetch command
    scraper_fetch_parser = subparsers.add_parser(
        "scrape-fetch",
        help="Fetch check-ins using web scraping",
    )
    scraper_fetch_parser.add_argument(
        "--username",
        help="Untappd username to fetch (defaults to authenticated user)",
    )
    scraper_fetch_parser.add_argument("--output", "-o", help="Save fetched data to CSV file")
    scraper_fetch_parser.add_argument(
        "--timeframe", "-t", default="Month", choices=TIMEFRAME_CHOICES, help="Render charts for this timeframe"
    )
    scraper_fetch_parser.add_argument("--output-dir", help="Directory to save HTML charts")
    scraper_fetch_parser.add_argument("--no-open", action="store_true", help="Do not open charts in browser")

    # Selenium login command
    selenium_login_parser = subparsers.add_parser(
        "selenium-login",
        help="Login using Selenium browser automation",
    )
    selenium_login_parser.add_argument("--username", required=True, help="Your Untappd username")
    selenium_login_parser.add_argument("--password", required=True, help="Your Untappd password")
    selenium_login_parser.add_argument(
        "--browser",
        default="firefox",
        choices=["firefox", "chrome"],
        help="Browser engine for Selenium",
    )
    selenium_login_parser.add_argument(
        "--headed",
        action="store_true",
        help="Run with visible browser window (headless by default)",
    )

    # Selenium fetch command
    selenium_fetch_parser = subparsers.add_parser(
        "selenium-fetch",
        help="Fetch check-ins using Selenium browser automation",
    )
    selenium_fetch_parser.add_argument("--username", help="Untappd username to fetch (defaults to authenticated user)")
    selenium_fetch_parser.add_argument("--output", "-o", help="Save fetched data to CSV file")
    selenium_fetch_parser.add_argument(
        "--timeframe", "-t", default="Month", choices=TIMEFRAME_CHOICES, help="Render charts for this timeframe"
    )
    selenium_fetch_parser.add_argument("--output-dir", help="Directory to save HTML charts")
    selenium_fetch_parser.add_argument("--no-open", action="store_true", help="Do not open charts in browser")
    selenium_fetch_parser.add_argument(
        "--browser",
        default="firefox",
        choices=["firefox", "chrome"],
        help="Browser engine for Selenium",
    )
    selenium_fetch_parser.add_argument(
        "--headed",
        action="store_true",
        help="Run with visible browser window (headless by default)",
    )

    # Original API login command
    login_parser = subparsers.add_parser("login", help="Authenticate with Untappd API (requires commercial account)")
    login_parser.add_argument(
        "--client-id",
        required=True,
        help="Untappd API client ID (register at https://untappd.com/api/dashboard)",
    )
    login_parser.add_argument("--client-secret", required=True, help="Untappd API client secret")

    # Original API fetch command
    fetch_parser = subparsers.add_parser("fetch", help="Fetch check-ins from authenticated Untappd account (API)")
    fetch_parser.add_argument("--username", help="Fetch checkins for specific user (optional, defaults to authenticated user)")
    fetch_parser.add_argument("--output", "-o", help="Save fetched data to CSV file")
    fetch_parser.add_argument("--timeframe", "-t", default="Month", choices=TIMEFRAME_CHOICES, help="Render charts for this timeframe")
    fetch_parser.add_argument("--output-dir", help="Directory to save HTML charts")
    fetch_parser.add_argument("--no-open", action="store_true", help="Do not open charts in browser")

    # Render command (from existing CSV/JSON)
    render_parser = subparsers.add_parser("render", help="Render charts from CSV or JSON file")
    render_parser.add_argument("--file", "-f", required=True, help="Path to Untappd CSV or JSON export")
    render_parser.add_argument("--timeframe", "-t", default="Month", choices=TIMEFRAME_CHOICES, help="Select a timeframe for charts")
    render_parser.add_argument("--date-col", help="Column name for check-in date")
    render_parser.add_argument("--state-col", help="Column name for state")
    render_parser.add_argument("--style-col", help="Column name for beer style")
    render_parser.add_argument("--serving-col", help="Column name for serving style")
    render_parser.add_argument("--rating-col", help="Column name for rating")
    render_parser.add_argument("--place-col", help="Column name for venue/place")
    render_parser.add_argument("--output-dir", help="Directory to save HTML renderings")
    render_parser.add_argument("--no-open", action="store_true", help="Do not open charts in browser")

    # Streamlit command
    streamlit_parser = subparsers.add_parser("streamlit", help="Launch interactive Streamlit dashboard")

    return parser.parse_args()


def handle_scraper_login(args):
    """Handle login using web scraping (no API key needed)."""
    print("Authenticating with Untappd using web scraping...")
    try:
        session = scraper_login(args.username, args.password)
        scraper_save_credentials(args.username, args.password)

        # Get user info
        user_info = scraper_get_user_info(session, args.username)
        print(f"✓ Successfully logged in as {user_info['username']}")
        if user_info.get("total_checkins"):
            print(f"  Total check-ins: {user_info['total_checkins']}")
    except Exception as e:
        print(f"✗ Login failed: {e}")
        raise SystemExit(1)


def handle_scraper_fetch(args):
    """Fetch check-ins using web scraping."""
    creds = scraper_load_credentials()
    if not creds.get("username") or not creds.get("password"):
        raise SystemExit(
            "Not authenticated. Run 'python run.py scrape-login --username YOUR_USERNAME --password YOUR_PASSWORD' first."
        )

    print("Creating authenticated session...")
    try:
        session = scraper_login(creds["username"], creds["password"])
    except Exception as e:
        print(f"Login failed: {e}. Please run scrape-login again.")
        raise SystemExit(1)

    target_user = args.username or creds["username"]
    print(f"Fetching check-ins from {target_user}...")

    try:
        df = scraper_fetch_checkins(session, target_user)
        print(f"✓ Downloaded {len(df)} check-ins")
    except Exception as e:
        print(f"✗ Error fetching check-ins: {e}")
        raise SystemExit(1)

    # Save to CSV if requested
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        print(f"Saved data to {output_path}")

    # Parse and render charts if output directory specified
    if args.output_dir:
        print(f"\nParsing data and rendering charts...")

        df_parsed = parse_dataframe(
            df,
            date_col="checkin_date",
            state_col="place_state",
            style_col="beer_style",
            serving_col="serving_style",
            rating_col="rating",
            place_col="venue_name",
        )

        if df_parsed.empty:
            print("No valid check-in records to render.")
            return

        filtered_df, cutoff, max_date = get_timeframe(df_parsed, args.timeframe)
        if filtered_df.empty:
            print("No check-ins in selected timeframe.")
            return

        metrics = {
            "checkins": filtered_df.shape[0],
            "unique_places": filtered_df["place_name"].nunique(),
            "average_rating": filtered_df["rating"].dropna().mean() if "rating" in filtered_df.columns else None,
            "states_visited": filtered_df["state_code"].dropna().nunique(),
        }

        print(f"Timeframe: {args.timeframe}")
        print(f"  Check-ins: {metrics['checkins']}")
        print(f"  Unique places: {metrics['unique_places']}")
        print(f"  States visited: {metrics['states_visited']}")
        if metrics["average_rating"] is not None:
            print(f"  Average rating: {metrics['average_rating']:.2f}")

        charts = {
            "state_map": create_state_map(filtered_df),
            "checkins": create_checkin_chart(filtered_df, args.timeframe),
            "styles": create_style_chart(filtered_df),
            "ratings": create_rating_serving_chart(filtered_df),
        }

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        saved_paths = []
        for label, chart in charts.items():
            if chart is not None:
                html_path = output_dir / f"{label}.html"
                save_plotly_chart(chart, html_path)
                saved_paths.append(html_path)

        write_summary_file(metrics, output_dir, args.timeframe, (cutoff, max_date))
        print(f"✓ Saved charts to {output_dir}")

        if not args.no_open:
            for chart in charts.values():
                if chart is not None:
                    chart.show()
            if saved_paths:
                open_html_files(saved_paths)


def handle_login(args):
    """Handle Untappd login/authentication."""
    print("Authenticating with Untappd...")
    access_token = authenticate(args.client_id, args.client_secret)

    # Verify the token works
    print("Verifying credentials...")
    user_info = get_user_info(access_token)
    print(f"✓ Successfully logged in as {user_info['username']}")
    print(f"  Total check-ins: {user_info['total_checkins']}")


def handle_fetch(args):
    """Fetch check-ins from Untappd account and optionally render charts."""
    creds = load_credentials()
    if not creds.get("access_token"):
        raise SystemExit(
            "Not authenticated. Run 'python run.py login --client-id YOUR_ID --client-secret YOUR_SECRET' first."
        )

    access_token = creds["access_token"]

    # Validate token
    if not validate_token(access_token):
        raise SystemExit("Stored access token is invalid. Please login again with the login command.")

    print(f"Fetching check-ins from Untappd...")
    df = fetch_user_checkins(access_token, username=args.username)
    print(f"✓ Downloaded {len(df)} check-ins")

    # Save to CSV if requested
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        print(f"Saved data to {output_path}")

    # Parse and render charts if output directory specified
    if args.output_dir:
        print(f"\nParsing data and rendering charts...")

        df_parsed = parse_dataframe(
            df,
            date_col="checkin_date",
            state_col="place_state",
            style_col="beer_style",
            serving_col="serving_style",
            rating_col="rating",
            place_col="venue_name",
        )

        if df_parsed.empty:
            print("No valid check-in records to render.")
            return

        filtered_df, cutoff, max_date = get_timeframe(df_parsed, args.timeframe)
        if filtered_df.empty:
            print("No check-ins in selected timeframe.")
            return

        metrics = {
            "checkins": filtered_df.shape[0],
            "unique_places": filtered_df["place_name"].nunique(),
            "average_rating": filtered_df["rating"].dropna().mean() if "rating" in filtered_df.columns else None,
            "states_visited": filtered_df["state_code"].dropna().nunique(),
        }

        print(f"Timeframe: {args.timeframe}")
        print(f"  Check-ins: {metrics['checkins']}")
        print(f"  Unique places: {metrics['unique_places']}")
        print(f"  States visited: {metrics['states_visited']}")
        if metrics["average_rating"] is not None:
            print(f"  Average rating: {metrics['average_rating']:.2f}")

        charts = {
            "state_map": create_state_map(filtered_df),
            "checkins": create_checkin_chart(filtered_df, args.timeframe),
            "styles": create_style_chart(filtered_df),
            "ratings": create_rating_serving_chart(filtered_df),
        }

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        saved_paths = []
        for label, chart in charts.items():
            if chart is not None:
                html_path = output_dir / f"{label}.html"
                save_plotly_chart(chart, html_path)
                saved_paths.append(html_path)

        write_summary_file(metrics, output_dir, args.timeframe, (cutoff, max_date))
        print(f"✓ Saved charts to {output_dir}")

        if not args.no_open:
            for chart in charts.values():
                if chart is not None:
                    chart.show()
            if saved_paths:
                open_html_files(saved_paths)


def handle_selenium_login(args):
    """Handle login using Selenium automation."""
    print(f"Authenticating with Untappd using Selenium ({args.browser})...")
    driver = None
    try:
        driver = selenium_login(
            args.username,
            args.password,
            headless=not args.headed,
            browser=args.browser,
        )
        selenium_save_credentials(args.username, args.password)
        user_info = selenium_get_user_info(driver, args.username)
        print(f"✓ Successfully logged in as {user_info['username']}")
        if user_info.get("total_checkins"):
            print(f"  Total check-ins: {user_info['total_checkins']}")
    except Exception as e:
        print(f"✗ Selenium login failed: {e}")
        raise SystemExit(1)
    finally:
        if driver is not None:
            quit_driver(driver)


def handle_selenium_fetch(args):
    """Fetch check-ins using Selenium automation."""
    creds = selenium_load_credentials()
    if not creds.get("username") or not creds.get("password"):
        raise SystemExit(
            "Not authenticated. Run 'python run.py selenium-login --username YOUR_USERNAME --password YOUR_PASSWORD' first."
        )

    target_user = args.username or creds["username"]
    driver = None
    try:
        print(f"Launching Selenium browser ({args.browser})...")
        driver = selenium_login(
            creds["username"],
            creds["password"],
            headless=not args.headed,
            browser=args.browser,
        )
        print(f"Fetching check-ins from {target_user}...")
        df = selenium_fetch_checkins(driver, target_user)
        print(f"✓ Downloaded {len(df)} check-ins")
    except Exception as e:
        print(f"✗ Error fetching check-ins with Selenium: {e}")
        raise SystemExit(1)
    finally:
        if driver is not None:
            quit_driver(driver)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        print(f"Saved data to {output_path}")

    if args.output_dir:
        print("\nParsing data and rendering charts...")
        df_parsed = parse_dataframe(
            df,
            date_col="checkin_date",
            state_col="place_state",
            style_col="beer_style",
            serving_col="serving_style",
            rating_col="rating",
            place_col="venue_name",
        )
        if df_parsed.empty:
            print("No valid check-in records to render.")
            return

        filtered_df, cutoff, max_date = get_timeframe(df_parsed, args.timeframe)
        if filtered_df.empty:
            print("No check-ins in selected timeframe.")
            return

        metrics = {
            "checkins": filtered_df.shape[0],
            "unique_places": filtered_df["place_name"].nunique(),
            "average_rating": filtered_df["rating"].dropna().mean() if "rating" in filtered_df.columns else None,
            "states_visited": filtered_df["state_code"].dropna().nunique(),
        }

        charts = {
            "state_map": create_state_map(filtered_df),
            "checkins": create_checkin_chart(filtered_df, args.timeframe),
            "styles": create_style_chart(filtered_df),
            "ratings": create_rating_serving_chart(filtered_df),
        }

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        saved_paths = []
        for label, chart in charts.items():
            if chart is not None:
                html_path = output_dir / f"{label}.html"
                save_plotly_chart(chart, html_path)
                saved_paths.append(html_path)
        write_summary_file(metrics, output_dir, args.timeframe, (cutoff, max_date))
        print(f"✓ Saved charts to {output_dir}")

        if not args.no_open:
            for chart in charts.values():
                if chart is not None:
                    chart.show()
            if saved_paths:
                open_html_files(saved_paths)


def handle_render(args):
    """Render charts from CSV/JSON file."""
    cli_main(args)


def main():
    args = parse_args()

    if args.command == "scrape-login":
        handle_scraper_login(args)
    elif args.command == "scrape-fetch":
        handle_scraper_fetch(args)
    elif args.command == "selenium-login":
        handle_selenium_login(args)
    elif args.command == "selenium-fetch":
        handle_selenium_fetch(args)
    elif args.command == "login":
        handle_login(args)
    elif args.command == "fetch":
        handle_fetch(args)
    elif args.command == "render":
        handle_render(args)
    elif args.command == "streamlit":
        run_streamlit_app()
    else:
        print("No command specified. Use --help for usage information.")


if __name__ == "__main__":
    main()
