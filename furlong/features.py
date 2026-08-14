"""Leakage-safe, time-aware feature engineering.

Every feature for a given runner is computed from information available *before*
that race goes off. Career and strike-rate stats use expanding windows that
exclude the current row; rolling form uses only prior runs. This is what keeps
the backtest honest and the live predictions trustworthy.

Input:  runner-level rows in the canonical schema (from ingest or synth).
Output: the same rows plus every column in config.FEATURES.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import FEATURES, GOING_SCALE

# Bayesian shrinkage strength for strike rates (pseudo-runs toward base rate).
_ALPHA = 12.0


def _going_soft(series: pd.Series) -> pd.Series:
    s = series.fillna("good").astype(str).str.strip().str.lower()
    return s.map(GOING_SCALE).fillna(3.0).astype(float)


def _pos_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _shrunk_strike_rate(df: pd.DataFrame, keys, base: float) -> pd.Series:
    """Expanding win rate for a group, excluding the current row, shrunk to base."""
    g = df.groupby(keys, observed=True)["won"]
    wins_before = g.cumsum() - df["won"]
    runs_before = g.cumcount()
    return (wins_before + _ALPHA * base) / (runs_before + _ALPHA)


def build(df: pd.DataFrame, verbose: bool = False) -> pd.DataFrame:
    df = df.sort_values(["date", "race_id"]).reset_index(drop=True).copy()
    df["date"] = pd.to_datetime(df["date"])
    base_win = float(df["won"].mean())

    # ---- normalise a few raw fields -------------------------------------- #
    df["going_soft"] = _going_soft(df["going"])
    df["pos_num"] = _pos_numeric(df["pos"])
    df["pos_fill"] = df["pos_num"].fillna(df["ran"]).astype(float)   # DNF => last
    for c in ["or_", "rpr", "ts"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # ---- within-race (relative) aggregates ------------------------------- #
    gr = df.groupby("race_id", observed=True)
    df["field_size"] = gr["horse_id"].transform("size").astype(float)
    df["rating_vs_field"] = df["or_"] - gr["or_"].transform("median")
    df["weight_vs_field"] = df["weight_lbs"] - gr["weight_lbs"].transform("mean")
    df["draw_pct"] = np.where(df["ran"] > 1, (df["draw"] - 1) / (df["ran"] - 1), 0.5)

    # ---- per-horse history (expanding / rolling, shifted) ---------------- #
    gh = df.groupby("horse_id", observed=True)
    df["runs_career"] = gh.cumcount().astype(float)
    df["days_since_run"] = (df["date"] - gh["date"].shift(1)).dt.days
    df["days_since_run"] = df["days_since_run"].fillna(180).clip(0, 400)

    wins_before = gh["won"].cumsum() - df["won"]
    df["win_pct_career"] = wins_before / df["runs_career"].replace(0, np.nan)
    placed = (df["pos_num"] <= 3).astype(float)
    place_before = gh.apply(lambda x: x["pos_num"].le(3).astype(float).cumsum(),
                            include_groups=False).reset_index(level=0, drop=True)
    df["place_pct_career"] = (place_before - placed) / df["runs_career"].replace(0, np.nan)
    df["win_pct_career"] = df["win_pct_career"].fillna(base_win)
    df["place_pct_career"] = df["place_pct_career"].fillna(3 * base_win)

    df["last_pos"] = gh["pos_fill"].shift(1)
    prev_pos = gh["pos_fill"].shift(1)
    df["avg_pos_3"] = prev_pos.groupby(df["horse_id"], observed=True) \
        .transform(lambda s: s.rolling(3, min_periods=1).mean())
    df["form_momentum"] = df["avg_pos_3"] - df["last_pos"]     # +ve => improving

    df["rpr_last"] = gh["rpr"].shift(1)
    prev_rpr = gh["rpr"].shift(1)
    df["rpr_best3"] = prev_rpr.groupby(df["horse_id"], observed=True) \
        .transform(lambda s: s.rolling(3, min_periods=1).max())
    prev_ts = gh["ts"].shift(1)
    df["ts_best3"] = prev_ts.groupby(df["horse_id"], observed=True) \
        .transform(lambda s: s.rolling(3, min_periods=1).max())

    # suitability: today's conditions vs this horse's recent norms (past only)
    df["dist_delta"] = df["distance_f"] - gh["distance_f"].transform(
        lambda s: s.shift(1).expanding().mean())
    df["going_delta"] = df["going_soft"] - gh["going_soft"].transform(
        lambda s: s.shift(1).expanding().mean())
    df["class_delta"] = df["race_class"] - gh["race_class"].transform(
        lambda s: s.shift(1).expanding().mean())

    # first-time headgear (present now, absent last run)
    hg_now = df["headgear"].fillna("").astype(str).str.strip().ne("")
    hg_prev = gh["headgear"].shift(1).fillna("").astype(str).str.strip().ne("")
    df["headgear_first"] = (hg_now & ~hg_prev).astype(float)

    # ---- context win rates (leakage-safe) -------------------------------- #
    df["dist_bucket"] = (df["distance_f"] // 2).astype(int)
    df["going_bucket"] = df["going_soft"].round().astype(int)
    df["course_win_pct"] = _shrunk_strike_rate(df, ["horse_id", "course"], base_win)
    df["dist_win_pct"] = _shrunk_strike_rate(df, ["horse_id", "dist_bucket"], base_win)
    df["going_win_pct"] = _shrunk_strike_rate(df, ["horse_id", "going_bucket"], base_win)

    # ---- connections strike rates ---------------------------------------- #
    df["jockey_sr"] = _shrunk_strike_rate(df, ["jockey_id"], base_win)
    df["trainer_sr"] = _shrunk_strike_rate(df, ["trainer_id"], base_win)
    df["sire_sr"] = _shrunk_strike_rate(df, ["sire"], base_win)
    df["trainer_jockey_sr"] = _shrunk_strike_rate(df, ["trainer_id", "jockey_id"], base_win)
    df["trainer_course_sr"] = _shrunk_strike_rate(df, ["trainer_id", "course"], base_win)

    # course/draw bias over time (leakage-safe expanding)
    df["draw_bias"] = _shrunk_strike_rate(df, ["course", "draw"], base_win)

    # ---- fill remaining gaps --------------------------------------------- #
    for c in ["or_", "rpr", "ts", "rpr_last", "rpr_best3", "ts_best3"]:
        df[c] = df[c].fillna(gr[c].transform("median") if c in ("or_", "rpr", "ts")
                             else df[c].median())
        df[c] = df[c].fillna(df[c].median())
    df["last_pos"] = df["last_pos"].fillna(df["ran"])
    df["avg_pos_3"] = df["avg_pos_3"].fillna(df["ran"])
    df["form_momentum"] = df["form_momentum"].fillna(0.0)
    for c in ["dist_delta", "going_delta", "class_delta"]:
        df[c] = df[c].fillna(0.0)

    # guarantee all model features exist and are finite
    for c in FEATURES:
        if c == "code":
            continue
        if c not in df.columns:
            raise KeyError(f"feature '{c}' was not constructed")
        df[c] = pd.to_numeric(df[c], errors="coerce").replace([np.inf, -np.inf], np.nan)
        df[c] = df[c].fillna(df[c].median() if df[c].notna().any() else 0.0)

    if verbose:
        print(f"built {len(FEATURES)} features on {len(df):,} runner-rows")
    return df
