# 地平线每日快报（GitHub Actions + GitHub Pages 自动部署指南）

本指南帮助你用 **零服务器成本** 把《地平线每日快报》部署到 GitHub Pages，每天北京时间早 7:00 自动抓取全球信源、由 AI 生成中英双语深度快报，并维护可切换的历史期归档。

---

## 站点产出结构

每次流水线运行后，会在 `docs/broadsheet/` 下产出完整的纯静态站点（部署时直接作为 `gh-pages` 分支根目录）：

- `index.html`：站点首页，始终指向最新一期中文版《地平线每日快报》
- `YYYY-MM-DD-zh.html` / `YYYY-MM-DD-en.html`：每日双语独立归档页
- `latest-zh.html` / `latest-en.html`：最新一期固定入口
- `YYYY-MM-DD-{lang}.json`：当日结构化资讯数据
- `editions.json`：全量往期清单（页面顶部「往期」下拉菜单自动读取）
- `.nojekyll`：关闭 Jekyll 构建，加速并保真静态发布

---

## 4 步完成上线

### 第 1 步：推送到你自己的 GitHub 仓库

将当前仓库推送到你自己的 GitHub 仓库（确保包含 `.github/workflows/daily-broadsheet.yml` 和 `data/config.broadsheet.json`）。

### 第 2 步：配置 AI 模型密钥（Secrets）

进入 GitHub 仓库 → **Settings → Secrets and variables → Actions → Secrets**，点击 **New repository secret**：

- **默认配置（OpenAI，支持自动识别主流 Key）**：
  - Name: `OPENAI_API_KEY`
  - Value: 你的 OpenAI API Key（默认使用 `gpt-4o-mini`，可在 Variables 中设 `AI_MODEL` 改用 `gpt-4o` 等其他模型）

如改用 DeepSeek / Claude / Gemini，直接添加对应 Secret（`DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY`），工作流会自动识别并切换默认模型；也可在 **Variables** 标签页精细覆盖：
   - `AI_PROVIDER`（如 `openai` / `anthropic` / `gemini` / `ali`）
   - `AI_MODEL`（如 `gpt-4o-mini` / `claude-sonnet-4-5` / `gemini-2.5-flash`）
   - `AI_API_KEY_ENV`（如 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY`）
   - `AI_BASE_URL`（如使用中转或自定义端点时填写，否则留空）

### 第 3 步：首次手动触发构建

1. 进入仓库 **Actions** 页面，选择左侧 **Daily Broadsheet (地平线每日快报)**；
2. 点击 **Run workflow**（可保持默认 `hours = 24`）等待约 2~5 分钟执行完成；
3. 成功后仓库会自动创建并推送 `gh-pages` 分支。

### 第 4 步：开启 GitHub Pages（并可选绑定自定义域名）

1. 进入 **Settings → Pages**；
2. **Build and deployment → Source** 选择 `Deploy from a branch`；
3. **Branch** 选择 `gh-pages`、目录选 `/ (root)`，点击 **Save**；
4. 1~2 分钟后即可通过 `https://<你的用户名>.github.io/<仓库名>/` 访问《地平线每日快报》！
5. 如需自定义域名（如 `news.yourdomain.com`），在 Pages 设置页填写 Custom domain 并配置对应 CNAME 记录即可自动获得 HTTPS。

---

## 自定义频率与信息源

- **修改更新时间**：编辑 `.github/workflows/daily-broadsheet.yml` 中的 `cron: '0 23 * * *'`（GitHub Actions 使用 UTC 时间，`23:00 UTC` = 北京时间 `07:00`）。
- **增减信息源 / 调整条数**：直接编辑 `data/config.broadsheet.json`（已内置 20 条上限与三版面均衡配额：科技新闻 9 / 科技博客 6 / 财经新闻 5）。
- **开启 Twitter / X 抓取（Apify 自动感知模式）**：
  1. 前往 [Apify Console](https://console.apify.com/account/integrations) 复制你的 Personal API token（每月含免费额度）；
  2. 在 GitHub 仓库 **Settings → Secrets and variables → Actions → Secrets** 添加 `APIFY_TOKEN`；
  3. 配置完成后每日工作流会自动抓取 Twitter 关注账号列表及高赞回复（未配置 `APIFY_TOKEN` 时自动跳过、不影响其他源）；
  4. 如需自定义关注的 X 账号，可在 **Variables** 中添加 `TWITTER_USERS`（逗号分隔，如 `karpathy,sama,OpenAI,AnthropicAI`）或直接修改 `data/config.broadsheet.json` 中的 `sources.twitter.users`。
- **本地零费用预览测试**：运行 `uv run python scripts/generate_broadsheet_preview.py --live` 即可在 `docs/broadsheet/` 下生成实时抓取的本地站点并用 `python3 -m http.server -d docs/broadsheet 8080` 预览往期切换与双语切换效果。

## 失败保护与告警

- **部署前校验**：工作流在推送 `gh-pages` 之前运行 `python -m src.rendering.verify`。当本次运行没有生成新一期、某种语言的条目数低于下限，或版面文件缺失时，工作流直接失败并跳过部署，线上保持上一期内容。
- **条目数下限**：默认 5 条，可在 **Variables** 中添加 `MIN_EDITION_ITEMS` 调整。
- **失败告警**：工作流失败时会在仓库里创建（或追加评论到）带 `daily-edition-failure` 标签的 issue，并附上运行日志链接；下一次成功发布后该 issue 自动关闭。
