import sys
from pathlib import Path
from flask import Flask
from .config import Config
from .routes.web import web_bp
from .routes.api import api_bp


def _resource_root() -> Path:
    # When bundled by PyInstaller, files are unpacked to sys._MEIPASS at runtime.
    # Otherwise, use this file's directory as normal.
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "app"
    return Path(__file__).resolve().parent


def create_app(config_class=Config):
    root = _resource_root()
    app = Flask(
        __name__,
        template_folder=str(root / "templates"),
        static_folder=str(root / "static"),
    )
    app.config.from_object(config_class)
    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp)
    return app
