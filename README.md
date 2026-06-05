# Untappd Beer History

Export your Untappd beer history with Selenium, save it to CSV, and review local statistics in a native desktop app built with Toga.

## Best Download Option

If you just want to use the app on macOS, download the latest DMG from GitHub Releases.

- `GitHub Releases`: packaged `.dmg` installer
- `Download ZIP`: source code only, intended for development or manual setup

## Project Layout

```text
Untappd-Beer-History-App/
├── data/
├── documentation/
├── resources/
├── src/
└── pyproject.toml
```

- `data/`: generated CSV, cache files, local config, and generated statistics HTML
- `documentation/`: setup and usage docs
- `resources/`: Briefcase app icon assets
- `src/`: Python source files and `requirements.txt`
- `pyproject.toml`: Briefcase packaging configuration

## Quick Start From Source

Source mode is intended for development and manual local runs.

```bash
cd apps/Untappd-Beer-History-App
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt
python3 src/run.py
```

The app opens a native window. Use:

- `Update Data` to launch Chrome, sign in to Untappd if needed, scrape beer history, and write `data/my_beers.csv`
- `Clean Run` to ignore the existing CSV row count/backstop and fetch your full visible Untappd beer history from scratch
- `Statistics` to generate and open local statistics HTML with a consumed-location heatmap
- `Stop Running Task` to stop a scrape or map build and close the open statistics tab when possible

CLI clean run:

```bash
python3 src/run.py --clean-run
python3 src/run.py --clean-run --no-ui
python3 src/run.py selenium-fetch-beers --clean-run
```

For a Raspberry Pi 5 server, run the CLI from source with Chromium/chromedriver and a persistent `UNTAPPD_DATA_DIR`. The Pi is best used as the scraper/report host; see `documentation/README.md` for a systemd/timer example and LAN report serving.

## CSV Schema

The generated CSV is `data/my_beers.csv`.

Important columns:

- `Beer Name`
- `Producer`
- `Producer Location`
- `Consumed Location`
- `Lat`
- `Long`
- `Beer Type`
- `My Rating`
- `Global Rating`
- `First Date`
- `Recent Date`
- `Total Checkins`

`Producer Location` is where the beer is produced. `Consumed Location`, `Lat`, and `Long` come from the Untappd check-in venue page. The heatmap uses consumed-location coordinates and ignores `Untappd at Home` only for the map.

## Generated Files

- `data/my_beers.csv`: exported beer history
- `data/producer_location_cache.json`: producer page location cache
- `data/consumed_location_cache.json`: consumed venue city/coordinate cache
- `data/app_config.json`: local app settings
- `data/beer_statistics.html`: generated statistics page
- `data/beer_map_fragment.js`: generated Plotly map data

## Build The macOS App

Briefcase is the supported macOS packaging path.

```bash
python3 -m venv .briefcase-venv
source .briefcase-venv/bin/activate
pip install briefcase
BRIEFCASE_HOME=.briefcase-home briefcase create macOS
BRIEFCASE_HOME=.briefcase-home briefcase update macOS
BRIEFCASE_HOME=.briefcase-home briefcase build macOS
BRIEFCASE_HOME=.briefcase-home briefcase package macOS --adhoc-sign
```

The rebuilt direct app appears in:

- `build/untappd_beer_history/macos/app/Untappd Beer History.app`

The packaged installer appears in:

- `dist/Untappd Beer History-0.2.1.dmg`

## Build The Windows Installer

Windows packaging uses PyInstaller plus Inno Setup and should be run on Windows.

Requirements:

- Python 3.12
- Inno Setup 6
- Google Chrome

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\packaging\windows\build-installer.ps1
```

The PyInstaller app appears in:

- `dist\UntappdBeerHistory\UntappdBeerHistory.exe`

The Inno Setup installer appears in:

- `dist\installer\Untappd-Beer-History-Setup-0.2.1.exe`

See `packaging/windows/README.md` for build options.

## More Docs

- `documentation/README.md`
- `documentation/QUICKSTART.md`
