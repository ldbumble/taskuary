# Chinese developer launch draft

Prepared 2026-09-15. Submission copy and routes; nothing has been submitted or posted.

## Positioning

**本地运行的任务工作台：把收到的消息变成任务，交给 Qwen Code 等智能体处理，再由你审核结果。**

Lead with one workflow and the local-app architecture. Offer Qwen Code plus Ollama as a setup
that does not require Claude Code, Codex, or Gemini. Describe the actual model provider separately:
Qwen Code can call a cloud model, and installing it does not make inference local.

The Chinese README and integration are ready in source. Before a wider launch, publish a release
containing the preset and have a mainland-based user verify installation, authentication, a real
coding task, session continuation, and the chosen inbound channel. The current compatibility
check used the real Qwen binary with a local mock endpoint; it did not establish regional access
or model quality. Record those results in [Qwen Code compatibility](qwen-code.md#compatibility-evidence).

## Distribution order

This order is a proposed launch sequence, not a claim about guaranteed reach:

1. **HelloGitHub.** Use its [project submission form](https://github.com/521xueweihan/HelloGitHub/issues/new?template=submit-en.yaml).
   Its [current template](https://github.com/521xueweihan/HelloGitHub/blob/master/.github/ISSUE_TEMPLATE/submit-en.yaml)
   accepts GitHub-hosted open-source projects, including your own. Search for an existing
   recommendation first and read the linked review guidelines.
2. **OSChina.** Its [operating guide](https://www.oschina.net/help-center/oschina-guides/how-to-play-in-osc.html)
   describes submitting a project to the software directory. Start with the listing, then
   attach release news to it. The signed-in submission flow still needs checking in the
   publisher's account; do not assume a Gitee mirror is required for the directory.
3. **Juejin or SegmentFault.** Publish an original technical walkthrough: one incoming request,
   one Qwen task, live progress, and the approval step. Explain stdin versus ACP, session IDs,
   and the distinction between local storage and cloud inference. Use the tested version and
   reproduction steps instead of broad availability claims.
4. **V2EX.** Its [分享创造 node](https://www.v2ex.com/go/create) welcomes new projects.
   Use a short first-person post with the working demo and specific questions for feedback.
   Posting eligibility must be checked in the actual account; no account-age requirement or
   launch date was established by this research.
5. **Curators and newsletters.** After the first users confirm the workflow, adapt the short
   description for GitHubDaily, Zhihu, or ruanyf's weekly. Check each current submission route
   before sending anything. Add a Gitee mirror only if actual users report download friction
   and someone will maintain the mirror.

## HelloGitHub submission copy

**Project URL:** https://github.com/ldbumble/taskuary

**Category:** Python

**Project title:** Taskuary：在本机把消息整理成任务，交给 AI 智能体处理

**Description:**

Taskuary 是一个本地运行的开源任务工作台。它把邮件、工单和报表汇集到时间线，整理成任务，
交给 Qwen Code 等编程 CLI 或通用智能体处理，再把回复与结果带回审核。支持查看执行过程、
继续会话，并用可编辑的 LEARNED.md 保存从用户纠正中学到的工作习惯。

**Highlights:**

- 从消息到任务、执行、审核，用同一个界面跟进。
- Qwen Code 可以使用用户配置的云端或本地模型；Taskuary 本身在本机运行。
- 保留会话上下文，智能体可以留下交接留言，并通过 Hub 共享发现。
- 学习记录是可阅读和修改的 Markdown；原始邮件不会因提示词中的凭据遮盖而被改写。
- MIT 开源，支持 Windows、macOS 和 Linux；提供无需连接账号的演示模式。

**Demo:** https://taskuary.com/demo/

**Chinese README:** https://github.com/ldbumble/taskuary/blob/master/README.zh-CN.md

**Suggested screenshots:** the [Timeline](readme/01-timeline-sources-and-times.png),
[Qwen connection](readme/07-coding-clis-qwen.png), and [Review](readme/04-review.png).

## Short community post

**Title:** 做了一个本地任务工作台：收到消息后，让 Qwen Code 接着做

我在做 Taskuary，想减少“读消息、抄成任务、交给智能体、再找回结果”这几步之间的来回切换。

它把邮件、工单和报表放到同一条时间线，需要处理的内容变成任务，再交给编程 CLI 或通用
智能体。你可以看执行过程、补充说明、继续会话，最后在 Review 中审核回复。

这次加入了 Qwen Code 和中文 README。应用在本机运行，模型可以选择自己的云端服务或本地
端点。界面目前主要是英文，欢迎反馈中文使用中的具体问题，也想了解大家最需要哪些消息源。

项目：https://github.com/ldbumble/taskuary

演示：https://taskuary.com/demo/ （虚构数据，不会连接账号或执行真实任务）

## Keep the translation current

Update `README.zh-CN.md` when the English README changes installation instructions, supported
CLIs, screenshots, privacy behavior, or version. Keep the same image assets to avoid divergent
walkthroughs. Link detailed English docs explicitly until translations exist, and use the normal
issue tracker for Chinese feedback without promising a response time that cannot be maintained.
