# Taskuary

[English](README.md) · **简体中文**

[![CI](https://github.com/ldbumble/taskuary/actions/workflows/ci.yml/badge.svg)](https://github.com/ldbumble/taskuary/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/taskuary.svg?cacheSeconds=300&release=0.3.6.1&asof=2026-09-22f)](https://pypi.org/project/taskuary/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)](https://www.python.org/)
[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/ldbumble/taskuary?style=flat&color=d4a72c&label=%E2%98%85%20stars)](https://github.com/ldbumble/taskuary/stargazers)

<p align="center"><b>⭐ 如果 Taskuary 对你有帮助，请给它一个 Star</b> —— 这是别人发现它的方式。</p>

## 让 AI 智能体帮你处理收件箱里的工作

Taskuary 在本机运行，把收到的消息整理成任务，交给智能体处理，再把结果带回给你审核。
它帮你分清哪些消息需要行动、哪些可以归档，以及哪些事情正在等待你的决定。
对外发送和交付由你批准。

![工作到来时，Taskuary 的工作室逐渐展开，AI 智能体就位。](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/hero.gif?v=workspace)

Taskuary 仍处于早期阶段，目前为 **v0.3.6.1**，1.0 之前可能出现不兼容变更。
应用界面和演示截图目前以英文为主；下文保留英文按钮名称，方便对照操作。

<p align="center">
  <a href="https://taskuary.com/demo/"><img
    src="https://img.shields.io/badge/%E2%96%B6%20Try%20it%20now-no%20install%2C%20in%20your%20browser-2f4858?style=for-the-badge&labelColor=1f2a22"
    alt="立即体验 Taskuary，无需安装"></a>
</p>

<p align="center"><sub>真实界面，虚构数据。演示不会连接外部服务、发送消息或运行智能体。</sub></p>

<p align="center"><b><a href="https://taskuary.com/docs/">阅读文档（英文）</a></b> —— 安装、初次运行、连接哪些系统，以及每一项设置。</p>

想从 Qwen Code 开始？可以使用 **本地 Taskuary + Ollama 分拣消息 + Qwen Code 编程**，
无需把 Claude Code、Codex 或 Gemini 作为必选依赖。
Qwen Code 使用哪个云端或本地模型，由你配置。见[使用 Qwen Code](#使用-qwen-code)。

## Taskuary 能做什么

用一个简单流程来了解应用：Ruth 希望在运营会议前拿到最新的供应商支出数据。
下面用同一项请求，从收到消息走到最终审核；所有业务数据均为虚构。

### 1. 把各处的工作放到同一条时间线

邮件、聊天、工单、提醒和报表汇集到 **Timeline**。不用逐个打开系统，也能看到什么刚到、
什么变成了任务，以及什么正在等你处理。图中的每一行都标注了来源，下面保留原来的时间。

![时间线中的邮件、Teams、WhatsApp、GitHub、SQL 报表、助手和日历，每行同时显示来源与时间。](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/01-timeline-sources-and-times.png)

### 2. 把请求变成任务

Ruth 想要八月份的总额、与七月份的对比，以及按类别划分的明细。
Taskuary 创建任务，保留原始请求，并关联负责处理的智能体。

![任务 TQ-0018 展示原始请求、负责人、任务状态和智能体工作区域。](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/02-task.png)

### 3. 查看智能体的工作过程

打开任务的 **Agent work**，查看分析过程并回答它的问题。
这里的通用智能体整理支出数据、核对分类合计，并准备回复草稿。

![通用智能体整理供应商支出，展示总额、分类明细、环比和数据来源。](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/03-agent.png)

### 4. 审核结果后再发送

回复进入 **Review**。核对原始请求、金额、收件人和措辞，必要时编辑，
最后点击 **Approve & send**。你也可以要求重新起草、拒绝，或标记为无需回复。

![审核页面对照原始请求与回复草稿，并提供批准发送、重写和拒绝操作。](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/04-review.png)

### 5. 让助手带你看下一步

在 **Assistant** 中选择 **Walk me through my tasks**。
助手把当前需要关注的任务带入对话，并提供直接打开任务的入口。

![助手围绕 Ruth 的请求展开对话，并链接到对应任务。](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/05-assistant.png)

### 6. 用每日摘要开始一天

打开 **Morning digest**，查看别人需要什么、哪些事情正在推进，以及今天的会议。
日历就在摘要上方：这项支出分析需要在运营会议前准备好。

![带有日历动画的每日摘要，展示运营会议和供应商规划会议。](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/06-morning.gif)

## 核心功能

### 使用你选择的编程 CLI

支持 Qwen Code、OpenCode、Kimi Code、Claude Code、Codex、Gemini、Cursor、Copilot、Muse Code、Devin，
也支持其他能够从标准输入接收提示词的 CLI。配置连接后，为不同智能体设置职责和指令，
在 Taskuary 中跟进会话、回答问题和审核结果。

通过 OpenCode 可使用 DeepSeek、GLM 或 MiniMax；Kimi Code 则提供 Moonshot 的编程 CLI。
在 **Connections → AI CLI agents** 中安装，OpenCode 用 `/connect` 配置服务，Kimi 用 `/login` 登录。
这两个预设用于执行任务；消息分拣和只读报告请选择 Qwen Code、Ollama 或 API 服务。
详见[安装步骤和验证范围（英文）](docs/chinese-coding-clis.md)。

![Claude、Qwen、OpenCode（支持 DeepSeek）和 Kimi Code 的连接卡片。](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/07-coding-clis-chinese.png)

### 用 Hub 保留共享知识

按主题保存发现、决定和有用的提醒。智能体可以查阅前面的工作、补充讨论，
也可以根据新证据纠正结论，减少重复摸索。

![Hub 中按主题组织的共享发现，以及智能体之间的讨论。](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/08-hub.png)

### 智能体之间可以交接留言

Board 的 **Live handoffs** 展示当前进展、阻碍和待接手事项。
一个智能体留下说明，下一个接手时就能读到上下文；已读标记显示谁看过这条留言。

![智能体的交接留言，包括进展、共享上下文和已读标记。](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/09-handoffs.png)

### 从你的决定中学习

你修改的草稿、重新分类的任务，都会成为了解你工作习惯的证据。
反复出现的规律会写入 **LEARNED.md**：你怎样写回复、负责什么、哪些事情值得创建任务。
例如，你多次把金额移到回复开头，它就可以学会以后先写总额。

打开 **Docs → LEARNED.md**，可以阅读、修改或删除这些记忆。
你在 `SOUL.md` 中写下的指令始终优先。

![LEARNED.md 编辑器中可查看和修改的偏好、证据、待验证假设和待批准规则。](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/11-learned-memory.png)

<details>
<summary>技术细节：LEARNED.md 如何形成记忆</summary>

- **从纠正开始。** 模型把明确的纠正整理成假设；批量反思会比较多次决定，也会考虑未修改就批准的草稿。
- **保留依据。** 自动生成的记忆带有 `s`（强度）、`ev`（证据编号）、`seen`（最近得到支持的日期），以及用于跨次改写识别同一条记忆的 `k`。
- **积累证据再生效。** 新假设从强度 2 开始。反思指令要求达到 4，并有至少三个事件、来自至少两个人或两个会话的支持，才升级为有效记忆。反例会削弱它，长期没有支持的假设也会逐渐衰减。
- **只使用有效记忆。** 提示词构建时会排除假设、待批准规则和原始决定记录。有效记忆用于消息分拣、回复草稿和智能体上下文。
- **控制权仍在你手里。** 推断出来的隐藏或归档规则先进入待批准区；两次相符的明确用户决定可以提供授权。你手写的不带机器标签的内容会保留，也可以在 Settings 中关闭学习。

参见[从你的决定中学习（英文文档）](https://taskuary.com/docs/how-it-works#correcting-it-teaches-it)，
或查看实现：[learn.py](taskuary/learn.py)、[learnedgraph.py](taskuary/learnedgraph.py)。

</details>

### 什么数据会离开你的机器

![任务上下文发送给所选 AI 服务或 CLI 前，先经过凭据检测；原始邮件保持不变。](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/10-prompt-privacy.svg)

Taskuary 在本机运行。使用云端模型时，完成工作所需的上下文会作为提示词发送给模型服务。
**如果模型也运行在本机，AI 提示词也可以留在本机。** 邮件等已连接的外部服务仍通过你配置的连接通信。

提示词发送前，能识别出的 API 密钥、带凭据的连接字符串、私钥等会被替换成带标签的占位符，
例如 `[redacted:aws-key]`。检测覆盖云端模型、无界面的 CLI 调用和智能体终端的第一条提示词。
原始邮件不会被改写；回复如果还包含这种占位符，会被阻止发送。

这套检测采用确定性规则，识别有特定结构的凭据，并不能发现所有秘密。
例如，“Wi-Fi 密码是 bluefish17”这样的普通句子未必能被识别。
安全问题请通过 [SECURITY.md](SECURITY.md) 报告。

## 安装

### Windows 应用

下载并打开最新版 [Taskuary.exe](https://github.com/ldbumble/taskuary/releases/latest/download/Taskuary.exe)，
无需单独安装 Python。

### Python

支持 Windows、macOS 和 Linux，需要 Python 3.10 或更新版本：

```bash
pip install taskuary
taskuary
```

打开 [http://127.0.0.1:7787](http://127.0.0.1:7787)。
若希望使用原生桌面窗口，安装 `pip install "taskuary[desktop]"`，然后运行 `taskuary-desktop`。

### Docker

```bash
git clone https://github.com/ldbumble/taskuary
cd taskuary
docker compose up
```

随后打开 [http://127.0.0.1:7787](http://127.0.0.1:7787)。
Docker 运行 Web 应用；编程 CLI 和可选的 WhatsApp 桥接程序位于宿主机。

首次运行时，在 **Connections** 中配置用于分拣的 AI、至少一个消息来源，以及处理任务的编程 CLI。
每个连接都可以先测试再启用。可以先用 IMAP 邮箱、已有数据库或手动创建的任务尝试基本流程。

## 使用 Qwen Code

1. 打开 **Connections → AI CLI agents → Qwen Code**，点击 **Install**。
   官方独立安装方式包含所需运行时。若自己使用 npm 安装，需要 **Node.js 22+**：
   `npm install -g @qwen-code/qwen-code@latest`。
2. 点击 **Set it up**，在 Qwen 终端运行 `/auth`，选择模型服务。
   使用阿里云百炼时，请选择与你的账号和套餐一致的区域与认证方式，
   参照[官方认证说明](https://qwenlm.github.io/qwen-code-docs/en/users/configuration/auth/)。
3. 保存并点击 **Test**。将 Qwen 分配给编程任务；模型字段留空时沿用 Qwen 自己的配置。
4. 先在测试仓库中完成一个小任务，核对结果，再停止并继续会话，确认上下文能保留。

若当前安装的 Taskuary 版本尚未显示 Qwen，请使用最新源码：

```bash
git clone https://github.com/ldbumble/taskuary
cd taskuary
pip install -e .
taskuary
```

消息分拣可以选择 Ollama，也可以在 **Settings → Triage brain** 中选择 Qwen。
**Qwen Code 是本地 CLI，不等于本地模型**：选择云端服务时仍会发送提示词；
希望本地推理时，需要另外配置本地模型端点。

已使用真实 Qwen Code 0.23.4 和本地模拟模型端点验证任务执行、进度、会话恢复、ACP 及分拣时的工具限制。
这不代表已经验证付费账号、真实模型效果或中国大陆网络环境。
完整步骤与验证范围见 [Qwen Code 集成说明（英文）](docs/qwen-code.md)。

## 不连接任何服务，先试用

```bash
taskuary --demo
# 或：docker compose --profile demo up
```

演示使用虚构工作和预设回复，不会访问外部系统、发送消息、运行工具或启动智能体。
刷新后，演示中的修改会重置。

## 安装量

![PyPI 每日安装量，不含镜像流量。](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/downloads.svg)

数据每天更新，不包含镜像流量。原始数据见 [docs/downloads.csv](docs/downloads.csv)。

## 文档

完整文档（英文）在 **[taskuary.com/docs](https://taskuary.com/docs/)**。

- [入门指南](https://taskuary.com/docs/)：安装、初始配置、Docker 和数据存储。
- [工作原理](https://taskuary.com/docs/how-it-works)：完整流程、五条路径、学习机制和配置文档。
- [连接](https://taskuary.com/docs/connections)：消息渠道、AI、业务系统和报表来源。
- [任务与智能体](https://taskuary.com/docs/tasks-and-agents)：任务、智能体工作与回复是三条独立的生命周期。
- [报表与助手](https://taskuary.com/docs/reports)：报表处理流程及助手的检查范围。
- [设置参考](https://taskuary.com/docs/settings)：全部设置项，由应用自身读取的同一份 schema 生成。
- [状态与路线图](docs/roadmap.md)：当前能力和后续计划。
- [贡献指南](CONTRIBUTING.md)：开发环境与贡献方式。

以上详细文档目前主要为英文。本页与 [English README](README.md) 对应；欢迎通过 Issue 或 PR 反馈翻译问题。
Taskuary 使用 [MIT 许可证](LICENSE)，免费开源。安全报告请使用 [SECURITY.md](SECURITY.md) 中的渠道。
