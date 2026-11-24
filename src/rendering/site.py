"""Static site publisher and edition archive manifest manager for Horizon Broadsheet."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from .._file_utils import _atomic_write_text
from ..storage.manager import safe_output_path


_EDITION_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-([A-Za-z0-9_-]+)\.html$")


class BroadsheetSitePublisher:
    """Publishes dated broadsheet editions, root index.html, and editions.json manifest."""

    def __init__(self, site_dir: Path | str = "docs/broadsheet"):
        self.site_dir = Path(site_dir)

    def load_manifest(self) -> Dict[str, Any]:
        """Load existing editions.json if present and valid."""
        manifest_path = self.site_dir / "editions.json"
        if not manifest_path.exists():
            return {"latest_date": None, "default_language": "zh", "editions": []}
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            return {"latest_date": None, "default_language": "zh", "editions": []}
        if not isinstance(data, dict) or not isinstance(data.get("editions"), list):
            return {"latest_date": None, "default_language": "zh", "editions": []}
        return data

    def publish_edition(
        self,
        *,
        date: str,
        language: str,
        html_content: str,
        edition_data: Dict[str, Any],
        is_default_language: bool = False,
        default_language: Optional[str] = None,
    ) -> Dict[str, Path]:
        """Write one dated language edition and update latest/index/manifest files."""
        self.site_dir.mkdir(parents=True, exist_ok=True)

        # Ensure GitHub Pages serves raw static HTML without Jekyll processing
        nojekyll_path = safe_output_path(self.site_dir, ".nojekyll")
        if not nojekyll_path.exists():
            _atomic_write_text(nojekyll_path, "")

        dated_html = safe_output_path(self.site_dir, f"{date}-{language}.html")
        dated_json = safe_output_path(self.site_dir, f"{date}-{language}.json")
        latest_html = safe_output_path(self.site_dir, f"latest-{language}.html")

        _atomic_write_text(dated_html, html_content)
        _atomic_write_text(
            dated_json,
            json.dumps(edition_data, indent=2, ensure_ascii=False) + "\n",
        )
        _atomic_write_text(latest_html, html_content)

        written: Dict[str, Path] = {
            "dated_html": dated_html,
            "dated_json": dated_json,
            "latest_html": latest_html,
        }

        if is_default_language:
            index_html = safe_output_path(self.site_dir, "index.html")
            _atomic_write_text(index_html, html_content)
            written["index_html"] = index_html

        manifest_path = self._update_manifest(
            date=date,
            language=language,
            edition_data=edition_data,
            default_language=default_language or (language if is_default_language else None),
        )
        written["manifest"] = manifest_path
        return written

    def _update_manifest(
        self,
        *,
        date: str,
        language: str,
        edition_data: Dict[str, Any],
        default_language: Optional[str] = None,
    ) -> Path:
        existing = self.load_manifest()
        by_date: Dict[str, Dict[str, Any]] = {}

        # Preserve prior editions from manifest
        for entry in existing.get("editions", []):
            if isinstance(entry, dict) and isinstance(entry.get("date"), str):
                by_date[entry["date"]] = {
                    "date": entry["date"],
                    "languages": list(entry.get("languages") or []),
                    "titles": dict(entry.get("titles") or {}),
                    "selected_count": dict(entry.get("selected_count") or {}),
                    "top_headline": dict(entry.get("top_headline") or {}),
                }

        # Also discover any historical YYYY-MM-DD-{lang}.html files present on disk
        # (e.g. checked out from gh-pages before running today's edition).
        for path in sorted(self.site_dir.iterdir()):
            if not path.is_file():
                continue
            match = _EDITION_FILE_RE.match(path.name)
            if not match:
                continue
            file_date, file_lang = match.group(1), match.group(2)
            rec = by_date.setdefault(
                file_date,
                {
                    "date": file_date,
                    "languages": [],
                    "titles": {},
                    "selected_count": {},
                    "top_headline": {},
                },
            )
            if file_lang not in rec["languages"]:
                rec["languages"].append(file_lang)

        # Upsert current edition metadata
        meta = edition_data.get("meta") or {}
        items = edition_data.get("items") or []
        lead_id = (edition_data.get("front_page") or {}).get("lead_id")
        lead_item = next((i for i in items if i.get("id") == lead_id), items[0] if items else None)

        current = by_date.setdefault(
            date,
            {
                "date": date,
                "languages": [],
                "titles": {},
                "selected_count": {},
                "top_headline": {},
            },
        )
        if language not in current["languages"]:
            current["languages"].append(language)
        if meta.get("title"):
            current["titles"][language] = meta["title"]
        current["selected_count"][language] = int(meta.get("selected_count", len(items)))
        if lead_item and lead_item.get("title"):
            current["top_headline"][language] = lead_item["title"]

        # Sort dates descending (newest first) and keep consistent language order (zh before en)
        def _lang_sort_key(code: str) -> tuple[int, str]:
            order = {"zh": 0, "en": 1}
            return (order.get(code, 2), code)

        editions_list: List[Dict[str, Any]] = []
        for ed_date in sorted(by_date.keys(), reverse=True):
            rec = by_date[ed_date]
            rec["languages"] = sorted(set(rec["languages"]), key=_lang_sort_key)
            editions_list.append(rec)

        manifest = {
            "latest_date": editions_list[0]["date"] if editions_list else date,
            "default_language": default_language or existing.get("default_language") or "zh",
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "editions": editions_list,
        }

        manifest_path = safe_output_path(self.site_dir, "editions.json")
        _atomic_write_text(
            manifest_path,
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        )
        return manifest_path
