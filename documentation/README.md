# Untappd Beer History Exporter

This project exports your Untappd beer history with Selenium, saves it under `data/my_beers.csv`, and opens a Streamlit dashboard for reviewing the results.

Supported Python versions: `3.9+`

## Project Layout

```text
untapped_data/
├── data/
├── deploy/
├── documentation/
└── src/
```

- `data/`: generated CSVs, local app config, and producer cache
- `deploy/`: macOS and Windows launchers, packaging script, and app assets
- `documentation/`: setup and usage docs
- `src/`: Python source files and `requirements.txt`

## Desktop Launcher

Desktop launchers are included for both macOS and Windows:

```text
macOS:   deploy/mac/Untappd Beer History.app
Windows: deploy/windows/start_desktop_app.bat
```

The desktop flow:

1. Creates `.venv` if needed
2. Installs dependencies from `src/requirements.txt`
3. Saves the Untappd username in `data/app_config.json`
4. Runs the first sync automatically when `data/my_beers.csv` is missing
5. Opens a desktop control window for later refreshes and dashboard access
6. Lets the user refresh beer data or open the dashboard without using Terminal or Command Prompt
7. Shows a loading bar while work is in progress

For a GitHub ZIP download on macOS:

1. Download the repository ZIP from GitHub
2. Unzip it
3. Open `deploy/mac/Untappd Beer History.app`
4. If Gatekeeper blocks the first launch, right-click the app and choose `Open`

## Setup

```bash
cd /Users/jacobbickus/Python_Files/apps/untapped_data
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt
```

## Main Workflow

```bash
python3 src/run.py
python3 src/run.py --update
```

Default behavior:

1. If `data/my_beers.csv` already exists, Streamlit opens immediately
2. With `--update`, Chrome launches for manual login if needed
3. Selenium exports the beer history to `data/my_beers.csv`
4. The dashboard opens after export

## Shareable Desktop Bundle

To create a shareable desktop bundle:

```bash
cd /Users/jacobbickus/Python_Files/apps/untapped_data
./deploy/package_desktop_bundle.sh
```

This creates:

```text
deploy/dist/UntappdBeerHistory-desktop.zip
```

## Commands

```bash
python3 src/run.py
python3 src/run.py --update
python3 src/run.py selenium-launch-chrome
python3 src/run.py selenium-fetch-beers
python3 src/run.py selenium-fetch-beers --backstop-total 250
python3 src/run.py streamlit
```

## Output Files

- `data/my_beers.csv`
- `data/producer_location_cache.json`
- `data/app_config.json`

## Notes

- `src/run.py` opens Streamlit immediately when `data/my_beers.csv` already exists. Pass `--update` to refresh from Untappd first.
- The Streamlit app reads `data/my_beers.csv` by default.
- Producer locations are cached in `data/producer_location_cache.json`.
- The macOS bundle is a native `.app`, but it still runs the Python project under the hood.
