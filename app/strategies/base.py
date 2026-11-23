from abc import ABC, abstractmethod
import secrets

from app.models.ticket import Ticket


class TicketGenerationStrategy(ABC):
    def __init__(self, game):
        self.game = game
        self.rng = secrets.SystemRandom()

    @abstractmethod
    def generate(self) -> Ticket:
        raise NotImplementedError

    def _weighted_bonus(self, weights: dict) -> int:
        """Pick the bonus ball (Mega Ball / Powerball), weighted by history.
        Balls outside the game's current range are ignored."""
        valid = {b: w for b, w in (weights or {}).items() if 1 <= b <= self.game.bonus_max}
        if not valid:
            return self.rng.randint(1, self.game.bonus_max)
        return self.rng.choices(list(valid), weights=list(valid.values()), k=1)[0]
