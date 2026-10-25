The questions people ask before they install, answered short. Each one links to the page that
holds the detail.

## Does it run locally?

Yes. Taskuary is an app on your own machine, not a service you sign up for. It keeps everything
in a SQLite file under `~/.taskuary/` and serves its interface at `http://127.0.0.1:7787`, for you
only. There is no Taskuary account and no Taskuary server: nothing you connect passes through us.

Setup on Windows is one file, [Taskuary.exe](https://github.com/ldbumble/taskuary/releases/latest/download/Taskuary.exe).
Anywhere with Python 3.10+, it is `pip install taskuary`. Docker works too. From there, **Set up
Taskuary** walks four steps: who you are, one AI, one work source, and a first read. See
[Start here](index#install-on-windows).

To look before connecting anything, `taskuary --demo` runs the real interface over invented work
and cannot reach a real system.

## Does it need internet access? What can the browser reach?

Taskuary itself only talks to the services you connect — your mailbox, your chat, your trackers and
the AI you chose. With a [local model](#do-i-need-to-buy-tokens), the AI calls never leave the machine.

When an agent needs a website, it drives a real browser on your machine (the optional
`agent-browser` tool), so it reaches whatever your machine can reach, over your network and VPN.
The page shows live beside the agent's terminal. The agent never sees a password or a 2FA code: you
press **Take over** and sign in yourself, or Taskuary types a sign-in you gave it (and, if you kept
the site's authenticator key, its code). A click that would pay, send or delete waits for your
**Approve**. Sites it should only *read* can go through
a search or reader connector instead, with no browser at all. See
[When the agent opens a browser](tasks-and-agents#when-the-agent-opens-a-browser).

## Do I need to buy tokens?

No Taskuary tokens or seats exist: the app is free and open source (MIT). The AI is the only thing
that costs, and you bring your own, in whichever of these you already pay for:

| You have | Taskuary uses |
|---|---|
| An API key (Anthropic, OpenAI, Azure OpenAI, OpenRouter) | the key, billed per use by that provider |
| A ChatGPT plan | **Sign in with ChatGPT**, billed to the plan under a weekly cap you set |
| A coding CLI subscription (Claude Code, Codex and others) | the CLI, with a light model for routine mail |
| None of these | Ollama or another local model server, at no cost per message |

Triage reads many messages and wants a small cheap model; coding wants a strong one. They can be
different. See [Choosing the AI setup](index#choosing-the-ai-setup).

## Will you sign a BAA? Can it handle patient data?

There is no Taskuary service holding your data, so there is nothing for us to sign a BAA for —
the data stays on your machine and in the systems you already use. The agreements that matter are
the ones you hold with whoever *does* receive data:

- **The AI provider.** A hosted model receives the text of what it reads. If that can include PHI,
  use a provider and account under your organisation's BAA (Azure OpenAI and the enterprise tiers
  of the major providers offer one), or a local model, which sends nothing out.
- **Your mail and other systems.** Taskuary reads them with your own sign-in, so the BAA you
  already hold with them still applies.

Before a prompt reaches a hosted model, Taskuary replaces recognisable credentials with
placeholders. It does not remove PHI: whether a given setup meets your HIPAA obligations is a
decision for your compliance team. See [What leaves your machine](index#what-leaves-your-machine).

## Can it be trained on our software?

Not by retraining a model — it learns the way a new hire does, by being given the material and
corrected on the job:

- **Your documents.** The Knowledge base indexes folders on the machine and SharePoint libraries
  (manuals, SOPs, policies). Agents, the Assistant and reply drafts are handed the passages that
  bear on the work. See [Connections](connections#data-and-report-sources).
- **Your systems.** Connect what has an API; for what only has a web screen, the agent works it in
  the browser while you watch.
- **Your jobs.** The first time an agent does a kind of job, Taskuary drafts a playbook — the
  steps, what it may do alone, what to ask first, what counts as done. Approve it and the next job
  like it follows it. See [Profiles and playbooks](tasks-and-agents#profiles-and-playbooks).
- **Your judgment.** Each verdict you correct becomes a lesson for the next message like it. See
  [How it works](how-it-works).

All of it lives in files on your machine that you can read, edit or delete. Taskuary trains no
model on it.
