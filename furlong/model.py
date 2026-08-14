"""Win model: gradient-boosted probabilities, isotonic calibration, and
within-race normalisation. One model per code (Flat / Jumps).

Design choices that matter for accuracy:
  * Separate Flat and Jumps models — the drivers genuinely differ.
  * Monotonic constraints on clearly-signed ability features (higher rating can
    only help; more weight / worse recent form can only hurt) — this stops the
    booster inventing non-sensical wiggles from noise and improves calibration.
  * Probabilities are normalised so each race sums to 1, and THEN isotonically
    calibrated on a held-out time slice — calibrating post-normalisation is what
    corrects the favourite-shrinkage you get if you calibrate the raw scores.
  * The market price is NOT a feature — predictions are independent of the odds,
    which is what makes the value comparison meaningful.
"""
from __future__ import annotations

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression

from .config import MODELS, NUMERIC_FEATURES, CODES

# Sign of the monotonic relationship with P(win); 0 = unconstrained.
_MONOTONIC = {
    "or_": 1, "rpr": 1, "ts": 1, "rpr_last": 1, "rpr_best3": 1, "ts_best3": 1,
    "rating_vs_field": 1, "win_pct_career": 1, "place_pct_career": 1,
    "jockey_sr": 1, "trainer_sr": 1, "trainer_jockey_sr": 1, "sire_sr": 1,
    "trainer_course_sr": 1, "course_win_pct": 1, "dist_win_pct": 1,
    "going_win_pct": 1, "form_momentum": 1,
    "weight_vs_field": -1, "last_pos": -1, "avg_pos_3": -1,
}


def _monotonic_vector():
    return [_MONOTONIC.get(f, 0) for f in NUMERIC_FEATURES]


def _new_estimator():
    return HistGradientBoostingClassifier(
        loss="log_loss",
        learning_rate=0.05,
        max_iter=450,
        max_leaf_nodes=31,
        min_samples_leaf=80,
        l2_regularization=1.0,
        monotonic_cst=_monotonic_vector(),
        early_stopping=True,
        validation_fraction=0.12,
        random_state=0,
    )


def _normalise_within_race(p: np.ndarray, race_id: pd.Series) -> np.ndarray:
    s = pd.Series(p, index=race_id.index).groupby(race_id).transform("sum")
    out = p / s.replace(0, np.nan).to_numpy()
    return np.nan_to_num(out, nan=0.0)


class RaceModel:
    """One estimator + one post-normalisation calibrator per race code."""

    def __init__(self):
        self.est: dict[str, HistGradientBoostingClassifier] = {}
        self.calib: dict[str, IsotonicRegression] = {}

    def _raw(self, code: str, df: pd.DataFrame) -> np.ndarray:
        X = df[NUMERIC_FEATURES].to_numpy(dtype=float)
        return np.clip(self.est[code].predict_proba(X)[:, 1], 1e-6, 1 - 1e-6)

    def fit(self, feats: pd.DataFrame):
        for code in CODES:
            sub = feats[feats["code"] == code].sort_values("date")
            if len(sub) < 1000:
                continue
            cut = int(len(sub) * 0.85)
            fit_part, cal_part = sub.iloc[:cut], sub.iloc[cut:]

            est = _new_estimator()
            est.fit(fit_part[NUMERIC_FEATURES].to_numpy(float),
                    fit_part["won"].to_numpy(int))
            self.est[code] = est

            # calibrate on the normalised probabilities of the held-out slice
            if len(cal_part) > 500 and cal_part["won"].sum() > 20:
                raw = self._raw(code, cal_part)
                p_norm = _normalise_within_race(raw, cal_part["race_id"])
                self.calib[code] = IsotonicRegression(out_of_bounds="clip").fit(
                    p_norm, cal_part["won"].to_numpy(int))

            # refit on all data for the shipped model
            est_full = _new_estimator()
            est_full.fit(sub[NUMERIC_FEATURES].to_numpy(float),
                         sub["won"].to_numpy(int))
            self.est[code] = est_full
        return self

    def predict_win(self, feats: pd.DataFrame) -> pd.DataFrame:
        out = feats.copy()
        out["p_win_raw"] = np.nan
        for code in self.est:
            mask = (out["code"] == code).to_numpy()
            if mask.any():
                out.loc[mask, "p_win_raw"] = self._raw(code, out.loc[mask])

        # rating-based fallback for any code without a trained model
        missing = out["p_win_raw"].isna()
        if missing.any():
            r = out.loc[missing, "rpr"].fillna(out["rpr"].median())
            out.loc[missing, "p_win_raw"] = np.exp((r - r.mean()) / 8.0)

        # normalise within race, then calibrate per code, then renormalise
        out["p_win"] = _normalise_within_race(out["p_win_raw"].to_numpy(),
                                              out["race_id"])
        for code, cal in self.calib.items():
            mask = (out["code"] == code).to_numpy()
            if mask.any():
                out.loc[mask, "p_win"] = cal.predict(out.loc[mask, "p_win"].to_numpy())
        # floor tiny probabilities (every runner has *some* chance) then renormalise
        out["p_win"] = np.clip(out["p_win"].to_numpy(), 0.002, None)
        out["p_win"] = _normalise_within_race(out["p_win"].to_numpy(), out["race_id"])
        return out

    # ---- persistence ---------------------------------------------------- #
    def save(self, path=None):
        path = path or (MODELS / "racemodel.joblib")
        joblib.dump(self, path)
        return path

    @staticmethod
    def load(path=None) -> "RaceModel":
        path = path or (MODELS / "racemodel.joblib")
        return joblib.load(path)

    @property
    def models(self):  # backwards-compat convenience
        return self.est
