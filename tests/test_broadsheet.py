"""Tests for the interactive newspaper broadsheet renderer and pipeline wiring."""

import asyncio
from datetime import datetime, timezone
from io import StringIO
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import ValidationError
import pytest
from rich.console import Console

from src.ai.enricher import EnrichmentBatchResult
from src.models import (
    AIConfig,
    ArtifactSource,
    BroadsheetConfig,
    ClassificationResult,
    Config,
    ContentAnalysis,
    ContentArtifact,
    ContentBlock,
    ContentItem,
    ProcessingResult,
    SourcesConfig,
    SourceType,
)
from pathlib import Path
from src.orchestrator import HorizonOrchestrator
from src.rendering.broadsheet import BroadsheetRenderer
from src.rendering.site import BroadsheetSitePublisher
from src.storage.manager import StorageManager


def _make_item(
    idx: int,
    *,
    profile: str = "tech-news",
    source_type: SourceType = SourceType.HACKERNEWS,
    score: float = 8.5,
    title: str | None = None,
    url: str | None = None,
    tags: list[str] | None = None,
    language: str = "zh",
) -> ContentItem:
    resolved_title = title or f"快报测试新闻 {idx}"
    return ContentItem(
        id=f"{source_type.value}:item:{idx}",
        source_type=source_type,
        title=resolved_title,
        url=url or f"https://example.com/articles/{idx}",
        content=f"Body {idx}",
        author=f"author-{idx}",
        published_at=datetime(2026, 11, 23, 6, idx % 60, tzinfo=timezone.utc),
        metadata={"score": 100 + idx * 10, "descendants": 20 + idx, "category": "ai-news"},
        profile=profile,
        processing=ProcessingResult(
            classification=ClassificationResult(profile=profile, method="source_override"),
            analysis=ContentAnalysis(
                score=score,
                reason="important",
                summary=f"这是第 {idx} 条摘要。",
                tags=tags if tags is not None else ["AI", "系统"],
            ),
            artifacts={
                language: ContentArtifact(
                    language=language,
                    title=resolved_title,
                    blocks=[
                        ContentBlock(
                            id="summary",
                            title="核心摘要",
                            content=f"这是第 {idx} 条核心摘要内容。",
                            primary=True,
                        ),
                        ContentBlock(
                            id="background",
                            title="技术背景",
                            content=f"第 {idx} 条背景补充说明。",
                        ),
                    ],
                    sources=[
                        ArtifactSource(
                            id=f"src-{idx}",
                            title=f"参考来源 {idx}",
                            url=f"https://ref.example.com/{idx}",
                        )
                    ],
                )
            },
        ),
    )


def test_broadsheet_config_defaults_and_strict_fields():
    cfg = BroadsheetConfig()
    assert cfg.enabled is True
    assert cfg.copy_to_docs is True
    assert cfg.title is None

    with pytest.raises(ValidationError):
        BroadsheetConfig.model_validate({"unknown_key": True})


def test_broadsheet_builds_front_page_sections_and_wire():
    items = [
        _make_item(1, profile="tech-news", source_type=SourceType.HACKERNEWS, score=9.4),
        _make_item(2, profile="tech-news", source_type=SourceType.GITHUB, score=8.7),
        _make_item(3, profile="tech-blog", source_type=SourceType.RSS, score=9.0),
        _make_item(4, profile="finance-news", source_type=SourceType.OPENBB, score=8.2),
    ]
    renderer = BroadsheetRenderer(
        profile_names={
            "tech-news": {"default": "Technology News", "zh": "科技新闻"},
            "tech-blog": {"default": "Technical Blog", "zh": "技术长文"},
            "finance-news": {"default": "Finance News", "zh": "财经要闻"},
        },
        profile_order=["tech-news", "tech-blog", "finance-news"],
    )

    edition = renderer.build_edition_data(items, date="2026-11-23", total_fetched=40, language="zh")
    assert edition["meta"]["title"] == "地平线每日快报"
    assert edition["meta"]["selected_count"] == 4
    assert edition["meta"]["total_fetched"] == 40
    assert edition["meta"]["drop_rate"] == 90
    assert edition["front_page"]["lead_id"] == "story-1"
    assert [sec["profile_id"] for sec in edition["sections"]] == [
        "tech-news",
        "tech-blog",
        "finance-news",
    ]
    assert [sec["code"] for sec in edition["sections"]] == ["A2", "A3", "A4"]
    assert edition["meta"]["wire_code"] == "A5"
    assert edition["meta"]["index_code"] == "A6"

    rendered = renderer.render_html(items, date="2026-11-23", total_fetched=40, language="zh", edition_data=edition)
    assert "<!DOCTYPE html>" in rendered
    assert "地平线每日快报" in rendered
    assert "科技新闻" in rendered
    assert "技术长文" in rendered
    assert "财经要闻" in rendered
    assert "horizon-edition-data" in rendered
    assert "[hidden]" in rendered
    for idx in range(1, 5):
        assert f'href="https://example.com/articles/{idx}"' in rendered


def test_broadsheet_escapes_html_and_unsafe_urls():
    xss_item = _make_item(
        1,
        title='<script>alert("xss")</script> 标题',
        tags=['<img src=x onerror=alert(1)>'],
    )
    xss_item.metadata["discussion_url"] = "javascript:alert(1)"
    xss_item.processing.artifacts["zh"].sources.append(
        ArtifactSource(id="bad", title="Bad Link", url="javascript:void(0)")
    )

    renderer = BroadsheetRenderer()
    rendered = renderer.render_html([xss_item], date="2026-11-23", total_fetched=5, language="zh")

    assert '<script>alert("xss")</script>' not in rendered
    assert "&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;" in rendered
    assert "javascript:alert" not in rendered
    assert "javascript:void" not in rendered
    assert "\\u003cscript\\u003e" in rendered


def test_broadsheet_handles_empty_edition_and_english_mode():
    renderer = BroadsheetRenderer()
    rendered = renderer.render_html([], date="2026-11-23", total_fetched=25, language="en")

    assert "Horizon Daily" in rendered
    assert "A Quiet Edition" in rendered
    assert "25" in rendered


def test_storage_saves_broadsheet_html_and_json(tmp_path):
    storage = StorageManager(data_dir=str(tmp_path / "data"))
    html_path = storage.save_daily_broadsheet("2026-11-23", "<html>ok</html>", language="zh")
    json_path = storage.save_daily_json("2026-11-23", {"ok": True}, language="zh")

    assert html_path.name == "horizon-2026-11-23-zh.html"
    assert html_path.read_text(encoding="utf-8") == "<html>ok</html>"
    assert json_path.name == "horizon-2026-11-23-zh.json"
    assert json.loads(json_path.read_text(encoding="utf-8")) == {"ok": True}


def test_orchestrator_generates_broadsheet_and_excludes_failed_items(tmp_path, monkeypatch):
    config = Config(
        ai=AIConfig(provider="openai", model="test", api_key_env="TEST_KEY", languages=["zh"]),
        sources=SourcesConfig(),
        broadsheet=BroadsheetConfig(enabled=True, title="地平线每日快报", copy_to_docs=True),
    )
    orchestrator = HorizonOrchestrator(
        config,
        StorageManager(str(tmp_path / "data")),
        console=Console(file=StringIO()),
    )
    good = _make_item(1, title="入选中文头条", score=9.3)
    failed = _make_item(2, title="未增强失败条目", score=8.1)
    failed.processing.artifacts.clear()

    monkeypatch.setattr(orchestrator, "fetch_all_sources", AsyncMock(return_value=[good, failed]))
    monkeypatch.setattr(orchestrator, "analyze_items", AsyncMock(return_value=[good, failed]))
    monkeypatch.setattr(orchestrator, "select_digest_items", AsyncMock(return_value=SimpleNamespace(items=[good, failed])))
    monkeypatch.setattr(
        orchestrator,
        "enrich_items",
        AsyncMock(return_value=EnrichmentBatchResult(succeeded_ids=[good.id], failures={failed.id: "boom"})),
    )
    monkeypatch.chdir(tmp_path)

    asyncio.run(orchestrator.run())

    html_files = list(orchestrator.storage.summaries_dir.glob("*.html"))
    json_files = list(orchestrator.storage.summaries_dir.glob("*.json"))
    assert len(html_files) == 1
    assert len(json_files) == 1

    html_text = html_files[0].read_text(encoding="utf-8")
    assert "地平线每日快报" in html_text
    assert "入选中文头条" in html_text
    assert "未增强失败条目" not in html_text

    latest_doc = tmp_path / "docs" / "broadsheet" / "latest-zh.html"
    assert latest_doc.exists()
    assert "入选中文头条" in latest_doc.read_text(encoding="utf-8")


def test_orchestrator_respects_broadsheet_disabled(tmp_path, monkeypatch):
    config = Config(
        ai=AIConfig(provider="openai", model="test", api_key_env="TEST_KEY", languages=["zh"]),
        sources=SourcesConfig(),
        broadsheet=BroadsheetConfig(enabled=False),
    )
    orchestrator = HorizonOrchestrator(
        config,
        StorageManager(str(tmp_path / "data")),
        console=Console(file=StringIO()),
    )
    item = _make_item(1)
    monkeypatch.setattr(orchestrator, "fetch_all_sources", AsyncMock(return_value=[item]))
    monkeypatch.setattr(orchestrator, "analyze_items", AsyncMock(return_value=[item]))
    monkeypatch.setattr(orchestrator, "select_digest_items", AsyncMock(return_value=SimpleNamespace(items=[item])))
    monkeypatch.setattr(
        orchestrator,
        "enrich_items",
        AsyncMock(return_value=EnrichmentBatchResult(succeeded_ids=[item.id])),
    )
    monkeypatch.chdir(tmp_path)

    asyncio.run(orchestrator.run())

    assert len(list(orchestrator.storage.summaries_dir.glob("*.md"))) == 1
    assert not list(orchestrator.storage.summaries_dir.glob("*.html"))
    assert not (tmp_path / "docs" / "broadsheet").exists()


def test_site_publisher_merges_archive_manifest_and_writes_index(tmp_path):
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    # Pre-existing historical edition on disk (e.g. from gh-pages)
    (site_dir / "2026-11-22-zh.html").write_text("<html>old</html>", encoding="utf-8")

    publisher = BroadsheetSitePublisher(site_dir)
    renderer = BroadsheetRenderer(
        config=BroadsheetConfig(titles={"zh": "地平线每日快报", "en": "Horizon Daily"})
    )
    zh_item = _make_item(1, title="中文头条", score=9.2, language="zh")
    en_item = _make_item(1, title="English Lead", score=9.2, language="en")

    for lang, item in (("zh", zh_item), ("en", en_item)):
        ed = renderer.build_edition_data([item], date="2026-11-23", total_fetched=20, language=lang)
        html_doc = renderer.render_html(
            [item],
            date="2026-11-23",
            total_fetched=20,
            language=lang,
            edition_data=ed,
            available_languages=["zh", "en"],
        )
        assert './2026-11-23-zh.html' in html_doc
        assert './2026-11-23-en.html' in html_doc
        publisher.publish_edition(
            date="2026-11-23",
            language=lang,
            html_content=html_doc,
            edition_data=ed,
            is_default_language=(lang == "zh"),
            default_language="zh",
        )

    assert (site_dir / ".nojekyll").exists()
    assert (site_dir / "index.html").exists()
    assert "中文头条" in (site_dir / "index.html").read_text(encoding="utf-8")
    assert "English Lead" in (site_dir / "latest-en.html").read_text(encoding="utf-8")

    manifest = json.loads((site_dir / "editions.json").read_text(encoding="utf-8"))
    assert manifest["latest_date"] == "2026-11-23"
    assert manifest["default_language"] == "zh"
    assert [entry["date"] for entry in manifest["editions"]] == ["2026-11-23", "2026-11-22"]
    assert manifest["editions"][0]["languages"] == ["zh", "en"]
    assert manifest["editions"][0]["titles"] == {"zh": "地平线每日快报", "en": "Horizon Daily"}


def test_production_broadsheet_config_validates():
    repo_root = Path(__file__).resolve().parents[1]
    storage = StorageManager(
        data_dir=str(repo_root / "data"),
        config_path=str(repo_root / "data" / "config.broadsheet.json"),
    )
    cfg = storage.load_config()
    assert cfg.broadsheet.enabled is True
    assert cfg.broadsheet.site_dir == "docs/broadsheet"
    assert cfg.broadsheet.default_language == "zh"
    assert cfg.ai.languages == ["zh", "en"]

