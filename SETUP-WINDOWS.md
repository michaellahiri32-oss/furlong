# Furlong — Windows setup (step by step)

Follow these in order. There are four phases:

- **A. Install Python & Git** (one-time, ~5 min)
- **B. Get the app live on your phone** with the built-in sample data (~10 min)
- **C. Wire in real racing data** (rpscrape + train)
- **D. Automate it** so it updates every morning by itself

You have a GitHub account already, which is all you need for hosting.

Tip for opening a command window *inside a folder*: open the folder in File
Explorer, click the **address bar**, type `cmd`, and press **Enter**. A black
Command Prompt window opens already pointing at that folder.

---

## Phase A — Install Python and Git (one-time)

1. **Python** — go to <https://www.python.org/downloads/>, click the big
   "Download Python" button, run the installer. **On the first screen, tick
   "Add python.exe to PATH"**, then click "Install Now". (This tick is important.)
2. **Git** — go to <https://git-scm.com/download/win>, download and run the
   installer. Click Next through the defaults; nothing to change.
3. **Check both worked**: open a fresh Command Prompt (Start → type `cmd` →
   Enter) and run:

   ```
   python --version
   git --version
   ```

   You should see a version number for each. If `python` says "not recognized",
   close and reopen the Command Prompt; if it still fails, try `py --version`
   and use `py` wherever this guide says `python`.

---

## Phase B — Get the app onto your phone (sample data)

### B1. Put the project on your PC

1. Save `furlong.zip` somewhere easy, then **right-click → Extract All**.
2. Move the extracted **furlong** folder to your C: drive so its path is
   `C:\furlong`. The project root is the folder that directly contains
   `README.md` and `requirements.txt`. (If after extracting you have
   `C:\furlong\furlong\README.md`, move the inner folder up so it's
   `C:\furlong\README.md`.)

### B2. Install the app's Python bits

Open a Command Prompt in `C:\furlong` (address-bar `cmd` trick), then:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

The first line makes a private Python environment; the second switches into it
(you'll see `(.venv)` at the start of the line); the third installs what it
needs. **Keep this window open** — every later command assumes you've run
`.venv\Scripts\activate` in it first.

### B3. (Optional) preview the app on your PC first

```
cd docs
python -m http.server 8000
```

Open a browser to **http://localhost:8000** — you'll see the app with sample
data. Press **Ctrl+C** in the window to stop, then `cd ..` to go back up.

### B4. Publish it to GitHub Pages (this is what your phone opens)

1. In your browser, go to <https://github.com/new> and create a repo named
   **furlong**. Leave it **Public** (free GitHub Pages needs public; the URL is
   unguessable and only the `docs` folder is published — not your data). Don't
   add a README. Click **Create repository**.
2. Back in your Command Prompt (in `C:\furlong`, with `(.venv)` showing), run
   these **one at a time**, replacing `YOURNAME` with your GitHub username:

   ```
   git init
   git add -A
   git commit -m "furlong"
   git branch -M main
   git remote add origin https://github.com/YOURNAME/furlong.git
   git push -u origin main
   ```

   On the `git push` line a window will pop up asking you to **sign in to
   GitHub** — do that once and it remembers you.
3. On GitHub, open your repo → **Settings** (top) → **Pages** (left menu). Under
   "Build and deployment", set **Source = Deploy from a branch**, **Branch =
   main**, **Folder = /docs**, and click **Save**.
4. Wait about a minute, then your app is live at:

   **https://YOURNAME.github.io/furlong/**

### B5. Add it to your phone

On your Android phone, open that URL in **Chrome** → tap the **⋮** menu →
**Add to Home screen** → Add. You'll get a Furlong icon that opens full-screen
like an app. 🎉 Right now it shows sample data — Phase C makes it real.

---

## Phase C — Wire in real racing data

This uses **rpscrape** to pull Racing Post data. In your Command Prompt with
`(.venv)` active:

### C1. Get rpscrape (next to the project)

```
cd C:\
git clone https://github.com/joenano/rpscrape
pip install -r C:\rpscrape\requirements.txt
cd C:\furlong
```

(Cloning into `C:\rpscrape` matches Furlong's default location, so there's
nothing to configure.)

### C2. Fetch some history (your training data)

rpscrape downloads results by region, years and code. From the rpscrape folder:

```
cd C:\rpscrape
python rpscrape.py -r gb -y 2016-2024 -t flat
python rpscrape.py -r gb -y 2016-2024 -t jumps
cd C:\furlong
```

This can take a while and saves CSVs under `C:\rpscrape\data`. (rpscrape's exact
options can vary by version — if a command errors, check its README at the
GitHub page; the goal is simply to end up with results CSVs in that `data`
folder. More history = better predictions; a few seasons of each is a good
start.)

### C3. Build the dataset and train the models

```
python -c "from furlong import ingest; ingest.build_results_dataset()"
python scripts\train.py
```

`train.py` builds features, prints a quick accuracy backtest, and saves the Flat
and Jumps models. This is the step that makes the numbers real.

### C4. Produce today's + tomorrow's predictions and publish

```
python scripts\run_daily.py --publish
```

This fetches the racecards via rpscrape, predicts, updates `docs\data.json` and
`docs\data-tomorrow.json`, and pushes to GitHub. Within a minute your phone app
shows **real** predictions. (Tomorrow's card only appears once its declarations
are out — usually the evening before.)

---

## Phase D — Make it automatic (Windows Task Scheduler)

So you never have to run anything by hand:

```
powershell -ExecutionPolicy Bypass -File automation\install_windows.ps1
```

That creates two scheduled tasks:

- **Furlong Daily** — every day at **08:00**: predict today + tomorrow, publish.
- **Furlong Retrain** — **Sundays 06:00**: refresh data from rpscrape + retrain.

Test the daily run immediately without waiting for 8am:

```
scripts\run_furlong.bat
```

Then refresh the app on your phone. Logs are written to `C:\furlong\logs\furlong.log`.

To remove the schedule later, in PowerShell:

```
Unregister-ScheduledTask -TaskName "Furlong Daily","Furlong Retrain" -Confirm:$false
```

> Note: the PC needs to be **on and awake** at the scheduled time for the run to
> happen (Task Scheduler will run it at the next wake if it was asleep).

---

## Troubleshooting

- **`python` not recognized** — reopen the Command Prompt; if still failing,
  reinstall Python with "Add to PATH" ticked, or use `py` instead of `python`.
- **`(.venv)` not showing** — run `.venv\Scripts\activate` again in that window.
- **`git push` asks for a password and rejects it** — use the browser sign-in
  window that pops up (GitHub no longer accepts your account password on the
  command line). If none appears, install "Git Credential Manager" (bundled with
  recent Git for Windows).
- **Pages shows 404** — double-check Settings → Pages is set to **main / /docs**,
  and give it a minute after saving.
- **App shows sample data still** — you've not run Phase C yet, or the daily run
  hasn't pushed; run `python scripts\run_daily.py --publish` and refresh.
- **rpscrape command errors** — versions differ; see its GitHub README for the
  exact flags. Furlong only needs the results CSVs it produces under
  `C:\rpscrape\data`.
- **Want it private, not public?** — free GitHub Pages is public. Alternatives:
  Cloudflare Pages / Netlify (both allow access control; point them at the
  `docs` folder), or serve `docs` from your PC over Tailscale. The app is
  identical; only the host changes.
