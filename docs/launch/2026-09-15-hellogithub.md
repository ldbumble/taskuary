### Project URL

https://github.com/ldbumble/taskuary

### Category

Python

### Project Title

Taskuary：从收到消息到智能体执行，再到人工审核的本地任务工作台

### Project Description

Taskuary 是一个本地运行的开源任务工作台，把邮件、工单和报表汇集到时间线，再整理成任务、交给智能体处理、带回人工审核。适合想把日常事务和编程任务放在同一处跟进的开发者。提供中文 README 和免登录演示，可查看 Python 后端如何衔接任务、编程 CLI 与会话恢复。

### Highlights

这是项目作者的自荐，目前仍处于早期阶段，希望收集实际使用反馈。

- 一条完整流程：收到请求 → 创建任务 → 查看智能体执行过程 → 审核结果。
- 最新源码已加入 Qwen Code、OpenCode 和 Kimi Code 集成。DeepSeek 等模型通过 OpenCode 配置，模型服务与 CLI 分开选择。
- 智能体可以留下交接笔记，通过 Hub 共享资料；可编辑的 `LEARNED.md` 记录用户纠正中总结出的工作习惯。
- 应用和任务数据保存在本机；使用云端模型或外部连接时，相关内容仍会发送给对应服务。本地运行不等于所有数据都不出机器。
- MIT 开源，支持 Windows、macOS、Linux；界面目前主要是英文，已有[简体中文说明与安装步骤](https://github.com/ldbumble/taskuary/blob/master/README.zh-CN.md)。

**CLI 验证范围：**已使用真实 Qwen Code、OpenCode、Kimi Code 程序与本地模拟模型端点验证集成。尚未完成这些集成的真实云端模型调用及中国大陆网络环境验证；欢迎有现成账号的开发者反馈安装、认证和任务执行情况。OpenCode、Kimi 预设目前用于执行任务，不用于消息分拣或只读报告。详细记录见 [Qwen](https://github.com/ldbumble/taskuary/blob/master/docs/qwen-code.md#compatibility-evidence) 与 [OpenCode / Kimi](https://github.com/ldbumble/taskuary/blob/master/docs/chinese-coding-clis.md)。

### Screenshots or Demo Videos

[浏览器演示](https://taskuary.com/demo/)：无需账号，使用虚构数据，不会连接外部账号或执行真实任务。

收到的消息与报表，在时间线上保留来源和时间：

![带有来源和时间的任务时间线](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/01-timeline-sources-and-times.png)

处理完成后，回到审核界面检查结果：

![人工审核智能体的处理结果](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/04-review.png)

在连接页面配置编程 CLI：

![Qwen Code、OpenCode 和 Kimi Code 等 CLI 的连接卡片](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/07-coding-clis-chinese.png)
