from dataclasses import dataclass

@dataclass(frozen=True)
class Ticket:
    white_numbers: tuple[int, int, int, int, int]
    mega_ball: int

    def to_dict(self):
        return {"white_numbers": list(self.white_numbers), "mega_ball": self.mega_ball}
