# Horizon Daily · 地平线每日快报

An AI-edited, bilingual (中文 / English) daily newspaper for tech and industry news. It collects items from many sources, scores and de-duplicates them with an LLM, and renders a single-page broadsheet that is published to GitHub Pages every morning — no server required.

**Live edition:** <https://shangliy.github.io/horizon-daily/> · [中文说明](README_zh.md)

## What it does

1. **Collect** — Hacker News, RSS/Atom feeds, GitHub releases, Reddit, Telegram, Twitter/X, arXiv, Bluesky, Polymarket, OSS Insight, GDELT, Google News and OpenBB.
2. **Edit** — an LLM routes each item to an editorial profile (`tech-news`, `tech-blog`, `finance-news`, `ai-creator`), scores it, merges duplicates across sources, and writes a summary in each output language.
3. **Print** — the result is rendered as one self-contained HTML page per language: front page, profile sections, a wire column, a searchable index, a reading drawer, light/dark paper themes and an archive of past editions.
4. **Publish** — a scheduled GitHub Actions workflow pushes the static site to the `gh-pages` branch.

## Quick start

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/shangliy/horizon-daily.git
cd horizon-daily
uv sync

# Preview the layout with live sources and no AI calls
uv run python scripts/generate_broadsheet_preview.py --live --hours 72
python3 -m http.server -d docs/broadsheet 8080
```

To run the full pipeline, copy the production config, provide one model API key, and run:

```bash
cp data/config.broadsheet.json data/config.json
cp .env.example .env          # then set OPENAI_API_KEY (or another provider's key)
uv run horizon --hours 24
```

The site is written to `docs/broadsheet/` (`index.html`, `latest-{zh,en}.html`, dated editions and `editions.json`).

## Deploy your own

Fork the repository, add a model API key under **Settings → Secrets and variables → Actions**, and set GitHub Pages to serve the `gh-pages` branch. `.github/workflows/daily-broadsheet.yml` then builds and publishes an edition every day at 23:00 UTC, and can be run by hand from the Actions tab. The step-by-step guide is in [docs/broadsheet-deploy.md](docs/broadsheet-deploy.md).

| Secret / variable | Purpose |
|---|---|
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `DEEPSEEK_API_KEY` | Model provider; the workflow picks whichever is set |
| `APIFY_TOKEN` (optional) | Turns on the Twitter/X source |
| `TWITTER_USERS` (optional variable) | Comma-separated accounts to follow |

## Project layout

| Path | Contents |
|---|---|
| `src/orchestrator.py` | The pipeline: fetch → score → de-duplicate → enrich → render → deliver |
| `src/scrapers/` | One module per source |
| `src/ai/` | Provider clients, scoring, enrichment, localization and prompts |
| `src/rendering/` | Broadsheet renderer, its stylesheet and script (`assets/`), UI copy (`broadsheet_i18n.py`) and the site publisher |
| `src/services/` | Optional delivery by email, webhook and WeChat |
| `src/mcp/`, `skills/horizon/` | MCP server and agent skill |
| `profiles/` | Editorial profiles: routing rules, scoring rubric and output instructions |
| `data/config.broadsheet.json` | The configuration used for the live edition |

## Documentation

- [Deployment](docs/broadsheet-deploy.md)
- [Configuration](docs/configuration.md)
- [Sources](docs/scrapers.md) and [content extractors](docs/extractors.md)
- [Profiles](docs/profiles.md) and [scoring](docs/scoring.md)
- [Agent skill](docs/agent-skill.md) and [MCP server](src/mcp/README.md)

## Development

```bash
uv sync --extra dev
uv run pytest
```

A few tests need network access or the optional `twitter` extra (Playwright).

## Credits

Horizon Daily is built on **[Horizon](https://github.com/Thysrael/Horizon)** by [Thysrael](https://github.com/Thysrael) and its contributors. The collection pipeline, source scrapers, AI scoring and enrichment, profiles, delivery services and MCP server come from that project; this repository adds the broadsheet renderer, the static-site publisher, the Polymarket, arXiv and Bluesky sources, and the GitHub Pages workflow. Thank you to the Horizon authors for releasing their work under the MIT license.

## License

[MIT](LICENSE). The original Horizon copyright notice is retained.
