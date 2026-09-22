Taskuary is a work assistant that runs on your own machine. It reads the places work arrives —
mail, chats, issue trackers, monitoring, your finance system — decides what each thing actually
is, and brings you the few that need you. Coding jobs go to a coding agent in your repository.
Answers come back as drafts you approve. Nothing is sent without you.

It keeps its data in a SQLite file in your home directory and serves its interface at
`http://127.0.0.1:7787`. There is no account to create and no server to rent.

## What Taskuary is

Three sentences, because the rest of this site is detail:

1. **Everything arrives in one Timeline.** A vendor's email, a GitHub pull request, a Teams
   message, a failed nightly export and this morning's spend report are one list, in the order
   they happened.
2. **Each item gets one verdict.** A small AI reads it and decides: nothing to do, a sentence
   settles it, an agent should work it, let's talk it through, or it's yours. That verdict is
   visible, and arguing with it teaches the next one.
3. **Work that can be done is done, and comes back for approval.** A coding agent works in your
   checkout; replies wait on the task. Approving is always a human action.

:::rule The one thing to understand
Taskuary never sends anything by itself. Replies, comments, invoices and posts all wait for you
on the task. The only deliberate exception is an alert you configured, which fires the moment its
rule trips — an alert that waits for approval is not an alert.
:::

## Install on Windows

Download [Taskuary.exe](https://github.com/ldbumble/taskuary/releases/latest/download/Taskuary.exe)
and open it. It is one file: the app and the desktop shell together, with no Python and no
installer.

The first run creates `%USERPROFILE%\.taskuary\` and opens the interface.

## Install with Python

Python 3.10 or newer:

```bash
pip install taskuary
taskuary
```

The browser opens by itself. For the same interface in a native desktop window:

```bash
pip install "taskuary[desktop]"
taskuary-desktop
```

:::note Which platform gets the most use
CI runs the full test matrix on Windows, Linux and macOS. Development happens mostly on Windows,
so the terminal, the desktop shell and the agent presets are best exercised there; macOS and
Linux may still have rough edges.
:::

## Docker

Runs Taskuary without putting Python on the host:

```bash
git clone https://github.com/ldbumble/taskuary
cd taskuary
docker compose up
```

Open `http://127.0.0.1:7787`. Data lives in the `taskuary-data` volume. The container gives you
the Timeline, Review, Reports and Connections; coding CLIs and the optional WhatsApp bridge stay
host programs, because both need a machine of their own.

The compose file binds to localhost. Set `TASKUARY_TOKEN` before publishing the port anywhere
else.

## Your first run

Open **Connections** and do these four things in order. The first two are the minimum that makes
Taskuary useful; the rest can wait.

**1 · Give it a brain.** Add a key for Anthropic, OpenAI, Azure OpenAI, OpenRouter or the Meta
Model API, or point it at Ollama for a local model. Triage reads a lot of short messages and
returns a one-line verdict, so the cheapest fast model is usually the right one.

**2 · Connect somewhere work arrives.** Outlook, Gmail or any IMAP mailbox, Teams, Slack,
Telegram, WhatsApp, Discord, GitHub, Jira — see [Connections](connections). Items start appearing
on the Timeline within a poll or two.

**3 · Connect a coding CLI**, if you want code written. Claude Code, Codex, Qwen Code, OpenCode,
Kimi Code, Gemini, Cursor, Copilot, Muse Code or Devin. If the CLI is not on this machine yet,
press **Install** on its card and Taskuary runs the vendor's own installer. A GitHub token lets
it discover your repositories.

**4 · Add a report**, if there are numbers you check by hand. Describe it in plain English or
build it from a database, a cloud account, a REST endpoint, an RSS feed or an MCP server, and
preview it against the live source before scheduling.

Two reports exist from the start: the **Morning digest** — one brief a day covering what slipped,
today's meetings, what happened and what is in flight — and the **Assistant**, which posts only
when it notices something between briefs. Both speak in the voice you set in `COUNSEL.md`. Delete
either to switch it off.

## Choosing the AI setup

Triage reads many messages cheaply; coding changes a repository rarely and wants a strong model.
Taskuary lets those be different brains, and the choice is mostly about what you already pay for.

| Setup | Triage, drafts, summaries | Coding sessions | Fits you if |
|---|---|---|---|
| **Two brains** (recommended) | a small cloud model on an API key | your coding CLI's full model | you have a low-cost API key |
| **One brain, two gears** | the CLI's *light* model | the same CLI's main model | you have one CLI subscription and no key |
| **One brain, one gear** | the CLI's full model | the same model | simplest, and expensive for routine mail |
| **Local brain** | Ollama or any OpenAI-compatible local server | a coding CLI, optionally the same local model | no key, and no mail leaving the machine |

With no cloud key, set the triage brain to your configured CLI in
[Settings](settings#triage-agents), and give that CLI a light model on its connector card so
routine triage does not burn the coding model.

## Where your data lives

The Python and desktop installs keep everything in `~/.taskuary/`:

| File | What it is |
|---|---|
| `taskuary.db` | the SQLite database — messages, tasks, settings, the audit log |
| `config.toml` | local configuration |
| `taskuary.log` | the application log |
| `playbooks/*.md` | one page per kind of job an agent has learned to do |
| `context/` | the context file each coding session is handed at startup |

`TASKUARY_HOME` moves all of it. Docker uses `/data` inside the container. `TASKUARY_HOST`,
`TASKUARY_PORT` and `TASKUARY_TOKEN` override server settings at runtime without being written
back to the config file.

:::warn Before you expose it beyond localhost
Set `[server].token` in the config or provide `TASKUARY_TOKEN`, and send that token in the
`X-Taskuary-Token` header. An unauthenticated Taskuary reachable from the network gives whoever
finds it your mail, your repositories and an agent that can run commands.
:::

## What leaves your machine

Taskuary calls the services you configure and nothing else. Hosted AI providers and coding CLIs
receive the prompts their work needs. With a model running on your machine, those prompts stay
on it too; connected services such as mail still use their own connections either way.

Before a prompt reaches a hosted model, a headless CLI run or the first turn of an agent pane,
Taskuary replaces recognisable credentials with labelled placeholders. The original message is
never altered. A reply that still contains one of those placeholders is refused rather than sent.
These are deterministic shape rules — they catch API keys and passwords that look like API keys
and passwords, and they cannot catch every secret.

## Updating

**Settings → Updates** shows the running build and the latest release, and installs it in place:
the exe is swapped or `pip install` runs, and the app reopens. Connections and settings are
untouched.

For the Python install you can also do it yourself:

```bash
pip install --upgrade taskuary
```

## Next

- [How it works](how-it-works) — one message from arrival to approval.
- [Connections](connections) — what Taskuary may read, and what it may do with it.
- [Reports and the Assistant](reports) — before you build your first report.
- The live API reference is at `/api/docs` while Taskuary is running.
