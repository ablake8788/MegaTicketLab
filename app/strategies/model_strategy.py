from app.models.ticket import Ticket
from app.services.historical_data import HistoricalDataLoader
from .base import TicketGenerationStrategy


class HistoricalModelStrategy(TicketGenerationStrategy):
    """Leans on real hot/overdue numbers calculated from the draw history
    (see config.ini for the data file). This is a selection heuristic only;
    it does not change the mathematical probability of any future drawing.
    """

    def generate(self):
        g = self.game
        data = HistoricalDataLoader.load()
        core = list(dict.fromkeys(data["hot_numbers"] + data["overdue_numbers"]))
        core = [n for n in core if 1 <= n <= g.white_max]

        selected = set(self.rng.sample(core, min(3, len(core))))
        remaining = [n for n in range(1, g.white_max + 1) if n not in selected]
        selected.update(self.rng.sample(remaining, g.white_count - len(selected)))

        return Ticket(tuple(sorted(selected)), self._weighted_bonus(data["mega_weights"]))
