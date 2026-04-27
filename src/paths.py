from pathlib import Path


SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
DEPLOY_DIR = PROJECT_ROOT / "deploy"
DOCUMENTATION_DIR = PROJECT_ROOT / "documentation"

DEFAULT_OUTPUT_PATH = DATA_DIR / "my_beers.csv"
APP_CONFIG_PATH = DATA_DIR / "app_config.json"
PRODUCER_LOCATION_CACHE_PATH = DATA_DIR / "producer_location_cache.json"


def ensure_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR
