"""JSON API. Every endpoint works for either game: pass ?game=mega_millions or
?game=powerball (the page always does). With no game, config.ini's
[game] name is used."""
from pathlib import Path

from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename

from app.config import Config
from app.games import GAMES, get_game
from app.models.ticket import Ticket
from app.services import ai_suggest
from app.services.historical_data import HistoricalDataLoader
from app.services.history_search import HistorySearch
from app.services.hot_games import HotNumberGames
from app.services.ticket_service import TicketService

api_bp = Blueprint("api", __name__, url_prefix="/api")


class GameError(ValueError):
    pass


def _game():
    """The game this request is for: ?game=..., then a 'game' form/JSON field,
    then the config.ini default."""
    name = request.args.get("game") or request.form.get("game")
    if not name and request.is_json:
        name = (request.get_json(silent=True) or {}).get("game")
    if not name:
        return Config.GAME
    try:
        return get_game(name)
    except ValueError:
        raise GameError(f"Unknown game '{name}'. Choose one of: {', '.join(GAMES)}.")


@api_bp.errorhandler(GameError)
def _bad_game(exc):
    return jsonify({"error": str(exc)}), 400


def _data_status(data: dict, game) -> dict:
    """What the "Upload data" section shows: which file/sheet is loaded."""
    return {
        "game": game.key,
        "source": data["source"],
        "file_name": data.get("file_name"),
        "data_file": data.get("data_file"),
        "uploaded": data.get("uploaded", False),
        "sheet": data.get("sheet"),
        "sheets": data.get("sheets", []),
        "draws_loaded": len(data["draw_history"]),
        "skipped_rows": data.get("skipped_rows", 0),
        "stats_from": data.get("stats_from"),
        "reason": data.get("reason"),
        "builtin_file": Config.data_path(game).name,
    }


@api_bp.get("/games")
def games():
    return jsonify({"default": Config.GAME.key, "games": [g.to_dict() for g in GAMES.values()]})


@api_bp.get("/game")
def game():
    g = _game()
    return jsonify({**g.to_dict(), **_data_status(HistoricalDataLoader.load(g), g)})


@api_bp.get("/data")
def data_status():
    g = _game()
    return jsonify(_data_status(HistoricalDataLoader.load(g), g))


@api_bp.post("/data/upload")
def data_upload():
    g = _game()
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "Choose a file to upload."}), 400
    name = Path(file.filename).name
    ext = Path(name).suffix.lower()
    if ext not in Config.UPLOAD_EXTENSIONS:
        return jsonify({"error": f"Unsupported file type '{ext or name}'. Use .xlsx, .xlsm or .csv."}), 400

    Config.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    saved = Config.UPLOAD_FOLDER / f"{g.key}_{secure_filename(name) or 'upload' + ext}"
    file.save(saved)
    data = HistoricalDataLoader.use_file(saved, name, request.form.get("sheet") or None, game=g)
    return jsonify(_data_status(data, g))


@api_bp.post("/data/sheet")
def data_sheet():
    g = _game()
    sheet = (request.get_json(silent=True) or {}).get("sheet")
    if not sheet:
        return jsonify({"error": "No sheet given."}), 400
    return jsonify(_data_status(HistoricalDataLoader.use_sheet(sheet, g), g))


@api_bp.post("/data/reset")
def data_reset():
    g = _game()
    return jsonify(_data_status(HistoricalDataLoader.reset(g), g))


@api_bp.get("/draws")
def draws():
    g = _game()
    data = HistoricalDataLoader.load(g)
    return jsonify({"game": g.key, "source": data["source"], "draws": data["draw_history"]})


@api_bp.get("/tickets")
def tickets():
    g = _game()
    try:
        count = request.args.get("count", 5, type=int)
        strategy = request.args.get("strategy", "random")
        generated = TicketService(g).generate_tickets(count, strategy)
        return jsonify({"game": g.key, "strategy": strategy, "count": len(generated),
                        "tickets": [t.to_dict() for t in generated]})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@api_bp.get("/search")
def search():
    """Keep generating until `count` tickets each match a past drawing with at
    least `min_white` white balls (+ the bonus ball when bonus=1)."""
    g = _game()
    try:
        count = request.args.get("count", 5, type=int)
        strategy = request.args.get("strategy", "random")
        min_white = request.args.get("min_white", 4, type=int)
        need_bonus = request.args.get("bonus", "0") in ("1", "true", "yes")
        result = HistorySearch(g).search(count, strategy, min_white, need_bonus)
        return jsonify({"game": g.key, "strategy": strategy, **result})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@api_bp.get("/hot-games")
def hot_number_games():
    """Tickets built only from the most-drawn numbers (see services/hot_games.py)."""
    g = _game()
    try:
        result = HotNumberGames(g).generate(
            games=request.args.get("games", 5, type=int),
            white_pool=request.args.get("white_pool", 10, type=int),
            bonus_pool=request.args.get("bonus_pool", 5, type=int),
        )
        return jsonify({"game": g.key, **result})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@api_bp.get("/suggest")
def suggestion():
    """Suggested games from the draw history: Claude when ANTHROPIC_API_KEY is
    set (and ai=1), otherwise the built-in analysis."""
    g = _game()
    try:
        games_n = request.args.get("games", 5, type=int)
        use_ai = request.args.get("ai", "1") in ("1", "true", "yes")
        return jsonify({"game": g.key, **ai_suggest.suggest(games_n, use_ai, g)})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@api_bp.get("/ai-status")
def ai_status():
    return jsonify(ai_suggest.ai_status())


@api_bp.post("/compare")
def compare():
    g = _game()
    try:
        data = request.get_json(force=True)
        generated = [Ticket(tuple(t["white_numbers"]), int(t["mega_ball"])) for t in data.get("tickets", [])]
        result = TicketService(g).compare(generated, [int(x) for x in data["winning_white"]],
                                          int(data["winning_mega"]))
        return jsonify({"game": g.key, "results": result})
    except (ValueError, KeyError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
