"""Suggestions based on the draw history, for the Most-Drawn Numbers section.

Two sources:
  * Built-in analysis (always available): works out hot, trending, overdue and
    cold numbers plus the typical shape of a winning ticket, then writes
    suggested games with the reason for every number.
  * Claude (optional): when an Anthropic API key is set (environment variable
    ANTHROPIC_API_KEY), the same statistics are sent to Claude, which returns
    its own suggested games and a short explanation. If the call fails, the
    built-in suggestion is shown with the reason.

Every suggestion is a way to choose numbers; none of them changes the odds of
a ticket. Both sources say so.
"""
import json
import os
import secrets
import statistics
import urllib.error
import urllib.request
from collections import Counter

from app.config import Config
from app.services.historical_data import HistoricalDataLoader

RECENT_DRAWS = 50          # "trending" window
MAX_GAMES = 10


# ======================================================================= stats
def history_stats(draws: list, game) -> dict:
    """Summary of the draw history (draws are newest first)."""
    n = len(draws)
    wmax, bmax, k = game.white_max, game.bonus_max, game.white_count
    w_all = Counter(x for d in draws for x in d["white_numbers"])
    b_all = Counter(d["mega_ball"] for d in draws if 1 <= d["mega_ball"] <= bmax)
    recent = draws[:RECENT_DRAWS]
    w_recent = Counter(x for d in recent for x in d["white_numbers"])

    def since(nums_of, rng):
        out = {}
        for num in rng:
            out[num] = next((i for i, d in enumerate(draws) if num in nums_of(d)), n)
        return out

    w_since = since(lambda d: d["white_numbers"], range(1, wmax + 1))
    b_since = since(lambda d: [d["mega_ball"]], range(1, bmax + 1))

    exp_w, exp_b = n * k / wmax, n / bmax
    exp_recent = len(recent) * k / wmax
    by_count = sorted(range(1, wmax + 1), key=lambda x: (-w_all[x], w_since[x], x))
    trending = sorted(range(1, wmax + 1), key=lambda x: (-(w_recent[x] - exp_recent), -w_all[x], x))
    overdue = sorted(range(1, wmax + 1), key=lambda x: (-w_since[x], x))
    b_hot = sorted(range(1, bmax + 1), key=lambda x: (-b_all[x], b_since[x], x))
    b_overdue = sorted(range(1, bmax + 1), key=lambda x: (-b_since[x], x))

    sums = sorted(sum(d["white_numbers"]) for d in draws)
    q = statistics.quantiles(sums, n=4) if len(sums) >= 4 else [min(sums), 0, max(sums)]
    odd_split = Counter(sum(x % 2 for x in d["white_numbers"]) for d in draws)
    low_split = Counter(sum(x <= wmax // 2 for x in d["white_numbers"]) for d in draws)

    return {
        "game": game.title,
        "bonus_name": game.bonus_name,
        "white_range": [1, wmax],
        "bonus_range": [1, bmax],
        "draws": n,
        "from_date": draws[-1]["date"],
        "to_date": draws[0]["date"],
        "expected_per_white": round(exp_w, 1),
        "expected_per_bonus": round(exp_b, 1),
        "hot_white": [{"number": x, "times": w_all[x]} for x in by_count[:10]],
        "cold_white": [{"number": x, "times": w_all[x]} for x in by_count[-5:][::-1]],
        "trending_white": [{"number": x, "last_50": w_recent[x], "expected_last_50": round(exp_recent, 1)}
                           for x in trending[:5]],
        "overdue_white": [{"number": x, "draws_since_seen": w_since[x]} for x in overdue[:5]],
        "hot_bonus": [{"number": x, "times": b_all[x]} for x in b_hot[:5]],
        "overdue_bonus": [{"number": x, "draws_since_seen": b_since[x]} for x in b_overdue[:3]],
        "typical_sum_range": [int(q[0]), int(q[2])],        # middle 50% of winning sums
        "odd_count_share": {str(c): round(v / n, 2) for c, v in sorted(odd_split.items())},
        "low_count_share": {str(c): round(v / n, 2) for c, v in sorted(low_split.items())},
        "last_draw": {"date": draws[0]["date"], "white_numbers": draws[0]["white_numbers"],
                      "bonus": draws[0]["mega_ball"]},
    }


# ================================================================== built-in
def builtin_suggestion(stats: dict, games: int, rng=None) -> dict:
    """Each game: 2 hot + 1 trending + 1 overdue + 1 wildcard, kept to the
    typical sum range and a 2/3 odd-even split; bonus balls from the hot list."""
    rng = rng or secrets.SystemRandom()
    wmax = stats["white_range"][1]
    hot = [h["number"] for h in stats["hot_white"]]
    trend = [h["number"] for h in stats["trending_white"]]
    due = [h["number"] for h in stats["overdue_white"]]
    bonus_pool = [h["number"] for h in stats["hot_bonus"]]
    lo, hi = stats["typical_sum_range"]

    tickets, seen, bonuses = [], set(), []
    uses = Counter()                     # spread numbers across the games

    def pick(cands, k, taken):
        """k numbers from cands, preferring the ones used least so far."""
        free = [x for x in cands if x not in taken]
        rng.shuffle(free)
        free.sort(key=lambda x: uses[x])
        return free[:k]

    for _ in range(games):
        if not bonuses:
            bonuses = list(bonus_pool)
            rng.shuffle(bonuses)
        for attempt in range(2000):
            taken = set()
            pick_hot = pick(hot, 2, taken) if attempt < 1000 else rng.sample(hot, 2)
            taken |= set(pick_hot)
            pick_trend = (pick(trend, 1, taken) or [None])[0]
            taken.add(pick_trend)
            pick_due = (pick(due, 1, taken) or [None])[0]
            taken.add(pick_due)
            pick_wild = rng.choice([x for x in range(1, wmax + 1)
                                    if x not in taken and x not in hot and uses[x] == 0]
                                   or [x for x in range(1, wmax + 1) if x not in taken])
            whites = [x for x in (*pick_hot, pick_trend, pick_due, pick_wild) if x is not None]
            while len(whites) < 5:                            # tiny pools: top up
                whites.append(rng.choice([x for x in range(1, wmax + 1) if x not in whites]))
            key = tuple(sorted(whites))
            odd = sum(x % 2 for x in whites)
            typical = lo <= sum(whites) <= hi and odd in (2, 3)
            if key not in seen and (typical or attempt > 1500):
                break
            if attempt % 50 == 49:              # reshuffle ties now and then
                rng.shuffle(hot)
        seen.add(key)
        uses.update(whites)
        b = bonuses.pop()
        parts = [f"hot {pick_hot[0]}, {pick_hot[1]}"]
        if pick_trend: parts.append(f"trending {pick_trend}")
        if pick_due: parts.append(f"overdue {pick_due}")
        parts.append(f"wildcard {pick_wild}")
        parts.append(f"{stats['bonus_name']} {b} (most drawn)")
        tickets.append({"white_numbers": list(key), "mega_ball": b, "reason": " · ".join(parts)})

    h, t, d, c = stats["hot_white"][0], stats["trending_white"][0], stats["overdue_white"][0], stats["cold_white"][0]
    summary = [
        f"Based on {stats['draws']} drawings from {stats['from_date']} to {stats['to_date']}.",
        f"Most drawn: {h['number']} ({h['times']} times, against an average of {stats['expected_per_white']}). "
        f"Least drawn: {c['number']} ({c['times']} times).",
        f"Trending in the last {RECENT_DRAWS} drawings: {', '.join(str(x['number']) for x in stats['trending_white'])}.",
        f"Longest absent: {d['number']} (not drawn for {d['draws_since_seen']} drawings).",
        f"Half of all winning tickets had white balls adding up to {lo}-{hi}, and most had 2 or 3 odd numbers, "
        f"so each suggested game is kept to that shape.",
        "Each game mixes 2 hot numbers, 1 trending, 1 overdue and 1 wildcard. "
        "These spreads are within normal random variation: every ticket still has the same odds.",
    ]
    return {"source": "builtin", "source_label": "Built-in analysis", "summary": summary, "tickets": tickets}


# ==================================================================== Claude
_SYSTEM = (
    "You analyze lottery draw history for a personal number-picking app. Lottery draws are independent "
    "and uniformly random: no pattern in past draws changes the odds of any ticket, and you must not claim "
    "or imply otherwise. You may describe what the history shows (most and least drawn numbers, recent "
    "streaks, gaps, typical sums and odd/even splits) and suggest tickets that reflect it, clearly framed as "
    "a way to choose numbers, not a prediction. Reply with JSON only."
)


def _prompt(stats: dict, games: int) -> str:
    return (
        f"Here are statistics from the {stats['game']} draw history:\n"
        f"{json.dumps(stats, indent=1)}\n\n"
        f"Suggest exactly {games} different tickets. Each ticket has 5 different white balls from "
        f"{stats['white_range'][0]}-{stats['white_range'][1]} and one {stats['bonus_name']} from "
        f"{stats['bonus_range'][0]}-{stats['bonus_range'][1]}. Use the statistics, vary the tickets, "
        f"and give a short reason (under 20 words) for each.\n"
        f"Also write a summary of 3 to 5 short sentences on what the history shows, ending with a plain "
        f"reminder that the odds are the same for every ticket.\n\n"
        'Reply with this JSON and nothing else: {"summary": ["sentence", ...], '
        '"tickets": [{"white_numbers": [n, n, n, n, n], "bonus": n, "reason": "..."}]}'
    )


def ai_status() -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return {"available": bool(key) and Config.AI_ENABLED, "model": Config.AI_MODEL,
            "enabled": Config.AI_ENABLED, "has_key": bool(key)}


def _call_claude(prompt: str) -> str:
    body = json.dumps({
        "model": Config.AI_MODEL,
        "max_tokens": 1500,
        "system": _SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body, method="POST",
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"].strip(),
                 "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=Config.AI_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise RuntimeError(f"Claude API error {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"could not reach the Claude API ({exc})") from exc
    return "".join(b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text")


def _parse_claude(text: str, stats: dict, games: int) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError("Claude's reply had no JSON in it")
    data = json.loads(text[start:end + 1])
    wlo, whi = stats["white_range"]
    blo, bhi = stats["bonus_range"]
    tickets, seen = [], set()
    for t in data.get("tickets", []):
        try:
            whites = sorted(int(x) for x in t["white_numbers"])
            bonus = int(t["bonus"])
        except (KeyError, TypeError, ValueError):
            continue
        key = (*whites, bonus)
        if (len(set(whites)) == 5 and all(wlo <= x <= whi for x in whites)
                and blo <= bonus <= bhi and key not in seen):
            seen.add(key)
            tickets.append({"white_numbers": whites, "mega_ball": bonus,
                            "reason": str(t.get("reason", ""))[:200]})
    if not tickets:
        raise RuntimeError("Claude's reply had no valid tickets")
    summary = [str(s)[:400] for s in data.get("summary", [])][:6]
    return {"tickets": tickets[:games], "summary": summary}


# ================================================================== public
def suggest(games: int = 5, use_ai: bool = True) -> dict:
    if not 1 <= games <= MAX_GAMES:
        raise ValueError(f"Games must be between 1 and {MAX_GAMES}.")
    draws = HistoricalDataLoader.load()["draw_history"]
    if len(draws) < 10:
        raise ValueError("Not enough draw history loaded - upload a draw-history file first.")

    game = Config.GAME
    stats = history_stats(draws, game)
    status = ai_status()
    result = builtin_suggestion(stats, games)
    note = None

    if use_ai and status["available"]:
        try:
            ai = _parse_claude(_call_claude(_prompt(stats, games)), stats, games)
            result = {"source": "claude", "source_label": f"Claude ({Config.AI_MODEL})", **ai}
            if len(ai["tickets"]) < games:
                note = f"Claude returned {len(ai['tickets'])} valid ticket(s) of the {games} asked for."
        except Exception as exc:          # any failure: keep the built-in result
            note = f"Claude suggestion unavailable: {exc}. Showing the built-in analysis instead."
    elif use_ai and not status["has_key"] and status["enabled"]:
        note = "Set the ANTHROPIC_API_KEY environment variable to get a suggestion written by Claude."

    return {**result, "note": note, "ai": status, "stats": stats}
