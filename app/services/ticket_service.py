from app.config import Config
from app.strategies.strategy_factory import StrategyFactory


class TicketService:
    MAX_TICKETS = 100

    def __init__(self, game=None):
        self.game = game or Config.GAME

    def generate_tickets(self, count: int, strategy_name: str):
        if not 1 <= count <= self.MAX_TICKETS:
            raise ValueError(f"Ticket count must be between 1 and {self.MAX_TICKETS}.")
        strategy = StrategyFactory.create(strategy_name, self.game)
        seen, tickets = set(), []
        while len(tickets) < count:
            ticket = strategy.generate()
            key = (*ticket.white_numbers, ticket.mega_ball)
            if key not in seen:
                seen.add(key)
                tickets.append(ticket)
        return tickets

    def compare(self, tickets, winning_white, winning_bonus):
        g = self.game
        if len(set(winning_white)) != g.white_count or any(n < 1 or n > g.white_max for n in winning_white):
            raise ValueError(f"Winning white balls must be {g.white_count} unique numbers from 1 to {g.white_max}.")
        if winning_bonus < 1 or winning_bonus > g.bonus_max:
            raise ValueError(f"{g.bonus_name} must be from 1 to {g.bonus_max}.")
        result = []
        target = set(winning_white)
        for ticket in tickets:
            matched = sorted(set(ticket.white_numbers) & target)
            result.append({
                **ticket.to_dict(),
                "white_matches": len(matched),
                "matched_white_numbers": matched,
                "mega_match": ticket.mega_ball == winning_bonus,
            })
        return result
