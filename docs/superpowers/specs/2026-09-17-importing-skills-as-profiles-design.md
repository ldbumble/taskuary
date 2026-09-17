# Importing a skill: somebody else's expertise, converted once, as a profile

2026-09-17

**Depends on** `2026-09-17-an-agent-gets-its-whole-profile-design.md`. That fixes `DOC_CHARS`, which
today delivers 1,800 characters of a profile to the session that runs as it. Importing a 7KB skill
into a document that arrives as its first quarter would produce a profile that looks configured and
is not. The fix is small and independent, and this feature is pointless without it.

## The problem

Anthropic ships eleven `knowledge-work-plugins` — sales, legal, finance, support, data — as
file-based skills: a `SKILL.md` per subject, frontmatter plus prose, no code. They encode how those
jobs are actually done, by people who do them.

They are stuck in one vendor's directory. A skill is read by Claude Code and means nothing to a
codex or gemini worker. There are already 57 on this machine that Taskuary cannot see.

Taskuary has the shape to use them. A **profile** is a worker: an `agent` row plus a `doc` row of the
same name, a one-line `purpose` that triage reads from `agents.roster()` to choose it, and a rules
document that `terminal.rules_text` puts into the session. Every CLI's worker reads that same block.

So a skill written for Claude Code, converted once, drives a codex session. That is the feature.

## Skills become profiles. Not playbooks.

This is the distinction the whole design rests on, and it is the owner's:

> A skill is **how to do things, what the logic is** — expertise. A playbook is **the actual
> workflow that writes**, and it is generated from the owner's own work, against the owner's own
> systems.

So **import produces profiles only.** Playbooks stay authored here, by `playbooks.DRAFT_SYSTEM` from
sessions that actually happened.

That is not a tidiness argument, it removes the sharpest risk in the earlier draft of this spec. A
playbook's fields are `uses / alone / ask first / done when` — every one of them about acting on a
system. A `SKILL.md` states none of them, so converting to a playbook meant a model *inventing* them,
and `playbooks.about_code` reads `uses:` to decide whether CODER.md's repository rules apply. A wrong
inference there sends a worker looking for a codebase to edit on an NDA.

A profile needs a `purpose` and a body. Both are in the file already. **Nothing is guessed.**

It also matches what is in these files. The finance plugin's `journal-entry-prep` — the one that
sounds like it writes — is *"JE preparation best practices, accrual types, documentation
requirements, review workflows"*. Methodology, not a script. It was never a playbook.

## The conversion

```
SKILL.md frontmatter + body          profile
  name          ──────────────►  the worker's name (slug)
  description   ──────────────►  purpose:  ← the ONE line agents.roster() shows triage
  body          ──────────────►  the rules document, whole
  plugin.json   ──────────────►  the suggested name and purpose when a whole plugin is imported
```

`description` is already a trigger sentence — it is how Claude Code decides whether a skill applies.
`purpose` is how triage decides whether a worker fits. Same sentence, same job, different field.

A model does the conversion, because a `description` is written for a harness and a `purpose` is
written for a roster, and the body usually needs its harness-specific preamble lifted off. But it is
converting prose the owner then reads and corrects — not inferring a fact that changes what a worker
may touch.

### What triage sees, and what the worker gets

Already separate in the code, and the separation is the point:

| | what | where | size |
|---|---|---|---|
| triage choosing a worker | `purpose`, one line | `agents.roster()` | all workers, 2000 chars total |
| the worker, once chosen | the whole rules document | `terminal.rules_text` | per worker (see the dependency) |

So an imported profile costs triage **one line**, and the body only reaches the session that was
actually assigned it. Eleven plugins is eleven lines — the roster budget is not the constraint here
that it would have been for playbooks.

## Where a skill comes from

Three doors, one conversion behind them:

1. **A path on disk** — a `SKILL.md`, or a plugin folder with a `skills/` directory.
2. **What is already installed** — the two globs, grouped by `plugin.json`:
   ```
   ~/.claude/skills/<name>/SKILL.md
   ~/.claude/plugins/cache/<marketplace>/<plugin>/<ver>/skills/<name>/SKILL.md
   ```
3. **A link** — a GitHub repository or a folder inside one, fetched read-only.

### A link is untrusted input, and it becomes a worker's rules

This is the one thing in this feature that deserves care. An imported skill ends up as instructions a
worker follows. Fetching one from the internet is ingress of text that becomes agent behaviour — the
same class of thing as mail arriving, and this install's stated posture is that egress is gated and
ingress is not.

Three things hold the line, and none of them is cleverness:

- **Nothing is written without the owner reading it.** The wizard shows the converted `purpose` and
  the body before anything is saved. A remote skill is a draft until a human says otherwise.
- **Nothing is active until it is switched on.** A profile saved with `triage_enabled: False` is
  never offered to triage; it can only be used by explicit dispatch.
- **A skill grants no capability.** It is prose in a rules block. Every system a worker can reach is
  a connector behind `scopes.py` and the proposal road, and importing text changes none of that.

What the import must NOT do is fetch anything the skill references — no following links inside the
file, no `.mcp.json`, no install step. It reads the markdown it was pointed at and stops.

### Connectors are never imported

Each plugin ships `.mcp.json`; the finance one declares Snowflake, Databricks, BigQuery, Slack, Gmail
and Calendar. **It is not read.** Taskuary's connectors are tested cards behind a guard with scoped
egress; importing MCP servers would hand a worker a second way out of the building. The import takes
the expertise and leaves the plumbing.

## The walk

A wizard, because the correcting is the point:

1. **Where from** — a path, a link, or a pick from what is installed.
2. **What is in it** — one row per skill, with its proposed name and `purpose`. A plugin proposes
   one profile per skill, and offers its `plugin.json` name as a prefix (`finance-reconciliation`).
3. **Correct it** — name, `purpose`, and the body, all editable. This is where a remote skill gets
   read before it becomes anything.
4. **Import** — writes each as `agent` row + `doc` row through the existing road
   (`ensure_profile_document`), with `triage_enabled` set from a tick box, default **off**.

### Harness skills are not domain skills

The superpowers skills on this machine run 6.5KB–32KB and instruct a worker to use tools that exist
only inside Claude Code. Imported, they would tell a codex session to call things that are not there.
The knowledge-work ones are domain knowledge and travel fine.

The importer does not try to classify this — it shows the size and says plainly that a skill written
for a specific harness will not travel. The owner reading the body in step 3 is the check.

## The lists have to survive success

Docs → Profiles and the playbook shelf were built for a handful. If this works there will be dozens.
Both get a scrolling list, and each row shows whether it is **on the triage roster** — because once
`triage_enabled` is the difference between a profile that routes work and one that sits there, that
state has to be visible where the list is, not only in an edit screen.

## Files

**Server**

- `taskuary/skillimport.py` — new. Finds skills (the globs, a path, a fetched repo), parses
  frontmatter and `plugin.json`, converts via a model, and returns proposals. Writes nothing.
- `taskuary/server.py` — `GET /api/skills/found`, `POST /api/skills/convert` (proposals, no write),
  `POST /api/skills/import` (write the confirmed ones through `agents`' existing profile road).

**Web**

- `website/src/SkillImport.jsx` — new. The wizard.
- `website/src/DocsView.jsx` — an **Import skills** entry beside Add profile; scrolling lists for
  profiles and playbooks with the on-the-roster state in each row.

Nothing in `agents.py`, `playbooks.py` or `triage.py` changes. An imported profile is an ordinary
profile, and that is the measure of whether this was done right.

## Tests

- a `SKILL.md`'s `description` becomes the profile's `purpose`, and its `name` becomes the slug
- the body lands in the profile's document whole, and `rules_text` returns it whole
- a plugin folder proposes one profile per skill, prefixed by the plugin's name
- **`.mcp.json` is never opened** — assert it, by path, in the importer's own tests
- **no playbook is ever created by an import** — assert `playbooks.list_all()` is unchanged
- imported with the box unticked → `triage_enabled: False` → absent from `agents.roster()`
- ticked → present in `roster()`, one line, its `purpose`
- importing the same skill twice does not create a second profile
- a fetched link reads only the file named; nothing inside it is followed
- `agents.roster()` stays within 2000 chars with eleven profiles imported, or says which was dropped

## Deliberately not doing

- **No playbooks.** Stated above and the load-bearing decision: a playbook is the owner's own
  workflow against the owner's own systems, drafted from work that happened.
- **No `commands/`.** A command is a thing invoked by name, which an attached playbook already is.
- **No MCP, no install step, no following links inside a skill.**
- **No live link.** Converted once and owned here. A `claude plugin update` does not silently change
  a document that has been running the business.
- **No auto-enable.** Nothing reaches triage's roster without a tick.

## The honest risk

The dangerous inference is gone — nothing about system access is guessed. What remains is quality: a
converted `purpose` that is vague will make triage choose that worker for the wrong work, and the
only thing standing between that and the roster is the owner reading one line in step 3. That is a
fair trade, and it is visible in a way a wrong `uses:` never was.
