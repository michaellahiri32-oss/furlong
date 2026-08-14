"""Synthetic race generator.

Produces data in the exact canonical schema that the real rpscrape ingestion
emits, so the whole pipeline (features -> model -> backtest -> report) can be
validated end-to-end without touching the live feed. There is genuine, learnable
signal (ratings track a latent ability; weight/going/draw/form nudge the result)
plus realistic noise, so calibration and backtest numbers are meaningful.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CODES

COURSES_FLAT = ["Ascot", "Newmarket", "York", "Goodwood", "Sandown", "Epsom",
                "Doncaster", "Kempton (AW)", "Lingfield (AW)", "Newcastle (AW)"]
COURSES_JUMP = ["Cheltenham", "Aintree", "Kempton", "Sandown", "Ascot",
                "Haydock", "Newbury", "Wetherby", "Ayr", "Exeter"]
GOINGS_TURF = ["Good to Firm", "Good", "Good to Soft", "Soft", "Heavy"]
GOINGS_AW = ["Standard", "Standard to Slow"]


def _make_population(rng, n_horses, n_jockeys, n_trainers, n_sires):
    horses = pd.DataFrame({
        "horse_id": [f"H{i:05d}" for i in range(n_horses)],
        "horse": [f"Horse {i}" for i in range(n_horses)],
        # latent ability on a ~OR scale (mean 70, sd 12)
        "ability": rng.normal(70, 12, n_horses),
        "pref_going": rng.uniform(2, 6, n_horses),      # preferred softness (see GOING_SCALE)
        "pref_dist": rng.uniform(5, 24, n_horses),      # preferred trip in furlongs
        "age": rng.integers(3, 10, n_horses),
        "sex": rng.choice(["G", "M", "F", "C", "H"], n_horses),
        "jockey_id": rng.integers(0, n_jockeys, n_horses),   # loose default pairing
        "trainer_id": rng.integers(0, n_trainers, n_horses),
        "sire_id": rng.integers(0, n_sires, n_horses),
    })
    jockey_skill = rng.normal(0, 3.0, n_jockeys)
    trainer_skill = rng.normal(0, 3.0, n_trainers)
    sire_skill = rng.normal(0, 2.0, n_sires)
    return horses, jockey_skill, trainer_skill, sire_skill


def generate(n_days=900, races_per_day=14, seed=7) -> pd.DataFrame:
    """Return a runner-level results DataFrame in the canonical schema."""
    rng = np.random.default_rng(seed)
    n_horses = 4000
    n_jockeys, n_trainers, n_sires = 120, 200, 150
    horses, jockey_skill, trainer_skill, sire_skill = _make_population(
        rng, n_horses, n_jockeys, n_trainers, n_sires)
    hz = horses.set_index("horse_id")

    start = pd.Timestamp("2022-01-01")
    rows = []
    race_counter = 0

    for d in range(n_days):
        date = start + pd.Timedelta(days=d)
        for _ in range(races_per_day):
            code = "flat" if rng.random() < 0.55 else "jumps"
            if code == "flat":
                course = rng.choice(COURSES_FLAT)
                aw = "(AW)" in course
                going_name = rng.choice(GOINGS_AW if aw else GOINGS_TURF)
                race_type = "Flat"
                distance_f = float(rng.choice([5, 6, 7, 8, 10, 12, 14, 16]))
            else:
                course = rng.choice(COURSES_JUMP)
                going_name = rng.choice(GOINGS_TURF)
                race_type = rng.choice(["Hurdle", "Chase", "NH Flat"], p=[.55, .35, .10])
                distance_f = float(rng.choice([16, 18, 20, 21, 24, 25, 28]))

            is_handicap = bool(rng.random() < 0.55)
            race_class = int(rng.integers(1, 8))
            going_soft = {"Good to Firm": 2, "Good": 3, "Good to Soft": 4,
                          "Soft": 5, "Heavy": 7, "Standard": 3,
                          "Standard to Slow": 4}[going_name]
            ran = int(rng.integers(5, 17)) if rng.random() < 0.85 else int(rng.integers(4, 24))

            field = hz.sample(ran, random_state=int(rng.integers(0, 1 << 31)))
            race_id = f"R{race_counter:07d}"
            race_counter += 1

            # --- true finishing merit ---
            merit = field["ability"].to_numpy().astype(float)
            merit += jockey_skill[field["jockey_id"].to_numpy()]
            merit += trainer_skill[field["trainer_id"].to_numpy()]
            merit += 0.5 * sire_skill[field["sire_id"].to_numpy()]
            # going & distance suitability (closer to preference = better)
            merit -= 1.2 * np.abs(field["pref_going"].to_numpy() - going_soft)
            merit -= 0.6 * np.abs(field["pref_dist"].to_numpy() - distance_f)
            # weight carried (lbs): higher-rated carry more in handicaps
            base_lbs = 126 if code == "flat" else 154
            if is_handicap:
                spread = (field["ability"].to_numpy() - field["ability"].mean())
                weight_lbs = np.round(base_lbs + spread * 0.6).astype(int)
                merit -= 0.10 * (weight_lbs - weight_lbs.mean())   # weight drags
            else:
                weight_lbs = np.full(ran, base_lbs) + rng.integers(-3, 4, ran)
            # draw bias on the flat (low draws slightly favoured at short trips)
            draw = np.arange(1, ran + 1)
            rng.shuffle(draw)
            if code == "flat" and distance_f <= 8:
                merit -= 0.15 * (draw - 1)
            # non-completion risk in jumps
            noncomp = np.zeros(ran, dtype=bool)
            if code == "jumps":
                noncomp = rng.random(ran) < 0.08
            merit += rng.normal(0, 6.0, ran)                     # race-day noise
            merit[noncomp] = -1e9

            order = np.argsort(-merit)
            pos = np.empty(ran, dtype=object)
            rank = np.empty(ran, dtype=int)
            rank[order] = np.arange(1, ran + 1)
            for i in range(ran):
                pos[i] = "PU" if noncomp[i] else str(int(rank[i]))
            won = np.array([1 if (not noncomp[i] and rank[i] == 1) else 0
                            for i in range(ran)])

            # --- observed ratings (noisy views of ability) ---
            abil = field["ability"].to_numpy()
            or_ = np.round(abil + rng.normal(0, 2.5, ran)).astype(int)
            rpr = np.round(abil + rng.normal(0, 4.0, ran)).astype(int)
            ts = np.round(abil + rng.normal(0, 6.0, ran)).astype(int)

            headgear = np.where(rng.random(ran) < 0.12,
                                rng.choice(["b", "v", "h", "t"], ran), "")
            # a plausible SP: shorter for higher merit, with overround
            strength = abil - abil.mean()
            sp_prob = np.exp(strength / 6.0)
            sp_prob = sp_prob / sp_prob.sum() * 1.20          # ~20% overround
            sp_dec = np.clip(1.0 / sp_prob, 1.1, 200).round(2)

            for i, (hid, hrow) in enumerate(field.iterrows()):
                rows.append({
                    "race_id": race_id, "date": date, "course": course,
                    "code": code, "race_type": race_type,
                    "is_handicap": is_handicap, "race_class": race_class,
                    "distance_f": distance_f, "going": going_name, "ran": ran,
                    "prize": float(rng.choice([3000, 5000, 8000, 15000, 40000])),
                    "horse_id": hid, "horse": hrow["horse"],
                    "pos": pos[i], "won": int(won[i]), "draw": int(draw[i]),
                    "age": int(hrow["age"]), "sex": hrow["sex"],
                    "weight_lbs": int(weight_lbs[i]),
                    "or_": int(or_[i]), "rpr": int(rpr[i]), "ts": int(ts[i]),
                    "jockey": f"Jockey {hrow['jockey_id']}",
                    "jockey_id": f"J{hrow['jockey_id']:04d}",
                    "trainer": f"Trainer {hrow['trainer_id']}",
                    "trainer_id": f"T{hrow['trainer_id']:04d}",
                    "sire": f"Sire {hrow['sire_id']}",
                    "headgear": headgear[i],
                    "sp_dec": float(sp_dec[i]),
                })

    df = pd.DataFrame(rows)
    return df.sort_values(["date", "race_id"]).reset_index(drop=True)


if __name__ == "__main__":
    d = generate(n_days=120, races_per_day=8)
    print(d.shape)
    print(d.head())
    print("codes:", d["code"].value_counts().to_dict())
