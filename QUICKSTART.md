# Quick Start

Supported Python versions: `3.9` and `3.10`

```bash
cd /Users/jacobbickus/Python_Files/apps/untapped_data
source .venv/bin/activate
python3 run.py
```

Default behavior:

- If `my_beers.csv` already exists, opens Streamlit immediately
- Use `python3 run.py --update` to force a fresh Untappd download
- Otherwise opens Chrome at `https://untappd.com/user/jb2019/beers`
- Attaches Selenium at `127.0.0.1:9222`
- Exports to `my_beers.csv`
- Uses the current row count of `my_beers.csv` as the default backstop total if the file already exists
- Opens Streamlit after the export finishes

Useful commands:

```bash
python3 run.py
python3 run.py --update
python3 run.py selenium-launch-chrome
python3 run.py selenium-fetch-beers
python3 run.py selenium-fetch-beers --backstop-total 250
python3 run.py streamlit
```
