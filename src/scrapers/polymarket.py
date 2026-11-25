"""Polymarket Gamma API scraper for active high-volume prediction markets.

Uses the key-less public Gamma API (https://gamma-api.polymarket.com/events)
to surface active tech, AI, macro, and finance prediction markets ordered by
24-hour trading volume.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any, List, Optional

from dateutil.parser import isoparse
import httpx

from ..models import ContentItem, PolymarketConfig, SourceType
from .base import BaseScraper, FetchResult

logger = logging.getLogger(__name__)


def _parse_json_list(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _format_usd(amount: float) -> str:
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"${amount / 1_000:.0f}K"
    return f"${amount:.0f}"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class PolymarketScraper(BaseScraper):
    """Scraper for active Polymarket prediction markets (key-less)."""

    SOURCE_TYPE = SourceType.POLYMARKET
    BASE_URL = "https://gamma-api.polymarket.com/events"

    def __init__(self, config: PolymarketConfig, http_client: httpx.AsyncClient):
        super().__init__(config.model_dump(), http_client)
        self.cfg = config
        self._keywords_lower = [kw.strip().lower() for kw in config.keywords if kw.strip()]

    async def fetch(self, since: datetime) -> FetchResult:
        result = FetchResult()
        if not self.cfg.enabled:
            return result

        tags = [t.strip().lower() for t in self.cfg.tags if t.strip()]
        seen_ids: set[str] = set()
        collected: List[ContentItem] = []

        if tags:
            for tag in tags:
                await result.collect(f"tag:{tag}", self._fetch_events(tag_slug=tag))
        else:
            await result.collect("top", self._fetch_events(tag_slug=None))

        for item in result.items:
            if item.id not in seen_ids:
                seen_ids.add(item.id)
                collected.append(item)

        collected.sort(
            key=lambda x: float(x.metadata.get("volume_24h") or 0.0),
            reverse=True,
        )
        result.items = collected[: self.cfg.max_items]
        return result

    async def _fetch_events(self, *, tag_slug: Optional[str]) -> List[ContentItem]:
        params: dict[str, Any] = {
            "active": "true",
            "closed": "false",
            "order": "volume24hr",
            "ascending": "false",
            "limit": max(self.cfg.max_items * 2, 20),
        }
        if tag_slug:
            params["tag_slug"] = tag_slug

        resp = await self.client.get(
            self.BASE_URL,
            params=params,
            headers={"Accept": "application/json", "User-Agent": "Horizon/0.1.0"},
        )
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list):
            raise ValueError("Polymarket returned unexpected non-list payload")

        items: List[ContentItem] = []
        for event in payload:
            if not isinstance(event, dict):
                continue
            item = self._parse_event(event, tag_slug=tag_slug)
            if item is not None:
                items.append(item)
        return items

    def _parse_event(self, event: dict[str, Any], *, tag_slug: Optional[str]) -> Optional[ContentItem]:
        event_id = str(event.get("id") or "").strip()
        slug = str(event.get("slug") or "").strip()
        title = str(event.get("title") or "").strip()
        if not event_id or not slug or not title:
            return None

        volume_24h = _safe_float(event.get("volume24hr"))
        if volume_24h < self.cfg.min_volume_24h:
            return None

        description = str(event.get("description") or "").strip()
        if self._keywords_lower:
            hay = f"{title} {description}".lower()
            if not any(kw in hay for kw in self._keywords_lower):
                return None

        markets = [m for m in (event.get("markets") or []) if isinstance(m, dict)]
        market_lines: List[str] = []
        leading_outcome = ""
        leading_prob: Optional[float] = None
        price_change_24h: Optional[float] = None

        # Rank sub-markets by highest 24h volume or highest Yes price
        ranked_markets = sorted(
            markets,
            key=lambda m: _safe_float(m.get("volume24hr"), _safe_float(m.get("volume"))),
            reverse=True,
        )
        for m in ranked_markets[:4]:
            question = str(m.get("groupItemTitle") or m.get("question") or "").strip()
            outcomes = _parse_json_list(m.get("outcomes"))
            prices = [_safe_float(p, -1.0) for p in _parse_json_list(m.get("outcomePrices"))]
            if outcomes and len(outcomes) == len(prices):
                pairs = [(str(o), p) for o, p in zip(outcomes, prices) if 0.0 <= p <= 1.0]
                if pairs:
                    top_name, top_price = max(pairs, key=lambda pair: pair[1])
                    pct = round(top_price * 100, 1)
                    if leading_prob is None:
                        leading_outcome = question if (question and len(ranked_markets) > 1) else top_name
                        leading_prob = pct
                        chg = m.get("oneDayPriceChange")
                        if chg is not None:
                            price_change_24h = round(_safe_float(chg) * 100, 1)
                    label = question or title
                    summary_pair = ", ".join(f"{o}: {round(p * 100)}%" for o, p in pairs[:2])
                    market_lines.append(f"- {label} ({summary_pair})")

        total_volume = _safe_float(event.get("volume"))
        liquidity = _safe_float(event.get("liquidity"))

        content_parts = [
            f"Prediction market 24h volume: {_format_usd(volume_24h)} (total volume: {_format_usd(total_volume)}, liquidity: {_format_usd(liquidity)})."
        ]
        if leading_prob is not None:
            chg_str = ""
            if price_change_24h:
                sign = "+" if price_change_24h > 0 else ""
                chg_str = f" (24h change: {sign}{price_change_24h:.1f}pp)"
            content_parts.append(f"Current consensus: {leading_outcome} at {leading_prob:.1f}%{chg_str}.")
        if market_lines:
            content_parts.append("Key contracts:\n" + "\n".join(market_lines))
        if description:
            content_parts.append(description[:800])

        published_at = self._parse_timestamp(event.get("updatedAt") or event.get("createdAt"))
        event_tags = [
            str(t.get("label") or t.get("slug") or "").strip()
            for t in (event.get("tags") or [])
            if isinstance(t, dict) and (t.get("label") or t.get("slug"))
        ]

        metadata: dict[str, Any] = {
            "event_slug": slug,
            "volume_24h": volume_24h,
            "volume_24h_display": _format_usd(volume_24h),
            "total_volume": total_volume,
            "liquidity": liquidity,
            "leading_outcome": leading_outcome,
            "probability_pct": leading_prob,
            "price_change_24h": price_change_24h,
            "market_tags": event_tags[:6],
        }
        if tag_slug:
            metadata["tag_slug"] = tag_slug
        if self.cfg.category:
            metadata["category"] = self.cfg.category

        return ContentItem(
            id=self._generate_id(self.SOURCE_TYPE.value, "event", event_id),
            source_type=self.SOURCE_TYPE,
            title=title,
            url=f"https://polymarket.com/event/{slug}",
            content="\n\n".join(content_parts),
            author="Polymarket",
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
