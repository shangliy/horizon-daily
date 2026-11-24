"""Single-page interactive newspaper broadsheet renderer for Horizon."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import html
import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from ..ai.localization import normalize_language
from ..ai.summarizer import DailySummarizer, _pangu, _safe_url
from ..models import BroadsheetConfig, ContentItem


_WEEKDAYS_ZH = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
_WEEKDAYS_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTHS_EN = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

_SOURCE_LABELS: Dict[str, Dict[str, str]] = {
    "zh": {
        "hackernews": "Hacker News",
        "rss": "RSS 订阅",
        "reddit": "Reddit",
        "github": "GitHub",
        "twitter": "X / Twitter",
        "telegram": "Telegram",
        "openbb": "OpenBB 金融",
        "ossinsight": "OSS Insight",
        "gdelt": "GDELT 全球",
        "google_news": "Google News",
    },
    "en": {
        "hackernews": "Hacker News",
        "rss": "RSS Feed",
        "reddit": "Reddit",
        "github": "GitHub",
        "twitter": "X / Twitter",
        "telegram": "Telegram",
        "openbb": "OpenBB Finance",
        "ossinsight": "OSS Insight",
        "gdelt": "GDELT Global",
        "google_news": "Google News",
    },
}

_COPY: Dict[str, Dict[str, str]] = {
    "zh": {
        "default_title": "地平线每日快报",
        "default_overline": "HORIZON DAILY BROADSHEET",
        "default_subtitle": "你只需享受新闻，剩下交给 Horizon — 多源聚合、AI 研判与深度背景每日速递。",
        "default_edition_label": "HORIZON · 全球科技与产业快报",
        "ear_left_kicker": "今日精选",
        "ear_left_sub": "从 {total} 条信源中筛选",
        "ear_left_link": "查看全量目录 →",
        "ear_right_kicker": "信号指数",
        "ear_right_sub": "最高 {top} · {sources} 类信源",
        "ear_right_link": "淘汰率 {drop_rate}%",
        "vol_label": "第 I 卷 · {date}",
        "updated_label": "更新于 {time} · 由 Horizon AI 编排",
        "nav_front": "头版",
        "nav_wire": "全球电讯",
        "nav_index": "全量检索",
        "lead_kicker": "今日头条",
        "left_col_title": "要闻速递",
        "left_col_link": "按版面浏览 →",
        "right_col_title": "深度与观察",
        "right_col_link": "查看电讯 →",
        "read_full": "展开深度简报 →",
        "original_link": "阅读原文 ↗",
        "source_link": "原文 ↗",
        "discussion_link": "社区讨论 ↗",
        "discuss_short": "讨论 ↗",
        "spotlight_left_kicker": "深度必读",
        "spotlight_left_title": "给工程师与研究者",
        "spotlight_right_kicker": "高热讨论",
        "spotlight_right_title": "社区正在争论什么",
        "desk_kicker": "HORIZON 情报台",
        "desk_title": "今日信源漏斗与分布",
        "desk_desc": "AI 自动完成多源抓取、跨源 URL 去重、语义聚类与背景检索，仅保留高信号条目。",
        "desk_cta": "打开全量检索台",
        "section_kicker_tpl": "{code} · 专题版面",
        "wire_kicker": "THE WIRE · 多源实时电讯",
        "wire_title": "全球信息源速览",
        "wire_desc": "按渠道高密度梳理今日入选资讯，涵盖技术社区、开源项目与行业媒体。",
        "wire_col_1": "社区热榜 · HN / Reddit",
        "wire_col_2": "开源与一线 · GitHub / X",
        "wire_col_3": "深度媒体 · RSS / 财经 / 全球",
        "wire_more": "全部 →",
        "index_kicker": "ARCHIVE DESK · 交互检索",
        "index_title": "本期全量资讯检索台",
        "index_desc": "按关键词、版面、信源或 AI 标签即时过滤，点击任意条目在右侧报刊抽屉阅读全文。",
        "search_placeholder": "搜索标题、摘要、标签或来源… (快捷键 /)",
        "search_btn": "检索",
        "clear_btn": "重置",
        "all_label": "全部",
        "sort_score": "按 AI 评分",
        "sort_time": "按发布时间",
        "no_match": "未找到匹配的资讯条目，请尝试清除筛选条件。",
        "empty_title": "今日情报台较平静，暂无达到阈值的重点资讯",
        "empty_desc": "本次共采集 {total} 条原始内容，但均未超过当前 Profile 设定的重要度门槛。可适当下调 threshold 或扩充订阅源后重新生成。",
        "btn_search": "检索",
        "btn_print": "打印版",
        "archive_label": "往期",
        "archive_latest": "最新",
        "theme_light": "浅色新闻纸",
        "theme_dark": "深色炭墨",
        "theme_system": "跟随系统",
        "home_pill": "↑ 地平线每日快报 · 头版",
        "drawer_score": "AI 重要度评分",
        "drawer_refs": "延伸参考与核验来源",
        "drawer_tags": "主题标签",
        "drawer_prev": "← 上一条",
        "drawer_next": "下一条 →",
        "drawer_close": "关闭 (Esc)",
        "footer_note": "由 Horizon 自动抓取、AI 分析、去重与背景增强生成 · 纯静态单页快报，支持离线阅读与打印。",
        "score_unit": "分",
        "items_unit": "条",
    },
    "en": {
        "default_title": "Horizon Daily",
        "default_overline": "AI-CURATED BROADSHEET EDITION",
        "default_subtitle": "Just enjoy the news — Horizon gathers, ranks, deduplicates, and enriches your daily signal.",
        "default_edition_label": "HORIZON · GLOBAL TECH & SIGNAL",
        "ear_left_kicker": "TODAY",
        "ear_left_sub": "selected from {total} items",
        "ear_left_link": "Browse full index →",
        "ear_right_kicker": "SIGNAL INDEX",
        "ear_right_sub": "Peak {top} · {sources} sources",
        "ear_right_link": "{drop_rate}% noise filtered",
        "vol_label": "Vol. I · {date}",
        "updated_label": "Updated {time} · Curated by Horizon AI",
        "nav_front": "Front Page",
        "nav_wire": "The Wire",
        "nav_index": "Full Index",
        "lead_kicker": "TOP STORY",
        "left_col_title": "DISPATCHES",
        "left_col_link": "All sections →",
        "right_col_title": "ANALYSIS & BRIEFINGS",
        "right_col_link": "The Wire →",
        "read_full": "Read full briefing →",
        "original_link": "Original ↗",
        "source_link": "Source ↗",
        "discussion_link": "Discussion ↗",
        "discuss_short": "Discuss ↗",
        "spotlight_left_kicker": "DEEP READS",
        "spotlight_left_title": "For Engineers & Builders",
        "spotlight_right_kicker": "HIGH ENGAGEMENT",
        "spotlight_right_title": "What Communities Debate",
        "desk_kicker": "HORIZON DESK",
        "desk_title": "Today's Signal Funnel",
        "desk_desc": "Multi-source ingestion, cross-source URL merge, AI topic clustering, and on-demand context enrichment.",
        "desk_cta": "Open Filter Desk",
        "section_kicker_tpl": "{code} · EDITION SECTION",
        "wire_kicker": "THE WIRE · MULTI-SOURCE FEED",
        "wire_title": "What Builders Are Reading",
        "wire_desc": "A high-density three-column wire organized across communities, open source, and publications.",
        "wire_col_1": "COMMUNITY · HN & REDDIT",
        "wire_col_2": "OPEN SOURCE & X",
        "wire_col_3": "PUBLICATIONS & MARKETS",
        "wire_more": "All →",
        "index_kicker": "ARCHIVE DESK · LIVE FILTER",
        "index_title": "Complete Edition Index",
        "index_desc": "Filter instantly by keyword, profile section, source, or tag. Click any story to open the reading drawer.",
        "search_placeholder": "Search headlines, summaries, tags, sources… (press /)",
        "search_btn": "SEARCH",
        "clear_btn": "RESET",
        "all_label": "Everything",
        "sort_score": "By AI Score",
        "sort_time": "By Time",
        "no_match": "No stories match the current filters.",
        "empty_title": "A Quiet Edition — No Items Crossed Today's Threshold",
        "empty_desc": "Horizon analyzed {total} fetched items, none of which met the active profile thresholds. Consider lowering the threshold or adding more sources.",
        "btn_search": "Search",
        "btn_print": "Print",
        "archive_label": "Archive",
        "archive_latest": "Latest",
        "theme_light": "Light newsprint",
        "theme_dark": "Dark charcoal",
        "theme_system": "System theme",
        "home_pill": "↑ Horizon Daily · FRONT PAGE",
        "drawer_score": "AI SIGNAL SCORE",
        "drawer_refs": "References & Context Sources",
        "drawer_tags": "Tags",
        "drawer_prev": "← Previous",
        "drawer_next": "Next →",
        "drawer_close": "Close (Esc)",
        "footer_note": "Automatically fetched, ranked, deduplicated, and enriched by Horizon · Self-contained single-page broadsheet.",
        "score_unit": "/10",
        "items_unit": "items",
    },
}


def _esc(value: object) -> str:
    """HTML-escape untrusted text for safe insertion into HTML text and attributes."""
    return html.escape(str(value), quote=True)


def _safe_json_for_script(payload: Any) -> str:
    """Serialize JSON so it can never prematurely close a <script> tag."""
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return (
        raw.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _is_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff\u3400-\u4dbf]", text))


def _format_date_display(date_str: str, language: str) -> str:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return date_str
    if language == "zh":
        weekday = _WEEKDAYS_ZH[dt.weekday()]
        return f"{dt.year}年{dt.month}月{dt.day}日 {weekday}"
    weekday = _WEEKDAYS_EN[dt.weekday()]
    month = _MONTHS_EN[dt.month - 1]
    return f"{weekday}, {month} {dt.day}, {dt.year}"


def _format_item_time(dt: Optional[datetime], language: str) -> str:
    if not dt:
        return ""
    if language == "zh":
        return f"{dt.month}月{dt.day}日 {dt:%H:%M}"
    day = dt.strftime("%d").lstrip("0")
    return dt.strftime(f"%b {day} · %H:%M")


def _domain_of(url: str) -> str:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _clean_text(text: str, language: str) -> str:
    normalized = normalize_language(text or "", language).strip()
    if language == "zh":
        return _pangu(normalized)
    return normalized


def _truncate(text: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: max(limit - 1, 1)].rstrip(" ，,;；:：") + "…"


class BroadsheetRenderer:
    """Renders Horizon ContentItems as an interactive single-page newspaper broadsheet."""

    def __init__(
        self,
        profile_names: Optional[Dict[str, Dict[str, str]]] = None,
        profile_order: Optional[List[str]] = None,
        config: Optional[BroadsheetConfig] = None,
    ):
        self.profile_names = profile_names or {}
        self.profile_order = profile_order or []
        self.config = config or BroadsheetConfig()
        self._summarizer = DailySummarizer(
            profile_names=self.profile_names,
            profile_order=self.profile_order,
        )

    def build_edition_data(
        self,
        items: List[ContentItem],
        date: str,
        total_fetched: int,
        language: str = "zh",
        *,
        generated_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Build a JSON-serializable structured representation of one newspaper edition."""
        lang_key = "zh" if language.lower().startswith("zh") else "en"
        copy = _COPY[lang_key]
        source_labels = _SOURCE_LABELS[lang_key]
        now = generated_at or datetime.now(timezone.utc)
        updated_str = now.strftime("%H:%M UTC")

        view = self._summarizer.build_view(items, language)

        records: List[Dict[str, Any]] = []
        group_map: Dict[str, Dict[str, Any]] = {}
        tag_counter: Counter[str] = Counter()
        source_counter: Counter[str] = Counter()

        for group in view.groups:
            group_entry = {
                "profile_id": group.profile_id,
                "name": _clean_text(group.name, language),
                "item_ids": [],
            }
            group_map[group.profile_id] = group_entry

            for view_item in group.items:
                item = view_item.item
                artifact = item.processing.artifacts.get(language) if item.processing else None
                analysis = item.processing.analysis if item.processing else None

                title = _clean_text(view_item.title, language)
                numeric_score: Optional[float] = (
                    float(analysis.score)
                    if analysis and analysis.score is not None
                    else None
                )
                score_display = (
                    f"{numeric_score:.1f}" if numeric_score is not None else "—"
                )

                blocks: List[Dict[str, Any]] = []
                primary_summary = ""
                if artifact and artifact.blocks:
                    for block in artifact.blocks:
                        b_title = _clean_text(block.title, language)
                        b_content = _clean_text(block.content, language)
                        if block.primary and not primary_summary:
                            primary_summary = b_content
                        blocks.append(
                            {
                                "id": block.id,
                                "title": b_title,
                                "content": b_content,
                                "primary": block.primary,
                            }
                        )
                if not primary_summary and analysis and analysis.summary:
                    primary_summary = _clean_text(analysis.summary, language)

                secondary_blocks = [b for b in blocks if not b["primary"]]
                if not secondary_blocks and len(blocks) > 1:
                    secondary_blocks = blocks[1:]

                raw_url = str(item.url)
                safe_url = _safe_url(raw_url)
                meta = item.metadata or {}
                raw_discussion = meta.get("discussion_url")
                safe_discussion = (
                    _safe_url(raw_discussion)
                    if raw_discussion and str(raw_discussion) != raw_url
                    else None
                )

                src_type = item.source_type.value
                source_counter[src_type] += 1
                sub_source = (
                    meta.get("feed_name")
                    or (f"r/{meta['subreddit']}" if meta.get("subreddit") else None)
                    or meta.get("channel")
                    or meta.get("repo")
                    or meta.get("watchlist")
                    or item.author
                    or _domain_of(raw_url)
                    or source_labels.get(src_type, src_type)
                )

                tags = [
                    _clean_text(tag, language)
                    for tag in (analysis.tags if analysis else [])
                    if str(tag).strip()
                ]
                for tag in tags:
                    tag_counter[tag] += 1

                engagement = self._extract_engagement(meta, lang_key)
                engagement_weight = (
                    int(meta.get("score") or 0)
                    + int(meta.get("descendants") or 0) * 2
                    + int(meta.get("favorite_count") or 0)
                    + int(meta.get("retweet_count") or 0) * 2
                    + int(meta.get("stars") or 0)
                    + (50 if safe_discussion else 0)
                )

                references = []
                if artifact and artifact.sources:
                    for src in artifact.sources:
                        ref_url = _safe_url(src.url)
                        references.append(
                            {
                                "id": src.id,
                                "title": _clean_text(src.title, language),
                                "url": ref_url,
                                "domain": _domain_of(src.url) if ref_url else "",
                            }
                        )

                record_id = f"story-{view_item.global_index}"
                record = {
                    "id": record_id,
                    "item_id": item.id,
                    "rank": view_item.global_index,
                    "group_index": view_item.index,
                    "profile_id": group.profile_id,
                    "profile_name": group_entry["name"],
                    "title": title,
                    "summary": primary_summary,
                    "score": numeric_score,
                    "score_display": score_display,
                    "reason": _clean_text(analysis.reason, language) if analysis else "",
                    "url": safe_url,
                    "domain": _domain_of(raw_url),
                    "discussion_url": safe_discussion,
                    "source_type": src_type,
                    "source_label": source_labels.get(src_type, src_type),
                    "sub_source": str(sub_source),
                    "author": str(item.author or ""),
                    "category": str(meta.get("category") or ""),
                    "published_at": item.published_at.isoformat() if item.published_at else "",
                    "time_display": _format_item_time(item.published_at, lang_key),
                    "tags": tags,
                    "blocks": blocks,
                    "secondary_blocks": secondary_blocks,
                    "references": references,
                    "engagement": engagement,
                    "engagement_weight": engagement_weight,
                }
                records.append(record)
                group_entry["item_ids"].append(record_id)

        # Rank records globally by AI score descending for Front Page placement
        ranked_records = sorted(
            records,
            key=lambda r: (r["score"] if r["score"] is not None else -1.0, -r["rank"]),
            reverse=True,
        )

        selected_count = len(records)
        scores = [r["score"] for r in records if r["score"] is not None]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
        top_score = round(max(scores), 1) if scores else 0.0
        drop_rate = (
            round((1 - selected_count / total_fetched) * 100)
            if total_fetched > 0 and total_fetched >= selected_count
            else 0
        )

        front_page = self._compose_front_page(ranked_records)
        wire_columns = self._compose_wire(records, lang_key)

        # Assign newspaper section page codes (A1, A2, ..., An)
        sections: List[Dict[str, Any]] = []
        page_num = 2
        for group in view.groups:
            g = group_map[group.profile_id]
            sections.append(
                {
                    "code": f"A{page_num}",
                    "dom_id": f"sec-{re.sub(r'[^a-zA-Z0-9_-]+', '-', group.profile_id)}",
                    "profile_id": group.profile_id,
                    "name": g["name"],
                    "item_ids": g["item_ids"],
                }
            )
            page_num += 1

        wire_code = f"A{page_num}"
        index_code = f"A{page_num + 1}"

        ticker_items = self._compose_ticker(ranked_records, tag_counter, lang_key)

        title = (
            self.config.titles.get(language)
            or self.config.titles.get(lang_key)
            or self.config.title
            or copy["default_title"]
        )
        subtitle = self.config.subtitle or copy["default_subtitle"]
        edition_label = self.config.edition_label or copy["default_edition_label"]

        source_breakdown = [
            {
                "source_type": src,
                "label": source_labels.get(src, src),
                "count": count,
                "pct": round(count / selected_count * 100) if selected_count else 0,
            }
            for src, count in source_counter.most_common()
        ]

        return {
            "meta": {
                "title": title,
                "overline": copy["default_overline"],
                "subtitle": subtitle,
                "edition_label": edition_label,
                "date": date,
                "date_display": _format_date_display(date, lang_key),
                "updated_at": updated_str,
                "language": language,
                "lang_key": lang_key,
                "total_fetched": total_fetched,
                "selected_count": selected_count,
                "avg_score": avg_score,
                "top_score": top_score,
                "drop_rate": drop_rate,
                "source_count": len(source_counter),
                "profile_count": len(sections),
                "wire_code": wire_code,
                "index_code": index_code,
            },
            "ticker": ticker_items,
            "front_page": front_page,
            "sections": sections,
            "wire": wire_columns,
            "source_breakdown": source_breakdown,
            "top_tags": [{"tag": t, "count": c} for t, c in tag_counter.most_common(16)],
            "items": records,
        }

    @staticmethod
    def _extract_engagement(meta: Dict[str, Any], lang_key: str) -> List[str]:
        parts: List[str] = []
        if meta.get("score"):
            parts.append(f"{meta['score']} 热度" if lang_key == "zh" else f"{meta['score']} pts")
        if meta.get("descendants"):
            parts.append(f"{meta['descendants']} 评论" if lang_key == "zh" else f"{meta['descendants']} comments")
        if meta.get("stars"):
            parts.append(f"★ {meta['stars']}")
        if meta.get("favorite_count"):
            parts.append(f"{meta['favorite_count']} 赞" if lang_key == "zh" else f"{meta['favorite_count']} likes")
        if meta.get("retweet_count"):
            parts.append(f"{meta['retweet_count']} 转发" if lang_key == "zh" else f"{meta['retweet_count']} RTs")
        if meta.get("views"):
            parts.append(f"{meta['views']} 浏览" if lang_key == "zh" else f"{meta['views']} views")
        return parts

    @staticmethod
    def _compose_front_page(ranked_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not ranked_records:
            return {
                "lead_id": None,
                "left_ids": [],
                "right_ids": [],
                "spotlight_left_ids": [],
                "spotlight_right_ids": [],
            }

        lead = ranked_records[0]
        remaining = ranked_records[1:]

        # Prefer complementary profiles (e.g. tech-blog / finance-news) for right column
        lead_profile = lead["profile_id"]
        other_profile_items = [r for r in remaining if r["profile_id"] != lead_profile]
        same_profile_items = [r for r in remaining if r["profile_id"] == lead_profile]

        left_items: List[Dict[str, Any]] = []
        right_items: List[Dict[str, Any]] = []

        for r in same_profile_items:
            if len(left_items) < 3:
                left_items.append(r)
        for r in other_profile_items:
            if len(right_items) < 2:
                right_items.append(r)

        used = {lead["id"], *(r["id"] for r in left_items), *(r["id"] for r in right_items)}
        for r in remaining:
            if r["id"] in used:
                continue
            if len(left_items) < 3:
                left_items.append(r)
                used.add(r["id"])
            elif len(right_items) < 2:
                right_items.append(r)
                used.add(r["id"])

        # Center lower spotlight tables:
        # Left = Deep Reads (prefer tech-blog or multi-block rich stories)
        # Right = Community Buzz (highest engagement_weight or discussion_url)
        deep_candidates = sorted(
            [r for r in ranked_records if r["id"] != lead["id"]],
            key=lambda r: (
                1 if "blog" in r["profile_id"] else 0,
                len(r["secondary_blocks"]),
                r["score"] or 0.0,
            ),
            reverse=True,
        )
        spotlight_left = [r["id"] for r in deep_candidates[:4]]

        buzz_candidates = sorted(
            [r for r in ranked_records if r["id"] != lead["id"]],
            key=lambda r: (
                r["engagement_weight"],
                1 if r["discussion_url"] else 0,
                r["score"] or 0.0,
            ),
            reverse=True,
        )
        spotlight_right = [r["id"] for r in buzz_candidates[:4]]

        return {
            "lead_id": lead["id"],
            "left_ids": [r["id"] for r in left_items],
            "right_ids": [r["id"] for r in right_items],
            "spotlight_left_ids": spotlight_left,
            "spotlight_right_ids": spotlight_right,
        }

    @staticmethod
    def _compose_wire(records: List[Dict[str, Any]], lang_key: str) -> List[Dict[str, Any]]:
        copy = _COPY[lang_key]
        col1_sources = {"hackernews", "reddit"}
        col2_sources = {"github", "ossinsight", "twitter"}

        col1: List[str] = []
        col2: List[str] = []
        col3: List[str] = []

        for r in records:
            src = r["source_type"]
            if src in col1_sources:
                col1.append(r["id"])
            elif src in col2_sources:
                col2.append(r["id"])
            else:
                col3.append(r["id"])

        # Rebalance only if a single column holds everything (e.g. RSS-only config)
        non_empty = sum(bool(c) for c in (col1, col2, col3))
        if non_empty == 1 and len(records) >= 3:
            all_ids = [r["id"] for r in records]
            col1 = all_ids[0::3]
            col2 = all_ids[1::3]
            col3 = all_ids[2::3]

        return [
            {"id": "wire-community", "title": copy["wire_col_1"], "style": "numbered", "item_ids": col1[:10]},
            {"id": "wire-builders", "title": copy["wire_col_2"], "style": "badged", "item_ids": col2[:8]},
            {"id": "wire-editorial", "title": copy["wire_col_3"], "style": "kicker", "item_ids": col3[:8]},
        ]

    @staticmethod
    def _compose_ticker(
        ranked_records: List[Dict[str, Any]],
        tag_counter: Counter[str],
        lang_key: str,
    ) -> List[Dict[str, Any]]:
        ticker: List[Dict[str, Any]] = []
        for tag, count in tag_counter.most_common(10):
            ticker.append(
                {
                    "kind": "tag",
                    "label": f"#{tag}",
                    "tag": tag,
                    "metric": f"{count} {_COPY[lang_key]['items_unit']}",
                    "delta": "up",
                }
            )
        for rec in ranked_records[:6]:
            ticker.append(
                {
                    "kind": "story",
                    "story_id": rec["id"],
                    "label": _truncate(rec["title"], 28 if lang_key == "zh" else 42),
                    "metric": f"▲ {rec['score_display']}",
                    "delta": "hot" if (rec["score"] or 0) >= 8.5 else "up",
                }
            )
        return ticker

    def render_html(
        self,
        items: List[ContentItem],
        date: str,
        total_fetched: int,
        language: str = "zh",
        *,
        generated_at: Optional[datetime] = None,
        edition_data: Optional[Dict[str, Any]] = None,
        available_languages: Optional[List[str]] = None,
    ) -> str:
        """Render a complete, self-contained interactive newspaper broadsheet HTML document."""
        data = edition_data or self.build_edition_data(
            items, date, total_fetched, language=language, generated_at=generated_at
        )
        meta = data["meta"]
        lang_key = meta["lang_key"]
        copy = _COPY[lang_key]
        items_by_id = {r["id"]: r for r in data["items"]}

        title_text = meta["title"]
        is_cjk_title = _is_cjk(title_text)
        nameplate_class = "mast-nameplate mast-nameplate-cjk" if is_cjk_title else "mast-nameplate mast-nameplate-latin"

        # Bilingual switcher when multiple languages are built in the same edition
        langs = list(dict.fromkeys(available_languages or [language]))
        lang_switch_html = ""
        if len(langs) > 1:
            lang_links = []
            for code in langs:
                label = "中文" if code.lower().startswith("zh") else code.upper()
                active_cls = " is-active" if code == language else ""
                href = f"./{meta['date']}-{code}.html"
                lang_links.append(
                    f'<a class="seg-btn seg-link{active_cls}" href="{_esc(href)}" '
                    f'data-lang-switch="{_esc(code)}">{_esc(label)}</a>'
                )
            lang_switch_html = (
                f'<div class="seg-group" role="group" aria-label="Language">{"".join(lang_links)}</div>'
            )

        # Navigation items + floating pager entries
        nav_entries: List[tuple[str, str, str]] = [
            ("A1", "#front-page", copy["nav_front"]),
        ]
        for sec in data["sections"]:
            nav_entries.append((sec["code"], f"#{sec['dom_id']}", sec["name"]))
        if data["items"]:
            nav_entries.append((meta["wire_code"], "#the-wire", copy["nav_wire"]))
            nav_entries.append((meta["index_code"], "#archive-desk", copy["nav_index"]))

        nav_html = "".join(
            f'<a href="{_esc(href)}" data-section-link="{_esc(code)}">'
            f'<span class="nav-code">{_esc(code)}</span> {_esc(label)}</a>'
            for code, href, label in nav_entries
        )

        pager_menu_html = "".join(
            f'<a class="pager-item" href="{_esc(href)}" data-pager-code="{_esc(code)}">'
            f'<span class="pager-code">{_esc(code)}</span>'
            f'<span class="pager-label">{_esc(label)}</span></a>'
            for code, href, label in nav_entries
        )

        ticker_html = self._render_ticker(data["ticker"])
        front_page_html = self._render_front_page(data, items_by_id, copy)
        sections_html = self._render_profile_sections(data, items_by_id, copy)
        wire_html = self._render_wire_section(data, items_by_id, copy) if data["items"] else ""
        index_html = self._render_index_section(data, copy) if data["items"] else ""

        html_lang = "zh-CN" if lang_key == "zh" else "en"
        embedded_json = _safe_json_for_script(data)
        embedded_copy = _safe_json_for_script(copy)

        return f"""<!DOCTYPE html>
<html lang="{html_lang}" data-theme="system" data-font="normal">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_esc(title_text)} — {_esc(meta["date_display"])}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Libre+Franklin:wght@400;500;600;700;800&family=Noto+Sans+SC:wght@400;500;600;700&family=Noto+Serif+SC:wght@600;700;900&family=Pirata+One&family=Playfair+Display:ital,wght@0,600;0,700;0,800;0,900;1,600&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&display=swap" rel="stylesheet">
  <style>
{_BROADSHEET_CSS}
  </style>
</head>
<body>
  <div class="paper-grain" aria-hidden="true"></div>

  <a class="home-pill" id="homePill" href="#top" aria-label="{_esc(copy['home_pill'])}">
    {_esc(copy['home_pill'])}
  </a>

  <div class="sheet" id="top">
    <!-- Top Utility Bar -->
    <header class="util-bar">
      <div class="util-left">{_esc(meta["edition_label"])}</div>
      <div class="util-right">
        <label class="archive-wrap" id="editionArchiveWrap" hidden>
          <span class="archive-prefix">{_esc(copy["archive_label"])}</span>
          <select id="editionArchiveSelect" class="archive-select" aria-label="{_esc(copy['archive_label'])}"></select>
        </label>
        {lang_switch_html}
        <button type="button" class="util-btn" id="jumpSearchBtn" title="Search (/)">
          <span>⌕</span> {_esc(copy["btn_search"])} <kbd>/</kbd>
        </button>
        <div class="seg-group" role="group" aria-label="Font size">
          <button type="button" class="seg-btn" data-font-set="normal" title="Standard font">A</button>
          <button type="button" class="seg-btn" data-font-set="large" title="Large font">A+</button>
        </div>
        <div class="seg-group" role="group" aria-label="Color theme">
          <button type="button" class="seg-btn" data-theme-set="light" title="{_esc(copy['theme_light'])}">☀︎</button>
          <button type="button" class="seg-btn" data-theme-set="dark" title="{_esc(copy['theme_dark'])}">☾</button>
          <button type="button" class="seg-btn" data-theme-set="system" title="{_esc(copy['theme_system'])}">◐</button>
        </div>
        <button type="button" class="util-btn util-btn-accent" id="printBtn">{_esc(copy["btn_print"])}</button>
      </div>
    </header>

    <!-- Newspaper Masthead -->
    <div class="masthead">
      <aside class="ear ear-left">
        <div class="ear-kicker">{_esc(copy["ear_left_kicker"])}</div>
        <div class="ear-num">{meta["selected_count"]}</div>
        <div class="ear-sub">{_esc(copy["ear_left_sub"].format(total=meta["total_fetched"]))}</div>
        <a class="ear-link" href="#archive-desk">{_esc(copy["ear_left_link"])}</a>
      </aside>

      <div class="mast-center">
        <div class="mast-overline">{_esc(meta["overline"])}</div>
        <h1 class="{nameplate_class}">{_esc(title_text)}</h1>
        <p class="mast-motto">{_esc(meta["subtitle"])}</p>
      </div>

      <aside class="ear ear-right">
        <div class="ear-kicker">{_esc(copy["ear_right_kicker"])}</div>
        <div class="ear-num">{meta["avg_score"]:.1f}<span class="ear-unit">/10</span></div>
        <div class="ear-sub">{_esc(copy["ear_right_sub"].format(top=f"{meta['top_score']:.1f}", sources=meta["source_count"]))}</div>
        <div class="ear-link-muted">{_esc(copy["ear_right_link"].format(drop_rate=meta["drop_rate"]))}</div>
      </aside>
    </div>

    <!-- Dateline Bar -->
    <div class="dateline">
      <div class="dateline-left">{_esc(copy["vol_label"].format(date=meta["date"]))}</div>
      <div class="dateline-center">{_esc(meta["date_display"])}</div>
      <div class="dateline-right">{_esc(copy["updated_label"].format(time=meta["updated_at"]))}</div>
    </div>

    <!-- Double-Rule Section Nav -->
    <nav class="section-nav" aria-label="Edition sections">
      {nav_html}
    </nav>

    <!-- Continuous Signal Ticker Tape -->
    {ticker_html}

    <!-- Main Broadsheet Canvas -->
    <main>
      {front_page_html}
      {sections_html}
      {wire_html}
      {index_html}
    </main>

    <!-- Colophon Footer -->
    <footer class="colophon">
      <div class="colophon-wordmark">{_esc(title_text)}</div>
      <p class="colophon-meta">
        {_esc(meta["date_display"])} · {_esc(copy["ear_left_sub"].format(total=meta["total_fetched"]))} · {meta["selected_count"]} {_esc(copy["items_unit"])}
      </p>
      <p class="colophon-note">{_esc(copy["footer_note"])}</p>
    </footer>
  </div>

  <!-- Floating Bottom-Right Section Pager -->
  <div class="pager-wrap" id="pagerWrap">
    <div class="pager-menu" id="pagerMenu" role="menu" hidden>
      {pager_menu_html}
    </div>
    <button type="button" class="pager-btn" id="pagerBtn" aria-expanded="false" aria-controls="pagerMenu">
      <span class="pager-btn-code" id="pagerActiveCode">A1</span>
      <span class="pager-btn-label" id="pagerActiveLabel">{_esc(copy["nav_front"])}</span>
      <span class="pager-caret" aria-hidden="true">▲</span>
    </button>
  </div>

  <!-- Newspaper Reading Drawer -->
  <div class="drawer-backdrop" id="drawerBackdrop" hidden></div>
  <aside class="drawer" id="articleDrawer" role="dialog" aria-modal="true" aria-labelledby="drawerTitle" hidden>
    <div class="drawer-topbar">
      <div class="drawer-kicker" id="drawerKicker"></div>
      <button type="button" class="drawer-close" id="drawerClose">{_esc(copy["drawer_close"])}</button>
    </div>
    <div class="drawer-scroll" id="drawerBody">
      <div class="drawer-head">
        <div class="drawer-badges" id="drawerBadges"></div>
        <h2 class="drawer-title" id="drawerTitle"></h2>
        <div class="drawer-meta" id="drawerMeta"></div>
        <div class="drawer-head-links" id="drawerHeadLinks"></div>
      </div>
      <div class="drawer-blocks" id="drawerBlocks"></div>
      <div class="drawer-refs" id="drawerRefs" hidden></div>
      <div class="drawer-tags" id="drawerTags" hidden></div>
    </div>
    <div class="drawer-footer">
      <button type="button" class="drawer-nav-btn" id="drawerPrev">{_esc(copy["drawer_prev"])}</button>
      <div class="drawer-ext-links" id="drawerExtLinks"></div>
      <button type="button" class="drawer-nav-btn" id="drawerNext">{_esc(copy["drawer_next"])}</button>
    </div>
  </aside>

  <script id="horizon-edition-data" type="application/json">{embedded_json}</script>
  <script id="horizon-edition-copy" type="application/json">{embedded_copy}</script>
  <script>
{_BROADSHEET_JS}
  </script>
</body>
</html>
"""

    def _render_ticker(self, ticker_items: List[Dict[str, Any]]) -> str:
        if not ticker_items:
            return ""
        chunks: List[str] = []
        for entry in ticker_items:
            delta_cls = "t-hot" if entry["delta"] == "hot" else "t-up"
            if entry["kind"] == "tag":
                chunks.append(
                    f'<button type="button" class="ticker-item" data-filter-tag="{_esc(entry["tag"])}">'
                    f'<span class="t-name">{_esc(entry["label"])}</span>'
                    f'<span class="{delta_cls}">{_esc(entry["metric"])}</span>'
                    "</button>"
                )
            else:
                chunks.append(
                    f'<button type="button" class="ticker-item" data-open-story="{_esc(entry["story_id"])}">'
                    f'<span class="t-name">{_esc(entry["label"])}</span>'
                    f'<span class="{delta_cls}">{_esc(entry["metric"])}</span>'
                    "</button>"
                )
        track = "".join(chunks)
        return (
            '<div class="ticker" aria-label="Trending signals">'
            f'<div class="ticker-track">{track}{track}</div>'
            "</div>"
        )

    def _render_front_page(
        self,
        data: Dict[str, Any],
        items_by_id: Dict[str, Dict[str, Any]],
        copy: Dict[str, str],
    ) -> str:
        fp = data["front_page"]
        meta = data["meta"]
        lead_id = fp["lead_id"]

        if not lead_id:
            return (
                '<section class="band front-page" id="front-page" data-page-code="A1" '
                f'data-page-label="{_esc(copy["nav_front"])}">'
                '<div class="empty-edition">'
                f'<div class="kicker hot-kicker">● {_esc(copy["lead_kicker"])}</div>'
                f'<h2>{_esc(copy["empty_title"])}</h2>'
                f'<p>{_esc(copy["empty_desc"].format(total=meta["total_fetched"]))}</p>'
                "</div></section>"
            )

        lead = items_by_id[lead_id]
        left_stories = [items_by_id[i] for i in fp["left_ids"] if i in items_by_id]
        right_stories = [items_by_id[i] for i in fp["right_ids"] if i in items_by_id]
        spot_left = [items_by_id[i] for i in fp["spotlight_left_ids"] if i in items_by_id]
        spot_right = [items_by_id[i] for i in fp["spotlight_right_ids"] if i in items_by_id]

        left_html = "".join(self._render_side_story(story, copy) for story in left_stories)
        right_html = "".join(self._render_side_story(story, copy) for story in right_stories)

        # Lead story inline highlight deck (up to 2 secondary blocks)
        lead_blocks_html = ""
        if lead["secondary_blocks"]:
            block_cards = []
            for blk in lead["secondary_blocks"][:2]:
                block_cards.append(
                    '<div class="lead-deck-cell">'
                    f'<div class="kicker">{_esc(blk["title"])}</div>'
                    f'<p>{_esc(_truncate(blk["content"], 220))}</p>'
                    "</div>"
                )
            lead_blocks_html = f'<div class="lead-deck-grid">{"".join(block_cards)}</div>'

        lead_tags_html = "".join(
            f'<button type="button" class="tag-chip" data-filter-tag="{_esc(tag)}">#{_esc(tag)}</button>'
            for tag in lead["tags"][:5]
        )

        lead_ext_html = ""
        if lead["url"]:
            lead_ext_html += (
                f'<a class="editorial-link" href="{lead["url"]}" target="_blank" '
                f'rel="noopener noreferrer">{_esc(copy["original_link"])}</a>'
            )
        if lead["discussion_url"]:
            lead_ext_html += (
                f'<a class="editorial-link" href="{lead["discussion_url"]}" target="_blank" '
                f'rel="noopener noreferrer">{_esc(copy["discussion_link"])}</a>'
            )

        lead_engagement = (
            f' · {" · ".join(_esc(e) for e in lead["engagement"])}'
            if lead["engagement"]
            else ""
        )

        # Lower center curated 2-column spotlight tables
        spotlight_html = ""
        if spot_left or spot_right:
            spot_left_rows = "".join(self._render_spotlight_row(s) for s in spot_left)
            spot_right_rows = "".join(self._render_spotlight_row(s) for s in spot_right)
            spotlight_html = (
                '<div class="spotlight-grid">'
                '<div class="spotlight-col">'
                f'<div class="kicker hot-kicker">{_esc(copy["spotlight_left_kicker"])}</div>'
                f'<h3 class="spotlight-heading">{_esc(copy["spotlight_left_title"])}</h3>'
                f'<div class="spotlight-list">{spot_left_rows}</div>'
                "</div>"
                '<div class="spotlight-col">'
                f'<div class="kicker accent-kicker">{_esc(copy["spotlight_right_kicker"])}</div>'
                f'<h3 class="spotlight-heading">{_esc(copy["spotlight_right_title"])}</h3>'
                f'<div class="spotlight-list">{spot_right_rows}</div>'
                "</div>"
                "</div>"
            )

        # Right column editorial signal desk (homage to buildweek.ai print ad box)
        bars_html = "".join(
            '<div class="funnel-row">'
            f'<div class="funnel-label"><span>{_esc(src["label"])}</span>'
            f'<span class="mono">{src["count"]}</span></div>'
            f'<div class="funnel-track"><div class="funnel-fill" style="width:{max(src["pct"], 8)}%"></div></div>'
            "</div>"
            for src in data["source_breakdown"][:5]
        )
        desk_box_html = (
            '<div class="desk-box">'
            f'<div class="desk-kicker">{_esc(copy["desk_kicker"])}</div>'
            f'<h3 class="desk-title">{_esc(copy["desk_title"])}</h3>'
            f'<p class="desk-desc">{_esc(copy["desk_desc"])}</p>'
            f'<div class="funnel-bars">{bars_html}</div>'
            f'<a class="solid-cta" href="#archive-desk">{_esc(copy["desk_cta"])}</a>'
            "</div>"
        )

        first_sec_href = f"#{data['sections'][0]['dom_id']}" if data["sections"] else "#archive-desk"

        return f"""
      <section class="band front-page" id="front-page" data-page-code="A1" data-page-label="{_esc(copy['nav_front'])}">
        <div class="fp-grid">
          <div class="fp-col fp-left">
            <div class="col-header">
              <span>{_esc(copy["left_col_title"])}</span>
              <a href="{_esc(first_sec_href)}">{_esc(copy["left_col_link"])}</a>
            </div>
            {left_html}
          </div>

          <article class="fp-col fp-center">
            <div class="lead-kicker-row">
              <span class="breaking-dot" aria-hidden="true"></span>
              <span class="kicker hot-kicker">{_esc(copy["lead_kicker"])} · {_esc(lead["profile_name"])}</span>
              <span class="score-pill score-hot">{_esc(lead["score_display"])}/10</span>
            </div>
            <h2 class="lead-headline">
              <button type="button" class="headline-trigger" data-open-story="{_esc(lead['id'])}">{_esc(lead["title"])}</button>
            </h2>
            <p class="lead-summary">{_esc(lead["summary"])}</p>
            <div class="story-meta lead-meta">
              <span>{_esc(lead["source_label"])} · {_esc(lead["sub_source"])}</span>
              <span>{_esc(lead["time_display"])}{lead_engagement}</span>
            </div>
            {lead_blocks_html}
            <div class="lead-actions">
              <button type="button" class="solid-cta solid-cta-inline" data-open-story="{_esc(lead['id'])}">{_esc(copy["read_full"])}</button>
              <div class="lead-ext">{lead_ext_html}</div>
            </div>
            <div class="tag-row">{lead_tags_html}</div>
            {spotlight_html}
          </article>

          <div class="fp-col fp-right">
            <div class="col-header">
              <span>{_esc(copy["right_col_title"])}</span>
              <a href="#the-wire">{_esc(copy["right_col_link"])}</a>
            </div>
            {right_html}
            {desk_box_html}
          </div>
        </div>
      </section>
        """

    @staticmethod
    def _render_inline_links(story: Dict[str, Any], copy: Dict[str, str]) -> str:
        links: List[str] = []
        if story.get("url"):
            links.append(
                f'<a class="inline-ext-link" href="{story["url"]}" target="_blank" '
                f'rel="noopener noreferrer">{_esc(copy["source_link"])}</a>'
            )
        if story.get("discussion_url"):
            links.append(
                f'<a class="inline-ext-link" href="{story["discussion_url"]}" target="_blank" '
                f'rel="noopener noreferrer">{_esc(copy["discuss_short"])}</a>'
            )
        if not links:
            return ""
        return f'<span class="inline-links">{"".join(links)}</span>'

    def _render_side_story(self, story: Dict[str, Any], copy: Dict[str, str]) -> str:
        score_cls = "score-hot" if (story["score"] or 0) >= 8.5 else "score-accent"
        tags_html = "".join(
            f'<button type="button" class="tag-chip" data-filter-tag="{_esc(tag)}">#{_esc(tag)}</button>'
            for tag in story["tags"][:3]
        )
        links_html = self._render_inline_links(story, copy)
        return (
            '<article class="side-story">'
            '<div class="story-kicker-row">'
            f'<span class="story-kicker">{_esc(story["source_label"])} · {_esc(story["time_display"])}</span>'
            f'<span class="score-pill {score_cls}">{_esc(story["score_display"])}</span>'
            "</div>"
            '<h3 class="side-headline">'
            f'<button type="button" class="headline-trigger" data-open-story="{_esc(story["id"])}">{_esc(story["title"])}</button>'
            "</h3>"
            f'<p class="side-summary">{_esc(_truncate(story["summary"], 130))}</p>'
            '<div class="story-byline-row">'
            f'<span class="story-byline">{_esc(story["profile_name"])} · {_esc(story["sub_source"])}</span>'
            f"{links_html}"
            "</div>"
            f'<div class="tag-row">{tags_html}</div>'
            "</article>"
        )

    def _render_spotlight_row(self, story: Dict[str, Any]) -> str:
        ext = (
            f'<a class="spot-ext" href="{story["url"]}" target="_blank" '
            f'rel="noopener noreferrer" title="{_esc(story["domain"] or story["url"])}">↗</a>'
            if story.get("url")
            else ""
        )
        return (
            '<div class="spotlight-row">'
            f'<button type="button" class="spot-btn" data-open-story="{_esc(story["id"])}">'
            f'<span class="spot-score">{_esc(story["score_display"])}</span>'
            '<span class="spot-body">'
            f'<span class="spot-title">{_esc(story["title"])}</span>'
            f'<span class="spot-meta">{_esc(story["sub_source"])} · {_esc(story["profile_name"])}</span>'
            "</span>"
            "</button>"
            f"{ext}"
            "</div>"
        )

    def _render_profile_sections(
        self,
        data: Dict[str, Any],
        items_by_id: Dict[str, Dict[str, Any]],
        copy: Dict[str, str],
    ) -> str:
        html_parts: List[str] = []
        for sec in data["sections"]:
            sec_items = [items_by_id[i] for i in sec["item_ids"] if i in items_by_id]
            if not sec_items:
                continue
            grid_cls = "section-grid-2" if len(sec_items) <= 2 else "section-grid-3"
            cards = []
            for idx, story in enumerate(sec_items, start=1):
                score_cls = "score-hot" if (story["score"] or 0) >= 8.5 else "score-accent"
                teaser = ""
                if story["secondary_blocks"]:
                    first_blk = story["secondary_blocks"][0]
                    teaser = (
                        '<div class="card-teaser">'
                        f'<strong>「{_esc(first_blk["title"])}」</strong> '
                        f'{_esc(_truncate(first_blk["content"], 115))}'
                        "</div>"
                    )
                tags_html = "".join(
                    f'<button type="button" class="tag-chip" data-filter-tag="{_esc(tag)}">#{_esc(tag)}</button>'
                    for tag in story["tags"][:4]
                )
                links_html = self._render_inline_links(story, copy)
                cards.append(
                    '<article class="section-card">'
                    '<div class="card-top">'
                    f'<span class="card-num">{idx:02d}</span>'
                    f'<span class="story-kicker">{_esc(story["source_label"])} · {_esc(story["sub_source"])}</span>'
                    f'<span class="score-pill {score_cls}">{_esc(story["score_display"])}</span>'
                    "</div>"
                    '<h3 class="card-headline">'
                    f'<button type="button" class="headline-trigger" data-open-story="{_esc(story["id"])}">{_esc(story["title"])}</button>'
                    "</h3>"
                    f'<p class="card-summary">{_esc(_truncate(story["summary"], 180))}</p>'
                    f"{teaser}"
                    '<div class="card-foot">'
                    f'<div class="tag-row">{tags_html}</div>'
                    '<div class="card-actions">'
                    f"{links_html}"
                    f'<button type="button" class="text-action" data-open-story="{_esc(story["id"])}">{_esc(copy["read_full"])}</button>'
                    "</div>"
                    "</div>"
                    "</article>"
                )

            kicker = copy["section_kicker_tpl"].format(code=sec["code"])
            html_parts.append(
                f'<section class="band profile-band" id="{_esc(sec["dom_id"])}" '
                f'data-page-code="{_esc(sec["code"])}" data-page-label="{_esc(sec["name"])}">'
                '<div class="band-head">'
                f'<div class="kicker">{_esc(kicker)}</div>'
                '<div class="band-title-row">'
                f'<h2 class="band-title">{_esc(sec["name"])}</h2>'
                f'<span class="band-count">{len(sec_items)} {_esc(copy["items_unit"])}</span>'
                "</div>"
                "</div>"
                f'<div class="section-grid {grid_cls}">{"".join(cards)}</div>'
                "</section>"
            )
        return "".join(html_parts)

    def _render_wire_section(
        self,
        data: Dict[str, Any],
        items_by_id: Dict[str, Dict[str, Any]],
        copy: Dict[str, str],
    ) -> str:
        wire_cols_html: List[str] = []
        for col in data["wire"]:
            col_items = [items_by_id[i] for i in col["item_ids"] if i in items_by_id]
            entries: List[str] = []
            for idx, story in enumerate(col_items, start=1):
                links_html = self._render_inline_links(story, copy)
                if col["style"] == "numbered":
                    meta_bits = [story["domain"] or story["sub_source"], *story["engagement"], story["time_display"]]
                    meta_line = " · ".join(bit for bit in meta_bits if bit)
                    entries.append(
                        '<div class="wire-entry wire-numbered">'
                        f'<span class="wire-rank">{idx}</span>'
                        '<div class="wire-content">'
                        f'<button type="button" class="wire-title" data-open-story="{_esc(story["id"])}">{_esc(story["title"])}</button>'
                        f'<div class="wire-meta-row"><span class="wire-meta">{_esc(meta_line)}</span>{links_html}</div>'
                        "</div>"
                        "</div>"
                    )
                elif col["style"] == "badged":
                    badge_cls = "wire-badge-yc" if story["source_type"] in {"github", "ossinsight"} else "wire-badge-accent"
                    entries.append(
                        '<div class="wire-entry">'
                        f'<div class="wire-kicker">{_esc(story["time_display"])} · {_esc(story["score_display"])}/10</div>'
                        '<div class="wire-head-inline">'
                        f'<button type="button" class="wire-title" data-open-story="{_esc(story["id"])}">{_esc(story["title"])}</button>'
                        f'<span class="wire-badge {badge_cls}">{_esc(story["source_label"])}</span>'
                        "</div>"
                        f'<p class="wire-blurb">{_esc(_truncate(story["summary"], 90))}</p>'
                        f'<div class="wire-meta-row"><span class="wire-meta">{_esc(story["domain"] or story["sub_source"])}</span>{links_html}</div>'
                        "</div>"
                    )
                else:
                    kicker_label = (story["category"] or story["profile_name"]).upper()
                    entries.append(
                        '<div class="wire-entry">'
                        f'<div class="wire-kicker">{_esc(kicker_label)} · {_esc(story["time_display"])}</div>'
                        f'<button type="button" class="wire-title" data-open-story="{_esc(story["id"])}">{_esc(story["title"])}</button>'
                        f'<div class="wire-meta-row"><span class="wire-meta">{_esc(story["sub_source"])} · AI {_esc(story["score_display"])}</span>{links_html}</div>'
                        "</div>"
                    )

            if not entries:
                entries.append('<div class="wire-empty">—</div>')

            wire_cols_html.append(
                '<div class="wire-col">'
                '<div class="col-header">'
                f'<span>{_esc(col["title"])}</span>'
                f'<a href="#archive-desk">{_esc(copy["wire_more"])}</a>'
                "</div>"
                f'{"".join(entries)}'
                "</div>"
            )

        wire_code = data["meta"]["wire_code"]
        return (
            f'<section class="band wire-band" id="the-wire" data-page-code="{_esc(wire_code)}" '
            f'data-page-label="{_esc(copy["nav_wire"])}">'
            '<div class="band-head">'
            f'<div class="kicker">{_esc(copy["wire_kicker"])}</div>'
            f'<h2 class="band-title">{_esc(copy["wire_title"])}</h2>'
            f'<p class="band-desc">{_esc(copy["wire_desc"])}</p>'
            "</div>"
            f'<div class="wire-grid">{"".join(wire_cols_html)}</div>'
            "</section>"
        )

    def _render_index_section(self, data: Dict[str, Any], copy: Dict[str, str]) -> str:
        index_code = data["meta"]["index_code"]
        profile_pills = [
            f'<button type="button" class="filter-pill is-active" data-filter-profile="all">'
            f'{_esc(copy["all_label"])} <span class="pill-count">{len(data["items"])}</span></button>'
        ]
        for sec in data["sections"]:
            profile_pills.append(
                f'<button type="button" class="filter-pill" data-filter-profile="{_esc(sec["profile_id"])}">'
                f'{_esc(sec["name"])} <span class="pill-count">{len(sec["item_ids"])}</span></button>'
            )

        source_pills = [
            f'<button type="button" class="filter-pill filter-pill-sm is-active" data-filter-source="all">'
            f'{_esc(copy["all_label"])}</button>'
        ]
        for src in data["source_breakdown"]:
            source_pills.append(
                f'<button type="button" class="filter-pill filter-pill-sm" data-filter-source="{_esc(src["source_type"])}">'
                f'{_esc(src["label"])} <span class="pill-count">{src["count"]}</span></button>'
            )

        # Server-rendered initial ledger rows (hydrated & filtered live by JS)
        ledger_rows = []
        for story in data["items"]:
            score_cls = "score-hot" if (story["score"] or 0) >= 8.5 else "score-accent"
            links_html = self._render_inline_links(story, copy)
            ledger_rows.append(
                f'<article class="ledger-item" data-story-id="{_esc(story["id"])}">'
                '<div class="ledger-top">'
                f'<span class="ledger-meta">{_esc(story["source_label"])} · {_esc(story["sub_source"])} · {_esc(story["time_display"])}</span>'
                f'<span class="score-pill {score_cls}">{_esc(story["score_display"])}</span>'
                "</div>"
                '<h3 class="ledger-title">'
                f'<button type="button" class="headline-trigger" data-open-story="{_esc(story["id"])}">{_esc(story["title"])}</button>'
                "</h3>"
                f'<p class="ledger-summary">{_esc(_truncate(story["summary"], 140))}</p>'
                '<div class="ledger-foot">'
                f'<span class="profile-tag">{_esc(story["profile_name"])}</span>'
                f'<span class="ledger-tags">{" ".join("#" + _esc(t) for t in story["tags"][:3])}</span>'
                f"{links_html}"
                "</div>"
                "</article>"
            )

        return (
            f'<section class="band index-band" id="archive-desk" data-page-code="{_esc(index_code)}" '
            f'data-page-label="{_esc(copy["nav_index"])}">'
            '<div class="band-head">'
            f'<div class="kicker">{_esc(copy["index_kicker"])}</div>'
            f'<h2 class="band-title">{_esc(copy["index_title"])}</h2>'
            f'<p class="band-desc">{_esc(copy["index_desc"])}</p>'
            "</div>"
            '<div class="filter-controls">'
            '<div class="search-row">'
            f'<input type="search" id="archiveSearch" class="search-input" placeholder="{_esc(copy["search_placeholder"])}" autocomplete="off">'
            f'<select id="archiveSort" class="sort-select" aria-label="Sort stories">'
            f'<option value="score">{_esc(copy["sort_score"])}</option>'
            f'<option value="time">{_esc(copy["sort_time"])}</option>'
            "</select>"
            f'<button type="button" id="archiveReset" class="util-btn">{_esc(copy["clear_btn"])}</button>'
            "</div>"
            f'<div class="pill-bar" id="profileFilterBar">{"".join(profile_pills)}</div>'
            f'<div class="pill-bar pill-bar-sub" id="sourceFilterBar">{"".join(source_pills)}</div>'
            '<div class="active-tag-bar" id="activeTagBar" hidden></div>'
            "</div>"
            f'<div class="ledger-grid" id="archiveLedger" aria-live="polite">{"".join(ledger_rows)}</div>'
            "</section>"
        )


_BROADSHEET_CSS = r"""
:root {
  --paper: #efe6d2;
  --ink: #1a1712;
  --ink-2: #3b352b;
  --mute: #6e6556;
  --rule: #1a1712;
  --hair: #cfc3a8;
  --accent: #2c5d82;
  --accent-ink: #ffffff;
  --hot: #a8231b;
  --ad: #e6dbc2;
  --chip: #e2d6bb;
  --up: #2e7d32;
  --down: #b3261e;
  --badge-hot-bg: #f3dad6;
  --badge-accent-bg: #d9e6ef;
  --badge-yc-bg: #d95b26;
  --grain: 0.44;
  --shadow: rgba(26, 23, 18, 0.22);

  --mast-latin: "Pirata One", "Old English Text MT", Georgia, serif;
  --mast-cjk: "Noto Serif SC", "Songti SC", "STSong", "Playfair Display", Georgia, serif;
  --head: "Playfair Display", "Noto Serif SC", Georgia, serif;
  --body: "Source Serif 4", "Noto Serif SC", Georgia, serif;
  --sans: "Libre Franklin", "Noto Sans SC", "PingFang SC", "Helvetica Neue", Arial, sans-serif;
  --base-size: 16.5px;
}

:root[data-font="large"] {
  --base-size: 18.5px;
}

:root[data-theme="dark"] {
  --paper: #1e1c19;
  --ink: #d8d2c4;
  --ink-2: #b2ab9c;
  --mute: #8b8578;
  --rule: #a9a293;
  --hair: #3a3731;
  --accent: #8fb8d8;
  --accent-ink: #141210;
  --hot: #ff7a6e;
  --ad: #26231f;
  --chip: #2d2a25;
  --up: #7cc882;
  --down: #f08a80;
  --badge-hot-bg: rgba(255, 122, 110, 0.16);
  --badge-accent-bg: rgba(143, 184, 216, 0.16);
  --badge-yc-bg: #df6c36;
  --grain: 0;
  --shadow: rgba(0, 0, 0, 0.55);
}

@media (prefers-color-scheme: dark) {
  :root[data-theme="system"] {
    --paper: #1e1c19;
    --ink: #d8d2c4;
    --ink-2: #b2ab9c;
    --mute: #8b8578;
    --rule: #a9a293;
    --hair: #3a3731;
    --accent: #8fb8d8;
    --accent-ink: #141210;
    --hot: #ff7a6e;
    --ad: #26231f;
    --chip: #2d2a25;
    --up: #7cc882;
    --down: #f08a80;
    --badge-hot-bg: rgba(255, 122, 110, 0.16);
    --badge-accent-bg: rgba(143, 184, 216, 0.16);
    --badge-yc-bg: #df6c36;
    --grain: 0;
    --shadow: rgba(0, 0, 0, 0.55);
  }
}

*, *::before, *::after {
  box-sizing: border-box;
}

[hidden] {
  display: none !important;
}

html {
  scroll-behavior: smooth;
  background: var(--paper);
  color: var(--ink);
  font-size: var(--base-size);
}

body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--body);
  line-height: 1.58;
  -webkit-font-smoothing: antialiased;
  overflow-x: hidden;
}

.paper-grain {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 900;
  opacity: var(--grain);
  mix-blend-mode: multiply;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='180' height='180' filter='url(%23n)' opacity='0.22'/%3E%3C/svg%3E");
}

a {
  color: inherit;
  text-decoration: none;
}

button {
  font: inherit;
  color: inherit;
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
}

:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.sheet {
  max-width: 1240px;
  margin: 0 auto;
  padding: 0 24px 88px;
}

/* Top Utility Bar */
.util-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 0 10px;
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.util-left {
  color: var(--ink-2);
}

.util-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.util-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 11px;
  border: 1px solid var(--ink);
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  transition: background 0.15s, color 0.15s;
}

.util-btn:hover {
  background: var(--chip);
}

.util-btn kbd {
  font-family: var(--sans);
  font-size: 10px;
  padding: 0 4px;
  border: 1px solid var(--hair);
  color: var(--mute);
}

.util-btn-accent {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-ink);
}

.util-btn-accent:hover {
  filter: brightness(1.08);
  background: var(--accent);
}

.seg-group {
  display: inline-flex;
  border: 1px solid var(--ink);
}

.seg-btn {
  padding: 5px 9px;
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 700;
  border-right: 1px solid var(--hair);
  color: var(--ink-2);
  transition: background 0.15s, color 0.15s;
}

.seg-btn:last-child {
  border-right: 0;
}

.seg-btn.is-active {
  background: var(--ink);
  color: var(--paper);
}

.seg-link {
  display: inline-flex;
  align-items: center;
  text-decoration: none;
}

.archive-wrap {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--ink);
  background: var(--paper);
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 700;
}

.archive-prefix {
  padding: 5px 8px;
  border-right: 1px solid var(--hair);
  color: var(--mute);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.archive-select {
  border: 0;
  background: transparent;
  color: var(--ink);
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 700;
  padding: 5px 8px;
  cursor: pointer;
  font-variant-numeric: tabular-nums;
}

/* Masthead */
.masthead {
  display: grid;
  grid-template-columns: 172px 1fr 172px;
  align-items: center;
  gap: 20px;
  padding: 10px 0 18px;
}

.ear {
  border: 1px solid var(--hair);
  padding: 10px 12px;
  font-family: var(--sans);
  line-height: 1.35;
}

.ear-right {
  text-align: right;
}

.ear-kicker {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--mute);
}

.ear-num {
  font-family: var(--head);
  font-size: 28px;
  font-weight: 800;
  line-height: 1.1;
  margin: 3px 0;
  font-variant-numeric: tabular-nums;
}

.ear-unit {
  font-size: 13px;
  font-weight: 600;
  color: var(--mute);
  margin-left: 2px;
}

.ear-sub {
  font-size: 11px;
  color: var(--ink-2);
}

.ear-link {
  display: inline-block;
  margin-top: 4px;
  font-size: 11px;
  font-weight: 700;
  color: var(--accent);
}

.ear-link:hover {
  text-decoration: underline;
}

.ear-link-muted {
  margin-top: 4px;
  font-size: 11px;
  color: var(--mute);
}

.mast-center {
  text-align: center;
}

.mast-overline {
  font-family: var(--sans);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: var(--mute);
  margin-bottom: 4px;
}

.mast-nameplate {
  margin: 0;
  line-height: 1.05;
  color: var(--ink);
}

.mast-nameplate-latin {
  font-family: var(--mast-latin);
  font-weight: 400;
  font-size: clamp(44px, 6.2vw, 88px);
  letter-spacing: 0.01em;
}

.mast-nameplate-cjk {
  font-family: var(--mast-cjk);
  font-weight: 900;
  font-size: clamp(36px, 5vw, 68px);
  letter-spacing: 0.12em;
}

.mast-motto {
  margin: 8px auto 0;
  max-width: 660px;
  font-family: var(--body);
  font-style: italic;
  font-size: 14px;
  color: var(--ink-2);
}

/* Dateline & Section Nav */
.dateline {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 12px;
  padding: 7px 0;
  border-top: 1px solid var(--rule);
  border-bottom: 1px solid var(--rule);
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-2);
}

.dateline-center {
  text-align: center;
  color: var(--ink);
  font-weight: 700;
}

.dateline-right {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.section-nav {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 6px 20px;
  padding: 10px 0;
  border-bottom: 3px double var(--rule);
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 600;
}

.section-nav a {
  padding: 2px 0;
  color: var(--ink-2);
  border-bottom: 2px solid transparent;
  transition: color 0.15s, border-color 0.15s;
}

.section-nav a:hover,
.section-nav a.is-current {
  color: var(--ink);
  border-bottom-color: var(--hot);
}

.nav-code {
  font-size: 10px;
  font-weight: 800;
  color: var(--mute);
  margin-right: 3px;
}

/* Continuous Signal Ticker Tape */
.ticker {
  overflow: hidden;
  border-bottom: 1px solid var(--hair);
  padding: 8px 0;
  position: relative;
}

.ticker-track {
  display: flex;
  width: max-content;
  animation: ticker-scroll 65s linear infinite;
}

.ticker:hover .ticker-track {
  animation-play-state: paused;
}

@keyframes ticker-scroll {
  from { transform: translateX(0); }
  to { transform: translateX(-50%); }
}

@media (prefers-reduced-motion: reduce) {
  .ticker {
    overflow-x: auto;
  }
  .ticker-track {
    animation: none;
  }
}

.ticker-item {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 18px;
  border-right: 1px solid var(--hair);
  font-family: var(--sans);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.ticker-item:hover .t-name {
  color: var(--accent);
  text-decoration: underline;
}

.t-name {
  font-weight: 700;
  color: var(--ink);
}

.t-up {
  font-weight: 700;
  color: var(--up);
}

.t-hot {
  font-weight: 700;
  color: var(--hot);
}

/* Shared Editorial Typography */
.band {
  padding: 26px 0 34px;
  border-bottom: 2px solid var(--rule);
}

.band:last-child {
  border-bottom: 0;
}

.band-head {
  margin-bottom: 20px;
}

.band-title-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--hair);
  padding-bottom: 10px;
}

.band-title {
  margin: 4px 0 0;
  font-family: var(--head);
  font-size: clamp(26px, 3vw, 38px);
  font-weight: 800;
  line-height: 1.15;
}

.band-count {
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 700;
  color: var(--mute);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.band-desc {
  margin: 8px 0 0;
  color: var(--ink-2);
  font-size: 15px;
}

.kicker {
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--mute);
}

.hot-kicker {
  color: var(--hot);
}

.accent-kicker {
  color: var(--accent);
}

.col-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 8px;
  margin-bottom: 14px;
  border-bottom: 2px solid var(--rule);
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.col-header a {
  color: var(--accent);
  font-weight: 700;
  text-transform: none;
  letter-spacing: 0;
}

.col-header a:hover {
  text-decoration: underline;
}

.score-pill {
  display: inline-flex;
  align-items: center;
  padding: 2px 7px;
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.03em;
  white-space: nowrap;
}

.score-hot {
  background: var(--badge-hot-bg);
  color: var(--hot);
}

.score-accent {
  background: var(--badge-accent-bg);
  color: var(--accent);
}

.headline-trigger {
  text-align: left;
  font: inherit;
  color: inherit;
  line-height: inherit;
  transition: color 0.15s;
}

.headline-trigger:hover {
  color: var(--accent);
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.tag-chip {
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 600;
  padding: 2px 7px;
  background: var(--chip);
  color: var(--ink-2);
  border: 1px solid transparent;
  transition: border-color 0.15s, color 0.15s;
}

.tag-chip:hover {
  border-color: var(--ink);
  color: var(--ink);
}

/* A1 Front Page 3-Column Broadsheet Grid */
.fp-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 2.05fr) minmax(0, 1fr);
  gap: 0;
  align-items: start;
}

.fp-col {
  min-width: 0;
}

.fp-left {
  padding-right: 22px;
  border-right: 1px solid var(--hair);
}

.fp-center {
  padding: 0 26px;
}

.fp-right {
  padding-left: 22px;
  border-left: 1px solid var(--hair);
}

.lead-kicker-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.breaking-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--hot);
  display: inline-block;
}

.lead-headline {
  margin: 0 0 14px;
  font-family: var(--head);
  font-size: clamp(28px, 3.3vw, 44px);
  font-weight: 900;
  line-height: 1.15;
  letter-spacing: -0.01em;
}

.lead-summary {
  margin: 0 0 14px;
  font-size: 17.5px;
  line-height: 1.65;
  color: var(--ink);
}

.story-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 6px 14px;
  font-family: var(--sans);
  font-size: 12px;
  color: var(--mute);
}

.lead-meta {
  padding: 8px 0;
  border-top: 1px solid var(--hair);
  border-bottom: 1px solid var(--hair);
  margin-bottom: 16px;
}

.lead-deck-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
  background: var(--ad);
  border-top: 2px solid var(--rule);
  border-bottom: 1px solid var(--hair);
  padding: 14px 16px;
  margin-bottom: 16px;
}

.lead-deck-cell p {
  margin: 6px 0 0;
  font-size: 14px;
  line-height: 1.55;
  color: var(--ink-2);
}

.lead-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 6px;
}

.lead-ext {
  display: flex;
  gap: 14px;
}

.editorial-link {
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 700;
  color: var(--accent);
}

.editorial-link:hover {
  text-decoration: underline;
}

.solid-cta {
  display: inline-block;
  width: 100%;
  text-align: center;
  padding: 9px 14px;
  background: var(--accent);
  color: var(--accent-ink);
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  transition: filter 0.15s;
}

.solid-cta:hover {
  filter: brightness(1.08);
}

.solid-cta-inline {
  width: auto;
  padding: 9px 16px;
}

/* Curated Spotlight Sub-Grid below Lead */
.spotlight-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-top: 22px;
  padding-top: 18px;
  border-top: 2px solid var(--rule);
}

.spotlight-col:first-child {
  padding-right: 16px;
  border-right: 1px solid var(--hair);
}

.spotlight-heading {
  margin: 4px 0 10px;
  font-family: var(--head);
  font-size: 18px;
  font-weight: 800;
}

.spotlight-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 8px 0;
  border-top: 1px solid var(--hair);
  transition: background 0.12s;
}

.spotlight-row:hover {
  background: var(--chip);
}

.spot-btn {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  flex: 1;
  min-width: 0;
  text-align: left;
}

.spot-ext {
  flex-shrink: 0;
  padding: 2px 6px;
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 800;
  color: var(--accent);
}

.spot-ext:hover {
  background: var(--accent);
  color: var(--accent-ink);
}

.inline-links {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.inline-ext-link {
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 700;
  color: var(--accent);
  white-space: nowrap;
}

.inline-ext-link:hover {
  text-decoration: underline;
}

.story-byline-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.card-actions {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.wire-meta-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 3px;
}

.wire-meta-row .wire-meta {
  margin-top: 0;
}

.drawer-head-links {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  margin-bottom: 18px;
}

.spot-score {
  font-family: var(--head);
  font-size: 15px;
  font-weight: 800;
  color: var(--hot);
  min-width: 28px;
  font-variant-numeric: tabular-nums;
}

.spot-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.spot-title {
  font-family: var(--body);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.35;
}

.spot-meta {
  font-family: var(--sans);
  font-size: 11px;
  color: var(--mute);
}

/* Left & Right Side Stories */
.side-story {
  padding-bottom: 16px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--hair);
}

.side-story:last-of-type {
  border-bottom: 0;
  margin-bottom: 12px;
}

.story-kicker-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 5px;
}

.story-kicker {
  font-family: var(--sans);
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--mute);
}

.side-headline {
  margin: 0 0 6px;
  font-family: var(--head);
  font-size: 18px;
  font-weight: 800;
  line-height: 1.28;
}

.side-summary {
  margin: 0 0 6px;
  font-size: 14px;
  line-height: 1.52;
  color: var(--ink-2);
}

.story-byline {
  font-family: var(--sans);
  font-size: 11px;
  color: var(--mute);
}

/* Editorial Signal Funnel Box (Print Ad Style) */
.desk-box {
  margin-top: 14px;
  padding: 16px;
  background: var(--ad);
  border: 1px solid var(--hair);
}

.desk-kicker {
  font-family: var(--sans);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--mute);
  text-align: center;
  margin-bottom: 6px;
}

.desk-title {
  margin: 0 0 6px;
  font-family: var(--head);
  font-size: 19px;
  font-weight: 800;
  text-align: center;
}

.desk-desc {
  margin: 0 0 12px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--ink-2);
}

.funnel-bars {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 14px;
}

.funnel-label {
  display: flex;
  justify-content: space-between;
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-2);
  margin-bottom: 3px;
}

.mono {
  font-variant-numeric: tabular-nums;
}

.funnel-track {
  height: 5px;
  background: var(--hair);
}

.funnel-fill {
  height: 100%;
  background: var(--ink);
}

/* Profile Sections (A2 - An) */
.section-grid {
  display: grid;
  gap: 0;
}

.section-grid-3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.section-grid-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.section-card {
  display: flex;
  flex-direction: column;
  padding: 16px 20px 20px;
  border-bottom: 1px solid var(--hair);
  border-right: 1px solid var(--hair);
}

.section-grid-3 .section-card:nth-child(3n),
.section-grid-2 .section-card:nth-child(2n) {
  border-right: 0;
}

.section-grid-3 .section-card:nth-child(3n + 1),
.section-grid-2 .section-card:nth-child(2n + 1) {
  padding-left: 0;
}

.card-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.card-num {
  font-family: var(--head);
  font-size: 15px;
  font-weight: 800;
  color: var(--mute);
  font-variant-numeric: tabular-nums;
}

.card-top .score-pill {
  margin-left: auto;
}

.card-headline {
  margin: 0 0 8px;
  font-family: var(--head);
  font-size: 20px;
  font-weight: 800;
  line-height: 1.28;
}

.card-summary {
  margin: 0 0 10px;
  font-size: 14.5px;
  line-height: 1.58;
  color: var(--ink-2);
}

.card-teaser {
  padding: 8px 10px;
  background: var(--ad);
  border-left: 2px solid var(--accent);
  font-size: 13px;
  line-height: 1.5;
  color: var(--ink-2);
  margin-bottom: 10px;
}

.card-foot {
  margin-top: auto;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.text-action {
  font-family: var(--sans);
  font-size: 11.5px;
  font-weight: 800;
  color: var(--accent);
  white-space: nowrap;
}

.text-action:hover {
  text-decoration: underline;
}

/* The Wire (3-Column Broadsheet News Wire) */
.wire-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0;
}

.wire-col {
  padding: 0 22px;
  border-right: 1px solid var(--hair);
}

.wire-col:first-child {
  padding-left: 0;
}

.wire-col:last-child {
  padding-right: 0;
  border-right: 0;
}

.wire-entry {
  padding: 11px 0;
  border-bottom: 1px solid var(--hair);
}

.wire-entry:last-child {
  border-bottom: 0;
}

.wire-numbered {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.wire-rank {
  font-family: var(--head);
  font-size: 16px;
  font-weight: 800;
  color: var(--mute);
  min-width: 18px;
  line-height: 1.3;
  font-variant-numeric: tabular-nums;
}

.wire-content {
  min-width: 0;
}

.wire-kicker {
  font-family: var(--sans);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--mute);
  margin-bottom: 3px;
}

.wire-head-inline {
  display: flex;
  align-items: baseline;
  gap: 7px;
  flex-wrap: wrap;
}

.wire-title {
  text-align: left;
  font-family: var(--head);
  font-size: 15.5px;
  font-weight: 700;
  line-height: 1.32;
  color: var(--ink);
}

.wire-title:hover {
  color: var(--accent);
}

.wire-badge {
  font-family: var(--sans);
  font-size: 10px;
  font-weight: 800;
  padding: 1px 6px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #ffffff;
  white-space: nowrap;
}

.wire-badge-yc {
  background: var(--badge-yc-bg);
}

.wire-badge-accent {
  background: var(--accent);
  color: var(--accent-ink);
}

.wire-blurb {
  margin: 4px 0 0;
  font-size: 13px;
  line-height: 1.48;
  color: var(--ink-2);
}

.wire-meta {
  margin-top: 3px;
  font-family: var(--sans);
  font-size: 11px;
  color: var(--mute);
}

.wire-empty {
  color: var(--mute);
  padding: 12px 0;
}

/* Archive Desk / Filterable Ledger */
.filter-controls {
  margin-bottom: 18px;
}

.search-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.search-input {
  flex: 1 1 280px;
  padding: 9px 12px;
  background: var(--paper);
  color: var(--ink);
  border: 1px solid var(--ink);
  font-family: var(--sans);
  font-size: 13.5px;
}

.sort-select {
  padding: 8px 12px;
  background: var(--paper);
  color: var(--ink);
  border: 1px solid var(--ink);
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 700;
}

.pill-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.filter-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  background: var(--chip);
  color: var(--ink);
  border: 1px solid transparent;
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 700;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.filter-pill:hover {
  border-color: var(--ink);
}

.filter-pill.is-active {
  background: var(--ink);
  color: var(--paper);
}

.filter-pill-sm {
  font-size: 11px;
  padding: 4px 10px;
}

.pill-count {
  opacity: 0.72;
  font-variant-numeric: tabular-nums;
}

.active-tag-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 700;
  color: var(--hot);
  margin-top: 6px;
}

.ledger-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 28px;
  border-top: 2px solid var(--rule);
}

.ledger-item {
  padding: 14px 0;
  border-bottom: 1px solid var(--hair);
}

.ledger-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 4px;
}

.ledger-meta {
  font-family: var(--sans);
  font-size: 11px;
  color: var(--mute);
}

.ledger-title {
  margin: 0 0 6px;
  font-family: var(--head);
  font-size: 17.5px;
  font-weight: 800;
  line-height: 1.3;
}

.ledger-summary {
  margin: 0 0 8px;
  font-size: 13.5px;
  line-height: 1.52;
  color: var(--ink-2);
}

.ledger-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-family: var(--sans);
  font-size: 11px;
}

.profile-tag {
  padding: 2px 7px;
  border: 1px solid var(--hair);
  font-weight: 700;
  color: var(--ink-2);
}

.ledger-tags {
  color: var(--mute);
}

.ledger-empty {
  grid-column: 1 / -1;
  padding: 32px 0;
  text-align: center;
  color: var(--mute);
  font-family: var(--sans);
}

/* Empty Edition */
.empty-edition {
  max-width: 680px;
  margin: 40px auto;
  padding: 32px;
  background: var(--ad);
  border: 1px solid var(--rule);
  text-align: center;
}

.empty-edition h2 {
  font-family: var(--head);
  margin: 10px 0;
}

/* Colophon Footer */
.colophon {
  margin-top: 32px;
  padding-top: 24px;
  border-top: 3px double var(--rule);
  text-align: center;
}

.colophon-wordmark {
  font-family: var(--mast-cjk);
  font-size: 26px;
  font-weight: 900;
  letter-spacing: 0.08em;
}

.colophon-meta {
  margin: 8px 0 4px;
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-2);
}

.colophon-note {
  margin: 0;
  font-family: var(--sans);
  font-size: 11.5px;
  color: var(--mute);
}

/* Floating Return Pill & Section Pager (Exact buildweek.ai Hard-Shadow Print Chrome) */
.home-pill {
  position: fixed;
  top: 14px;
  right: 18px;
  z-index: 600;
  padding: 7px 13px;
  background: var(--paper);
  color: var(--ink);
  border: 1px solid var(--ink);
  box-shadow: 3px 3px 0 var(--ink);
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  opacity: 0;
  pointer-events: none;
  transform: translateY(-6px);
  transition: opacity 0.18s, transform 0.18s;
}

.home-pill.is-visible {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0);
}

.pager-wrap {
  position: fixed;
  right: 18px;
  bottom: 18px;
  z-index: 600;
}

.pager-btn {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  background: var(--paper);
  color: var(--ink);
  border: 1px solid var(--ink);
  box-shadow: 3px 3px 0 var(--ink);
  font-family: var(--sans);
  font-size: 11.5px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.pager-btn-code {
  font-family: var(--head);
  font-size: 14px;
  font-weight: 900;
  color: var(--hot);
}

.pager-menu {
  position: absolute;
  right: 0;
  bottom: calc(100% + 8px);
  min-width: 210px;
  background: var(--paper);
  border: 1px solid var(--ink);
  box-shadow: 4px 4px 0 var(--ink);
  padding: 6px 0;
}

.pager-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 14px;
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 600;
}

.pager-item:hover,
.pager-item.is-active {
  background: var(--chip);
}

.pager-code {
  font-family: var(--head);
  font-weight: 800;
  color: var(--hot);
  min-width: 24px;
}

/* Newspaper Reading Drawer */
.drawer-backdrop {
  position: fixed;
  inset: 0;
  z-index: 800;
  background: rgba(20, 17, 13, 0.54);
  backdrop-filter: blur(2px);
}

.drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 810;
  width: min(680px, 100vw);
  background: var(--paper);
  border-left: 2px solid var(--ink);
  box-shadow: -8px 0 32px var(--shadow);
  display: flex;
  flex-direction: column;
}

.drawer-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 24px;
  border-bottom: 1px solid var(--rule);
  font-family: var(--sans);
}

.drawer-kicker {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--hot);
}

.drawer-close {
  padding: 5px 10px;
  border: 1px solid var(--ink);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.05em;
}

.drawer-close:hover {
  background: var(--ink);
  color: var(--paper);
}

.drawer-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 22px 26px 32px;
}

.drawer-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.drawer-title {
  margin: 0 0 12px;
  font-family: var(--head);
  font-size: clamp(24px, 2.8vw, 32px);
  font-weight: 900;
  line-height: 1.2;
}

.drawer-meta {
  padding: 10px 0;
  border-top: 1px solid var(--hair);
  border-bottom: 1px solid var(--hair);
  font-family: var(--sans);
  font-size: 12px;
  color: var(--mute);
  margin-bottom: 18px;
}

.drawer-block {
  margin-bottom: 18px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--hair);
}

.drawer-block:last-child {
  border-bottom: 0;
}

.drawer-block-title {
  font-family: var(--sans);
  font-size: 11.5px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: 6px;
}

.drawer-block-text {
  margin: 0;
  font-size: 15.5px;
  line-height: 1.72;
  color: var(--ink);
  white-space: pre-line;
}

.drawer-refs {
  margin-top: 16px;
  padding: 14px 16px;
  background: var(--ad);
  border: 1px solid var(--hair);
}

.drawer-refs ul {
  margin: 8px 0 0;
  padding-left: 18px;
  font-family: var(--sans);
  font-size: 13px;
}

.drawer-refs li {
  margin-bottom: 5px;
}

.drawer-refs a {
  color: var(--accent);
}

.drawer-refs a:hover {
  text-decoration: underline;
}

.drawer-tags {
  margin-top: 16px;
}

.drawer-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 24px;
  border-top: 2px solid var(--rule);
  background: var(--ad);
  font-family: var(--sans);
}

.drawer-nav-btn {
  padding: 6px 12px;
  border: 1px solid var(--ink);
  font-size: 11.5px;
  font-weight: 800;
}

.drawer-nav-btn:hover:not(:disabled) {
  background: var(--ink);
  color: var(--paper);
}

.drawer-nav-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.drawer-ext-links {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
}

/* Responsive Breakpoints */
@media (max-width: 1020px) {
  .masthead {
    grid-template-columns: 1fr;
    gap: 12px;
  }
  .ear {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    text-align: left;
  }
  .fp-grid {
    grid-template-columns: 1fr;
    gap: 24px;
  }
  .fp-left, .fp-center, .fp-right {
    padding: 0;
    border: 0;
  }
  .fp-center {
    order: -1;
    padding-bottom: 22px;
    border-bottom: 2px solid var(--rule);
  }
  .section-grid-3, .section-grid-2, .wire-grid, .ledger-grid, .spotlight-grid {
    grid-template-columns: 1fr;
  }
  .section-card, .wire-col, .spotlight-col:first-child {
    padding-left: 0;
    padding-right: 0;
    border-right: 0;
  }
  .wire-col {
    padding-top: 16px;
  }
  .dateline {
    grid-template-columns: 1fr;
    text-align: center;
    gap: 4px;
  }
  .dateline-right {
    text-align: center;
  }
}

@media print {
  .paper-grain, .util-bar, .pager-wrap, .home-pill, .drawer, .drawer-backdrop, .filter-controls, .ticker {
    display: none !important;
  }
  .sheet {
    max-width: 100%;
    padding: 0;
  }
  body, html {
    background: #ffffff !important;
    color: #000000 !important;
  }
}
"""


_BROADSHEET_JS = r"""
(function () {
  const dataEl = document.getElementById("horizon-edition-data");
  const copyEl = document.getElementById("horizon-edition-copy");
  if (!dataEl || !copyEl) return;

  const edition = JSON.parse(dataEl.textContent || "{}");
  const copy = JSON.parse(copyEl.textContent || "{}");
  const items = edition.items || [];
  const itemsById = new Map(items.map((item) => [item.id, item]));

  // Theme management
  const root = document.documentElement;
  const themeBtns = document.querySelectorAll("[data-theme-set]");
  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    try { localStorage.setItem("horizon-broadsheet-theme", theme); } catch (_) {}
    themeBtns.forEach((btn) => {
      btn.classList.toggle("is-active", btn.getAttribute("data-theme-set") === theme);
    });
  }
  let savedTheme = "light";
  try { savedTheme = localStorage.getItem("horizon-broadsheet-theme") || "light"; } catch (_) {}
  applyTheme(savedTheme);
  themeBtns.forEach((btn) => {
    btn.addEventListener("click", () => applyTheme(btn.getAttribute("data-theme-set") || "light"));
  });

  // Font size toggle
  const fontBtns = document.querySelectorAll("[data-font-set]");
  function applyFont(size) {
    root.setAttribute("data-font", size);
    try { localStorage.setItem("horizon-broadsheet-font", size); } catch (_) {}
    fontBtns.forEach((btn) => {
      btn.classList.toggle("is-active", btn.getAttribute("data-font-set") === size);
    });
  }
  let savedFont = "normal";
  try { savedFont = localStorage.getItem("horizon-broadsheet-font") || "normal"; } catch (_) {}
  applyFont(savedFont);
  fontBtns.forEach((btn) => {
    btn.addEventListener("click", () => applyFont(btn.getAttribute("data-font-set") || "normal"));
  });

  // Print button
  const printBtn = document.getElementById("printBtn");
  if (printBtn) printBtn.addEventListener("click", () => window.print());

  // Edition Archive Switcher (loads ./editions.json when served over HTTP/HTTPS)
  const archiveWrap = document.getElementById("editionArchiveWrap");
  const archiveSelect = document.getElementById("editionArchiveSelect");
  const currentDate = (edition.meta && edition.meta.date) || "";
  const currentLang = (edition.meta && edition.meta.language) || "zh";

  if (archiveWrap && archiveSelect && typeof fetch === "function" && location.protocol !== "file:") {
    fetch("./editions.json", { cache: "no-cache" })
      .then((res) => (res.ok ? res.json() : null))
      .then((manifest) => {
        if (!manifest || !Array.isArray(manifest.editions) || !manifest.editions.length) return;
        archiveSelect.innerHTML = "";
        manifest.editions.forEach((entry, idx) => {
          const opt = document.createElement("option");
          const langs = Array.isArray(entry.languages) ? entry.languages : [];
          const targetLang = langs.includes(currentLang) ? currentLang : (langs[0] || currentLang);
          opt.value = `./${entry.date}-${targetLang}.html`;
          const count = entry.selected_count && entry.selected_count[targetLang];
          const suffix = idx === 0 ? ` · ${copy.archive_latest || "Latest"}` : "";
          const countSuffix = typeof count === "number" ? ` (${count})` : "";
          opt.textContent = `${entry.date}${suffix}${countSuffix}`;
          if (entry.date === currentDate) opt.selected = true;
          archiveSelect.appendChild(opt);
        });
        archiveWrap.hidden = false;
        archiveSelect.addEventListener("change", () => {
          if (archiveSelect.value) window.location.href = archiveSelect.value;
        });
      })
      .catch(() => {});
  }

  // Article Reading Drawer
  const drawer = document.getElementById("articleDrawer");
  const backdrop = document.getElementById("drawerBackdrop");
  const drawerKicker = document.getElementById("drawerKicker");
  const drawerBadges = document.getElementById("drawerBadges");
  const drawerTitle = document.getElementById("drawerTitle");
  const drawerMeta = document.getElementById("drawerMeta");
  const drawerHeadLinks = document.getElementById("drawerHeadLinks");
  const drawerBlocks = document.getElementById("drawerBlocks");
  const drawerRefs = document.getElementById("drawerRefs");
  const drawerTags = document.getElementById("drawerTags");
  const drawerExtLinks = document.getElementById("drawerExtLinks");
  const drawerPrev = document.getElementById("drawerPrev");
  const drawerNext = document.getElementById("drawerNext");
  const drawerClose = document.getElementById("drawerClose");
  let currentStoryIdx = -1;

  function makeEl(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function openStory(storyId) {
    const story = itemsById.get(storyId);
    if (!story || !drawer || !backdrop) return;
    currentStoryIdx = items.findIndex((i) => i.id === storyId);

    drawerKicker.textContent = `${story.profile_name} · #${story.rank}`;
    drawerBadges.innerHTML = "";
    const scorePill = makeEl(
      "span",
      `score-pill ${(story.score || 0) >= 8.5 ? "score-hot" : "score-accent"}`,
      `${copy.drawer_score || "AI"}: ${story.score_display}/10`
    );
    drawerBadges.appendChild(scorePill);
    drawerBadges.appendChild(makeEl("span", "profile-tag", story.source_label));
    if (story.category) {
      drawerBadges.appendChild(makeEl("span", "profile-tag", story.category));
    }

    drawerTitle.textContent = story.title;
    const metaParts = [story.sub_source, story.time_display, ...(story.engagement || [])].filter(Boolean);
    drawerMeta.textContent = metaParts.join(" · ");

    if (drawerHeadLinks) {
      drawerHeadLinks.innerHTML = "";
      if (story.url) {
        const label = story.domain
          ? `${copy.original_link || "Original ↗"} (${story.domain})`
          : (copy.original_link || "Original ↗");
        const a = makeEl("a", "editorial-link", label);
        a.href = story.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        drawerHeadLinks.appendChild(a);
      }
      if (story.discussion_url) {
        const a = makeEl("a", "editorial-link", copy.discussion_link || "Discussion ↗");
        a.href = story.discussion_url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        drawerHeadLinks.appendChild(a);
      }
    }

    drawerBlocks.innerHTML = "";
    const blocks = (story.blocks && story.blocks.length)
      ? story.blocks
      : [{ title: copy.nav_front || "Summary", content: story.summary || "" }];
    blocks.forEach((blk) => {
      if (!blk.content) return;
      const box = makeEl("section", "drawer-block");
      box.appendChild(makeEl("div", "drawer-block-title", blk.title));
      box.appendChild(makeEl("p", "drawer-block-text", blk.content));
      drawerBlocks.appendChild(box);
    });

    drawerRefs.innerHTML = "";
    if (story.references && story.references.length) {
      drawerRefs.hidden = false;
      drawerRefs.appendChild(makeEl("div", "kicker", copy.drawer_refs || "References"));
      const ul = document.createElement("ul");
      story.references.forEach((ref) => {
        const li = document.createElement("li");
        if (ref.url) {
          const a = makeEl("a", "", ref.title || ref.url);
          a.href = ref.url;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          li.appendChild(a);
          if (ref.domain) li.appendChild(document.createTextNode(` (${ref.domain})`));
        } else {
          li.textContent = ref.title;
        }
        ul.appendChild(li);
      });
      drawerRefs.appendChild(ul);
    } else {
      drawerRefs.hidden = true;
    }

    drawerTags.innerHTML = "";
    if (story.tags && story.tags.length) {
      drawerTags.hidden = false;
      drawerTags.appendChild(makeEl("div", "kicker", copy.drawer_tags || "Tags"));
      const row = makeEl("div", "tag-row");
      story.tags.forEach((tag) => {
        const btn = makeEl("button", "tag-chip", `#${tag}`);
        btn.type = "button";
        btn.addEventListener("click", () => {
          closeDrawer();
          filterByTag(tag);
        });
        row.appendChild(btn);
      });
      drawerTags.appendChild(row);
    } else {
      drawerTags.hidden = true;
    }

    drawerExtLinks.innerHTML = "";
    if (story.url) {
      const a = makeEl("a", "editorial-link", copy.original_link || "Original ↗");
      a.href = story.url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      drawerExtLinks.appendChild(a);
    }
    if (story.discussion_url) {
      const a = makeEl("a", "editorial-link", copy.discussion_link || "Discussion ↗");
      a.href = story.discussion_url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      drawerExtLinks.appendChild(a);
    }

    drawerPrev.disabled = currentStoryIdx <= 0;
    drawerNext.disabled = currentStoryIdx < 0 || currentStoryIdx >= items.length - 1;

    drawer.hidden = false;
    backdrop.hidden = false;
    document.body.style.overflow = "hidden";
    const scroller = document.getElementById("drawerBody");
    if (scroller) scroller.scrollTop = 0;
  }

  function closeDrawer() {
    if (!drawer || !backdrop) return;
    drawer.hidden = true;
    backdrop.hidden = true;
    document.body.style.overflow = "";
  }

  if (drawerClose) drawerClose.addEventListener("click", closeDrawer);
  if (backdrop) backdrop.addEventListener("click", closeDrawer);
  if (drawerPrev) {
    drawerPrev.addEventListener("click", () => {
      if (currentStoryIdx > 0) openStory(items[currentStoryIdx - 1].id);
    });
  }
  if (drawerNext) {
    drawerNext.addEventListener("click", () => {
      if (currentStoryIdx >= 0 && currentStoryIdx < items.length - 1) openStory(items[currentStoryIdx + 1].id);
    });
  }

  // Archive Desk Filtering
  const searchInput = document.getElementById("archiveSearch");
  const sortSelect = document.getElementById("archiveSort");
  const resetBtn = document.getElementById("archiveReset");
  const ledgerEl = document.getElementById("archiveLedger");
  const activeTagBar = document.getElementById("activeTagBar");
  const profileBar = document.getElementById("profileFilterBar");
  const sourceBar = document.getElementById("sourceFilterBar");

  const filterState = { query: "", profile: "all", source: "all", tag: "", sort: "score" };

  function renderLedger() {
    if (!ledgerEl) return;
    const q = filterState.query.trim().toLowerCase();
    const filtered = items.filter((story) => {
      if (filterState.profile !== "all" && story.profile_id !== filterState.profile) return false;
      if (filterState.source !== "all" && story.source_type !== filterState.source) return false;
      if (filterState.tag && !(story.tags || []).includes(filterState.tag)) return false;
      if (q) {
        const hay = [
          story.title, story.summary, story.sub_source, story.source_label,
          story.profile_name, ...(story.tags || [])
        ].join(" ").toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

    filtered.sort((a, b) => {
      if (filterState.sort === "time") {
        return (b.published_at || "").localeCompare(a.published_at || "");
      }
      return (b.score ?? -1) - (a.score ?? -1) || a.rank - b.rank;
    });

    if (activeTagBar) {
      activeTagBar.innerHTML = "";
      if (filterState.tag) {
        activeTagBar.hidden = false;
        activeTagBar.appendChild(makeEl("span", "", `Tag: #${filterState.tag}`));
        const clearTag = makeEl("button", "util-btn", "×");
        clearTag.type = "button";
        clearTag.addEventListener("click", () => {
          filterState.tag = "";
          renderLedger();
        });
        activeTagBar.appendChild(clearTag);
      } else {
        activeTagBar.hidden = true;
      }
    }

    ledgerEl.innerHTML = "";
    if (!filtered.length) {
      ledgerEl.appendChild(makeEl("div", "ledger-empty", copy.no_match || "No matches."));
      return;
    }

    filtered.forEach((story) => {
      const card = makeEl("article", "ledger-item");
      const top = makeEl("div", "ledger-top");
      top.appendChild(
        makeEl("span", "ledger-meta", `${story.source_label} · ${story.sub_source} · ${story.time_display}`)
      );
      top.appendChild(
        makeEl(
          "span",
          `score-pill ${(story.score || 0) >= 8.5 ? "score-hot" : "score-accent"}`,
          story.score_display
        )
      );
      card.appendChild(top);

      const h3 = makeEl("h3", "ledger-title");
      const btn = makeEl("button", "headline-trigger", story.title);
      btn.type = "button";
      btn.addEventListener("click", () => openStory(story.id));
      h3.appendChild(btn);
      card.appendChild(h3);

      const summary = story.summary.length > 140 ? `${story.summary.slice(0, 139)}…` : story.summary;
      card.appendChild(makeEl("p", "ledger-summary", summary));

      const foot = makeEl("div", "ledger-foot");
      foot.appendChild(makeEl("span", "profile-tag", story.profile_name));
      foot.appendChild(makeEl("span", "ledger-tags", (story.tags || []).slice(0, 3).map((t) => `#${t}`).join(" ")));
      const linksWrap = makeEl("span", "inline-links");
      if (story.url) {
        const orig = makeEl("a", "inline-ext-link", copy.source_link || "Source ↗");
        orig.href = story.url;
        orig.target = "_blank";
        orig.rel = "noopener noreferrer";
        linksWrap.appendChild(orig);
      }
      if (story.discussion_url) {
        const disc = makeEl("a", "inline-ext-link", copy.discuss_short || "Discuss ↗");
        disc.href = story.discussion_url;
        disc.target = "_blank";
        disc.rel = "noopener noreferrer";
        linksWrap.appendChild(disc);
      }
      if (linksWrap.childNodes.length) foot.appendChild(linksWrap);
      card.appendChild(foot);
      ledgerEl.appendChild(card);
    });
  }

  function filterByTag(tag) {
    filterState.tag = tag;
    renderLedger();
    const desk = document.getElementById("archive-desk");
    if (desk) desk.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      filterState.query = searchInput.value;
      renderLedger();
    });
  }
  if (sortSelect) {
    sortSelect.addEventListener("change", () => {
      filterState.sort = sortSelect.value;
      renderLedger();
    });
  }
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      filterState.query = "";
      filterState.profile = "all";
      filterState.source = "all";
      filterState.tag = "";
      filterState.sort = "score";
      if (searchInput) searchInput.value = "";
      if (sortSelect) sortSelect.value = "score";
      if (profileBar) {
        profileBar.querySelectorAll(".filter-pill").forEach((p) => {
          p.classList.toggle("is-active", p.getAttribute("data-filter-profile") === "all");
        });
      }
      if (sourceBar) {
        sourceBar.querySelectorAll(".filter-pill").forEach((p) => {
          p.classList.toggle("is-active", p.getAttribute("data-filter-source") === "all");
        });
      }
      renderLedger();
    });
  }

  if (profileBar) {
    profileBar.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-filter-profile]");
      if (!btn) return;
      filterState.profile = btn.getAttribute("data-filter-profile") || "all";
      profileBar.querySelectorAll(".filter-pill").forEach((p) => p.classList.toggle("is-active", p === btn));
      renderLedger();
    });
  }
  if (sourceBar) {
    sourceBar.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-filter-source]");
      if (!btn) return;
      filterState.source = btn.getAttribute("data-filter-source") || "all";
      sourceBar.querySelectorAll(".filter-pill").forEach((p) => p.classList.toggle("is-active", p === btn));
      renderLedger();
    });
  }

  // Delegated clicks for story triggers and tag chips anywhere on the broadsheet
  document.addEventListener("click", (e) => {
    const storyTrigger = e.target.closest("[data-open-story]");
    if (storyTrigger) {
      openStory(storyTrigger.getAttribute("data-open-story"));
      return;
    }
    const tagTrigger = e.target.closest("[data-filter-tag]");
    if (tagTrigger) {
      filterByTag(tagTrigger.getAttribute("data-filter-tag") || "");
    }
  });

  // Jump-to-search button & keyboard shortcuts
  function focusSearch() {
    if (!searchInput) return;
    const desk = document.getElementById("archive-desk");
    if (desk) desk.scrollIntoView({ behavior: "smooth", block: "start" });
    setTimeout(() => searchInput.focus(), 220);
  }
  const jumpSearchBtn = document.getElementById("jumpSearchBtn");
  if (jumpSearchBtn) jumpSearchBtn.addEventListener("click", focusSearch);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeDrawer();
      if (pagerMenu) pagerMenu.hidden = true;
      if (pagerBtn) pagerBtn.setAttribute("aria-expanded", "false");
      return;
    }
    if (drawer && !drawer.hidden) {
      if (e.key === "ArrowLeft" && currentStoryIdx > 0) openStory(items[currentStoryIdx - 1].id);
      if (e.key === "ArrowRight" && currentStoryIdx < items.length - 1) openStory(items[currentStoryIdx + 1].id);
      return;
    }
    if ((e.key === "/" || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k")) &&
        document.activeElement !== searchInput) {
      e.preventDefault();
      focusSearch();
    }
  });

  // Floating Pager & Return-to-Front-Page Pill
  const pagerBtn = document.getElementById("pagerBtn");
  const pagerMenu = document.getElementById("pagerMenu");
  const pagerActiveCode = document.getElementById("pagerActiveCode");
  const pagerActiveLabel = document.getElementById("pagerActiveLabel");
  const homePill = document.getElementById("homePill");

  if (pagerBtn && pagerMenu) {
    pagerBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const willOpen = pagerMenu.hidden;
      pagerMenu.hidden = !willOpen;
      pagerBtn.setAttribute("aria-expanded", String(willOpen));
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest("#pagerWrap")) {
        pagerMenu.hidden = true;
        pagerBtn.setAttribute("aria-expanded", "false");
      }
    });
    pagerMenu.addEventListener("click", () => {
      pagerMenu.hidden = true;
      pagerBtn.setAttribute("aria-expanded", "false");
    });
  }

  const bands = Array.from(document.querySelectorAll("section[data-page-code]"));
  function setActiveSection(code, label) {
    if (pagerActiveCode) pagerActiveCode.textContent = code;
    if (pagerActiveLabel) pagerActiveLabel.textContent = label;
    document.querySelectorAll("[data-section-link]").forEach((el) => {
      el.classList.toggle("is-current", el.getAttribute("data-section-link") === code);
    });
    document.querySelectorAll("[data-pager-code]").forEach((el) => {
      el.classList.toggle("is-active", el.getAttribute("data-pager-code") === code);
    });
  }

  if ("IntersectionObserver" in window && bands.length) {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length) {
          const target = visible[0].target;
          setActiveSection(
            target.getAttribute("data-page-code") || "A1",
            target.getAttribute("data-page-label") || ""
          );
        }
      },
      { rootMargin: "-15% 0px -65% 0px", threshold: 0.01 }
    );
    bands.forEach((b) => observer.observe(b));
  }

  window.addEventListener(
    "scroll",
    () => {
      if (homePill) homePill.classList.toggle("is-visible", window.scrollY > 360);
    },
    { passive: true }
  );
})();
"""
