from abc import ABC, abstractmethod
from app.models.ticket import Ticket

class TicketGenerationStrategy(ABC):
    @abstractmethod
    def generate(self) -> Ticket:
        raise NotImplementedError
