import json
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urljoin
from urllib.request import urlopen

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from tqdm import tqdm
from webdriver_manager.chrome import ChromeDriverManager

from paths import (
    BEER_DETAILS_CACHE_PATH,
    VENUE_COORDINATES_CACHE_PATH,
    ensure_data_dir,
)


UNTAPPD_BASE = "https://untappd.com"
CSV_COLUMNS = [
    "Beer Name",
    "Producer",
    "Consumed Location",
    "Lat",
    "Long",
    "Beer Type",
    "My Rating",
    "Global Rating",
    "Recent Date",
    "Total Checkins",
]


def load_json_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_json_cache(path: Path, cache: dict) -> None:
    ensure_data_dir()
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def load_beer_details_cache() -> dict[str, list[str]]:
    return load_json_cache(BEER_DETAILS_CACHE_PATH)


def load_venue_coordinates_cache() -> dict[str, list[str]]:
    return load_json_cache(VENUE_COORDINATES_CACHE_PATH)


def save_scrape_caches(
    beer_stats_cache: dict[str, list[str]],
    coordinate_cache: dict[str, list[str]],
) -> None:
    save_json_cache(BEER_DETAILS_CACHE_PATH, beer_stats_cache)
    save_json_cache(VENUE_COORDINATES_CACHE_PATH, coordinate_cache)


def _raise_if_stopped(stop_requested: Optional[Callable[[], bool]]) -> None:
    if stop_requested and stop_requested():
        from app_runtime import TaskCancelled

        raise TaskCancelled()


def chrome_service() -> ChromeService:
    chromedriver_path = shutil.which("chromedriver")
    if chromedriver_path:
        return ChromeService(chromedriver_path)
    return ChromeService(ChromeDriverManager().install())


def create_chrome_driver_from_debugger(debugger_address: str) -> webdriver.Remote:
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", debugger_address)
    return webdriver.Chrome(service=chrome_service(), options=options)


def is_debugger_ready(debugger_address: str, timeout: float = 2.0) -> bool:
    host, _, port_text = debugger_address.partition(":")
    if not host or not port_text.isdigit():
        return False
    try:
        with socket.create_connection((host, int(port_text)), timeout=timeout):
            pass
        with urlopen(f"http://{debugger_address}/json/version", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return bool(payload.get("Browser"))
    except Exception:
        return False


def wait_for_debugger(debugger_address: str, timeout: int = 20) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_debugger_ready(debugger_address):
            return True
        time.sleep(0.5)
    return False


def default_chrome_user_data_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return str(Path(base) / "Untappd Beer History" / "ChromeProfile")
        return str(Path.home() / "AppData" / "Local" / "Untappd Beer History" / "ChromeProfile")
    return "/tmp/untappd-manual"


def find_chrome_binary() -> Optional[str]:
    names = ["google-chrome", "chrome", "chromium", "chromium-browser"]
    if sys.platform == "win32":
        names = ["chrome.exe", "chrome", *names]
        for root in (
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        ):
            if not root:
                continue
            candidate = Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if candidate.exists():
                return str(candidate)
    for name in names:
        binary = shutil.which(name)
        if binary:
            return binary
    return None


def launch_chrome_with_debugger(
    debugger_address: str = "127.0.0.1:9222",
    user_data_dir: Optional[str] = None,
    start_url: Optional[str] = None,
    headless: bool = True,
) -> None:
    host, _, port = debugger_address.partition(":")
    if not host or not port.isdigit():
        raise ValueError("Debugger address must look like 127.0.0.1:9222")
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("For safety, debugger host must be 127.0.0.1 or localhost.")

    start_url = start_url or f"{UNTAPPD_BASE}/user/login"
    user_data_dir = user_data_dir or default_chrome_user_data_dir()
    Path(user_data_dir).expanduser().mkdir(parents=True, exist_ok=True)
    chrome_args = [
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--new-window",
        start_url,
    ]
    if headless:
        chrome_args.extend(["--headless=new", "--disable-gpu", "--window-size=1920,1080"])

    if sys.platform == "darwin" and shutil.which("open"):
        subprocess.Popen(["open", "-na", "Google Chrome", "--args", *chrome_args])
        return
    chrome_binary = find_chrome_binary()
    if chrome_binary:
        subprocess.Popen([chrome_binary, *chrome_args])
        return
    raise RuntimeError("Could not find Google Chrome.")


def start_manual_login(
    browser: str = "chrome",
    headless: bool = True,
    attach_debugger: Optional[str] = None,
) -> webdriver.Remote:
    if browser != "chrome" or not attach_debugger:
        raise ValueError("This scraper requires Chrome attached through a debugger address.")
    return create_chrome_driver_from_debugger(attach_debugger)


def activate_untappd_tab(driver: webdriver.Remote, target_url: str) -> None:
    """Select an Untappd tab or create one when ChromeDriver attached elsewhere."""
    for handle in driver.window_handles:
        try:
            driver.switch_to.window(handle)
            if "untappd.com" in (driver.current_url or "").casefold():
                driver.get(target_url)
                return
        except Exception:
            continue

    driver.switch_to.new_window("tab")
    driver.get(target_url)
    try:
        current_url = driver.current_url or ""
    except Exception:
        current_url = ""
    if "untappd.com" not in current_url.casefold():
        raise RuntimeError(
            "Chrome did not open the dedicated Untappd tab. "
            f"Navigation remained on: {current_url or 'unknown'}."
        )


def _login_required(driver: webdriver.Remote) -> bool:
    try:
        current_url = driver.current_url.lower()
    except Exception:
        current_url = ""
    try:
        title = driver.title.lower()
    except Exception:
        title = ""
    return "/login" in current_url or "login" in title or "just a moment" in title


def wait_for_manual_login(
    driver: webdriver.Remote,
    timeout: int = 300,
    stop_requested: Optional[Callable[[], bool]] = None,
) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        _raise_if_stopped(stop_requested)
        if not _login_required(driver):
            return
        time.sleep(0.5)
    raise TimeoutException("Manual login was not completed before timeout.")


def prompt_manual_login(
    driver: webdriver.Remote,
    username: str,
    timeout: int = 300,
    stop_requested: Optional[Callable[[], bool]] = None,
) -> None:
    user_url = f"{UNTAPPD_BASE}/user/{username}"
    activate_untappd_tab(driver, user_url)
    if _login_required(driver):
        print("Complete the Untappd login in Chrome. The app will continue automatically.")
        wait_for_manual_login(driver, timeout=timeout, stop_requested=stop_requested)
    driver.get(user_url)
    time.sleep(2)


def click_show_more(driver: webdriver.Remote) -> bool:
    for button in reversed(driver.find_elements(By.XPATH, "//*[contains(normalize-space(), 'Show More')]")):
        try:
            if "show more" not in (button.text or "").strip().lower() or not button.is_displayed():
                continue
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
            driver.execute_script("arguments[0].click();", button)
            return True
        except Exception:
            continue
    return False


def _text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def _checkin_identity(beer_name: str, producer_name: str, recent_date: str) -> tuple[str, str, str]:
    parsed_date = pd.to_datetime(recent_date, errors="coerce", utc=True)
    normalized_date = "" if pd.isna(parsed_date) else parsed_date.isoformat()
    return (
        str(beer_name or "").strip().casefold(),
        str(producer_name or "").strip().casefold(),
        normalized_date,
    )


def checkin_identity_from_row(row) -> tuple[str, str, str]:
    return _checkin_identity(
        row.get("Beer Name"),
        row.get("Producer"),
        row.get("Recent Date"),
    )


def _checkin_anchors(checkin):
    sentence = checkin.select_one(".checkin .top p.text")
    if sentence is None:
        raise ValueError("Check-in does not contain the expected patterned sentence.")

    beer = sentence.find("a", href=lambda href: href and "/b/" in href)
    venue = sentence.find("a", href=lambda href: href and ("/v/" in href or "/venue/" in href))
    recent_date = checkin.select_one(".checkin .bottom a.time[data-gregtime]")

    producer = None
    if beer is not None:
        for anchor in beer.find_all_next("a"):
            if anchor.parent is not sentence:
                continue
            if venue is not None and anchor is venue:
                break
            producer = anchor
            break
    if beer is None or producer is None:
        raise ValueError("Could not find the beer and producer links.")
    return beer, producer, venue, recent_date


def checkin_identity_from_card(checkin) -> tuple[str, str, str]:
    beer, producer, _venue, recent_date_anchor = _checkin_anchors(checkin)
    recent_date = str(recent_date_anchor.get("data-gregtime", "")) if recent_date_anchor else ""
    return _checkin_identity(_text(beer), _text(producer), recent_date)


def get_coordinates(venue_html: str) -> tuple[str, str]:
    soup = BeautifulSoup(venue_html, "html.parser")
    latitude_meta = soup.find("meta", property="place:location:latitude")
    longitude_meta = soup.find("meta", property="place:location:longitude")
    if latitude_meta and longitude_meta:
        return str(latitude_meta.get("content", "")), str(longitude_meta.get("content", ""))

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        for entry in data if isinstance(data, list) else [data]:
            if not isinstance(entry, dict):
                continue
            geo = entry.get("geo", {})
            if isinstance(geo, dict) and "latitude" in geo and "longitude" in geo:
                return str(geo["latitude"]), str(geo["longitude"])
    return "", ""


def get_beer_page_stats(beer_html: str) -> tuple[str, str, str]:
    soup = BeautifulSoup(beer_html, "html.parser")
    rating = soup.select_one(".beer-page .details .caps[data-rating]")
    global_rating = str(rating.get("data-rating", "")) if rating else ""
    beer_type = _text(soup.select_one(".beer-page .details p.style") or soup.select_one("p.style"))

    total_checkins = ""
    for stat_group in soup.select(".beer-page .stats p"):
        stat = stat_group.select_one(".stat")
        if stat and _text(stat).casefold() == "you":
            total_checkins = _text(stat_group.select_one(".count"))
            break
    return global_rating, beer_type, total_checkins


def get_global_rating(beer_html: str) -> str:
    return get_beer_page_stats(beer_html)[0]


def _load_page_in_temporary_tab(driver: webdriver.Remote, url: str) -> str:
    original_window = driver.current_window_handle
    page_source = ""
    try:
        driver.switch_to.new_window("tab")
        driver.get(url)
        WebDriverWait(driver, 15).until(
            lambda current_driver: current_driver.execute_script("return document.readyState") == "complete"
        )
        page_source = driver.page_source
    finally:
        try:
            if driver.current_window_handle != original_window:
                driver.close()
        except WebDriverException:
            pass
        try:
            driver.switch_to.window(original_window)
        except WebDriverException:
            pass
    return page_source


def get_checkin_details(
    driver: webdriver.Remote,
    checkin,
    beer_stats_cache: Optional[dict[str, list[str]]] = None,
    coordinate_cache: Optional[dict[str, list[str]]] = None,
) -> tuple[str, str, str, str, str, str, str, str, str]:
    beer, producer, venue, recent_date_anchor = _checkin_anchors(checkin)
    beer_name = _text(beer)
    producer_name = _text(producer)
    recent_date = str(recent_date_anchor.get("data-gregtime", "")) if recent_date_anchor else ""
    beer_url = urljoin(UNTAPPD_BASE, beer["href"])

    beer_stats_cache = beer_stats_cache if beer_stats_cache is not None else {}
    beer_key = beer_url.casefold()
    beer_stats = beer_stats_cache.get(beer_key)
    if not isinstance(beer_stats, (list, tuple)) or len(beer_stats) != 3:
        beer_stats = None
    if beer_stats is None:
        global_rating = ""
        beer_type = ""
        total_checkins = ""
        try:
            global_rating, beer_type, total_checkins = get_beer_page_stats(
                _load_page_in_temporary_tab(driver, beer_url)
            )
        except (TimeoutException, WebDriverException) as error:
            print(f"Could not load beer details for {beer_name}: {type(error).__name__}")
        beer_stats = [global_rating, beer_type, total_checkins]
        if any(beer_stats):
            beer_stats_cache[beer_key] = beer_stats
    global_rating, beer_type, total_checkins = beer_stats

    consumed_location = _text(venue)
    if venue is None:
        return (
            beer_name,
            producer_name,
            beer_type,
            global_rating,
            total_checkins,
            recent_date,
            "",
            "",
            "",
        )

    coordinate_cache = coordinate_cache if coordinate_cache is not None else {}
    venue_url = urljoin(UNTAPPD_BASE, venue["href"])
    cache_key = venue_url.casefold()
    coordinates = coordinate_cache.get(cache_key)
    if not isinstance(coordinates, (list, tuple)) or len(coordinates) != 2:
        coordinates = None
    if coordinates is None:
        try:
            latitude, longitude = get_coordinates(_load_page_in_temporary_tab(driver, venue_url))
            coordinates = [latitude, longitude]
            if latitude or longitude:
                coordinate_cache[cache_key] = coordinates
        except (TimeoutException, WebDriverException) as error:
            print(f"Could not load coordinates for {consumed_location}: {type(error).__name__}")
            coordinates = ["", ""]
    latitude, longitude = coordinates
    return (
        beer_name,
        producer_name,
        beer_type,
        global_rating,
        total_checkins,
        recent_date,
        consumed_location,
        latitude,
        longitude,
    )


def get_checkin_rating(checkin) -> str:
    rating = checkin.select_one("[data-rating]")
    return str(rating.get("data-rating", "")) if rating else ""


def find_checkins(soup: BeautifulSoup):
    return soup.select("div.item[data-checkin-id]")


def load_user_checkin_page(
    driver: webdriver.Remote,
    username: str,
    timeout: int = 30,
    stop_requested: Optional[Callable[[], bool]] = None,
) -> None:
    user_url = f"{UNTAPPD_BASE}/user/{username}"
    activate_untappd_tab(driver, user_url)
    for attempt in range(1, 3):
        _raise_if_stopped(stop_requested)
        print(f"Loading Untappd check-ins for {username} (attempt {attempt}/2)...")
        driver.get(user_url)

        deadline = time.time() + timeout
        while time.time() < deadline:
            _raise_if_stopped(stop_requested)
            if _login_required(driver):
                wait_for_manual_login(
                    driver,
                    timeout=max(1, int(deadline - time.time())),
                    stop_requested=stop_requested,
                )
                driver.get(user_url)

            soup = BeautifulSoup(driver.page_source, "html.parser")
            if find_checkins(soup):
                return
            time.sleep(0.5)

        if attempt == 1:
            print("No check-in cards appeared; refreshing the user page and trying once more.")

    try:
        current_url = driver.current_url
    except Exception:
        current_url = "unknown"
    try:
        page_title = driver.title
    except Exception:
        page_title = "unknown"
    raise RuntimeError(
        "Untappd did not return any check-in cards after two attempts. "
        "The update was not saved. Complete any login or Cloudflare prompt in Chrome, then retry. "
        f"Final URL: {current_url}. Page title: {page_title}."
    )


def scroll_until_all_checkins_loaded(
    driver: webdriver.Remote,
    backstop_total: Optional[int] = None,
    max_passes: int = 200,
    stop_requested: Optional[Callable[[], bool]] = None,
) -> BeautifulSoup:
    previous_count = -1
    unchanged_passes = 0
    for _ in range(max_passes):
        _raise_if_stopped(stop_requested)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        current_count = len(find_checkins(soup))
        if backstop_total is not None and current_count >= backstop_total:
            return soup
        unchanged_passes = unchanged_passes + 1 if current_count == previous_count else 0
        previous_count = current_count
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        clicked = click_show_more(driver)
        time.sleep(2 if clicked else 1.5)
        if not clicked and unchanged_passes >= 2:
            return BeautifulSoup(driver.page_source, "html.parser")
    return BeautifulSoup(driver.page_source, "html.parser")


def fetch_checkin_rows(
    driver: webdriver.Remote,
    username: str,
    login_timeout: int = 300,
    backstop_total: Optional[int] = None,
    existing_checkin_keys: Optional[set[tuple[str, str, str]]] = None,
    stop_requested: Optional[Callable[[], bool]] = None,
) -> list[dict]:
    load_user_checkin_page(
        driver,
        username,
        timeout=min(login_timeout, 30),
        stop_requested=stop_requested,
    )

    soup = scroll_until_all_checkins_loaded(
        driver,
        backstop_total=backstop_total,
        stop_requested=stop_requested,
    )
    rows = []
    beer_stats_cache = load_beer_details_cache()
    coordinate_cache = load_venue_coordinates_cache()
    initial_beer_cache_size = len(beer_stats_cache)
    initial_venue_cache_size = len(coordinate_cache)
    print(
        f"Loaded persistent caches: {initial_beer_cache_size:,} beers and "
        f"{initial_venue_cache_size:,} venues."
    )
    checkins = find_checkins(soup)
    if not checkins:
        raise RuntimeError(
            "Untappd check-in cards disappeared before they could be processed. "
            "The update was not saved; retry after the user page finishes loading."
        )
    loaded_count = len(checkins)
    if backstop_total is not None:
        checkins = checkins[:backstop_total]
        if loaded_count < backstop_total:
            print(
                f"Untappd returned {loaded_count:,} check-ins, below the "
                f"{backstop_total:,} target. The update will use all available check-ins."
            )

    existing_checkin_keys = existing_checkin_keys or set()
    if existing_checkin_keys:
        new_checkins = []
        skipped_existing = 0
        for checkin in checkins:
            try:
                key = checkin_identity_from_card(checkin)
            except ValueError:
                new_checkins.append(checkin)
                continue
            if key in existing_checkin_keys:
                skipped_existing += 1
            else:
                new_checkins.append(checkin)
        checkins = new_checkins
        print(
            f"Found {skipped_existing:,} check-ins already in the CSV; "
            f"{len(checkins):,} new check-ins need detail pulls."
        )

    if not checkins:
        print("No new check-ins were found. The existing CSV will be preserved.")
        return []

    print(
        f"Pulling details for {len(checkins):,} check-ins. "
        "The completion estimate will stabilize after the first few pulls."
    )
    try:
        with tqdm(
            checkins,
            desc="Check-in data",
            unit="check-in",
            file=sys.stdout,
            disable=False,
            ascii=True,
            mininterval=0.5,
            smoothing=0.2,
            bar_format="{l_bar}{bar:30}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]{postfix}",
        ) as progress:
            for checkin in progress:
                _raise_if_stopped(stop_requested)
                try:
                    (
                        beer_name,
                        producer,
                        beer_type,
                        global_rating,
                        total_checkins,
                        recent_date,
                        consumed_location,
                        latitude,
                        longitude,
                    ) = get_checkin_details(driver, checkin, beer_stats_cache, coordinate_cache)
                except ValueError as error:
                    print(f"Skipping check-in {checkin.get('data-checkin-id', 'unknown')}: {error}")
                    continue
                rows.append(
                    {
                        "Beer Name": beer_name,
                        "Producer": producer,
                        "Consumed Location": consumed_location,
                        "Lat": latitude,
                        "Long": longitude,
                        "Beer Type": beer_type,
                        "My Rating": get_checkin_rating(checkin),
                        "Global Rating": global_rating,
                        "Recent Date": recent_date,
                        "Total Checkins": total_checkins,
                    }
                )
                progress.set_postfix(
                    beers=len(beer_stats_cache),
                    venues=len(coordinate_cache),
                    refresh=False,
                )
    finally:
        save_scrape_caches(beer_stats_cache, coordinate_cache)
        print(
            f"Saved persistent caches: {len(beer_stats_cache):,} beers and "
            f"{len(coordinate_cache):,} venues."
        )
    print(f"Completed data pulls for {len(rows):,} of {len(checkins):,} check-ins.")
    return rows


def fetch_beers(
    driver: webdriver.Remote,
    username: str,
    backstop_total: Optional[int] = None,
    existing_checkin_keys: Optional[set[tuple[str, str, str]]] = None,
    stop_requested: Optional[Callable[[], bool]] = None,
    login_timeout: int = 300,
) -> pd.DataFrame:
    rows = fetch_checkin_rows(
        driver,
        username,
        login_timeout=login_timeout,
        backstop_total=backstop_total,
        existing_checkin_keys=existing_checkin_keys,
        stop_requested=stop_requested,
    )
    return pd.DataFrame(rows, columns=CSV_COLUMNS)


def quit_driver(driver: webdriver.Remote) -> None:
    try:
        driver.quit()
    except Exception:
        pass
