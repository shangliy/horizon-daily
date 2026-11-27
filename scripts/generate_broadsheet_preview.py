"""Generate a live (or offline) preview edition of 地平线每日快报 (Horizon Broadsheet).

Usage:
  uv run python scripts/generate_broadsheet_preview.py --live    # Fetch real live items (default)
  uv run python scripts/generate_broadsheet_preview.py --mock    # Offline sample using real homepages
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
import re
import sys
from typing import List

from bs4 import BeautifulSoup
import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.models import (
    ArtifactSource,
    BroadsheetConfig,
    ClassificationResult,
    ContentAnalysis,
    ContentArtifact,
    ContentBlock,
    ContentItem,
    GitHubSourceConfig,
    HackerNewsConfig,
    OSSInsightConfig,
    ProcessingResult,
    RSSSourceConfig,
    SourceType,
)
from src.processing.content import split_content
from src.processing.profiles import ProfileRegistry
from src.rendering.broadsheet import BroadsheetRenderer
from src.rendering.site import BroadsheetSitePublisher
from src.scrapers.github import GitHubScraper
from src.scrapers.hackernews import HackerNewsScraper
from src.scrapers.ossinsight import OSSInsightScraper
from src.scrapers.rss import RSSScraper


_KEYWORD_TAGS = [
    ("ai", "AI"),
    ("llm", "LLM"),
    ("agent", "Agent"),
    ("claude", "Claude"),
    ("openai", "OpenAI"),
    ("gemini", "Gemini"),
    ("python", "Python"),
    ("rust", "Rust"),
    ("cuda", "CUDA"),
    ("gpu", "GPU"),
    ("nvidia", "NVIDIA"),
    ("linux", "Linux"),
    ("sqlite", "SQLite"),
    ("mcp", "MCP"),
    ("open source", "open-source"),
    ("fed", "Fed"),
    ("stock", "equities"),
    ("market", "tech-markets"),
    ("chip", "semiconductors"),
    ("cloud", "Cloud"),
]


def _plain_text(raw: str | None) -> str:
    if not raw:
        return ""
    if "<" in raw and ">" in raw:
        text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
    else:
        text = raw
    return re.sub(r"\s+", " ", text).strip()


def _infer_tags(item: ContentItem) -> list[str]:
    tags: list[str] = []
    hay = f"{item.title} {item.content or ''}".lower()
    for needle, label in _KEYWORD_TAGS:
        if needle in hay and label not in tags:
            tags.append(label)
        if len(tags) >= 4:
            break
    cat = item.metadata.get("category")
    if cat and str(cat) not in tags and len(tags) < 4:
        tags.append(str(cat))
    if not tags:
        tags.append(item.source_type.value)
    return tags[:4]


def _heuristic_score(item: ContentItem) -> float:
    meta = item.metadata
    if item.source_type == SourceType.HACKERNEWS:
        pts = max(int(meta.get("score") or 50), 1)
        desc = max(int(meta.get("descendants") or 0), 0)
        raw = 7.1 + min(2.4, math.log10(pts + desc * 1.5) * 0.72)
        return round(min(9.6, raw), 1)
    if item.source_type == SourceType.OSSINSIGHT:
        stars = max(int(meta.get("stars_gained") or meta.get("stars") or 20), 1)
        raw = 7.4 + min(1.8, math.log10(stars + 10) * 0.55)
        return round(min(9.2, raw), 1)
    if item.source_type == SourceType.GITHUB:
        return 8.5
    if item.profile == "tech-blog":
        return 8.6
    if item.profile == "finance-news":
        return 8.3
    return 8.2


def _build_artifact_for_lang(
    item: ContentItem,
    main_text: str,
    comments_text: str,
    language: str,
) -> ContentArtifact:
    is_zh = language.lower().startswith("zh")
    source_hint = item.metadata.get("feed_name") or item.author or item.source_type.value

    if main_text:
        summary = main_text[:280].rstrip() + ("…" if len(main_text) > 280 else "")
    elif is_zh:
        summary = f"来自 {source_hint} 的实时精选资讯，点击「阅读原文」查看完整报道与原始出处。"
    else:
        summary = f"Live curated dispatch from {source_hint}. Open the original link to read the full story."

    blocks = [
        ContentBlock(
            id="summary",
            title="核心摘要" if is_zh else "Summary",
            content=summary,
            primary=True,
        )
    ]

    if len(main_text) > 280:
        detail = main_text[280:900].strip()
        if detail:
            blocks.append(
                ContentBlock(
                    id="excerpt",
                    title="正文摘录" if is_zh else "Article Excerpt",
                    content=detail + ("…" if len(main_text) > 900 else ""),
                )
            )

    if comments_text:
        blocks.append(
            ContentBlock(
                id="community_discussion",
                title="社区讨论摘录" if is_zh else "Community Discussion",
                content=comments_text[:650].rstrip() + ("…" if len(comments_text) > 650 else ""),
            )
        )

    refs = [ArtifactSource(id="orig", title=item.title, url=str(item.url))]
    disc_url = item.metadata.get("discussion_url")
    if disc_url and str(disc_url) != str(item.url):
        refs.append(
            ArtifactSource(
                id="disc",
                title="原始社区讨论帖" if is_zh else "Community Discussion Thread",
                url=str(disc_url),
            )
        )

    return ContentArtifact(
        language=language,
        title=item.title,
        blocks=blocks,
        sources=refs,
    )


def _hydrate_live_item(item: ContentItem) -> ContentItem:
    profile_id = item.profile if isinstance(item.profile, str) and item.profile else "tech-news"
    parts = split_content(item.content)
    main_text = _plain_text(parts.main)
    comments_text = _plain_text(parts.comments)

    zh_artifact = _build_artifact_for_lang(item, main_text, comments_text, "zh")
    en_artifact = _build_artifact_for_lang(item, main_text, comments_text, "en")

    score = _heuristic_score(item)
    tags = _infer_tags(item)

    item.processing = ProcessingResult(
        classification=ClassificationResult(profile=profile_id, method="source_override"),
        analysis=ContentAnalysis(
            score=score,
            reason="Live fetched item ranked by engagement and source weight.",
            summary=en_artifact.blocks[0].content,
            tags=tags,
        ),
        artifacts={
            "zh": zh_artifact,
            "en": en_artifact,
        },
    )
    return item


async def fetch_live_items(hours: int = 72) -> tuple[List[ContentItem], int]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    hn_cfg = HackerNewsConfig(enabled=True, fetch_top_stories=25, min_score=60, category="ai-news", profile="tech-news")
    oss_cfg = OSSInsightConfig(
        enabled=True,
        period="past_24_hours",
        languages=["All", "Python", "TypeScript"],
        min_stars=10,
        max_items=6,
        category="open-source",
        profile="tech-blog",
    )
    rss_cfgs = [
        RSSSourceConfig(
            name="Simon Willison",
            url="https://simonwillison.net/atom/everything/",
            category="ai-tools",
            profile="tech-news",
        ),
        RSSSourceConfig(
            name="Sean Goedecke",
            url="https://www.seangoedecke.com/rss.xml",
            category="software-engineering",
            profile="tech-blog",
        ),
        RSSSourceConfig(
            name="NVIDIA Developer Blog",
            url="https://developer.nvidia.com/blog/tag/cuda/feed/",
            category="cuda",
            profile="tech-blog",
        ),
        RSSSourceConfig(
            name="CNBC Finance",
            url="https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
            category="finance",
            profile="finance-news",
        ),
        RSSSourceConfig(
            name="CNBC Tech",
            url="https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910",
            category="tech-markets",
            profile="finance-news",
        ),
    ]
    gh_cfgs = [
        GitHubSourceConfig(type="repo_releases", owner="astral-sh", repo="uv", category="dev-tools", profile="tech-news"),
        GitHubSourceConfig(type="repo_releases", owner="vllm-project", repo="vllm", category="llm-inference", profile="tech-news"),
    ]

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        results = await asyncio.gather(
            HackerNewsScraper(hn_cfg, client).fetch(since),
            RSSScraper(rss_cfgs, client).fetch(since),
            OSSInsightScraper(oss_cfg, client).fetch(since),
            GitHubScraper(gh_cfgs, client).fetch(since),
            return_exceptions=True,
        )

    fetched: List[ContentItem] = []
    for res in results:
        if isinstance(res, Exception):
            print(f"[warn] scraper failed: {res}", file=sys.stderr)
            continue
        if res.failures:
            for src_name, err in res.failures.items():
                print(f"[warn] partial failure {src_name}: {err}", file=sys.stderr)
        fetched.extend(res.items)

    # Deduplicate by URL
    seen_urls: set[str] = set()
    unique_items: List[ContentItem] = []
    for item in fetched:
        key = str(item.url).rstrip("/")
        if key in seen_urls:
            continue
        seen_urls.add(key)
        unique_items.append(_hydrate_live_item(item))

    # Balance across profiles so all sections look crisp and every URL is real
    quotas = {"tech-news": 7, "tech-blog": 5, "finance-news": 5}
    selected: List[ContentItem] = []
    for profile_id, limit in quotas.items():
        bucket = [
            it for it in unique_items
            if it.processing and it.processing.classification.profile == profile_id
        ]
        bucket.sort(
            key=lambda it: (
                it.processing.analysis.score if it.processing and it.processing.analysis else 0.0,
                it.published_at,
            ),
            reverse=True,
        )
        selected.extend(bucket[:limit])

    return selected, len(fetched)


def build_offline_sample_items() -> list[ContentItem]:
    """Offline fallback items whose URLs all point to real, live canonical pages."""
    now = datetime.now(timezone.utc)
    raw = [
        (
            "github:repo:horizon",
            SourceType.GITHUB,
            "Horizon — AI 驱动的多源信息聚合与双语日报系统",
            "https://github.com/shangliy/horizon-daily",
            "shangliy/horizon-daily",
            "tech-news",
            9.4,
            "支持 10 类信息源、Profile 声明式规则引擎、多模型降级链、MCP Server 与单页交互式报纸快报。",
            ["Horizon", "AI", "开源"],
            {"repo": "shangliy/horizon-daily", "category": "ai-tools"},
        ),
        (
            "rss:simon:home",
            SourceType.RSS,
            "Simon Willison's Weblog — AI 工具链与 LLM 工程前沿笔记",
            "https://simonwillison.net/",
            "Simon Willison",
            "tech-news",
            9.0,
            "持续追踪大模型能力评测、提示词工程、Datasette 与个人开发者工具生态的深度观察。",
            ["LLM", "AI", "工具链"],
            {"feed_name": "Simon Willison", "category": "ai-tools"},
        ),
        (
            "github:repo:uv",
            SourceType.GITHUB,
            "Astral uv — 极速 Rust 编写的 Python 包与项目管理工具",
            "https://github.com/astral-sh/uv",
            "astral-sh/uv",
            "tech-news",
            8.8,
            "统一替代 pip、pip-tools、poetry 与 pyenv 的新一代 Python 工具链，原生支持锁文件与虚拟环境管理。",
            ["Python", "uv", "Rust"],
            {"repo": "astral-sh/uv", "category": "dev-tools"},
        ),
        (
            "rss:vllm:home",
            SourceType.RSS,
            "vLLM — 高吞吐、显存友好的大模型推理与服务引擎",
            "https://github.com/vllm-project/vllm",
            "vllm-project",
            "tech-blog",
            9.1,
            "基于 PagedAttention 的开源 LLM 推理引擎，持续推进长上下文、量化推理与分布式解码优化。",
            ["LLM", "vLLM", "GPU"],
            {"feed_name": "vLLM", "category": "llm-inference"},
        ),
        (
            "rss:seangoedecke:home",
            SourceType.RSS,
            "Sean Goedecke — 大型软件工程与分布式系统实战随笔",
            "https://www.seangoedecke.com/",
            "Sean Goedecke",
            "tech-blog",
            8.7,
            "聚焦大厂后端架构、系统稳定性、技术决策与工程组织实践的深度长文博客。",
            ["系统架构", "工程实践"],
            {"feed_name": "Sean Goedecke", "category": "software-engineering"},
        ),
        (
            "rss:cnbc:finance",
            SourceType.RSS,
            "CNBC Markets & Finance — 全球科技股与宏观金融快讯",
            "https://www.cnbc.com/finance/",
            "CNBC Finance",
            "finance-news",
            8.5,
            "追踪美联储利率动向、AI 芯片供应链、科技巨头财报与全球资本市场动态。",
            ["美股", "宏观", "科技股"],
            {"feed_name": "CNBC Finance", "category": "finance"},
        ),
    ]
    items: list[ContentItem] = []
    for idx, (iid, stype, title, url, author, prof, score, summary, tags, meta) in enumerate(raw):
        item = ContentItem(
            id=iid,
            source_type=stype,
            title=title,
            url=url,
            content=summary,
            author=author,
            published_at=now - timedelta(hours=idx + 1),
            metadata=meta,
            profile=prof,
            processing=ProcessingResult(
                classification=ClassificationResult(profile=prof, method="source_override"),
                analysis=ContentAnalysis(score=score, reason="Canonical live URL", summary=summary, tags=tags),
                artifacts={
                    lang: ContentArtifact(
                        language=lang,
                        title=title,
                        blocks=[ContentBlock(id="summary", title="核心摘要" if lang == "zh" else "Summary", content=summary, primary=True)],
                        sources=[ArtifactSource(id="orig", title=title, url=url)],
                    )
                    for lang in ("zh", "en")
                },
            ),
        )
        items.append(item)
    return items


def build_sample_editorial(records: list[dict], lang: str) -> dict | None:
    """Placeholder editorial so the preview shows the layout without an AI call."""
    if len(records) < 3:
        return None
    top = sorted(records, key=lambda r: r["score"] or 0, reverse=True)[:3]
    if lang.startswith("zh"):
        headline = "示例社论：这里是当天的编辑部观点"
        body = (
            "这是版面预览用的占位文字，不是模型写的社论。正式运行时，模型会从当天入选的条目里挑出两到四条，"
            "写一段把它们放在一起看意味着什么的短评。\n\n"
            "下方“文中提及”的链接会打开对应条目的阅读抽屉。"
        )
    else:
        headline = "Sample editorial: the day's argument goes here"
        body = (
            "This is placeholder text for the layout preview, not a model-written editorial. In a real run "
            "the model picks two to four of the day's stories and argues what they mean together.\n\n"
            "The links under “Stories discussed” open each story in the reading drawer."
        )
    return {"headline": headline, "body": body, "story_ids": [r["id"] for r in top]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 地平线每日快报 preview HTML")
    parser.add_argument("--live", action="store_true", help="Fetch real live items from Horizon scrapers")
    parser.add_argument("--mock", action="store_true", help="Use offline canonical sample items")
    parser.add_argument("--hours", type=int, default=72, help="Lookback window in hours for --live mode")
    parser.add_argument("--lang", default="both", help="Output language (zh, en, or both)")
    args = parser.parse_args()

    use_live = args.live or not args.mock
    now = datetime.now(timezone.utc)
    edition_date = now.strftime("%Y-%m-%d")

    if use_live:
        items, total_fetched = asyncio.run(fetch_live_items(hours=args.hours))
        if not items:
            print("[warn] live fetch returned 0 items, falling back to offline canonical items", file=sys.stderr)
            items = build_offline_sample_items()
            total_fetched = len(items)
    else:
        items = build_offline_sample_items()
        total_fetched = len(items)

    profiles = ProfileRegistry.load(ROOT / "profiles", "tech-news")
    languages = ["zh", "en"] if args.lang == "both" else [args.lang]
    renderer = BroadsheetRenderer(
        profile_names=profiles.names,
        profile_order=["tech-news", "tech-blog", "finance-news"],
        config=BroadsheetConfig(
            titles={"zh": "地平线每日快报", "en": "Horizon Daily"},
            site_dir=str(ROOT / "docs" / "broadsheet"),
            default_language="zh",
        ),
    )
    publisher = BroadsheetSitePublisher(ROOT / "docs" / "broadsheet")
    default_lang = "zh" if "zh" in languages else languages[0]

    for lang in languages:
        edition_data = renderer.build_edition_data(
            items,
            date=edition_date,
            total_fetched=max(total_fetched, len(items)),
            language=lang,
            generated_at=now,
        )
        edition_data["editorial"] = build_sample_editorial(edition_data["items"], lang)
        html_content = renderer.render_html(
            items,
            date=edition_date,
            total_fetched=max(total_fetched, len(items)),
            language=lang,
            generated_at=now,
            edition_data=edition_data,
            available_languages=languages,
        )
        written = publisher.publish_edition(
            date=edition_date,
            language=lang,
            html_content=html_content,
            edition_data=edition_data,
            is_default_language=(lang == default_lang),
            default_language=default_lang,
        )
        # Keep preview-{lang}.html synced for direct file preview
        preview_path = ROOT / "docs" / "broadsheet" / f"preview-{lang}.html"
        preview_path.write_text(html_content, encoding="utf-8")
        print(
            f"Published {lang.upper()} broadsheet: {written['dated_html']} "
            f"({len(items)} items from {total_fetched} fetched, {len(html_content):,} bytes)"
        )


if __name__ == "__main__":
    main()
