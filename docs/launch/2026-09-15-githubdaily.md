- 项目名称：Taskuary（作者自荐，MIT 开源）

- 项目地址：https://github.com/ldbumble/taskuary

- 项目简介（100 字以内）：

  本地任务工作台：把消息整理成任务，交给智能体执行，再由你审核结果。支持编程 CLI、交接笔记、共享资料，以及可编辑的 Markdown 记忆。

- 项目截图（6 张以内）：

  ![消息、工单和报表进入同一条时间线](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/01-timeline-sources-and-times.png)

  ![人工审核智能体的处理结果](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/04-review.png)

  ![编程 CLI 连接页面](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/07-coding-clis-chinese.png)

补充链接：[中文 README 与安装说明](https://github.com/ldbumble/taskuary/blob/master/README.zh-CN.md) · [免登录演示](https://taskuary.com/demo/)（虚构数据，不执行真实任务）。

项目仍处于早期阶段，界面主要为英文。最新源码包含 Qwen Code、OpenCode 和 Kimi Code 集成；这些集成已使用真实 CLI 与本地模拟模型端点验证，尚未完成真实云端模型调用及中国大陆网络环境验证。DeepSeek 等模型通过 OpenCode 配置；OpenCode、Kimi 预设目前用于执行任务。本地运行的应用使用云端模型时仍会向对应服务发送内容。欢迎反馈。
