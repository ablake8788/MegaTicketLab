"""
Loads draw history for the game selected in config.ini ([game] name) and
exposes hot / overdue / pair / bonus-ball data the strategies can use.

Accepted data files (config.ini [data]):
  * .xlsx - needs a "Draw History" sheet (Draw Date | Ball 1..5 | bonus ball).
            The Mega Millions analysis workbook also carries pre-computed
            "White Ball Frequency", "Overdue Numbers", "Top Pairs" and
            "Mega Ball Frequency" sheets; when all four exist they are used
            as-is. Otherwise the statistics are calculated from Draw History.
  * .csv  - one draw per row: a date, then five white balls and the bonus
            ball. Both "18,26,49,50,54,1" style columns and a single
            "18 26 49 50 54 01" cell work; any extra column (Power Play,
            jackpot...) after the bonus ball is ignored.

If the file is missing or unreadable the app falls back to a built-in
snapshot (Mega Millions) or to uniform random pools (Powerball) so it still
runs; the "source" field of the result says which one you got.
"""
import csv
import re
import threading
from collections import Counter
from datetime import datetime
from itertools import combinations
from pathlib import Path

from openpyxl import load_workbook

from app.config import Config

# Fallback snapshot, used only for Mega Millions if the workbook can't be read.
_FALLBACK_HOT = [42, 22, 49, 58, 66, 43, 27, 36, 52, 31]
_FALLBACK_OVERDUE = [11, 28, 69, 64, 15, 40, 12, 67, 16, 13]
_FALLBACK_PAIRS = [(22, 42), (18, 64), (18, 27), (43, 52), (19, 31)]

_STAT_SHEETS = ("White Ball Frequency", "Overdue Numbers", "Top Pairs", "Mega Ball Frequency")
_DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%m-%d-%Y", "%Y/%m/%d")


class HistoricalDataLoader:
    _lock = threading.Lock()
    _cache = None  # populated on first load()
    # Set by the "Upload data" section: {"path", "name", "sheet", "uploaded"}.
    # None = use the file named in config.ini.
    _override = None

    @classmethod
    def load(cls, force_reload: bool = False) -> dict:
        """Returns a dict with hot_numbers, overdue_numbers, top_pairs,
        mega_weights (bonus ball -> weight), draw_history and a 'source'
        flag: 'workbook' (data file read) or 'fallback'."""
        with cls._lock:
            if cls._cache is not None and not force_reload:
                return cls._cache
            cls._cache = cls._load_from_file()
            return cls._cache

    # ------------------------------------------------- upload / sheet choice
    @classmethod
    def current_file(cls) -> dict:
        """The data file in use: an uploaded one, or the config.ini one."""
        if cls._override:
            return dict(cls._override)
        return {"path": Config.DATA_PATH, "name": Config.DATA_PATH.name, "sheet": None, "uploaded": False}

    @classmethod
    def use_file(cls, path, name: str, sheet=None, uploaded: bool = True) -> dict:
        """Switch to another data file (and optionally a sheet) and reload."""
        with cls._lock:
            cls._override = {"path": Path(path), "name": name, "sheet": sheet or None, "uploaded": uploaded}
            cls._cache = None
        return cls.load()

    @classmethod
    def use_sheet(cls, sheet: str) -> dict:
        cur = cls.current_file()
        return cls.use_file(cur["path"], cur["name"], sheet, cur["uploaded"])

    @classmethod
    def reset(cls) -> dict:
        """Forget any upload / sheet choice and go back to config.ini's file."""
        with cls._lock:
            cls._override = None
            cls._cache = None
        return cls.load()

    @staticmethod
    def list_sheets(path) -> list:
        path = Path(path)
        if path.suffix.lower() == ".csv" or not path.exists():
            return []
        try:
            wb = load_workbook(path, read_only=True)
            try:
                return list(wb.sheetnames)
            finally:
                wb.close()
        except Exception:
            return []

    # ------------------------------------------------------------------ load
    @classmethod
    def _load_from_file(cls) -> dict:
        cur = cls.current_file()
        result = cls._load_path(cur["path"], cur["sheet"])
        result.update({
            "data_file": str(cur["path"]),
            "file_name": cur["name"],
            "uploaded": cur["uploaded"],
            "sheets": cls.list_sheets(cur["path"]),
        })
        result.setdefault("sheet", cur["sheet"])
        return result

    @classmethod
    def _load_path(cls, path, sheet=None) -> dict:
        path = Path(path)
        game = Config.GAME
        if not path.exists():
            return cls._fallback(f"data file not found at {path}")

        try:
            if path.suffix.lower() == ".csv":
                draws, skipped = cls._read_draws_csv(path, game)
                precomputed, sheet = None, None
            else:
                draws, skipped, precomputed, sheet = cls._read_workbook(path, game, sheet)
        except Exception as exc:  # corrupt/locked file, wrong format, etc.
            out = cls._fallback(f"could not read data file: {exc}")
            out["sheet"] = sheet
            return out

        if not draws:
            where = f'sheet "{sheet}"' if sheet else "data file"
            out = cls._fallback(f"{where} has no valid {game.title} draws ({skipped} row(s) skipped)")
            out.update({"sheet": sheet, "skipped_rows": skipped})
            return out

        draws.sort(key=lambda d: d["date"], reverse=True)
        stats = precomputed or cls._compute_stats(cls._windowed(draws), game)
        if not stats["hot_numbers"] or not stats["overdue_numbers"]:
            return cls._fallback("data file parsed but statistics were empty")

        return {
            **stats,
            "draw_history": draws,
            "source": "workbook",
            "path": str(path),
            "game": game.key,
            "skipped_rows": skipped,
            "sheet": sheet,
            "stats_from": "workbook sheets" if precomputed else "draw history",
        }

    @staticmethod
    def _windowed(draws: list) -> list:
        """Draws used for computed statistics: last Config.YEARS years."""
        if not Config.YEARS or not draws:
            return draws
        newest = datetime.strptime(draws[0]["date"], "%Y-%m-%d")
        try:
            cutoff = newest.replace(year=newest.year - Config.YEARS)
        except ValueError:  # Feb 29
            cutoff = newest.replace(year=newest.year - Config.YEARS, day=28)
        cutoff_s = cutoff.strftime("%Y-%m-%d")
        return [d for d in draws if d["date"] > cutoff_s]

    # ------------------------------------------------------------- xlsx / csv
    @classmethod
    def _read_workbook(cls, path, game, sheet=None):
        """Reads draws from `sheet` (default: "Draw History", else the first
        sheet). Returns (draws, skipped, precomputed_stats_or_None, sheet)."""
        wb = load_workbook(path, data_only=True, read_only=True)
        try:
            if sheet:
                if sheet not in wb.sheetnames:
                    raise ValueError(f'workbook has no sheet named "{sheet}"')
            else:
                sheet = "Draw History" if "Draw History" in wb.sheetnames else wb.sheetnames[0]
            rows = list(wb[sheet].iter_rows(min_row=1, values_only=True))
            if rows:
                cls._check_game(rows[0], game)
            draws, skipped = cls._rows_to_draws(rows, game)
            precomputed = None
            if (game.key == "mega_millions" and sheet == "Draw History"
                    and all(s in wb.sheetnames for s in _STAT_SHEETS)):
                precomputed = {
                    "hot_numbers": cls._read_hot(wb),
                    "overdue_numbers": cls._read_overdue(wb),
                    "top_pairs": cls._read_pairs(wb),
                    "mega_weights": cls._read_mega_weights(wb, game),
                }
            return draws, skipped, precomputed, sheet
        finally:
            wb.close()

    @classmethod
    def _read_draws_csv(cls, path, game):
        with open(path, newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh))
        if rows:
            cls._check_game(rows[0], game)
        return cls._rows_to_draws(rows, game)

    @staticmethod
    def _check_game(header_row, game):
        """Stop a Mega Millions file being read as Powerball (or the reverse):
        many of its draws would otherwise pass the range checks silently."""
        from app.games import GAMES
        text = " ".join(str(c) for c in header_row if c is not None).lower()
        if game.bonus_name.lower() in text:
            return
        for other in GAMES.values():
            if other.key != game.key and other.bonus_name.lower() in text:
                raise ValueError(
                    f"this looks like a {other.title} file, but the app is set to "
                    f"{game.title} (config.ini [game] name)")

    @classmethod
    def _rows_to_draws(cls, rows, game):
        draws, skipped = [], 0
        for r in rows:
            if not r or r[0] is None or str(r[0]).strip() == "":
                continue
            date_str = cls._parse_date(r[0])
            if date_str is None:        # header or junk line
                continue
            # first 6 integers after the date = 5 white balls + bonus ball
            nums = [int(x) for x in re.findall(r"\d+", " ".join(str(c) for c in r[1:] if c is not None))][:6]
            if len(nums) < 6:
                skipped += 1
                continue
            white, bonus = sorted(nums[:5]), nums[5]
            if (len(set(white)) != 5 or white[0] < 1 or white[-1] > game.white_max
                    or not 1 <= bonus <= (game.history_bonus_max or game.bonus_max)):
                skipped += 1            # e.g. older draws from a previous game format
                continue
            draws.append({"date": date_str, "white_numbers": white, "mega_ball": bonus})
        return draws, skipped

    @staticmethod
    def _parse_date(value):
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")
        text = str(value).strip()
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    # -------------------------------------------- statistics from draw history
    @staticmethod
    def _compute_stats(draws: list, game) -> dict:
        n = len(draws)  # newest first
        counts, last_idx, pairs, bonus = Counter(), {}, Counter(), Counter()
        for i, d in enumerate(draws):
            for b in d["white_numbers"]:
                counts[b] += 1
                last_idx.setdefault(b, i)
            for c in combinations(d["white_numbers"], 2):
                pairs[c] += 1
            bonus[d["mega_ball"]] += 1
        balls = range(1, game.white_max + 1)
        hot = sorted(balls, key=lambda b: (-counts[b], b))[: Config.HOT_COUNT]
        overdue = sorted(balls, key=lambda b: (-last_idx.get(b, n), b))[: Config.OVERDUE_COUNT]
        top_pairs = [p for p, _ in sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0]))[: Config.PAIR_COUNT]]
        weights = {b: max(bonus[b], 1) for b in range(1, game.bonus_max + 1)}
        return {"hot_numbers": hot, "overdue_numbers": overdue,
                "top_pairs": top_pairs, "mega_weights": weights}

    # ------------------------------------ pre-computed Mega Millions workbook
    @staticmethod
    def _read_hot(wb) -> list:
        rows = [r for r in wb["White Ball Frequency"].iter_rows(min_row=2, values_only=True) if r and r[0] is not None]
        rows.sort(key=lambda r: r[1] or 0, reverse=True)
        return [int(r[0]) for r in rows[: Config.HOT_COUNT]]

    @staticmethod
    def _read_overdue(wb) -> list:
        rows = [r for r in wb["Overdue Numbers"].iter_rows(min_row=2, values_only=True) if r and r[0] is not None]
        rows.sort(key=lambda r: r[1] or 0, reverse=True)
        return [int(r[0]) for r in rows[: Config.OVERDUE_COUNT]]

    @staticmethod
    def _read_pairs(wb) -> list:
        rows = [r for r in wb["Top Pairs"].iter_rows(min_row=2, values_only=True)
                if r and r[0] is not None and r[1] is not None]
        rows.sort(key=lambda r: r[2] or 0, reverse=True)
        return [(int(r[0]), int(r[1])) for r in rows[: Config.PAIR_COUNT]]

    @staticmethod
    def _read_mega_weights(wb, game) -> dict:
        # Uses the "Current Regime" column. Every ball in the current range gets
        # weight >= 1 so nothing is impossible; balls OUTSIDE the current range
        # (e.g. Mega Ball 25, retired 04/2025) are dropped.
        ws = wb["Mega Ball Frequency"]
        header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
        try:
            col_idx = next(i for i, h in enumerate(header) if h and "Current Regime" in str(h))
        except StopIteration:
            col_idx = 1
        weights = {}
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or row[0] is None:
                continue
            ball = int(row[0])
            if not 1 <= ball <= game.bonus_max:
                continue
            count = row[col_idx] if col_idx < len(row) else None
            weights[ball] = max(int(count or 0), 1)
        return weights

    # ----------------------------------------------------------------- fallback
    @staticmethod
    def _fallback(reason: str) -> dict:
        game = Config.GAME
        mega = game.key == "mega_millions"
        return {
            "hot_numbers": list(_FALLBACK_HOT) if mega else [],
            "overdue_numbers": list(_FALLBACK_OVERDUE) if mega else [],
            "top_pairs": list(_FALLBACK_PAIRS) if mega else [],
            "mega_weights": {n: 1 for n in range(1, game.bonus_max + 1)},
            "draw_history": [],
            "source": "fallback",
            "game": game.key,
            "reason": reason,
        }
