import secrets
from app.models.ticket import Ticket
from app.services.historical_data import HistoricalDataLoader
from .base import TicketGenerationStrategy


class V2PortfolioStrategy(TicketGenerationStrategy):
    """Experimental coverage heuristic: anchor on a real observed pair from
    the analysis workbook, add overdue coverage, then diversify. No
    predictive advantage over a random pick is implied.
    """

    def __init__(self):
        self.rng = secrets.SystemRandom()

    def generate(self):
        data = HistoricalDataLoader.load()
        pairs = data["top_pairs"]
        overdue = data["overdue_numbers"]

        anchor = self.rng.choice(pairs) if pairs else (
            self.rng.randint(1, 70), self.rng.randint(1, 70)
        )
        selected = set(anchor)

        remaining_overdue = [n for n in overdue if n not in selected]
        if remaining_overdue and len(selected) < 5:
            selected.add(self.rng.choice(remaining_overdue))

        pool = [n for n in range(1, 71) if n not in selected]
        while len(selected) < 5:
            n = self.rng.choice(pool)
            selected.add(n)
            pool.remove(n)

        mega = self._weighted_mega(data["mega_weights"])
        return Ticket(tuple(sorted(selected)), mega)

    def _weighted_mega(self, weights: dict) -> int:
        if not weights:
            return self.rng.randint(1, 24)
        balls = list(weights.keys())
        totals = list(weights.values())
        return self.rng.choices(balls, weights=totals, k=1)[0]
