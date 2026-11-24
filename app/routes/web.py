from flask import Blueprint, make_response, render_template, request

from app.config import Config
from app.games import GAMES

web_bp = Blueprint("web", __name__)


@web_bp.get("/")
def home():
    """One page for both games: ?game=powerball / ?game=mega_millions picks the
    game (the dropdown in the header sets it); the last choice is remembered."""
    key = request.args.get("game") or request.cookies.get("game") or Config.GAME.key
    game = GAMES.get(key, Config.GAME)
    resp = make_response(render_template(
        "index.html", game=game.to_dict(), games=[g.to_dict() for g in GAMES.values()]))
    resp.set_cookie("game", game.key, max_age=365 * 24 * 3600, samesite="Lax")
    return resp
