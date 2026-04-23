import json
import os
import webbrowser
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

UNTAPPD_API_BASE = "https://api.untappd.com/v4"
CREDENTIALS_FILE = ".untappd_credentials"


def get_credentials_path():
    return Path.home() / ".untappd" / CREDENTIALS_FILE


def ensure_credentials_dir():
    cred_dir = Path.home() / ".untappd"
    cred_dir.mkdir(exist_ok=True, parents=True)


def save_credentials(client_id: str, client_secret: str, access_token: Optional[str] = None):
    """Save Untappd API credentials to disk."""
    ensure_credentials_dir()
    creds = {
        "client_id": client_id,
        "client_secret": client_secret,
        "access_token": access_token,
    }
    with open(get_credentials_path(), "w") as f:
        json.dump(creds, f, indent=2)
    os.chmod(get_credentials_path(), 0o600)


def load_credentials() -> dict:
    """Load Untappd API credentials from disk."""
    cred_path = get_credentials_path()
    if not cred_path.exists():
        return {}
    with open(cred_path, "r") as f:
        return json.load(f)


def save_access_token(access_token: str):
    """Update access token while preserving other credentials."""
    creds = load_credentials()
    creds["access_token"] = access_token
    save_credentials(creds.get("client_id"), creds.get("client_secret"), access_token)


def authenticate(client_id: str, client_secret: str) -> str:
    """
    Perform OAuth flow to get access token.
    Returns the access token.
    """
    redirect_uri = "http://localhost:8888/callback"
    auth_url = (
        f"https://untappd.com/oauth/authenticate?"
        f"client_id={client_id}"
        f"&response_type=code"
        f"&redirect_uri={redirect_uri}"
    )

    print("Opening Untappd authentication page in your browser...")
    print(f"If the browser doesn't open, visit: {auth_url}")
    webbrowser.open(auth_url)

    auth_code = input("\nEnter the auth code from the redirect URL (or paste the full URL): ").strip()

    # Extract code from URL if user pastes full URL
    if auth_code.startswith("http"):
        try:
            auth_code = auth_code.split("code=")[1].split("&")[0]
        except IndexError:
            raise ValueError("Could not extract code from URL")

    # Exchange code for access token
    token_url = f"{UNTAPPD_API_BASE}/oauth/authorize/grant"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "response_type": "code",
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": redirect_uri,
    }

    response = requests.post(token_url, json=payload)
    response.raise_for_status()

    data = response.json()
    if data.get("meta", {}).get("code") != 200:
        raise ValueError(f"Authentication failed: {data.get('meta', {}).get('error_detail')}")

    access_token = data["response"]["access_token"]
    save_access_token(access_token)
    print(f"✓ Successfully authenticated! Access token saved.")
    return access_token


def fetch_user_checkins(access_token: str, username: Optional[str] = None, limit: int = 50) -> pd.DataFrame:
    """
    Fetch check-ins from Untappd for the authenticated user.
    If username is provided, fetch that user's checkins instead.
    """
    checkins = []
    offset = 0
    max_iterations = 100  # Safety limit to prevent infinite loops

    endpoint = "user/checkins" if username is None else f"user/{username}/checkins"

    for iteration in range(max_iterations):
        url = f"{UNTAPPD_API_BASE}/{endpoint}"
        params = {
            "access_token": access_token,
            "limit": limit,
            "offset": offset,
            "sort": "date"
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("meta", {}).get("code") != 200:
                error_msg = data.get("meta", {}).get("error_detail", "Unknown error")
                raise ValueError(f"API error: {error_msg}")

            batch = data.get("response", {}).get("checkins", {}).get("items", [])
            if not batch:
                break

            for checkin in batch:
                beer = checkin.get("beer", {})
                brewery = checkin.get("brewery", {})
                venue = checkin.get("venue", {})

                checkins.append({
                    "checkin_id": checkin.get("checkin_id"),
                    "checkin_date": checkin.get("created_at"),
                    "beer_name": beer.get("beer_name"),
                    "beer_style": beer.get("beer_style"),
                    "brewery_name": brewery.get("brewery_name"),
                    "venue_name": venue.get("venue_name"),
                    "place_state": venue.get("location", {}).get("venue_state"),
                    "place_city": venue.get("location", {}).get("venue_city"),
                    "place_country": venue.get("location", {}).get("venue_country"),
                    "rating": checkin.get("rating_score"),
                    "serving_style": checkin.get("serving", {}).get("serving_name"),
                    "comment": checkin.get("checkin_comment"),
                })

            offset += limit
            print(f"  Fetched {len(checkins)} check-ins...")

        except requests.RequestException as e:
            print(f"Network error while fetching checkins: {e}")
            break

    if not checkins:
        raise ValueError("No check-ins found for this user")

    df = pd.DataFrame(checkins)
    df["checkin_date"] = pd.to_datetime(df["checkin_date"])
    return df.sort_values("checkin_date", ascending=False)


def get_user_info(access_token: str) -> dict:
    """Fetch authenticated user's profile info."""
    url = f"{UNTAPPD_API_BASE}/user/info"
    params = {"access_token": access_token}

    response = requests.get(url, params=params)
    response.raise_for_status()

    data = response.json()
    if data.get("meta", {}).get("code") != 200:
        raise ValueError(f"Failed to fetch user info: {data.get('meta', {}).get('error_detail')}")

    user = data.get("response", {}).get("user", {})
    return {
        "username": user.get("user_name"),
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
        "total_checkins": user.get("stats", {}).get("total_checkins"),
    }


def validate_token(access_token: str) -> bool:
    """Check if the access token is still valid."""
    try:
        get_user_info(access_token)
        return True
    except Exception:
        return False
