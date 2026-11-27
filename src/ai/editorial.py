"""Daily editorial: one short opinion piece tying the day's top stories together."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .client import AIClient
from .prompting.editorial import EDITORIAL_LANGUAGES, EDITORIAL_SYSTEM, EDITORIAL_USER
from .utils import parse_json_response

logger = logging.getLogger(__name__)

# An editorial needs stories to connect; below this it would only restate one item.
MIN_STORIES = 3
MAX_STORIES = 14
MAX_CITED_STORIES = 4
_SUMMARY_LIMIT = 320
_MAX_BODY_CHARS = 2000


class EditorialWriter:
    """Writes the editorial for one language edition.

    The editorial is an optional extra. Any failure returns None so the
    edition is published without it.
    """

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client

    async def write(
        self, records: List[Dict[str, Any]], language: str
    ) -> Optional[Dict[str, Any]]:
        """Return {"headline", "body", "story_ids"} or None.

        Args:
            records: Story records from BroadsheetRenderer.build_edition_data.
            language: Edition language code.
        """
        lang_key = "zh" if language.lower().startswith("zh") else "en"
        stories = sorted(
            (r for r in records if r.get("title")),
            key=lambda r: r["score"] if r.get("score") is not None else -1.0,
            reverse=True,
        )[:MAX_STORIES]
        if len(stories) < MIN_STORIES:
            return None

        lines = []
        for index, story in enumerate(stories):
            summary = " ".join(str(story.get("summary") or "").split())[:_SUMMARY_LIMIT]
            lines.append(
                f"[{index}] ({story.get('profile_name') or story.get('profile_id') or ''}) "
                f"{story['title']}\n    {summary}"
            )

        try:
            response = await self.ai_client.complete(
                system=EDITORIAL_SYSTEM,
                user=EDITORIAL_USER.format(
                    stories="\n".join(lines), **EDITORIAL_LANGUAGES[lang_key]
                ),
                temperature=0.6,
                max_tokens=1200,
            )
        except Exception as exc:  # the edition must not depend on this call
            logger.warning("Editorial generation failed: %s", exc)
            return None

        return self._parse(response, stories)

    @staticmethod
    def _parse(response: Any, stories: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(response, str):
            return None
        parsed = parse_json_response(response)
        if not isinstance(parsed, dict):
            logger.warning("Editorial response was not a JSON object")
            return None

        headline = parsed.get("headline")
        body = parsed.get("body")
        if not isinstance(headline, str) or not isinstance(body, str):
            return None
        headline = " ".join(headline.split())
        paragraphs = [" ".join(p.split()) for p in body.split("\n")]
        body = "\n\n".join(p for p in paragraphs if p)
        if not headline or not body or len(body) > _MAX_BODY_CHARS:
            return None

        story_ids: List[str] = []
        indices = parsed.get("story_indices")
        for index in indices if isinstance(indices, list) else []:
            if isinstance(index, bool) or not isinstance(index, int):
                continue
            if 0 <= index < len(stories):
                story_id = stories[index]["id"]
                if story_id not in story_ids:
                    story_ids.append(story_id)
        return {
            "headline": headline,
            "body": body,
            "story_ids": story_ids[:MAX_CITED_STORIES],
        }
