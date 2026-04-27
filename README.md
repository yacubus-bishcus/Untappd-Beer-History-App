# Untappd Beer History Exporter

This project exports your Untappd beer history with Selenium, saves it to `my_beers.csv`, and opens a Streamlit dashboard for reviewing the results.

Supported Python versions: `3.9` and `3.10`

## What `python run.py` Does

Running `python run.py` from `apps/untapped_data` will:

1. If `my_beers.csv` already exists, skip Untappd and open the Streamlit dashboard immediately.
2. If you pass `--update`, launch Chrome with remote debugging enabled.
3. Open `https://untappd.com/user/jb2019/beers`.
4. Wait for you to finish logging in manually if needed.
5. Click `Show More` until all beers are loaded.
6. Save the export to `my_beers.csv`.
7. Use the existing row count in `my_beers.csv` as the default backstop total if that file already exists.
8. Open the Streamlit dashboard.

Defaults:

- Username: `jb2019`
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
- If `my_beers.csv` already exists, its current row count becomes the default backstop total unless you pass `--backstop-total`.
- `python3 run.py` opens Streamlit immediately when `my_beers.csv` already exists. Pass `--update` to refresh from Untappd first.
- The Streamlit app reads `my_beers.csv` by default.
- Streamlit builds a global country map directly from the `Location` values in `my_beers.csv`.

## File Structure

```text
untapped_data/
├── run.py
├── streamlit_app.py
├── untapped.py
├── untapped_selenium.py
├── requirements.txt
└── my_beers.csv
```
