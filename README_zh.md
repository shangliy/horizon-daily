# 地平线每日快报 · Horizon Daily

一份由 AI 编辑的中英双语科技与产业日报。它从多个信源抓取内容，用大模型评分、去重、撰写摘要，再排成一张单页的报纸版面，每天早上自动发布到 GitHub Pages，不需要服务器。

**线上版：** <https://shangliy.github.io/horizon-daily/> · [English](README.md)

## 它做什么

1. **采集**：Hacker News、RSS/Atom、GitHub Releases、Reddit、Telegram、Twitter/X、arXiv、Bluesky、Polymarket、OSS Insight、GDELT、Google News、OpenBB。
2. **编辑**：大模型把每条内容分到一个编辑画像（`tech-news`、`tech-blog`、`finance-news`、`ai-creator`），打分，合并跨信源的重复报道，并按每种输出语言写摘要。
3. **排版**：每种语言生成一个自包含的 HTML 页面，含头版、各画像专题版、电讯栏、可检索的索引、阅读抽屉、浅色/深色纸面和往期归档。
4. **发布**：GitHub Actions 定时把静态站点推送到 `gh-pages` 分支。

## 快速开始

需要 Python 3.11+ 和 [uv](https://github.com/astral-sh/uv)。

```bash
git clone https://github.com/shangliy/horizon-daily.git
cd horizon-daily
uv sync

# 用实时信源预览版面，不调用 AI
uv run python scripts/generate_broadsheet_preview.py --live --hours 72
python3 -m http.server -d docs/broadsheet 8080
```

要跑完整流水线，复制线上配置，填入一个模型的 API Key，然后运行：

```bash
cp data/config.broadsheet.json data/config.json
cp .env.example .env          # 填入 OPENAI_API_KEY（或其他模型的 Key）
uv run horizon --hours 24
```

站点输出在 `docs/broadsheet/`（`index.html`、`latest-{zh,en}.html`、按日期归档的各期和 `editions.json`）。

## 部署你自己的一份

Fork 本仓库，在 **Settings → Secrets and variables → Actions** 里添加模型 API Key，并把 GitHub Pages 设为从 `gh-pages` 分支发布。之后 `.github/workflows/daily-broadsheet.yml` 会在每天 23:00 UTC（北京时间 07:00）构建并发布新一期，也可以在 Actions 页面手动触发。分步说明见 [docs/broadsheet-deploy.md](docs/broadsheet-deploy.md)。

| Secret / 变量 | 用途 |
|---|---|
| `OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`GOOGLE_API_KEY`、`DEEPSEEK_API_KEY` | 模型服务，工作流自动使用已配置的那个 |
| `APIFY_TOKEN`（可选） | 开启 Twitter/X 信源 |
| `TWITTER_USERS`（可选变量） | 逗号分隔的关注账号 |

## 目录结构

| 路径 | 内容 |
|---|---|
| `src/orchestrator.py` | 主流程：抓取 → 评分 → 去重 → 富化 → 渲染 → 分发 |
| `src/scrapers/` | 每个信源一个模块 |
| `src/ai/` | 模型客户端、评分、富化、本地化和提示词 |
| `src/rendering/` | 大报渲染器、样式与脚本（`assets/`）、界面文案（`broadsheet_i18n.py`）和站点发布器 |
| `src/services/` | 可选的邮件、Webhook、微信推送 |
| `src/mcp/`、`skills/horizon/` | MCP 服务和 Agent Skill |
| `profiles/` | 编辑画像：路由规则、评分标准和输出要求 |
| `data/config.broadsheet.json` | 线上版使用的配置 |

## 文档

- [部署](docs/broadsheet-deploy.md)
- [配置](docs/configuration.md)
- [信源](docs/scrapers.md)和[正文提取器](docs/extractors.md)
- [画像](docs/profiles.md)和[评分](docs/scoring.md)
- [Agent Skill](docs/agent-skill.md) 和 [MCP 服务](src/mcp/README.md)

## 开发

```bash
uv sync --extra dev
uv run pytest
```

少数测试需要联网或可选的 `twitter` 依赖（Playwright）。

## 致谢

地平线每日快报基于 [Thysrael](https://github.com/Thysrael) 及其贡献者的开源项目 **[Horizon](https://github.com/Thysrael/Horizon)** 构建。采集流水线、信源抓取器、AI 评分与富化、画像、推送服务和 MCP 服务都来自该项目；本仓库新增了大报渲染器、静态站点发布器、Polymarket / arXiv / Bluesky 信源和 GitHub Pages 工作流。感谢 Horizon 作者以 MIT 协议开源。

## 许可证

[MIT](LICENSE)，保留了 Horizon 原始版权声明。
