"""Render the daily predictions as a single self-contained HTML dashboard.

Colours follow the validated data-viz reference palette: a single blue
sequential hue for the win-probability bars (magnitude), the fixed status green
for value flags (state, always paired with a label — never colour alone), and
the palette's ink/surface tokens with a real dark mode.
"""
from __future__ import annotations

import html
from datetime import datetime

import numpy as np
import pandas as pd

from .utils import fmt_odds

_CSS = """
:root{
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e;
  --muted:#898781; --grid:#e1e0d9; --border:rgba(11,11,11,.10);
  --blue:#2a78d6; --blue-soft:#cde2fb; --good:#0ca30c; --good-ink:#006300;
  --warn:#fab219; --chip:#f0efec;
  color-scheme:light;
}
:root[data-theme="dark"]{
  --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7;
  --muted:#898781; --grid:#2c2c2a; --border:rgba(255,255,255,.10);
  --blue:#3987e5; --blue-soft:#184f95; --good:#0ca30c; --good-ink:#0ca30c;
  --warn:#fab219; --chip:#26261f; color-scheme:dark;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7;
  --muted:#898781; --grid:#2c2c2a; --border:rgba(255,255,255,.10);
  --blue:#3987e5; --blue-soft:#184f95; --good:#0ca30c; --good-ink:#0ca30c;
  --chip:#26261f; color-scheme:dark;}}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:15px;line-height:1.45}
.wrap{max-width:1080px;margin:0 auto;padding:24px 20px 80px}
header{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;
  flex-wrap:wrap;margin-bottom:8px}
h1{font-size:24px;margin:0 0 2px}
.sub{color:var(--ink2);font-size:13px}
.toggle{border:1px solid var(--border);background:var(--surface);color:var(--ink2);
  border-radius:8px;padding:7px 12px;cursor:pointer;font-size:13px}
.tiles{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0 26px}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:14px 18px;min-width:120px}
.tile .n{font-size:26px;font-weight:650;font-variant-numeric:tabular-nums}
.tile .l{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
h2{font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;
  margin:30px 0 10px;border-bottom:1px solid var(--grid);padding-bottom:6px}
.meeting{margin-top:26px}
.meeting h3{font-size:19px;margin:0 0 4px}
.race{background:var(--surface);border:1px solid var(--border);border-radius:14px;
  padding:14px 16px;margin:12px 0}
.race .rh{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;
  align-items:baseline;margin-bottom:8px}
.race .rt{font-weight:600}
.race .rm{color:var(--muted);font-size:12.5px}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;color:var(--muted);font-weight:500;font-size:11.5px;
  text-transform:uppercase;letter-spacing:.03em;padding:4px 8px;border-bottom:1px solid var(--grid)}
td{padding:6px 8px;border-bottom:1px solid var(--grid);font-variant-numeric:tabular-nums}
tr:last-child td{border-bottom:none}
.top td{background:color-mix(in srgb,var(--blue) 7%,transparent)}
.horse{font-weight:600;font-variant-numeric:normal}
.num{text-align:right}
.bar{position:relative;height:16px;background:var(--chip);border-radius:4px;min-width:90px}
.bar>span{position:absolute;left:0;top:0;bottom:0;background:var(--blue);border-radius:4px}
.barlab{font-size:12px;color:var(--ink2);margin-left:6px;font-variant-numeric:tabular-nums}
.pill{display:inline-flex;align-items:center;gap:4px;font-size:11px;font-weight:600;
  padding:2px 7px;border-radius:20px;white-space:nowrap}
.pill.value{background:color-mix(in srgb,var(--good) 16%,transparent);color:var(--good-ink)}
.pill.ew{background:color-mix(in srgb,var(--warn) 20%,transparent);color:var(--ink2)}
.muted{color:var(--muted)}
.shortlist td{border-bottom:1px solid var(--grid)}
.disclaimer{margin-top:40px;font-size:12px;color:var(--muted);border-top:1px solid var(--grid);
  padding-top:14px}
footer{margin-top:24px;font-size:12px;color:var(--muted)}
a{color:var(--blue)}
"""

_JS = """
function tgl(){var r=document.documentElement;
var d=r.getAttribute('data-theme')==='dark'||(!r.getAttribute('data-theme')&&
matchMedia('(prefers-color-scheme:dark)').matches);
r.setAttribute('data-theme',d?'light':'dark');}
"""


def _esc(x) -> str:
    return html.escape(str(x)) if x is not None else ""


def _fmt_dist(f):
    try:
        f = float(f)
    except Exception:
        return "—"
    whole = int(f)
    half = f - whole
    frac = {0.0: "", 0.5: "½"}.get(round(half, 1), "")
    return f"{whole}{frac}f"


def _pill(row) -> str:
    out = []
    if row.get("value_win"):
        out.append(f'<span class="pill value">▲ VALUE +{row["ev_win"]*100:.0f}%</span>')
    elif row.get("value_ew"):
        out.append(f'<span class="pill ew">EW value +{row["ev_ew"]*100:.0f}%</span>')
    return " ".join(out)


def _race_card(g: pd.DataFrame) -> str:
    r0 = g.iloc[0]
    hcap = "Handicap " if r0.get("is_handicap") else ""
    head = (f'<div class="rh"><span class="rt">{_esc(r0["course"])} — '
            f'{hcap}{_esc(r0["race_type"])}</span>'
            f'<span class="rm">{_fmt_dist(r0["distance_f"])} · {_esc(r0["going"])} · '
            f'{int(r0["ran"])} runners</span></div>')

    pmax = max(g["p_win"].max(), 1e-6)
    rows = []
    for _, r in g.iterrows():
        w = r["p_win"] / pmax * 100
        top = " top" if r["rank"] == 1 else ""
        price = fmt_odds(r["sp_dec"]) if pd.notna(r.get("sp_dec")) else "—"
        pl = f'{r["p_place"]*100:.0f}%' if pd.notna(r.get("p_place")) else "—"
        rows.append(
            f'<tr class="{top.strip()}">'
            f'<td class="num muted">{int(r["rank"])}</td>'
            f'<td class="horse">{_esc(r["horse"])}</td>'
            f'<td class="num muted">{"" if pd.isna(r.get("draw")) else int(r["draw"])}</td>'
            f'<td class="num muted">{"" if pd.isna(r.get("or_")) else int(r["or_"])}</td>'
            f'<td><div style="display:flex;align-items:center">'
            f'<div class="bar"><span style="width:{w:.0f}%"></span></div>'
            f'<span class="barlab">{r["p_win"]*100:.1f}%</span></div></td>'
            f'<td class="num">{fmt_odds(r["fair_odds"])}</td>'
            f'<td class="num muted">{price}</td>'
            f'<td class="num muted">{pl}</td>'
            f'<td>{_pill(r)}</td>'
            '</tr>')
    table = (
        '<table><thead><tr>'
        '<th class="num">#</th><th>Horse</th><th class="num">Dr</th>'
        '<th class="num">OR</th><th>Win%</th><th class="num">Fair</th>'
        '<th class="num">SP</th><th class="num">Plc%</th><th></th>'
        '</tr></thead><tbody>' + "".join(rows) + '</tbody></table>')
    return f'<div class="race">{head}{table}</div>'


def render(pred: pd.DataFrame, out_path, generated_at: datetime | None = None,
           title: str = "Furlong — Racing Predictions") -> str:
    generated_at = generated_at or datetime.now()
    pred = pred.sort_values(["course", "race_id", "rank"])
    day = pred["date"].iloc[0] if len(pred) else generated_at
    day_str = pd.to_datetime(day).strftime("%A %d %B %Y")

    n_races = pred["race_id"].nunique()
    n_meet = pred["course"].nunique()
    n_run = len(pred)
    val = pred[pred.get("value_win", False) | pred.get("value_ew", False)] \
        if "value_win" in pred.columns else pred.iloc[0:0]

    tiles = "".join(
        f'<div class="tile"><div class="n">{n}</div><div class="l">{l}</div></div>'
        for n, l in [(n_meet, "Meetings"), (n_races, "Races"),
                     (n_run, "Runners"), (len(val), "Value bets")])

    # value shortlist
    short = ""
    if len(val):
        vr = val.sort_values("ev_win", ascending=False)
        rows = "".join(
            f'<tr><td class="horse">{_esc(r["horse"])}</td>'
            f'<td class="muted">{_esc(r["course"])}</td>'
            f'<td class="muted">{_fmt_dist(r["distance_f"])}</td>'
            f'<td class="num">{r["p_win"]*100:.1f}%</td>'
            f'<td class="num">{fmt_odds(r["fair_odds"])}</td>'
            f'<td class="num">{fmt_odds(r.get("sp_dec"))}</td>'
            f'<td>{_pill(r)}</td></tr>'
            for _, r in vr.iterrows())
        short = ('<h2>Value shortlist</h2><div class="race"><table class="shortlist">'
                 '<thead><tr><th>Horse</th><th>Course</th><th>Dist</th>'
                 '<th class="num">Win%</th><th class="num">Fair</th>'
                 '<th class="num">SP</th><th></th></tr></thead><tbody>'
                 + rows + '</tbody></table></div>')

    # meetings
    body = ""
    for course, gm in pred.groupby("course"):
        cards = "".join(_race_card(gr) for _, gr in gm.groupby("race_id"))
        body += f'<div class="meeting"><h3>{_esc(course)}</h3>{cards}</div>'

    disclaimer = (
        "Model estimates only. Win probabilities are calibrated on historical "
        "Racing Post data; place/each-way figures come from Monte-Carlo "
        "simulation of the win model; “Value” compares the model’s fair "
        "odds to the price shown and is not a guarantee of profit. Bet responsibly "
        "— 18+, begambleaware.org.")

    return_html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title><style>{_CSS}</style></head><body>
<div class="wrap">
<header><div><h1>{_esc(title)}</h1>
<div class="sub">{day_str} · generated {generated_at:%H:%M}</div></div>
<button class="toggle" onclick="tgl()">◐ Theme</button></header>
<div class="tiles">{tiles}</div>
{short}
<h2>All meetings</h2>
{body}
<div class="disclaimer">{disclaimer}</div>
<footer>Furlong v0.1 · built for personal use.</footer>
</div><script>{_JS}</script></body></html>"""

    with open(out_path, "w") as f:
        f.write(return_html)
    return str(out_path)
