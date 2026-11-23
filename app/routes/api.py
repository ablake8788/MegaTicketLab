from pathlib import Path

from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename
from app.config import Config
from app.services.ticket_service import TicketService
from app.services.historical_data import HistoricalDataLoader
from app.services.history_search import HistorySearch
from app.services.hot_games import HotNumberGames
from app.services import ai_suggest
from app.models.ticket import Ticket

api_bp = Blueprint("api", __name__, url_prefix="/api")
service = TicketService(Config.GAME)
searcher = HistorySearch(Config.GAME)
hot_games = HotNumberGames(Config.GAME)


def _data_status(data: dict) -> dict:
    """What the "Upload data" section shows: which file/sheet is loaded."""
    return {
        "game": Config.GAME.key,
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
        "builtin_file": Config.DATA_PATH.name,
    }


@api_bp.get("/game")
def game():
    return jsonify({**Config.GAME.to_dict(), **_data_status(HistoricalDataLoader.load())})


@api_bp.get("/data")
def data_status():
    return jsonify(_data_status(HistoricalDataLoader.load()))


@api_bp.post("/data/upload")
def data_upload():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "Choose a file to upload."}), 400
    name = Path(file.filename).name
    ext = Path(name).suffix.lower()
    if ext not in Config.UPLOAD_EXTENSIONS:
        return jsonify({"error": f"Unsupported file type '{ext or name}'. Use .xlsx, .xlsm or .csv."}), 400

    Config.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    saved = Config.UPLOAD_FOLDER / f"{Config.GAME.key}_{secure_filename(name) or 'upload' + ext}"
    file.save(saved)
    data = HistoricalDataLoader.use_file(saved, name, request.form.get("sheet") or None)
    return jsonify(_data_status(data))


@api_bp.post("/data/sheet")
def data_sheet():
    sheet = (request.get_json(silent=True) or {}).get("sheet")
    if not sheet:
        return jsonify({"error": "No sheet given."}), 400
    return jsonify(_data_status(HistoricalDataLoader.use_sheet(sheet)))


@api_bp.post("/data/reset")
def data_reset():
    return jsonify(_data_status(HistoricalDataLoader.reset()))


@api_bp.get("/draws")
def draws():
    data = HistoricalDataLoader.load()
    return jsonify({"game": Config.GAME.key, "source": data["source"], "draws": data["draw_history"]})


@api_bp.get("/tickets")
def tickets():
    try:
        count = request.args.get("count", 5, type=int)
        strategy = request.args.get("strategy", "random")
        generated = service.generate_tickets(count, strategy)
        return jsonify({"strategy": strategy, "count": len(generated), "tickets": [t.to_dict() for t in generated]})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@api_bp.get("/search")
def search():
    """Keep generating until `count` tickets each match a past drawing with at
    least `min_white` white balls (+ the bonus ball when bonus=1)."""
    try:
        count = request.args.get("count", 5, type=int)
        strategy = request.args.get("strategy", "random")
        min_white = request.args.get("min_white", 4, type=int)
        need_bonus = request.args.get("bonus", "0") in ("1", "true", "yes")
        result = searcher.search(count, strategy, min_white, need_bonus)
        return jsonify({"strategy": strategy, **result})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@api_bp.get("/hot-games")
def hot_number_games():
    """Tickets built only from the most-drawn numbers (see services/hot_games.py)."""
    try:
        result = hot_games.generate(
            games=request.args.get("games", 5, type=int),
            white_pool=request.args.get("white_pool", 10, type=int),
            bonus_pool=request.args.get("bonus_pool", 5, type=int),
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@api_bp.get("/suggest")
def suggestion():
    """Suggested games from the draw history: Claude when ANTHROPIC_API_KEY is
    set (and ai=1), otherwise the built-in analysis."""
    try:
        games = request.args.get("games", 5, type=int)
        use_ai = request.args.get("ai", "1") in ("1", "true", "yes")
        return jsonify(ai_suggest.suggest(games, use_ai))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@api_bp.get("/ai-status")
def ai_status():
    return jsonify(ai_suggest.ai_status())


@api_bp.post("/compare")
def compare():
    try:
        data = request.get_json(force=True)
        generated = [Ticket(tuple(t["white_numbers"]), int(t["mega_ball"])) for t in data.get("tickets", [])]
        result = service.compare(generated, [int(x) for x in data["winning_white"]], int(data["winning_mega"]))
        return jsonify({"results": result})
    except (ValueError, KeyError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
