"""Publish the PWA to GitHub Pages.

The published site lives in `docs/` (GitHub Pages → "Deploy from branch",
folder `/docs`). `sync_app()` copies the app shell there; `write_data()` drops
today's `data.json`; `git_push()` commits and pushes so your phone sees it.
"""
from __future__ import annotations

import shutil
import subprocess
from datetime import datetime

import pandas as pd

from .config import DOCS, ROOT, WEBAPP
from .utils import get_logger
from .webexport import write_json

log = get_logger()

_SHELL = ["index.html", "manifest.webmanifest", "sw.js", "icon-192.png",
          "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png"]


def sync_app() -> None:
    """Copy the PWA shell files into docs/ (leaves data.json untouched)."""
    DOCS.mkdir(parents=True, exist_ok=True)
    for name in _SHELL:
        src = WEBAPP / name
        if src.exists():
            shutil.copy2(src, DOCS / name)
    # a .nojekyll file stops GitHub Pages mangling the static files
    (DOCS / ".nojekyll").touch()


def write_data(pred: pd.DataFrame, filename: str = "data.json",
               generated_at: datetime | None = None) -> str:
    """Write a day's prediction payload into docs/ (data.json = today,
    data-tomorrow.json = tomorrow)."""
    DOCS.mkdir(parents=True, exist_ok=True)
    return write_json(pred, DOCS / filename, generated_at)


DATA_FILES = {"today": "data.json", "tomorrow": "data-tomorrow.json"}


def git_push(message: str | None = None) -> bool:
    """Commit docs/ and push. Returns False (without raising) if git isn't set up."""
    message = message or f"furlong: update {datetime.now():%Y-%m-%d %H:%M}"
    try:
        if not (ROOT / ".git").exists():
            log.warning("no git repo — skipping push (see README GitHub Pages setup)")
            return False
        subprocess.run(["git", "add", "docs"], cwd=ROOT, check=True)
        # nothing to commit is fine
        r = subprocess.run(["git", "commit", "-m", message], cwd=ROOT,
                           capture_output=True, text=True)
        if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
            log.warning("git commit: " + r.stdout + r.stderr)
        subprocess.run(["git", "push"], cwd=ROOT, check=True)
        log.info("pushed to GitHub Pages")
        return True
    except Exception as e:  # noqa
        log.warning(f"git push failed ({e}); the docs/ folder is still updated locally")
        return False


def publish(pred: pd.DataFrame, push: bool = False, filename: str = "data.json",
            generated_at: datetime | None = None) -> str:
    """Publish a single day (default today). For both days, prefer publish_days."""
    sync_app()
    path = write_data(pred, filename, generated_at)
    if push:
        git_push()
    return path


def publish_days(preds: dict, push: bool = False,
                 generated_at: datetime | None = None) -> list[str]:
    """preds: {'today': df, 'tomorrow': df}. Writes each present day, one push."""
    sync_app()
    written = []
    for day, fname in DATA_FILES.items():
        pred = preds.get(day)
        if pred is not None and len(pred):
            written.append(write_data(pred, fname, generated_at))
    if push:
        git_push()
    return written
