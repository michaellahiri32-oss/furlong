"""Evaluate the models on held-out future races.

Usage:
    python scripts/backtest.py
    python scripts/backtest.py --test-fraction 0.25
"""
import argparse

import _bootstrap  # noqa
import pandas as pd

from furlong import backtest, features
from furlong.config import PROCESSED
from furlong.utils import get_logger

log = get_logger()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(PROCESSED / "results.parquet"))
    ap.add_argument("--test-fraction", type=float, default=0.2)
    args = ap.parse_args()

    df = pd.read_parquet(args.results)
    feats = features.build(df, verbose=True)
    m = backtest.run(feats, test_fraction=args.test_fraction)
    backtest.print_report(m)


if __name__ == "__main__":
    main()
