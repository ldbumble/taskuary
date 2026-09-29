# The assistant canvas runs the whole app — design

Date: 2026-09-29 · Status: approved in conversation, awaiting spec review

## Goal

One screen. The Assistant becomes the app: a thin sidebar on the left drives the work, and the canvas on the right
shows whatever part of the app is in use — a task, an agent's session, a connector, a setting, a report — inside the
conversation. The deterministic app is walked and browsed by clicks that never wait on a model; the AI is always
beside it, with the thing on screen as its context, and can operate any of it. The tab strip goes.

This extends `2026-09-18-assistant-runs-the-app-design.md` (the walk is the spine; the chat is the hands, never the
ideas) — it does not replace it.

## What the owner asked for (the brief)

- Sidebar: today's work rail, **kept as it looks now** (the spine with its dots, the age gutter, the category pills,
  the bordered rows), only narrower, with a few buttons on top. Not a copy of another product's sidebar.
- Rail sections: **On you** · **Agents working** · **For later** (replaces "passed") · **Reports** · **Advisor ideas**
  · **FYI**. Clicking a section heading walks that section.
- **For later** says when each item comes back, in the age gutter's own short form.
- Clicking a row shows that part of the app **inside the assistant canvas**, as the Tasks tab shows it today, a
  little narrower. Every card keeps the look of the tab it comes from. The walk's own chat cards go: walking shows the task view, item after item.
- Coding and general agents open **near full size inside the chat** — a chat within the chat — and the assistant can
  relay both ways with the agent on screen.
- Connections, Settings, Reports and Hub are browsed **deterministically in the chat**: pick a section, its cards
  appear, click one and the rest go (Back returns), its details open. The AI can always talk about, or set up, the
  card that is open.
- Timeline is a switch (Work | Timeline) that sits **with the rail**, under the buttons — it changes the task rows,
  not Reports or Connections. **New** (a new task) is the first of the sidebar's buttons. Board and its agent wall stay a full-screen view reached from the top.
- The phone matches: the WhatsApp/Telegram doorway and the web app at phone width.
- The terminal must not redraw garbage, and the rail must not rebuild on every click.

## Layout

```
┌ sidebar ~320px ──────────────┐┌ canvas ─────────────────────────────────────────┐
│  New · Reports               ││ ✦ Taskuary · 2 in the pipe          Board · 2   │
│  Connections                 ││  earlier items, folded to one line              │
│  Hub                         ││                                                  │
│  Settings                    ││  ┌ TQ-0801 Export drops rows ─────── Next [⤢]┐  │
│ [  Work  |  Timeline  ] (⏷)  │  │ (1) Task       — the Tasks tab's card      │  │
│ 2 in today · synced · Sync   ││  │ (2) Agent work — session, near full height │  │
│      ( ON YOU )──────── 2    ││  │ (3) Close out                              │  │
│ <30m ●│[✉ Export drops… on you]│  └────────────────────────────────────────────┘  │
│  2h  ●│[✉ Approve invoice…]  ││                                                  │
│      ( AGENTS WORKING )─ 1   ││  [ Ask about this one…                  🎤 ↑ ]  │
│      ( FOR LATER )────── 3   │└──────────────────────────────────────────────────┘
│  3h  ●│[✉ Lease renewal…]    │   gutter in For later = time until it comes back
│      ( REPORTS )(IDEAS)(FYI) │
└──────────────────────────────┘
```

### Sidebar (`AssistantView` rail, narrowed)

- **Today's rail, narrowed** to ~320px (today ~470): the spine with a source dot per row, the age gutter, the
  category pills with their rule and count, bordered rows with icon, title, ref and state chip, "on the table" on
  the current row. Collapsible.
- **Buttons on top:** New · Reports · Connections · Hub · Settings — one line each. New opens the new-task form;
  the rest post their browse card (below).
- **Under the buttons, the rail's header:** a full-width `Work | Timeline` selector (two equal halves) with the
  filter as a small icon button beside it (it opens today's Kind / Source popover; its tooltip says what it filters
  to), then the counts / checked / Sync now line. The switch belongs to the rail because it changes the task rows only.
- **Sections**, sticky headings, in this order. `funnelPile.LEVEL_ORDER` becomes
  `urgent, task, agents, passed→later, reports, ideas, fyi`:
  - **On you** — urgent + your task (as today).
  - **Agents working** — moves from last to second.
  - **For later** — what Next walked past (today's `passed`) **and** tasks put away with Remind me. The gutter shows
    how long until it comes back, in the age gutter's own short form (`< 30m`, `3h`, `2d` — `funnelPile.railAge`
    applied to the return time); sorted soonest first; no sub-headings. Walked-past rows come back after
    `task_return_minutes`; Remind-me rows at `RemindAt`.
  - **Reports**
  - **Advisor ideas** — new level; ideas leave FYI (`levelOf`: `kind === "idea"`). Only while it is still an
    idea: made a task or handed to an agent, it is a task and moves to On you / Agents working like any other;
    dismissed, it leaves the rail.
  - **FYI**
- Rows keep today's grammar and look; the title truncates earlier at the narrower width, the full title on hover.
- The fill rule (`fillCaps`) is unchanged: reports, ideas and fyi divide what is left; your work is never capped.

### Walking a section

- Clicking a section heading puts that section's first row on the table; **Next stays inside the section** until it is
  empty, then says so ("FYI done") and returns to the normal walk.
- Server: `concierge.surface` / `funnel.next_item` accept `section` (a level name). The level is computed server-side
  from the same band the rail uses (`order_band`, `surfaced`, kind), so the rail and the walk agree on membership.
  The section is kept with the walk's current key (`concierge.current_key`), and cleared when it runs out.
- Clicking a row puts that row on the table, as today.

## The canvas

### The item on the table is the task view

Every card keeps the look it has in its tab today — the numbered stage headings with their colours, the bar
buttons, the lifecycle chips, the agent pane's harness/model row and Full screen; the connector card of the
Connections tab; the settings groups; the report editor. Only the width changes.

The walk no longer draws its own cards (report card, item card, Next/More actions). Every item is shown by
**`TaskPage`** — the Tasks tab's task view, extracted — at canvas width minus margins:

- **An item with a task behind it:** Task · Agent work · Close out, exactly the Tasks tab's three cards and buttons.
- **An item with no task** (an fyi mail, a landed report, an idea): the same view with only the first card — the
  message or report in full, with the same actions the walk offers today (Next, Make a task, Send to agent, Not ours,
  Mark read). Making it a task fills in the other two cards in place.
- **Next** lives on the view's bar, as on the Tasks tab.

Earlier items **fold to their title line** in the scroll; clicking a folded line puts it back on the table. Only the
item on the table is mounted live: one terminal, one editor at a time.

### Agent sessions: a chat within the chat

- When the item on the table has an agent (coding or general), **Agent work opens near full canvas height** — the
  terminal for a CLI agent, the conversation pane (`GeneralWorkspace`) for a general one. The Task and Close out
  cards collapse to their headers above and below it.
- **Expand** takes the whole view to full canvas height; the composer stays under it.
- **The assistant relays both ways.** Its context for the turn includes the agent's state and recent output
  (`workerstate.status`, the witness's last message, the run's open question). "What is it doing?" is answered from
  that; "tell it to use the staging branch" goes to the agent (`agent.answer`, or the session's input when it is
  working). Owner words typed into the agent's own pane go straight to the agent, as now.

### Browsing Connections, Settings, Reports and Hub (no AI)

One pattern, all in the scroll, all clicks:

1. **Sections.** The sidebar button posts a card of section chips — Connections: the catalogue's groups (Mail,
   Chat, Code, Finance…); Settings: the settings map's sections (`settings_schema.json` groups); Reports: the ones you
   run + New report; Hub: a search box.
2. **The list.** A chip posts that section's cards in a grid.
3. **One.** Clicking a card hides the rest of that list and opens its details in place — the real connector card,
   settings group, report editor or Hub page, with today's controls. **Back** returns to the list; nothing above it
   in the scroll changes.

The open card is the item on the table: the AI's context is that card's key. "Why is this failing?" is about that
connector; "connect it with my work account", "turn on auto-drafts", "send this report at 8" become the existing
operations (`connection.create`, `setting.set`, `report.route` …) and the card re-renders in place when they run.
Irreversible actions still wait for a yes on the card (the tiers of the 2026-09-18 spec).

This reuses the setup walk's machinery (`/api/setup/walk`, `pushStop`) — a card pushed into the conversation with
buttons — rather than inventing a second.

### Top bar

Brand · **Board** (full screen: agents + wall) · the counters and icons on the right. The Tasks, Reports,
Connections, Settings and Hub tabs are removed. Deep links (`#task=123`, `#settings/…`, `#connections/…`,
`#reports/…`) open the matching card in the canvas, so notifications and old links still land.

## Phone

- **Web at phone width:** the sidebar is a drawer (today's rail-open toggle); the canvas is full width; the task view
  stacks its cards; an agent session opens full screen with a back arrow to the chat.
- **WhatsApp / Telegram doorway** (`remote_assistant`): the same sections — "walk FYI", "walk For later" are
  offered as picks; For later lines carry their come-back time; an opened task arrives as the task view's three
  parts in text (task · agent · close out), the way `story_block` + `move_block` already write it; a running agent's
  latest output and question are relayed, and a reply goes to the agent (the doorway already answers agents with
  `answer_the_agent`). Browsing Connections/Settings on the phone is numbered picks through the same
  sections → list → one steps.

## Hard requirements

1. **No terminal redraw corruption.** A ConPTY grown after output corrupts the pane (see
   `ConPTY grow corrupts the pane`). Folding, unfolding and Expand must never resize a live pty upward: the pane
   opens at the largest size it can be shown at (the expanded canvas) and is clipped when folded, as the current fix
   does. Test: expand/collapse a live session and assert the pty's size never grows after first output.
2. **No rail rebuild on a click.** Folding, unfolding, expanding and browsing are client state. Only an action that
   changes an item (Next, done, a proposal run) may rebuild the pile; putting a row on the table uses the existing
   `surface` path, which is measured at ~0.5 s. Test: a fold/unfold/expand/Back sequence issues no `/api/funnel/pile`
   request.
3. **One live card.** At most one `TaskPage`, one terminal and one browse detail mounted at a time.

## Build order — each step ships alone and the app works after it

1. **Sidebar.** Width, Work|Timeline switch, buttons (opening the existing tabs for now), new section order,
   Advisor ideas level, For later with return times, section walk (server `section` parameter).
2. **Extract `TaskPage`** from `TasksView.jsx`. The Tasks tab renders it first — the proof nothing changed.
3. **The walk shows `TaskPage`.** Folding, one live card, Expand, agent sessions near full height, the relay in
   the assistant's context. The old walk cards are removed.
4. **Browse pattern** — Connections, then Settings, then Reports, then Hub; sidebar buttons switch from tabs to cards.
5. **Remove the tabs**; deep links open canvas cards.
6. **Phone** — the doorway's sections, return times, task-view text and agent relay; the web drawer layout.

## Testing

- Full Python and frontend suites green at every step; `npm run lint:undef` clean.
- Step 2: the existing Tasks-tab tests pass unchanged against `TaskPage`.
- Browser: walk a section by its heading; open a task; expand; Back from a connector detail; the two hard-requirement
  tests above.
- `website/ui_audit.mjs` at phone and desktop widths after steps 1, 3 and 5.
- Replay the walk against a live-DB snapshot after step 3 (the pile path's timing must not regress).

## Out of scope

- A new chat brain, new operations, or a tool map of the routes (the 2026-09-18 spec's rule stands).
- Board's content (it stays as is, full screen).
- Redesigning the connector, settings or report editors themselves — they are shown as they are.
