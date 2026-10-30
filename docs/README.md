# Taskuary documentation

The user documentation lives at **[taskuary.com/docs](https://taskuary.com/docs/)**.

It is written once, as markdown in [`docs/site/`](site/), and built into `site/docs/` by
`npm run build:docs` in `website/`. CI rebuilds it and fails if the committed pages are not what a
fresh build produces, so the site and the source cannot drift apart.

| Page | Covers |
|---|---|
| [Start here](https://taskuary.com/docs/) | What Taskuary is, how to install it, and what the first hour looks like |
| [How it works](https://taskuary.com/docs/how-it-works) | One message from arrival to approval: the work rail, the five roads, and what triage actually decides |
| [Connections](https://taskuary.com/docs/connections) | The accounts Taskuary may read, and the role that says what it may do with each |
| [Tasks and agents](https://taskuary.com/docs/tasks-and-agents) | A task, the agent work on it and the reply to the sender are three separate lives |
| [Assistant buttons](https://taskuary.com/docs/assistant) | Every button under an Assistant card, the one question two of them ask, Remind me, and the words that work typed |
| [What the Assistant sees](https://taskuary.com/docs/assistant-tools) | Every tool the Assistant has: the summary it gets on every turn, and each tool in detail |
| [Reports and the Advisor](https://taskuary.com/docs/reports) | Reading the systems you work in on a schedule, and the report whose job is to judge |
| [The Advisor](https://taskuary.com/docs/advisor) | What goes into the brain that says what should happen next, its two clocks, and the outcome ledger |
| [On your phone](https://taskuary.com/docs/phone) | The same assistant over WhatsApp or Telegram, and what it may do there |
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

**[The Assistant's words](assistant-words.md)** is the same for the Assistant's buttons: which card offers
which, the one question two of them ask, and what was retired. Its trees are drawn onto the docs site
(`website/tools/render-diagrams.mjs`), where each word also gets a row in a table.
