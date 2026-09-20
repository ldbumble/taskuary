# ACP: one protocol where nobody is watching the terminal

*Design, 2026-09-15. Implemented in `taskuary/acp.py`; Qwen compatibility is recorded in
[Qwen Code setup](qwen-code.md#compatibility-evidence).*

Taskuary drives every AI CLI by writing argv and reading stdout. `clis.py` is that dialect,
hand-maintained: claude takes `-p`, codex takes `exec`, devin spells its approval bypass as a
`--permission-mode`, muse emits a JSON event schema nothing here parses. The session story is worse
than the launch story — gemini and cursor "keep their sessions in files and hand out no id", so
`sessionfiles.SOURCES` hashes a project root and reads `~/.gemini/tmp/<sha256>/chats` to learn what
conversation we just had. Every CLI added is another row of that table and another way to find out
what it called the thing it just did.

The [Agent Client Protocol](https://agentclientprotocol.com) is the same idea LSP had: agents
implement one protocol, clients speak it, and the N×M integrations collapse. JSON-RPC over the
subprocess's stdin/stdout, newline-delimited.

This document designs adopting it for **one slice**, and says clearly which slices it is not for.

## Where it applies, and where it does not

The line is **whether a person is watching the terminal**.

| | Transport | Why |
|---|---|---|
| General agent, CLI run for its tools (`make_cli_llm` with `cli_tools` or a `cwd` — the runs with hands, in scratch) | **ACP** | nobody watches; we want the session id, cancel, and progress in our own UI |
| General agent, plain chat | API connector, unchanged | `general.py` already prefers it — "dramatically quicker than launching a coding CLI" |
| Coding sessions | native CLI and pty, unchanged | a developer wants the real CLI, not a protocol's rendering of it |
| Triage | unchanged | one classification, no tools, deliberately `no_hands`, on the light gear |
| Replying | unchanged | it *is* triage — `responder.draft_reply` calls `build_llm(store)` with no pick |
| Assistant brain | unchanged | a per-item decision on the light gear; there is no session to track |

The Assistant is worth a sentence because it keeps coming up. It does not need ACP as its brain.
It is, however, already the human-in-the-loop channel for agent questions, and today that channel
is guesswork: `handraise._line()` reads the last six *rendered terminal lines* and
`waitroom.looks_like_question()` decides whether that was a question, while `say_to_task` types the
answer back "in seed()-sized bites… then Enter until it lands." ACP replaces both halves with a
typed request and a response. That is a benefit on the **agent** side; the Assistant itself does
not change.

## Which CLIs

Only the ones that speak ACP natively, verified against each vendor's own documentation:

| CLI | ACP | How |
|---|---|---|
| gemini | native | `gemini --acp` |
| qwen | native | `qwen --acp`; Qwen Code 0.23.4 verified with a local mock model endpoint |
| cursor | native | `cursor-agent acp` |
| copilot | native | `copilot --acp` (stdio default; public preview since 2026-01-28) |
| claude | adapter only | `@agentclientprotocol/claude-agent-acp` |
| codex | adapter only | `codex-acp` |
| devin | native | `devin acp` (arrived after this survey; verified with `acp.ACPClient` 2026-09-20: session ids like `relieved-radiator`, `loadSession` true) |
| muse | none | — |

OpenCode (`opencode acp`) and Kimi Code (`kimi acp`) also offer native ACP, but
Taskuary's presets currently use their headless CLI interfaces. Model selection and
session behavior over ACP have not been verified for those integrations. See
[Chinese-model coding CLIs](chinese-coding-clis.md#compatibility-evidence) for the
paths tested with real binaries.

For the four native ones, ACP is **the binary already installed, in another mode** — the Gemini
docs: "In ACP mode, Gemini CLI listens for incoming JSON-RPC requests." Same process, same login,
no new dependency and nothing new to authenticate.

The adapters are a different animal and are **out of scope**, for a reason beyond the Node
dependency: `claude-agent-acp` is a separate package that drives Claude through the Agent SDK, not
the `claude` binary, and **neither adapter documents whether it bills against a CLI subscription or
an API key**. Muse taught us that a CLI subscription does not cover the API. Treat adapter billing
as unverified until someone checks it.

Neither Anthropic nor OpenAI has published a roadmap either committing to or declining native
support. Twelve months of ecosystem practice has settled on adapters.

## How it plugs in

One branch, in one place:

```
make_cli_llm ─▶ run_cli ─┬─ no acp in the profile ─▶ today's argv + stdin road
                         └─ acp in the profile ────▶ run_acp
```

Callers learn nothing. The profile carries **the launch arguments, not a boolean**:

```python
{'name': 'gemini', 'cmd': 'gemini', 'acp': ['--acp'], ...}
{'name': 'cursor', 'cmd': 'cursor-agent', 'acp': ['acp'], ...}
```

Because an ACP agent is then just "a command we launch", adopting claude or codex later is a
profile entry pointing at the adapter — no code change. The decision is reversible the day the
billing question is answered.

## The module

`taskuary/acp.py`, modelled on `mcp.py`, which is already a 152-line stdio JSON-RPC client with no
SDK: spawn, a `_pump` thread reading NDJSON into a queue, `request()` matching by id.

One thing genuinely changes. MCP as we use it is one-way — we ask, the server answers, and the pump
can assume every inbound message is a reply:

```python
if m.get('id') == self._id: return m.get('result', {})
```

ACP is bidirectional. While a turn runs, the agent sends requests **to us**. So the pump dispatches
three kinds instead of one:

| Inbound | Shape | What we do |
|---|---|---|
| our reply | `id` + `result`/`error` | hand to the waiting caller, as today |
| notification | `method`, no `id` | `session/update` — stream it into the run trace |
| the agent asking us | `method` + `id` | **must answer, or the agent blocks forever** |

That last row is the same deadlock `clis.py` already documents — "a headless run with no permission
flag waits forever for an approval nobody can click" — one layer up. It is why the permission
capability below is not optional.

A turn is `session/new` → `session/prompt` → updates until a stop reason.

`session/update` maps onto the trace vocabulary `run_cli` already emits (`_live_line`,
`trace('live'|'tool', …)`), so the Board shows the work with no new UI.

## What we advertise

**No `fs` capability.** The agent uses its own file access, exactly as it does under `-p` today.
Declaring `fs/read_text_file` and `fs/write_text_file` would route the agent's file work through
Taskuary, which is a real feature and a different project.

**Permissions auto-approved.** `session/request_permission` is answered yes, which reproduces
today's behaviour: every headless run already carries `--dangerously-skip-permissions`, `--yolo`, or
`--permission-mode dangerous`, because in a headless run nobody can click Approve.

This is deliberate and it is the whole product decision of the first version: **the channel is
wired and answers itself.** Behaviour is identical to today, so the first version is a pure
transport swap that can be judged on whether it works rather than on whether we like the new
feature attached to it.

It also puts the interesting thing within reach. Today the choice is all-or-nothing: `no_hands`
turns every tool off for the classifier, and an agent that genuinely needs hands gets the safety off
in a scratch directory, where the *folder* is the only fence. A permission channel that already
exists makes "may use its browser, must ask before writing a file" expressible per action. Given
that the general agent reads untrusted mail for a living, that is a larger security gain than the
credential scrub. **Not in this version** — but the reason to wire the channel now.

## Session identity — the payoff

`session/new` returns a session id, and it goes onto the existing `ExtId` road that
`/continue-session` already reads.

For gemini and cursor this **deletes the file-scraping**: no hashing a project root, no reading a
vendor's temp directory, no learning after the fact what the conversation was called. Resume becomes
`session/load`, which the agent advertises in `initialize` — a capability we ask about rather than a
flag we look up by the CLI's name.

That last point generalises, and is worth taking even without ACP: `resume_argv`, `assign_argv` and
`sessionfiles.SOURCES` all branch on the CLI's **name**. Capabilities are the same correction that
`no-hardcoded-words` made for routing — ask what it can do, do not look up who it is.

## Lifecycle

**One session per run. Nothing held between runs.** An earlier draft proposed holding a connection
open per CLI to avoid per-call process spawn; that was chasing a latency problem nobody reported and
buying health checks, idle timeouts and restart-on-death in exchange. Rejected.

The care already in `run_cli` needs an ACP equivalent, not a copy:

- `_CLI_CHILDREN` registration, so shutdown does not leave an invisible agent running
- the timeout killer
- cancel — now `session/cancel` first, with the existing process kill as the backstop when the
  agent does not honour it

## Testing

`tests/fake_acp_server.py`, modelled on the 24-line `fake_mcp_server.py`: a scripted agent that
completes a handshake, emits a few `session/update` notifications, asks for one permission, and ends
the turn. This is what makes the work testable without installing three vendor CLIs, and it is
where most of the time will go.

Cases worth pinning: a session id reaches `ExtId`; updates become trace lines; an unanswered
permission request is a **test failure, not a hang** (assert we answer); cancel ends a turn; an
agent that dies mid-turn surfaces as a run failure rather than a silent empty result.

## Risks

- **copilot's ACP is public preview** since January. It may change under us.
- **cursor spells it as a subcommand** (`agent acp` in the docs) against our `cursor-agent` binary
  name — the launch shape differs from the other two, which is why the profile stores arguments
  rather than a flag.
- **A protocol error is a new failure mode.** `run_cli` has years of accumulated care around what a
  CLI does when it fails; `run_acp` starts with none of it, and the first version should fail
  loudly rather than fall back silently to the argv road, or we will never learn which is broken.

## Deliberately not built

- adapters for claude and codex (billing unverified; a profile entry when someone checks)
- the `fs` capability
- surfacing permissions or questions to the owner
- any change to triage, replying, the assistant brain, or coding sessions
- holding connections open between runs
