"""Honest, time-ordered backtest.

Train on the past, test on the unseen future — never the other way round. We
report probabilistic accuracy (log loss, Brier), ranking accuracy (top-pick
strike rate vs the market favourite), calibration, and a flat-stake value-bet
ROI. The ROI figure is the least reliable number here and comes with caveats:
it uses starting price, ignores that you can't always get SP, and is sensitive
to the test window. Treat it as a sanity check, not a promise.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from .model import RaceModel
from .predict import predict


def _calibration_bins(y, p, n_bins=10):
    df = pd.DataFrame({"y": y, "p": p})
    df["bin"] = pd.cut(df["p"], np.linspace(0, df["p"].max() + 1e-9, n_bins + 1))
    g = df.groupby("bin", observed=True)
    out = g.agg(pred=("p", "mean"), obs=("y", "mean"), n=("y", "size")).dropna()
    return out.reset_index(drop=True)


def run(feats: pd.DataFrame, test_fraction: float = 0.2, sims: int = 4000) -> dict:
    feats = feats.sort_values("date")
    dates = feats["date"]
    cut_date = dates.quantile(1 - test_fraction)
    train = feats[dates < cut_date]
    test = feats[dates >= cut_date]

    model = RaceModel().fit(train)
    pred = predict(model, test, sims=sims)

    y = pred["won"].to_numpy(dtype=int)
    p = pred["p_win"].to_numpy(dtype=float)
    mkt = pred["market_prob"].to_numpy(dtype=float)

    metrics = {
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "test_races": int(pred["race_id"].nunique()),
        "train_period": f"{train['date'].min():%Y-%m-%d} → {train['date'].max():%Y-%m-%d}",
        "test_period": f"{test['date'].min():%Y-%m-%d} → {test['date'].max():%Y-%m-%d}",
        "log_loss": float(log_loss(y, np.clip(p, 1e-6, 1 - 1e-6))),
        "brier": float(brier_score_loss(y, p)),
        "auc": float(roc_auc_score(y, p)),
    }
    if np.isfinite(mkt).sum() > 100:
        m = np.isfinite(mkt)
        metrics["log_loss_market"] = float(log_loss(y[m], np.clip(mkt[m], 1e-6, 1 - 1e-6)))
        metrics["auc_market"] = float(roc_auc_score(y[m], mkt[m]))

    # ranking: does the model's top pick win more than the market favourite?
    tops = pred[pred["rank"] == 1]
    metrics["model_top_strike"] = float(tops["won"].mean())
    if pred["market_prob"].notna().any():
        fav = pred.loc[pred.groupby("race_id")["market_prob"].idxmax().dropna()]
        metrics["market_fav_strike"] = float(fav["won"].mean())

    # flat-stake value betting on SP (win + each-way)
    vb = pred[pred["value_win"]]
    if len(vb):
        profit = np.where(vb["won"] == 1, vb["sp_dec"] - 1.0, -1.0)
        metrics["value_bets"] = int(len(vb))
        metrics["value_strike"] = float((vb["won"] == 1).mean())
        metrics["value_roi_pct"] = float(profit.mean() * 100)
        metrics["value_avg_price"] = float(vb["sp_dec"].mean())

    metrics["_calibration"] = _calibration_bins(y, p)
    metrics["_predictions"] = pred
    return metrics


def print_report(m: dict):
    print("\n" + "=" * 62)
    print("  FURLONG BACKTEST")
    print("=" * 62)
    print(f"  Train : {m['train_rows']:>7,} runners   {m['train_period']}")
    print(f"  Test  : {m['test_rows']:>7,} runners   {m['test_period']}")
    print(f"  Races tested: {m['test_races']:,}")
    print("-" * 62)
    print(f"  Log loss (model) : {m['log_loss']:.4f}"
          + (f"   market: {m['log_loss_market']:.4f}" if "log_loss_market" in m else ""))
    print(f"  Brier score      : {m['brier']:.4f}")
    print(f"  AUC (model)      : {m['auc']:.4f}"
          + (f"   market: {m['auc_market']:.4f}" if "auc_market" in m else ""))
    print("-" * 62)
    print(f"  Model top-pick strike : {m['model_top_strike']*100:5.1f}%"
          + (f"   market fav: {m['market_fav_strike']*100:.1f}%"
             if "market_fav_strike" in m else ""))
    if "value_bets" in m:
        print(f"  Value bets (SP)  : {m['value_bets']:,} bets, "
              f"{m['value_strike']*100:.1f}% strike, "
              f"avg price {m['value_avg_price']:.2f}")
        print(f"  Flat-stake ROI   : {m['value_roi_pct']:+.1f}%   "
              f"(SP, illustrative — see caveats)")
    print("-" * 62)
    print("  Calibration (predicted vs observed win rate):")
    for _, r in m["_calibration"].iterrows():
        bar = "#" * int(r["obs"] * 60)
        print(f"    pred {r['pred']*100:5.1f}%  obs {r['obs']*100:5.1f}%  "
              f"(n={int(r['n']):>4})  {bar}")
    print("=" * 62 + "\n")
