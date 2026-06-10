# Paper Radar Windows 新手使用说明

这个包适合不熟悉 Linux 的同学使用。最简单的规则是：每完成一个阶段后，都回到解压目录，再双击最外层的 `Windows-Install.bat`，直到它提示安装完成。

如果不想看长说明，先打开：

```text
00-START-HERE-Windows.txt
```

## 第一次安装

解压这个 zip 后，双击：

```text
Windows-Install.bat
```

然后按窗口提示走。

如果它提示安装 WSL Ubuntu，输入 `Y`。如果 Windows 要求重启，就重启。

重启后不要找别的文件，还是回到这个文件夹，继续双击：

```text
Windows-Install.bat
```

如果它弹出 Ubuntu 窗口，请创建 Ubuntu 用户名和密码。密码输入时屏幕不会显示字符，这是正常的。

Ubuntu 设置完成后，再回到这个文件夹，继续双击：

```text
Windows-Install.bat
```

安装脚本会做这些事：

- 在 WSL 里创建 Python 环境；
- 安装依赖；
- 让你按编号关闭不需要的订阅源；
- 让你填写 DeepSeek / NCBI API Key，直接回车可以跳过。

不懂 API Key 也没关系，直接跳过即可。原文模式不需要 DeepSeek。

## 启动

双击：

```text
Windows-Start.bat
```

浏览器会打开：

```text
http://localhost:8090/?mode=original
```

推荐先用原文模式。这个模式不消耗 DeepSeek API，适合配合浏览器翻译阅读标题和摘要。

## 停止、查看状态和日志

```text
Windows-Stop.bat     停止服务
Windows-Logs.bat     查看最近日志
windows\status.bat   查看是否运行
windows\open.bat     只打开浏览器页面
```

## 重新选择订阅源

双击：

```text
windows\configure-sources.bat
```

脚本会列出所有内置期刊源。默认全部启用，输入你不想要的编号即可关闭。比如不想要 arXiv，可以关闭名字里带 `arXiv` 的几项。

订阅源目录见：

```text
docs\SOURCES.md
```

以后维护者新增期刊源后，这个选择列表会自动更新。

## 重新配置 API Key

双击：

```text
windows\config-env.bat
```

可以填写或更新：

- DeepSeek API Key：用于标题翻译、智能检索和 AI 摘要；
- NCBI API Key：用于 PubMed 摘要补全；
- NCBI Email：可选。

## 日常使用

1. 双击 `Windows-Start.bat`。
2. 浏览器打开后点击 `抓取新文章`。
3. 看到感兴趣的文章，点击 `打开原文`。
4. 回到控制台写笔记、加标签、收藏或标为待读。
5. 看完后点 `标为已读`。

## 轻薄本能不能用

可以。这个工具不在本地跑大模型，主要是 RSS 抓取、SQLite 数据库和浏览器页面。DeepSeek 和 PubMed 都是远程 API。

建议先不要使用 Docker / FreshRSS。这个 Windows 新手包只启动 Paper Radar Web 控制台。

## 常见问题

### 双击 Windows-Start.bat 后打不开

先双击：

```text
windows\status.bat
Windows-Logs.bat
```

如果提示 WSL 不存在，需要先安装 WSL Ubuntu。

如果刚安装过 WSL，通常是因为还没有重启电脑，或者还没有第一次打开 Ubuntu 完成用户名和密码设置。请先重启，再从开始菜单打开 `Ubuntu` 完成初始化，然后重新运行：

```text
Windows-Install.bat
Windows-Start.bat
```

如果浏览器已经打开但 `localhost:8090` 显示无法访问，等 10 秒后再试一次 `Windows-Start.bat`，或者运行 `Windows-Logs.bat` 查看日志。

### 端口 8090 被占用

先双击：

```text
Windows-Stop.bat
```

然后再双击：

```text
Windows-Start.bat
```

### ScienceDirect 文章没有摘要

Cell Press / ScienceDirect 的 RSS 经常只给标题、作者和出版信息。系统会用 PubMed 尽力补摘要；如果 PubMed 暂时没有收录或没有摘要，就只能显示元信息。
