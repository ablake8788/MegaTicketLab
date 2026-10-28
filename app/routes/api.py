from flask import Blueprint, jsonify, request
from app.services.ticket_service import TicketService
from app.models.ticket import Ticket

api_bp = Blueprint("api", __name__, url_prefix="/api")
service = TicketService()

@api_bp.get("/tickets")
def tickets():
    try:
        count = request.args.get("count", 5, type=int)
        strategy = request.args.get("strategy", "random")
        generated = service.generate_tickets(count, strategy)
        return jsonify({"strategy": strategy, "count": len(generated), "tickets": [t.to_dict() for t in generated]})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

@api_bp.post("/compare")
def compare():
    try:
        data = request.get_json(force=True)
        generated = [Ticket(tuple(t["white_numbers"]), int(t["mega_ball"])) for t in data.get("tickets", [])]
        result = service.compare(generated, [int(x) for x in data["winning_white"]], int(data["winning_mega"]))
        return jsonify({"results": result})
    except (ValueError, KeyError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
