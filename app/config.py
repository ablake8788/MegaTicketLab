import configparser
from pathlib import Path

# Project root is two levels up from this file (app/config.py -> project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INI_PATH = PROJECT_ROOT / "config.ini"


def _load_ini() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    if INI_PATH.exists():
        parser.read(INI_PATH)
    return parser


_ini = _load_ini()


class Config:
    JSON_SORT_KEYS = False

    # --- [data] ---
    _data_folder = _ini.get("data", "folder", fallback="data")
    _data_filename = _ini.get(
        "data", "filename", fallback="Mega_Millions_3_Year_Advanced_Pattern_Analysis.xlsx"
    )

    _folder_path = Path(_data_folder)
    DATA_FOLDER = _folder_path if _folder_path.is_absolute() else (PROJECT_ROOT / _folder_path)
    DATA_FILENAME = _data_filename
    DATA_PATH = DATA_FOLDER / DATA_FILENAME

    HOT_COUNT = _ini.getint("data", "hot_count", fallback=12)
    OVERDUE_COUNT = _ini.getint("data", "overdue_count", fallback=12)
    PAIR_COUNT = _ini.getint("data", "pair_count", fallback=10)

    # --- [app] ---
    HOST = _ini.get("app", "host", fallback="127.0.0.1")
    PORT = _ini.getint("app", "port", fallback=5000)
    DEBUG = _ini.getboolean("app", "debug", fallback=False)
