# Browser use vs computer use — what Taskuary should drive

*2026-09-14. Asked after TQ-0514 ("log into ADP every morning at 9am and clock me in"): which of the
two open-source families makes this seamless, given that for local work the shell already does most
of it.*

## The short answer

Stay browser-first, and do not buy a pixel-driving desktop agent. The order to reach for is:

1. **An API or connector** — if the system has one, nothing below is worth doing.
2. **Structured UI** — the browser's DOM/accessibility tree (what we already drive), and on Windows
   the UI Automation tree for native apps. Cheap, fast, inspectable, and it says what a control *is*
   rather than what it looks like.
3. **The shell** — CMD/PowerShell for anything local. Deterministic, auditable, free. The owner is
   right that this covers most local work; a GUI agent clicking through Explorer is a worse `robocopy`.
4. **Pixels (true computer use)** — a model looking at screenshots and moving a mouse. The escape
   hatch for Citrix, thick clients, and anything with no tree at all. Slow, expensive, and on Windows
   it fights us for the owner's own screen.
5. **The human** — the take-over button. Always reachable, and the only correct answer for a password
   or a 2FA code.

We are already at (2) and (3) and should deepen those. (4) earns its place only inside an isolated
desktop nobody is sitting in front of, and we have no job today that needs it.

## Why not pixels — the numbers

The gap is not ideology, it is an order of magnitude on both axes.

| | Structured (DOM / AX tree) | Pixels (screenshot loop) |
|---|---|---|
| Tokens per step | baseline | ~6× more (pixels vs the same page as a tree) |
| A real admin-panel task | 8 structured calls, ~12K tokens | 53 steps, ~551K input tokens |
| Latency | no image encode | ~0.8s of extra inference per screenshot |
| What the model sees | role, name, value, state | a picture it must ground into coordinates |

Reliability tells the same story. On **OSWorld** — the desktop benchmark — humans score ~72%, and
published 2026 systems land between ~54% and ~77% depending on the harness (CoAct-1 60.8%, Agent S2.5
56.0%, Agent Alpha 77.3%). Blog round-ups claiming "85% by June 2026" do not match the papers; treat
the high numbers as harness-specific. And on **OSWorld 2.0**, whose median task takes a human 1.6
hours, the best frontier system finishes **20.6%**. Long, real jobs are exactly what a clock-in
automation is made of.

Browser agents on browser work are in a different regime: Browser Use reports **89.1%** on WebVoyager
(vendor-reported, 586 tasks). Same models, different observation interface.

## Where the browser field landed, and where we already are

The consensus in 2026 is CDP directly, not Playwright, with the accessibility tree as the model's
view of the page. Browser Use (MIT, ~115K stars) rewrote itself onto raw CDP for exactly that reason;
Playwright MCP and Chrome DevTools MCP are the same idea packaged as tool servers.

We are not behind this — we are already on it. `browserview.py` drives **agent-browser**
(vercel-labs, Rust core, ~40K stars) over its own session files, relays its CDP screencast into the
pane, forwards the owner's mouse and keys back, and restores cookies with `--restore taskuary`. That
is the live-view-plus-take-over surface the hosted products sell, running locally.

Three concrete things to fix rather than replace:

- **We are on 0.35.1; upstream is 0.37.1.** The newer screencast uses `Page.startScreencast` on a
  dedicated session instead of polling `captureScreenshot` — Chrome pushes a frame per repaint, which
  is a smoother pane for free.
- **We run headless.** Detection in 2026 is not a `navigator` boolean; it is whether the session looks
  internally consistent — and *"a session that performs a login without a single mouse-move event
  preceding it is bot-by-default"*, with CDP-injected input failing entropy checks almost universally.
  A payroll portal behind a commercial bot-detection vendor is the likeliest place for this to bite.
  The fix is a headful Chrome on a hidden display rather than `--headless`, plus keeping the owner's
  restored profile (aged cookies are the strongest "real user" signal we have).
- **The tree is the cheap view, and we do not ask for it.** The CLI drives the page through
  agent-browser's own commands; we never hand the model an AX-tree snapshot. That is the single
  biggest quality lever available before any new dependency.

There is a fourth option worth naming and rejecting: an **extension in the owner's own Chrome**
(Nanobrowser and friends). It inherits their real logged-in sessions — no second login, no detection
problem — but it drives the browser they are using, which is the same conflict as a desktop agent,
and it cannot run at 9am while the laptop sits locked.

## Computer use, if we ever need it

The open-source stack is real and Apache-2.0-clean, so this is a choice, not a constraint:

- **UI-TARS Desktop** (ByteDance, Apache-2.0) — open-weight grounding models trained on GUI
  screenshots, with native Windows understanding. Needs a GPU to run the model locally; otherwise a
  hosted VLM per step.
- **Bytebot** (Apache-2.0) — a whole containerized Linux desktop the agent owns, watched over VNC.
  The right *shape*: the agent gets its own machine, the owner watches a stream. Linux only, which is
  not where Northwind's applications live.
- **Agent S3 / E2B desktop** — same shape, sandbox-first.
- **Hosted CUAs** — Azure's `computer-use-preview` is registration-gated at $3/$12 per Mtok, and
  Copilot Studio's computer-use agents went GA on 2026-05-13. Both assume a VM you can screenshot.

The blocker for us is not capability, it is **whose screen**. Every Windows pixel agent drives the
interactive desktop session — the owner's. It steals focus, it types into whatever is in front, and
Windows deliberately forbids it the sign-in screen and UAC prompts. To make it watchable-and-not-in-
the-way you need a second desktop: Windows Sandbox, a Hyper-V VM, or a VNC/RDP session we stream into
a pane exactly as we stream the browser. That is a machine to build and maintain, for jobs we do not
currently have.

## Windows desktop without pixels

If a native app does come up, the first move is not vision — it is **UI Automation**, the desktop's
accessibility tree. Several MIT/Apache MCP servers already expose it (FlaUI-MCP, CursorTouch's
Windows-MCP, deploymenttheory's windows-mcp-server, the consent-gated UIInspect.MCP), and we have a
stdio MCP client in `mcp.py` to talk to one. No vision model, no grounding, the same structured
argument that makes the browser work.

Two honest caveats before anyone plans on it: those servers are young (single-digit stars in one
case), and building a desktop AX tree is *not* free the way a DOM snapshot is — OSWorld-Human measured
**3 to 26 seconds** per tree depending on the window. It is still the right first move; it is not a
drop-in.

## What "seamless" actually requires for the ADP job

The walk's agent was right to say it could not set up unattended daily clock-ins from that
conversation, and none of the reasons are about browser-vs-computer use:

- **Credential custody.** We hold connector secrets in the store today; a portal login needs the same
  treatment plus an explicit owner grant, and the take-over button stays the path for anything typed
  once.
- **Northwind.** If ADP demands a code every session, unattended is impossible by design and the honest
  product is a 9am *prompt* with the page already open on the clock-in button — one click, not zero.
  If it accepts a remembered device, the restored profile carries it.
- **A schedule that owns a browser.** `reports.py` runs work on a clock; nothing there starts a
  browser session and nobody watches the result. That is the actual build.
- **Detection and terms.** Automating a payroll portal may breach its ToS, and a flagged session is an
  IT conversation the owner has to want to have. Name it before building, not after.

## Verdict

Browser use, and deepen it: upgrade agent-browser, go headful on a hidden display, give the model the
accessibility tree, and put a scheduled browser job behind the walk. Keep the shell for local work.
Treat Windows UIA over MCP as the next rung *if* a native app ever blocks a job, and treat pixel
computer use as a sandboxed last resort we have not yet needed — the day we do, the shape is Bytebot's
(the agent gets its own desktop; the owner watches a stream), never a model taking the owner's mouse.

## Sources

- [Browser Use (MIT, CDP rewrite)](https://github.com/browser-use/browser-use) ·
  [Leaving Playwright for CDP](https://browser-use.com/posts/playwright-to-cdp)
- [vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser) ·
  [releases](https://github.com/vercel-labs/agent-browser/releases)
- [OSWorld](http://osworld-v1.xlang.ai/) · [CoAct-1](https://arxiv.org/pdf/2508.03923) ·
  [Agent Alpha](https://arxiv.org/pdf/2602.02995) · [OSWorld 2.0](https://arxiv.org/pdf/2606.29537) ·
  [OSWorld-Human (AX-tree latency)](https://arxiv.org/pdf/2506.16042)
- [Accessibility tree vs screenshots: the token math](https://dev.to/siropkin/accessibility-tree-vs-screenshots-the-token-math-behind-my-browser-agent-3fk9) ·
  [API → connector → browser → computer use hierarchy](https://dev.to/amitrix/api-connector-browser-computer-use-human-a-cost-justified-hierarchy-for-agent-tooling-119b)
- [Headless browser detection in 2026](https://cside.com/blog/headless-browser-detection) ·
  [CDP detection in 2026](https://usefoil.com/learn/cdp-detection)
- [UI-TARS Desktop (Apache-2.0)](https://github.com/bytedance/UI-TARS-desktop) ·
  [Bytebot (Apache-2.0)](https://github.com/bytebot-ai/bytebot) · [E2B desktop](https://e2b.dev/docs/use-cases/computer-use)
- [Azure computer-use](https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/computer-use) ·
  [Copilot Studio computer use GA](https://www.digitalapplied.com/blog/copilot-studio-computer-use-agents-ga-deep-dive)
- Windows UIA over MCP: [FlaUI-MCP](https://github.com/shanselman/FlaUI-MCP) ·
  [windows-mcp-server (MIT)](https://github.com/deploymenttheory/windows-mcp-server) ·
  [UIInspect.MCP](https://github.com/ChrisPulman/UIInspect.MCP)
- [Nanobrowser (extension in your own Chrome)](https://github.com/nanobrowser/nanobrowser)
