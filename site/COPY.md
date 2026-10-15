# The words on taskuary.com

Every piece of text on the landing page, pulled out of the code and laid out as plain
writing. **Edit this file (or a copy of it) freely — you cannot break the site from here.**
Nobody has to touch HTML: whoever owns the repo pastes the approved wording back into
`site/index.html`, slot by slot, using the numbers below.

## Read this first (about "the login")

There isn't one, and that is not a permissions problem — there is no account to hand over.
taskuary.com is a single hand-written file (`site/index.html`) that Cloudflare re-publishes
every time it changes in GitHub. No CMS, no admin panel, no "edit page" button. The only
accounts involved are GitHub (where the file lives) and Cloudflare (which serves it), and
neither is a place you'd want to write copy.

Three ways to work, easiest first:

1. **This document.** Rewrite the slots below, send it back, it gets pasted in. No tools,
   no account, no markup. This is the recommended path and the reason this file exists.
2. **GitHub account.** An invite to the repo lets you edit this one file in the browser and
   get a private preview link of the real page before anything goes live. Still shaped like
   a developer tool, but it's one file and a pencil icon.
3. **Move the site onto Webflow/Framer** so there's a genuine visual editor. Honest cost:
   the animated hero is a custom renderer borrowed from the app itself and no page builder
   will host it as-is, so this means rebuilding the page. Not worth it at v0.3.

**To see the product before writing about it, you do not need a login either:**
<https://taskuary.com/demo/> is the real app running on invented work, in the browser,
no install and no sign-up.

## How to use the slots

Each slot has the text that's on the page now, and a suggested rewrite. The suggestions are
a first pass in one direction — *the product is that your work keeps moving and nothing gets
dropped; the agents are how, not what* — written to be argued with, not accepted. Strike
them out and write your own.

Keep roughly within the lengths noted; they're what the layout holds without reflowing badly.

---

## The copy as it stands (2026-10-15 - "Your work manager" voice)

Short, plain, one idea per line. Two lines from the mockup this voice came from were left out on purpose: **"HIPAA
Certified"** (there is no official HIPAA certification and Taskuary has had no compliance audit - a public claim we
cannot back) and **"Free in beta, limited time"** (the site says MIT licensed, free, no subscription; "limited time"
contradicts it). Put either back only with that settled.

| # | Slot | Now |
|---|---|---|
| 1a | Headline | `Your work manager.` / accent line `Locally. Securely. In control.` |
| 1b | Under it | `Mail, chats and tickets become one list, in the right order. Taskuary drafts the replies, your AI agents do the work, and nothing goes out without your yes.` |
| 1c | Button / line under | `Download today` / `Windows · or pip install taskuary on macOS and Linux · try it in your browser` |
| 1d | Four promises | `Runs on your computer` - Your data stays with you. · `Private by design` - No account. No cloud. · `Free and open source` - No subscription. · `Minutes to set up` - Download and start working. |
| 2 | Three steps | `01 · IT ARRIVES` Everything in one place - Email, Teams, Slack, WhatsApp, tickets and reports - one list, in the order it came in. · `02 · IT GETS SORTED` Only what's yours - It reads the whole thread, drafts the answers, and turns real work into tasks. · `03 · IT GETS DONE` You say yes - Agents do the work while you're elsewhere. Nothing goes out until you approve. |
| 3 | What it does | `Your work, in the right order.` / One list for everything people ask of you - sorted, started, and waiting on your yes. |
| 3a-f | Six cards | Nothing goes out without you · Watch the work happen · Reports in plain English · Tell it once · Uses the AI you have · Your data stays home - one line each |
| 4 | Download | `Download today.` / One app, three ways to install. Everything stays in one folder on your computer. New to it? Start here. |
| 5 | Open source | `Built in the open.` / MIT licensed, and running its author's own inbox every day. |
| 6 | Bottom strip | `it arrives → it gets sorted → it gets done` |
| - | Tab title / previews | `Taskuary — your work manager. Locally. Securely. In control.` · search: `Your work manager: mail, chats and tickets in one list, in the right order - worked, and waiting for your yes. Runs on your computer. Free.` |

The README (both languages), the package description and the docs' header tag carry the same headline.
