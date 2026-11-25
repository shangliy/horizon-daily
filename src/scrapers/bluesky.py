"""Bluesky public AT Protocol AppView scraper (key-less).

Uses the open AppView endpoints at https://public.api.bsky.app/xrpc/ to fetch
posts from followed author handles (app.bsky.feed.getAuthorFeed) and/or keyword
searches (app.bsky.feed.searchPosts) without requiring any API key or login.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import re
from typing import Any, List, Optional

from dateutil.parser import isoparse
import httpx

from ..models import BlueskyConfig, ContentItem, SourceType
from .base import BaseScraper, FetchResult

logger = logging.getLogger(__name__)


def _rkey_from_uri(uri: str) -> str:
    # Format: at://did:plc:.../app.bsky.feed.post/<rkey>
    return uri.rsplit("/", 1)[-1] if "/" in uri else uri


def _make_title(text: str, handle: str, external_title: str = "") -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if external_title and len(compact) < 24:
        return f"@{handle}: {external_title}"
    if not compact:
        return f"@{handle} on Bluesky"
    first_sentence = re.split(r"(?<=[.!?。！？])\s+", compact, maxsplit=1)[0]
    candidate = first_sentence if 18 <= len(first_sentence) <= 110 else compact
    if len(candidate) > 110:
        candidate = candidate[:109].rstrip() + "…"
    return f"@{handle}: {candidate}"


class BlueskyScraper(BaseScraper):
    """Scraper for Bluesky public author feeds and search queries."""

    SOURCE_TYPE = SourceType.BLUESKY
    BASE_URL = "https://public.api.bsky.app/xrpc"

    def __init__(self, config: BlueskyConfig, http_client: httpx.AsyncClient):
        super().__init__(config.model_dump(), http_client)
        self.cfg = config

    async def fetch(self, since: datetime) -> FetchResult:
        result = FetchResult()
        if not self.cfg.enabled:
            return result

        handles = [h.strip().lstrip("@") for h in self.cfg.handles if h.strip()]
        queries = [q.strip() for q in self.cfg.queries if q.strip()]
        if not handles and not queries:
            return result

        tasks = [
            result.collect(f"handle:{handle}", self._fetch_author_feed(handle, since))
            for handle in handles
        ]
        tasks.extend(
            result.collect(f"query:{query}", self._search_posts(query, since))
            for query in queries
        )
        await asyncio.gather(*tasks)

        # Deduplicate across handles and queries by post ID
        deduped: List[ContentItem] = []
        seen_ids: set[str] = set()
        for item in result.items:
            if item.id not in seen_ids:
                seen_ids.add(item.id)
                deduped.append(item)

        deduped.sort(
            key=lambda x: (
                int(x.metadata.get("favorite_count") or 0)
                + int(x.metadata.get("retweet_count") or 0) * 2
            ),
            reverse=True,
        )
        result.items = deduped
        return result

    async def _fetch_author_feed(self, handle: str, since: datetime) -> List[ContentItem]:
        resp = await self.client.get(
            f"{self.BASE_URL}/app.bsky.feed.getAuthorFeed",
            params={
                "actor": handle,
                "limit": min(max(self.cfg.fetch_limit, 1), 50),
                "filter": "posts_no_replies",
            },
            headers={"Accept": "application/json", "User-Agent": "Horizon/0.1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        feed = data.get("feed") if isinstance(data, dict) else None
        if not isinstance(feed, list):
            return []

        items: List[ContentItem] = []
        for entry in feed:
            if not isinstance(entry, dict):
                continue
            # Skip reposts by other authors to keep signal clean
            if entry.get("reason"):
                continue
            post = entry.get("post")
            if isinstance(post, dict):
                item = self._parse_post(post, since)
                if item is not None:
                    items.append(item)
        return items

    async def _search_posts(self, query: str, since: datetime) -> List[ContentItem]:
        resp = await self.client.get(
            f"{self.BASE_URL}/app.bsky.feed.searchPosts",
            params={
                "q": query,
                "sort": "top",
                "limit": min(max(self.cfg.fetch_limit, 1), 50),
                "since": since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            headers={"Accept": "application/json", "User-Agent": "Horizon/0.1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        posts = data.get("posts") if isinstance(data, dict) else None
        if not isinstance(posts, list):
            return []

        items: List[ContentItem] = []
        for post in posts:
            if isinstance(post, dict):
                item = self._parse_post(post, since)
                if item is not None:
                    items.append(item)
        return items

    def _parse_post(self, post: dict[str, Any], since: datetime) -> Optional[ContentItem]:
        uri = str(post.get("uri") or "").strip()
        author_obj = post.get("author") if isinstance(post.get("author"), dict) else {}
        handle = str(author_obj.get("handle") or "").strip()
        display_name = str(author_obj.get("displayName") or "").strip()
        record = post.get("record") if isinstance(post.get("record"), dict) else {}
        if not uri or not handle or not record:
            return None

        likes = int(post.get("likeCount") or 0)
        reposts = int(post.get("repostCount") or 0)
        replies = int(post.get("replyCount") or 0)
        if likes < self.cfg.min_likes:
            return None

        created_raw = record.get("createdAt") or post.get("indexedAt")
        published_at = self._parse_timestamp(created_raw)
        if published_at < since:
            return None

        text = str(record.get("text") or "").strip()
        embed = post.get("embed") if isinstance(post.get("embed"), dict) else {}
        external = embed.get("external") if isinstance(embed.get("external"), dict) else {}
        ext_title = str(external.get("title") or "").strip()
        ext_uri = str(external.get("uri") or "").strip()
        ext_desc = str(external.get("description") or "").strip()

        rkey = _rkey_from_uri(uri)
        post_url = f"https://bsky.app/profile/{handle}/post/{rkey}"
        title = _make_title(text, handle, external_title=ext_title)

        body_parts = [text] if text else []
        if ext_title or ext_uri:
            link_line = f"Shared link: {ext_title} ({ext_uri})" if ext_title and ext_uri else f"Shared link: {ext_title or ext_uri}"
            body_parts.append(link_line)
        if ext_desc:
            body_parts.append(ext_desc[:400])

        metadata: dict[str, Any] = {
            "handle": handle,
            "favorite_count": likes,
            "retweet_count": reposts,
            "reply_count": replies,
            "feed_name": f"@{handle}",
        }
        if ext_uri:
            metadata["shared_url"] = ext_uri
        if self.cfg.category:
            metadata["category"] = self.cfg.category

        return ContentItem(
            id=self._generate_id(self.SOURCE_TYPE.value, "post", f"{handle}:{rkey}"),
            source_type=self.SOURCE_TYPE,
            title=title,
            url=post_url,
            content="\n\n".join(body_parts) or title,
            author=display_name or f"@{handle}",
            published_at=published_at,
            metadata=metadata,
            profile=self.cfg.profile,
        )

    @staticmethod
    def _parse_timestamp(raw: Any) -> datetime:
        if isinstance(raw, str) and raw.strip():
            try:
                dt = isoparse(raw.strip())
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass
        return datetime.now(timezone.utc)
