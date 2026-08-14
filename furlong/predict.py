"""Turn a trained model + engineered features into a betting-ready prediction
table: win probability, fair odds, place/EW probabilities, value edge vs the
market, and a per-race ranked tipsheet.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .model import RaceModel
from .placesim import add_place_probs
from .utils import odds_to_prob, prob_to_odds, remove_overround

# Value-flag guardrails. A bet is only flagged as "value" when the modelled edge
# clears the threshold AND the selection is plausible — we ignore huge-priced
# longshots where model noise, not genuine edge, produces most false positives.
VALUE_THRESHOLD = 0.05      # min expected value per £1 win stake
VALUE_MIN_PROB = 0.04       # ignore <4% shots
VALUE_MAX_PRICE = 26.0      # ignore prices longer than 25/1


def predict(model: RaceModel, feats: pd.DataFrame, sims: int = 8000) -> pd.DataFrame:
    pred = model.predict_win(feats)
    pred = add_place_probs(pred, sims=sims)

    pred["fair_odds"] = prob_to_odds(pred["p_win"].to_numpy())

    # market probability (overround-removed) from available price, if any
    if "sp_dec" in pred.columns and pred["sp_dec"].notna().any():
        # index-safe overround removal per race
        mp = pred.groupby("race_id").apply(
            lambda g: pd.Series(remove_overround(odds_to_prob(g["sp_dec"].to_numpy())),
                                index=g.index), include_groups=False)
        pred["market_prob"] = mp.reset_index(level=0, drop=True)
    else:
        pred["sp_dec"] = np.nan
        pred["market_prob"] = np.nan

    price = pred["sp_dec"].to_numpy()
    pwin = pred["p_win"].to_numpy()
    pred["edge"] = pred["p_win"] - pred["market_prob"]
    pred["ev_win"] = pwin * price - 1.0

    # each-way EV (half win / half place at the place fraction)
    frac = pred["ew_fraction"].to_numpy()
    place_price = 1.0 + (price - 1.0) * frac
    ev_ew = 0.5 * (pwin * price - 1.0) + 0.5 * (pred["p_place"].to_numpy() * place_price - 1.0)
    pred["ev_ew"] = np.where(pred["ew_places"] > 1, ev_ew, np.nan)

    plausible = (pred["sp_dec"].notna() & (pred["p_win"] >= VALUE_MIN_PROB)
                 & (pred["sp_dec"] <= VALUE_MAX_PRICE))
    pred["value_win"] = (pred["ev_win"] > VALUE_THRESHOLD) & plausible
    pred["value_ew"] = (pred["ev_ew"] > VALUE_THRESHOLD) & plausible

    # rank within race by win probability (1 = model's top pick)
    pred["rank"] = pred.groupby("race_id")["p_win"].rank(ascending=False,
                                                         method="first").astype(int)
    pred = pred.sort_values(["date", "course", "race_id", "rank"])
    return pred


PRED_COLS = ["date", "course", "race_id", "race_type", "distance_f", "going",
             "ran", "is_handicap", "rank", "horse", "draw", "or_", "rpr",
             "p_win", "fair_odds", "sp_dec", "p_place", "ew_places",
             "edge", "ev_win", "ev_ew", "value_win", "value_ew"]


def tidy(pred: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in PRED_COLS if c in pred.columns]
    return pred[cols].reset_index(drop=True)
