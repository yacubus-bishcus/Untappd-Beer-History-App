import os
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parent
IS_BUNDLED_APP = SRC_DIR.name == "app" and SRC_DIR.parent.name == "Resources"
PROJECT_ROOT = SRC_DIR if IS_BUNDLED_APP else SRC_DIR.parent
BUNDLED_PYTHON_PATH = (
    SRC_DIR.parent.parent / "Frameworks" / "Python.framework" / "Python"
    if IS_BUNDLED_APP
    else None
)
DATA_DIR = Path(os.environ.get("UNTAPPD_DATA_DIR", str(PROJECT_ROOT / "data"))).expanduser()
DEPLOY_DIR = PROJECT_ROOT / "deploy"
DEFAULT_OUTPUT_PATH = DATA_DIR / "my_beers.csv"
APP_CONFIG_PATH = DATA_DIR / "app_config.json"
BEER_DETAILS_CACHE_PATH = DATA_DIR / "beer_details_cache.json"
VENUE_COORDINATES_CACHE_PATH = DATA_DIR / "venue_coordinates_cache.json"


def ensure_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR
