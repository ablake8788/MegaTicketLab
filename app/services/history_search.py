"""Search mode: keep generating tickets until each one matches a past drawing
at (or above) a target level, e.g. "4 white + bonus ball, or better".

Matching is done with lookup tables of every 5-, 4- and 3-number group that
appeared in a past drawing, so checking one ticket against the whole history
takes microseconds no matter how many draws are loaded.

Note: a ticket that matched a past drawing has exactly the same chance as any
other ticket of matching the NEXT drawing. This is a backtest curiosity, not
a way to improve the odds.
"""
import time
from itertools import combinations

from app.services.historical_data import HistoricalDataLoader
from app.strategies.strategy_factory import StrategyFactory


class HistoryMatcher:
    LEVELS = (5, 4, 3)  # smallest white-ball overlap the tables can find

    def __init__(self, draws: list):
        self.draws = draws
        self._index = {k: {} for k in self.LEVELS}
        for i, d in enumerate(draws):
            whites = sorted(d["white_numbers"])
            for k in self.LEVELS:
                for combo in combinations(whites, k):
                    self._index[k].setdefault(combo, []).append(i)

    def best_match(self, ticket):
        """Best (white_matches, bonus_match, draw) for this ticket, or
        (0, False, None) when no past drawing shares 3+ white balls.
        Order follows the prize table: 5 white beats 4 white + bonus."""
        whites = sorted(ticket.white_numbers)
        for k in self.LEVELS:
            hits = set()
            for combo in combinations(whites, k):
                hits.update(self._index[k].get(combo, ()))
            if hits:
                draws = [self.draws[i] for i in sorted(hits)]  # newest first
                with_bonus = [d for d in draws if d["mega_ball"] == ticket.mega_ball]
                best = with_bonus[0] if with_bonus else draws[0]
                return k, bool(with_bonus), best
        return 0, False, None


class HistorySearch:
    MAX_TICKETS = 100
    TIME_LIMIT_S = 45          # stop searching after this many seconds
    MAX_ATTEMPTS = 5_000_000   # ... or this many candidate tickets

    def __init__(self, game):
        self.game = game

    def search(self, count: int, strategy_name: str, min_white: int, need_bonus: bool) -> dict:
        if not 1 <= count <= self.MAX_TICKETS:
            raise ValueError(f"Ticket count must be between 1 and {self.MAX_TICKETS}.")
        if min_white not in HistoryMatcher.LEVELS:
            raise ValueError("Target must be 3, 4 or 5 white balls.")

        draws = HistoricalDataLoader.load()["draw_history"]
        if not draws:
            raise ValueError("No historical draws are loaded - upload a draw-history file first.")

        matcher = HistoryMatcher(draws)
        strategy = StrategyFactory.create(strategy_name, self.game)
        target = (min_white, need_bonus)
        seen, found = set(), []
        attempts, start = 0, time.perf_counter()

        while len(found) < count and attempts < self.MAX_ATTEMPTS:
            ticket = strategy.generate()
            attempts += 1
            key = (*ticket.white_numbers, ticket.mega_ball)
            if key in seen:
                continue
            white, bonus, draw = matcher.best_match(ticket)
            if (white, bonus) >= target:
                seen.add(key)
                matched = sorted(set(ticket.white_numbers) & set(draw["white_numbers"]))
                found.append({
                    **ticket.to_dict(),
                    "white_matches": white,
                    "mega_match": bonus,
                    "matched_white_numbers": matched,
                    "matched_draw": draw,
                    "found_after": attempts,
                })
            if attempts % 2000 == 0 and time.perf_counter() - start > self.TIME_LIMIT_S:
                break

        return {
            "tickets": found,
            "requested": count,
            "complete": len(found) == count,
            "attempts": attempts,
            "seconds": round(time.perf_counter() - start, 2),
            "draws_checked": len(draws),
            "target": {"min_white": min_white, "bonus": need_bonus},
        }
