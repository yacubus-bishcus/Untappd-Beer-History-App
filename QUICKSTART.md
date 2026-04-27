# Quick Start

Supported Python versions: `3.9+`

```bash
cd /Users/jacobbickus/Python_Files/apps/untapped_data
source .venv/bin/activate
python3 run.py
```

Default behavior:

- If `my_beers.csv` already exists, opens Streamlit immediately
- Use `python3 run.py --update` to force a fresh Untappd download
- Otherwise opens Chrome at `https://untappd.com/user/<configured-username>/beers`
- Attaches Selenium at `127.0.0.1:9222`
- Exports to `my_beers.csv`
- Uses `--backstop-total` if you pass one during a refresh
- Opens Streamlit after the export finishes

Desktop bundle behavior:

- On macOS, open `Untappd Beer History.app`
- On Windows, open `Windows/start_desktop_app.bat`
- On first launch, the app asks for the Untappd username and saves it to `app_config.json`
- If no `my_beers.csv` exists yet, the launcher automatically starts the first sync
- Local source launchers now live in `deploy/mac` and `deploy/windows`

Useful commands:

```bash
python3 run.py
python3 run.py --update
python3 run.py selenium-launch-chrome
python3 run.py selenium-fetch-beers
python3 run.py selenium-fetch-beers --backstop-total 250
python3 run.py streamlit
```
