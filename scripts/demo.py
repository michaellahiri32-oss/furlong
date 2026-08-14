"""End-to-end validation on synthetic data (no scraping needed).

Proves the whole pipeline runs and is calibrated: generate realistic synthetic
races → engineer features → time-split backtest → train → predict the final day
as if it were a live racecard → publish a sample dashboard.

Usage:
    python scripts/demo.py
"""
import argparse
from datetime import datetime

import _bootstrap  # noqa
import pandas as pd

from furlong import backtest, features, synth
from furlong.config import REPORTS
from furlong.model import RaceModel
from furlong.predict import predict, tidy
from furlong.report import render
from furlong.utils import get_logger

log = get_logger()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=540)
    ap.add_argument("--races-per-day", type=int, default=12)
    args = ap.parse_args()

    log.info(f"generating synthetic data ({args.days} days)…")
    df = synth.generate(n_days=args.days, races_per_day=args.races_per_day)
    log.info(f"{len(df):,} runners across {df['race_id'].nunique():,} races "
             f"({df['code'].value_counts().to_dict()})")

    log.info("building features…")
    feats = features.build(df, verbose=True)

    log.info("running time-split backtest…")
    m = backtest.run(feats, test_fraction=0.2)
    backtest.print_report(m)

    # simulate a live day: hold out the final calendar day as a 'racecard'
    last_day = feats["date"].max()
    train = feats[feats["date"] < last_day]
    today = feats[feats["date"] == last_day].copy()
    log.info(f"training on history before {last_day:%Y-%m-%d}; "
             f"predicting {today['race_id'].nunique()} races on the day")
    model = RaceModel().fit(train)
    model.save()
    pred = predict(model, today)

    out = REPORTS / "sample_dashboard.html"
    render(pred, out, generated_at=datetime.now(),
           title="Furlong — Sample Predictions (synthetic demo)")
    log.info(f"sample dashboard → {out}")

    # quick peek at one race
    log.info("example race (model's ranking):")
    rid = pred["race_id"].iloc[0]
    one = pred[pred["race_id"] == rid].sort_values("rank")
    cols = ["rank", "horse", "p_win", "fair_odds", "sp_dec", "p_place", "value_win"]
    show = one[[c for c in cols if c in one.columns]].copy()
    show["p_win"] = (show["p_win"] * 100).round(1)
    show["p_place"] = (show["p_place"] * 100).round(0)
    print(show.to_string(index=False))


if __name__ == "__main__":
    main()
