from .random_strategy import RandomTicketStrategy
from .model_strategy import HistoricalModelStrategy
from .v2_strategy import V2PortfolioStrategy

class StrategyFactory:
    _strategies = {
        "random": RandomTicketStrategy,
        "model": HistoricalModelStrategy,
        "v2": V2PortfolioStrategy,
    }

    @classmethod
    def create(cls, name: str):
        strategy = cls._strategies.get((name or "").lower())
        if not strategy:
            raise ValueError(f"Unknown strategy '{name}'. Choose random, model, or v2.")
        return strategy()
