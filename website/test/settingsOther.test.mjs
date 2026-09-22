// The "Other" tab is a catch-all: any row in the settings table without a KNOB_META entry lands
// there as an editable box. The settings table is ALSO where the app keeps its own bookkeeping -
// which CLI session a chat is on (concierge_cli_sid:<id>), where a per-task cursor got to
// (assistant_current:<id>), when a sweep last ran - so the tab filled with machine state you
// could type over: 185 of 249 rows on a real install, 162 of them per-entity ids and timestamps
// (the owner, 2026-09-16: "what is this? does not feel useful").
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const src = fs.readFileSync(path.join(process.cwd(), "src", "SettingsView.jsx"), "utf8");
// the knob table itself lives in taskuary/settings_schema.json now (one file for the page and the
// assistant, 2026-09-18); the tests about WHAT the knobs are read it from there
const SCHEMA = JSON.parse(fs.readFileSync(path.join(process.cwd(), "..", "taskuary", "settings_schema.json"), "utf8"));
const KNOBS = SCHEMA.knobs, PANEL_OWNED = SCHEMA.panel_owned;

test("per-entity state never renders as a knob", () => {
  assert.match(src, /const isState = \(name\) => name\.includes\(":"\)/,
    "a `name:<id>` key is state by construction - there are hundreds of them and they are not settings");
  const at = src.indexOf("const hidden = (name) =>");
  assert.notEqual(at, -1);
  assert.ok(src.slice(at, at + 220).includes("isState(name)"),
    "hidden() is the one filter both the tab list and the search use, so the rule belongs there");
});

test("the scalar bookkeeping keys are named, not guessed at", () => {
  // Deliberately a list, not a prefix rule: `assistant_notes` is state, `assistant_card` is a
  // real toggle, and no prefix tells them apart. Anything added here stops being offered as a
  // knob, so it has to be a decision somebody made rather than a pattern that swept it up.
  // The `_at` stamps left this list for a rule of their own - naming each new one as it appeared
  // is what let two of them through onto the page - and that rule is pinned below.
  for (const k of ["app_sessions", "assistant_last_run", "wall_rolled_on"]) {
    assert.ok(new RegExp(`"${k}"`).test(src.slice(src.indexOf("const STATE = new Set"), src.indexOf("const isState"))),
      `${k} is machine state and must not be offered as a setting`);
  }
  // `assistant_card` was in here as "a real toggle, not state" on the strength of it RENDERING
  // as a switch. It has no reader in any Python module or any browser file - it is dead, like
  // send_enabled and the rest, and the label was the only evidence for it. Assert the rule that
  // actually holds instead: a key in STATE is one nothing reads or one the app writes itself.
  const stateBlock = src.slice(src.indexOf("const STATE = new Set"), src.indexOf("const isState"));
  assert.ok(/"assistant_card"/.test(stateBlock) && /"counsel_enabled"/.test(stateBlock),
    "a knob with no reader is not offered, however much it looks like one");
});

test("a key the AI-defaults panel owns is suppressed in every section, not just its own", () => {
  // assistant_ai lost its KNOB_META entry when it became a card, so meta() defaulted it to the
  // "Other" group - where the old tab-scoped guard did not run, and it came back as a bare
  // unlabelled text box next to the machine state (d3bde8bd). The groups are sections on one
  // page now rather than tabs, and the rule is the same one: the filter never names a group.
  const at = src.indexOf("const rowsOf = (g) => settings.filter");
  assert.notEqual(at, -1);
  const filter = src.slice(at, at + 260);
  assert.ok(filter.includes("!(panelOk && PANEL_OWNED.has(s.Name))"),
    "the suppression must not be scoped to one section");
  assert.ok(!/=== "Triage & agents" && panelOk/.test(filter),
    "the old tab-scoped form is what let an owned key leak onto Other");
});

test("every panel-owned key still has a labelled fallback row", () => {
  // panelOk puts the plain rows back when the panel cannot load. A key with no schema entry falls
  // back to a box labelled with its own raw name, which is not a fallback. The list it walks is
  // the schema's now - see "nothing falls into Other" below for why it stopped being written here.
  for (const key of PANEL_OWNED) assert.ok(KNOBS[key], `${key} is hidden by the panel but has no schema entry`);
  assert.ok(PANEL_OWNED.length >= 8, "all five AI slots, their two model settings and the phone doorway");
});

test("one question gets one row: the three trust switches are a single control", () => {
  // Who may start a worker without you was three separate switches, so knowing the answer meant
  // reading all three (the owner, 2026-09-16: "combine trust own domain, sent history etc").
  const row = KNOBS.trust_own_domain;
  assert.ok(row, "the combined row exists");
  assert.equal(row.type, "flags", "it is one control over several boolean settings");
  for (const k of ["trust_own_domain", "trust_sent_history", "trust_non_email"]) {
    assert.ok(row.flags?.[k]?.label, `${k} must still be one of the pills`);
  }
  // no new key, no migration: senders.py keeps reading exactly what it read before
  assert.ok(!Object.keys(KNOBS).some((k) => /trust_sources|trust_csv/.test(k)), "combining the ROW must not invent a fourth setting");
  // ...and the two it now owns must not also appear as their own rows
  const state = src.slice(src.indexOf("const STATE = new Set"), src.indexOf("const isState"));
  for (const k of ["trust_sent_history", "trust_non_email"]) {
    assert.ok(state.includes(`"${k}"`), `${k} is drawn by the combined row, so it is not its own row`);
  }
});

test("every row the page offers is a knob somebody reads", () => {
  // The audit's own rule, kept honest: a key with no KNOB_META entry renders with its raw name
  // and no explanation, which is what the "Other" tab was. Nothing should reach it now.
  const keys = Object.keys(KNOBS);
  for (const dead of ["send_enabled", "outlook_drafts_enabled", "attach_threshold", "backup_agents",
                      "assistant_card", "counsel_enabled"]) {
    assert.ok(!keys.includes(dead), `${dead} has no reader - it must not be offered as a setting`);
  }
  for (const real of ["default_brain", "backup_brains", "profile_brains"]) {
    assert.ok(keys.includes(real), `${real} is read by agents.py and needs a row that explains it`);
  }
});

// ── a quiet assistant post promises only what it renders ─────────────────────────────────
test("the quiet post does not point at a block it has not got", () => {
  const feed = fs.readFileSync(path.join(process.cwd(), "src", "FeedView.jsx"), "utf8");
  const at = feed.indexOf("Nothing worth saying this time");
  assert.notEqual(at, -1);
  const line = feed.slice(at - 60, at + 220);
  assert.ok(/\{rv \? " What it read is below\." : ""\}/.test(line),
    "the promise must be conditional on the `what it reviewed` block actually being there");
});

test("an assistant post shows what the assistant said, even with no structured ideas", () => {
  // Every line of the post is drawn from brief.ideas, so a post whose brief did not reach the
  // page rendered empty - while the sentence it actually wrote sat unused in sel.Preview.
  const feed = fs.readFileSync(path.join(process.cwd(), "src", "FeedView.jsx"), "utf8");
  const at = feed.indexOf("THE ASSISTANT'S OWN WORDS");
  assert.notEqual(at, -1, "the fallback must be there and say why");
  const block = feed.slice(at, at + 1100);
  assert.ok(/\{!ideas\.length && cleanText\(sel\.Preview\) &&/.test(block),
    "with no ideas but a body, the body is what the post shows");
  assert.ok(/\{!ideas\.length && !cleanText\(sel\.Preview\) &&/.test(block),
    "the 'nothing worth saying' line is only for a post that truly said nothing");
});


// ── the browser pane says when there is nothing to show ──────────────────────────────────
test("a browser with no page open says so instead of painting black", () => {
  // agent-browser answers its screencast port the moment the daemon launches, page or no page.
  // browserview.state() calls that "open", the relay connects, and the daemon's first and only
  // message is {"connected": false, "screencasting": false} - measured on a live session: one
  // status message, zero frames. The pane dropped `status` on the floor and drew an empty canvas,
  // so a browser nobody had navigated looked exactly like a broken one (the owner, 2026-09-16).
  const pane = fs.readFileSync(path.join(process.cwd(), "src", "BrowserPane.jsx"), "utf8");
  assert.match(pane, /m\.type === "status"\) setAttached\(m\.connected !== false\)/,
    "the stream's own status is the answer - it must not be ignored");
  assert.match(pane, /attached === false && !live &&/,
    "say it only before the first frame: mid-navigation is not an empty pane");
  assert.ok(pane.includes("the browser is running, with no page open"),
    "and say which of the two it is, in words");
});

// ...and a browser that IS streaming, on about:blank, says that too. A needs:browser session starts
// on an empty tab, which painted as a white rectangle labelled LIVE (the 2026-09-18 pane pass).
test("a live browser on an empty tab says it is an empty tab", () => {
  const pane = fs.readFileSync(path.join(process.cwd(), "src", "BrowserPane.jsx"), "utf8");
  assert.match(pane, /live && \(!url \|\| url === "about:blank"\) &&/, "only while live and blank");
  assert.ok(pane.includes("an empty tab, live"));
  assert.match(pane, /pointerEvents: "none"/, "the note must not swallow a take-over click");
});

// EVERY SETTINGS PAGE IS THE SAME WIDTH, AND THE RAIL IS WHY. Pages used to cap themselves inside
// their own component (Updates at 720, About you at 860); then each page declared its own width in
// a table, which read better per page and moved the rail: the block is centred, so a page that
// wanted 1300 pushed the menu left of where the page before it had drawn it, and you watched the
// thing you had just clicked slide away (the owner, 2026-09-18: "keep it the same as above").
test("every settings page is one width, so the rail never moves", () => {
  // The guarantee is THE RAIL NEVER MOVES; the mechanism changed and the guarantee did not. It
  // used to be a single 980 cap on every page (a per-page width had slid the rail). Settings is
  // full width now, and the rail is the grid's fixed first column, which cannot slide whatever
  // the page beside it does (the owner, 2026-09-22: "setting layout is full width").
  assert.doesNotMatch(src, /PAGE_WIDTH/, "the per-page table is gone");
  assert.doesNotMatch(src, /^const PAGE = \d+;$/m, "and so is the single cap that replaced it");
  assert.match(src, /gridTemplateColumns: \{ xs: "minmax\(0, 1fr\)", md: `\$\{RAIL\}px minmax\(0,1fr\)` \}/,
    "the rail is a FIXED first column - that is what pins it now");
  assert.match(src, /maxWidth: "none"/, "and the page takes the rest of the window");
  assert.match(src, /gap: 3, alignItems: "start", mx: "auto"/, "the grid itself is unchanged");
  assert.doesNotMatch(src, /minWidth: 0, maxWidth: \(!q &&/,
    "the page must not be capped inside a column that is wider than it - that is the void");
  // the width cannot depend on which page is showing, or the rail drifts again by another route
  assert.doesNotMatch(src, /const width = /, "no per-page width is computed at render");
  for (const name of ["UpdateCard.jsx", "AboutYou.jsx"]) {
    const page = fs.readFileSync(path.join(process.cwd(), "src", name), "utf8");
    const open = page.indexOf("return (");
    assert.doesNotMatch(page.slice(open, open + 200), /maxWidth: \d+/,
      `${name} must not cap its own root - PAGE is the one place a width is set`);
  }
});

// "Other" is the group a key with no schema entry falls into, and the page only draws a group that
// has something in it - so on a healthy install it never appears at all. It appeared: three keys
// had fallen through, two stamps and one REAL setting (`judge_ai`, the fifth AI-defaults slot),
// which meant the one place you would never look for it (the owner, 2026-09-18: "what is the other
// settings in configuration"). Both leaks get a rule rather than another name on a hand-written list.
test("nothing falls into Other: a stamp is state, and a card's key is the card's", () => {
  assert.match(src, /const isState = \(name\) => name\.includes\(":"\) \|\| name\.endsWith\("_at"\) \|\| STATE\.has\(name\);/,
    "a key ending _at is when the app last did something, never a knob");
  assert.ok(Object.keys(KNOBS).every((k) => !k.endsWith("_at")),
    "...which is only safe while no real knob is named that way");
  assert.match(src, /const PANEL_OWNED = new Set\(schema\.panel_owned\);/,
    "the panel's keys come from the schema - the hand-written set is what missed judge_ai");
  for (const key of PANEL_OWNED) {
    assert.ok(KNOBS[key], `${key} is hidden by a card but has no schema entry to fall back to`);
  }
  assert.ok(PANEL_OWNED.includes("judge_ai"), "the slot that leaked is covered by the rule that replaced the list");
});
