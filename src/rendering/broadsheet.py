"""Single-page interactive newspaper broadsheet renderer for Horizon."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from ..ai.localization import normalize_language
from ..ai.summarizer import DailySummarizer, _pangu, _safe_url
from ..models import BroadsheetConfig, ContentItem
from .broadsheet_i18n import (
    _WEEKDAYS_ZH,
    _WEEKDAYS_EN,
    _MONTHS_EN,
    _SOURCE_LABELS,
    _localize_category,
    _localize_tag,
    _COPY,
    _is_cjk,
)


_ASSETS_DIR = Path(__file__).parent / "assets"


def _load_asset(name: str) -> str:
    """Read a bundled stylesheet/script; wrapped in newlines for inlining."""
    return "\n" + (_ASSETS_DIR / name).read_text(encoding="utf-8").strip("\n") + "\n"


_BROADSHEET_CSS = _load_asset("broadsheet.css")
_BROADSHEET_JS = _load_asset("broadsheet.js")


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

                tags = []
                for raw_tag in (analysis.tags if analysis else []):
                    localized_tag = _localize_tag(_clean_text(str(raw_tag), language), lang_key)
                    if localized_tag and localized_tag not in tags:
                        tags.append(localized_tag)
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
                    "category": _localize_category(str(meta.get("category") or ""), lang_key),
                    "published_at": item.published_at.isoformat() if item.published_at else "",
                    "time_display": _format_item_time(item.published_at, lang_key),
                    "tags": tags,
                    "blocks": blocks,
                    "secondary_blocks": secondary_blocks,
                    "references": references,
                    "engagement": engagement,
                    "engagement_weight": engagement_weight,
                    "probability_pct": meta.get("probability_pct"),
                    "leading_outcome": meta.get("leading_outcome"),
                    "volume_24h_display": meta.get("volume_24h_display"),
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
        if meta.get("probability_pct") is not None:
            outcome = meta.get("leading_outcome") or "Yes"
            parts.append(f"{outcome} {float(meta['probability_pct']):.0f}%")
        if meta.get("volume_24h_display"):
            vol = meta["volume_24h_display"]
            parts.append(f"24h 成交 {vol}" if lang_key == "zh" else f"{vol} 24h vol")
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
        col2_sources = {"github", "ossinsight", "twitter", "bluesky"}

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
        # Lead ticker with live Polymarket prediction odds when present
        pm_records = [
            rec for rec in ranked_records
            if rec["source_type"] == "polymarket" and rec.get("probability_pct") is not None
        ]
        for rec in pm_records[:5]:
            prob = float(rec["probability_pct"])
            ticker.append(
                {
                    "kind": "story",
                    "story_id": rec["id"],
                    "label": f"POLYMARKET · {_truncate(rec['title'], 26 if lang_key == 'zh' else 38)}",
                    "metric": f"{prob:.0f}%",
                    "delta": "hot" if prob >= 70 or prob <= 30 else "up",
                }
            )
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
            if rec in pm_records[:5]:
                continue
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
        editorial_html = self._render_editorial(data.get("editorial"), items_by_id, copy)

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
        {editorial_html}
      </section>
        """

    @staticmethod
    def _render_editorial(
        editorial: Optional[Dict[str, Any]],
        items_by_id: Dict[str, Dict[str, Any]],
        copy: Dict[str, str],
    ) -> str:
        """Front-page editorial strip; empty when the edition has no editorial."""
        if not editorial or not editorial.get("headline") or not editorial.get("body"):
            return ""
        paragraphs = "".join(
            f"<p>{_esc(p)}</p>" for p in str(editorial["body"]).split("\n\n") if p.strip()
        )
        refs = "".join(
            f'<button type="button" class="editorial-ref" data-open-story="{_esc(story_id)}">'
            f'{_esc(_truncate(items_by_id[story_id]["title"], 44))}</button>'
            for story_id in editorial.get("story_ids") or []
            if story_id in items_by_id
        )
        refs_html = (
            f'<div class="editorial-refs"><span class="kicker">{_esc(copy["editorial_refs"])}</span>{refs}</div>'
            if refs
            else ""
        )
        return (
            '<aside class="editorial" aria-labelledby="editorialHeadline">'
            '<div class="editorial-head">'
            f'<div class="kicker accent-kicker">{_esc(copy["editorial_kicker"])}</div>'
            f'<h3 class="editorial-headline" id="editorialHeadline">{_esc(editorial["headline"])}</h3>'
            f'<div class="editorial-byline">{_esc(copy["editorial_byline"])}</div>'
            "</div>"
            f'<div class="editorial-body">{paragraphs}{refs_html}</div>'
            "</aside>"
        )

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
