"""Hot-Number Games: a set of tickets built only from the most-drawn numbers
in the loaded draw history.

Rules (same as the "Powerball Hot-Number Games" spreadsheet):
  * white balls come from the top `white_pool` most-drawn numbers,
    the bonus ball from the top `bonus_pool` most-drawn bonus balls;
  * every hot white ball is used; the 5 x games slots are shared out as evenly
    as possible, with the extra uses going to the most-drawn numbers;
  * tickets share as few numbers with each other as possible
    (e.g. 5 games from 10 numbers: any two games share exactly 2);
  * each game gets a different bonus ball while there are enough of them.
Each Regenerate gives a different arrangement that follows the same rules.

This organizes picks by frequency; it does not change the odds of any ticket.
"""
import secrets
from collections import Counter
from itertools import combinations

from app.models.ticket import Ticket
from app.services.historical_data import HistoricalDataLoader


class HotNumberGames:
    MAX_GAMES = 20
    RESTARTS = 25
    STEPS = 1500

    def __init__(self, game):
        self.game = game
        self.rng = secrets.SystemRandom()

    # ------------------------------------------------------------- public
    def generate(self, games: int = 5, white_pool: int = 10, bonus_pool: int = 5) -> dict:
        g = self.game
        if not 1 <= games <= self.MAX_GAMES:
            raise ValueError(f"Games must be between 1 and {self.MAX_GAMES}.")
        if not g.white_count <= white_pool <= g.white_max:
            raise ValueError(f"Top white balls must be between {g.white_count} and {g.white_max}.")
        if not 1 <= bonus_pool <= g.bonus_max:
            raise ValueError(f"Top {g.bonus_name}s must be between 1 and {g.bonus_max}.")

        data = HistoricalDataLoader.load()
        draws = data["draw_history"]
        if not draws:
            raise ValueError("No historical draws are loaded - upload a draw-history file first.")

        hot_white = self._ranked(draws, "white", g.white_max)[:white_pool]
        hot_bonus = self._ranked(draws, "bonus", g.bonus_max)[:bonus_pool]
        white_nums = [n for n, _ in hot_white]

        # Balls drawn equally often around the cut-off: the ones left out
        tie_note = self._tie_note(draws, white_pool, bonus_pool)

        targets = self._targets(white_nums, games)
        tickets_white = self._arrange(targets, games)
        bonuses = self._bonuses([n for n, _ in hot_bonus], games)

        tickets = [Ticket(tuple(sorted(w)), b) for w, b in zip(tickets_white, bonuses)]
        used_w = Counter(n for t in tickets for n in t.white_numbers)
        used_b = Counter(t.mega_ball for t in tickets)
        overlaps = [len(set(a.white_numbers) & set(b.white_numbers)) for a, b in combinations(tickets, 2)]

        return {
            "tickets": [t.to_dict() for t in tickets],
            "hot_white": [{"number": n, "times_drawn": c, "games_using": used_w[n]} for n, c in hot_white],
            "hot_bonus": [{"number": n, "times_drawn": c, "games_using": used_b[n]} for n, c in hot_bonus],
            "max_shared": max(overlaps, default=0),
            "draws": len(draws),
            "from_date": draws[-1]["date"],
            "to_date": draws[0]["date"],
            "avg_white": round(len(draws) * g.white_count / g.white_max, 1),
            "avg_bonus": round(len(draws) / g.bonus_max, 1),
            "tie_note": tie_note,
        }

    # ------------------------------------------------------------- ranking
    @staticmethod
    def _ranked(draws, kind, max_n):
        """[(number, times_drawn)] most-drawn first; ties go to the number
        drawn more recently. draws are newest first."""
        counts, last = Counter(), {}
        for i, d in enumerate(draws):
            nums = d["white_numbers"] if kind == "white" else [d["mega_ball"]]
            for n in nums:
                if 1 <= n <= max_n:            # skips retired balls (e.g. Mega Ball 25)
                    counts[n] += 1
                    last.setdefault(n, i)
        order = sorted(range(1, max_n + 1), key=lambda n: (-counts[n], last.get(n, len(draws)), n))
        return [(n, counts[n]) for n in order]

    def _tie_note(self, draws, white_pool, bonus_pool):
        notes = []
        for kind, pool, max_n, label in (("white", white_pool, self.game.white_max, "white ball"),
                                         ("bonus", bonus_pool, self.game.bonus_max, self.game.bonus_name)):
            ranked = self._ranked(draws, kind, max_n)
            if pool < len(ranked) and ranked[pool - 1][1] == ranked[pool][1]:
                cut = ranked[pool - 1][1]
                out = [n for n, c in ranked[pool:] if c == cut]
                notes.append(f"{label} {', '.join(map(str, out))} also drawn {cut} times "
                             f"(ties go to the more recently drawn number)")
        return "; ".join(notes) or None

    # ------------------------------------------------------------- layout
    def _targets(self, numbers, games):
        """How many games each hot number goes on: 5 x games slots shared as
        evenly as possible, extra uses to the most-drawn numbers."""
        slots = self.game.white_count * games
        if len(numbers) > slots:                        # more hot numbers than slots
            numbers = numbers[:slots]
        base, extra = divmod(slots, len(numbers))
        if base + (1 if extra else 0) > games:          # a number can't appear twice in a game
            raise ValueError("Too few hot numbers for that many games.")
        return {n: base + (1 if i < extra else 0) for i, n in enumerate(numbers)}

    def _arrange(self, targets, games):
        best, best_cost = None, None
        for _ in range(self.RESTARTS):
            tickets = self._deal(targets, games)
            cost = self._improve(tickets)
            if best_cost is None or cost < best_cost:
                best, best_cost = [set(t) for t in tickets], cost
            if self._is_ideal(best_cost, targets, games):
                break
        self.rng.shuffle(best)
        return best

    def _deal(self, targets, games):
        """Random starting layout that meets every target count."""
        k = self.game.white_count
        while True:
            tickets = [set() for _ in range(games)]
            items = list(targets.items())
            self.rng.shuffle(items)
            items.sort(key=lambda kv: -kv[1])
            ok = True
            for n, times in items:
                open_ = [t for t in tickets if len(t) < k and n not in t]
                if len(open_) < times:
                    ok = False
                    break
                self.rng.shuffle(open_)
                open_.sort(key=len)
                for t in open_[:times]:
                    t.add(n)
            if ok:
                return tickets

    @staticmethod
    def _cost(tickets):
        ov = [len(a & b) for a, b in combinations(tickets, 2)]
        return (max(ov, default=0), sum(o * o for o in ov))

    def _improve(self, tickets):
        """Swap numbers between games (keeps every count) while it lowers the
        overlap between games."""
        cost = self._cost(tickets)
        if len(tickets) < 2:
            return cost
        for _ in range(self.STEPS):
            i, j = self.rng.sample(range(len(tickets)), 2)
            a = self.rng.choice(list(tickets[i] - tickets[j]) or [None])
            b = self.rng.choice(list(tickets[j] - tickets[i]) or [None])
            if a is None or b is None:
                continue
            tickets[i].remove(a); tickets[i].add(b)
            tickets[j].remove(b); tickets[j].add(a)
            new = self._cost(tickets)
            if new <= cost:
                cost = new
            else:
                tickets[i].remove(b); tickets[i].add(a)
                tickets[j].remove(a); tickets[j].add(b)
        return cost

    def _is_ideal(self, cost, targets, games):
        """True when overlaps can't be spread any more evenly."""
        pairs = games * (games - 1) // 2
        if not pairs:
            return True
        total = sum(c * (c - 1) // 2 for c in targets.values())   # fixed by the counts
        lo, rem = divmod(total, pairs)
        return cost == (lo + (1 if rem else 0), (pairs - rem) * lo * lo + rem * (lo + 1) ** 2)

    def _bonuses(self, pool, games):
        """A different bonus ball per game while they last, then reuse evenly."""
        out = []
        while len(out) < games:
            batch = list(pool)
            self.rng.shuffle(batch)
            out.extend(batch)
        return out[:games]
