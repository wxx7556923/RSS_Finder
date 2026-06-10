# Paper Radar Windows 新手使用说明

这个 Windows 包不再使用 WSL/Ubuntu，直接在 Windows Python 里运行。

如果不想看长说明，先打开：

```text
00-START-HERE-Windows.txt
```

## 第一次安装

1. 完整解压 zip，不要在压缩包预览窗口里双击。如果文件来自微信/QQ，不要直接在聊天文件目录里运行；请把解压后的 `PaperRadar` 文件夹复制到桌面、下载目录或 `C:\PaperRadar`。
2. 如果电脑已经有 Python 3.10 或更新版本，直接双击 `Windows-Install.bat`。
3. 如果电脑没有 Python，安装 Python 3.10 或更新版本：

```text
https://www.python.org/downloads/windows/
```

安装 Python 时勾选：

```text
Add python.exe to PATH
```

4. 回到解压后的 `PaperRadar` 文件夹，双击：

```text
Windows-Install.bat
```

安装脚本会做这些事：

- 自动检测已有 Python，并显示检测到的版本；
- 创建 `.venv` Python 虚拟环境；
- 如果包内有 `wheels` 目录，优先离线安装依赖；
- 如果包内没有 `wheels` 目录，再使用清华 PyPI 镜像安装依赖；
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
http://127.0.0.1:8090/?mode=original
```

## 停止、查看状态和日志

```text
Windows-Stop.bat      停止服务
Windows-Status.bat    查看是否运行
Windows-Logs.bat      查看最近日志
```

## 重新选择订阅源

双击：

```text
windows\configure-sources.bat
```

默认全部启用，输入不想要的编号即可关闭。

## 重新配置 API Key

双击：

```text
windows\config-env.bat
```

可以填写或更新：

- DeepSeek API Key：用于标题翻译、智能检索和 AI 摘要；
- NCBI API Key：用于 PubMed 摘要补全；
- NCBI Email：可选。

## 常见问题

### 双击 Windows-Install.bat 提示找不到 Python

安装 Python 3.10 或更新版本，并确认安装时勾选了 `Add python.exe to PATH`。安装后重新打开这个文件夹，再双击 `Windows-Install.bat`。

### 安装依赖失败

新版安装包如果带有 `wheels` 目录，会先离线安装依赖，不需要连接 PyPI。如果包内没有 `wheels`，安装脚本会使用清华 PyPI 镜像，并设置 `PIP_CONFIG_FILE=NUL` 和 `pip --isolated` 来忽略用户 pip 配置里的代理。如果仍然出现 `Cannot connect to proxy` 或连接被拒绝，通常是代理、VPN、校园网或公司网络限制。可以关闭代理/VPN、换网络，或向维护者索要带 `wheels` 的安装包。

### 提示 Permission denied

这表示当前 `PaperRadar` 文件夹不可写。常见原因是从微信/QQ文件目录、压缩包预览窗口或受保护目录中运行。请完整解压后，把 `PaperRadar` 文件夹复制到桌面、下载目录或 `C:\PaperRadar`，再双击 `Windows-Install.bat`。

### Windows-Start.bat 打不开网页

先双击：

```text
Windows-Status.bat
Windows-Logs.bat
```

如果提示没有安装，先运行 `Windows-Install.bat`。

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
