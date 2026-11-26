"""Tests for the pre-deploy edition check."""

from datetime import datetime, timedelta, timezone
import json

from src.rendering.site import BroadsheetSitePublisher
from src.rendering.verify import check_site, main


def _publish(site_dir, *, count=8, languages=("zh", "en"), date="2026-11-26"):
    publisher = BroadsheetSitePublisher(site_dir)
    for language in languages:
        publisher.publish_edition(
            date=date,
            language=language,
            html_content="<html></html>",
            edition_data={
                "meta": {"title": "Horizon Daily", "selected_count": count},
                "items": [{"id": str(i), "title": f"Item {i}"} for i in range(count)],
            },
            is_default_language=(language == "zh"),
            default_language="zh",
        )


def test_fresh_edition_passes(tmp_path):
    _publish(tmp_path)

    assert check_site(tmp_path, min_items=5) == []
    assert main(["--site-dir", str(tmp_path)]) == 0


def test_missing_manifest_fails(tmp_path, capsys):
    problems = check_site(tmp_path)

    assert len(problems) == 1 and "no edition was published" in problems[0]
    assert main(["--site-dir", str(tmp_path)]) == 1
    assert "edition check failed" in capsys.readouterr().err


def test_manifest_restored_but_not_rewritten_fails(tmp_path):
    # The workflow restores yesterday's manifest; a run that publishes nothing leaves it stale.
    _publish(tmp_path)
    later = datetime.now(timezone.utc) + timedelta(hours=24)

    problems = check_site(tmp_path, now=later)

    assert len(problems) == 1 and "did not publish a new edition" in problems[0]


def test_thin_edition_fails_per_language(tmp_path):
    _publish(tmp_path, count=2)

    problems = check_site(tmp_path, min_items=5)

    assert len(problems) == 2
    assert all("has 2 items, fewer than the minimum of 5" in p for p in problems)
    assert check_site(tmp_path, min_items=2) == []


def test_missing_edition_file_fails(tmp_path):
    _publish(tmp_path)
    (tmp_path / "latest-en.html").unlink()

    assert check_site(tmp_path) == [f"latest-en.html is missing from {tmp_path}"]


def test_corrupt_manifest_fails(tmp_path):
    (tmp_path / "editions.json").write_text("{not json", encoding="utf-8")
    assert "unreadable" in check_site(tmp_path)[0]

    (tmp_path / "editions.json").write_text(json.dumps({"editions": []}), encoding="utf-8")
    assert "updated_at" in check_site(tmp_path)[0]
