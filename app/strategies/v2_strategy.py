from app.models.ticket import Ticket
from app.services.historical_data import HistoricalDataLoader
from .base import TicketGenerationStrategy


class V2PortfolioStrategy(TicketGenerationStrategy):
    """Experimental coverage heuristic: anchor on a real observed pair from
    the draw history, add overdue coverage, then diversify. No predictive
    advantage over a random pick is implied.
    """

    def generate(self):
        g = self.game
        data = HistoricalDataLoader.load(g)
        pairs = [p for p in data["top_pairs"] if max(p) <= g.white_max]
        overdue = data["overdue_numbers"]

        anchor = self.rng.choice(pairs) if pairs else tuple(self.rng.sample(range(1, g.white_max + 1), 2))
        selected = set(anchor)

        remaining_overdue = [n for n in overdue if n not in selected and n <= g.white_max]
        if remaining_overdue and len(selected) < g.white_count:
            selected.add(self.rng.choice(remaining_overdue))

        pool = [n for n in range(1, g.white_max + 1) if n not in selected]
        while len(selected) < g.white_count:
            n = self.rng.choice(pool)
            selected.add(n)
            pool.remove(n)

        return Ticket(tuple(sorted(selected)), self._weighted_bonus(data["mega_weights"]))
