# Taskuary documentation

The user documentation lives at **[taskuary.com/docs](https://taskuary.com/docs/)**.

It is written once, as markdown in [`docs/site/`](site/), and built into `site/docs/` by
`npm run build:docs` in `website/`. CI rebuilds it and fails if the committed pages are not what a
fresh build produces, so the site and the source cannot drift apart.

| Page | Covers |
|---|---|
| [Start here](https://taskuary.com/docs/) | What Taskuary is, installing it, the first run, where your data lives |
| [How it works](https://taskuary.com/docs/how-it-works) | The Timeline, the five roads, what triage decides, the documents that govern it |
| [Connections](https://taskuary.com/docs/connections) | The accounts Taskuary may read, and the role that says what it may do |
| [Tasks and agents](https://taskuary.com/docs/tasks-and-agents) | The task, the agent work and the reply as three separate lives |
| [Reports and the Advisor](https://taskuary.com/docs/reports) | The report pipeline, and the report whose job is to judge |
| [On your phone](https://taskuary.com/docs/phone) | The same assistant over WhatsApp or Telegram |
| [Settings reference](https://taskuary.com/docs/settings) | Every setting — generated from `taskuary/settings_schema.json` |
| [When something is wrong](https://taskuary.com/docs/troubleshooting) | What to check, in the order worth checking it |

## Editing the documentation

1. Edit the markdown in `docs/site/`. A `##` heading becomes a rail entry, an anchor and a search
   crumb at once — there is no separate index to update.
2. `cd website && npm run build:docs`
3. Commit `docs/site/` and `site/docs/` together.

`npm test` in `website/` checks that every cross-reference still resolves, that every page is in
the manifest and vice versa, and that the settings reference still matches the schema.

The settings page is generated: adding a knob to `taskuary/settings_schema.json` puts it in the
docs on the next build, with the same label, group and help text the app shows.

## Engineering notes

The rest of this folder is working material rather than product documentation — design records,
acceptance ledgers, investigation write-ups, and the specs and plans under `superpowers/`. It is
kept because it explains why things are the way they are, not because it is meant to be read as a
guide. [Status and roadmap](roadmap.md) is the one that is still for readers.

**[How a task ends](how-a-task-ends.md)** is required reading before touching anything that finishes a
task: the one close (Mark done), every door into it, and the decision tree.
