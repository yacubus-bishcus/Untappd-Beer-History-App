import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from app_config import get_configured_username
from app_runtime import TaskCancelled
from paths import DEFAULT_OUTPUT_PATH
from untappd_scraper import (
    CSV_COLUMNS,
    checkin_identity_from_row,
    default_chrome_user_data_dir,
    fetch_beers as selenium_fetch_beers,
    is_debugger_ready,
    launch_chrome_with_debugger,
    prompt_manual_login as selenium_prompt_manual_login,
    start_manual_login as selenium_start_manual_login,
    wait_for_debugger,
    quit_driver,
)

DEFAULT_USERNAME = get_configured_username("")
DEFAULT_DEBUGGER_ADDRESS = "127.0.0.1:9222"
DEFAULT_OUTPUT = str(DEFAULT_OUTPUT_PATH)

DEFAULT_USER_DATA_DIR = default_chrome_user_data_dir()


def ensure_supported_python():
    version = sys.version_info
    if version.major != 3 or version.minor < 9:
        raise SystemExit(
            f"Unsupported Python version: {version.major}.{version.minor}. "
            "Use Python 3.9 or newer for this project."
        )


def open_statistics_ui():
    print("Opening native statistics UI...")
    from untappd_beer_history.app import main as create_statistics_ui

    app = create_statistics_ui()
    app.main_loop()


def open_statistics_report(output: str):
    print("Opening browser statistics report...")
    from cli_statistics import open_statistics_report as open_cli_statistics_report

    return open_cli_statistics_report(output)


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


def load_existing_history(output_path: Path, clean_run: bool) -> pd.DataFrame:
    if clean_run or not output_path.exists():
        return pd.DataFrame(columns=CSV_COLUMNS)
    return pd.read_csv(output_path)


def existing_checkin_keys(df: pd.DataFrame) -> set[tuple[str, str, str]]:
    if df.empty:
        return set()
    return {
        checkin_identity_from_row(row)
        for _, row in df.iterrows()
    }


def merge_checkin_history(existing_df: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
    if existing_df.empty:
        combined = new_df.copy()
    elif new_df.empty:
        combined = existing_df.copy()
    else:
        combined = pd.concat([new_df, existing_df], ignore_index=True)

    if combined.empty:
        return pd.DataFrame(columns=CSV_COLUMNS)

    combined = combined.copy()
    combined["_checkin_key"] = [
        checkin_identity_from_row(row)
        for _, row in combined.iterrows()
    ]
    combined = combined.drop_duplicates(subset="_checkin_key", keep="first")
    combined["_sort_date"] = pd.to_datetime(combined["Recent Date"], errors="coerce", utc=True)
    combined = combined.sort_values("_sort_date", ascending=False, na_position="last")
    combined = combined.drop(columns=["_checkin_key", "_sort_date"]).reset_index(drop=True)
    return combined.reindex(columns=CSV_COLUMNS)


def resolve_backstop_total(
    output_path: Path,
    provided_backstop_total: Optional[int],
    clean_run: bool = False,
) -> Optional[int]:
    # An explicit --backstop-total should always win, even during --clean-run.
    # Clean-run only disables the implicit backstop inferred from the existing CSV.
    if provided_backstop_total is not None:
        return provided_backstop_total
    if clean_run:
        return None
    existing_rows = count_csv_rows(output_path)
    return existing_rows or None


def describe_backstop_mode(
    clean_run: bool,
    effective_backstop_total: Optional[int],
    existing_count: int = 0,
):
    if clean_run and effective_backstop_total is not None:
        print(
            "Clean run enabled: ignoring existing CSV data and stopping after "
            f"{effective_backstop_total} visible check-ins."
        )
    elif clean_run:
        print("Clean run enabled: ignoring existing CSV/backstop and fetching until Show More is exhausted.")
    elif effective_backstop_total is not None:
        additional_target = max(0, effective_backstop_total - existing_count)
        print(
            f"Update target: {effective_backstop_total:,} total check-ins. "
            f"Existing CSV: {existing_count:,}. "
            f"Up to {additional_target:,} additional check-ins will be pulled if they exist."
        )
    else:
        print("No backstop total available. The scraper will stop when Show More is exhausted.")


def perform_beer_fetch_workflow(
    username: str,
    debugger_address: str,
    output: str,
    backstop_total: Optional[int],
    user_data_dir: str,
    clean_run: bool = False,
    stop_requested: Optional[Callable[[], bool]] = None,
    on_driver_ready: Optional[Callable[[object], None]] = None,
):
    stop_requested = stop_requested or (lambda: False)

    def ensure_not_stopped():
        if stop_requested():
            raise TaskCancelled()

    if not username:
        raise SystemExit(
            "No Untappd username is configured yet. Please launch from the desktop starter first "
            "or pass --username explicitly."
        )
    output_path = Path(output)
    existing_df = load_existing_history(output_path, clean_run=clean_run)
    effective_backstop_total = resolve_backstop_total(output_path, backstop_total, clean_run=clean_run)
    describe_backstop_mode(clean_run, effective_backstop_total, existing_count=len(existing_df))

    launch_url = f"https://untappd.com/user/{username}"
    ensure_not_stopped()
    if not is_debugger_ready(debugger_address):
        print(f"Launching Chrome for manual login at {launch_url}...")
        launch_chrome_with_debugger(
            debugger_address=debugger_address,
            user_data_dir=user_data_dir,
            start_url=launch_url,
        )
        if not wait_for_debugger(debugger_address, timeout=20):
            raise RuntimeError(f"Could not connect to Chrome debugger at {debugger_address}.")
    else:
        print(f"Using the existing Chrome debugger at {debugger_address}...")

    driver = None
    try:
        ensure_not_stopped()
        time.sleep(2)
        print(f"Attaching Selenium to Chrome at {debugger_address}...")
        driver = selenium_start_manual_login(
            browser="chrome",
            headless=True,
            attach_debugger=debugger_address,
        )
        if on_driver_ready is not None:
            on_driver_ready(driver)
        selenium_prompt_manual_login(driver, username, timeout=300, stop_requested=stop_requested)

        ensure_not_stopped()
        print(f"Fetching beer history for {username}...")
        df = selenium_fetch_beers(
            driver,
            username=username,
            backstop_total=effective_backstop_total,
            existing_checkin_keys=existing_checkin_keys(existing_df),
            stop_requested=stop_requested,
        )
        ensure_not_stopped()
        merged_df = merge_checkin_history(existing_df, df)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        merged_df.to_csv(output_path, index=False)
        print(
            f"Saved {len(merged_df):,} total check-ins to {output_path} "
            f"({len(df):,} added during this update)."
        )
    finally:
        if driver is not None:
            quit_driver(driver)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Selenium-based Untappd beer history exporter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Default behavior:
  python src/run.py

Examples:
  python src/run.py selenium-launch-chrome
  python src/run.py selenium-fetch-beers
  python src/run.py selenium-fetch-beers --backstop-total 250
        """,
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Force a fresh Untappd download even if data/my_beers.csv already exists",
    )
    parser.add_argument(
        "--clean-run",
        action="store_true",
        help="Ignore existing CSV/backstop data and fetch all visible check-ins from scratch",
    )
    parser.add_argument(
        "--no-ui",
        action="store_true",
        help="Run the default workflow without opening the native app; open the browser statistics report instead",
    )
    parser.add_argument(
        "--username",
        default=DEFAULT_USERNAME,
        help="Untappd username for the default python src/run.py workflow",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=DEFAULT_OUTPUT,
        help="Output CSV path for the default python src/run.py workflow",
    )
    parser.add_argument(
        "--debugger-address",
        default=DEFAULT_DEBUGGER_ADDRESS,
        help="Chrome debugger address for the default python src/run.py workflow",
    )
    parser.add_argument(
        "--user-data-dir",
        default=DEFAULT_USER_DATA_DIR,
        help="Chrome profile directory for the default python src/run.py workflow",
    )
    parser.add_argument(
        "--backstop-total",
        type=int,
        help="Optional maximum check-in count for the default python src/run.py workflow",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    selenium_launch_chrome_parser = subparsers.add_parser(
        "selenium-launch-chrome",
        help="Launch a real Chrome window with remote debugging for manual Untappd login",
    )
    selenium_launch_chrome_parser.add_argument("--page", default="beers", choices=["login", "beers"])
    selenium_launch_chrome_parser.add_argument("--username", default=DEFAULT_USERNAME)
    selenium_launch_chrome_parser.add_argument("--debugger-address", default=DEFAULT_DEBUGGER_ADDRESS)
    selenium_launch_chrome_parser.add_argument("--user-data-dir", default=DEFAULT_USER_DATA_DIR)

    selenium_fetch_beers_parser = subparsers.add_parser(
        "selenium-fetch-beers",
        help="Fetch check-in history from the Untappd user page using Selenium",
    )
    selenium_fetch_beers_parser.add_argument("--username", default=DEFAULT_USERNAME)
    selenium_fetch_beers_parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT)
    selenium_fetch_beers_parser.add_argument("--attach-debugger", default=DEFAULT_DEBUGGER_ADDRESS)
    selenium_fetch_beers_parser.add_argument("--user-data-dir", default=DEFAULT_USER_DATA_DIR)
    selenium_fetch_beers_parser.add_argument("--timeout", type=int, default=300)
    selenium_fetch_beers_parser.add_argument("--backstop-total", type=int)
    selenium_fetch_beers_parser.add_argument(
        "--clean-run",
        action="store_true",
        help="Ignore existing CSV/backstop data and fetch until Show More is exhausted",
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
    run_default_parser.add_argument("--update", action="store_true")
    run_default_parser.add_argument("--clean-run", action="store_true")
    run_default_parser.add_argument("--no-ui", action="store_true")

    return parser.parse_args()


def handle_selenium_launch_chrome(args):
    if not args.username:
        raise SystemExit("No Untappd username is configured yet. Pass --username explicitly.")
    if args.page == "login":
        start_url = "https://untappd.com/user/login"
    else:
        start_url = f"https://untappd.com/user/{args.username}"

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
    existing_df = load_existing_history(output_path, clean_run=args.clean_run)
    effective_backstop_total = resolve_backstop_total(
        output_path,
        args.backstop_total,
        clean_run=args.clean_run,
    )
    describe_backstop_mode(args.clean_run, effective_backstop_total, existing_count=len(existing_df))

    if not is_debugger_ready(args.attach_debugger):
        start_url = f"https://untappd.com/user/{args.username}"
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
        selenium_prompt_manual_login(driver, args.username, timeout=args.timeout)

        print(f"Fetching beer history from {args.username}...")
        df = selenium_fetch_beers(
            driver,
            args.username,
            backstop_total=effective_backstop_total,
            existing_checkin_keys=existing_checkin_keys(existing_df),
        )
        merged_df = merge_checkin_history(existing_df, df)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        merged_df.to_csv(output_path, index=False)
        print(
            f"Saved {len(merged_df):,} total check-ins to {output_path} "
            f"({len(df):,} added during this update)."
        )
    finally:
        if driver is not None:
            quit_driver(driver)


def handle_run_default(args):
    output_path = Path(args.output)
    if output_path.exists() and not args.update and not args.clean_run:
        print(f"Found existing {output_path}. Skipping Untappd download. Use --update to refresh.")
        if args.no_ui:
            open_statistics_report(args.output)
        else:
            open_statistics_ui()
        return

    perform_beer_fetch_workflow(
        username=args.username,
        debugger_address=args.debugger_address,
        output=args.output,
        backstop_total=args.backstop_total,
        user_data_dir=args.user_data_dir,
        clean_run=args.clean_run,
    )
    if args.no_ui:
        open_statistics_report(args.output)
    else:
        open_statistics_ui()


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
            clean_run=getattr(args, "clean_run", False),
            no_ui=getattr(args, "no_ui", False),
        )
        handle_run_default(namespace)
    elif args.command == "selenium-launch-chrome":
        handle_selenium_launch_chrome(args)
    elif args.command == "selenium-fetch-beers":
        handle_selenium_fetch_beers(args)
    else:
        raise SystemExit("Unsupported command.")


if __name__ == "__main__":
    main()
