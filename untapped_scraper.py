import json
import os
import re
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

UNTAPPD_BASE = "https://untappd.com"
CREDENTIALS_FILE = ".untappd_credentials"


def get_credentials_path():
    return Path.home() / ".untappd" / CREDENTIALS_FILE


def ensure_credentials_dir():
    cred_dir = Path.home() / ".untappd"
    cred_dir.mkdir(exist_ok=True, parents=True)


def save_credentials(username: str, password: str):
    """Save Untappd login credentials to disk."""
    ensure_credentials_dir()
    creds = {
        "username": username,
        "password": password,
        "auth_method": "scraper",
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


def login(username: str, password: str, session: Optional[requests.Session] = None) -> requests.Session:
    """
    Log into Untappd and return authenticated session.
    """
    if session is None:
        session = requests.Session()

    # Set realistic headers to avoid bot detection
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
    })

    # First, visit the home page to establish session cookies
    print("Establishing session...")
    try:
        home_response = session.get(UNTAPPD_BASE, timeout=10)
        home_response.raise_for_status()
    except requests.RequestException as e:
        print(f"Warning: Could not fetch home page: {e}")
        # Continue anyway, maybe cookies will still work

    # Get login page
    print("Fetching login page...")
    try:
        response = session.get(f"{UNTAPPD_BASE}/user/login", timeout=10)
        response.raise_for_status()
    except requests.HTTPError as e:
        if e.response.status_code == 403:
            print("⚠️  Untappd is blocking automated requests (403 Forbidden).")
            print("     This may indicate Untappd has bot protection enabled.")
            print("     Try: 1) Using a different network/VPN")
            print("          2) Waiting a few minutes before retrying")
            print("          3) Checking if your account has unusual login activity")
            raise ValueError(f"Untappd blocked the request: {e}")
        else:
            raise ValueError(f"Failed to fetch login page: {e}")
    except requests.RequestException as e:
        raise ValueError(f"Failed to fetch login page: {e}")

    # Extract CSRF token
    soup = BeautifulSoup(response.content, "html.parser")
    csrf_token = None
    csrf_input = soup.find("input", {"name": "_token"})
    if csrf_input:
        csrf_token = csrf_input.get("value")

    # Perform login with proper headers
    print("Logging in...")
    login_data = {
        "username": username,
        "password": password,
    }
    if csrf_token:
        login_data["_token"] = csrf_token

    # Update headers for POST request
    session.headers.update({
        "Referer": f"{UNTAPPD_BASE}/user/login",
        "Origin": UNTAPPD_BASE,
        "Content-Type": "application/x-www-form-urlencoded",
    })

    try:
        response = session.post(
            f"{UNTAPPD_BASE}/user/login",
            data=login_data,
            timeout=10,
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise ValueError(f"Login POST failed: {e}")

    # Check if login was successful
    response_text = response.text.lower()
    if "logout" not in response_text and f"/user/{username.lower()}" not in response_text:
        # Check if we got redirected to login page (indicating failed login)
        if "login" in response_text and ("password" in response_text or "username" in response_text):
            raise ValueError("Login failed: invalid username or password")
        # Sometimes the check might be inconclusive, but we proceed
        print("⚠️  Could not fully verify login, but continuing...")

    print(f"✓ Successfully logged in as {username}")
    return session


def fetch_checkins(session: requests.Session, username: str, limit: int = 100) -> pd.DataFrame:
    """
    Scrape check-ins from a user's profile page.
    """
    checkins = []
    offset = 0
    max_iterations = 50  # Safety limit

    # Update headers for profile page requests
    session.headers.update({
        "Referer": f"{UNTAPPD_BASE}/user/{username}",
    })

    for iteration in range(max_iterations):
        url = f"{UNTAPPD_BASE}/user/{username}/checkins"
        params = {"offset": offset}

        print(f"Fetching check-ins (offset {offset})...")
        try:
            response = session.get(url, params=params, timeout=10)
            
            # Check for 403 Forbidden
            if response.status_code == 403:
                print("⚠️  Untappd blocked the request (403). Waiting before retry...")
                time.sleep(2)
                response = session.get(url, params=params, timeout=10)
            
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Error fetching page: {e}")
            break

        soup = BeautifulSoup(response.content, "html.parser")

        # Find all checkin items
        checkin_items = soup.find_all("div", {"class": "checkin"})
        if not checkin_items:
            # Try alternative selectors
            checkin_items = soup.find_all("li", {"class": "item"})

        if not checkin_items:
            print("No more check-ins found")
            break

        for item in checkin_items:
            try:
                checkin_data = parse_checkin_item(item)
                if checkin_data:
                    checkins.append(checkin_data)
            except Exception as e:
                print(f"Warning: Failed to parse checkin item: {e}")
                continue

        # If we got fewer items than requested, we're at the end
        if len(checkin_items) < limit:
            break

        offset += limit
        time.sleep(1)  # Be respectful with requests

    if not checkins:
        raise ValueError("No check-ins found for this user")

    df = pd.DataFrame(checkins)
    df["checkin_date"] = pd.to_datetime(df["checkin_date"], errors="coerce")
    return df.sort_values("checkin_date", ascending=False)


def parse_checkin_item(item) -> Optional[dict]:
    """
    Parse a single checkin item from HTML.
    """
    try:
        # Extract beer info
        beer_link = item.find("a", {"class": "label"})
        if not beer_link:
            beer_link = item.find("a", {"href": re.compile(r"/beer/")})

        beer_name = beer_link.get_text(strip=True) if beer_link else "Unknown"

        # Extract brewery info
        brewery_link = item.find("a", {"href": re.compile(r"/brewery/")})
        brewery_name = brewery_link.get_text(strip=True) if brewery_link else "Unknown"

        # Extract venue info
        venue_link = item.find("a", {"href": re.compile(r"/venue/")})
        venue_name = venue_link.get_text(strip=True) if venue_link else "Unknown"

        # Extract location (state/country)
        location_elem = item.find("span", {"class": "location"})
        if not location_elem:
            location_elem = item.find("small")
        location_text = location_elem.get_text(strip=True) if location_elem else ""

        # Parse state from location
        state_code = None
        if location_text:
            # Try to extract state code (e.g., "CA" from "San Francisco, CA")
            parts = location_text.split(",")
            if len(parts) >= 2:
                state_code = parts[-1].strip().upper()
                if len(state_code) != 2:
                    state_code = None

        # Extract beer style
        style_elem = item.find("em") or item.find("small", {"class": "style"})
        beer_style = style_elem.get_text(strip=True) if style_elem else "Unknown"
        # Clean up style (remove extra info)
        if " - " in beer_style:
            beer_style = beer_style.split(" - ")[0]

        # Extract rating
        rating = None
        rating_elem = item.find("span", {"class": "rating"})
        if not rating_elem:
            # Look for star rating
            rating_elem = item.find("span", {"class": re.compile(r"stars")})
        if rating_elem:
            rating_text = rating_elem.get_text(strip=True)
            # Extract number from rating text
            match = re.search(r"(\d+\.?\d*)", rating_text)
            if match:
                try:
                    rating = float(match.group(1))
                except ValueError:
                    pass

        # Extract serving style
        serving_style = "Unknown"
        serving_elem = item.find("span", {"class": re.compile(r"serving|glass")})
        if serving_elem:
            serving_style = serving_elem.get_text(strip=True)

        # Extract date
        date_elem = item.find("time") or item.find("span", {"class": "date"})
        checkin_date = "Unknown"
        if date_elem:
            checkin_date = date_elem.get("datetime") or date_elem.get_text(strip=True)

        return {
            "checkin_date": checkin_date,
            "beer_name": beer_name,
            "beer_style": beer_style,
            "brewery_name": brewery_name,
            "venue_name": venue_name,
            "place_state": state_code,
            "rating": rating,
            "serving_style": serving_style,
        }

    except Exception as e:
        print(f"Error parsing checkin: {e}")
        return None


def get_user_info(session: requests.Session, username: str) -> dict:
    """Get user profile info from their public profile page."""
    try:
        url = f"{UNTAPPD_BASE}/user/{username}"
        response = session.get(url, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        # Try to extract username and checkin count
        user_info = {
            "username": username,
            "first_name": None,
            "total_checkins": None,
        }

        # Look for checkin count in stats
        stats_elem = soup.find("span", {"class": "count"})
        if stats_elem:
            count_text = stats_elem.get_text(strip=True)
            match = re.search(r"(\d+)", count_text)
            if match:
                user_info["total_checkins"] = int(match.group(1))

        return user_info

    except Exception as e:
        print(f"Warning: Could not fetch user info: {e}")
        return {"username": username, "total_checkins": None}

