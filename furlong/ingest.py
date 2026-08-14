"""Ingestion: turn rpscrape output into the canonical schema.

rpscrape (https://github.com/joenano/rpscrape) is the data source. Its exact
column names vary a little by version, so `normalise()` maps defensively and
fills anything missing. The two stable entry points you'll actually call:

    build_results_dataset(csv_dir)  -> data/processed/results.parquet   (history)
    load_racecard(path)             -> canonical rows for today's cards  (no result)

`fetch_results()` / `fetch_racecards()` shell out to your local rpscrape clone;
if your version's CLI differs, run rpscrape yourself and point the loaders at the
CSV/JSON it produces — the normaliser is the part that matters.
"""
from __future__ import annotations

import glob
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .config import PROCESSED, RAW, RPSCRAPE_DIR, SCHEMA
from .utils import get_logger

log = get_logger()

# rpscrape column name -> canonical name (any subset may be present)
_COLMAP = {
    "date": "date", "course": "course", "type": "race_type",
    "class": "race_class", "dist_f": "distance_f", "going": "going",
    "ran": "ran", "prize": "prize", "num": "draw", "draw": "draw",
    "pos": "pos", "horse": "horse", "age": "age", "sex": "sex",
    "lbs": "weight_lbs", "hg": "headgear", "dec": "sp_dec", "sp_dec": "sp_dec",
    "jockey": "jockey", "trainer": "trainer", "or": "or_", "rpr": "rpr",
    "ts": "ts", "sire": "sire", "race_name": "race_name", "pattern": "pattern",
    "horse_id": "horse_id", "jockey_id": "jockey_id", "trainer_id": "trainer_id",
}

_JUMP_TYPES = {"hurdle", "chase", "nh flat", "national hunt flat", "bumper",
               "nhf", "n_h flat"}


def _to_furlongs(v) -> float:
    """Accept 12.0, '12', '1m2f', '1m', '6f', '2m4½f' → furlongs."""
    if pd.isna(v):
        return np.nan
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().lower().replace("½", ".5")
    if re.fullmatch(r"[0-9.]+", s):
        return float(s)
    miles = re.search(r"([0-9.]+)\s*m", s)
    furl = re.search(r"([0-9.]+)\s*f", s)
    total = 0.0
    if miles:
        total += float(miles.group(1)) * 8
    if furl:
        total += float(furl.group(1))
    return total or np.nan


def _classify_code(race_type: str) -> str:
    t = str(race_type).strip().lower()
    return "jumps" if any(k in t for k in _JUMP_TYPES) else "flat"


def _stable_id(series: pd.Series, prefix: str) -> pd.Series:
    """Deterministic id from a name when rpscrape gives none."""
    return prefix + series.fillna("unknown").astype(str).map(
        lambda s: format(abs(hash(s)) % (10 ** 8), "08d"))


def normalise(raw: pd.DataFrame, is_racecard: bool = False) -> pd.DataFrame:
    df = raw.rename(columns={c: _COLMAP[c] for c in raw.columns if c in _COLMAP}).copy()

    df["date"] = pd.to_datetime(df.get("date"), errors="coerce")
    df["course"] = df.get("course", "Unknown").astype(str)
    df["race_type"] = df.get("race_type", "Flat").astype(str)
    df["code"] = df["race_type"].map(_classify_code)
    df["distance_f"] = df.get("distance_f").map(_to_furlongs) if "distance_f" in df \
        else np.nan
    df["going"] = df.get("going", "Good").astype(str)
    df["race_class"] = pd.to_numeric(df.get("race_class"), errors="coerce")

    # handicap flag from any available text
    def _col(name):
        return df[name].astype(str) if name in df.columns \
            else pd.Series("", index=df.index)
    text = (_col("race_name") + " " + _col("pattern") + " " +
            df["race_type"].astype(str)).str.lower()
    df["is_handicap"] = text.str.contains("handicap|h'cap|hcap", regex=True)

    for c in ["draw", "age", "weight_lbs", "or_", "rpr", "ts", "ran", "prize",
              "sp_dec"]:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            df[c] = np.nan

    for c in ["horse", "jockey", "trainer", "sire", "sex", "headgear"]:
        col = df[c] if c in df.columns else pd.Series("", index=df.index)
        df[c] = col.astype(str).replace("nan", "")

    # ids
    if "horse_id" not in df:
        df["horse_id"] = _stable_id(df["horse"], "H")
    if "jockey_id" not in df:
        df["jockey_id"] = _stable_id(df["jockey"], "J")
    if "trainer_id" not in df:
        df["trainer_id"] = _stable_id(df["trainer"], "T")

    # race_id: use provided; else identify a race by the fields that are constant
    # within it (date, course, off-time, distance, type). Off-time is present in
    # real rpscrape data; the extra keys keep races distinct if it isn't.
    if "race_id" not in df.columns or df["race_id"].isna().all():
        off = _col("off")
        key = (df["date"].dt.strftime("%Y%m%d").fillna("na") + "|" +
               df["course"].astype(str) + "|" + off + "|" +
               df["distance_f"].round(1).astype(str) + "|" +
               df["race_type"].astype(str))
        df["race_id"] = "R" + key.map(
            lambda s: format(abs(hash(s)) % (10 ** 12), "012d"))

    # ran fallback from field count
    df["ran"] = df["ran"].fillna(df.groupby("race_id")["horse"].transform("size"))

    if is_racecard:
        df["pos"] = np.nan
        df["won"] = np.nan
    else:
        df["pos"] = df.get("pos")
        df["won"] = (pd.to_numeric(df["pos"], errors="coerce") == 1).astype(float)

    for c in SCHEMA:
        if c not in df:
            df[c] = np.nan
    keep = SCHEMA + (["off"] if "off" in df.columns else [])
    return df[keep].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Loaders
# --------------------------------------------------------------------------- #
def build_results_dataset(csv_dir: str | Path | None = None,
                          out=PROCESSED / "results.parquet") -> Path:
    """Read every rpscrape results CSV under csv_dir, normalise, concat, save."""
    csv_dir = Path(csv_dir) if csv_dir else RPSCRAPE_DIR / "data"
    files = glob.glob(str(csv_dir / "**" / "*.csv"), recursive=True)
    if not files:
        raise FileNotFoundError(
            f"No rpscrape CSVs under {csv_dir}. Run a fetch first (see README).")
    frames = []
    for f in files:
        try:
            frames.append(normalise(pd.read_csv(f, low_memory=False)))
        except Exception as e:  # noqa
            log.warning(f"skipping {Path(f).name}: {e}")
    df = pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=["race_id", "horse_id"])
    df = df.sort_values(["date", "race_id"]).reset_index(drop=True)
    df.to_parquet(out, index=False)
    log.info(f"results dataset: {len(df):,} runners, "
             f"{df['race_id'].nunique():,} races → {out}")
    return out


def load_racecard(path: str | Path) -> pd.DataFrame:
    """Load today's/tomorrow's cards from an rpscrape racecards JSON or CSV."""
    path = Path(path)
    if path.suffix == ".json":
        data = json.loads(path.read_text())
        rows = _flatten_racecard_json(data)
        raw = pd.DataFrame(rows)
    else:
        raw = pd.read_csv(path, low_memory=False)
    return normalise(raw, is_racecard=True)


def _flatten_racecard_json(data) -> list[dict]:
    """rpscrape racecards JSON is nested {course: {off: {race..., runners:[]}}}."""
    rows = []
    def walk(course, off, race):
        meta = {"course": course, "off": off,
                "race_name": race.get("race_name", race.get("name", "")),
                "race_type": race.get("type", race.get("race_type", "Flat")),
                "distance_f": race.get("dist_f", race.get("distance", "")),
                "going": race.get("going", ""), "date": race.get("date", ""),
                "race_class": race.get("class", "")}
        for r in race.get("runners", []):
            rows.append({**meta,
                         "horse": r.get("name", r.get("horse", "")),
                         "horse_id": r.get("horse_id"),
                         "draw": r.get("draw"), "age": r.get("age"),
                         "lbs": r.get("lbs", r.get("weight_lbs")),
                         "or": r.get("or"), "rpr": r.get("rpr"), "ts": r.get("ts"),
                         "jockey": r.get("jockey"), "trainer": r.get("trainer"),
                         "sire": r.get("sire"), "hg": r.get("headgear", ""),
                         "dec": r.get("odds", r.get("dec"))})
    if isinstance(data, dict):
        for course, offs in data.items():
            if not isinstance(offs, dict):
                continue
            for off, race in offs.items():
                if isinstance(race, dict):
                    walk(course, off, race)
    return rows


# --------------------------------------------------------------------------- #
# Optional: shell out to a local rpscrape clone
# --------------------------------------------------------------------------- #
def fetch_results(region="gb", years="2015-2024", code="flat") -> None:
    """Best-effort call to rpscrape.py. Adjust to your rpscrape version if needed."""
    script = RPSCRAPE_DIR / "scripts" / "rpscrape.py"
    if not script.exists():
        raise FileNotFoundError(f"rpscrape not found at {script}. Clone it first.")
    cmd = [sys.executable, str(script), "-r", region, "-y", years, "-t", code]
    log.info("running: " + " ".join(cmd))
    subprocess.run(cmd, cwd=RPSCRAPE_DIR, check=True)


def fetch_racecards(day="today") -> Path:
    """Best-effort call to rpscrape racecards.py; returns the JSON path."""
    script = RPSCRAPE_DIR / "scripts" / "racecards.py"
    if not script.exists():
        raise FileNotFoundError(f"racecards.py not found at {script}.")
    subprocess.run([sys.executable, str(script), day], cwd=RPSCRAPE_DIR, check=True)
    cards = sorted((RPSCRAPE_DIR / "racecards").glob("*.json"))
    if not cards:
        raise FileNotFoundError("rpscrape produced no racecard JSON.")
    dest = RAW / cards[-1].name
    dest.write_bytes(cards[-1].read_bytes())
    return dest
