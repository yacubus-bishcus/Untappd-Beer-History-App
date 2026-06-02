# Quick Start

Source workflow Python: `3.9+`
Briefcase packaging Python: `3.12+`

```bash
cd /Users/jacobbickus/Python_Files/apps/Untappd-Beer-History-App
source .venv/bin/activate
python3 src/run.py
```

Default behavior:

- If `data/my_beers.csv` exists, the native app opens so you can view statistics or refresh data
- Use `python3 src/run.py --update` to force a fresh Untappd download
- Use `python3 src/run.py --clean-run` to ignore the existing CSV row count/backstop and fetch all visible beer history from scratch
- The export writes `data/my_beers.csv`
- The `Statistics` button generates local HTML and opens it in your browser

Useful commands:

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

Generated files:

- `data/my_beers.csv`
- `data/producer_location_cache.json`
- `data/consumed_location_cache.json`
- `data/beer_statistics.html`
- `data/beer_map_fragment.js`

Briefcase packaging:

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

Best install path for non-developers:

- Download the DMG from `GitHub Releases`
- Use `Download ZIP` only if you want the source code
