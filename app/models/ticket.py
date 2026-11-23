from dataclasses import dataclass


@dataclass(frozen=True)
class Ticket:
    """One play. `mega_ball` holds the bonus ball for whichever game is active
    (Mega Ball for Mega Millions, Powerball for Powerball); the key name is kept
    so the API and front end stay unchanged."""
    white_numbers: tuple[int, int, int, int, int]
    mega_ball: int

    def to_dict(self):
        return {"white_numbers": list(self.white_numbers), "mega_ball": self.mega_ball}
