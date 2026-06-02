# Untappd Beer History Exporter

This project exports Untappd beer history with Selenium, writes `data/my_beers.csv`, and provides a native Toga desktop UI for updating data and generating local statistics.

Source workflow Python: `3.9+`
Briefcase packaging Python: `3.12+`

## Download Options

- `GitHub Releases`: best option for macOS users who just want to install the app
- `Download ZIP`: source code only, best for development or manual local setup

## Project Layout

```text
Untappd-Beer-History-App/
├── data/
├── documentation/
├── resources/
├── src/
└── pyproject.toml
```

- `data/`: generated CSV, local app config, caches, and statistics HTML
- `documentation/`: setup and usage docs
- `resources/`: Briefcase app icon assets
- `src/`: Python source files and `requirements.txt`
- `pyproject.toml`: Briefcase packaging configuration

## Setup

```bash
cd /Users/jacobbickus/Python_Files/apps/Untappd-Beer-History-App
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt
```

## Main Workflow

```bash
python3 src/run.py
python3 src/run.py --update
python3 src/run.py --clean-run
python3 src/run.py --clean-run --no-ui
```

Default behavior:

1. If `data/my_beers.csv` already exists, the native app opens so you can view statistics or refresh data
2. With `--update`, Chrome launches for manual login if needed
3. Selenium exports beer history to `data/my_beers.csv`
4. The native app can generate `data/beer_statistics.html` and `data/beer_map_fragment.js`

Use `--clean-run` when you want the scraper to act like the export is brand new. It ignores the existing CSV row count/backstop and keeps loading Untappd history until the page no longer has `Show More`. The old CSV is overwritten only after the new scrape succeeds.

## Native App Controls

- `Update Data`: refreshes beer history from Untappd
- `Clean Run`: ignores the existing CSV row count/backstop and fetches all visible Untappd beer history from scratch
- `Statistics`: builds and opens the local statistics page
- `Open Export Folder`: opens the folder containing the CSV and generated HTML
- `Stop Running Task`: stops the active task; for statistics generation, it also tries to close the open browser tab

## Commands

```bash
python3 src/run.py
python3 src/run.py --update
python3 src/run.py --clean-run
python3 src/run.py --clean-run --no-ui
python3 src/run.py selenium-launch-chrome
python3 src/run.py selenium-fetch-beers
python3 src/run.py selenium-fetch-beers --clean-run
python3 src/run.py selenium-fetch-beers --backstop-total 250
```

## Raspberry Pi 5 Server Setup

The app is a native Toga desktop app, so a headless Pi is best used as the scraper/report host rather than the primary GUI machine. Run the CLI on the Pi, store the CSV and generated HTML in a persistent data directory, and optionally serve that directory over your LAN.

Install the project:

```bash
sudo apt update
sudo apt install -y python3-venv chromium-browser chromium-driver
git clone <your-repo-url> ~/apps/Untappd-Beer-History-App
cd ~/apps/Untappd-Beer-History-App
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt
```

Choose a stable data location:

```bash
mkdir -p /srv/untappd-beer-history/data
export UNTAPPD_DATA_DIR=/srv/untappd-beer-history/data
```

Run a full rebuild:

```bash
source .venv/bin/activate
UNTAPPD_DATA_DIR=/srv/untappd-beer-history/data \
python3 src/run.py --username YOUR_UNTAPPD_USERNAME --clean-run --no-ui
```

For first login or Cloudflare/CAPTCHA prompts, use one of these:

- Run the command from a desktop session on the Pi with a monitor, VNC, or X forwarding
- Launch Chromium manually on the Pi with remote debugging, log in interactively, then run `selenium-fetch-beers`
- Do the first clean run on your Mac, copy `data/my_beers.csv` and cache files to the Pi, then use the Pi for scheduled refreshes

Optional systemd service for scheduled refreshes:

```ini
[Unit]
Description=Untappd Beer History refresh

[Service]
Type=oneshot
WorkingDirectory=/home/pi/apps/Untappd-Beer-History-App
Environment=UNTAPPD_DATA_DIR=/srv/untappd-beer-history/data
ExecStart=/home/pi/apps/Untappd-Beer-History-App/.venv/bin/python src/run.py --username YOUR_UNTAPPD_USERNAME --update --no-ui
```

Optional timer:

```ini
[Unit]
Description=Run Untappd Beer History refresh daily

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

To view generated files from another computer, serve the data directory with nginx or a small local HTTP server:

```bash
cd /srv/untappd-beer-history/data
python3 -m http.server 8088
```

Then open `http://pi5server:8088/beer_statistics.html` on your LAN after generating statistics.

## Output Files

- `data/my_beers.csv`
- `data/producer_location_cache.json`
- `data/consumed_location_cache.json`
- `data/app_config.json`
- `data/beer_statistics.html`
- `data/beer_map_fragment.js`

## CSV Columns

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

`Producer Location` comes from the producer page. `Consumed Location`, `Lat`, and `Long` come from the Untappd venue page linked from each check-in. The heatmap uses consumed-location coordinates and excludes `Untappd at Home` only from the map.

## Briefcase Packaging

The macOS distribution path is Briefcase.

Project files for Briefcase live at:

```text
pyproject.toml
src/untappd_beer_history/
resources/appicon.icns
```

Typical macOS packaging flow:

```bash
python3 -m venv .briefcase-venv
source .briefcase-venv/bin/activate
pip install briefcase
mkdir -p .briefcase-home
BRIEFCASE_HOME=.briefcase-home briefcase create macOS
BRIEFCASE_HOME=.briefcase-home briefcase update macOS
BRIEFCASE_HOME=.briefcase-home briefcase build macOS
BRIEFCASE_HOME=.briefcase-home briefcase package macOS --adhoc-sign
```

Recommended retest flow after code changes:

1. Rebuild with `briefcase update macOS` and `briefcase build macOS`
2. Test the direct app bundle under `build/`
3. Package a fresh DMG
4. Reinstall from the new DMG if the direct bundle looks good

## Notes

- Producer locations are cached in `data/producer_location_cache.json`
- Consumed venue coordinates are cached in `data/consumed_location_cache.json`
- The native desktop UI uses Toga and generates local statistics HTML
- The bundled app window shows a version/build stamp so you can tell whether you are opening a fresh build or a stale installed copy
