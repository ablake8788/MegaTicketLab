import configparser
import tempfile
from pathlib import Path

from app.games import GAMES, get_game

# Project root is two levels up from this file (app/config.py -> project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INI_PATH = PROJECT_ROOT / "config.ini"


def _load_ini() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    if INI_PATH.exists():
        parser.read(INI_PATH)
    return parser


_ini = _load_ini()

_folder = Path(_ini.get("data", "folder", fallback="data"))
_DATA_FOLDER = _folder if _folder.is_absolute() else (PROJECT_ROOT / _folder)


def _data_paths(folder: Path) -> dict:
    """game key -> its draw-history file from config.ini [data]."""
    return {
        key: folder / (
            _ini.get("data", f"{key}_filename", fallback=None)
            # the old single "filename" key still works for Mega Millions
            or (_ini.get("data", "filename", fallback=None) if key == "mega_millions" else None)
            or g.default_filename
        )
        for key, g in GAMES.items()
    }


class Config:
    JSON_SORT_KEYS = False

    # --- [game] ---  default game when the page or an API call names none
    GAME = get_game(_ini.get("game", "name", fallback="mega_millions"))

    # --- [data] ---  each game has its own draw-history file
    DATA_FOLDER = _DATA_FOLDER
    DATA_PATHS = _data_paths(_DATA_FOLDER)
    DATA_PATH = DATA_PATHS[GAME.key]          # default game's file
    DATA_FILENAME = DATA_PATH.name

    @classmethod
    def data_path(cls, game=None) -> Path:
        return cls.DATA_PATHS[(game or cls.GAME).key]

    YEARS = _ini.getint("data", "years", fallback=0)
    HOT_COUNT = _ini.getint("data", "hot_count", fallback=12)
    OVERDUE_COUNT = _ini.getint("data", "overdue_count", fallback=12)
    PAIR_COUNT = _ini.getint("data", "pair_count", fallback=10)

    # Files uploaded in the browser are saved here (outside the project, so the
    # .exe build works too). Uploads last until Reset or an app restart.
    UPLOAD_FOLDER = Path(tempfile.gettempdir()) / "MegaTicketLab" / "uploads"
    UPLOAD_EXTENSIONS = (".xlsx", ".xlsm", ".csv")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB upload limit (Flask setting)

    # --- [ai] ---  (Claude suggestions; the API key comes from the
    # ANTHROPIC_API_KEY environment variable, never from this file)
    AI_ENABLED = _ini.getboolean("ai", "enabled", fallback=True)
    AI_MODEL = _ini.get("ai", "model", fallback="claude-sonnet-5-5")
    AI_TIMEOUT = _ini.getint("ai", "timeout", fallback=45)

    # --- [app] ---
    HOST = _ini.get("app", "host", fallback="127.0.0.1")
    PORT = _ini.getint("app", "port", fallback=5000)
    DEBUG = _ini.getboolean("app", "debug", fallback=False)
