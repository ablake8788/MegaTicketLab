import sys
from pathlib import Path
from flask import Flask, jsonify
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

    @app.errorhandler(413)
    def too_large(_exc):
        limit = app.config.get("MAX_CONTENT_LENGTH", 0) // (1024 * 1024)
        return jsonify({"error": f"File is too large (limit {limit} MB)."}), 413

    return app
