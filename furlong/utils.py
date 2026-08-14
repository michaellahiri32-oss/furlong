"""Small shared helpers: odds/probability conversion and logging."""
from __future__ import annotations

import logging
import sys

import numpy as np


def get_logger(name: str = "furlong") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s",
                                         "%H:%M:%S"))
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
    return logger


def prob_to_odds(p: float | np.ndarray) -> float | np.ndarray:
    """Fair decimal odds from a probability (guards against divide-by-zero)."""
    p = np.clip(p, 1e-6, 1.0)
    return 1.0 / p


def odds_to_prob(dec: float | np.ndarray) -> float | np.ndarray:
    """Implied probability from decimal odds (not overround-adjusted)."""
    dec = np.asarray(dec, dtype=float)
    out = np.where(dec > 1.0, 1.0 / dec, np.nan)
    return out


def remove_overround(implied: np.ndarray) -> np.ndarray:
    """Normalise a set of bookmaker implied probabilities to sum to 1."""
    implied = np.asarray(implied, dtype=float)
    s = np.nansum(implied)
    if s <= 0:
        return implied
    return implied / s


def fmt_distance(furlongs) -> str:
    """Furlongs (float) → UK-style distance, e.g. 10.0 -> '1m2f', 6.0 -> '6f'."""
    try:
        f = float(furlongs)
    except (TypeError, ValueError):
        return "—"
    whole = int(f)
    half = "½" if abs(f - whole - 0.5) < 0.1 else ""
    miles, furl = divmod(whole, 8)
    parts = []
    if miles:
        parts.append(f"{miles}m")
    if furl or half:
        parts.append(f"{furl}{half}f")
    return "".join(parts) or f"{whole}f"


def fmt_odds(dec: float) -> str:
    """Pretty decimal odds: 3.5 -> '3.50'; very long prices capped for display."""
    if dec is None or not np.isfinite(dec):
        return "—"
    if dec >= 200:
        return "200+"
    if dec >= 50:
        return f"{dec:.0f}"
    return f"{dec:.2f}"
