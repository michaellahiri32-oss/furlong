"""Fast sanity checks. Run:  python tests/test_pipeline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from furlong import features, synth
from furlong.config import FEATURES
from furlong.placesim import topk_probs


def test_features_complete_and_finite():
    df = synth.generate(n_days=60, races_per_day=6)
    f = features.build(df)
    for c in FEATURES:
        if c == "code":
            continue
        assert c in f.columns, f"missing {c}"
        assert np.isfinite(f[c]).all(), f"non-finite in {c}"
    print("PASS features complete & finite")


def test_no_target_leakage():
    """career win% on a horse's k-th run must use only its first k-1 runs."""
    df = synth.generate(n_days=120, races_per_day=6)
    f = features.build(df).sort_values(["horse_id", "date"])
    # pick a horse with several runs
    counts = f.groupby("horse_id").size()
    hid = counts[counts >= 5].index[0]
    g = f[f["horse_id"] == hid].sort_values("date")
    wins = g["won"].to_numpy()
    got = g["win_pct_career"].to_numpy()
    runs = g["runs_career"].to_numpy()
    # for runs>=1, expected = mean of prior wins (excludes current)
    for i in range(1, len(g)):
        expected = wins[:i].mean()
        assert abs(got[i] - expected) < 1e-9, (i, got[i], expected)
    assert runs[0] == 0
    print("PASS no target leakage in career win%")


def test_place_sim_invariants():
    p = np.array([0.4, 0.25, 0.15, 0.1, 0.06, 0.04])
    out = topk_probs(p, max_k=4, sims=20000, seed=1)
    # column 0 == P(win) should match input within MC noise
    assert np.allclose(out[:, 0], p, atol=0.02), out[:, 0]
    # top-k monotonic non-decreasing in k, bounded by 1
    for i in range(len(p)):
        row = out[i]
        assert np.all(np.diff(row) >= -1e-9), row
        assert row.max() <= 1.0 + 1e-9
    # exactly k horses fill the top-k in expectation: column sums to k
    for k in range(1, 5):
        assert abs(out[:, k - 1].sum() - k) < 0.05, (k, out[:, k - 1].sum())
    print("PASS place-sim invariants")


if __name__ == "__main__":
    test_features_complete_and_finite()
    test_no_target_leakage()
    test_place_sim_invariants()
    print("\nALL TESTS PASSED")
