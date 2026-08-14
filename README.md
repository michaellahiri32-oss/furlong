# Furlong — UK horse racing predictor & value finder

A local, automatic pipeline for **Flat and Jumps** UK racing. It scrapes Racing
Post data (via [rpscrape](https://github.com/joenano/rpscrape)), engineers
leakage‑safe form features, trains **calibrated** win models, derives
**place / each‑way** probabilities by simulation, flags **value** against the
market, and publishes a daily HTML dashboard — on a schedule, hands‑off.

> **For personal use.** Scraping Racing Post is against their terms of service,
> so keep this private and non‑commercial. Model outputs are estimates, not
> guarantees — see *Honest expectations* below. 18+, begambleaware.org.

---

## What you get for each race

- **Win probability** for every runner, **calibrated** so a 20% shot really wins
  ~20% of the time, and normalised to sum to 100% per race.
- **Fair odds** = 1 / win probability.
- **Place / each‑way probability** from a Plackett–Luce Monte‑Carlo of the win
  model, using the correct industry place terms for the field size.
- **Ranked tipsheet** per race (the model's 1‑2‑3…).
- **Value flags** — where the model's fair odds are shorter than the price on
  offer (with sensible guardrails so it doesn't chase noise longshots).

Flat and Jumps get **separate models**, because the drivers differ (draw/speed
vs stamina/jumping).

---

## Quick start

### 1. Install

```bash
cd furlong
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. See it work immediately (no scraping needed)

```bash
python scripts/demo.py
```

This generates realistic **synthetic** races, trains, runs a full time‑split
**backtest** (prints accuracy + calibration), and writes a sample dashboard to
`reports/sample_dashboard.html`. Open it in your browser. This is proof the
whole pipeline runs before you wire in real data.

### 3. Wire in real Racing Post data (rpscrape)

```bash
# clone rpscrape next to this project
git clone https://github.com/joenano/rpscrape ../rpscrape
pip install -r ../rpscrape/requirements.txt   # aiohttp, lxml, etc.
```

Point Furlong at it (only needed if you cloned elsewhere):

```bash
export RPSCRAPE_DIR=/full/path/to/rpscrape
```

**Fetch history** (results are your training data). Use rpscrape however you
like — by region, year range, and code. For example, from the rpscrape folder:

```bash
# inside rpscrape (see its README for exact syntax on your version)
python3 scripts/rpscrape.py -r gb -y 2015-2024 -t flat
python3 scripts/rpscrape.py -r gb -y 2015-2024 -t jumps
```

Then build the tidy dataset and train:

```bash
python -c "from furlong import ingest; ingest.build_results_dataset()"
python scripts/train.py            # builds features, backtests, trains, saves
```

`build_results_dataset()` reads **every** CSV under `rpscrape/data/**` and maps
it into Furlong's schema, so you can fetch as much history as you want and just
re‑run it. More history = better models; 5+ seasons of both codes is a good base.

### 4. Predict today's card

```bash
python scripts/run_daily.py --day today --open
```

It fetches today's racecard via rpscrape, builds each runner's form from your
history, predicts, and writes **`reports/index.html`** (plus a dated copy). If
your rpscrape version's racecard command differs, save its output and pass it in:

```bash
python scripts/run_daily.py --card /path/to/racecards.json
```

---

## Make it automatic (the point of the whole thing)

On **macOS** (launchd), from the project root:

```bash
bash automation/install_macos.sh
```

That schedules:

- **daily 08:00** — fetch today's card, predict, refresh `reports/index.html`
- **Sundays 06:00** — refresh results from rpscrape and retrain the models

Bookmark `reports/index.html` in your browser; it's rewritten in place every
morning, so it's always today's card. Logs go to `logs/furlong.log`. Remove the
schedule any time with `bash automation/uninstall_macos.sh`.

Prefer **cron** (or on Linux)? See `automation/crontab.example`.

Tip: to have it pop open automatically each morning, add `--open` in
`scripts/run_furlong.sh`, or point a browser‑start item at the file.

---

## Open it on your phone (the app)

Furlong ships as an **installable web app (PWA)**. The daily run publishes a
mobile site to **GitHub Pages**; you open it on Android and **Add to Home
Screen** to get an icon that launches full‑screen like a native app.

The app opens on a **branded landing page** with **Today** and **Tomorrow**
buttons. Each day shows its **cards split by course** plus a **Value shortlist**
link, and drills in: tap a course → its races → runners. Navigation (Home,
Today, Tomorrow, Value) lives in the **burger menu, top‑right**. It works offline
(shows the last cards it loaded). The pipeline publishes two data files —
`data.json` (today) and `data-tomorrow.json` (tomorrow); tomorrow appears once
declarations are out, usually the evening before.

### One‑time setup (≈5 minutes)

1. Create a **new GitHub repo** (e.g. `furlong`) — [github.com/new](https://github.com/new).
   Free GitHub Pages serves from a public repo; the URL is unguessable but public,
   and the only thing published is `docs/` (the app + today's predictions), never
   your data or code. Want it fully private? See *Keeping it private* below.
2. From the project folder, point it at your repo and push once:

   ```bash
   cd furlong
   git init && git add -A && git commit -m "furlong"
   git branch -M main
   git remote add origin https://github.com/<you>/furlong.git
   python scripts/publish_web.py        # builds docs/ and pushes
   git push -u origin main
   ```

3. On GitHub: **Settings → Pages → Build and deployment → Deploy from a branch**,
   choose **main** / **/docs**, Save. After a minute your app is live at
   `https://<you>.github.io/furlong/`.
4. Open that URL in **Chrome on your phone → ⋮ menu → Add to Home screen**. Done —
   tap the Furlong icon any time.

After this, the scheduled daily run (`run_furlong.sh`) calls
`run_daily.py --publish`, which regenerates `docs/data.json` and `git push`es it,
so the app shows the new card every morning with nothing for you to do. To test
publishing by hand: `python scripts/run_daily.py --card <file> --publish`.

### Keeping it private

Free GitHub Pages is public (albeit at an unguessable URL, and racing tips aren't
sensitive). If you'd rather it not be public: use **Cloudflare Pages** or
**Netlify** (both allow access controls / private deploys — point them at `docs/`),
or serve `docs/` from your Mac over **Tailscale** and open that address on your
phone. The app itself is identical; only the host changes.

---

## How the model works (and why it should be trustworthy)

**Features (leakage‑safe).** Every feature for a runner uses only information
available *before* that race: the big three ratings (OR, RPR, Topspeed) plus
recent bests, weight carried vs the field, draw and a course draw‑bias term,
days since last run, career and recent form (last position, 3‑run average,
momentum), suitability vs the horse's own norms (distance/going/class moves),
and time‑aware, Bayesian‑shrunk strike rates for jockey, trainer,
trainer×jockey, trainer×course and sire. Career and strike stats use expanding
windows that **exclude the current race**, so the backtest can't cheat.

**Model.** Gradient‑boosted trees (`HistGradientBoostingClassifier`) per code,
with **monotonic constraints** on clearly‑signed features (more ability can only
help; more weight / worse form can only hurt) to stop the booster fitting noise.

**Calibration.** Win scores are normalised within each race, then **isotonically
calibrated** on a held‑out *time* slice, so probabilities mean what they say.

**Places.** Given the win probabilities, we sample thousands of finishing orders
(Plackett–Luce via the Gumbel‑max trick) and read off top‑k frequencies — exact,
and correct for any field size.

**Value.** Because the market price is deliberately **not** a model input, the
fair odds are independent of the bookmaker, so comparing them is meaningful.
A selection is flagged only when the edge clears a threshold *and* it isn't an
implausible longshot.

### The backtest

`python scripts/backtest.py` trains on the past and tests on the unseen future,
reporting log loss and AUC (vs the market where price is available), Brier score,
top‑pick strike rate vs the market favourite, a calibration table, and a
flat‑stake value‑bet ROI.

---

## Honest expectations

Horse racing markets are **efficient** and hard to beat after costs. A good,
well‑calibrated model can match or slightly edge the market's *accuracy* and
find pockets of *value*, but:

- The **ROI** number in the backtest is the least reliable figure. It uses
  starting price (you can't always get SP), ignores commission/margins, and is
  sensitive to the test window. Treat it as a sanity check, not a forecast.
- **More and cleaner data** helps most. Feed it several seasons of both codes.
- Ratings‑poor runners (debutants, first‑time‑in‑UK) are inherently harder.

Use the win probabilities and value flags as **one input** to your own judgement.

---

## Project layout

```
furlong/
  furlong/            # library
    config.py         # paths, canonical schema, feature lists, EW terms
    ingest.py         # rpscrape → canonical schema (results + racecards)
    features.py       # leakage-safe, time-aware feature engineering
    model.py          # per-code GBM + isotonic calibration + normalisation
    placesim.py       # Plackett–Luce Monte-Carlo place/EW probabilities
    predict.py        # win%/fair odds/place%/value assembly
    backtest.py       # time-split evaluation + metrics
    report.py         # self-contained HTML dashboard (light/dark)
    webexport.py      # predictions → data.json for the phone app
    publish.py        # build docs/ + git push to GitHub Pages
    synth.py          # synthetic data generator (for the demo/tests)
  webapp/             # the PWA: index.html, manifest, service worker, icons
  docs/               # published site GitHub Pages serves (app + data.json)
  scripts/
    demo.py           # end-to-end validation on synthetic data
    train.py          # build features + backtest + train + save
    backtest.py       # evaluate on held-out future races
    run_daily.py      # fetch card → predict → dashboard + publish app
    publish_web.py    # deploy/redeploy the app to GitHub Pages
    run_furlong.sh    # wrapper used by the scheduler
  automation/         # launchd plists, install/uninstall, cron example
  data/               # raw/ processed/ models/  (gitignored)
  reports/            # generated dashboards
```

## Tuning knobs

- Value sensitivity: `VALUE_THRESHOLD`, `VALUE_MIN_PROB`, `VALUE_MAX_PRICE` in
  `furlong/predict.py`.
- Model strength/speed: the `HistGradientBoostingClassifier` args in
  `furlong/model.py` (`max_iter`, `learning_rate`, `min_samples_leaf`).
- Schedule times: the `StartCalendarInterval` blocks in the `automation/*.plist`
  templates (or the cron lines).
- Add live/exchange odds: drop them onto the racecard as `sp_dec` (or extend
  `predict.py`) and the value logic uses them automatically.
