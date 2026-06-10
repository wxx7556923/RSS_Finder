# 订阅源目录

这个文件面向维护者和普通用户，记录当前内置的期刊/RSS 来源。普通用户不需要自己查 RSS；在 Windows 安装时可以按编号关闭不需要的来源。

## 微生物、宿主互作和免疫相关

- Cell Host & Microbe
  - RSS: `https://rss.sciencedirect.com/publication/science/19313128`
  - 说明：Cell Press / ScienceDirect 源，适合宿主-微生物互作、病原和免疫方向。
- Nature Microbiology
  - RSS: `https://www.nature.com/nmicrobiol.rss`
- Nature Reviews Microbiology
  - RSS: `https://www.nature.com/nrmicro.rss`
- Nature Immunology
  - RSS: `https://www.nature.com/ni.rss`
- Nature Reviews Immunology
  - RSS: `https://www.nature.com/nri.rss`
- ISME Communications
  - RSS: `https://www.nature.com/ismecomms.rss`
- Immunity
  - RSS: `https://rss.sciencedirect.com/publication/science/10747613`
- Cell Systems
  - RSS: `https://www.cell.com/action/showFeed?type=etoc&feed=rss&jc=cell-systems`
- Cell Reports Medicine
  - RSS: `https://rss.sciencedirect.com/publication/science/26663791`
- Trends in Microbiology
  - RSS: `https://rss.sciencedirect.com/publication/science/0966842X`
- Trends in Immunology
  - RSS: `https://rss.sciencedirect.com/publication/science/14714906`
- Current Opinion in Microbiology
  - RSS: `https://rss.sciencedirect.com/publication/science/13695274`
- Current Opinion in Immunology
  - RSS: `https://rss.sciencedirect.com/publication/science/09527915`
- Current Opinion in Plant Biology
  - RSS: `https://rss.sciencedirect.com/publication/science/13695266`
- PLOS Pathogens
  - RSS: `https://journals.plos.org/plospathogens/feed/rss`
- PLOS Biology
  - RSS: `https://journals.plos.org/plosbiology/feed/rss`
- PLOS Genetics
  - RSS: `https://journals.plos.org/plosgenetics/feed/rss`
- PLOS Computational Biology
  - RSS: `https://journals.plos.org/ploscompbiol/feed/rss`
- mBio (ASM, optional) / mSystems / mSphere / Microbiology Spectrum / Applied and Environmental Microbiology / Infection and Immunity
  - RSS: `https://journals.asm.org/action/showFeed?...`
  - 说明：这些 ASM 源已写入 `config/app.yml`，但默认 `enabled: false`。原因是 `journals.asm.org` 当前对脚本抓取经常返回 HTTP 403；如果以后本机网络可访问，可以在 Windows 安装向导或 `config/app.yml` 里手动开启。

## 植物学和植物免疫相关

- Nature Plants
  - RSS: `https://www.nature.com/nplants.rss`
- Molecular Plant
  - RSS: `https://rss.sciencedirect.com/publication/science/16742052`
- Plant Communications
  - RSS: `https://rss.sciencedirect.com/publication/science/25903462`
- The Plant Cell
  - RSS: `https://academic.oup.com/rss/site_6317/advanceAccess_4077.xml`
- Journal of Experimental Botany
  - RSS: `https://academic.oup.com/rss/site_5304/advanceAccess_3170.xml`
- New Phytologist
  - RSS: `https://onlinelibrary.wiley.com/action/showFeed?type=etoc&feed=rss&jc=14698137`
- Plant Biotechnology Journal
  - RSS: `https://onlinelibrary.wiley.com/action/showFeed?type=etoc&feed=rss&jc=14677652`
- The Plant Journal
  - RSS: `https://onlinelibrary.wiley.com/action/showFeed?type=etoc&feed=rss&jc=1365313x`
- Plant, Cell & Environment
  - RSS: `https://onlinelibrary.wiley.com/action/showFeed?type=etoc&feed=rss&jc=13653040`
- Trends in Plant Science
  - RSS: `https://rss.sciencedirect.com/publication/science/13601385`

## 综合、组学、生信和 AI 相关

- Nature
- Nature Genetics
- Nature Communications
- Nature Machine Intelligence
- Nature Computational Science
- Nature Reviews Genetics
- Nature Methods
- Nature Biotechnology
- Science
- Science Advances
- Cell
- Cell Systems
- Cell Reports Medicine
- Current Biology
- Cell Reports
- Cell Genomics
- Genome Biology
- Genome Research
- PNAS
- Advanced Science
- arXiv cs.CL / cs.LG / cs.AI / q-bio.BM
- bioRxiv: bioinformatics, genomics, systems_biology, molecular_biology, cell_biology

## 维护规则

- 普通 RSS 源写在 `config/app.yml` 的 `feeds:` 下。
- 官网兜底抓取源写在 `config/app.yml` 的 `html_sources:` 下。
- bioRxiv 分类写在 `config/app.yml` 的 `biorxiv_api.categories:` 下。
- Windows 安装向导读取 `config/app.yml`，所以新增或删除订阅源后，用户安装时会自动看到新的编号列表。
- 新增或替换 RSS 后，先运行 `python tools/check_sources.py --contains sciencedirect.com` 或 `python tools/check_sources.py`，确认配置名和远程 feed 标题一致。
- 如果本地显示名和远程 feed 标题天然不同，可以在对应 `feeds:` 项下加 `expected_title:`，只用于 `tools/check_sources.py` 校验，不影响抓取。
- ScienceDirect / Cell Press RSS 通常只给标题、作者和出版信息；系统会用 PubMed 尽力补摘要，查不到就保留原始元信息。
