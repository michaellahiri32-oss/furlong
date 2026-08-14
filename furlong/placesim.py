"""Place / each-way probabilities via Plackett-Luce Monte Carlo.

Given each runner's win probability, we sample many plausible finishing orders
(the Gumbel-max trick yields exact Plackett-Luce samples in one vectorised step)
and read off how often each horse lands in the top-k. This handles any field
size and any number of places, and correctly accounts for the fact that placing
depends on who *else* is fast.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import place_terms


def topk_probs(p_win: np.ndarray, max_k: int, sims: int = 8000,
               seed: int = 0) -> np.ndarray:
    """Return an (n_runners, max_k) array; column k-1 = P(finish in top k)."""
    p = np.clip(np.asarray(p_win, dtype=float), 1e-9, None)
    p = p / p.sum()
    n = len(p)
    max_k = min(max_k, n)
    rng = np.random.default_rng(seed)
    # Plackett-Luce via Gumbel: argsort(log p + Gumbel) ~ PL ordering
    g = rng.gumbel(size=(sims, n))
    keys = np.log(p)[None, :] + g
    order = np.argsort(-keys, axis=1)            # positions -> runner idx
    ranks = np.empty((sims, n), dtype=np.int32)
    cols = np.arange(n)
    ranks[np.arange(sims)[:, None], order] = cols  # runner idx -> finishing rank
    out = np.zeros((n, max_k))
    for k in range(1, max_k + 1):
        out[:, k - 1] = (ranks < k).mean(axis=0)
    return out


def add_place_probs(pred: pd.DataFrame, sims: int = 8000) -> pd.DataFrame:
    """Add p_place (each-way places), p_top2/3/4, and ew value columns per race."""
    pred = pred.copy()
    for col in ["p_place", "p_top2", "p_top3", "p_top4", "ew_places", "ew_fraction"]:
        pred[col] = np.nan

    for i, (rid, g) in enumerate(pred.groupby("race_id")):
        ran = int(g["ran"].iloc[0])
        is_hcap = bool(g["is_handicap"].iloc[0])
        n_places, frac = place_terms(ran, is_hcap)
        probs = topk_probs(g["p_win"].to_numpy(), max_k=4, sims=sims, seed=i)
        idx = g.index
        pred.loc[idx, "p_top2"] = probs[:, min(1, probs.shape[1] - 1)]
        pred.loc[idx, "p_top3"] = probs[:, min(2, probs.shape[1] - 1)]
        pred.loc[idx, "p_top4"] = probs[:, min(3, probs.shape[1] - 1)]
        pk = min(n_places, probs.shape[1])
        pred.loc[idx, "p_place"] = probs[:, pk - 1]
        pred.loc[idx, "ew_places"] = n_places
        pred.loc[idx, "ew_fraction"] = frac
    return pred
