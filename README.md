# Untappd Drinks Dashboard

A comprehensive dashboard for visualizing your Untappd check-in data with interactive maps and statistics.

## Features

- 🗺️ Interactive US state choropleth map showing check-in locations
- 📊 Check-in trends over customizable time ranges (Week, Month, Year, Year-to-Date)
- 🍺 Top beer styles by check-in volume
- ⭐ Average ratings by serving style
- 📱 Interactive Streamlit dashboard
- 🔐 **Web scraping login** (no API key needed!)
- 🔑 OAuth login to automatically fetch your Untappd data
- 📥 Upload CSV/JSON exports from Untappd

## Installation

1. Clone or download this project
2. Create a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Getting Started

### Option 1: Web Scraping (Recommended - No API Key Required)

1. Activate your virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Scrape your Untappd data:
   ```bash
   # Login to your Untappd account
   python run.py scrape-login --username YOUR_USERNAME --password YOUR_PASSWORD
   
   # Fetch your check-ins and generate charts
   python run.py scrape-fetch --output-dir ./charts
   ```

### Option 1b: Selenium Browser Automation (Firefox or Chrome)

Use Selenium when standard scraping is blocked and you want a real browser session.

```bash
# Login with Firefox (headless by default)
python run.py selenium-login --username YOUR_USERNAME --password YOUR_PASSWORD --browser firefox

# Or use Chrome
python run.py selenium-login --username YOUR_USERNAME --password YOUR_PASSWORD --browser chrome

# Download your check-ins
python run.py selenium-fetch --browser firefox --output my_checkins.csv

# Run with a visible browser window
python run.py selenium-fetch --browser chrome --headed --output-dir ./charts

# Keep login fully manual (good for CAPTCHA/2FA), then automate scraping after login
python run.py selenium-manual-fetch --username YOUR_USERNAME --browser chrome --output my_checkins.csv

# If CAPTCHA still blocks Selenium-launched Chrome, login first in a real Chrome window:
#   google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/untappd-manual
# then attach Selenium to that live browser
python run.py selenium-manual-fetch --username YOUR_USERNAME --browser chrome --attach-debugger 127.0.0.1:9222 --output my_checkins.csv
```

4. View the results in Streamlit:
   ```bash
   python run.py streamlit
   ```

### Option 2: Interactive Streamlit Dashboard

#### Using Web Scraping

1. Launch the dashboard:
   ```bash
   python run.py streamlit
   ```

2. Select "Web Scraping" in the sidebar
3. Enter your Untappd username and password
4. Click "Login with Web Scraping"
5. Click "Fetch My Check-ins (Web Scraping)" to download all your data

#### Using Untappd API (Commercial Accounts Only)

1. Register your app with Untappd:
   - Visit https://untappd.com/api/dashboard
   - Create a new app to get your Client ID and Client Secret

2. Launch the dashboard:
   ```bash
   python run.py streamlit
   ```

3. Select "Untappd API" in the sidebar, click "Login to Untappd API", and enter your credentials
4. Click "Fetch My Check-ins (API)" to automatically download all your check-in data

#### Using CSV/JSON Export

1. Export your check-ins from Untappd as CSV or JSON
2. Launch the dashboard:
   ```bash
   python run.py streamlit
   ```
3. Select "Upload CSV/JSON" and choose your file
4. The app will auto-detect columns; adjust if needed

### Option 3: Command Line Interface

#### Web Scraping (Recommended)

```bash
# Login to your Untappd account
python3 run.py scrape-login --username YOUR_USERNAME --password YOUR_PASSWORD

# Fetch check-ins and render charts
python3 run.py scrape-fetch --output-dir ./charts

# Fetch and save to CSV
python3 run.py scrape-fetch --output my_checkins.csv

# Specify a timeframe (default: Month)
python3 run.py scrape-fetch --timeframe Year --output-dir ./charts
```

#### Selenium (Firefox or Chrome)

```bash
# Login via Selenium
python3 run.py selenium-login --username YOUR_USERNAME --password YOUR_PASSWORD --browser firefox

# Fetch with Selenium
python3 run.py selenium-fetch --browser chrome --output my_checkins.csv

# Manual login in browser, automated post-login scraping
python3 run.py selenium-manual-fetch --username YOUR_USERNAME --browser chrome --output my_checkins.csv
```

#### Untappd API (If you have commercial access)

```bash
# Login with API credentials
python3 run.py login --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET

# Fetch check-ins
python3 run.py fetch --output-dir ./charts
```

#### Render Charts from CSV/JSON

```bash
python3 run.py render --file checkins.csv --timeframe Month --output-dir ./output
```

## Data Structure

The app expects the following columns (auto-detected):

- **Date**: checkin_date, created_at, date, timestamp, checkin_time, time, datetime
- **State**: state, venue_state, brewery_state, location_state, place_state
- **Beer Style**: beer_style, style, beer_style_name, style_name
- **Serving Style**: serving_style, serving_type, serving, beer_serving, glass_type, glass
- **Rating**: rating, rating_score, rating_overall, beer_rating
- **Place**: venue_name, brewery_name, place_name, location_name, venue

## How It Works

### Untappd API Integration

The app uses Untappd's OAuth 2.0 authentication flow:

1. **Login**: You provide Client ID and Client Secret
2. **OAuth Flow**: Your browser opens Untappd's auth page
3. **Authorization Code**: You grant permission to the app
4. **Access Token**: The app receives a token to access your data
5. **Secure Storage**: The token is saved to `~/.untappd/.untappd_credentials`
6. **Data Fetching**: The app fetches your check-ins via the Untappd API

### Privacy & Security

**Web Scraping:**
- Your credentials are stored locally only on your machine
- No API registration or external accounts needed
- Faster setup, no commercial account required
- Respectful rate limiting (pauses between requests)

**API Access:**
- Your credentials are never shared with anyone
- The access token is stored locally on your machine only
- You can revoke access anytime by removing the credentials file or logging out in the app
- All data processing happens locally on your machine

Both methods keep your data private and secure.

## Troubleshooting

**"Streamlit is not installed" error**
```bash
pip install streamlit
```

**"No valid U.S. state information found"**
- Make sure your CSV/JSON has a state column
- Check that state values are US state names or codes (e.g., "California" or "CA")

**Token expired or invalid**
- Run the login command again to re-authenticate
- Remove `~/.untappd/.untappd_credentials` and start fresh

**Import errors**
- Make sure you're in the virtual environment: `source .venv/bin/activate`
- Reinstall dependencies: `pip install -r requirements.txt`

## File Structure

```
untapped_data/
├── run.py                 # CLI entry point
├── streamlit_app.py       # Interactive Streamlit dashboard
├── untapped.py            # Data processing & charting functions
├── untapped_api.py        # Untappd API client & OAuth
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## License

This project is provided as-is for personal use.
