import pytest

from app.config import Config
from app.games import GAMES
from app.services.historical_data import HistoricalDataLoader
from app.services.ticket_service import TicketService


@pytest.fixture(autouse=True)
def _reset_loader():
    yield
    HistoricalDataLoader._cache = None


def use_game(monkeypatch, key, path):
    monkeypatch.setattr(Config, "GAME", GAMES[key])
    monkeypatch.setattr(Config, "DATA_PATH", path)
    HistoricalDataLoader._cache = None


@pytest.mark.parametrize("key", ["mega_millions", "powerball"])
@pytest.mark.parametrize("strategy", ["random", "model", "v2"])
def test_generation_respects_game_ranges(monkeypatch, tmp_path, key, strategy):
    use_game(monkeypatch, key, tmp_path / "missing.xlsx")  # forces the fallback path
    g = GAMES[key]
    tickets = TicketService(g).generate_tickets(40, strategy)
    assert len(tickets) == 40
    for t in tickets:
        assert len(set(t.white_numbers)) == g.white_count
        assert all(1 <= n <= g.white_max for n in t.white_numbers)
        assert 1 <= t.mega_ball <= g.bonus_max


def test_compare_mega_millions():
    svc = TicketService(GAMES["mega_millions"])
    results = svc.compare(svc.generate_tickets(2, "random"), [1, 20, 30, 46, 68], 17)
    assert len(results) == 2 and all("white_matches" in r for r in results)
    with pytest.raises(ValueError):
        svc.compare([], [1, 2, 3, 4, 70 + 1], 5)
    with pytest.raises(ValueError):
        svc.compare([], [1, 2, 3, 4, 5], 25)        # Mega Ball 25 is retired


def test_compare_powerball_bounds():
    svc = TicketService(GAMES["powerball"])
    svc.compare([], [1, 2, 3, 4, 69], 26)           # valid extremes
    with pytest.raises(ValueError):
        svc.compare([], [1, 2, 3, 4, 70], 5)        # 70 is not a Powerball white ball
    with pytest.raises(ValueError):
        svc.compare([], [1, 2, 3, 4, 5], 27)


def test_powerball_csv_all_layouts(monkeypatch, tmp_path):
    f = tmp_path / "pb.csv"
    f.write_text(
        "Draw Date,Winning Numbers,Multiplier\n"
        "10/26/2026,18 26 49 50 54 01,3\n"          # one cell, zero-padded bonus
        "2026-10-24,4,5,15,19,55,19,2\n"            # separate columns + Power Play
        "10/21/2026,21 50 44 57 01 05,2\n"          # 1 appears twice as number -> ok (white 1)
        "10/19/2026,31 42 8 32 48 27,4\n"           # bonus 27 invalid for Powerball -> skipped
        "10/17/2026,13 35 32 24 70 11,3\n"          # white 70 invalid -> skipped
    )
    use_game(monkeypatch, "powerball", f)
    data = HistoricalDataLoader.load()
    assert data["source"] == "workbook" and data["stats_from"] == "draw history"
    assert [d["date"] for d in data["draw_history"]] == ["2026-10-26", "2026-10-24", "2026-10-21"]
    assert data["draw_history"][0] == {"date": "2026-10-26", "white_numbers": [18, 26, 49, 50, 54], "mega_ball": 1}
    assert data["skipped_rows"] == 2
    assert set(data["mega_weights"]) == set(range(1, 27))


def test_powerball_xlsx_and_year_window(monkeypatch, tmp_path):
    from openpyxl import Workbook
    from datetime import datetime
    wb = Workbook(); ws = wb.active; ws.title = "Draw History"
    ws.append(["Draw Date", "Ball 1", "Ball 2", "Ball 3", "Ball 4", "Ball 5", "Powerball"])
    ws.append([datetime(2026, 10, 26), 18, 26, 49, 50, 54, 1])
    ws.append([datetime(2026, 1, 5), 18, 26, 40, 41, 42, 1])
    ws.append([datetime(2020, 1, 1), 5, 6, 7, 8, 9, 2])          # outside the 3-year window
    f = tmp_path / "pb.xlsx"; wb.save(f)
    use_game(monkeypatch, "powerball", f)
    monkeypatch.setattr(Config, "YEARS", 3)
    data = HistoricalDataLoader.load()
    assert len(data["draw_history"]) == 3            # history keeps everything
    assert data["top_pairs"][0] == (18, 26)          # seen together twice in the window
    assert 5 not in data["hot_numbers"]              # 2020 draw excluded from stats
    assert data["overdue_numbers"][0] not in (18, 26)


def test_mega_ball_25_is_never_generated(monkeypatch, tmp_path):
    use_game(monkeypatch, "mega_millions", tmp_path / "missing.xlsx")
    monkeypatch.setattr(HistoricalDataLoader, "_cache",
                        {"hot_numbers": [1], "overdue_numbers": [2], "top_pairs": [(1, 2)],
                         "mega_weights": {24: 1, 25: 10_000}, "draw_history": [], "source": "workbook"})
    tickets = TicketService(GAMES["mega_millions"]).generate_tickets(100, "model")
    assert all(t.mega_ball <= 24 for t in tickets)


def test_missing_file_falls_back(monkeypatch, tmp_path):
    use_game(monkeypatch, "powerball", tmp_path / "nope.xlsx")
    data = HistoricalDataLoader.load()
    assert data["source"] == "fallback" and "not found" in data["reason"]


# ---------------------------------------------------------------- upload section
def _client(monkeypatch, tmp_path, key="powerball"):
    from app import create_app
    import app.routes.api as api
    use_game(monkeypatch, key, tmp_path / "builtin_missing.xlsx")
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", tmp_path / "uploads")
    monkeypatch.setattr(api.service, "game", GAMES[key])
    monkeypatch.setattr(HistoricalDataLoader, "_override", None)
    return create_app().test_client()


def _pb_workbook(path):
    from openpyxl import Workbook
    from datetime import datetime
    wb = Workbook(); ws = wb.active; ws.title = "Notes"
    ws.append(["just notes"])
    ws = wb.create_sheet("download")
    ws.append(["Draw Date", "Ball 1", "Ball 2", "Ball 3", "Ball 4", "Ball 5", "Powerball"])
    ws.append([datetime(2026, 10, 26), 18, 26, 49, 50, 54, 1])
    ws.append([datetime(2026, 10, 24), 4, 5, 15, 19, 55, 19])
    wb.save(path)


def test_upload_sheet_switch_and_reset(monkeypatch, tmp_path):
    import io
    c = _client(monkeypatch, tmp_path)
    f = tmp_path / "Dayton NJ.xlsx"; _pb_workbook(f)

    r = c.post("/api/data/upload", data={"file": (io.BytesIO(f.read_bytes()), "Dayton NJ.xlsx")},
               content_type="multipart/form-data")
    s = r.get_json()
    assert r.status_code == 200 and s["uploaded"] and s["file_name"] == "Dayton NJ.xlsx"
    assert s["sheets"] == ["Notes", "download"]
    assert s["sheet"] == "Notes" and s["source"] == "fallback"      # first sheet has no draws

    s = c.post("/api/data/sheet", json={"sheet": "download"}).get_json()
    assert s["source"] == "workbook" and s["draws_loaded"] == 2 and s["sheet"] == "download"
    assert len(c.get("/api/draws").get_json()["draws"]) == 2
    assert c.get("/api/tickets?count=5&strategy=v2").status_code == 200

    s = c.post("/api/data/reset").get_json()
    assert not s["uploaded"] and s["source"] == "fallback" and "not found" in s["reason"]


def test_upload_rejects_bad_type_and_wrong_game(monkeypatch, tmp_path):
    import io
    c = _client(monkeypatch, tmp_path)
    r = c.post("/api/data/upload", data={"file": (io.BytesIO(b"x"), "notes.txt")}, content_type="multipart/form-data")
    assert r.status_code == 400 and "Unsupported" in r.get_json()["error"]

    mm_csv = b"Draw Date,Ball 1,Ball 2,Ball 3,Ball 4,Ball 5,Mega Ball\n10/27/2026,14,19,21,45,67,3\n"
    s = c.post("/api/data/upload", data={"file": (io.BytesIO(mm_csv), "mm.csv")},
               content_type="multipart/form-data").get_json()
    assert s["source"] == "fallback" and "Mega Millions file" in s["reason"]


# ------------------------------------------------------------- search mode
def test_matcher_finds_best_prize_level():
    from app.models.ticket import Ticket
    from app.services.history_search import HistoryMatcher
    draws = [
        {"date": "2026-10-26", "white_numbers": [1, 2, 3, 4, 50], "mega_ball": 9},
        {"date": "2026-10-24", "white_numbers": [1, 2, 3, 4, 5], "mega_ball": 7},
    ]
    m = HistoryMatcher(draws)
    assert m.best_match(Ticket((1, 2, 3, 4, 5), 9))[:2] == (5, False)    # 5 white beats 4 white + bonus
    assert m.best_match(Ticket((1, 2, 3, 4, 60), 9))[:2] == (4, True)    # prefers the draw with the bonus
    assert m.best_match(Ticket((1, 2, 3, 4, 60), 9))[2]["date"] == "2026-10-26"
    assert m.best_match(Ticket((10, 20, 30, 40, 60), 9))[:2] == (0, False)


@pytest.mark.parametrize("strategy", ["random", "model", "v2"])
def test_search_returns_only_tickets_meeting_target(monkeypatch, tmp_path, strategy):
    import secrets
    from app.services.history_search import HistorySearch
    use_game(monkeypatch, "powerball", tmp_path / "missing.xlsx")
    rng = secrets.SystemRandom()
    draws = [{"date": f"2026-01-{i:02d}", "white_numbers": sorted(rng.sample(range(1, 70), 5)),
              "mega_ball": rng.randint(1, 26)} for i in range(1, 29)] * 10
    monkeypatch.setattr(HistoricalDataLoader, "_cache",
                        {"hot_numbers": draws[0]["white_numbers"], "overdue_numbers": draws[1]["white_numbers"],
                         "top_pairs": [tuple(draws[0]["white_numbers"][:2])],
                         "mega_weights": {}, "draw_history": draws, "source": "workbook"})
    result = HistorySearch(GAMES["powerball"]).search(3, strategy, 3, False)
    assert result["complete"] and len(result["tickets"]) == 3
    for t in result["tickets"]:
        overlap = set(t["white_numbers"]) & set(t["matched_draw"]["white_numbers"])
        assert len(overlap) == t["white_matches"] >= 3


def test_search_needs_history(monkeypatch, tmp_path):
    from app.services.history_search import HistorySearch
    use_game(monkeypatch, "powerball", tmp_path / "missing.xlsx")
    with pytest.raises(ValueError, match="No historical draws"):
        HistorySearch(GAMES["powerball"]).search(1, "random", 4, True)


# ------------------------------------------------------------- hot-number games
@pytest.mark.parametrize("games,white_pool,bonus_pool", [(5, 10, 5), (3, 10, 5), (8, 12, 4), (1, 5, 1)])
def test_hot_games_follow_the_rules(monkeypatch, tmp_path, games, white_pool, bonus_pool):
    from collections import Counter
    from app.services.hot_games import HotNumberGames
    f = tmp_path / "pb.xlsx"; _pb_workbook(f)
    use_game(monkeypatch, "powerball", tmp_path / "missing.xlsx")
    import secrets
    rng = secrets.SystemRandom()
    draws = [{"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "white_numbers": sorted(rng.sample(range(1, 70), 5)),
              "mega_ball": rng.randint(1, 26)} for i in range(200)]
    draws.sort(key=lambda d: d["date"], reverse=True)
    monkeypatch.setattr(HistoricalDataLoader, "_cache", {"hot_numbers": [1], "overdue_numbers": [2], "top_pairs": [],
                                                         "mega_weights": {}, "draw_history": draws, "source": "workbook"})
    r = HotNumberGames(GAMES["powerball"]).generate(games, white_pool, bonus_pool)
    hot_w = [h["number"] for h in r["hot_white"]]
    hot_b = [h["number"] for h in r["hot_bonus"]]
    counts = Counter(n for d in draws for n in d["white_numbers"])
    assert [counts[n] for n in hot_w] == sorted(counts.values(), reverse=True)[:white_pool]
    assert len(r["tickets"]) == games
    used = Counter()
    for t in r["tickets"]:
        assert len(set(t["white_numbers"])) == 5 and set(t["white_numbers"]) <= set(hot_w)
        assert t["mega_ball"] in hot_b
        used.update(t["white_numbers"])
    slots = 5 * games
    if white_pool <= slots:                                   # every hot number used, evenly
        assert set(used) == set(hot_w) and max(used.values()) - min(used.values()) <= 1
        assert [used[n] for n in hot_w] == sorted(used.values(), reverse=True)   # extras to the most-drawn
    bon = [t["mega_ball"] for t in r["tickets"]]
    assert len(set(bon)) == min(games, bonus_pool)


def test_hot_games_five_from_ten_share_exactly_two(monkeypatch, tmp_path):
    from itertools import combinations
    from app.services.hot_games import HotNumberGames
    use_game(monkeypatch, "powerball", tmp_path / "missing.xlsx")
    draws = [{"date": f"2026-01-{i:02d}", "white_numbers": [i, i + 10, i + 20, i + 30, i + 40], "mega_ball": i}
             for i in range(1, 25)]
    monkeypatch.setattr(HistoricalDataLoader, "_cache", {"hot_numbers": [1], "overdue_numbers": [2], "top_pairs": [],
                                                         "mega_weights": {}, "draw_history": draws, "source": "workbook"})
    for _ in range(5):
        r = HotNumberGames(GAMES["powerball"]).generate(5, 10, 5)
        shared = [len(set(a["white_numbers"]) & set(b["white_numbers"])) for a, b in combinations(r["tickets"], 2)]
        assert shared == [2] * 10


def test_hot_games_api_validates(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    assert c.get("/api/hot-games?games=0").status_code == 400
    assert c.get("/api/hot-games?white_pool=3").status_code == 400
    r = c.get("/api/hot-games")                    # built-in file missing in this test -> no history
    assert r.status_code == 400 and "No historical draws" in r.get_json()["error"]


# ------------------------------------------------------------- suggestions
def _history(monkeypatch, tmp_path, n=120):
    import secrets
    use_game(monkeypatch, "powerball", tmp_path / "missing.xlsx")
    rng = secrets.SystemRandom()
    draws = [{"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "white_numbers": sorted(rng.sample(range(1, 70), 5)),
              "mega_ball": rng.randint(1, 26)} for i in range(n)]
    draws.sort(key=lambda d: d["date"], reverse=True)
    monkeypatch.setattr(HistoricalDataLoader, "_cache", {"hot_numbers": [1], "overdue_numbers": [2], "top_pairs": [],
                                                         "mega_weights": {}, "draw_history": draws, "source": "workbook"})
    return draws


def _valid(t):
    w = t["white_numbers"]
    return len(set(w)) == 5 and all(1 <= x <= 69 for x in w) and 1 <= t["mega_ball"] <= 26


def test_builtin_suggestion(monkeypatch, tmp_path):
    from app.services import ai_suggest
    _history(monkeypatch, tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = ai_suggest.suggest(5)
    assert r["source"] == "builtin" and "ANTHROPIC_API_KEY" in r["note"]
    assert len(r["tickets"]) == 5 and all(_valid(t) for t in r["tickets"])
    assert len({tuple(t["white_numbers"]) for t in r["tickets"]}) == 5
    assert all("hot" in t["reason"] for t in r["tickets"])
    assert any("same odds" in s for s in r["summary"])


def test_claude_suggestion_is_validated(monkeypatch, tmp_path):
    import json
    from app.services import ai_suggest
    _history(monkeypatch, tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    reply = {"summary": ["History looks random.", "Same odds for every ticket."], "tickets": [
        {"white_numbers": [5, 12, 33, 41, 60], "bonus": 7, "reason": "mix <b>hot</b>"},
        {"white_numbers": [5, 5, 33, 41, 60], "bonus": 7, "reason": "duplicate ball"},     # invalid
        {"white_numbers": [1, 2, 3, 4, 99], "bonus": 7, "reason": "out of range"},          # invalid
        {"white_numbers": [8, 19, 27, 44, 52], "bonus": 30, "reason": "bad bonus"},         # invalid
        {"white_numbers": [8, 19, 27, 44, 52], "bonus": 3, "reason": "ok"}]}
    monkeypatch.setattr(ai_suggest, "_call_claude", lambda prompt: "Here you go:\n" + json.dumps(reply))
    r = ai_suggest.suggest(3)
    assert r["source"] == "claude"
    assert [t["white_numbers"] for t in r["tickets"]] == [[5, 12, 33, 41, 60], [8, 19, 27, 44, 52]]
    assert "2 valid ticket(s)" in r["note"]


def test_claude_failure_falls_back(monkeypatch, tmp_path):
    from app.services import ai_suggest
    _history(monkeypatch, tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def boom(prompt):
        raise RuntimeError("could not reach the Claude API")
    monkeypatch.setattr(ai_suggest, "_call_claude", boom)
    r = ai_suggest.suggest(4)
    assert r["source"] == "builtin" and len(r["tickets"]) == 4
    assert "unavailable" in r["note"]

    monkeypatch.setattr(ai_suggest, "_call_claude", lambda p: "sorry, no JSON")
    assert ai_suggest.suggest(2)["source"] == "builtin"


def test_suggest_api(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    assert c.get("/api/suggest?games=0").status_code == 400
    _history(monkeypatch, tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = c.get("/api/suggest?games=3&ai=0").get_json()
    assert r["source"] == "builtin" and len(r["tickets"]) == 3 and r["note"] is None
    assert c.get("/api/ai-status").get_json()["available"] is False
