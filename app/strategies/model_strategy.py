import secrets
from app.models.ticket import Ticket
from app.services.historical_data import HistoricalDataLoader
from .base import TicketGenerationStrategy


class HistoricalModelStrategy(TicketGenerationStrategy):
    """Leans on real hot/overdue numbers pulled from the analysis workbook
    (see config.ini for its location). This is a selection heuristic only;
    it does not change the mathematical probability of any future drawing.
    """

    def __init__(self):
        self.rng = secrets.SystemRandom()

    def generate(self):
        data = HistoricalDataLoader.load()
        hot = data["hot_numbers"]
        overdue = data["overdue_numbers"]
        core = list(dict.fromkeys(hot + overdue))  # de-duped, order preserved

        pool_size = min(3, len(core))
        selected = set(self.rng.sample(core, pool_size))
        remaining = [n for n in range(1, 71) if n not in selected]
        selected.update(self.rng.sample(remaining, 5 - len(selected)))

        mega = self._weighted_mega(data["mega_weights"])
        return Ticket(tuple(sorted(selected)), mega)

    def _weighted_mega(self, weights: dict) -> int:
        if not weights:
            return self.rng.randint(1, 24)
        balls = list(weights.keys())
        totals = list(weights.values())
        return self.rng.choices(balls, weights=totals, k=1)[0]
