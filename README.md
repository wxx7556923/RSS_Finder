# RSS Finder

面向科研用户的本地期刊追踪工作台。RSS Finder 会抓取期刊 RSS、部分官网文章列表、bioRxiv API 和 arXiv feed，把文章保存到本地 SQLite 数据库，并提供网页界面用于浏览、筛选、标记、笔记、导出和生成订阅输出。

仓库不包含个人数据：没有 `.env`、数据库、日志、RSS 输出文件或 FreshRSS 数据卷。

## 功能特点

- 多来源抓取：期刊 RSS、Nature/Springer/CSHL 官网文章列表、bioRxiv API、arXiv feed
- 本地数据库：文章统一进入 SQLite，自动去重，保留阅读状态、收藏、笔记、标签和删除记录
- 网页工作台：按来源、状态、关键词、收藏、系统标签浏览和筛选文章
- 一键同步：抓取新文章、应用过滤规则、翻译标题、重建 RSS 输出
- 标题翻译：配置 DeepSeek API Key 后可批量生成中文标题
- 原始摘要展示：优先展示来源提供的摘要、作者和文章描述
- 阅读管理：未读、已读、待精读、过滤；点击 `打开原文` 自动标为已读
- 文章管理：收藏、笔记、手动标签、删除、Zotero 状态标记
- 删除保护：删除过的文章会记录在本地数据库中，后续同步不会重新导入同一篇
- 文献导出：单篇导出 RIS，方便导入 Zotero、EndNote 等文献管理工具
- RSS 输出：提供 `/feed.xml` 和 `/feed-original.xml`，可被 FreshRSS 或其他 RSS 阅读器订阅
- 来源健康记录：记录各来源最近抓取状态、HTTP 状态码、条目数量和错误信息
- Codex 工作流：提供期刊名查 RSS 的提示词模板，方便继续添加新期刊

## 数据库管理能力

RSS Finder 的核心数据保存在 `data/rss_ai.db`。网页上的阅读状态、收藏、笔记、标签、Zotero 标记、删除记录都基于这个数据库管理。

数据库中会保存：

- 文章来源、标题、链接、发布时间、抓取时间
- RSS 或官网页面提供的原始摘要和作者信息
- DeepSeek 翻译后的中文标题
- 阅读状态：未读、已读、待精读、过滤
- 收藏状态、用户笔记、用户标签、系统标签
- 删除记录，用于避免同步时重新导入已删除文章
- 来源健康状态，用于查看哪些来源抓取成功或失败

## 默认关注来源

默认配置偏向植物生物学、基因组学、生物信息、AI for biology 和综合高影响期刊。可以直接使用，也可以删掉不需要的来源。

默认期刊/feed 来源包括：

- Nature
- Nature Genetics
- Nature Communications
- Nature Plants
- Nature Machine Intelligence
- Nature Computational Science
- Nature Reviews Genetics
- Nature Methods
- Nature Biotechnology
- Science
- Science Advances
- Cell
- Molecular Plant
- Plant Communications
- The Plant Cell
- Journal of Experimental Botany
- Horticulture Research
- Developmental Cell
- Current Biology
- Cell Reports
- Trends in Plant Science
- Trends in Genetics
- PNAS
- Advanced Science
- New Phytologist
- Plant Biotechnology Journal
- The Plant Journal
- Plant, Cell & Environment
- Genome Biology
- Genome Research
- Cell Genomics
- arXiv cs.CL
- arXiv cs.LG
- arXiv cs.AI
- arXiv q-bio.BM

默认 bioRxiv API 分类包括：

- bioinformatics
- genomics
- systems_biology
- molecular_biology
- cell_biology

默认官网文章列表兜底来源包括：

- Nature 系列期刊
- Genome Biology
- Genome Research

## 快速开始

Linux 需要有 Python 3、venv 和 pip。Ubuntu/Debian 可以先安装：

```bash
sudo apt install python3 python3-venv python3-pip
```

克隆仓库后进入目录：

```bash
git clone git@github.com:wxx7556923/RSS_Finder.git
cd RSS_Finder
```

创建本地环境变量文件：

```bash
cp .env.example .env
```

编辑 `.env`，填入自己的 DeepSeek API Key：

```bash
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

启动 Web 控制台：

```bash
bash start.sh
```

打开：

```text
http://localhost:8090
```

## 日常使用

推荐主流程：

1. 点击 `一键同步`
2. 浏览文章列表
3. 对感兴趣的文章点击 `打开原文`
4. 对暂时要保留的文章点击 `待精读`
5. 对看完的文章点击 `标为已读`
6. 需要时点击 `重新生成 RSS`

备用按钮：

- `抓取新文章`：抓取 RSS、官网兜底来源、bioRxiv 和 arXiv 并入库
- `应用规则`：重新应用过滤和标签规则
- `批量翻译标题`：翻译待处理标题
- `重新生成 RSS`：重新输出 feed 文件

## 网页界面

网页工作台支持：

- 来源筛选
- 阅读状态筛选
- 收藏筛选
- 标题、摘要、笔记、标签关键词搜索
- 智能检索词扩展
- 原文模式和翻译标题模式切换
- 打开原文
- 标为已读
- 标为待精读
- 收藏
- 笔记
- 用户标签
- Zotero 状态标记
- 删除文章
- 导出 RIS

## RSS 输出

Web 服务启动后提供：

```text
http://localhost:8090/feed.xml
http://localhost:8090/feed-original.xml
```

- `feed.xml`：翻译标题并保留来源摘要后的 RSS
- `feed-original.xml`：原始标题和来源原始摘要

## 配置来源

配置文件：

```text
config/app.yml
```

RSS 来源写在 `feeds`：

```yaml
feeds:
  - name: "My Journal"
    url: "https://example.com/rss"
```

官网文章列表兜底来源写在 `html_sources`：

```yaml
html_sources:
  - name: "My Journal"
    url: "https://example.com/articles"
    parser: "nature_articles"
    pages: 2
```

也可以用命令追加 RSS：

```bash
python tools/add_feed.py --name "My Journal" --url "https://example.com/rss"
```

如果只知道期刊名，不知道 RSS 地址，可以使用：

```text
codex_workflows/journal_to_rss/SKILL.md
```

## 过滤和标签规则

规则写在：

```text
config/app.yml
```

- `rules.exclude_rules`：匹配后自动标记为已过滤
- `rules.tag_rules`：匹配后自动添加系统标签

默认规则会处理 news、podcast、editorial、correction、retraction 等非研究类内容，并给 AI/ML、genomics、crop genomics、single-cell、stress tolerance 等主题添加标签。

## FreshRSS 可选订阅

启动 FreshRSS：

```bash
docker compose up -d
```

FreshRSS 页面：

```text
http://localhost:8080
```

在 FreshRSS 中添加订阅：

```text
http://host.docker.internal:8090/feed.xml
```

Linux 下也可以查看本机 IP：

```bash
hostname -I
```

然后订阅：

```text
http://你的IP:8090/feed.xml
```

## 健康检查

```bash
python tools/health_check.py
```

检查内容：

- `config/app.yml`
- `.env`
- `DEEPSEEK_API_KEY`
- RSS 源数量
- `data/` 写入权限

## 常用文件

- `config/app.yml`：来源、规则、DeepSeek 参数
- `.env`：DeepSeek API Key，本地私密文件，不要提交
- `data/rss_ai.db`：本地 SQLite 数据库
- `output/output.xml`：翻译标题 feed
- `output/original.xml`：原文 feed
- `logs/app.log`：运行日志
- `codex_workflows/journal_to_rss/SKILL.md`：期刊名查 RSS 的 Codex 工作流

## CLI 调试

```bash
python3 -m src.main fetch --limit 100
python3 -m src.main translate-titles --concurrency 3 --limit 100
python3 -m src.main build-feed
```
