from app.strategies.strategy_factory import StrategyFactory

class TicketService:
    MAX_TICKETS = 100

    def generate_tickets(self, count: int, strategy_name: str):
        if not 1 <= count <= self.MAX_TICKETS:
            raise ValueError(f"Ticket count must be between 1 and {self.MAX_TICKETS}.")
        strategy = StrategyFactory.create(strategy_name)
        seen, tickets = set(), []
        while len(tickets) < count:
            ticket = strategy.generate()
            key = (*ticket.white_numbers, ticket.mega_ball)
            if key not in seen:
                seen.add(key)
                tickets.append(ticket)
        return tickets

    def compare(self, tickets, winning_white, winning_mega):
        if len(set(winning_white)) != 5 or any(n < 1 or n > 70 for n in winning_white):
            raise ValueError("Winning white balls must be 5 unique numbers from 1 to 70.")
        if winning_mega < 1 or winning_mega > 24:
            raise ValueError("Mega Ball must be from 1 to 24.")
        result = []
        target = set(winning_white)
        for ticket in tickets:
            matched = sorted(set(ticket.white_numbers) & target)
            result.append({
                **ticket.to_dict(),
                "white_matches": len(matched),
                "matched_white_numbers": matched,
                "mega_match": ticket.mega_ball == winning_mega,
            })
        return result
