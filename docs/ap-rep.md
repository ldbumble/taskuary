# Taskuary for an accounts-payable rep

*Thought through 2026-10-08. The question asked: can someone whose job is AP, not code, use this
app? Their mail should go to an AP worker by default. That worker answers vendors by looking
things up in the ledger (Sage Intacct) and works the bills waiting in a bill-approval portal that
has no API, in the browser, into the ledger.*

**Short answer: yes, and most of it was already built.** Four parts existed separately, and someone
who is not technical never assembled them. The missing part was putting them together.

## The day it is built for

| Arrives | What happens | Who acts |
|---|---|---|
| "Where is payment for invoice 4471?" from a known vendor | triage: a task, the `vendor-payment-inquiry` playbook, the `ap` worker → the worker reads VENDOR / APBILL / APPYMT through the Intacct card → a drafted reply on the task | the rep approves the reply |
| A statement of account | same road; the reply lists only the open items | the rep approves |
| "We changed banks, please update" | the playbook puts it under *ask first*: flagged for a call-back, and no confirming reply is drafted | the rep phones a number already on file |
| 08:00, the daily portal job (once switched on) | the `ap` worker opens the portal in the browser it was signed into, lists approved bills, looks each up in Intacct, and posts **one proposal per missing bill** plus a table of what disagrees | the rep approves each bill proposal; approving it posts the bill |

## What one click lays out (`taskuary/roles.py`)

**Docs → Profiles → Start from a role: Accounts payable → Set up** (or `POST /api/roles/ap`):

1. **The worker:** an `ap` profile with `AP.md` (`templates/ap.md`), on the triage roster, running
   on the same CLI as the coding agent.
2. **Two playbooks**, copied into `~/.taskuary/playbooks`: `vendor-payment-inquiry` (read-only, a
   drafted reply) and `bill-portal-to-ledger` (reads the portal and proposes bills).
3. **Where the mail goes:** `default_profile = ap`, a new setting (Settings → Triage & routing →
   *Your mail goes to*). `agents.routed_role` uses it when triage judges a message to be general
   work and names no better-suited worker. Triage still picks a researcher for outside
   information, and coding still goes to the coding agent.
4. **The ledger is narrowed to read**, but only if nobody ever chose the Intacct card's Authority.
   Every bill then becomes a proposal the rep approves. Since 2026-10-05 connections start at full
   authority, and at that level an agent could post a bill itself. The playbooks forbid it, but
   wording in a prompt does not stop anything. A card whose Authority someone set is left alone.
5. **The daily portal workflow**, created **switched off**: a browser job, `access: write`,
   `agent: ap`, daily at 08:00, carrying the portal address if one was given. It stays off until
   the rep has signed in to the portal once, by hand, in the pane. Workflow runs now run as the
   worker they name (`workflows.run` stamps `Assignee`), so the job is given AP.md.

Applying twice changes nothing, and nothing the owner already wrote is overwritten.

## What is honestly still weak

- **A browser click is not gated by code.** The agent drives agent-browser from its own shell.
  Nothing in Taskuary sits between it and the portal's *Approve* button except the playbook's
  wording. That is why the portal side is read-only and every change goes through an Intacct
  proposal. Keeping it safe means keeping it that way. A browser action that waits for approval
  would be a new kind of proposal, and it is not built.
- **Sign-ins expire.** The saved sign-in is kept only when the browser closes cleanly, and SSO or
  2FA prompts are never answered automatically. When the portal turns the run away, it stops on the
  sign-in page and asks. Expect that on some mornings.
- **A first-time vendor does not start an agent on its own.** Mail from an unknown sender never
  auto-starts a worker (`ingest.auto_start_ok`), which is the prompt-injection boundary. The task
  waits for the rep to press Start. That is the right default for mail asking about money.
- **A question triage judges `reply_only` is drafted blind.** The responder has no tools. A vendor
  question that needs a lookup should become a task (TRIAGE.md says so), and the AP playbook's
  `when:` line steers it there. When it misses, the fix is in the evidence (TRIAGE.md, LEARNED.md),
  never a hard-coded word list.
- **Invoice numbers.** The playbook tells the agent to try the obvious variants. There is no
  normaliser in code.
- **Proposals are not re-validated at approval.** `proposals.validate` checks only that a type is
  present, and the agent's keys can override the card's (`company_id`, `entity_id`). The bill
  proposal shows the exact record, so the rep sees what they approve. Hardening this is open.

## Not done, on purpose

- No portal connector. The portal has no API; the browser *is* the connector, and naming one
  vendor's portal in shipped code would say whose stack this is.
- No auto-posting threshold ("bills under $500 post themselves"). The playbook template supports an
  `alone:` line for it. The rep can write one once they trust the run, and setup does not start
  with one.
