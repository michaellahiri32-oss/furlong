"""Central configuration: paths, the canonical data schema, and feature lists.

Everything downstream (ingest, synthetic data, features, model) agrees on the
schema defined here, so the real rpscrape feed and the synthetic generator are
interchangeable.
"""
from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"                 # raw rpscrape CSV dumps
PROCESSED = DATA / "processed"     # tidy parquet: results.parquet, racecards.parquet
MODELS = DATA / "models"           # pickled models + calibrators + metadata
REPORTS = ROOT / "reports"         # generated HTML dashboards
WEBAPP = ROOT / "webapp"           # PWA source (shell, manifest, sw, icons)
DOCS = ROOT / "docs"               # published site (GitHub Pages serves this)

for _p in (RAW, PROCESSED, MODELS, REPORTS):
    _p.mkdir(parents=True, exist_ok=True)

# Where your local clone of rpscrape lives (https://github.com/joenano/rpscrape).
# Override with the RPSCRAPE_DIR environment variable.
RPSCRAPE_DIR = Path(os.environ.get("RPSCRAPE_DIR", ROOT.parent / "rpscrape"))

# --------------------------------------------------------------------------- #
# Canonical runner-level schema (one row per horse per race)
# --------------------------------------------------------------------------- #
# Identity / race context
ID_COLS = ["race_id", "date", "course", "code", "race_type", "is_handicap",
           "race_class", "distance_f", "going", "ran", "prize"]

# Runner attributes
RUNNER_COLS = ["horse_id", "horse", "pos", "won", "draw", "age", "sex",
               "weight_lbs", "or_", "rpr", "ts", "jockey", "jockey_id",
               "trainer", "trainer_id", "sire", "headgear", "days_since_run",
               "sp_dec"]

SCHEMA = ID_COLS + RUNNER_COLS

# Race "codes" — modelled separately because the drivers differ.
CODES = ("flat", "jumps")

# Going normalisation → an ordinal softness scale (firmer = lower).
GOING_SCALE = {
    "hard": 0, "firm": 1, "good to firm": 2, "good": 3, "good to soft": 4,
    "yielding": 4, "soft": 5, "good to yielding": 4, "yielding to soft": 5,
    "soft to heavy": 6, "heavy": 7,
    # all-weather
    "standard to slow": 3, "standard": 3, "standard to fast": 2, "slow": 4, "fast": 2,
}

# --------------------------------------------------------------------------- #
# Feature groups used by the model (leakage-safe; no same-race outcome info).
# NB: today's market price (sp_dec on a racecard) is deliberately EXCLUDED from
# the win model, so predictions are market-independent and can be compared to
# the price to find value.
# --------------------------------------------------------------------------- #
NUMERIC_FEATURES = [
    # ability
    "or_", "rpr", "ts",
    "rpr_last", "rpr_best3", "ts_best3",
    "rating_vs_field",            # this runner's OR minus field-median OR
    # weight & physical
    "weight_lbs", "weight_vs_field", "age",
    # draw
    "draw", "draw_pct", "draw_bias",
    # form / recency
    "days_since_run", "runs_career", "win_pct_career", "place_pct_career",
    "form_momentum",              # recent finishing-position trend
    "last_pos", "avg_pos_3",
    # suitability
    "going_delta", "dist_delta", "class_delta",
    "course_win_pct", "dist_win_pct", "going_win_pct",
    # connections (time-aware strike rates)
    "jockey_sr", "trainer_sr", "trainer_jockey_sr", "sire_sr",
    "trainer_course_sr",
    # context
    "field_size", "headgear_first",
]

CATEGORICAL_FEATURES = ["code"]

FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET = "won"

# --------------------------------------------------------------------------- #
# Each-way place terms (UK standard). Returns (n_places, place_fraction).
# --------------------------------------------------------------------------- #
def place_terms(ran: int, is_handicap: bool) -> tuple[int, float]:
    """Standard industry each-way terms by field size and handicap status."""
    if ran <= 4:
        return 1, 0.0            # win only
    if ran <= 7:
        return 2, 0.25
    if not is_handicap:
        return 3, 0.20
    # handicaps
    if ran <= 11:
        return 3, 0.20
    if ran <= 15:
        return 3, 0.25
    return 4, 0.25
