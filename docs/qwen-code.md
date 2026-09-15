# Qwen Code with Taskuary

[简体中文入门](../README.zh-CN.md#使用-qwen-code) · [Product guide](product-guide.md)

Qwen Code is a coding CLI option in **Connections → AI CLI agents**. Taskuary can install it,
open its setup terminal, run tasks, display progress, and resume its conversations. General
agents with tools can use Qwen's native ACP transport; watched coding sessions use its terminal.

## Install and connect

1. Open **Connections → AI CLI agents → Qwen Code → Install**. Taskuary offers Qwen's official
   standalone installer on Windows, macOS, and Linux; it includes the runtime. The npm fallback
   requires **Node.js 22 or newer**: `npm install -g @qwen-code/qwen-code@latest`.
2. Choose **Set it up** to open Qwen's own terminal. Run `/auth` and configure your model
   provider. For Alibaba ModelStudio, choose the plan and region belonging to your account.
   A Coding Plan key and a standard DashScope API key use different endpoints. Follow the
   [official authentication guide](https://qwenlm.github.io/qwen-code-docs/en/users/configuration/auth/).
3. Save the connection and use **Test**. Leave Taskuary's model override blank to use the model
   configured in Qwen, or enter a model ID supported by that provider. Use Qwen's `/model`
   command to see your configured choices.
4. Choose the Qwen worker on a coding task. Installed Qwen copies also get a worker when
   Taskuary discovers them. Try a small task in a test repository, inspect its changes, stop
   the session, and use **Continue** to confirm it resumes the same conversation.

If your installed Taskuary release does not yet list Qwen, use the current source checkout:

```bash
git clone https://github.com/ldbumble/taskuary
cd taskuary
pip install -e .
taskuary
```

For triage and drafts, choose either a configured Ollama connection or the Qwen worker in
**Settings → Triage brain**. Qwen triage runs with customizations disabled and a zero tool-call
budget. Its report-reader mode uses the same conservative restriction: supply report data
through Taskuary's source connections instead of expecting that mode to fetch data with tools.

## Local app versus local model

Qwen Code runs on your machine; its selected model may run elsewhere. An Alibaba Cloud provider
receives prompts over the network. To keep model inference local, configure Qwen with a locally
hosted model endpoint, such as Ollama or vLLM, following Qwen's
[custom-provider configuration](https://qwenlm.github.io/qwen-code-docs/en/users/configuration/auth/).
Model capability and tool support depend on the model you deploy.

A setup using local Taskuary, local triage, and Qwen with your chosen provider does not require
Claude Code, Codex, or Gemini. It does not establish that every dependency or connected workplace
service is reachable from every network. Qwen's chat integrations do not become Taskuary
connectors merely by installing the CLI.

## Compatibility evidence

Checked on Windows with **Qwen Code 0.23.4 and Node 22**, using the real npm CLI and an isolated,
local OpenAI-compatible mock endpoint. The mock generates fixed responses and tool requests;
it does not test a model's reasoning quality or a hosted account.

| Path | Verified behavior |
|---|---|
| Headless task | Reads the prompt on stdin; `stream-json` returns a final answer and session ID |
| Progress | Tool events appear in Taskuary's trace; an allowed file write completes |
| Resume | A subsequent run uses the same session ID and includes the preceding conversation |
| Triage | A model-requested write is refused by the zero tool-call budget |
| ACP | Initialization, session creation, and a prompt complete through Taskuary's ACP client |

The automated tests also cover install detection, connection defaults, setup, interactive prompt
arguments, assigned session IDs, and routing between restricted triage and capable general agents.
The installer scripts were inspected; a fresh standalone installation, a live paid provider,
and mainland-China network access have not been tested in this check.

Sources: [Qwen Code repository](https://github.com/QwenLM/qwen-code),
[headless mode](https://qwenlm.github.io/qwen-code-docs/en/users/features/headless/).
