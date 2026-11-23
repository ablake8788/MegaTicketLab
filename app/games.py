"""Game profiles. Everything that differs between lotteries lives here so the
rest of the app never hard-codes a ball range or a label.

New Jersey (like every other state) plays the single national Powerball game,
so there is no separate "NJ" profile - the rules and draws are identical.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class GameProfile:
    key: str
    title: str
    white_max: int
    bonus_max: int
    bonus_name: str
    bonus_short: str
    default_filename: str
    white_count: int = 5
    history_bonus_max: int = 0   # widest bonus range allowed in old draws (0 = same as bonus_max)

    @property
    def badge(self) -> str:
        return f"{self.white_count} / {self.white_max} + {self.bonus_short} / {self.bonus_max}"

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "white_count": self.white_count,
            "white_max": self.white_max,
            "bonus_max": self.bonus_max,
            "bonus_name": self.bonus_name,
            "bonus_short": self.bonus_short,
            "badge": self.badge,
        }


GAMES = {
    "mega_millions": GameProfile(
        key="mega_millions",
        title="Mega Millions",
        white_max=70,
        bonus_max=24,          # current format since 04/08/2025
        history_bonus_max=25,  # draws before 04/08/2025 used Mega Ball 1-25
        bonus_name="Mega Ball",
        bonus_short="MB",
        default_filename="Mega_Millions_3_Year_Advanced_Pattern_Analysis.xlsx",
    ),
    "powerball": GameProfile(
        key="powerball",
        title="Powerball",
        white_max=69,
        bonus_max=26,          # format since 10/2015
        bonus_name="Powerball",
        bonus_short="PB",
        default_filename="Powerball_Draw_History.xlsx",
    ),
}


def get_game(name: str) -> GameProfile:
    key = (name or "").strip().lower().replace(" ", "_").replace("-", "_")
    if key not in GAMES:
        raise ValueError(
            f"Unknown game '{name}' in config.ini [game] name. Choose one of: {', '.join(GAMES)}."
        )
    return GAMES[key]
