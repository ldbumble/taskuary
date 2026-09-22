# Working in this repository

## Never commit the owner's own data

This repository is **public**. It is also built by reading one person's real mail, so the pull is
constant: the quickest way to write a test for a bug is to paste the message that caused it, and
the clearest way to explain a fix is to name the people in it. Both put a private thing somewhere
it cannot be taken back from — a commit message, a fixture, a comment, a screenshot.

**None of it goes in.** Not in code, tests, fixtures, docs, comments, commit messages, or images:

- names of colleagues, senders, residents, patients or customers
- company names, facility names and numbers, internal repository names
- mailbox addresses and the domains around them
- what a real thread actually said, where it identifies the people in it
- anything a divestiture, a contract or a salary could be read out of

What a bug NEEDS is its shape — a forwarded chain, a report that repeats, two mails in one poll.
Write that, with invented people. A test reads better for it, and the failure it pins is the same.

### The stand-ins this repository already uses

Addresses use RFC 2606's reserved names — `*.example`, `example.com`, `.test`, `.invalid` — and
nothing else. `tests/test_demo.py::test_nobody_real_is_in_it` enforces that for the demo world, and
it asserts the invariant rather than naming any real domain, which is the pattern to copy: a guard
that spells out the thing it guards against has published it.

| for | use |
|---|---|
| the owner | Alex Doyle, `alex@northwind.example` |
| their company | Northwind, `northwind.example` |
| colleagues | Erin Blake, Gail Moreno, Paula Vance, Ray Colton, Marcus Reed, Omar Keller |
| a vendor | `vendor.example`, Payworth, Trainly, Spendly, PhishGuard |
| repositories | `northwind/ledger`, `northwind/portal`, `org/app` |

**The one exception** is the connector catalogue (`taskuary/connectorcatalog.json`,
`website/src/logos.jsx`, `docs/site/connections.md`, the keyword list in `taskuary/reports.py`).
Naming PointClickCare, ADP, Epic or Cerner there says what this app can connect to. That is a
feature of the product, not a fact about its owner.

### A commit message is public too

Say what changed and why it was wrong. The story can keep its shape without its cast: "a sender
wrote twice in one morning", not the sender's name; "two divested sites", not which ones. If the
detail is what makes the commit understandable, it belongs in the code comment — with invented
names there as well.

### Screenshots and recordings

`docs/*.png` and `docs/product-demo/*.mp4` are shot from a running app. Shoot them against the
demo world (`taskuary --demo`), never against a live mailbox, and check the sidebar, the titles and
the notification tray before committing the frame.
