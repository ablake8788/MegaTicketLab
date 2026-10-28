import secrets
from app.models.ticket import Ticket
from .base import TicketGenerationStrategy

class RandomTicketStrategy(TicketGenerationStrategy):
    def __init__(self):
        self.rng = secrets.SystemRandom()

    def generate(self):
        white = tuple(sorted(self.rng.sample(range(1, 71), 5)))
        return Ticket(white, self.rng.randint(1, 24))
