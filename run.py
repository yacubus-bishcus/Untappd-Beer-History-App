import argparse
import csv
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from app_config import get_configured_username
from untapped_selenium import (
    fetch_beers as selenium_fetch_beers,
    is_debugger_ready,
    launch_chrome_with_debugger,
    start_manual_login as selenium_start_manual_login,
    wait_for_manual_login as selenium_wait_for_manual_login,
    wait_for_debugger,
    quit_driver,
)

DEFAULT_USERNAME = get_configured_username("")
DEFAULT_DEBUGGER_ADDRESS = "127.0.0.1:9222"
DEFAULT_OUTPUT = "my_beers.csv"
DEFAULT_USER_DATA_DIR = "/tmp/untappd-manual"


def ensure_supported_python():
    version = sys.version_info
    if version.major != 3 or version.minor < 9:
        raise SystemExit(
            f"Unsupported Python version: {version.major}.{version.minor}. "
            "Use Python 3.9 or newer for this project."
        )


def run_streamlit_app():
    subprocess.run([sys.executable, "-m", "streamlit", "run", "streamlit_app.py"], check=True)


def count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            next(reader)
        except StopIteration:
            return 0
        return sum(1 for _ in reader)


def resolve_backstop_total(output_path: Path, provided_backstop_total: Optional[int]) -> Optional[int]:
    if provided_backstop_total is not None:
        return provided_backstop_total
    existing_rows = count_csv_rows(output_path)
    return existing_rows or None


def perform_beer_fetch_workflow(
    username: str,
    debugger_address: str,
    output: str,
    backstop_total: Optional[int],
    user_data_dir: str,
    open_streamlit_after: bool,
):
    if not username:
        raise SystemExit(
            "No Untappd username is configured yet. Please launch from the desktop starter first "
            "or pass --username explicitly."
        )
    output_path = Path(output)
    effective_backstop_total = resolve_backstop_total(output_path, backstop_total)

    if effective_backstop_total is not None:
        print(f"Using backstop total: {effective_backstop_total}")
    else:
        print("No backstop total available. The scraper will stop when Show More is exhausted.")

    launch_url = f"https://untappd.com/user/{username}/beers"
    print(f"Launching Chrome for manual login at {launch_url}...")
    launch_chrome_with_debugger(
        debugger_address=debugger_address,
        user_data_dir=user_data_dir,
        start_url=launch_url,
    )

    driver = None
    try:
        time.sleep(2)
        print(f"Attaching Selenium to Chrome at {debugger_address}...")
        driver = selenium_start_manual_login(
            browser="chrome",
            headless=True,
            attach_debugger=debugger_address,
        )
        selenium_wait_for_manual_login(driver, timeout=300)

        print(f"Fetching beer history for {username}...")
        df = selenium_fetch_beers(
            driver,
            username=username,
            backstop_total=effective_backstop_total,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        print(f"Saved data to {output_path}")
    finally:
        if driver is not None:
            quit_driver(driver)

    if open_streamlit_after:
        print("Opening Streamlit...")
        run_streamlit_app()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Selenium-based Untappd beer history exporter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Default behavior:
  python run.py

Examples:
  python run.py selenium-launch-chrome
  python run.py selenium-fetch-beers
  python run.py selenium-fetch-beers --backstop-total 250
  python run.py streamlit
        """,
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Force a fresh Untappd download even if my_beers.csv already exists",
    )
    parser.add_argument(
        "--backstop-total",
        type=int,
        help="Optional expected total beer count for the default python run.py workflow",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    selenium_launch_chrome_parser = subparsers.add_parser(
        "selenium-launch-chrome",
        help="Launch a real Chrome window with remote debugging for manual Untappd login",
    )
    selenium_launch_chrome_parser.add_argument(
        "--page",
        default="beers",
        choices=["login", "beers"],
        help="Which Untappd page to open first",
    )
    selenium_launch_chrome_parser.add_argument(
        "--username",
        default=DEFAULT_USERNAME,
        help="Untappd username used when opening the beer history page",
    )
    selenium_launch_chrome_parser.add_argument(
        "--debugger-address",
        default=DEFAULT_DEBUGGER_ADDRESS,
        help="Debugger address that Selenium will attach to later",
    )
    selenium_launch_chrome_parser.add_argument(
        "--user-data-dir",
        default=DEFAULT_USER_DATA_DIR,
        help="Chrome profile directory for the manual session",
    )

    selenium_fetch_beers_parser = subparsers.add_parser(
        "selenium-fetch-beers",
        help="Fetch beer history from the Untappd /beers page using Selenium",
    )
    selenium_fetch_beers_parser.add_argument(
        "--username",
        default=DEFAULT_USERNAME,
        help="Untappd username whose beer history should be downloaded",
    )
    selenium_fetch_beers_parser.add_argument(
        "--output",
        "-o",
        default=DEFAULT_OUTPUT,
        help="Save fetched data to CSV file",
    )
    selenium_fetch_beers_parser.add_argument(
        "--attach-debugger",
        default=DEFAULT_DEBUGGER_ADDRESS,
        help="Attach to an existing Chrome instance",
    )
    selenium_fetch_beers_parser.add_argument(
        "--user-data-dir",
        default=DEFAULT_USER_DATA_DIR,
        help="Chrome profile directory to use if Chrome needs to be launched automatically",
    )
    selenium_fetch_beers_parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="How long to wait (seconds) for you to finish manual login when not attaching to an existing browser",
    )
    selenium_fetch_beers_parser.add_argument(
        "--backstop-total",
        type=int,
        help="Expected total beer count; defaults to the current number of rows in the output CSV if it exists",
    )

    run_default_parser = subparsers.add_parser(
        "run-default",
        help="Run the default end-to-end beer export workflow",
    )
    run_default_parser.add_argument("--username", default=DEFAULT_USERNAME)
    run_default_parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT)
    run_default_parser.add_argument("--debugger-address", default=DEFAULT_DEBUGGER_ADDRESS)
    run_default_parser.add_argument("--user-data-dir", default=DEFAULT_USER_DATA_DIR)
    run_default_parser.add_argument("--backstop-total", type=int)
    run_default_parser.add_argument(
        "--update",
        action="store_true",
        help="Force a fresh Untappd download even if my_beers.csv already exists",
    )

    subparsers.add_parser("streamlit", help="Launch the beer history Streamlit dashboard")

    return parser.parse_args()


def handle_selenium_launch_chrome(args):
    if not args.username:
        raise SystemExit("No Untappd username is configured yet. Pass --username explicitly.")
    if args.page == "login":
        start_url = "https://untappd.com/user/login"
    else:
        start_url = f"https://untappd.com/user/{args.username}/beers"

    launch_chrome_with_debugger(
        debugger_address=args.debugger_address,
        user_data_dir=args.user_data_dir,
        start_url=start_url,
    )
    print("Opened Chrome with remote debugging enabled.")
    print(f"Debugger address: {args.debugger_address}")
    print(f"Start URL: {start_url}")


def handle_selenium_fetch_beers(args):
    if not args.username:
        raise SystemExit("No Untappd username is configured yet. Pass --username explicitly.")
    output_path = Path(args.output)
    effective_backstop_total = resolve_backstop_total(output_path, args.backstop_total)
    if effective_backstop_total is not None:
        print(f"Using backstop total: {effective_backstop_total}")

    if not is_debugger_ready(args.attach_debugger):
        start_url = f"https://untappd.com/user/{args.username}/beers"
        print(f"No Chrome debugger detected at {args.attach_debugger}. Launching Chrome automatically...")
        launch_chrome_with_debugger(
            debugger_address=args.attach_debugger,
            user_data_dir=args.user_data_dir,
            start_url=start_url,
        )
        if not wait_for_debugger(args.attach_debugger, timeout=20):
            raise SystemExit(
                f"Could not connect to Chrome debugger at {args.attach_debugger} after launching Chrome."
            )

    driver = None
    try:
        print(f"Attaching to Chrome debugger at {args.attach_debugger}...")
        driver = selenium_start_manual_login(
            browser="chrome",
            headless=True,
            attach_debugger=args.attach_debugger,
        )
        selenium_wait_for_manual_login(driver, timeout=args.timeout)

        print(f"Fetching beer history from {args.username}...")
        df = selenium_fetch_beers(
            driver,
            args.username,
            backstop_total=effective_backstop_total,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        print(f"Saved data to {output_path}")
    finally:
        if driver is not None:
            quit_driver(driver)


def handle_run_default(args):
    output_path = Path(args.output)
    if output_path.exists() and not args.update:
        print(f"Found existing {output_path}. Skipping Untappd download. Use --update to refresh.")
        run_streamlit_app()
        return

    perform_beer_fetch_workflow(
        username=args.username,
        debugger_address=args.debugger_address,
        output=args.output,
        backstop_total=args.backstop_total,
        user_data_dir=args.user_data_dir,
        open_streamlit_after=True,
    )


def main():
    ensure_supported_python()
    args = parse_args()

    if args.command in {None, "run-default"}:
        namespace = argparse.Namespace(
            username=getattr(args, "username", DEFAULT_USERNAME),
            output=getattr(args, "output", DEFAULT_OUTPUT),
            debugger_address=getattr(args, "debugger_address", DEFAULT_DEBUGGER_ADDRESS),
            user_data_dir=getattr(args, "user_data_dir", DEFAULT_USER_DATA_DIR),
            backstop_total=getattr(args, "backstop_total", None),
            update=getattr(args, "update", False),
        )
        handle_run_default(namespace)
    elif args.command == "selenium-launch-chrome":
        handle_selenium_launch_chrome(args)
    elif args.command == "selenium-fetch-beers":
        handle_selenium_fetch_beers(args)
    elif args.command == "streamlit":
        run_streamlit_app()
    else:
        raise SystemExit("Unsupported command.")


if __name__ == "__main__":
    main()
