"""The daily automatic pipeline: refresh cards → predict → publish the app.

By default it builds BOTH today's and tomorrow's cards and publishes both to the
phone app (data.json + data-tomorrow.json). Tomorrow is skipped gracefully if its
declarations aren't out yet.

Steps per day:
  1. Load historical results (data/processed/results.parquet).
  2. Get the racecard — via rpscrape, or a --card file you pass (applies to today).
  3. Build features on (history + card) so each runner has full form context.
  4. Predict, write the day's app payload, and (today) the desktop dashboard.

Usage:
    python scripts/run_daily.py --publish            # today + tomorrow → GitHub Pages
    python scripts/run_daily.py --days today
    python scripts/run_daily.py --card cards.json    # supply today's card manually
"""
import argparse
import webbrowser
from datetime import datetime

import _bootstrap  # noqa
import pandas as pd

from furlong import features, ingest, publish
from furlong.config import PROCESSED, REPORTS
from furlong.model import RaceModel
from furlong.predict import predict
from furlong.report import render
from furlong.utils import get_logger

log = get_logger()


def _predict_day(day, history, model, card_path=None):
    """Return a predictions DataFrame for a day, or None if no card available."""
    try:
        if card_path:
            card = ingest.load_racecard(card_path)
        else:
            card = ingest.load_racecard(ingest.fetch_racecards(day))
    except Exception as e:  # noqa
        log.warning(f"no {day} card ({e}); skipping")
        return None
    if not len(card):
        log.warning(f"{day} card is empty; skipping")
        return None
    log.info(f"{day}: {card['race_id'].nunique()} races, {len(card)} runners")
    union = pd.concat([history, card], ignore_index=True)
    feats = features.build(union)
    sub = feats[feats["race_id"].isin(set(card["race_id"]))].copy()
    return predict(model, sub)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(PROCESSED / "results.parquet"))
    ap.add_argument("--card", default=None,
                    help="path to a racecard JSON/CSV (used as TODAY's card)")
    ap.add_argument("--days", default="today,tomorrow",
                    help="comma list: today,tomorrow (default both)")
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--publish", action="store_true",
                    help="push the app + data to GitHub Pages")
    ap.add_argument("--no-app", action="store_true")
    args = ap.parse_args()

    days = [d.strip() for d in args.days.split(",") if d.strip()]
    log.info("loading history + model")
    history = pd.read_parquet(args.results)
    model = RaceModel.load()

    preds, total_val = {}, 0
    for day in days:
        card_path = args.card if (day == "today" and args.card) else None
        pred = _predict_day(day, history, model, card_path)
        if pred is None:
            continue
        preds[day] = pred
        total_val += int((pred.get("value_win", False) | pred.get("value_ew", False)).sum())

    if "today" in preds:
        out = REPORTS / "index.html"
        render(preds["today"], out, generated_at=datetime.now())
        log.info(f"desktop dashboard → {out}")

    if not args.no_app and preds:
        written = publish.publish_days(preds, push=args.publish,
                                       generated_at=datetime.now())
        log.info(f"published {len(written)} day(s) → phone app"
                 + ("  (pushed to GitHub Pages)" if args.publish else ""))
    log.info(f"{total_val} value selections flagged across {len(preds)} day(s)")

    if args.open and "today" in preds:
        webbrowser.open(f"file://{REPORTS / 'index.html'}")


if __name__ == "__main__":
    main()
