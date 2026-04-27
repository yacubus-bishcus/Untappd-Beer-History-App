# Untappd Beer History Exporter

This project exports your Untappd beer history with Selenium, saves it to `my_beers.csv`, and opens a Streamlit dashboard for reviewing the results.

Supported Python versions: `3.9+`

## Desktop Launcher

Desktop launchers are included for both macOS and Windows:

```text
macOS:   Untappd Beer History.app
Windows: start_desktop_app.bat
```

The packaged desktop experience works like this:

1. Create `.venv` if needed
2. Install dependencies
3. Ask for the user's Untappd username on first launch and save it locally
4. Run the first sync automatically when no `my_beers.csv` exists yet
5. Open a desktop control window for later refreshes and dashboard access
6. Let the user refresh beer data or open the dashboard without using Terminal or Command Prompt

On macOS, the main launcher is now a native Cocoa window built with `PyObjC`, packaged inside a real `.app` bundle for Finder. The existing `start_desktop_app.command` is still included as a fallback for development or troubleshooting.
The platform-specific launcher files live in:

```text
deploy/mac
deploy/windows
```

If Python is missing or older than `3.9`, the launchers prompt the user to open the official Python download page. If the macOS Python build does not include the Cocoa bridge, the app falls back to the browser-based Streamlit dashboard instead of crashing. Windows continues to use the existing Python desktop launcher flow.

Note: the macOS bundle is a native `.app`, but it still runs the Python project under the hood. Windows is still distributed as a script launcher rather than a fully packaged `.exe`.

## What `python run.py` Does

Running `python run.py` from `apps/untapped_data` will:

1. If `my_beers.csv` already exists, skip Untappd and open the Streamlit dashboard immediately.
2. If you pass `--update`, launch Chrome with remote debugging enabled.
3. Open `https://untappd.com/user/<configured-username>/beers`.
4. Wait for you to finish logging in manually if needed.
5. Click `Show More` until all beers are loaded.
6. Save the export to `my_beers.csv`.
7. Optionally honor `--backstop-total` if you pass one during a refresh.
8. Open the Streamlit dashboard.

Defaults:

- Username: value saved in `app_config.json`
- Debugger address: `127.0.0.1:9222`
- Output file: `my_beers.csv`

## Setup

```bash
cd /Users/jacobbickus/Python_Files/apps/untapped_data
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Main Workflow

```bash
python3 run.py
python3 run.py --update
```

## Shareable Desktop Bundle

To create a shareable desktop bundle:

```bash
cd /Users/jacobbickus/Python_Files/apps/untapped_data
./package_desktop_bundle.sh
```

This creates:

```text
dist/UntappdBeerHistory-desktop.zip
```

The recipient can unzip it and then:

- on macOS, open `Untappd Beer History.app`
- on Windows, open `Windows/start_desktop_app.bat`

For local fallback launching from source:

- macOS: `deploy/mac/start_desktop_app.command`
- Windows: `deploy/windows/start_desktop_app.bat`

## Commands

```bash
# Run the full default workflow
python3 run.py

# Force a fresh download from Untappd
python3 run.py --update

# Launch Chrome only
python3 run.py selenium-launch-chrome

# Attach to Chrome and export beers
python3 run.py selenium-fetch-beers

# Override the default row backstop
python3 run.py selenium-fetch-beers --backstop-total 250

# Open the dashboard
python3 run.py streamlit
```

## Output Columns

The beer export is saved with these columns:

- `Beer Name`
- `Producer`
- `Location`
- `Beer Type`
- `My Rating`
- `Global Rating`
- `First Date`
- `Recent Date`

## Notes

- `selenium-fetch-beers` clicks the page's `Show More` control until it reaches the backstop total or no more items load.
- During export, Selenium now visits each unique producer page once and tries to extract the producer's city/state into `Location`.
- Producer locations are cached locally in `producer_location_cache.json`
- `selenium-fetch-beers` uses the current row count in the output CSV as a default backstop only when you run that command directly without an explicit `--backstop-total`.
- `python3 run.py` opens Streamlit immediately when `my_beers.csv` already exists. Pass `--update` to refresh from Untappd first.
- The Streamlit app reads `my_beers.csv` by default.
- Streamlit builds a global country map directly from the `Location` values in `my_beers.csv`.

## File Structure

```text
untapped_data/
├── deploy/
│   ├── mac/
│   └── windows/
├── run.py
├── streamlit_app.py
├── untapped.py
├── untapped_selenium.py
├── requirements.txt
└── my_beers.csv
```
