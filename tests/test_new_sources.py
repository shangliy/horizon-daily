"""Unit tests for key-less Polymarket, arXiv, and Bluesky scrapers and broadsheet wiring."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx

from src.models import (
    ArXivConfig,
    BlueskyConfig,
    PolymarketConfig,
    SourceType,
)
from src.rendering.broadsheet import BroadsheetRenderer
from src.scrapers.arxiv import ArXivScraper
from src.scrapers.bluesky import BlueskyScraper
from src.scrapers.polymarket import PolymarketScraper
from src.storage.manager import StorageManager


def _mock_client(json_payload=None, text_payload=None):
    response = MagicMock(spec=httpx.Response)
    response.raise_for_status = MagicMock()
    if json_payload is not None:
        response.json = MagicMock(return_value=json_payload)
    if text_payload is not None:
        response.text = text_payload
    client = MagicMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(return_value=response)
    return client


def test_polymarket_scraper_parses_events_and_filters_volume():
    payload = [
        {
            "id": "pm-1",
            "slug": "openai-releases-next-model-2026",
            "title": "Will OpenAI release GPT-6 in 2026?",
            "description": "Resolves Yes if officially released before Dec 31.",
            "volume24hr": 185000.0,
            "volume": 2400000.0,
            "liquidity": 410000.0,
            "updatedAt": "2026-11-24T12:00:00Z",
            "markets": [
                {
                    "question": "Will OpenAI release GPT-6 in 2026?",
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["0.74", "0.26"]',
                    "volume24hr": 185000.0,
                    "oneDayPriceChange": 0.05,
                }
            ],
            "tags": [{"slug": "ai", "label": "AI"}],
        },
        {
            "id": "pm-low",
            "slug": "tiny-market",
            "title": "Tiny illiquid market",
            "volume24hr": 120.0,
            "markets": [],
        },
    ]
    client = _mock_client(json_payload=payload)
    cfg = PolymarketConfig(enabled=True, tags=["ai"], min_volume_24h=10000.0, max_items=5, profile="finance-news")

    result = asyncio.run(PolymarketScraper(cfg, client).fetch(datetime.now(timezone.utc) - timedelta(hours=24)))

    assert result.status == "success"
    assert len(result.items) == 1
    item = result.items[0]
    assert item.source_type == SourceType.POLYMARKET
    assert str(item.url) == "https://polymarket.com/event/openai-releases-next-model-2026"
    assert item.metadata["probability_pct"] == 74.0
    assert item.metadata["leading_outcome"] == "Yes"
    assert item.metadata["volume_24h_display"] == "$185K"
    assert "74.0%" in (item.content or "")


def test_arxiv_scraper_parses_atom_entries_and_filters_keywords():
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    atom_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2611.12345v1</id>
        <published>{now_iso}</published>
        <title>Sparse Attention for Fast LLM Inference</title>
        <summary>We accelerate long-context inference by 4x using sparse KV compression.</summary>
        <author><name>Alice Smith</name></author>
        <author><name>Bob Chen</name></author>
        <link title="pdf" href="https://arxiv.org/pdf/2611.12345v1" rel="related" type="application/pdf"/>
        <category term="cs.LG"/>
      </entry>
      <entry>
        <id>http://arxiv.org/abs/2611.99999v1</id>
        <published>{now_iso}</published>
        <title>Unrelated Botany Classification</title>
        <summary>Leaf shapes in alpine meadows.</summary>
        <author><name>Carol</name></author>
        <category term="cs.CV"/>
      </entry>
    </feed>
    """
    client = _mock_client(text_payload=atom_xml)
    cfg = ArXivConfig(enabled=True, categories=["cs.LG"], keywords=["inference"], max_results=10, profile="tech-blog")

    result = asyncio.run(ArXivScraper(cfg, client).fetch(datetime.now(timezone.utc) - timedelta(hours=24)))

    assert result.status == "success"
    assert len(result.items) == 1
    item = result.items[0]
    assert item.source_type == SourceType.ARXIV
    assert str(item.url) == "https://arxiv.org/abs/2611.12345v1"
    assert item.author == "Alice Smith, Bob Chen"
    assert item.metadata["arxiv_id"] == "2611.12345v1"
    assert item.metadata["pdf_url"] == "https://arxiv.org/pdf/2611.12345v1"


def test_bluesky_scraper_parses_search_posts_and_enforces_min_likes():
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "posts": [
            {
                "uri": "at://did:plc:abc123/app.bsky.feed.post/3kxyz789",
                "author": {"handle": "simonwillison.net", "displayName": "Simon Willison"},
                "record": {
                    "text": "Just tested a new open-source local LLM tool and it is impressively fast.",
                    "createdAt": now_iso,
                },
                "likeCount": 142,
                "repostCount": 27,
                "replyCount": 11,
                "embed": {
                    "external": {
                        "title": "Fast Local LLM Notes",
                        "uri": "https://simonwillison.net/2026/fast-llm",
                    }
                },
            },
            {
                "uri": "at://did:plc:low/app.bsky.feed.post/3klow",
                "author": {"handle": "quiet.bsky.social"},
                "record": {"text": "Low engagement post", "createdAt": now_iso},
                "likeCount": 2,
            },
        ]
    }
    client = _mock_client(json_payload=payload)
    cfg = BlueskyConfig(enabled=True, queries=["LLM"], min_likes=20, profile="tech-news")

    result = asyncio.run(BlueskyScraper(cfg, client).fetch(datetime.now(timezone.utc) - timedelta(hours=24)))

    assert result.status == "success"
    assert len(result.items) == 1
    item = result.items[0]
    assert item.source_type == SourceType.BLUESKY
    assert str(item.url) == "https://bsky.app/profile/simonwillison.net/post/3kxyz789"
    assert item.metadata["favorite_count"] == 142
    assert item.metadata["retweet_count"] == 27
    assert item.metadata["shared_url"] == "https://simonwillison.net/2026/fast-llm"


def test_broadsheet_ticker_and_config_include_new_keyless_sources():
    repo_root = Path(__file__).resolve().parents[1]
    storage = StorageManager(
        data_dir=str(repo_root / "data"),
        config_path=str(repo_root / "data" / "config.broadsheet.json"),
    )
    cfg = storage.load_config()
    assert cfg.sources.polymarket is not None and cfg.sources.polymarket.enabled is True
    assert cfg.sources.arxiv is not None and cfg.sources.arxiv.enabled is True
    assert cfg.sources.bluesky is not None and cfg.sources.bluesky.enabled is True

    # Verify Polymarket odds appear in broadsheet ticker and engagement line
    payload = [
        {
            "id": "pm-ticker",
            "slug": "fed-rate-cut",
            "title": "Fed cuts rates in December?",
            "volume24hr": 500000.0,
            "markets": [
                {
                    "question": "Fed cuts rates in December?",
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["0.82", "0.18"]',
                    "volume24hr": 500000.0,
                }
            ],
        }
    ]
    pm_item = asyncio.run(
        PolymarketScraper(PolymarketConfig(enabled=True, tags=["finance"], profile="finance-news"), _mock_client(json_payload=payload))
        .fetch(datetime.now(timezone.utc) - timedelta(hours=24))
    ).items[0]
    from src.models import ClassificationResult, ContentAnalysis, ContentArtifact, ContentBlock, ProcessingResult

    pm_item.processing = ProcessingResult(
        classification=ClassificationResult(profile="finance-news", method="source_override"),
        analysis=ContentAnalysis(score=8.8, reason="high vol", summary="Market prices 82% odds.", tags=["Fed"]),
        artifacts={
            "en": ContentArtifact(
                language="en",
                title="Fed cuts rates in December?",
                blocks=[ContentBlock(id="summary", title="Summary", content="Market prices 82% odds.", primary=True)],
            )
        },
    )
    renderer = BroadsheetRenderer()
    edition = renderer.build_edition_data([pm_item], date="2026-11-24", total_fetched=10, language="en")
    assert any(t["label"].startswith("POLYMARKET") and t["metric"] == "82%" for t in edition["ticker"])
    assert any("82%" in e for e in edition["items"][0]["engagement"])
