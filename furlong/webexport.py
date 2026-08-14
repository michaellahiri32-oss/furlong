"""Export predictions to the JSON payload the mobile app (PWA) consumes.

Shape: the day → meetings (one per course) → races → runners, plus a
cross-card value shortlist and summary totals. The app is a static site; this
JSON is the only thing that changes each day.
"""
from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd

from .utils import fmt_distance, fmt_odds


def _num(x, default=None):
    if x is None or (isinstance(x, float) and not np.isfinite(x)) or pd.isna(x):
        return default
    return x


def _runner(r) -> dict:
    return {
        "rank": int(r["rank"]),
        "horse": str(r["horse"]),
        "draw": _num(int(r["draw"]) if pd.notna(r.get("draw")) else None),
        "or": _num(int(r["or_"]) if pd.notna(r.get("or_")) else None),
        "rpr": _num(int(r["rpr"]) if pd.notna(r.get("rpr")) else None),
        "p_win": round(float(r["p_win"]), 4),
        "fair": fmt_odds(r["fair_odds"]),
        "fair_dec": round(float(r["fair_odds"]), 2),
        "sp": fmt_odds(r["sp_dec"]) if pd.notna(r.get("sp_dec")) else None,
        "p_place": round(float(r["p_place"]), 3) if pd.notna(r.get("p_place")) else None,
        "value_win": bool(r.get("value_win", False)),
        "value_ew": bool(r.get("value_ew", False)),
        "ev_win": round(float(r["ev_win"]), 3) if pd.notna(r.get("ev_win")) else None,
        "ev_ew": round(float(r["ev_ew"]), 3) if pd.notna(r.get("ev_ew")) else None,
    }


def _race(rid, gr) -> dict:
    r0 = gr.iloc[0]
    gr = gr.sort_values("rank")
    off = str(r0["off"]) if "off" in gr.columns and pd.notna(r0.get("off")) else ""
    hcap = "Handicap " if r0.get("is_handicap") else ""
    n_val = int((gr.get("value_win", False) | gr.get("value_ew", False)).sum())
    return {
        "race_id": str(rid),
        "off": off,
        "title": f"{hcap}{r0['race_type']}".strip(),
        "distance": fmt_distance(r0["distance_f"]),
        "going": str(r0["going"]),
        "ran": int(r0["ran"]),
        "n_value": n_val,
        "runners": [_runner(r) for _, r in gr.iterrows()],
    }


def build_payload(pred: pd.DataFrame, generated_at: datetime | None = None) -> dict:
    generated_at = generated_at or datetime.now()
    day = pd.to_datetime(pred["date"].iloc[0]) if len(pred) else generated_at

    meetings = []
    for course, gm in pred.groupby("course"):
        races = [_race(rid, gr) for rid, gr in gm.groupby("race_id")]
        races.sort(key=lambda r: (r["off"] or "99:99", r["race_id"]))
        n_val = sum(r["n_value"] for r in races)
        meetings.append({
            "course": str(course),
            "going": races[0]["going"] if races else "",
            "n_races": len(races),
            "n_value": n_val,
            "first_off": races[0]["off"] if races else "",
            "races": races,
        })
    meetings.sort(key=lambda m: (m["first_off"] or "99:99", m["course"]))

    # value shortlist across the whole day, best edge first
    val = pred[(pred.get("value_win", False)) | (pred.get("value_ew", False))].copy() \
        if "value_win" in pred.columns else pred.iloc[0:0]
    shortlist = []
    if len(val):
        val = val.sort_values("ev_win", ascending=False)
        for _, r in val.iterrows():
            shortlist.append({
                "horse": str(r["horse"]), "course": str(r["course"]),
                "off": str(r.get("off", "")) if pd.notna(r.get("off", np.nan)) else "",
                "distance": fmt_distance(r["distance_f"]),
                "p_win": round(float(r["p_win"]), 4),
                "fair": fmt_odds(r["fair_odds"]),
                "sp": fmt_odds(r["sp_dec"]) if pd.notna(r.get("sp_dec")) else None,
                "ev_win": round(float(r["ev_win"]), 3) if pd.notna(r.get("ev_win")) else None,
                "value_win": bool(r.get("value_win", False)),
                "value_ew": bool(r.get("value_ew", False)),
            })

    return {
        "generated_at": generated_at.isoformat(timespec="minutes"),
        "generated_label": generated_at.strftime("%H:%M"),
        "date": day.strftime("%Y-%m-%d"),
        "day_label": day.strftime("%A %-d %B %Y"),
        "totals": {
            "meetings": int(pred["course"].nunique()),
            "races": int(pred["race_id"].nunique()),
            "runners": int(len(pred)),
            "value": int(len(val)),
        },
        "meetings": meetings,
        "value_shortlist": shortlist,
    }


def write_json(pred: pd.DataFrame, path, generated_at: datetime | None = None) -> str:
    payload = build_payload(pred, generated_at)
    with open(path, "w") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    return str(path)
