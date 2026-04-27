# Quick Start

Supported Python versions: `3.9+`

```bash
cd /Users/jacobbickus/Python_Files/apps/untapped_data
source .venv/bin/activate
python3 src/run.py
```

Default behavior:

- If `data/my_beers.csv` already exists, Streamlit opens immediately
- Use `python3 src/run.py --update` to force a fresh Untappd download
- Exports to `data/my_beers.csv`
- Opens Streamlit after the export finishes

Desktop launchers:

- macOS: `deploy/mac/Untappd Beer History.app`
- Windows: `deploy/windows/start_desktop_app.bat`
- First launch saves the Untappd username to `data/app_config.json`
- If macOS blocks the first launch, right-click the app and choose `Open`

Useful commands:

```bash
python3 src/run.py
python3 src/run.py --update
python3 src/run.py selenium-launch-chrome
python3 src/run.py selenium-fetch-beers
python3 src/run.py selenium-fetch-beers --backstop-total 250
python3 src/run.py streamlit
```
