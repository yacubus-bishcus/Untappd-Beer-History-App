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
├── packaging/
├── resources/
├── src/
└── pyproject.toml
```

- `data/`: generated CSV, local config, and generated statistics HTML
- `packaging/`: platform-specific build files
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

On Windows, activate the environment with `.venv\Scripts\Activate.ps1`.

The app opens a native window. Use:

- `Update Data` to load the requested check-in range, skip rows already present in `data/my_beers.csv`, and append only newly discovered check-ins
- `Clean Run` to ignore the existing CSV row count/backstop and fetch your full visible Untappd check-in history from scratch
- `Statistics` to generate and open local statistics HTML with a consumed-location heatmap
- `Open Export Folder` to open the CSV and generated report directory
- `Stop Running Task` to stop a scrape or map build and close the open statistics tab when possible

Check-in detail pulls show a `tqdm` tracker with completed/total rows, elapsed time, estimated time remaining, and processing rate.

## CLI Commands

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

Default behavior:

1. If `data/my_beers.csv` exists, the native app opens without downloading again.
2. `--update` forces a fresh scrape.
3. `Backstop Total` is the desired total CSV size. For example, if the CSV has 75 check-ins and the target is 150, the update pulls up to 75 additional check-ins, provided they exist on the site.
4. `--clean-run` ignores existing CSV data and loads check-ins until `Show More` is exhausted.
5. The existing CSV is overwritten only after the update succeeds.

## CSV Schema

The generated CSV is `data/my_beers.csv`.

| Column | Source |
| --- | --- |
| `Beer Name` | User check-in page |
| `Producer` | User check-in page |
| `Consumed Location` | User check-in page |
| `Lat` | Consumed-location venue page |
| `Long` | Consumed-location venue page |
| `Beer Type` | Beer page |
| `My Rating` | User check-in |
| `Global Rating` | Beer page |
| `Recent Date` | User check-in page |
| `Total Checkins` | Beer page |

`Consumed Location`, `Lat`, and `Long` come from the venue linked in each Untappd check-in. The heatmap and Top Consumed Locations statistics use these values and ignore `Untappd at Home` only for the map.

## Generated Files

- `data/my_beers.csv`: exported beer history
- `data/app_config.json`: local app settings
- `data/beer_details_cache.json`: persistent beer type, global rating, and check-in totals
- `data/venue_coordinates_cache.json`: persistent venue latitude and longitude
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

After code changes, run `briefcase update macOS` and `briefcase build macOS`, test the direct app bundle, and then package a fresh DMG.

## Build The Windows Installer

Windows packaging uses PyInstaller plus Inno Setup and should be run on Windows.

Requirements:

- Python 3.12+
- Inno Setup 6
- Google Chrome

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\packaging\windows\build-installer.ps1
```

The script uses the default Python selected by the Windows `py` launcher. Select a specific supported version with `-PythonVersion "-3.14"`.

The PyInstaller app appears in:

- `dist\UntappdBeerHistory\UntappdBeerHistory.exe`

The Inno Setup installer appears in:

- `dist\installer\Untappd-Beer-History-Setup-0.2.1.exe`

See `packaging/windows/README.md` for build options.

The installed Windows app writes user data to `%LOCALAPPDATA%\Untappd Beer History`.

## Raspberry Pi 5

A headless Pi is best used as the scraper and report host rather than as the native GUI machine.

```bash
sudo apt update
sudo apt install -y python3-venv chromium-browser chromium-driver
git clone <your-repo-url> ~/apps/Untappd-Beer-History-App
cd ~/apps/Untappd-Beer-History-App
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt
sudo mkdir -p /srv/untappd-beer-history/data
```

Run a full scrape with a persistent data directory:

```bash
UNTAPPD_DATA_DIR=/srv/untappd-beer-history/data \
python3 src/run.py --username YOUR_UNTAPPD_USERNAME --clean-run --no-ui
```

The initial login or a Cloudflare/CAPTCHA challenge requires an interactive Chromium session through a monitor, VNC, X forwarding, or remote debugging.

Example systemd service:

```ini
[Unit]
Description=Untappd Beer History refresh

[Service]
Type=oneshot
WorkingDirectory=/home/pi/apps/Untappd-Beer-History-App
Environment=UNTAPPD_DATA_DIR=/srv/untappd-beer-history/data
ExecStart=/home/pi/apps/Untappd-Beer-History-App/.venv/bin/python src/run.py --username YOUR_UNTAPPD_USERNAME --update --no-ui
```

Example daily timer:

```ini
[Unit]
Description=Run Untappd Beer History refresh daily

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

Serve the generated report over your LAN:

```bash
cd /srv/untappd-beer-history/data
python3 -m http.server 8088
```

Then open `http://pi5server:8088/beer_statistics.html`.

## Notes

- Beer details and venue coordinates are cached in JSON across runs, reducing repeat page loads and request volume.
- The bundled app displays a version/build stamp to help identify stale installations.

## License

This project is licensed under the MIT License. See `LICENSE`.

Untappd Beer History is an independent project and is not affiliated with or
endorsed by Untappd. Users are responsible for complying with applicable
terms, laws, privacy obligations, and account permissions.

## Troubleshooting

To capture a page for parser debugging, open the browser Developer Tools console and run:

```javascript
copy(document.documentElement.outerHTML)
```
