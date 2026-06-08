# RSS Finder

一个面向 Linux 本地使用的 RSS 论文/期刊追踪控制台。它会抓取期刊 RSS、部分官网文章列表兜底来源和 bioRxiv/arXiv 来源，保存到本地 SQLite 数据库，并在网页中按来源、状态、关键词、收藏等条件筛选。配置 DeepSeek API Key 后，可以批量翻译标题；摘要区域优先展示来源提供的原始摘要。

这个仓库不包含个人数据：没有 `.env`、数据库、日志、RSS 输出文件或 FreshRSS 数据卷。

## 主要功能

- 聚合多个期刊 RSS、Nature/Springer/CSHL 官网文章列表兜底、arXiv 分类和 bioRxiv API 来源
- 本地 SQLite 去重保存文章
- Web 控制台浏览、检索、筛选和管理文章
- 一键同步：抓取新文章、应用过滤规则、翻译标题、重建 RSS
- DeepSeek 标题翻译
- 阅读状态管理：未读、已读、待精读、过滤
- 收藏、笔记、标签和 Zotero 标记
- 点击 `打开原文` 后自动标为已读
- 导出 RIS，方便导入文献管理工具
- 生成 `/feed.xml` 和 `/feed-original.xml`，可被 FreshRSS 订阅
- 提供期刊名查 RSS 的 Codex 工作流

## 默认关注来源

默认配置偏向植物生物学、基因组学、生物信息、AI for biology 和综合高影响期刊。可以直接使用，也可以删掉不需要的来源。

默认 RSS/feed 来源包括：

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

默认还启用了 bioRxiv API，分类包括：

- bioinformatics
- genomics
- systems_biology
- molecular_biology
- cell_biology

## 适合谁

- 熟悉 Linux 命令行的用户
- 想本地追踪期刊/RSS 的科研用户
- 愿意自己配置 DeepSeek API Key 的用户
- 想把筛选后的文章输出给 FreshRSS 的用户

它不是双击安装的软件；如果完全不想碰终端，这个版本还不够傻瓜。

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

- `抓取新文章`：只抓 RSS/bioRxiv/arXiv 并入库
- `应用规则`：重新应用过滤和标签规则
- `批量翻译标题`：只翻译待处理标题
- `重新生成 RSS`：重新输出 feed 文件

## RSS 输出

Web 服务启动后提供：

```text
http://localhost:8090/feed.xml
http://localhost:8090/feed-original.xml
```

- `feed.xml`：翻译标题并保留 RSS 摘要后的 RSS
- `feed-original.xml`：原始标题和原始 RSS 描述

## 配置 RSS 源

RSS 源在：

```text
config/app.yml
```

删除不需要的源时，删掉对应的 `name` 和 `url` 两行即可。

添加新源示例：

```yaml
feeds:
  - name: "My Journal"
    url: "https://example.com/rss"
```

也可以用命令追加：

```bash
python tools/add_feed.py --name "My Journal" --url "https://example.com/rss"
```

如果只知道期刊名，不知道 RSS 地址，使用：

```text
codex_workflows/journal_to_rss/SKILL.md
```

把里面的提示词交给 Codex，让它搜索官方期刊页面并生成可放进 `config/app.yml` 的 YAML。

## 过滤和标签规则

规则也在：

```text
config/app.yml
```

- `rules.exclude_rules`：匹配后自动标记为已过滤
- `rules.tag_rules`：匹配后自动加系统标签

默认规则会过滤 news、podcast、editorial、correction、retraction 等非研究类内容，并给 AI/ML、genomics 等主题加标签。

## FreshRSS 可选订阅

如果想用 FreshRSS 订阅本工具生成的 RSS：

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

如果不可用，在 Linux 中查看本机 IP：

```bash
hostname -I
```

然后尝试：

```text
http://你的IP:8090/feed.xml
```

## 健康检查

```bash
python tools/health_check.py
```

它会检查：

- `config/app.yml` 是否存在
- `.env` 是否存在
- `DEEPSEEK_API_KEY` 是否配置
- RSS 源数量
- `data/` 是否可写

没有配置 DeepSeek Key 时，抓取 RSS 仍然可用，但标题翻译和 AI 摘要不可用。

## 常用文件

- `config/app.yml`：RSS 源、规则、DeepSeek 参数
- `.env`：DeepSeek API Key，本地私密文件，不要提交
- `data/rss_ai.db`：本地数据库，运行后自动生成
- `output/output.xml`：AI 摘要 RSS
- `output/original.xml`：原文 RSS
- `logs/app.log`：运行日志
- `codex_workflows/journal_to_rss/SKILL.md`：期刊名查 RSS 的 Codex 工作流


## CLI 调试

```bash
python3 -m src.main fetch --limit 100
python3 -m src.main translate-titles --concurrency 3 --limit 100
python3 -m src.main summarize --article-id 12
```
