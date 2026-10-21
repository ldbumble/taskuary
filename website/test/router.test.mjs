// ONE ROUTER (the 2026-10-19 UI walk, G2): every link names a place with its target, the canvas writes where the owner is back into
// the address, and only appLinks.js writes it. The browser half - a link over an open page, Back after two opens, the address after
// Next - is deadend_check.mjs's PLACE, BACK and ADDRESS.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { canvasRequestFromHash, hashFor, placeOf } from "../src/canvasLinks.js";
import { ownerHref, recordPlace, onPlace } from "../src/appLinks.js";
import { PLACES } from "../src/words.js";

const src = (p) => fs.readFileSync(new URL(p, import.meta.url), "utf8");

test("a link carries its target, so a page already open can open it", () => {
  assert.deepEqual(canvasRequestFromHash("#connector=github").state, { section: null, open: null, connector: "github" });
  assert.deepEqual(canvasRequestFromHash("#connector=12").state, { section: null, open: null, connector: "12" });
  assert.deepEqual(canvasRequestFromHash("#cli-agents").state, { section: null, open: null, connector: "cli-agents" });
  assert.deepEqual(canvasRequestFromHash("#connector=").state, { section: null, open: null }, "no target: the landing, said as the landing");
  assert.equal(canvasRequestFromHash("#settings=config&group=Assistant&key=kb_semantic").state.knob, "kb_semantic");
});

test("every place words.json names is a place the canvas opens", () => {
  for (const [id, p] of Object.entries(PLACES)) {
    if (!p.href || p.href === "#setup") continue;           // setup is a mode, not a page; '' is a place with no address
    assert.ok(canvasRequestFromHash(p.href), `${id}: ${p.href} opens nothing`);
    assert.ok(placeOf(p.href), `${id}: ${p.href} names no place`);
  }
  // the AI section and the CLI page are their target, not the bare Connections landing ("Check the AI connection", 2026-10-19)
  assert.equal(canvasRequestFromHash(PLACES.ai.href).state.section, "AI — agents & models");
  assert.equal(canvasRequestFromHash(PLACES.ai_apps.href).state.connector, "cli-agents");
});

test("where a setting is saved opens that card - never the Profiles shelf", () => {
  // every owner_link the server writes (aidefaults.py): a place id, or one connector
  const links = [...src("../../taskuary/aidefaults.py").matchAll(/owner_link=(?:'([^']*)'|f"connector:)/g)].map((m) => m[1] ?? "connector:7");
  assert.ok(links.includes("ai_apps") && links.includes("connector:7"), JSON.stringify(links));
  for (const l of links.filter(Boolean)) {
    const req = canvasRequestFromHash(ownerHref(l));
    assert.equal(req?.area, "connections", `${l} -> ${ownerHref(l)}`);
    assert.ok(req.state.connector, `${l} names no card`);
  }
  // ...and every place the panel names in its own words: its "still Connections" was onGo("connectors"), a place words.json does not
  // have, so ownerHref gave "" and the click did nothing (verify, 2026-10-19)
  const named = [...src("../src/AiDefaults.jsx").matchAll(/onGo\("([^"]*)"\)/g)].map((m) => m[1]);
  assert.ok(named.length, "the panel names no place of its own any more - this check reads nothing");
  for (const l of named) assert.ok(canvasRequestFromHash(ownerHref(l)), `AiDefaults' onGo("${l}") -> "${ownerHref(l)}" opens nothing`);
  assert.equal(ownerHref("connector:7"), "#connector=7");
  assert.equal(ownerHref(""), "");
});

test("the address of a place reads back as the same place", () => {
  const places = [
    ["connections", {}], ["connections", { section: "Email", open: null }], ["connections", { section: "Email", open: "c3", connector: "3" }],
    ["connections", { connector: "cli-agents" }], ["settings", { section: null }], ["settings", { section: "config", open: null }],
    ["settings", { section: "config", open: "Sync & startup", knob: "poll_minutes" }], ["settings", { section: "policies", open: "policies" }],
    ["settings", { section: "docs", open: "d:learned", view: "changes" }], ["settings", { section: "profiles", open: null }],
    ["reports", { section: "reports", open: 17 }], ["reports", { section: "reports", open: "new-report" }], ["reports", { section: "workflows", open: null }],
    ["reports", { section: "workflows", open: "new-agent" }], ["reports", { section: "playbooks", open: null }],
    ["reports", { section: "playbooks", open: "pb:weekly-close" }], ["hub", {}], ["new", {}],
  ];
  for (const [area, state] of places) {
    const h = hashFor(area, state), req = canvasRequestFromHash(h);
    assert.ok(req, `${area} ${JSON.stringify(state)} -> ${h} opens nothing`);
    assert.equal(req.kind === "new" ? "new" : req.area, area, h);
    assert.equal(placeOf(h), h, `${h} is not its own place`);
  }
  // two spellings of one place are one place; a run's Fix is an act, never a step Back asks again
  assert.equal(placeOf("#connector="), placeOf("#connections"));
  assert.equal(placeOf("#playbook=weekly-close"), "#playbook=weekly-close");
  assert.equal(placeOf("#settings=playbooks"), "#report=playbooks");
  assert.equal(placeOf("#report=17&fix=9"), "#report=17");
  // a message link is a place until the canvas writes the table's own address over it (a reload then lands on that table)
  assert.equal(placeOf("#msg=4"), "#msg=4");
  assert.equal(placeOf("#message=4"), "#msg=4", "two spellings of one message are one place");
});

// a window with a history: what recordPlace wrote, and what onPlace heard
const fakeWindow = (hash = "") => {
  const steps = [], on = {};
  const w = { location: { pathname: "/", search: "?k=x", hash }, history: { state: null,
    pushState: (_, __, u) => { steps.push(["push", u]); w.location.hash = u.includes("#") ? u.slice(u.indexOf("#")) : ""; },
    replaceState: (_, __, u) => { steps.push(["replace", u]); w.location.hash = u.includes("#") ? u.slice(u.indexOf("#")) : ""; } },
  addEventListener: (t, f) => { on[t] = f; }, removeEventListener: (t) => { delete on[t]; } };
  return { w, steps, on };
};

test("the canvas writes where the owner is: a step for a new place, nothing for the same one", () => {
  const { w, steps } = fakeWindow("#task=11");
  globalThis.window = w;
  try {
    recordPlace("#task=11", "push");                         // the same place: no step
    recordPlace("#connector=3", "push");                     // somewhere new: a step Back returns from
    recordPlace("#connector=3", "replace");
    recordPlace("#task=12", "replace");                      // the walk's Next: the address follows, no step
    recordPlace("", "replace");                              // an item with no task: the address names none, the sign-in key stays
    assert.deepEqual(steps, [["push", "/?k=x#connector=3"], ["replace", "/?k=x#task=12"], ["replace", "/?k=x"]]);
  } finally { delete globalThis.window; }
});

test("a step of history is heard once, and only Back asks for the address with no place", async () => {
  const { w, on } = fakeWindow("#connector=3");
  globalThis.window = w;
  const heard = [];
  try {
    const off = onPlace((h, back) => heard.push([h, back]));
    on.popstate({ type: "popstate" }); on.hashchange({ type: "hashchange" });   // one Back fires both
    await new Promise((r) => setTimeout(r, 5));
    w.location.hash = "";
    on.popstate({ type: "popstate" });
    off();
    assert.deepEqual(heard, [["#connector=3", true], ["", true]]);
    assert.equal(Object.keys(on).length, 0);
  } finally { delete globalThis.window; }
});

// the one writer: a hash set anywhere else is a link the router never hears as the owner's, and a page reading the address on mount
// is the bug this replaced (ConnectorsView read #connector= once, when its list loaded)
test("only appLinks.js writes the address", () => {
  const dir = new URL("../src/", import.meta.url);
  const files = fs.readdirSync(dir).filter((f) => /\.(jsx?|mjs)$/.test(f) && f !== "appLinks.js");
  const writers = files.filter((f) => /location\.hash\s*=[^=]/.test(fs.readFileSync(new URL(f, dir), "utf8")));
  assert.deepEqual(writers, [], `set the address through openAppLink: ${writers.join(", ")}`);
  assert.doesNotMatch(src("../src/ConnectorsView.jsx"), /location\.hash/, "Connections is handed its card in the browse state");
  assert.doesNotMatch(src("../src/SettingsView.jsx"), /goFromPanel = \(where\) => \{[\s\S]{0,200}profiles/, "the panel's own map is gone");
});
