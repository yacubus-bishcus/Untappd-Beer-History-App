import json
import os
import time
from pathlib import Path
from typing import Optional

import pandas as pd
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

UNTAPPD_BASE = "https://untappd.com"
CREDENTIALS_FILE = ".untappd_credentials_selenium"
BROWSER_CHOICES = {"firefox", "chrome"}


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

    if headless:
        options.add_argument("--headless")

    # Avoid being detected as a bot
    if browser == "firefox":
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")

    # Set a realistic user agent
    options.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    )

    try:
        if browser == "chrome":
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        else:
            service = FirefoxService(GeckoDriverManager().install())
            driver = webdriver.Firefox(service=service, options=options)
    except Exception as e:
        browser_name = browser.capitalize()
        print(f"Error setting up {browser_name} WebDriver: {e}")
        raise

    return driver


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
    df["checkin_date"] = pd.to_datetime(df["checkin_date"], errors="coerce")
    return df.sort_values("checkin_date", ascending=False)


def parse_checkin_item(item) -> Optional[dict]:
    """Parse a single checkin item from HTML."""
    try:
        # Extract beer info
        beer_link = item.find("a", {"class": "label"})
        if not beer_link:
            beer_link = item.find("a", {"href": lambda x: x and "/beer/" in x})
        
        beer_name = beer_link.get_text(strip=True) if beer_link else "Unknown"
        
        # Extract brewery info
        brewery_link = item.find("a", {"href": lambda x: x and "/brewery/" in x})
        brewery_name = brewery_link.get_text(strip=True) if brewery_link else "Unknown"
        
        # Extract venue info
        venue_link = item.find("a", {"href": lambda x: x and "/venue/" in x})
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
