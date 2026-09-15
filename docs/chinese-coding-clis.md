# Chinese-model coding CLIs

Taskuary includes **Qwen Code**, **OpenCode (DeepSeek, GLM, MiniMax)**, and
**Kimi Code (Moonshot AI)** under **Connections → AI CLI agents**. Update and restart
Taskuary if those entries are missing.

These are coding tools running on your machine. A cloud model still receives the
context sent to it. Provider accounts, pricing, and regional availability are separate
from Taskuary; this integration does not establish mainland-China availability.

## DeepSeek through OpenCode

DeepSeek's [official integration guide](https://github.com/deepseek-ai/awesome-deepseek-agent/blob/main/docs/opencode.md)
recommends OpenCode as one way to use its models. Taskuary runs **OpenCode**, not an
official standalone "DeepSeek CLI."

1. Open **Connections → AI CLI agents → OpenCode (DeepSeek, GLM, MiniMax)** and click **Install**.
   Windows uses `npm install -g opencode-ai`, so Node/npm must be installed.
   macOS and Linux also have a standalone installer.
2. Click **Set it up**. In OpenCode, type `/connect`, choose **DeepSeek**, and enter
   your DeepSeek API key directly in the CLI.
3. Use `/models` to select an available DeepSeek model.
4. Save the connection, click **Test**, then choose its coding worker for a task.
   Leave Taskuary's model field blank to use OpenCode's selection, or enter an
   exact `provider/model` identifier from `opencode models`.

The same OpenCode connection can use **Z.AI's GLM** or **MiniMax**: select the
appropriate provider with `/connect`, then choose its model with `/models`.
Regional and coding-plan providers may use different credentials or endpoints;
follow [OpenCode's provider instructions](https://opencode.ai/docs/providers/).

## Kimi Code

1. Open **Connections → AI CLI agents → Kimi Code (Moonshot AI)** and click **Install**.
   Taskuary prefers Moonshot's standalone installer. The npm alternative is
   `npm install -g @moonshot-ai/kimi-code` and requires Node 22.19 or newer.
   **Windows also requires Git Bash.**
2. Click **Set it up**, run `/login`, and complete Kimi or Moonshot authentication.
3. Save and **Test**, then assign the Kimi coding worker to a task. Leave the model
   blank to use Kimi's configured default, or enter a configured model alias.

This preset targets the current [MoonshotAI/kimi-code](https://github.com/MoonshotAI/kimi-code)
project. Upgrade old Python `kimi-cli` installations before using it; the command-line
flags differ. See the [current command reference](https://moonshotai.github.io/kimi-code/en/reference/kimi-command).

## Qwen Code

Use the [Qwen Code setup guide](qwen-code.md) for installation, provider selection,
local-model configuration, and native ACP support.

## Roles and sessions

Taskuary's model picker includes provider-specific suggestions. Qwen reads model IDs
for the active protocol from `QWEN_HOME/settings.json` (normally `~/.qwen/settings.json`);
its OAuth choice is `coder-model`. Kimi reads aliases from
`KIMI_CODE_HOME/config.toml` (normally `~/.kimi-code/config.toml`), with its documented
`/login` aliases as the fallback. Those files are re-read when the picker loads.
OpenCode suggestions use exact `provider/model` IDs from its provider catalog;
connect the corresponding provider before selecting one. A blank model still keeps
the CLI's own default. Model choices never change your credentials or sign-in method.

Identifier references: [Qwen model providers](https://qwenlm.github.io/qwen-code-docs/en/users/configuration/model-providers/),
[Kimi model aliases](https://moonshotai.github.io/kimi-code/en/configuration/config-files#models),
and [OpenCode models](https://opencode.ai/docs/cli/#models).

- **OpenCode and Kimi:** coding tasks and general-agent tasks with tools enabled.
  Taskuary refuses to use these presets for message triage or read-only reports,
  because a per-run restriction on their inherited tools has not been verified.
  Use Qwen Code, Ollama, or an API provider for those roles.
- Headless runs stream readable text and tool activity, save the CLI session ID,
  and resume the same conversation. Interactive coding tasks open the real CLI.
  Automatic discovery of a new interactive pane's session ID is not implemented for
  these two CLIs; use the CLI's own session picker to reopen such conversations.
- Both vendors offer ACP, but these two Taskuary presets currently use their native
  command-line interfaces. Their ACP model selection and session behavior are not
  yet part of Taskuary's verified integration.
- Kimi takes headless prompts as an argument, so the operating system's command-line
  length limit applies. OpenCode reads headless prompts from stdin.

## Compatibility evidence

Verified on Windows on 2026-09-15 using **OpenCode 1.18.31** and **Kimi Code 0.43.1**,
with isolated CLI homes and a local mock model endpoint:

- Prompt delivery and readable output through Taskuary's actual runner.
- Session IDs and resumed requests containing the previous conversation.
- A real file write requested by the mock model, plus structured tool progress.
- Focused regression tests for connection adoption, installers, updates, interactive
  arguments, model forwarding, output parsing, and restricted-role rejection.

No paid DeepSeek, GLM, MiniMax, or Kimi service was called. Real-provider authentication,
billing, model quality, and mainland-China connectivity still need user-side verification.
