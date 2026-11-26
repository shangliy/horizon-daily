"""Pre-deploy check for the broadsheet site.

Run as ``python -m src.rendering.verify`` after the pipeline and before the
site is pushed. It exits non-zero when this run did not produce a usable
edition, so a failed or near-empty run never replaces yesterday's front page.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional


def check_site(
    site_dir: Path | str,
    *,
    min_items: int = 5,
    max_age_hours: float = 6.0,
    now: Optional[datetime] = None,
) -> List[str]:
    """Return the reasons the site must not be deployed (empty when it is fine)."""
    site_dir = Path(site_dir)
    now = now or datetime.now(timezone.utc)
    manifest_path = site_dir / "editions.json"

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"{manifest_path} is missing: no edition was published"]
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{manifest_path} is unreadable: {exc}"]

    # The workflow restores the previous manifest from gh-pages before the
    # run, so a manifest that exists but was not rewritten means no new edition.
    try:
        updated_at = datetime.strptime(
            manifest.get("updated_at", ""), "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return ["editions.json has no valid updated_at timestamp"]
    if now - updated_at > timedelta(hours=max_age_hours):
        return [
            f"editions.json was last updated at {manifest['updated_at']}: "
            "this run did not publish a new edition"
        ]

    latest_date = manifest.get("latest_date")
    latest = next(
        (
            entry
            for entry in manifest.get("editions") or []
            if isinstance(entry, dict) and entry.get("date") == latest_date
        ),
        None,
    )
    if latest is None:
        return [f"editions.json has no entry for latest_date {latest_date!r}"]

    problems: List[str] = []
    counts = latest.get("selected_count") or {}
    if not counts:
        problems.append(f"edition {latest_date} has no item counts")
    for language, count in sorted(counts.items()):
        if not isinstance(count, int) or count < min_items:
            problems.append(
                f"edition {latest_date} [{language}] has {count} items, "
                f"fewer than the minimum of {min_items}"
            )
        for name in (f"{latest_date}-{language}.html", f"latest-{language}.html"):
            if not (site_dir / name).is_file():
                problems.append(f"{name} is missing from {site_dir}")
    if not (site_dir / "index.html").is_file():
        problems.append(f"index.html is missing from {site_dir}")
    return problems


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site-dir", default="docs/broadsheet")
    parser.add_argument("--min-items", type=int, default=5)
    parser.add_argument("--max-age-hours", type=float, default=6.0)
    args = parser.parse_args(argv)

    problems = check_site(
        args.site_dir, min_items=args.min_items, max_age_hours=args.max_age_hours
    )
    if problems:
        for problem in problems:
            print(f"edition check failed: {problem}", file=sys.stderr)
        return 1
    print(f"edition check passed: {args.site_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
