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

## Try the demo

You do not have to connect anything to see what Taskuary does:

```bash
taskuary --demo                    # or: docker compose --profile demo up
```

The demo is the real interface over invented work, with scripted replies where the AI would answer
and replayed sessions where coding agents would work. Nothing it offers can reach a real system:
nothing sends, no connection can be created or given a secret, no shell or CLI starts, and no tool
runs. A request that would touch something real is refused, and says so. It keeps its data in a
throwaway folder: what you change stays until you stop it, and the next start is a fresh demo.

## Command-line options

The everyday options for the Python install are:

| Option | What it does |
|---|---|
| `--demo` | Runs a throwaway demo instance: invented work, scripted replies, and nothing that can reach a real system |
| `--port PORT` | Overrides the configured server port for this run |
| `--host HOST` | Overrides the configured server host; use `0.0.0.0` to listen on all interfaces |
| `--no-browser` | Starts the server without opening a browser tab |
| `--debug` | Enables verbose console logging for requests, report runs and errors |

Run `taskuary --help` for the complete command reference.

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

The first time it opens, the Assistant asks three questions. Each one is answered by clicking a
card, and the cards are the same ones the [Connections](connections) page shows. The line at the
top always says what to do next, and so do the Work list and the **Setup** chip in the top bar.

1. **What AI do you have?** Click the one you already pay for: Claude, ChatGPT, Gemini or
   Copilot. Taskuary connects it, checks that it answers, and uses it to sort your mail. If it
   is not installed, the click installs it. If it needs you to sign in once, the card says
   **Needs sign-in** and **Set it up** opens the AI's own sign-in. **More AI** lists every other
   AI on this computer and every API provider, for when you would rather paste a key.
2. **What email do you have?** Microsoft 365 or Outlook is one sign-in, with nothing to type.
   Gmail needs an App Password, which Google makes at
   [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) once 2-Step
   Verification is on. Any other mailbox takes its address, server and password.
3. **Any other connection you'd like to set up?** While your mail is read, WhatsApp, Teams,
   Slack and Telegram are offered, and **More connections** shows the rest. This one is optional:
   press **Walk me through my tasks** when you are ready.

**Setup** on the top bar opens the same three questions again whenever you want to
change the AI or the mailbox. Setup does not overwrite an existing user's model or connection
configuration.

After that, connect a coding CLI if you want code written, or add a report for numbers you check
by hand. **Settings → How mail is sorted** lets you use different models for different jobs. Reports
and the Hub can wait until you have a workflow that needs them.

Two reports exist from the start: the **End of day checkup** and the **Advisor**, which looks for
useful follow-ups and patterns in your work. You can review or remove either in Reports. The
Morning digest is available as an optional report.

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
[Settings](settings#how-mail-is-sorted), and give that CLI a light model on its connector card so
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
- [Reports and the Advisor](reports) — before you build your first report.
- The live API reference is at `/api/docs` while Taskuary is running.
