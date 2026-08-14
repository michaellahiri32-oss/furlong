"""Deploy / redeploy the phone app to GitHub Pages.

  python scripts/publish_web.py            # sync app shell into docs/ and push
  python scripts/publish_web.py --data-only  # just re-push whatever data.json exists

Use this after editing the app, or for the one-time first deploy. The daily
run publishes automatically via run_daily.py --publish.
"""
import argparse

import _bootstrap  # noqa

from furlong import publish
from furlong.utils import get_logger

log = get_logger()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-only", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()

    if not args.data_only:
        publish.sync_app()
        log.info("app shell synced into docs/")
    if not args.no_push:
        publish.git_push("furlong: deploy app")


if __name__ == "__main__":
    main()
