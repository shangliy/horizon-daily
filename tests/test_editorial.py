"""Tests for the front-page editorial."""

import asyncio
from io import StringIO
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from rich.console import Console

from src.ai.editorial import EditorialWriter
from src.ai.enricher import EnrichmentBatchResult
from src.models import AIConfig, BroadsheetConfig, Config, SourcesConfig
from src.orchestrator import HorizonOrchestrator
from src.rendering.broadsheet import BroadsheetRenderer
from src.rendering.broadsheet_i18n import _COPY
from src.storage.manager import StorageManager
from tests.test_broadsheet import _make_item


def _records(count=5):
    return [
        {
            "id": f"story-{i}",
            "title": f"Story {i}",
            "summary": f"Summary of story {i}.",
            "profile_name": "Tech News",
            "score": float(i),
        }
        for i in range(count)
    ]


def _writer(response):
    client = AsyncMock()
    if isinstance(response, Exception):
        client.complete.side_effect = response
    else:
        client.complete.return_value = response
    return EditorialWriter(client), client


def test_editorial_maps_indices_to_ids_in_score_order():
    writer, client = _writer(json.dumps({
        "headline": "  Open weights are  winning ",
        "body": "First paragraph.\n\nSecond\nparagraph.",
        "story_indices": [0, 2, 2, 99, "1", True],
    }))

    editorial = asyncio.run(writer.write(_records(), "en"))

    assert editorial == {
        "headline": "Open weights are winning",
        "body": "First paragraph.\n\nSecond\n\nparagraph.",
        # Index 0 is the highest-scored story, not the first record.
        "story_ids": ["story-4", "story-2"],
    }
    prompt = client.complete.await_args.kwargs["user"]
    assert prompt.index("[0] (Tech News) Story 4") < prompt.index("[4] (Tech News) Story 0")
    assert "Write the editorial in English." in prompt


def test_editorial_prompt_follows_edition_language():
    writer, client = _writer('{"headline": "标题", "body": "正文。", "story_indices": []}')

    editorial = asyncio.run(writer.write(_records(), "zh-CN"))

    assert editorial == {"headline": "标题", "body": "正文。", "story_ids": []}
    assert "Simplified Chinese" in client.complete.await_args.kwargs["user"]


def test_editorial_skipped_without_enough_stories():
    writer, client = _writer("{}")

    assert asyncio.run(writer.write(_records(2), "en")) is None
    client.complete.assert_not_awaited()


def test_editorial_failures_return_none():
    for response in (
        RuntimeError("provider down"),
        "not json",
        '{"headline": "", "body": "text"}',
        '{"headline": "h", "body": 3}',
        json.dumps({"headline": "h", "body": "x" * 3000}),
    ):
        writer, _ = _writer(response)
        assert asyncio.run(writer.write(_records(), "en")) is None


def test_editorial_renders_escaped_with_story_links():
    items_by_id = {"story-1": {"title": "<b>Story</b> one"}}
    html = BroadsheetRenderer._render_editorial(
        {
            "headline": "<script>alert(1)</script>",
            "body": "One & two.\n\nThree.",
            "story_ids": ["story-1", "story-missing"],
        },
        items_by_id,
        _COPY["en"],
    )

    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<p>One &amp; two.</p><p>Three.</p>" in html
    assert html.count("data-open-story=") == 1
    assert 'data-open-story="story-1"' in html
    assert "&lt;b&gt;Story&lt;/b&gt; one" in html
    assert _COPY["en"]["editorial_byline"].replace("'", "&#x27;") in html


def test_editorial_absent_renders_nothing():
    for editorial in (None, {}, {"headline": "h", "body": ""}):
        assert BroadsheetRenderer._render_editorial(editorial, {}, _COPY["zh"]) == ""


def _run_pipeline(tmp_path, monkeypatch, *, editorial_enabled, response):
    orchestrator = HorizonOrchestrator(
        Config(
            ai=AIConfig(provider="openai", model="test", api_key_env="TEST_KEY", languages=["zh"]),
            sources=SourcesConfig(),
            broadsheet=BroadsheetConfig(editorial=editorial_enabled),
        ),
        StorageManager(str(tmp_path / "data")),
        console=Console(file=StringIO()),
    )
    items = [_make_item(i, title=f"头条 {i}", score=9.0 - i) for i in range(1, 5)]
    client = AsyncMock()
    client.complete.return_value = response
    monkeypatch.setattr(HorizonOrchestrator, "ai_client", property(lambda self: client))
    monkeypatch.setattr(orchestrator, "fetch_all_sources", AsyncMock(return_value=items))
    monkeypatch.setattr(orchestrator, "analyze_items", AsyncMock(return_value=items))
    monkeypatch.setattr(orchestrator, "select_digest_items", AsyncMock(return_value=SimpleNamespace(items=items)))
    monkeypatch.setattr(orchestrator, "enrich_items", AsyncMock(
        return_value=EnrichmentBatchResult(succeeded_ids=[item.id for item in items]),
    ))
    monkeypatch.chdir(tmp_path)

    asyncio.run(orchestrator.run())

    site = tmp_path / "docs" / "broadsheet"
    html = (site / "latest-zh.html").read_text(encoding="utf-8")
    data = json.loads(next(site.glob("*-zh.json")).read_text(encoding="utf-8"))
    return html, data, client


_GOOD_RESPONSE = json.dumps(
    {"headline": "今日社论标题", "body": "社论正文。", "story_indices": [0]}, ensure_ascii=False
)


def test_orchestrator_puts_editorial_on_the_front_page(tmp_path, monkeypatch):
    html, data, client = _run_pipeline(
        tmp_path, monkeypatch, editorial_enabled=True, response=_GOOD_RESPONSE
    )

    assert '<aside class="editorial"' in html and "今日社论标题" in html
    assert data["editorial"]["story_ids"] == ["story-1"]
    client.complete.assert_awaited_once()


def test_orchestrator_publishes_without_editorial_on_bad_response(tmp_path, monkeypatch):
    html, data, _ = _run_pipeline(
        tmp_path, monkeypatch, editorial_enabled=True, response="sorry, no JSON"
    )

    assert '<aside class="editorial"' not in html
    assert data["editorial"] is None
    assert "头条 1" in html


def test_orchestrator_skips_editorial_when_disabled(tmp_path, monkeypatch):
    html, data, client = _run_pipeline(
        tmp_path, monkeypatch, editorial_enabled=False, response=_GOOD_RESPONSE
    )

    assert '<aside class="editorial"' not in html and "editorial" not in data
    client.complete.assert_not_awaited()
