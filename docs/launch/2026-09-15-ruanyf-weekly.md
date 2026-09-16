我在开发一个 MIT 开源的本地任务工作台 **Taskuary**，想解决从“收到一条请求”到“智能体完成并交回审核”之间反复切换工具的问题，向周刊自荐。

基本流程是：邮件、工单或报表进入时间线 → 整理成任务 → 交给编程 CLI 或通用智能体 → 查看进度并审核结果。也可以直接手动创建任务。

除了执行任务，智能体可以留下交接笔记，借助 Hub 共享资料；从用户纠正中总结的工作习惯保存在可编辑的 `LEARNED.md` 中。

- 项目与源码：https://github.com/ldbumble/taskuary
- [简体中文介绍、截图和安装步骤](https://github.com/ldbumble/taskuary/blob/master/README.zh-CN.md)
- [免登录演示](https://taskuary.com/demo/)：虚构数据，不连接外部账号、不执行真实任务。

![Taskuary 时间线：每项保留消息来源和时间](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/01-timeline-sources-and-times.png)

最新源码加入了 Qwen Code、OpenCode（可配置 DeepSeek 等模型）和 Kimi Code。应用本地运行，使用云端模型时仍会向模型服务发送内容。

目前是早期项目，界面主要为英文。这三个 CLI 的集成已用真实程序与本地模拟模型端点验证，尚未完成真实云端模型调用和中国大陆网络环境验证；OpenCode、Kimi 预设目前用于执行任务。欢迎有现成服务账号的开发者试用，并反馈最需要的消息源和使用问题。
