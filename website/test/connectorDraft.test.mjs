// EVERY FIELD ON A CONNECTION CARD SAVES ITSELF (the owner, 2026-11-05: "what saves with one click while other hit the save buttons.
// it's just confusing"). The rules in connectorDraft.js - the draft holds only what changed and saves it as a patch (#242) - and a
// guard that no card carries a Save button or a Save bar any more.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { applied, cfgPatch, changes, patched, prune, saveBody, stage, stageable, tickWords } from "../src/connectorDraft.js";

const conn = { ConnectorId: 3, Active: 1, Roles: "trigger", Scope: "read", ConfigJson: JSON.stringify({ bulk: "clear", reply_comments: false }) };
const src = readFileSync(new URL("../src/ConnectorsView.jsx", import.meta.url), "utf8");
const draft = readFileSync(new URL("../src/ConnectorDraft.jsx", import.meta.url), "utf8");

test("a control's settings post is held; an action is not", () => {
  assert.equal(stageable({ ConnectorId: 3, ConfigJson: "{}" }, "ConnectorId"), true);
  assert.equal(stageable({ ConnectorId: 3, Active: false, Roles: "feed" }, "ConnectorId"), true);
  assert.equal(stageable({ Type: "github", Name: "x" }, "ConnectorId"), false);          // creating one
  assert.equal(stageable({ Channel: "github", Address: "org/app" }, "SourceId"), false);  // adding a source
});

test("a patch is the keys that changed, and a key gone is null", () => {
  assert.deepEqual(cfgPatch({ a: 1, b: 2, c: 3 }, { a: 1, b: 5 }), { b: 5, c: null });
  assert.deepEqual(patched({ a: 1, c: 3 }, { b: 5, c: null }), { a: 1, b: 5 });
  assert.deepEqual(cfgPatch({ x: [1] }, { x: [1] }), {});
});

test("the draft is what the controls changed, laid over what is saved", () => {
  let want = stage(null, { ConnectorId: 3, ConfigJson: JSON.stringify({ bulk: "rank", reply_comments: false }) }, conn);
  // the next control builds on the draft it was drawn from, so it carries the first change too
  want = stage(want, { ConnectorId: 3, ConfigJson: JSON.stringify({ ...JSON.parse(applied(conn, want).ConfigJson), bulk_head: 6 }) }, conn);
  want = stage(want, { ConnectorId: 3, Roles: "trigger,feed" }, conn);
  assert.deepEqual(want.cfg, { bulk: "rank", bulk_head: 6 }, "only the keys changed, never the whole config");
  const d = applied(conn, want);
  assert.deepEqual(JSON.parse(d.ConfigJson), { bulk: "rank", reply_comments: false, bulk_head: 6 });
  assert.equal(d.Roles, "trigger,feed");
  assert.deepEqual(changes(conn, want).map((c) => `${c.key}:${c.from}->${c.to}`),
    ["Roles:trigger->feed,trigger", "bulk:clear->rank", "bulk_head:undefined->6"]);
});

test("a save posts only what changed: the fields, and the config keys as a patch - so a poller's watermark is never sent back (#242)", () => {
  const polled = { ...conn, ConfigJson: JSON.stringify({ bulk: "clear", reply_comments: false, tg_offset: 41 }) };
  const want = stage(null, { ConnectorId: 3, Scope: "write", ConfigJson: JSON.stringify({ bulk: "rank", reply_comments: false, tg_offset: 41 }) }, polled);
  // ...the poller moves on before the save goes: the patch does not carry its key at all
  const later = { ...polled, ConfigJson: JSON.stringify({ bulk: "clear", reply_comments: false, tg_offset: 57 }) };
  assert.deepEqual(saveBody(later, want, "ConnectorId"), { ConnectorId: 3, Scope: "write", ConfigPatch: { bulk: "rank" } });
});

test("changing a setting back to what is saved leaves nothing to post", () => {
  const want = stage(stage(null, { ConnectorId: 3, Active: false }, conn), { ConnectorId: 3, Active: true }, conn);
  assert.deepEqual(changes(conn, want), []);
  assert.equal(saveBody(conn, want, "ConnectorId"), null);
});

test("what the server now holds drops out of the draft; what it does not stays", () => {
  const want = stage(null, { ConnectorId: 3, Roles: "feed", ConfigJson: JSON.stringify({ bulk: "rank", reply_comments: true }) }, conn);
  const back = { ...conn, Roles: "feed", ConfigJson: JSON.stringify({ bulk: "rank", reply_comments: false }) };
  assert.deepEqual(prune(back, want), { cfg: { reply_comments: true } });
  assert.equal(prune({ ...back, ConfigJson: JSON.stringify({ bulk: "rank", reply_comments: true }) }, want), null);
});

test("the tick says Saved, or Not saved and why", () => {
  assert.equal(tickWords({ state: "saved" }), "Saved");
  assert.equal(tickWords({ state: "error", why: "a imap connector named 'Work mail' already exists" }), "Not saved - a imap connector named 'Work mail' already exists");
  assert.equal(tickWords({ state: "saving" }), "");
  assert.equal(tickWords(null), "");
});

test("no Save button and no Save bar on any connection card: each field saves itself", () => {
  assert.doesNotMatch(src, /"Save & continue"|"Save name"|<SaveBar|>Save<|: "Save"\}/);
  assert.doesNotMatch(draft, /export function SaveBar/);
  // every connector post left beside an id is the name's own save or a reuse that patches; a source setting is never posted whole
  const posts = src.match(/api\.post\("\/api\/connectors", \{ ConnectorId: conn\.ConnectorId,.*$/gm) || [];
  assert.ok(posts.length && posts.every((p) => /Name: value|ConfigPatch: cfgPatch\(cfg, next\)/.test(p)), posts.join("\n"));
  assert.ok(!/api\.post\("\/api\/sources", \{ SourceId/.test(src), "a source setting posted by itself");
  // the draft saves itself: typing once it pauses, a pick at once, and what was waiting when the card is left
  assert.match(draft, /later\(typing\(\) \? TYPE_MS : PICK_MS\)/);
  assert.match(draft, /useEffect\(\(\) => \(\) => \{ if \(timer\.current\) save\(\); \}, \[save\]\);/);
  assert.match(draft, /ConfigPatch: patch/);
  // ...and says so by the open step's name, or by the switch
  assert.match(src, /<StepButton onClick=\{\(\) => setStep\(i\)\}>\{s\.label\}\{i === step && <Tick st=\{draft\.st\} \/>\}<\/StepButton>/);
});

test("a card's boxes save themselves: the typing on its pause, a secret when its box is left, each with its own tick", () => {
  for (const part of ["need", "maybe", "late"])
    assert.match(src, new RegExp(`\\{${part}\\.map\\(\\(f\\) => <ConfigField [^\\n]*tick=\\{boxes\\.tick\\(f\\[1\\]\\)\\} onBlur=\\{boxes\\.flush\\} />\\)\\}`), part);
  assert.equal((src.match(/InputProps=\{\{ endAdornment: boxes\.tick\("Secret"\) \}\}/g) || []).length, 2, "the mail card's key and the generic card's");
  assert.match(draft, /if \(!all\) wo\.forEach\(\(k\) => delete patch\[k\]\);/, "a write-only key waits for its box to be left");
  assert.match(draft, /const keys = Object\.keys\(patch\), withSecret = all && !!s;/, "...and so does the secret");
  // the first run's simple card keeps its one Connect
  assert.match(src, /useBoxesSave\(\{ off: simple,/);
});
