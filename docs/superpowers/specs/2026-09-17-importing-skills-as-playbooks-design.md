# Importing a skill: somebody else's procedure, converted once, running on any CLI

2026-09-17

## The problem

Anthropic ships eleven `knowledge-work-plugins` — sales, legal, finance, support, data — as
file-based skills: a `SKILL.md` per job, frontmatter plus prose, no code. They are good, they are
free, and they are written by people who know those jobs.

They are also stuck. A skill lives in Claude Code's own directories, is read by Claude Code, and
means nothing to a codex or gemini worker. On this machine there are already 57 of them:

```
~/.claude/skills/<name>/SKILL.md                                     personal
~/.claude/plugins/cache/<marketplace>/<plugin>/<ver>/skills/<name>/   installed plugins
```

Taskuary has the shape to use them and cannot see them. It has two levels triage already routes to
— a **profile** (a worker; `agents.roster()` offers it, triage names it, it rides on `Assignee`) and
a **playbook** (a job; `playbooks.menu()` offers it, triage tags the task, `seed_block` flattens it
into the prompt). Both end up in the `PROCEDURE FOR THIS JOB` slot of whatever CLI runs the work.

So a skill written for Claude Code, converted once, would drive a codex session. That conversion is
the whole feature.

## What is being built

**An import door.** Point it at a `SKILL.md` or a plugin folder. It reads what is there, a model
converts each skill into Taskuary's own six fields, you correct the one field a model cannot know,
and from then on it is an ordinary playbook or profile — Taskuary's, provider-neutral, on any CLI.

Nothing is linked, referenced or watched. The import is a conversion, and the result belongs here.
That is the same decision `save_report_skill` already made and for the same stated reason: a
procedure must not live in "one provider's private skill directory".

### The conversion already exists

`playbooks.DRAFT_SYSTEM` turns prose into exactly the six fields and is already instructed to
*"Name systems by the connection types listed"* — it is handed the owner's connection types and told
to map onto them. It converts a terminal transcript today. Importing a skill is the same call with a
different input.

```
SKILL.md                                  playbook
  name             ───────────────►  slug / title
  description      ───────────────►  when:        ← the line triage matches on
  body             ───────────────►  steps: / notes
  (nothing)        ───────────────►  uses:        ← the model infers, the OWNER confirms
  .claude-plugin/plugin.json          which profile it belongs to
```

`description` is already a trigger sentence — it is how Claude Code decides whether a skill applies.
Same job as `when:`, different field name. Nothing needs inventing.

### `uses:` is the field a human must confirm

A `SKILL.md` never states which systems it touches, so the model infers it from prose. That is the
one inference with teeth: `playbooks.about_code` reads `uses:` against `CODE_SYSTEMS`, and a
playbook that looks like code gets CODER.md's repository rules. Import a legal skill with a wrong
`uses:` and a worker goes looking for a codebase to edit on an NDA.

So `uses:` is shown as an editable field, pre-filled by the model, checked against
`store.list_connectors()`, and the check is the useful part:

```
  uses:  [ intacct                         ]
         ⚠ this skill assumes an accounting system. You have none
           connected — it will know how to prepare an entry and have
           no way to post one.
```

That warning is not a blocker. It is the honest state of an import, and the failure it describes is
the safe one — see below.

### Connectors are never imported

Each plugin ships a `.mcp.json`. The finance one declares Snowflake, Databricks, BigQuery
(`https://bigquery.googleapis.com/mcp`), Slack (`https://mcp.slack.com/mcp`, OAuth), Calendar and
Gmail. **None of it is read.**

Taskuary's connectors are tested cards behind a guard with scoped egress and a proposal road.
Importing MCP servers would hand a worker a second way out of the building. So the import takes the
knowledge and leaves the plumbing: the skill says *how* the job is done, `uses:` names which of
**your** systems it may touch, and `seed_block` already ends with the sentence that makes this true —
*"the systems named in USES are the ground, reached through Taskuary's tools and proposals"*.

This is also why a write-shaped skill is safe to import. Of the finance plugin's six skills, one
(`journal-entry-prep`) is about writing; the rest read. But even that one is *methodology* — accrual
types, documentation requirements, review workflows — not a script that posts anything. Imported
without an accounting connector it produces a worker that knows how to prepare an entry and has
nowhere to put it. It will propose, and a proposal already needs the owner's yes.

## The limit, which is the whole risk

Triage's prompt has a budget, and it is small:

```
playbooks.menu()   → capped at 3000 chars in the triage call   (triage.py:477)
agents.roster()    → capped at 2000 chars                       (triage.py:484)
```

Importing eleven plugins wholesale would not fail loudly. It would crowd the owner's own playbooks
out of a prompt that silently truncates, and routing would get worse for everything with nothing to
point at. **That is the failure this design exists to prevent**, and it is more important than the
feature.

Two mechanisms already exist and are used rather than rebuilt:

- `agents.roster()` skips any profile whose config carries `triage_enabled: False`
- `playbooks.menu()` lists only playbooks that have a `when:` line

So: **import as many as you like; only the ones you switch on ride the triage prompt.** The rest stay
imported and usable by hand or by explicit dispatch. And because the budget is knowable, the wizard
shows it rather than guessing:

```
Import: knowledge-work / finance                    6 skills found

  ☑ reconciliation        reads    → playbook   +180
  ☑ variance-analysis     reads    → playbook   +165
  ☐ journal-entry-prep    writes   → playbook   ⚠ no accounting connector
  ☐ close-management      reads    → playbook
  ☐ financial-statements  reads    → playbook
  ☐ audit-support         reads    → playbook

  triage menu: ███████░░░  2,180 / 3,000
               your own playbooks: 1,835

  [ Import 2 ]
```

Ticked means converted **and** on the menu. Unticked means converted and off it. The bar is what
stops this degrading routing by accident, and it is the reason the import is deliberate and few.

## The walk

A wizard, because the interesting part is the correcting and there are several stops:

1. **Where from.** A path on disk, or a pick from what is already installed — the two globs above,
   grouped by `plugin.json` so `finance (6 skills)` reads as one thing.
2. **What is in it.** One row per skill with the model's proposed level and a one-line `when:`.
   Plugin-level import proposes a **profile** for the plugin and a **playbook** per skill.
3. **Correct it.** Per skill: level, slug, `when:`, `uses:` with the connector check, and the body.
   The budget bar sits under the list and moves as boxes are ticked.
4. **Import.** Writes each through `playbooks.write` / the profile's `agent` + `doc` rows. Unticked
   ones are written with `triage_enabled: False` (profile) or no `when:` line (playbook).

### Only skills, not commands

The finance plugin has five `commands/` and six `skills/`, overlapping in subject — `/reconciliation`
and `reconciliation` are the same job said twice. Importing both would put near-duplicates on the
triage menu, which is precisely the budget problem. **Skills only.** A command is a thing the owner
invokes by name, which is what a playbook attached by hand already is — so importing them would add
a second road to the same place rather than a capability. Out of scope, and not a gap.

## The lists have to survive success

Docs → Profiles and the playbook shelf were built for a handful. If this works there will be dozens,
so both get a scrolling list with the live state visible in the row — a profile or playbook that is
*not* on the triage menu must say so where you can see it, or the budget bar is the only place the
truth lives and nobody will look at it twice.

## Files

**Server**

- `taskuary/skillimport.py` — new. Finds skills (the two globs plus a given path), parses frontmatter
  and `plugin.json`, and converts via the existing `DRAFT_SYSTEM` road. Nothing about HTTP or UI.
- `taskuary/playbooks.py` — reuse `write`, `parse`, `menu`, `about_code`; no change expected beyond
  whatever the import needs to call cleanly.
- `taskuary/server.py` — `GET /api/skills/found` (what is installed), `POST /api/skills/convert`
  (one file → proposed fields, no write), `POST /api/skills/import` (write the confirmed ones).

**Web**

- `website/src/SkillImport.jsx` — new. The wizard and the budget bar.
- `website/src/DocsView.jsx` — the **Import skills** entry, beside Add profile; scrolling lists for
  profiles and playbooks with the on-the-menu state in each row.

## Tests

- a `SKILL.md`'s `description` becomes `when:`, and its `name` becomes the slug
- a plugin folder proposes one profile and N playbooks; a lone file proposes one playbook
- `uses:` naming a connector that does not exist imports fine and is reported as unconnected
- a skill whose inferred `uses:` hits `CODE_SYSTEMS` is flagged, because CODER.md would then apply
- **nothing in `.mcp.json` is read** — assert the importer never opens it
- an unticked skill is written with `triage_enabled: False` / no `when:`, and
  `playbooks.menu()` / `agents.roster()` do not list it
- the budget the wizard reports equals `len(playbooks.menu())` and `len(agents.roster())` after
  import — the bar cannot drift from the thing it claims to measure
- importing the same skill twice does not create a second copy
- `commands/` is ignored

## Deliberately not doing

- **No marketplace, no `claude plugin install`.** The owner installs with the vendor's own tooling,
  or points at a path. Taskuary reads files.
- **No live link.** Converted once, owned here. A `claude plugin update` does not silently change a
  procedure that has been running your business.
- **No MCP.** Stated above and worth repeating: connectors are the one thing this never imports.
- **No auto-import.** Nothing arrives on the triage menu without somebody ticking a box.
- **No commands.** Skills only, this time.

## The honest risk

The model infers `uses:` from prose, and it will sometimes be wrong. Everything else here is
mechanical — frontmatter to fields — but that one line decides whether repository rules apply and
which systems a worker believes it may reach. It is shown, editable and checked against real
connectors for exactly that reason, and it is the field to watch in the first weeks.
