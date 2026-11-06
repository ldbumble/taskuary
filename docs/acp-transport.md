# ACP everywhere a CLI runs; argv as the fallback

*Design 2026-09-15 (one slice: the general agent's tool runs on native-ACP CLIs). Step 1 of 3, 2026-11-06: every
headless CLI run of the general agent, Claude Code and Codex included, through their adapters. Implemented in
`taskuary/acp.py`, `taskuary/acpgate.py` and `agents.run_acp`; Qwen compatibility is recorded in
[Qwen Code setup](qwen-code.md#compatibility-evidence). Step 2, the same day: coding sessions on claude and codex
(`taskuary/acpcoding.py`).*

Taskuary drives every AI CLI by writing argv and reading stdout. `clis.py` is that dialect,
hand-maintained: claude takes `-p`, codex takes `exec`, devin spells its approval bypass as a
`--permission-mode`, muse emits a JSON event schema nothing here parses. The session story is worse
than the launch story — gemini and cursor "keep their sessions in files and hand out no id", so
`sessionfiles.SOURCES` hashes a project root and reads `~/.gemini/tmp/<sha256>/chats` to learn what
conversation we just had.

The [Agent Client Protocol](https://agentclientprotocol.com) is the same idea LSP had: agents
implement one protocol, clients speak it, and the N×M integrations collapse. JSON-RPC over the
subprocess's stdin/stdout, newline-delimited.

The owner's reasons for moving every CLI onto it (2026-11-06):

- **control**: every tool call and every permission is a typed request we can see, and refuse. On the
  argv road a headless run carries the CLI's bypass flag, and the only fences are the ones the CLI enforces
  for us; Codex has none that can refuse a call at all.
- **one shape** for general and coding agents.
- **remote chat** (WhatsApp, Slack, Teams): a typed stream of steps and questions is what a chat can carry.

## The three steps

| Step | What | State |
|---|---|---|
| 1 | Every headless CLI run of the general agent over ACP: claude and codex through their adapters, Taskuary's own rules answering every permission, the same steps on screen | **built** |
| 2 | Coding sessions on claude and codex over ACP, drawn as the one coding chat; the pty as the fallback | **built** — see below |
| 3 | What the rules hold put to the owner as buttons, in the chat and on a bound channel (`permissions.py`) | **built** |

API brains stay direct: an API connector is already a typed stream.

## Where it applies

| | Transport | Why |
|---|---|---|
| General agent, CLI run with hands (`make_cli_llm` with `cli_tools` or a `cwd`) | **ACP**, argv as the fallback | every tool call typed, answered by our rules; the session id returned, not scraped |
| General agent, plain chat on an API connector | API, unchanged | "dramatically quicker than launching a coding CLI" |
| Coding sessions on claude and codex | **ACP** (`acpcoding.py`), the pty as the fallback | step 2: one chat, every call typed and answered by our rules |
| Any other coding CLI, and a stranger's coding task | native CLI in a pty | not checked over ACP / argv's floor |
| Triage, the drafter, quick look-ups (`no_hands`) | argv, unchanged | one classification with every tool off; there is nothing to permit |
| A stranger's task (`origin.launch_mode`: `auto`, `look`) | argv, unchanged | its floor is built from argv: the CLI's own reviewer mode, `--strict-mcp-config`, a trimmed environment |

The switch is **Settings → Agent permissions → Run CLI agents over ACP** (`acp_cli`, on by default). Off, every
run takes argv as before.

**The fallback.** A run whose agent does not get as far as a session — the adapter will not start, it fails
`initialize`, or `session/new` errors for any reason but a sign-in — raises `ACPStartError`; nothing of the turn
ran, so `run_cli` takes the argv road for that run. The log says so **once per CLI** per process, and the run's
launch line says so on every run. A sign-in error is said as a sign-in, as on argv, and never falls back (argv
would fail the same way). An error *mid-turn* never falls back either: the turn may have done part of its work.

## Which CLIs, and how each starts

| CLI | ACP | How it starts |
|---|---|---|
| gemini | native | `gemini --acp` |
| qwen | native | `qwen --acp` |
| cursor | native | `cursor-agent acp` |
| copilot | native | `copilot --acp` |
| devin | native | `devin acp` |
| claude | **adapter** | `@agentclientprotocol/claude-agent-acp@0.101.0` driving the owner's `claude` binary |
| codex | **adapter** | `@agentclientprotocol/codex-acp@2.5.0` driving the owner's `codex` binary |
| muse, opencode, kimi | argv only | — |

The adapters live in `clis.ADAPTERS`, not in `clis.KNOWN`'s rows, so a pinned version never lands in a saved
connection. Each row names the package (**pinned**: an adapter is a protocol translator, and a new release is a new
set of update shapes to check), the binary on PATH a global install provides, the environment variable that points
it at the owner's own CLI, and the session mode that makes it ask.

**The @zed-industries packages are renamed.** `@zed-industries/claude-code-acp` (0.16.2) and
`@zed-industries/codex-acp` (0.16.0) are both marked deprecated on npm in favour of the `@agentclientprotocol`
ones, and the old claude adapter (Agent SDK 0.2.44) failed `session/new` with "Internal error" against Claude
Code 2.1.318. The old codex adapter still started.

**Starting.** With the adapter installed globally (`npm i -g @agentclientprotocol/claude-agent-acp
@agentclientprotocol/codex-acp`) its own command is used; otherwise `npx -y <pkg>@<version>`. Measured on the owner's
Windows machine, three warm starts each, to a session ready for a prompt:

| | npx (cached) | the package run by node directly |
|---|---|---|
| claude-agent-acp | 5.0–6.0 s (median 5.3) | 2.7–3.3 s (median 3.2) |
| codex-acp | 2.9–4.5 s (median 3.4) | 1.0–1.1 s (median 1.1) |

npx costs about 2.3 s per start. A first-ever start also downloads the package (14.5 s for claude's). A kept
conversation pays the start once (below), and `warm_cli` pays it before the first turn.

**Signing in: nothing new.** The claude adapter runs the Claude Agent SDK, which runs the CLI named by
`CLAUDE_CODE_EXECUTABLE` — set to the owner's resolved `claude` — with its own login, settings and hooks (the SDK
loads `user`, `project` and `local` setting sources). The codex adapter starts `codex app-server` from `CODEX_PATH`,
set to the owner's `codex`, which reads `~/.codex/auth.json`. Both answered with the owner's existing subscription
sign-in (`_auth/status_update` names the plan) and advertise API-key methods only as alternatives. Neither needed an
API key. Node: the claude adapter declares `node >= 22`; it ran on the machine's Node 20.10.

## What each adapter supports

| | claude-agent-acp 0.101.0 | codex-acp 2.5.0 |
|---|---|---|
| model | config option `model` (category `model`): `opus`, `sonnet`, `haiku`, `fable`, `default` and full ids | config option `model`: `gpt-6.1-sol`, `gpt-6-astra`, … |
| effort | config option `effort` (category `thought_level`): low … max | config option `reasoning_effort` (`thought_level`): low … ultra |
| mode | `default`, `acceptEdits`, `plan`, `auto`, `bypassPermissions` | `read-only`, `workspace-write`, `agent`, `agent-full-access` |
| resume | `session/resume` (no replay) and `session/load` | `session/resume` and `session/load` |
| other | fork, list, close, delete; `_meta.claudeCode.options` takes Agent SDK options | fork, list, close, delete; `CODEX_CONFIG` takes session config |

Model and effort are set with `session/set_config_option`, found by **category**, so either spelling works. A model
the agent does not list is said on the run ("offers no model 'x' over ACP — it runs on opus") and never sent to fail
the session. A native CLI keeps its `--model` flag.

Resume prefers `session/resume`, which continues the conversation without replaying it. `session/load` replays the
whole thread as `session/update`s first, so its updates are muted; traced, they read as this turn's work. The ids are
the CLI's own (Claude session ids, Codex thread ids), so a conversation started on argv resumes over ACP and back.

**The mode is what makes it ask.** Claude's `default` asks for every tool the owner's own settings do not already
allow; measured, Read, Glob, Grep, Bash, PowerShell, Edit, WebFetch and WebSearch each asked. Codex's
`workspace-write` runs commands in Codex's sandbox without asking, and blocks and then asks for whatever needs the
network or a folder outside the workspace; `agent-full-access` would ask for nothing. A folder named by its 8.3 short
name made Codex's Windows sandbox deny even `Get-ChildItem`, so the folder is passed by its long name.

## What the argv carried, over ACP

`make_cli_llm` builds Taskuary's tools and the owner's send filter into argv. The adapters take them another way
(`agents.claude_acp_options`, `agents.codex_acp_config`):

| argv | claude adapter | codex adapter |
|---|---|---|
| Taskuary's MCP server | `--mcp-config <file>` passed through as Claude's own flag (SDK `extraArgs`), so the CLI expands `${TASKUARY_TOKEN}` from its environment — no token written (verified: listed by the adapter's `/mcp`) | `-c mcp_servers.taskuary.*` as the same dotted keys in `CODEX_CONFIG`; headers still named by env var (verified: a server given this way is listed by codex-acp's `/mcp`) |
| the owner's send tools left out | `--disallowedTools` → `disallowedTools` | `-c mcp_servers.<s>.disabled_tools=[…]` → `CODEX_CONFIG` |
| the agent's instructions | `--append-system-prompt-file` → `systemPrompt: {preset: claude_code, append}` | in the prompt, as on argv |
| the browser hold | `--settings` → `settings` | — |
| bypass, print mode, output format, model, resume | the protocol's own: dropped | the protocol's own: dropped |

## Permissions: Taskuary's rules answer

`session/request_permission` goes to `acpgate.answerer`, on the pump thread (an unanswered request is a hang):

- **Taskuary's own tools** (the `taskuary` MCP server) are allowed: none of them sends; a propose tool lights a button.
- **Any other MCP tool** runs only when the send filter judged it not to send (`sendfilter.verdicts`, the verdicts that
  build `--disallowedTools` and `disabled_tools`). One it has not judged, or a server it does not know, is refused:
  fail closed, as the send filter is.
- **A shell step that goes out or deletes outside the agent's folder** is held through `shellgate.check`, onto the task
  as a proposal for the owner's Approve. So is an HTTP client that **writes** to a host off this machine
  (`curl -X POST`, `-d`, `-F`, `Invoke-RestMethod -Method Post`…), refused, by each tool's grammar. Taskuary's own API
  on localhost is the guard's to answer.
- **Everything else** — reads, edits in its folder, searches, a page fetched — is allowed, as the bypass allowed it.
- The answer is always **allow once**, never "allow always": "don't ask again for commands that start with git" would
  stop the next call reaching us. A rule that raises refuses.

Each answer is a `permission` event in the run trace (`{tool_call_id, answer, why}`) and a log line. The step a held
call ends as reads **held for the owner**, not "failed": the tracer shows Taskuary's words for a call it did not
allow, not the adapter's "the user refused". What the rules hold goes to the owner's buttons (step 3, `permissions.ask`) with
Developer mode on; with it off, the Approve card.

## What the owner sees

`agents.ACPSteps` turns `session/update` into the trace events the argv road emits (`tool_call`, `tool_result`,
`progress` text and thinking, `live`), so `website/src/agentSteps.js` draws the same steps whichever road a run took.
`tests/test_agent_steps_backends.py` records one invented turn as each backend speaks it — claude's stream-json,
codex's JSONL, opencode, gemini over ACP, and **both adapters in their measured shapes** — and
`website/test/agentSteps.test.mjs` asserts all six render to the same plain steps.

An update is not a step:

- **Claude's adapter announces a call with no input** and a generic title ("Read File", "Terminal"), then streams the
  input key by key in `tool_call_update`s. Traced at once that read "Read a file" with no file, then the same call
  again. A call is held until its input **settles** — a permission asked for it, a status that says it runs or ran, or
  the next thing the agent does — and traced once, by the tool's own name (`Read`, `Bash`, `mcp__taskuary__my_task`)
  with its whole input, exactly as stream-json names it.
- **Codex's adapter** announces a command running with its input and streams its output as terminal deltas (collected
  as the step's result); announces a web search with an empty query and fills it at the end (`openPage` is a page
  read, `search` a web search); and asks for a file read with its own kind and the command wrapped in a shell. The ask
  only fills gaps.
- Words and thoughts arrive a token at a time and are traced as whole paragraphs. **The answer is what it said after
  its last tool call**, as claude's `result` and codex's last message are on argv; its earlier words are steps.
- At the end of the turn every open call ends — done at a normal end, not done at any other — so no step spins.
- Every ACP kind reads in plain words (`tests/fixtures/agent_steps/kinds_acp.json`): read "Read store.py", edit "Edited
  budget.py", delete "Deleted notes.txt", move "Moved README.md to docs/", search "Searched files for 'approvedTotal'"
  or "Searched the web for '…'", execute by its command ("Ran git status"), think by its title, fetch "Read
  docs.northwind.example/budget/review" (never the query string), other "Used <its title>". A shell `rm`, `mv`,
  `Rename-Item` or `Add-Content` now reads as what it did on every road. Claude's `ToolSearch` — loading a tool it has
  not loaded yet — is plumbing, not a step.

## A kept conversation

A general agent's task and the Assistant keep their conversation open between turns (`keep_alive`); on argv that is
one claude process in `clipool`. Over ACP it is one connection: `acp.Conversation` in the same pool, so the idle clock,
`MAX_LIVE`, New chat (`clipool.close`) and shutdown close it like a process. A different launch (command, folder,
environment's names, options, mode) or another conversation's id opens a new one; a turn that fails part-way drops it
and is never sent again on it. `warm_cli` opens it before the first turn.

## Live check, 2026-11-06

One general-agent turn through each adapter on the real road (`make_cli_llm` → `run_cli` → `run_acp`), in a temp
`TASKUARY_HOME`, asked "List the files in this folder and say how many there are" over three files:

| | session ready | first token | done | steps |
|---|---|---|---|---|
| claude (warm) | 3.6 s | 8.0 s | 8.7 s | Glob `*` (permission: allowed) → "There are 3 files" |
| claude (first start) | 21.2 s | 25.9 s | 26.6 s | the same |
| codex | 3.5 s | 8.3 s | 18.3 s | one PowerShell `Get-ChildItem`, sandboxed, no ask → "There are 3 files" |

## Step 2: coding sessions over ACP

*Built 2026-11-06 (`taskuary/acpcoding.py`).* With the switch on, a coding task on **claude or codex** opens as one ACP connection
in the task's checkout instead of the CLI's TUI in a pty. `terminal.open_session` decides (`acpcoding.wanted`: a task's session, the
owner's own - `origin.launch_mode` `full` - the switch on, a CLI with an adapter) and everything it already builds is the launch:

- **the argv, carried over**: the pane's flags after the binary - Taskuary's MCP server, `--disallowedTools`, the theme/hooks
  `--settings` file for claude; the `-c` keys for codex - go through `agents.acp_launch` exactly as a general run's do. The model and
  effort the router chose (`brainroute.for_session`) are session options (`_acp_gears`), so `--model`/`--effort`/`-m` are dropped.
- **the seed** `seed_text` built for the pane - the ask, the mail, the repo, the coding profile's rules - is the first `session/prompt`,
  recorded as a `user_message_chunk` with `_meta.taskuary = 'brief'`. A quiet resume sends nothing: the agent is back at its prompt.
- **resume** is the agent's own conversation by its own id (`session/resume`, else `session/load`), so a conversation a pty held
  continues over ACP, and back. Each session keeps its own updates, so a resumed one never stands in for the turns before it.
- **the start is not the request's**: `open_session` returns at once and the connection opens on the session's own thread.

**What the owner sees.** Every `session/update` goes to `codingchat.record_update` (stamped `_at` as it arrives), and the coding chat
draws it with the log road's own rows (`codingChat.stepsFromAcp`): words, the work folded into "N steps", each edit its own
"Edited ledger.py (+1 −0)" row opening on its numbered diff, the plan as one checklist (the turn's newest). The box sends a prompt; one
written while a turn runs waits and goes in, with anything else that waited, as **one** prompt when the turn ends - the waiting room's
notes too, drawn as the owner's own lines with Taskuary's framing as its brief. **Stop** (a ✕ while a turn runs,
`POST /api/tasks/<id>/agent/cancel`) is `session/cancel`: the turn ends, the session stays. A permission is acpgate's: the rules
answer first, what they hold is the owner's Allow/Reject card in the chat and on a bound channel (`permissions.ask`).

**The Terminal toggle** shows the session's commands and their output: `$ git status`, then what it printed - streamed for Codex
(`_meta.terminal_output_delta`), the call's own result for Claude (its fenced block unwrapped) - with the agent's words between them.
`codingchat.live_of` says `terminal: false` until a command has printed, and the toggle is not offered: never a blank pane. Typing
into it and Enter is a prompt; ^C is Stop.

**One registry entry, the pty's shape.** `ACPCoding` sits in `terminal.SESSIONS` with a `Term`'s fields and methods, so what reads a
coding session reads it unchanged:

| Reader | What it reads | Over ACP |
|---|---|---|
| Board, Wall, task page (`terminal.listing`, `for_task`, `info`) | sid, cli, phase, waiting, files, the witness's card | `transport: 'acp'`; phase is the turn (working while one runs); its card from the calls (tool, files, plan, last words) |
| blackboard, peers, `briefing`, `note_peers` | `t.files()`, `t.cwd`, `t.argv` | git's dirty files plus every file an edit's diff named; and `touching` - `path:line` from the calls' locations, said to peers |
| waiting room, relays, devphone `tell_agent`, agent channels | `waitroom.state`, `term.tell`/`type_into` | a prompt, never keys; delivered the moment the turn ends (`waitroom.later`) |
| workerstate, hand raise | worker events, `screen_asking` | the turn's start and end written as a hook would (`hooks._events` UserPromptSubmit/Stop - Codex's hooks do not run over ACP; Claude's, when they reach the session, are not doubled); no screen, so no chooser |
| questions on the card (`answer_form`), `screen`, `asking_lines` | the TUI's screen | the answers are its next prompt; the "screen" is its last words |
| wrap-up (`harvest`, `transcript_for`), `keep` | the rendered scrollback | its turns themselves (`transcript_text`) |
| hooks (`hooks.receive`) | argv[0] names the CLI; `ext_id` | argv is the pane's; `ext_id` is the ACP session id - Claude's own session id, Codex's thread id |
| landing, proof, selfclose | `cwd`, `started_ts`, `n` | the same fields |

`terminal.is_acp(t)` is the one test, and it is `is True`: a test's `Mock` answers every attribute.

**The fallback.** An adapter that does not get as far as a session - it does not start, fails `initialize`, or `session/new` fails,
a sign-in included (the pty is where the owner signs in) - takes the session out of the registry and opens today's pty with the same
seed (`open_session(..., pty=True)`), said once in the log per CLI and on the task. A turn that fails part-way is said and not retried.

**Still in a pty**: a stranger's task (its floor is argv's), the switch off, a native-ACP CLI (gemini, qwen, cursor, copilot, devin -
their coding road over ACP is not checked yet), argv-only CLIs (muse, opencode, kimi), a plain shell, the CLI install and sign-in
terminals, and any coding session whose adapter did not start.

### A stranger's task never runs over ACP

A task someone not on the trusted list wrote (a public PR or issue, a mail from outside) keeps exactly the floor it had, on both roads:

| Road | A stranger's task | Where it is enforced |
|---|---|---|
| Coding session | a pty in the CLI's own reviewer mode (`origin.launch_mode` → `auto`: claude's `--permission-mode auto`, `--strict-mcp-config`, its session settings file with the floor's hooks, `--add-dir` its own folder), a trimmed environment (`Term` mode `auto` → `STRICT_ENV`), a task-bound token, no Taskuary toolbox; a CLI with no reviewer (codex) is refused | `acpcoding.wanted` takes only `mode == 'full'` **and** refuses any task `origin.of_task` reads as a stranger's, whatever mode it is handed |
| General agent, with hands | argv in the reviewer mode, `strict_env`, its own folder outside Taskuary's home | `llm.make_cli_llm` sets `acp_ok` False for `auto` and `look`; `agents._acp_road` also refuses any profile with `strict_env` |
| General agent, a look (research) | argv with no tools, `strict_env` | as above |
| The classifier, the drafter, a read-only look on a CLI with no reviewer (`origin.looks_only`) | argv with every tool off | `no_hands` sets `acp_ok` False, whatever a saved profile says |

A task that becomes a stranger's after its session started keeps today's rule on both transports: the waiting room types nothing into
a session started `full` (`waitroom.full_on_stranger`), and peers' notes wait the same way. Pinned by `tests/test_acp_coding.py`.

### Live check, 2026-11-06

`terminal.open_session` on the real road, a temp `TASKUARY_HOME` (its hooks pointed at a port nothing listens on), a temp git repo with
one file, the task "add a one-line comment to the top of the file ledger.py", the adapters through `npx` (not installed globally):

| | session ready | first words | done | calls | updates | asks (all allowed by the rules) |
|---|---|---|---|---|---|---|
| claude | 6.0 s | 47.9 s | 50.1 s | 5: read the context, Edit, Read, check + commit, clean up + `taskuary --done` | 85 | 4 (Bash ×3, Edit) |
| codex | 7.4 s | 12.1 s | 120.1 s | 17, its sandboxed tries and their escalated reruns among them | 293 | 5 (`git add`, `git commit`, and `taskuary` reaching the network) |

Each made the edit and committed it; the chat drew it as `Edited ledger.py (+1 −0)` with the one added line over the file's first
lines. The Board row read `transport: acp`, `phase: parked`, "claude is waiting on you", with `ledger.py` as its file. `taskuary
--done` failed in both, as it should with no server behind the temp home. The first check found one bug: a checkout named by its 8.3
short name left the paths absolute on the card - fixed (the folder by its long name).

### Not built in step 2

- **Mid-turn input**: both adapters advertise `_meta.steering` (and claude `promptQueueing`); words still wait for the turn's end.
- **The plan** was not exercised live - neither CLI wrote one for a one-line edit; the checklist is pinned by the unit test.
- **`fs` and `terminal` client capabilities**: not advertised; the agent keeps its own hands and shell.
- **Native-ACP CLIs for coding** (gemini `--acp` and the rest): their general road works; the coding road is claude and codex.
- **Idle**: a coding session holds its adapter and CLI until it is closed, as a pty does - no idle reaping.

## Risks

- **Adapter releases change update shapes.** Pinned for that reason; a bump re-records the two fixtures from a live run.
- **Copilot's ACP is public preview** since January.
- **Hooks**: Claude's still run (the SDK loads user settings). Codex's `--dangerously-bypass-hook-trust` has no
  `CODEX_CONFIG` spelling, so Codex hooks the owner never approved stay skipped on this road, as they were before
  that flag.
- **A protocol error is a new failure mode** — answered by the fallback at start, and by failing loudly mid-turn.

## Deliberately not built

- coding sessions over ACP on a native-ACP CLI (gemini, qwen, cursor, copilot, devin)
- the `fs` and `terminal` client capabilities
- a stranger's task over ACP: its floor is argv's
