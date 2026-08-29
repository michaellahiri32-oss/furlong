#!/usr/bin/env python3
"""
TipXI build script.

Runs on Netlify (or locally). It:
  1. Reads last season's per-team aggregates from the committed seed
     (data/statsdata_2526.txt) — this is the guaranteed baseline / "prior".
  2. If it can reach football-data.co.uk, fetches the CURRENT season's results
     for each division and BLENDS them into the baseline. Early in the season a
     team's numbers lean on last year; as more current-season games are played
     this season's results progressively take over (shrinkage — see PRIOR_GAMES).
     It also computes recent-form multipliers the app layers on automatically.
  3. Loads the committed fixture list (data/fixtures.json), assembles the data
     object, and injects it + the logo into template.html -> public/index.html.

No third-party packages — Python standard library only.
Run `python3 build.py --local` to build from the seed only (no network).
"""
import json, os, sys, csv, io, urllib.request, datetime
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, 'public')
LIVE = '--local' not in sys.argv

def find(name):
    """Locate a bundled file whether it sits at the repo root or in data/ or assets/."""
    for d in (HERE, os.path.join(HERE,'data'), os.path.join(HERE,'assets')):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(name + " (looked in repo root, data/, assets/)")

LEAGUE_NAME = {'E0':'Premier League','E1':'Championship','E2':'League One','E3':'League Two'}
FD = 'https://www.football-data.co.uk/mmz4281'
CURRENT_SEASON_CODE = '2627'      # football-data code for 2026/27

# ---- Blend controls -------------------------------------------------------
# Last season is treated as a "prior" worth PRIOR_GAMES games per home/away
# split. With PRIOR_GAMES = 4, once a team has played ~4 current-season home
# games its home numbers are a 50/50 blend of last year and this year; before
# that last year dominates (so 2-3 games nudge the numbers rather than swing
# them). Lower it to trust this season sooner; raise it to lean on last year.
PRIOR_GAMES = 4
# Only start blending a division once its teams average at least this many
# current-season games (guards against acting on a near-empty CSV).
ACCEPT_MIN_AVG_GAMES = 2
FORM_WINDOW = 6                   # recent games that define "form"

# ---------------------------------------------------------------------------
def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent':'TipXI-build/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')

def blank():
    return dict(hp=0, ap=0, hgf=0, hga=0, agf=0, aga=0, hcf=0, hca=0, acf=0, aca=0)

def rate(n, d):
    return (n/d) if d else None

def r2(x):
    return None if x is None else round(x, 2)

# ---------------------------------------------------------------------------
# 1. Baseline from the committed seed (last full season).
# ---------------------------------------------------------------------------
def baseline():
    """Return name -> (div, sums) for every team in last season's seed."""
    out = {}
    for line in open(find('statsdata_2526.txt')):
        line = line.strip()
        if not line:
            continue
        div,name,hp,ap,hgf,hga,agf,aga,hcf,hca,acf,aca = line.split('|')
        vals = list(map(int,(hp,ap,hgf,hga,agf,aga,hcf,hca,acf,aca)))
        s = blank()
        for k,v in zip(('hp','ap','hgf','hga','agf','aga','hcf','hca','acf','aca'), vals):
            s[k] = v
        out[name] = (div, s)
    return out

def last_rates(s):
    """Per-split per-game rates from a season's sums record (or None-filled)."""
    if not s:
        return {k: None for k in ('h_gf','h_ga','h_cf','h_ca',
                                  'a_gf','a_ga','a_cf','a_ca','gf','ga','cf','ca')}
    gp = s['hp'] + s['ap']
    return {
        'h_gf':rate(s['hgf'],s['hp']), 'h_ga':rate(s['hga'],s['hp']),
        'h_cf':rate(s['hcf'],s['hp']), 'h_ca':rate(s['hca'],s['hp']),
        'a_gf':rate(s['agf'],s['ap']), 'a_ga':rate(s['aga'],s['ap']),
        'a_cf':rate(s['acf'],s['ap']), 'a_ca':rate(s['aca'],s['ap']),
        'gf':rate(s['hgf']+s['agf'],gp), 'ga':rate(s['hga']+s['aga'],gp),
        'cf':rate(s['hcf']+s['acf'],gp), 'ca':rate(s['hca']+s['aca'],gp),
    }

def shrink(prior, tot, games, K):
    """Blend a last-season prior rate with this season's observed total/games."""
    if games <= 0:
        return prior
    if prior is None:              # promoted team with no last-season record
        return tot / games
    return (prior * K + tot) / (K + games)

# ---------------------------------------------------------------------------
# 2. Current-season fetch (optional; needs network).
# ---------------------------------------------------------------------------
def parse_date(d):
    for fmt in ('%d/%m/%Y','%d/%m/%y','%Y-%m-%d'):
        try: return datetime.datetime.strptime(d, fmt)
        except ValueError: pass
    return None

def current_season():
    """Return name -> {'div':div, 's':sums(+form)} for divisions that are under way."""
    if not LIVE:
        return {}
    cur = {}
    for div in ('E0','E1','E2','E3'):
        try:
            txt = fetch(f'{FD}/{CURRENT_SEASON_CODE}/{div}.csv')
        except Exception as e:
            print(f'  no current data for {div}: {e}', file=sys.stderr); continue
        try:
            rows = list(csv.DictReader(io.StringIO(txt)))
        except Exception:
            continue
        teams = {}
        recent = {}   # name -> list of (date, gf,ga,cf,ca), chronological
        for r in rows:
            try:
                if r.get('Div') != div: continue
                h,a = r['HomeTeam'], r['AwayTeam']
                hg,ag = int(r['FTHG']), int(r['FTAG'])
                hc,ac = int(float(r['HC'])), int(float(r['AC']))
                dt = parse_date(r.get('Date',''))
            except (KeyError, ValueError, TypeError):
                continue
            if not h or not a: continue
            H = teams.setdefault(h, blank()); A = teams.setdefault(a, blank())
            H['hp']+=1; H['hgf']+=hg; H['hga']+=ag; H['hcf']+=hc; H['hca']+=ac
            A['ap']+=1; A['agf']+=ag; A['aga']+=hg; A['acf']+=ac; A['aca']+=hc
            recent.setdefault(h, []).append((dt, hg, ag, hc, ac))
            recent.setdefault(a, []).append((dt, ag, hg, ac, hc))
        # only blend a division that is genuinely under way
        gp_each = [s['hp']+s['ap'] for s in teams.values()]
        avg = (sum(gp_each)/len(gp_each)) if gp_each else 0
        if avg < ACCEPT_MIN_AVG_GAMES:
            print(f'  {div}: ~{avg:.1f} games/team — holding on last season')
            continue
        # recent-form multipliers (recent N games vs this season's own average)
        for name, s in teams.items():
            gp = s['hp']+s['ap']
            if not gp: continue
            seas_gf=(s['hgf']+s['agf'])/gp; seas_ga=(s['hga']+s['aga'])/gp
            seas_cf=(s['hcf']+s['acf'])/gp; seas_ca=(s['hca']+s['aca'])/gp
            games = sorted([x for x in recent.get(name,[]) if x[0]], key=lambda x:x[0])[-FORM_WINDOW:]
            n = len(games)
            if n >= 3 and seas_gf and seas_ga and seas_cf and seas_ca:
                rgf=sum(g[1] for g in games)/n; rga=sum(g[2] for g in games)/n
                rcf=sum(g[3] for g in games)/n; rca=sum(g[4] for g in games)/n
                clamp=lambda x:max(0.5,min(1.7,x))
                s['form']={'gf':round(clamp(rgf/seas_gf),3),'ga':round(clamp(rga/seas_ga),3),
                           'cf':round(clamp(rcf/seas_cf),3),'ca':round(clamp(rca/seas_ca),3)}
                s['formN']=n
            cur[name] = {'div':div, 's':s}
    return cur

# ---------------------------------------------------------------------------
# 3. Blend one team: last-season prior + this-season observed.
# ---------------------------------------------------------------------------
def blended_team(name, div, last_s, cur_s):
    lr = last_rates(last_s)
    hp = cur_s['hp'] if cur_s else 0
    ap = cur_s['ap'] if cur_s else 0
    gp = hp + ap
    def H(key, tot):  # home split
        return r2(shrink(lr[key], cur_s[tot] if cur_s else 0, hp, PRIOR_GAMES))
    def A(key, tot):  # away split
        return r2(shrink(lr[key], cur_s[tot] if cur_s else 0, ap, PRIOR_GAMES))
    def O(key, th, ta):  # overall (both venues), prior worth 2x the split prior
        tot = (cur_s[th] + cur_s[ta]) if cur_s else 0
        return r2(shrink(lr[key], tot, gp, 2*PRIOR_GAMES))
    rec = {
        'team':name, 'league':LEAGUE_NAME[div], 'div':div,
        'h_gf':H('h_gf','hgf'), 'h_ga':H('h_ga','hga'), 'h_cf':H('h_cf','hcf'), 'h_ca':H('h_ca','hca'),
        'a_gf':A('a_gf','agf'), 'a_ga':A('a_ga','aga'), 'a_cf':A('a_cf','acf'), 'a_ca':A('a_ca','aca'),
        'gf':O('gf','hgf','agf'), 'ga':O('ga','hga','aga'), 'cf':O('cf','hcf','acf'), 'ca':O('ca','hca','aca'),
        'homeP':hp, 'awayP':ap,
    }
    if cur_s and last_s:
        rec['season'] = f'blend · {gp} new'
        rec['played'] = gp
    elif cur_s:
        rec['season'] = f'26/27 · {gp} gms'
        rec['played'] = gp
    else:
        rec['season'] = '2025/26'
        rec['played'] = last_s['hp'] + last_s['ap']
    if cur_s and cur_s.get('form'):
        rec['form'] = cur_s['form']; rec['formN'] = cur_s['formN']
    return rec

def league_avg_from_records(recs_by_div):
    """League average rate per split = mean of the blended team rates in that division."""
    keys = ['h_gf','h_ga','a_gf','a_ga','h_cf','h_ca','a_cf','a_ca']
    la = {}
    for div, recs in recs_by_div.items():
        acc = {k:[] for k in keys}
        for rec in recs:
            for k in keys:
                if rec.get(k) is not None: acc[k].append(rec[k])
        la[LEAGUE_NAME[div]] = {k:(round(sum(v)/len(v),3) if v else None) for k,v in acc.items()}
    return la

# ---------------------------------------------------------------------------
def assemble():
    last = baseline()                       # name -> (div, sums)
    cur = current_season()                  # name -> {'div', 's'}
    teams = {}
    recs_by_div = defaultdict(list)
    handled = set()

    # teams with current-season data: blend, and file under their CURRENT division
    for name, info in cur.items():
        div, s = info['div'], info['s']
        last_s = last[name][1] if name in last else None
        rec = blended_team(name, div, last_s, s)
        teams[name] = rec; recs_by_div[div].append(rec); handled.add(name)

    # remaining teams (no current data yet): pure last-season, last-season division
    for name, (div, s) in last.items():
        if name in handled: continue
        rec = blended_team(name, div, s, None)
        teams[name] = rec; recs_by_div[div].append(rec)

    blended_divs = sorted({info['div'] for info in cur.values()})
    if blended_divs:
        print('blended current season into divisions:', blended_divs,
              f'(prior = {PRIOR_GAMES} games)')
    else:
        print('using last-season baseline for all divisions')

    la = league_avg_from_records(recs_by_div)

    seed = json.load(open(find('fixtures.json')))
    meta = dict(seed['meta'])
    meta['generated'] = datetime.date.today().isoformat()
    meta['leagueAvg'] = la
    meta['blend'] = {'prior': PRIOR_GAMES, 'divisions': blended_divs}
    return {'meta':meta, 'teams':teams, 'fixtures':seed['fixtures']}

def main():
    data = assemble()

    tpl = open(find('template.html')).read()
    tpl = tpl.replace('__DATA__', json.dumps(data, separators=(',',':')))
    tpl = tpl.replace('__LOGO__', open(find('logo_b64.txt')).read())
    tpl = tpl.replace('__ICON__', open(find('icon_b64.txt')).read())
    for ph in ('__DATA__','__LOGO__','__ICON__'):
        assert ph not in tpl, f'placeholder {ph} not replaced'

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR,'index.html'),'w') as f:
        f.write(tpl)
    import shutil
    for name in ('manifest.webmanifest','sw.js','icon-192.png','icon-512.png',
                 'icon-192-maskable.png','icon-512-maskable.png'):
        try: shutil.copy(find(name), os.path.join(OUT_DIR, name))
        except FileNotFoundError: pass
    print(f"built public/index.html  teams={len(data['teams'])} "
          f"fixtures={len(data['fixtures'])} updated={data['meta']['generated']}")

if __name__ == '__main__':
    main()
