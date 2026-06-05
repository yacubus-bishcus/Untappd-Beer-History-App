import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from urllib.request import urlopen
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from paths import DATA_DIR, PRODUCER_LOCATION_CACHE_PATH, ensure_data_dir

UNTAPPD_BASE = "https://untappd.com"
CREDENTIALS_FILE = ".untappd_credentials_selenium"
BROWSER_CHOICES = {"firefox", "chrome"}


def _stop_requested(stop_requested) -> bool:
    return bool(stop_requested and stop_requested())


def _raise_if_stopped(stop_requested):
    if _stop_requested(stop_requested):
        from app_runtime import TaskCancelled

        raise TaskCancelled()


def get_credentials_path():
    return Path.home() / ".untappd" / CREDENTIALS_FILE


def get_producer_location_cache_path():
    ensure_data_dir()
    return PRODUCER_LOCATION_CACHE_PATH


def get_consumed_location_cache_path():
    ensure_data_dir()
    return DATA_DIR / "consumed_location_cache.json"


def get_debug_snapshot_path() -> Path:
    ensure_data_dir()
    return PRODUCER_LOCATION_CACHE_PATH.parent / "beer_page_debug.html"


def ensure_credentials_dir():
    cred_dir = Path.home() / ".untappd"
    cred_dir.mkdir(exist_ok=True, parents=True)


def save_credentials(username: str, password: str):
    """Save Untappd login credentials to disk."""
    ensure_credentials_dir()
    creds = {
        "username": username,
        "password": password,
        "auth_method": "selenium",
    }
    with open(get_credentials_path(), "w") as f:
        json.dump(creds, f, indent=2)
    os.chmod(get_credentials_path(), 0o600)


def load_credentials() -> dict:
    """Load Untappd credentials from disk."""
    cred_path = get_credentials_path()
    if not cred_path.exists():
        return {}
    with open(cred_path, "r") as f:
        return json.load(f)


def load_producer_location_cache() -> dict:
    cache_path = get_producer_location_cache_path()
    return load_json_cache(cache_path)


def save_producer_location_cache(cache: dict):
    save_json_cache(get_producer_location_cache_path(), cache)


def load_consumed_location_cache() -> dict:
    return load_json_cache(get_consumed_location_cache_path())


def save_consumed_location_cache(cache: dict):
    save_json_cache(get_consumed_location_cache_path(), cache)


def load_json_cache(cache_path: Path) -> dict:
    if not cache_path.exists():
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_json_cache(cache_path: Path, cache: dict):
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False, sort_keys=True)


def chrome_service() -> ChromeService:
    chromedriver_path = shutil.which("chromedriver")
    if chromedriver_path:
        return ChromeService(chromedriver_path)
    return ChromeService(ChromeDriverManager().install())


def create_driver(headless: bool = True, browser: str = "firefox") -> webdriver.Remote:
    """Create and configure a Selenium WebDriver (Firefox or Chrome)."""
    browser = browser.lower()
    if browser not in BROWSER_CHOICES:
        supported = ", ".join(sorted(BROWSER_CHOICES))
        raise ValueError(f"Unsupported browser '{browser}'. Supported: {supported}.")

    if browser == "chrome":
        options = webdriver.ChromeOptions()
    else:
        options = webdriver.FirefoxOptions()
        firefox_binary = shutil.which("firefox")
        if firefox_binary:
            options.binary_location = firefox_binary
        else:
            raise RuntimeError(
                "Firefox browser binary not found. Install Firefox or rerun with '--browser chrome'."
            )

    if headless:
        options.add_argument("--headless")

    # Avoid being detected as a bot
    if browser == "firefox":
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference("useAutomationExtension", False)
    else:
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("--disable-blink-features=AutomationControlled")

    # Set a realistic user agent
    options.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    )

    try:
        if browser == "chrome":
            service = chrome_service()
            driver = webdriver.Chrome(service=service, options=options)
        else:
            service = FirefoxService(GeckoDriverManager().install())
            driver = webdriver.Firefox(service=service, options=options)
    except Exception as e:
        browser_name = browser.capitalize()
        print(f"Error setting up {browser_name} WebDriver: {e}")
        raise

    return driver


def create_chrome_driver_from_debugger(debugger_address: str) -> webdriver.Remote:
    """
    Attach Selenium to an already-running local Chrome instance.
    This allows manual login/CAPTCHA handling in a real browser profile first.
    """
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", debugger_address)
    service = chrome_service()
    return webdriver.Chrome(service=service, options=options)


def is_debugger_ready(debugger_address: str, timeout: float = 2.0) -> bool:
    """
    Check whether Chrome's remote debugger endpoint is reachable.
    """
    host, _, port_text = debugger_address.partition(":")
    if not host or not port_text.isdigit():
        return False

    try:
        with socket.create_connection((host, int(port_text)), timeout=timeout):
            pass
    except OSError:
        return False

    try:
        with urlopen(f"http://{debugger_address}/json/version", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return bool(payload.get("Browser"))
    except Exception:
        return False


def wait_for_debugger(debugger_address: str, timeout: int = 20) -> bool:
    """
    Wait for a Chrome debugger endpoint to become available.
    """
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
        candidate_roots = [
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        ]
        for root in candidate_roots:
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
):
    """
    Launch a standalone Chrome window with remote debugging enabled.
    This is useful when you want to log in manually with a real profile window
    and later attach Selenium to that same browser.
    """
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

    if sys.platform == "darwin" and shutil.which("open"):
        command = ["open", "-na", "Google Chrome", "--args", *chrome_args]
        subprocess.Popen(command)
        return

    chrome_binary = find_chrome_binary()
    if chrome_binary:
        subprocess.Popen([chrome_binary, *chrome_args])
        return

    raise RuntimeError(
        "Could not find Google Chrome. Launch Chrome manually with remote debugging enabled instead."
    )


def login(
    username: str,
    password: str,
    headless: bool = True,
    browser: str = "firefox",
) -> webdriver.Remote:
    """
    Log into Untappd using Selenium.
    Returns the authenticated WebDriver.
    """
    print(f"Starting {browser.capitalize()} browser...")
    driver = create_driver(headless=headless, browser=browser)

    try:
        # Navigate to login page
        print("Navigating to Untappd login page...")
        driver.get(f"{UNTAPPD_BASE}/user/login")
        
        # Wait for page to load
        time.sleep(2)
        
        # Find and fill username field
        print("Logging in...")
        try:
            username_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "username"))
            )
            username_field.send_keys(username)
        except TimeoutException:
            raise ValueError("Could not find username field on login page")
        
        # Find and fill password field
        try:
            password_field = driver.find_element(By.NAME, "password")
            password_field.send_keys(password)
        except NoSuchElementException:
            raise ValueError("Could not find password field on login page")
        
        # Find and click login button
        try:
            login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
            login_button.click()
        except NoSuchElementException:
            raise ValueError("Could not find login button")
        
        # Wait for redirect after login
        print("Waiting for login to complete...")
        time.sleep(3)
        
        # Check if login was successful
        current_url = driver.current_url
        if "login" in current_url.lower():
            # Still on login page, check for error message
            page_text = driver.page_source.lower()
            if "invalid" in page_text or "incorrect" in page_text:
                raise ValueError("Login failed: invalid username or password")
            raise ValueError("Login failed: unable to authenticate")
        
        # Verify we're logged in by checking for user menu
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, f"//a[contains(@href, '/user/{username}')]"))
            )
        except TimeoutException:
            print("⚠️  Could not verify login from page elements, but continuing...")
        
        print(f"✓ Successfully logged in as {username}")
        return driver
        
    except Exception as e:
        driver.quit()
        raise


def start_manual_login(
    browser: str = "firefox",
    headless: bool = False,
    attach_debugger: Optional[str] = None,
) -> webdriver.Remote:
    """
    Start a browser session for manual Untappd login.
    Caller is responsible for completing login interactively.
    """
    if attach_debugger:
        if browser != "chrome":
            raise ValueError("--attach-debugger is only supported with Chrome.")
        print(f"Attaching to Chrome debugger at {attach_debugger}...")
        driver = create_chrome_driver_from_debugger(attach_debugger)
        print("Attached to existing Chrome instance. You can complete login/CAPTCHA there.")
        return driver

    if headless:
        raise ValueError("Manual login requires a visible browser window. Run without headless mode.")

    print(f"Starting {browser.capitalize()} browser for manual login...")
    driver = create_driver(headless=headless, browser=browser)
    driver.get(f"{UNTAPPD_BASE}/user/login")
    print("Opened Untappd login page. Complete login manually in the browser window.")
    return driver


def wait_for_manual_login(driver: webdriver.Remote, timeout: int = 300, stop_requested=None):
    """
    Wait until manual login is completed by checking that we're no longer on /login.
    """
    print(f"Waiting up to {timeout} seconds for manual login to complete...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        _raise_if_stopped(stop_requested)
        try:
            current_url = driver.current_url
        except Exception:
            current_url = ""
        try:
            page_title = driver.title
        except Exception:
            page_title = ""
        if not _should_prompt_for_manual_login(current_url, page_title):
            print("✓ Manual login detected.")
            return
        time.sleep(0.5)
    raise TimeoutException("Manual login was not completed before timeout.")


def _should_prompt_for_manual_login(url: str, title: str) -> bool:
    url_lower = (url or "").lower()
    title_lower = (title or "").lower()
    if "/login" in url_lower:
        return True
    if "login" in title_lower:
        return True
    if "just a moment" in title_lower:
        return True
    return False


def prompt_manual_login(driver: webdriver.Remote, username: str, timeout: int = 300, stop_requested=None):
    current_url = ""
    page_title = ""
    try:
        current_url = driver.current_url
    except Exception:
        current_url = ""
    try:
        page_title = driver.title
    except Exception:
        page_title = ""

    if not _should_prompt_for_manual_login(current_url, page_title):
        print("Manual login already appears complete; continuing without an Enter prompt.")
    else:
        print("\nUntappd login appears to be required before beer history can load.")
        print("Please complete login manually in the open browser window.")
        print("If a CAPTCHA or Cloudflare challenge is shown, resolve it in Chrome.")
        if sys.stdin and sys.stdin.isatty():
            try:
                input("Press Enter after you have completed login in the browser window...")
            except Exception:
                print("Unable to prompt for interactive confirmation. Waiting for login completion instead...")
        else:
            print("No interactive terminal is available, so the app will auto-detect login completion.")

    wait_for_manual_login(driver, timeout=timeout, stop_requested=stop_requested)
    print("Login completed. Refreshing the beer history page...")
    try:
        driver.get(f"{UNTAPPD_BASE}/user/{username}/beers")
        time.sleep(2)
    except Exception:
        pass


def fetch_beers(
    driver: webdriver.Remote,
    username: str,
    backstop_total: Optional[int] = None,
    max_clicks: int = 200,
    stop_requested=None,
    retry_on_login: bool = True,
) -> pd.DataFrame:
    """
    Load a user's beer history page, keep clicking "Show More" until all entries are loaded,
    then parse all visible beers.
    """
    url = f"{UNTAPPD_BASE}/user/{username}/beers"
    print(f"Loading beer history for {username}...")
    _raise_if_stopped(stop_requested)
    driver.get(url)
    time.sleep(2)

    for click_num in range(1, max_clicks + 1):
        _raise_if_stopped(stop_requested)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.0)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        items = find_beer_items(soup)
        current_count = len(items)
        print(f"Pass {click_num}: found {current_count} beer entries...")

        if backstop_total is not None and current_count >= backstop_total:
            print(f"Reached backstop total of {backstop_total} beers.")
            break

        if click_show_more(driver):
            if wait_for_beer_count_increase(driver, current_count, timeout=12, stop_requested=stop_requested):
                continue
            print("Show More was clicked, but the beer count did not increase yet.")

        _raise_if_stopped(stop_requested)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)

        refreshed_soup = BeautifulSoup(driver.page_source, "html.parser")
        refreshed_count = len(find_beer_items(refreshed_soup))
        if refreshed_count > current_count:
            print(f"After scrolling, found {refreshed_count} beer entries...")
            continue

        if not has_show_more(driver):
            print("No more beers found and Show More is no longer available.")
            break

    final_page_source = driver.page_source
    final_soup = BeautifulSoup(final_page_source, "html.parser")
    beer_items = find_beer_items(final_soup)
    beers = []
    for item in beer_items:
        _raise_if_stopped(stop_requested)
        parsed = parse_beer_item(item)
        if parsed:
            beers.append(parsed)

    if not beers:
        current_url = ""
        page_title = ""
        try:
            current_url = driver.current_url
        except Exception:
            current_url = ""
        try:
            page_title = driver.title
        except Exception:
            page_title = ""

        if retry_on_login and _should_prompt_for_manual_login(current_url, page_title):
            print("No beer entries were found, and Untappd appears to be requiring login or a page refresh.")
            prompt_manual_login(driver, username, stop_requested=stop_requested)
            print("Retrying beer history fetch after manual login...")
            return fetch_beers(
                driver,
                username,
                backstop_total=backstop_total,
                max_clicks=max_clicks,
                stop_requested=stop_requested,
                retry_on_login=False,
            )

        debug_path = get_debug_snapshot_path()
        try:
            debug_path.write_text(final_page_source, encoding="utf-8")
            print(f"Saved debug HTML snapshot to {debug_path}")
        except Exception as exc:
            print(f"Could not save debug HTML snapshot: {exc}")

        raise ValueError(
            "No beer history entries were found on the /beers page. "
            f"Final URL: {current_url or 'unknown'}. "
            f"Page title: {page_title or 'unknown'}. "
            f"Debug HTML: {debug_path}"
        )

    df = pd.DataFrame(beers)
    for date_col in ("first_checkin", "recent_checkin"):
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], format="%m/%d/%y", errors="coerce")

    df = enrich_producer_locations(driver, df, stop_requested=stop_requested)
    df = enrich_consumed_locations(driver, username, df, stop_requested=stop_requested)

    sort_cols = [col for col in ["recent_checkin", "first_checkin", "beer_name"] if col in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=[False, False, True][: len(sort_cols)], na_position="last")
    df = df.reset_index(drop=True)
    return format_beer_history_dataframe(df)


def find_beer_items(soup: BeautifulSoup):
    """Locate beer-history cards on the page with a few fallback selectors."""
    selectors = [
        "div.beer-item",
        "div.beer",
        "div.item",
        "div[class*='beer-item']",
        "div[class*='distinct'] div.item",
    ]

    seen = set()
    items = []
    for selector in selectors:
        for node in soup.select(selector):
            beer_link = node.find("a", href=lambda href: href and ("/beer/" in href or "/b/" in href))
            if not beer_link:
                continue
            node_id = id(node)
            if node_id in seen:
                continue
            seen.add(node_id)
            items.append(node)
    return items


def click_show_more(driver: webdriver.Remote) -> bool:
    """Click the page's Show More control if it is available."""
    show_more_xpaths = [
        "//*[contains(normalize-space(), 'Show More')]",
    ]

    for xpath in show_more_xpaths:
        try:
            elements = driver.find_elements(By.XPATH, xpath)
        except Exception:
            elements = []

        for button in reversed(elements):
            try:
                text = (button.text or "").strip().lower()
                if "show more" not in text:
                    continue
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                time.sleep(0.5)
                if not button.is_displayed():
                    continue
                try:
                    if hasattr(button, "is_enabled") and not button.is_enabled():
                        continue
                except Exception:
                    pass
                driver.execute_script("arguments[0].click();", button)
                print("Clicked Show More...")
                return True
            except Exception:
                continue

    try:
        clicked = driver.execute_script(
            """
            const nodes = Array.from(document.querySelectorAll('*'))
              .filter(node => (node.innerText || '').trim().toLowerCase() === 'show more');
            const target = nodes[nodes.length - 1];
            if (!target) return false;
            target.scrollIntoView({block: 'center'});
            target.click();
            return true;
            """
        )
        if clicked:
            print("Clicked Show More via JavaScript fallback...")
            return True
    except Exception:
        pass

    return False


def has_show_more(driver: webdriver.Remote) -> bool:
    """Return True if a Show More control is currently visible."""
    show_more_xpaths = [
        "//*[contains(normalize-space(), 'Show More')]",
    ]
    for xpath in show_more_xpaths:
        try:
            elements = driver.find_elements(By.XPATH, xpath)
            for button in elements:
                text = (button.text or "").strip().lower()
                if "show more" in text and button.is_displayed():
                    return True
        except Exception:
            continue
    return False


def wait_for_beer_count_increase(driver: webdriver.Remote, previous_count: int, timeout: int = 8, stop_requested=None) -> bool:
    """
    Wait for the number of loaded beer items to increase after clicking Show More.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        _raise_if_stopped(stop_requested)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        current_count = len(find_beer_items(soup))
        if current_count > previous_count:
            print(f"Beer count increased to {current_count}.")
            return True
        time.sleep(0.5)
    return False


def parse_beer_item(item) -> Optional[dict]:
    """Parse one beer-history entry from the Untappd /beers page."""
    text = " ".join(item.stripped_strings)
    if not text:
        return None

    pieces = [piece.strip() for piece in item.stripped_strings if piece.strip()]
    display_pieces = [
        piece for piece in pieces
        if not re.search(r"(your rating|global rating|abv|ibu|first:|recent:|total:|search|sort & filter)", piece, re.I)
    ]

    beer_link = first_matching_anchor(
        item,
        lambda href: href and ("/beer/" in href or "/b/" in href),
    )
    brewery_link = find_producer_anchor(item)

    beer_name = clean_anchor_text(beer_link)
    brewery_name = clean_anchor_text(brewery_link)

    if not beer_name and display_pieces:
        beer_name = display_pieces[0]
    if not brewery_name and len(display_pieces) > 1:
        brewery_name = display_pieces[1]

    beer_name = beer_name or "Unknown"
    brewery_name = brewery_name or "Unknown"

    beer_url = None
    if beer_link:
        href = beer_link.get("href")
        if href:
            beer_url = f"{UNTAPPD_BASE}{href}" if href.startswith("/") else href
    consumed_location_anchor = find_consumed_location_anchor(item)

    style = None
    if brewery_name != "Unknown" and brewery_name in display_pieces:
        brewery_index = display_pieces.index(brewery_name)
        if brewery_index + 1 < len(display_pieces):
            candidate = display_pieces[brewery_index + 1]
            if candidate not in {beer_name, brewery_name}:
                style = candidate
    if not style and len(display_pieces) > 2:
        candidate = display_pieces[2]
        if candidate not in {beer_name, brewery_name}:
            style = candidate

    your_rating = extract_float(r"YOUR RATING\s*\(([\d.]+)\)", text)
    global_rating = extract_float(r"GLOBAL RATING\s*\(([\d.]+)\)", text)
    abv = extract_float(r"([\d.]+)%\s*ABV", text)
    ibu = extract_float(r"([\d.]+)\s*IBU", text)
    total = extract_int(r"TOTAL:\s*(\d+)", text)

    first_checkin = extract_date(text, "FIRST")
    recent_checkin = extract_date(text, "RECENT")

    return {
        "beer_name": beer_name,
        "brewery_name": brewery_name,
        "brewery_url": build_absolute_url(brewery_link.get("href")) if brewery_link else None,
        "beer_style": style,
        "beer_url": beer_url,
        "consumed_location_name": clean_anchor_text(consumed_location_anchor),
        "consumed_location_url": build_absolute_url(consumed_location_anchor.get("href"))
        if consumed_location_anchor
        else None,
        "your_rating": your_rating,
        "global_rating": global_rating,
        "abv": abv,
        "ibu": ibu,
        "first_checkin": first_checkin,
        "recent_checkin": recent_checkin,
        "total_checkins": total,
    }


def clean_anchor_text(anchor) -> str:
    if not anchor:
        return ""
    return anchor.get_text(" ", strip=True)


def build_absolute_url(href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    if href.startswith("/"):
        return f"{UNTAPPD_BASE}{href}"
    return href


def find_producer_anchor(item):
    """
    Find the producer link for a beer-history item. Untappd often uses root slugs
    like /samadams instead of /brewery/... links.
    """
    anchors = item.find_all("a", href=True)

    for anchor in anchors:
        href = anchor.get("href", "")
        text = clean_anchor_text(anchor)
        if not text:
            continue
        if (
            "/beer/" in href
            or "/b/" in href
            or "/user/" in href
            or "/photo/" in href
            or "/venue/" in href
            or "/v/" in href
        ):
            continue
        if href.startswith("#") or href.startswith("javascript:"):
            continue
        return anchor

    for anchor in anchors:
        href = anchor.get("href", "")
        if href and "/brewery/" in href:
            return anchor
    return None


def find_consumed_location_anchor(item):
    """Find a check-in venue/location link on an Untappd item."""
    anchors = item.find_all("a", href=True)
    for anchor in anchors:
        href = anchor.get("href", "")
        if "/venue/" in href or "/v/" in href:
            return anchor

    strings = list(item.stripped_strings)
    text = " ".join(strings)
    match = re.search(r"\bat\s+(.+?)(?:\s+(?:Purchased|Earned|Tagged|Comments?|Toast)|$)", text, re.I)
    if not match:
        return None
    location_text = match.group(1).strip()
    if not location_text:
        return None
    for anchor in anchors:
        anchor_text = clean_anchor_text(anchor)
        if anchor_text and anchor_text in location_text:
            return anchor
    return None


def first_matching_anchor(item, href_matcher):
    for anchor in item.find_all("a", href=href_matcher):
        if clean_anchor_text(anchor):
            return anchor
    return item.find("a", href=href_matcher)


def format_beer_history_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert the raw scraper output into the user-facing beer-history columns.
    """
    formatted = pd.DataFrame({
        "Beer Name": df.get("beer_name"),
        "Producer": df.get("brewery_name"),
        "Producer Location": df.get("producer_location"),
        "Consumed Location": df.get("consumed_location"),
        "Lat": df.get("lat"),
        "Long": df.get("long"),
        "Beer Type": df.get("beer_style"),
        "My Rating": df.get("your_rating"),
        "Global Rating": df.get("global_rating"),
        "First Date": format_date_series(df.get("first_checkin")),
        "Recent Date": format_date_series(df.get("recent_checkin")),
        "Total Checkins": df.get("total_checkins"),
    })
    return formatted


def format_date_series(series):
    if series is None:
        return None
    return series.dt.strftime("%Y-%m-%d").where(series.notna(), None)


def enrich_producer_locations(driver: webdriver.Remote, df: pd.DataFrame, stop_requested=None) -> pd.DataFrame:
    """
    Visit each unique producer page once and extract a readable city/state location.
    """
    if df.empty or "brewery_name" not in df.columns:
        return df

    producer_cache = load_producer_location_cache()
    unique_producers = (
        df[["brewery_name", "brewery_url"]]
        .drop_duplicates()
        .fillna("")
        .to_dict("records")
    )

    runtime_locations = {}
    unresolved = []

    for producer in unique_producers:
        _raise_if_stopped(stop_requested)
        producer_name = producer.get("brewery_name", "").strip()
        producer_url = producer.get("brewery_url", "").strip()
        if not producer_name or not producer_url:
            continue
        cached_location = producer_cache.get(producer_name)
        if cached_location:
            runtime_locations[producer_name] = cached_location
            continue
        unresolved.append({"brewery_name": producer_name, "brewery_url": producer_url})

    if unresolved:
        print(
            f"Resolving {len(unresolved)} producer locations "
            f"({len(unique_producers) - len(unresolved)} loaded from local cache)..."
        )

        cookies = {cookie["name"]: cookie["value"] for cookie in driver.get_cookies()}
        user_agent = driver.execute_script("return navigator.userAgent") or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )

        resolved_parallel = fetch_producer_locations_parallel(
            unresolved,
            cookies=cookies,
            user_agent=user_agent,
            max_workers=4,
        )

        for producer_name, location in resolved_parallel.items():
            if location:
                runtime_locations[producer_name] = location
                producer_cache[producer_name] = location

        still_missing = [p for p in unresolved if not runtime_locations.get(p["brewery_name"])]
        for idx, producer in enumerate(still_missing, start=1):
            _raise_if_stopped(stop_requested)
            producer_name = producer["brewery_name"]
            producer_url = producer["brewery_url"]
            print(
                f"Falling back to Selenium for producer location {idx}/{len(still_missing)}: {producer_name}"
            )
            location = fetch_producer_location(driver, producer_url)
            if location:
                runtime_locations[producer_name] = location
                producer_cache[producer_name] = location
            time.sleep(0.5)

        save_producer_location_cache(producer_cache)

    enriched = df.copy()
    enriched["producer_location"] = enriched["brewery_name"].map(
        lambda name: runtime_locations.get(name) or producer_cache.get(name)
    )
    return enriched


def enrich_consumed_locations(
    driver: webdriver.Remote,
    username: str,
    df: pd.DataFrame,
    stop_requested=None,
) -> pd.DataFrame:
    """
    Attach the most recent known check-in venue city/state for each beer row.
    """
    if df.empty:
        return df

    enriched = df.copy()
    consumed_cache = load_consumed_location_cache()
    row_keys = {
        beer_producer_key(row.get("beer_name"), row.get("brewery_name"))
        for _, row in enriched.iterrows()
    }
    row_keys.discard(None)

    location_by_key = {}
    coords_by_key = {}
    venue_by_key = {}
    for _, row in enriched.iterrows():
        key = beer_producer_key(row.get("beer_name"), row.get("brewery_name"))
        venue_url = row.get("consumed_location_url")
        if key and venue_url:
            venue_by_key.setdefault(key, venue_url)

    for key, venue_url in venue_by_key.items():
        cached = consumed_cache.get(venue_url)
        if has_complete_consumed_location(cached):
            location_by_key[key] = cached.get("location")
            coords = consumed_location_coords(cached)
            if coords:
                coords_by_key[key] = coords

    unresolved_keys = row_keys - set(location_by_key)
    if unresolved_keys:
        print(f"Scanning recent check-ins for consumed locations ({len(unresolved_keys)} beers missing)...")
        cookies = {cookie["name"]: cookie["value"] for cookie in driver.get_cookies()}
        user_agent = driver.execute_script("return navigator.userAgent") or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        checkin_matches = collect_checkin_venue_matches_parallel(
            username,
            unresolved_keys,
            cookies=cookies,
            user_agent=user_agent,
            stop_requested=stop_requested,
            max_checkins=len(enriched),
            max_workers=4,
        )
        remaining_keys = unresolved_keys - set(checkin_matches)
        if remaining_keys:
            if checkin_matches:
                print(
                    "Parallel check-in scan found "
                    f"{len(checkin_matches)} venue links; using Selenium for "
                    f"{len(remaining_keys)} remaining beers..."
                )
            else:
                print("Parallel check-in scan found no venue links; falling back to Selenium scan...")
            selenium_matches = collect_checkin_venue_matches(
                driver,
                username,
                remaining_keys,
                stop_requested=stop_requested,
                max_checkins=len(enriched),
            )
            checkin_matches.update(selenium_matches)
        for key, venue_url in checkin_matches.items():
            venue_by_key.setdefault(key, venue_url)

    unresolved_venues = sorted(
        {
            venue_url
            for key, venue_url in venue_by_key.items()
            if key not in location_by_key
            and venue_url
            and not has_complete_consumed_location(consumed_cache.get(venue_url))
        }
    )
    if unresolved_venues:
        print(f"Resolving {len(unresolved_venues)} consumed location pages...")
        cookies = {cookie["name"]: cookie["value"] for cookie in driver.get_cookies()}
        user_agent = driver.execute_script("return navigator.userAgent") or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        resolved_parallel = fetch_consumed_locations_parallel(
            unresolved_venues,
            cookies=cookies,
            user_agent=user_agent,
            max_workers=4,
        )
        for venue_url, venue_data in resolved_parallel.items():
            if venue_data:
                consumed_cache[venue_url] = venue_data

        still_missing = [url for url in unresolved_venues if not consumed_cache.get(url)]
        for idx, venue_url in enumerate(still_missing, start=1):
            _raise_if_stopped(stop_requested)
            print(f"Falling back to Selenium for consumed location {idx}/{len(still_missing)}")
            venue_data = fetch_consumed_location(driver, venue_url)
            if venue_data:
                consumed_cache[venue_url] = venue_data
            time.sleep(0.3)

        save_consumed_location_cache(consumed_cache)

    for key, venue_url in venue_by_key.items():
        if key not in location_by_key and venue_url:
            cached = consumed_cache.get(venue_url)
            if has_complete_consumed_location(cached):
                location_by_key[key] = cached.get("location")
                coords = consumed_location_coords(cached)
                if coords:
                    coords_by_key[key] = coords

    enriched["consumed_location"] = enriched.apply(
        lambda row: location_by_key.get(beer_producer_key(row.get("beer_name"), row.get("brewery_name"))),
        axis=1,
    )
    enriched["lat"] = enriched.apply(
        lambda row: (
            coords_by_key.get(beer_producer_key(row.get("beer_name"), row.get("brewery_name"))) or (None, None)
        )[0],
        axis=1,
    )
    enriched["long"] = enriched.apply(
        lambda row: (
            coords_by_key.get(beer_producer_key(row.get("beer_name"), row.get("brewery_name"))) or (None, None)
        )[1],
        axis=1,
    )
    resolved_count = enriched["consumed_location"].fillna("").replace("", pd.NA).dropna().count()
    print(f"Added consumed locations for {resolved_count:,} of {len(enriched):,} beer rows.")
    return enriched


def has_complete_consumed_location(value) -> bool:
    if not isinstance(value, dict):
        return False
    return bool(value.get("location")) and bool(consumed_location_coords(value))


def beer_producer_key(beer_name, brewery_name) -> Optional[str]:
    beer = normalize_key_part(beer_name)
    brewery = normalize_key_part(brewery_name)
    if not beer:
        return None
    return f"{beer}|{brewery}"


def normalize_key_part(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def consumed_location_coords(value: dict) -> Optional[tuple[float, float]]:
    lat = value.get("lat")
    lng = value.get("long")
    try:
        if lat is None or lng is None:
            return None
        return float(lat), float(lng)
    except (TypeError, ValueError):
        return None


def collect_checkin_venue_matches(
    driver: webdriver.Remote,
    username: str,
    target_keys: set[str],
    stop_requested=None,
    max_checkins: Optional[int] = None,
    max_pages: int = 80,
) -> dict[str, str]:
    matches = {}
    scanned_checkins = 0
    seen_keys = set()
    next_url = build_checkin_page_url(username)
    for page_num in range(1, max_pages + 1):
        _raise_if_stopped(stop_requested)
        if target_keys and target_keys.issubset(matches):
            break
        if max_checkins is not None and len(seen_keys) >= max_checkins:
            break
        print(f"Checking consumed locations page {page_num}...")
        if page_num == 1:
            driver.get(next_url)
            time.sleep(1.2)
            soup = BeautifulSoup(driver.page_source, "html.parser")
        else:
            soup = fetch_more_feed_page(driver, username, next_url)
        checkin_items = find_checkin_items(soup)
        if not checkin_items:
            break
        scanned_checkins += len(checkin_items)
        for item in checkin_items:
            parsed = parse_checkin_item(item)
            if not parsed:
                continue
            key = beer_producer_key(parsed.get("beer_name"), parsed.get("brewery_name"))
            if key:
                seen_keys.add(key)
            venue_url = parsed.get("venue_url")
            if key in target_keys and venue_url and key not in matches:
                matches[key] = venue_url
        last_checkin_id = find_last_checkin_id(checkin_items)
        if not last_checkin_id:
            break
        next_url = build_more_feed_url(username, last_checkin_id)
    return matches


def fetch_more_feed_page(driver: webdriver.Remote, username: str, url: str) -> BeautifulSoup:
    cookies = {cookie["name"]: cookie["value"] for cookie in driver.get_cookies()}
    user_agent = driver.execute_script("return navigator.userAgent") or (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    )
    response = requests.get(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{UNTAPPD_BASE}/user/{username}",
        },
        cookies=cookies,
        timeout=15,
    )
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def find_last_checkin_id(items) -> Optional[str]:
    for item in reversed(items):
        checkin_id = item.get("data-checkin-id")
        if checkin_id:
            return checkin_id
        node = item.find(attrs={"data-checkin-id": True})
        if node:
            return node.get("data-checkin-id")
        match = re.search(r"checkin_(\d+)", item.get("id", ""))
        if match:
            return match.group(1)
    return None


def collect_checkin_venue_matches_parallel(
    username: str,
    target_keys: set[str],
    cookies: dict,
    user_agent: str,
    stop_requested=None,
    max_checkins: Optional[int] = None,
    max_pages: int = 80,
    max_workers: int = 4,
    batch_size: int = 8,
) -> dict[str, str]:
    """
    Fetch check-in pages with authenticated HTTP requests in parallel batches.

    Lower offsets are newer check-ins, so results are applied in offset order to
    preserve the "most recent consumed location" behavior.
    """
    matches = {}
    effective_max_pages = max_pages
    if max_checkins is not None:
        effective_max_pages = max(1, min(max_pages, (max_checkins + 24) // 25))
    offsets = list(range(0, effective_max_pages * 25, 25))
    scanned_checkins = 0
    for batch_start in range(0, len(offsets), batch_size):
        _raise_if_stopped(stop_requested)
        if target_keys and target_keys.issubset(matches):
            break
        if max_checkins is not None and scanned_checkins >= max_checkins:
            break

        batch_offsets = offsets[batch_start: batch_start + batch_size]
        print(
            "Checking consumed location pages "
            f"{batch_start + 1}-{batch_start + len(batch_offsets)} in parallel..."
        )
        batch_results = fetch_checkin_pages_parallel(
            username,
            batch_offsets,
            cookies=cookies,
            user_agent=user_agent,
            max_workers=max_workers,
        )

        saw_items = False
        batch_had_short_page = False
        for offset in sorted(batch_results):
            items = batch_results[offset]
            if items:
                saw_items = True
            if len(items) < 10:
                batch_had_short_page = True
            scanned_checkins += len(items)
            for parsed in items:
                key = beer_producer_key(parsed.get("beer_name"), parsed.get("brewery_name"))
                venue_url = parsed.get("venue_url")
                if key in target_keys and venue_url and key not in matches:
                    matches[key] = venue_url

        if not saw_items or batch_had_short_page:
            break

    print(f"Parallel check-in scan matched {len(matches):,} consumed venue links.")
    return matches


def fetch_checkin_pages_parallel(
    username: str,
    offsets: list[int],
    cookies: dict,
    user_agent: str,
    max_workers: int = 4,
) -> dict[int, list[dict]]:
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_offset = {
            executor.submit(
                fetch_checkin_page_via_http,
                username,
                offset,
                cookies,
                user_agent,
            ): offset
            for offset in offsets
        }
        for future in as_completed(future_to_offset):
            offset = future_to_offset[future]
            try:
                results[offset] = future.result()
            except Exception as exc:
                print(f"Warning: Check-in page offset {offset} failed over HTTP: {exc}")
                results[offset] = []
    return results


def fetch_checkin_page_via_http(
    username: str,
    offset: int,
    cookies: dict,
    user_agent: str,
) -> list[dict]:
    url = build_checkin_page_url(username, offset)
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": f"{UNTAPPD_BASE}/user/{username}",
    }
    response = requests.get(url, headers=headers, cookies=cookies, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    return [
        parsed
        for item in find_checkin_items(soup)
        if (parsed := parse_checkin_item(item))
    ]


def build_checkin_page_url(username: str, offset: int = 0) -> str:
    if offset <= 0:
        return f"{UNTAPPD_BASE}/user/{username}"
    return f"{UNTAPPD_BASE}/user/{username}/checkins?offset={offset}"


def build_more_feed_url(username: str, checkin_id: str) -> str:
    return f"{UNTAPPD_BASE}/profile/more_feed/{username}/{checkin_id}?v2=true"


def find_checkin_items(soup: BeautifulSoup):
    selectors = [
        "div.checkin",
        "div.item",
        "li.item",
        "div[class*='checkin']",
    ]
    seen = set()
    items = []
    for selector in selectors:
        for node in soup.select(selector):
            checkin_id = node.get("data-checkin-id")
            if not checkin_id:
                checkin_parent = node.find_parent(attrs={"data-checkin-id": True})
                if checkin_parent:
                    checkin_id = checkin_parent.get("data-checkin-id")
            beer_link = first_matching_anchor(
                node,
                lambda href: href and ("/beer/" in href or "/b/" in href),
            )
            venue_link = find_consumed_location_anchor(node)
            if not beer_link or not venue_link:
                continue
            node_id = checkin_id or id(node)
            if node_id in seen:
                continue
            seen.add(node_id)
            items.append(node)
    return items


def fetch_producer_locations_parallel(producers, cookies: dict, user_agent: str, max_workers: int = 4) -> dict:
    """
    Fetch missing producer pages in parallel using lightweight HTTP requests.
    """
    results = {}
    if not producers:
        return results

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_name = {
            executor.submit(
                fetch_producer_location_via_http,
                producer["brewery_url"],
                cookies,
                user_agent,
            ): producer["brewery_name"]
            for producer in producers
        }
        for future in as_completed(future_to_name):
            producer_name = future_to_name[future]
            try:
                location = future.result()
                if location:
                    print(f"Resolved producer location in parallel: {producer_name} -> {location}")
                results[producer_name] = location
            except Exception as e:
                print(f"Warning: Parallel producer lookup failed for {producer_name}: {e}")
                results[producer_name] = None
    return results


def fetch_consumed_locations_parallel(venue_urls, cookies: dict, user_agent: str, max_workers: int = 4) -> dict:
    results = {}
    if not venue_urls:
        return results

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(fetch_consumed_location_via_http, venue_url, cookies, user_agent): venue_url
            for venue_url in venue_urls
        }
        for future in as_completed(future_to_url):
            venue_url = future_to_url[future]
            try:
                venue_data = future.result()
                if venue_data:
                    print(f"Resolved consumed location: {venue_url} -> {venue_data.get('location')}")
                results[venue_url] = venue_data
            except Exception as e:
                print(f"Warning: Parallel consumed location lookup failed for {venue_url}: {e}")
                results[venue_url] = None
    return results


def fetch_consumed_location_via_http(venue_url: str, cookies: dict, user_agent: str) -> Optional[dict]:
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": UNTAPPD_BASE,
    }
    response = requests.get(
        venue_url,
        headers=headers,
        cookies=cookies,
        timeout=15,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    return extract_consumed_location_data(soup)


def fetch_consumed_location(driver: webdriver.Remote, venue_url: str) -> Optional[dict]:
    try:
        driver.get(venue_url)
        time.sleep(1.2)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        venue_data = extract_consumed_location_data(soup)
        if venue_data:
            print(f"Resolved consumed location with Selenium: {venue_data.get('location')}")
        else:
            print(f"Warning: No consumed location address found on {venue_url}")
        return venue_data
    except Exception as e:
        print(f"Warning: Could not fetch consumed location page {venue_url}: {e}")
        return None


def extract_consumed_location_data(soup: BeautifulSoup) -> Optional[dict]:
    location = extract_location_from_consumed_location_page(soup)
    coords = extract_venue_coordinates(soup)
    if not location and not coords:
        return None

    data = {"location": location}
    if coords:
        data["lat"] = coords[0]
        data["long"] = coords[1]
    return data


def extract_location_from_consumed_location_page(soup: BeautifulSoup) -> Optional[str]:
    structured_location = extract_location_from_json_ld(soup)
    if structured_location:
        return structured_location

    candidates = []
    selectors = [
        ".address",
        ".venue-address",
        ".location",
        "[itemprop='address']",
        "[itemprop='streetAddress']",
        "[itemprop='addressLocality']",
        "address",
        "div.info",
        "div.content",
        "body",
    ]
    for selector in selectors:
        for node in soup.select(selector):
            text = normalize_location_text(node.get_text(" ", strip=True))
            city_state = simplify_to_city_state(text) if text else None
            if city_state:
                candidates.append(city_state)
        if candidates:
            break

    page_text = normalize_location_text(" ".join(soup.stripped_strings))
    city_state = simplify_to_city_state(page_text) if page_text else None
    if city_state:
        candidates.append(city_state)

    return candidates[0] if candidates else None


def extract_location_from_json_ld(soup: BeautifulSoup) -> Optional[str]:
    for script in soup.find_all("script", type="application/ld+json"):
        raw_text = script.string or script.get_text()
        if not raw_text:
            continue
        try:
            payload = json.loads(unescape(raw_text.strip()))
        except json.JSONDecodeError:
            continue
        for node in iter_json_ld_nodes(payload):
            if not isinstance(node, dict):
                continue
            address = node.get("address")
            if not isinstance(address, dict):
                continue
            city = normalize_location_text(address.get("addressLocality") or "")
            region = normalize_location_text(address.get("addressRegion") or "")
            if city and region:
                return simplify_location(f"{city}, {region}")
    return None


def iter_json_ld_nodes(payload):
    if isinstance(payload, dict):
        yield payload
        graph = payload.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from iter_json_ld_nodes(item)
    elif isinstance(payload, list):
        for item in payload:
            yield from iter_json_ld_nodes(item)


def extract_venue_coordinates(soup: BeautifulSoup) -> Optional[tuple[float, float]]:
    lat_meta = soup.find("meta", attrs={"property": "place:location:latitude"})
    long_meta = soup.find("meta", attrs={"property": "place:location:longitude"})
    if not lat_meta or not long_meta:
        return None
    try:
        return float(lat_meta.get("content")), float(long_meta.get("content"))
    except (TypeError, ValueError):
        return None


def fetch_producer_location_via_http(producer_url: str, cookies: dict, user_agent: str) -> Optional[str]:
    """
    Fetch a producer page over HTTP using the current browser cookies.
    """
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": UNTAPPD_BASE,
    }
    response = requests.get(
        producer_url,
        headers=headers,
        cookies=cookies,
        timeout=15,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    return extract_location_from_producer_page(soup)


def fetch_producer_location(driver: webdriver.Remote, producer_url: str) -> Optional[str]:
    """
    Scrape a producer page for a location string such as 'City, ST'.
    """
    try:
        driver.get(producer_url)
        time.sleep(1.5)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        location = extract_location_from_producer_page(soup)
        if location:
            print(f"Resolved producer location: {location}")
        else:
            print(f"Warning: No producer location found on {producer_url}")
        return location
    except Exception as e:
        print(f"Warning: Could not fetch producer page {producer_url}: {e}")
        return None


def extract_location_from_producer_page(soup: BeautifulSoup) -> Optional[str]:
    """
    Try to extract the location line from the producer header block.
    """
    candidates = []

    header_selectors = [
        "div.top",
        "div.name",
        "div.info",
        "div.content",
        "div#slide",
        "body",
    ]
    for selector in header_selectors:
        for node in soup.select(selector):
            header_location = extract_location_from_header_block(node)
            if header_location:
                candidates.append(header_location)
        if candidates:
            break

    selectors = [
        ".location",
        ".address",
        "[itemprop='address']",
        "[itemprop='addressLocality']",
    ]
    for selector in selectors:
        for node in soup.select(selector):
            text = normalize_location_text(node.get_text(" ", strip=True))
            if text:
                candidates.append(text)

    page_text = " ".join(soup.stripped_strings)
    regex_candidates = re.findall(
        r"([A-Z][A-Za-zÀ-ÿ0-9.&'\- ]+,\s*(?:[A-Z]{2}|[A-Z][A-Za-zÀ-ÿ'\- ]+)\s+(?:United States|USA|Canada|Mexico|Ireland|England|Scotland|Wales|Germany|Australia|New Zealand|Japan|Czechia|Czech Republic|Belgium|Austria|Ukraine|Denmark|Netherlands|Italy|Spain|France))",
        page_text,
    )
    for candidate in regex_candidates:
        text = normalize_location_text(candidate)
        if text:
            candidates.append(text)

    for candidate in candidates:
        if is_reasonable_location(candidate):
            return simplify_location(candidate)
    return None


def extract_location_from_header_block(node) -> Optional[str]:
    strings = [s.strip() for s in node.stripped_strings if s.strip()]
    for i, text in enumerate(strings):
        normalized = normalize_location_text(text)
        if not normalized:
            continue
        if is_reasonable_location(normalized):
            return normalized
        if "," in normalized and i + 1 < len(strings):
            combined = normalize_location_text(f"{normalized} {strings[i + 1]}")
            if combined and is_reasonable_location(combined):
                return combined
    return None


def normalize_location_text(text: str) -> Optional[str]:
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip(" ,")
    text = re.sub(r"\s*·\s*", " ", text)
    return text or None


def is_reasonable_location(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    blocked = ("your rating", "global rating", "show more", "beer history", "untappd")
    if any(token in lowered for token in blocked):
        return False
    if len(text) < 4:
        return False
    if "," not in text:
        return False
    location_markers = (
        "united states", "usa", "canada", "mexico", "ireland", "england", "scotland",
        "wales", "germany", "australia", "new zealand", "japan", "czechia",
        "czech republic", "belgium", "austria", "ukraine", "denmark", "netherlands",
        "italy", "spain", "france", "brazil", "chile"
    )
    us_state_match = re.search(r",\s*[A-Z]{2}(?:\s|$)", text)
    country_match = any(marker in lowered for marker in location_markers)
    return bool(us_state_match or country_match)


def simplify_location(text: str) -> str:
    """
    Keep the city/state style location the user wants, e.g. 'Boston, MA'.
    """
    text = text.strip()
    city_state = simplify_to_city_state(text)
    if city_state:
        return city_state
    match = re.match(r"(.+?,\s*[A-Z]{2})\s+United States$", text, flags=re.I)
    if match:
        return match.group(1)
    return text


def simplify_to_city_state(text: str) -> Optional[str]:
    if not text:
        return None
    text = normalize_location_text(text) or ""
    matches = re.findall(
        r"([A-Za-zÀ-ÿ0-9.&'’\- ]+),\s*([A-Z]{2})(?:\s+\d{5}(?:-\d{4})?)?(?:\s+United States)?",
        text,
    )
    if not matches:
        return None
    city, state = matches[-1]
    city = strip_street_address_prefix(city)
    if not city:
        return None
    return f"{city}, {state}"


def strip_street_address_prefix(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip(" ,")
    if not re.search(r"\d", value):
        return value

    street_suffixes = (
        "aly", "alley", "ave", "avenue", "blvd", "boulevard", "cir", "circle",
        "ct", "court", "dr", "drive", "hwy", "highway", "ln", "lane", "pkwy",
        "parkway", "pl", "place", "rd", "road", "sq", "square", "st", "street",
        "ter", "terrace", "trl", "trail", "way",
    )
    suffix_pattern = "|".join(street_suffixes)
    match = re.search(
        rf"\b(?:{suffix_pattern})\.?\s+(?P<city>[A-Za-zÀ-ÿ.&'’\- ]+)$",
        value,
        flags=re.I,
    )
    if match:
        city = match.group("city").strip(" ,")
        if city:
            return city

    return re.sub(r"^\d+\s+", "", value).strip(" ,")


def extract_float(pattern: str, text: str) -> Optional[float]:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def extract_int(pattern: str, text: str) -> Optional[int]:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def extract_date(text: str, label: str) -> Optional[str]:
    match = re.search(rf"{label}:\s*(\d{{1,2}}/\d{{1,2}}/\d{{2,4}})", text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def fetch_checkins(driver: webdriver.Remote, username: str) -> pd.DataFrame:
    """
    Scrape check-ins from user's profile using Selenium.
    """
    checkins = []
    offset = 0
    max_iterations = 50
    
    print(f"Fetching check-ins for {username}...")
    
    for iteration in range(max_iterations):
        # Navigate to checkins page
        url = f"{UNTAPPD_BASE}/user/{username}/checkins?offset={offset}"
        print(f"Fetching page {iteration + 1} (offset {offset})...")
        
        try:
            driver.get(url)
            time.sleep(2)  # Wait for page to load
            
            # Get page source and parse
            soup = BeautifulSoup(driver.page_source, "html.parser")
            
            # Find checkin items
            checkin_items = soup.find_all("div", {"class": "item"})
            if not checkin_items:
                checkin_items = soup.find_all("li", {"class": "item"})
            
            if not checkin_items:
                print("No more check-ins found")
                break
            
            # Parse each checkin
            for item in checkin_items:
                try:
                    checkin_data = parse_checkin_item(item)
                    if checkin_data:
                        checkins.append(checkin_data)
                except Exception as e:
                    print(f"Warning: Failed to parse checkin: {e}")
                    continue
            
            # If we got fewer items than a full page, we're at the end
            if len(checkin_items) < 10:
                break
            
            offset += 25  # Untappd default pagination
            
        except Exception as e:
            print(f"Error fetching page: {e}")
            break
    
    if not checkins:
        raise ValueError("No check-ins found for this user")
    
    df = pd.DataFrame(checkins)
    df["checkin_date"] = pd.to_datetime(df["checkin_date"], format="%m/%d/%y", errors="coerce")
    return df.sort_values("checkin_date", ascending=False)


def parse_checkin_item(item) -> Optional[dict]:
    """Parse a single checkin item from HTML."""
    try:
        beer_link = item.find("a", {"class": "label"})
        if not beer_link or not clean_anchor_text(beer_link):
            text_node = item.select_one("p.text")
            beer_link = first_matching_anchor(
                text_node or item,
                lambda x: x and ("/beer/" in x or "/b/" in x),
            )
        
        beer_name = clean_anchor_text(beer_link) if beer_link else "Unknown"
        
        brewery_link = find_producer_anchor(item)
        brewery_name = brewery_link.get_text(strip=True) if brewery_link else "Unknown"
        
        # Extract venue info
        venue_link = find_consumed_location_anchor(item)
        venue_name = venue_link.get_text(strip=True) if venue_link else "Unknown"
        
        # Extract location (state/country)
        location_elem = item.find("span", {"class": "location"})
        if not location_elem:
            # Try finding small tag with location
            all_small = item.find_all("small")
            if all_small:
                location_elem = all_small[-1]  # Usually last small tag
        
        location_text = location_elem.get_text(strip=True) if location_elem else ""
        
        # Parse state from location
        state_code = None
        if location_text:
            parts = location_text.split(",")
            if len(parts) >= 2:
                state_code = parts[-1].strip().upper()
                if len(state_code) != 2:
                    state_code = None
        
        # Extract beer style
        style_elem = item.find("em")
        beer_style = style_elem.get_text(strip=True) if style_elem else "Unknown"
        # Clean up style
        if " - " in beer_style:
            beer_style = beer_style.split(" - ")[0]
        
        # Extract rating
        rating = None
        rating_elem = item.find("span", {"class": lambda x: x and "star" in x.lower()})
        if rating_elem:
            rating_text = rating_elem.get_text(strip=True)
            # Extract number
            import re
            match = re.search(r"(\d+\.?\d*)", rating_text)
            if match:
                try:
                    rating = float(match.group(1))
                except ValueError:
                    pass
        
        # Extract serving style
        serving_style = "Unknown"
        # Look for serving info in the item
        for small in item.find_all("small"):
            text = small.get_text(strip=True).lower()
            if "draft" in text or "bottle" in text or "can" in text or "tap" in text:
                serving_style = small.get_text(strip=True)
                break
        
        # Extract date
        date_elem = item.find("time")
        checkin_date = "Unknown"
        if date_elem:
            checkin_date = date_elem.get("datetime") or date_elem.get_text(strip=True)
        
        return {
            "checkin_date": checkin_date,
            "beer_name": beer_name,
            "beer_url": build_absolute_url(beer_link.get("href")) if beer_link else None,
            "beer_style": beer_style,
            "brewery_name": brewery_name,
            "brewery_url": build_absolute_url(brewery_link.get("href")) if brewery_link else None,
            "venue_name": venue_name,
            "venue_url": build_absolute_url(venue_link.get("href")) if venue_link else None,
            "place_state": state_code,
            "rating": rating,
            "serving_style": serving_style,
        }
        
    except Exception as e:
        print(f"Error parsing checkin: {e}")
        return None


def get_user_info(driver: webdriver.Remote, username: str) -> dict:
    """Get user profile info."""
    try:
        print(f"Fetching user info for {username}...")
        driver.get(f"{UNTAPPD_BASE}/user/{username}")
        time.sleep(2)
        
        # Try to find checkin count
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        user_info = {
            "username": username,
            "total_checkins": None,
        }
        
        # Look for stats
        import re
        page_text = soup.get_text()
        match = re.search(r"(\d+)\s+Check[- ]?ins?", page_text, re.IGNORECASE)
        if match:
            user_info["total_checkins"] = int(match.group(1))
        
        return user_info
        
    except Exception as e:
        print(f"Warning: Could not fetch user info: {e}")
        return {"username": username, "total_checkins": None}


def quit_driver(driver: webdriver.Remote):
    """Safely close the browser."""
    try:
        driver.quit()
    except Exception as e:
        print(f"Warning: Error closing browser: {e}")
