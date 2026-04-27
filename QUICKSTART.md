# Quick Start: Untappd Integration

⚠️ **Important**: Untappd API is now limited to commercial accounts only. Use **web scraping** (no API key needed!) instead.

## Option 1: Web Scraping (Recommended - No API Key Needed)

### Step 1: Set Up Your Environment

```bash
# Navigate to the project directory
cd /Users/jacobbickus/Python_Files/apps/untapped_data

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Authenticate with Web Scraping

```bash
python3 run.py scrape-login --username YOUR_USERNAME --password YOUR_PASSWORD
```

Replace `YOUR_USERNAME` and `YOUR_PASSWORD` with your Untappd account credentials.

**What happens:**
- Your credentials are securely saved locally
- Your session is authenticated with Untappd

### Step 3: Fetch Your Data

```bash
# Fetch check-ins and generate charts
python3 run.py scrape-fetch --output-dir ./my_charts

# Or save raw data to CSV
python3 run.py scrape-fetch --output my_checkins.csv

# Fetch with specific timeframe
python3 run.py scrape-fetch --timeframe Year --output-dir ./charts
```

Available timeframes: `Week`, `Month`, `Year`, `Year to date`

### Step 4: View Your Dashboard

#### Interactive Streamlit Dashboard

```bash
python3 run.py streamlit
```

This opens an interactive web app where you can:
- Toggle between web scraping, Untappd API, or CSV/JSON upload
- View your map of check-in locations
- See check-in trends over time
- Explore top beer styles
- Check ratings by serving style
- Filter by time range

#### Command-Line Charts

The `scrape-fetch` command with `--output-dir` automatically generates HTML charts:

```bash
# Charts are saved as:
# - state_map.html        (Interactive US map)
# - checkins.html         (Check-in trends)
# - styles.html           (Top beer styles)
# - ratings.html          (Ratings by serving style)
# - summary.txt           (Text summary of stats)
```

---

## Option 2: Untappd API (For Commercial Accounts Only)

### Step 1: Register Your App with Untappd

1. Visit https://untappd.com/api/dashboard
2. Log in to your Untappd account (create one if you don't have it)
3. Click "Create New App"
4. Fill in the app details:
   - **Name**: "Untappd Dashboard" (or your preferred name)
   - **Website**: http://localhost (or any URL)
   - **Redirect URL**: http://localhost:8888/callback
5. Accept terms and click "Create App"
6. Copy your **Client ID** and **Client Secret**

### Step 2: Set Up Your Environment

```bash
# Navigate to the project directory
cd /Users/jacobbickus/Python_Files/apps/untapped_data

# Activate virtual environment
source .venv/bin/activate

# Install dependencies (already done, but just in case)
pip install -r requirements.txt
```

### Step 3: Authenticate with API

```bash
python3 run.py login --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET
```

Replace `YOUR_CLIENT_ID` and `YOUR_CLIENT_SECRET` with the values from your Untappd app dashboard.

**What happens:**
- Your browser opens Untappd's authorization page
- You grant permission to access your check-in data
- A code appears in the redirect URL
- Paste that code into the terminal prompt
- Your credentials are securely saved locally

### Step 4: Fetch Your Data

```bash
# Fetch check-ins and generate charts
python3 run.py fetch --output-dir ./my_charts

# Or save raw data to CSV
python3 run.py fetch --output my_checkins.csv

# Fetch with specific timeframe
python3 run.py fetch --timeframe Year --output-dir ./charts
```

---

## Option 3: Upload Data from CSV/JSON

If you prefer to use a CSV/JSON export instead of logging in:

```bash
python3 run.py render --file path/to/export.csv --timeframe Month --output-dir ./charts
```

Or use the interactive dashboard:

```bash
python3 run.py streamlit
# Then select "Upload CSV/JSON" in the sidebar
```

## Commands Reference

```bash
# Web Scraping (No API Key Needed)
python3 run.py scrape-login --username USER --password PASS
python3 run.py scrape-fetch [options]

# Untappd API (Commercial accounts)
python3 run.py login --client-id ID --client-secret SECRET
python3 run.py fetch [options]

# Render charts from file
python3 run.py render --file DATA.csv [options]
  --timeframe RANGE           # Select time range
  --output-dir FOLDER         # Save charts
  --date-col COLUMN           # Specify date column
  --state-col COLUMN          # Specify state column
  # ... and more column mappings

# Launch Streamlit dashboard
python3 run.py streamlit

# Launch a real Chrome window for manual login, then export beer history
python3 run.py selenium-launch-chrome --page beers --username YOUR_USERNAME
python3 run.py selenium-fetch-beers --username YOUR_USERNAME --attach-debugger 127.0.0.1:9222 --backstop-total 250 --output my_beers.csv

# Show help
python3 run.py --help
python3 run.py scrape-login --help
python3 run.py scrape-fetch --help
```

## Tips

- **First time?** Start with web scraping (`scrape-login` + `scrape-fetch`) - it's the easiest!
- **Web scraping vs API**: Scraping is slower but requires no registration. API is faster but limited to commercial accounts.
- **Large data sets?** Fetching might take a while for 100+ check-ins. Be patient!
- **Privacy:** Your credentials are stored locally in `~/.untappd/.untappd_credentials`. Keep it safe!
- **Offline mode:** Once you've downloaded data to CSV, you can render charts offline using the `render` command
- **Different user:** Use public profiles with scraping to view other users' check-ins

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Module not found" errors | Make sure venv is activated: `source .venv/bin/activate` |
| Web scraping login fails | Double-check your username and password. Make sure your account isn't locked. |
| "No check-ins found" | Might take a while to load. Try again, or check your network connection. |
| API token expired | Run the login command again to refresh |
| States not showing on map | Make sure your state column has US state names or codes |
| BeautifulSoup not found | Run `pip install beautifulsoup4` |

## Support

For web scraping issues, make sure you have BeautifulSoup4 installed:
```bash
pip install beautifulsoup4
```

For issues with the Untappd API, visit: https://untappd.com/api/docs

For questions about this dashboard, check the README.md file.
