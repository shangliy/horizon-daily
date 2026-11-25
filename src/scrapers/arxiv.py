"""arXiv Atom API scraper for recent AI/ML/CS research papers (key-less).

Queries https://export.arxiv.org/api/query for configured arXiv categories
(e.g., cs.AI, cs.LG, cs.CL), parses Atom entries via feedparser, and emits
normalized ContentItems with canonical https://arxiv.org/abs/<id> URLs.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
import logging
import re
from typing import List, Optional

import feedparser
import httpx

from ..models import ArXivConfig, ContentItem, SourceType
from .base import BaseScraper, FetchResult

logger = logging.getLogger(__name__)

_ARXIV_ID_RE = re.compile(r"/abs/([^\s/?#]+)$")


def _compact_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


class ArXivScraper(BaseScraper):
    """Scraper for recent arXiv research papers."""

    SOURCE_TYPE = SourceType.ARXIV
    BASE_URL = "https://export.arxiv.org/api/query"

    def __init__(self, config: ArXivConfig, http_client: httpx.AsyncClient):
        super().__init__(config.model_dump(), http_client)
        self.cfg = config
        self._keywords_lower = [kw.strip().lower() for kw in config.keywords if kw.strip()]

    async def fetch(self, since: datetime) -> FetchResult:
        result = FetchResult()
        if not self.cfg.enabled:
            return result

        cats = [c.strip() for c in self.cfg.categories if c.strip()]
        if not cats:
            return result

        # arXiv only announces batches on weekdays, so respect a minimum lookback
        # window so weekend/Monday runs still return recent papers.
        floor_since = datetime.now(timezone.utc) - timedelta(hours=max(self.cfg.min_lookback_hours, 24))
        effective_since = min(since, floor_since)

        await result.collect(
            ",".join(cats),
            self._fetch_categories(cats, effective_since),
        )
        return result

    async def _fetch_categories(self, categories: List[str], since: datetime) -> List[ContentItem]:
        search_query = " OR ".join(f"cat:{cat}" for cat in categories)
        params = {
            "search_query": search_query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "start": 0,
            "max_results": max(self.cfg.max_results, 1),
        }
        resp = await self.client.get(
            self.BASE_URL,
            params=params,
            headers={"User-Agent": "Horizon/0.1.0 (+https://github.com/Thysrael/Horizon)"},
        )
        resp.raise_for_status()

        feed = feedparser.parse(resp.text)
        if getattr(feed, "bozo", False) and not feed.entries:
            raise ValueError(f"Failed to parse arXiv Atom feed: {feed.bozo_exception}")

        items: List[ContentItem] = []
        seen_ids: set[str] = set()
        for entry in feed.entries:
            item = self._parse_entry(entry, since)
            if item is None or item.id in seen_ids:
                continue
            seen_ids.add(item.id)
            items.append(item)
        return items

    def _parse_entry(self, entry: dict, since: datetime) -> Optional[ContentItem]:
        raw_id = str(entry.get("id") or entry.get("link") or "").strip()
        title = _compact_ws(str(entry.get("title") or ""))
        if not raw_id or not title:
            return None

        match = _ARXIV_ID_RE.search(raw_id)
        arxiv_id = match.group(1) if match else raw_id.rsplit("/", 1)[-1]
        canonical_url = f"https://arxiv.org/abs/{arxiv_id}"

        published_at = self._entry_datetime(entry)
        if published_at < since:
            return None

        abstract = _compact_ws(str(entry.get("summary") or ""))
        if self._keywords_lower:
            hay = f"{title} {abstract}".lower()
            if not any(kw in hay for kw in self._keywords_lower):
                return None

        authors_list = [
            _compact_ws(str(a.get("name") or ""))
            for a in (entry.get("authors") or [])
            if isinstance(a, dict) and a.get("name")
        ]
        if len(authors_list) > 3:
            author_str = ", ".join(authors_list[:3]) + " et al."
        else:
            author_str = ", ".join(authors_list) or "arXiv"

        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
        for link in entry.get("links") or []:
            if isinstance(link, dict) and link.get("type") == "application/pdf" and link.get("href"):
                pdf_url = str(link["href"])
                break

        arxiv_cats = [
            str(tag.get("term") or "").strip()
            for tag in (entry.get("tags") or [])
            if isinstance(tag, dict) and tag.get("term")
        ]

        content_lines = [abstract] if abstract else []
        if arxiv_cats:
            content_lines.append(f"arXiv categories: {', '.join(arxiv_cats[:5])}")
        content_lines.append(f"PDF: {pdf_url}")

        metadata = {
            "arxiv_id": arxiv_id,
            "arxiv_categories": arxiv_cats[:5],
            "pdf_url": pdf_url,
            "feed_name": f"arXiv ({arxiv_cats[0]})" if arxiv_cats else "arXiv",
        }
        if self.cfg.category:
            metadata["category"] = self.cfg.category

        return ContentItem(
            id=self._generate_id(self.SOURCE_TYPE.value, "paper", arxiv_id),
            source_type=self.SOURCE_TYPE,
            title=title,
            url=canonical_url,
            content="\n\n".join(content_lines),
            author=author_str,
            published_at=published_at,
            metadata=metadata,
            profile=self.cfg.profile,
        )

    @staticmethod
    def _entry_datetime(entry: dict) -> datetime:
        for field in ("published_parsed", "updated_parsed"):
            parsed = entry.get(field)
            if parsed is not None:
                try:
                    return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)
                except (OverflowError, OSError, ValueError):
                    continue
        return datetime.now(timezone.utc)
