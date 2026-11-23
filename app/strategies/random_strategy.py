from app.models.ticket import Ticket
from .base import TicketGenerationStrategy


class RandomTicketStrategy(TicketGenerationStrategy):
    def generate(self):
        g = self.game
        white = tuple(sorted(self.rng.sample(range(1, g.white_max + 1), g.white_count)))
        return Ticket(white, self.rng.randint(1, g.bonus_max))
