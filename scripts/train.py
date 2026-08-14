"""Train the Flat & Jumps win models from your historical results.

Usage:
    python scripts/train.py                 # uses data/processed/results.parquet
    python scripts/train.py --no-backtest   # skip the quick evaluation
"""
import argparse

import _bootstrap  # noqa
import pandas as pd

from furlong import backtest, features
from furlong.config import MODELS, PROCESSED
from furlong.model import RaceModel
from furlong.utils import get_logger

log = get_logger()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(PROCESSED / "results.parquet"))
    ap.add_argument("--no-backtest", action="store_true")
    args = ap.parse_args()

    log.info(f"loading {args.results}")
    df = pd.read_parquet(args.results)
    log.info(f"{len(df):,} runners; building features…")
    feats = features.build(df, verbose=True)

    if not args.no_backtest:
        backtest.print_report(backtest.run(feats))

    log.info("training on full history…")
    model = RaceModel().fit(feats)
    path = model.save()
    log.info(f"saved model → {path}")
    for code, m in model.models.items():
        log.info(f"  {code}: trained on this code")


if __name__ == "__main__":
    main()
