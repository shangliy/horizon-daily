"""Localized labels and UI copy for the broadsheet renderer."""

from __future__ import annotations

import re
from typing import Dict


def _is_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff\u3400-\u4dbf]", text))


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
        "polymarket": "Polymarket 预测",
        "arxiv": "arXiv 论文",
        "bluesky": "Bluesky",
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
        "polymarket": "Polymarket",
        "arxiv": "arXiv",
        "bluesky": "Bluesky",
    },
}

_CATEGORY_LABELS: Dict[str, Dict[str, str]] = {
    "zh": {
        "ai-news": "AI 资讯",
        "ai-tools": "AI 工具",
        "ai-infra": "AI 基础设施",
        "ai-engineering": "AI 工程",
        "llm-inference": "大模型推理",
        "llm-local": "本地大模型",
        "ml-research": "机器学习研究",
        "software-engineering": "软件工程",
        "dev-tools": "开发者工具",
        "open-source": "开源项目",
        "finance": "财经要闻",
        "tech-markets": "科技市场",
        "equities": "美股动态",
        "tech-flash": "科技快讯",
        "x-signal": "X 精选",
        "cuda": "CUDA / GPU",
        "semiconductors": "半导体",
        "linux-kernel": "Linux 内核",
        "github-trending": "GitHub 趋势",
        "prediction-markets": "预测市场",
        "ai-research": "前沿论文",
        "bluesky": "Bluesky 讨论",
    },
    "en": {
        "ai-news": "AI News",
        "ai-tools": "AI Tools",
        "ai-infra": "AI Infra",
        "ai-engineering": "AI Engineering",
        "llm-inference": "LLM Inference",
        "llm-local": "Local LLM",
        "ml-research": "ML Research",
        "software-engineering": "Software Engineering",
        "dev-tools": "Dev Tools",
        "open-source": "Open Source",
        "finance": "Finance",
        "tech-markets": "Tech Markets",
        "equities": "Equities",
        "tech-flash": "Tech Flash",
        "x-signal": "X Signal",
        "cuda": "CUDA",
        "semiconductors": "Semiconductors",
        "linux-kernel": "Linux Kernel",
        "github-trending": "GitHub Trending",
        "prediction-markets": "Prediction Markets",
        "ai-research": "AI Research",
        "bluesky": "Bluesky",
    },
}

_ZH_TO_EN_TAGS: Dict[str, str] = {
    "开源": "Open Source",
    "开源项目": "Open Source",
    "美联储": "Fed",
    "美股": "US Equities",
    "市场": "Markets",
    "芯片": "Chips",
    "云计算": "Cloud",
    "大模型": "LLM",
    "人工智能": "AI",
    "软件工程": "Software Engineering",
    "系统架构": "Architecture",
    "财经": "Finance",
    "科技股": "Tech Stocks",
    "半导体": "Semiconductors",
    "宏观经济": "Macro",
}


def _localize_category(category: str, lang_key: str) -> str:
    raw = category.strip()
    if not raw:
        return ""
    mapped = _CATEGORY_LABELS[lang_key].get(raw.lower())
    if mapped:
        return mapped
    if lang_key == "en" and _is_cjk(raw):
        return _ZH_TO_EN_TAGS.get(raw, "")
    return raw


def _localize_tag(tag: str, lang_key: str) -> str:
    raw = tag.strip()
    if not raw:
        return ""
    if lang_key == "zh":
        return _CATEGORY_LABELS["zh"].get(raw.lower(), raw)
    # In English mode, translate known Chinese tags and drop untranslated CJK tags
    if raw.lower() in _CATEGORY_LABELS["en"]:
        return _CATEGORY_LABELS["en"][raw.lower()]
    if _is_cjk(raw):
        return _ZH_TO_EN_TAGS.get(raw, "")
    return raw


_COPY: Dict[str, Dict[str, str]] = {
    "zh": {
        "default_title": "地平线每日快报",
        "default_overline": "地平线 · 每日数字大报",
        "default_subtitle": "你只需享受新闻，剩下交给地平线 — 多源聚合、AI 研判与深度背景每日速递。",
        "default_edition_label": "地平线 · 全球科技与产业快报",
        "ear_left_kicker": "今日精选",
        "ear_left_sub": "从 {total} 条信源中筛选",
        "ear_left_link": "查看全量目录 →",
        "ear_right_kicker": "信号指数",
        "ear_right_sub": "最高 {top} · {sources} 类信源",
        "ear_right_link": "淘汰率 {drop_rate}%",
        "vol_label": "第 I 卷 · {date}",
        "updated_label": "更新于 {time} · 地平线 AI 编排",
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
        "desk_kicker": "地平线情报台",
        "desk_title": "今日信源漏斗与分布",
        "desk_desc": "系统自动完成多源抓取、跨源链接去重、语义聚类与背景检索，仅保留高信号条目。",
        "desk_cta": "打开全量检索台",
        "section_kicker_tpl": "{code} · 专题版面",
        "wire_kicker": "全球电讯 · 多源实时速递",
        "wire_title": "全球信息源速览",
        "wire_desc": "按渠道高密度梳理今日入选资讯，涵盖技术社区、开源项目与行业媒体。",
        "wire_col_1": "社区热榜 · HN / Reddit",
        "wire_col_2": "开源与社交 · GitHub / Bluesky / X",
        "wire_col_3": "论文、媒体与预测 · RSS / arXiv / Polymarket",
        "wire_more": "全部 →",
        "index_kicker": "全量档案 · 交互检索",
        "index_title": "本期全量资讯检索台",
        "index_desc": "按关键词、版面、信源或主题标签即时过滤，点击任意条目在右侧报刊抽屉阅读全文。",
        "search_placeholder": "搜索标题、摘要、标签或来源… (快捷键 /)",
        "search_btn": "检索",
        "clear_btn": "重置",
        "all_label": "全部",
        "sort_score": "按 AI 评分",
        "sort_time": "按发布时间",
        "no_match": "未找到匹配的资讯条目，请尝试清除筛选条件。",
        "empty_title": "今日情报台较平静，暂无达到阈值的重点资讯",
        "empty_desc": "本次共采集 {total} 条原始内容，但均未超过当前栏目设定的重要度门槛。可适当下调阈值或扩充订阅源后重新生成。",
        "btn_search": "检索",
        "btn_print": "打印版",
        "archive_label": "往期",
        "archive_latest": "最新",
        "active_tag_prefix": "当前标签: #",
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
        "wire_col_2": "OPEN SOURCE, BLUESKY & X",
        "wire_col_3": "PAPERS, MEDIA & POLYMARKET",
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
        "active_tag_prefix": "Tag: #",
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
