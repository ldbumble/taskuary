// THE PLACES A SENTENCE SENDS THE OWNER, AND THE WORDS THEY NEVER SEE (taskuary/words.json, read by words.js here and words.py on the
// server): a sentence names a place through place(id), never a typed "Settings → ..." string, and the walk's WORDS rule reads the
// same jargon list the server's sentences are held to.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { GONE, JARGON, jargonIn, noun, place, placeName } from "../src/words.js";
import { canvasRequestFromHash } from "../src/canvasLinks.js";

const SRC = path.join(process.cwd(), "src");

test("every place has a name, and every link it gives opens on the canvas", () => {
  for (const id of ["ai", "mail", "sorting", "ai_defaults", "later", "voice", "rules", "docs"]) assert.ok(placeName(id), id);
  for (const id of ["ai", "mail", "sorting", "ai_defaults", "voice", "rules", "docs", "ai_apps"])
    assert.ok(canvasRequestFromHash(place(id).href), `${id}: ${place(id).href} is a link the canvas knows`);
  assert.equal(place("nowhere").href, "", "an unknown place is named as asked, with no link - never undefined");
});

test("jargon is matched as a word: 'repo' is caught, 'approve' is not 'PR', 'session' in any case", () => {
  assert.ok(JARGON.length > 5);
  assert.equal(jargonIn("pick a repo")?.[0], "repo");
  assert.equal(jargonIn("approve it and Proceed"), null);
  assert.ok(jargonIn("the Session ended"));
  assert.equal(jargonIn("sorted 1m ago"), null);
});

test("no page types a place of this app: the sentence asks words.place", () => {
  const typed = /["'`>][^"'`<]*(?:Settings → (?:How mail is sorted|Routing policies|Docs|AI defaults)|Connections → (?:AI|Email)|under For later on your rail)/;
  const hits = [];
  for (const f of fs.readdirSync(SRC).filter((f) => /\.(jsx?|mjs)$/.test(f) && !f.startsWith("demo"))) {
    const code = fs.readFileSync(path.join(SRC, f), "utf8").split("\n").filter((l) => !/^\s*(\/\/|\/\*|\*|\{\/\*)/.test(l));
    code.forEach((l, i) => { if (typed.test(l)) hits.push(`${f}:${i + 1}`); });
  }
  assert.deepEqual(hits, []);
});

// THE SURFACES THAT ARE GONE are named in no line the owner reads (2026-10-19 UI walk: copy still sent people to the Timeline, the
// Reports tab and the Assistant tab). Read in the strings and the JSX text of every page, comments left out - "Timeline" the component
// name is code, not a line
const stripComments = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1");
const linesOf = (s) => [...(s.match(/"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`/g) || []), ...(s.match(/>[^<>{}]+</g) || [])];
test("no page, demo or catalogue line names a surface that is gone", () => {
  const hits = [];
  const files = [...fs.readdirSync(SRC).filter((f) => /\.(jsx?|mjs)$/.test(f)).map((f) => path.join(SRC, f)),
    path.join(process.cwd(), "..", "taskuary", "connectorcatalog.json")];
  // ...a bare "Timeline" is a destination key the router still resolves (TaskHubPage go()), not a line
  for (const f of files) for (const l of linesOf(stripComments(fs.readFileSync(f, "utf8")))) if (l.slice(1, -1) !== "Timeline")
    for (const re of GONE.map((w) => new RegExp(`\\b${w}\\b`))) if (re.test(l)) hits.push(`${path.basename(f)}: ${l.slice(0, 90)}`);
  assert.deepEqual(hits, []);
  assert.ok(jargonIn("it lands on the Timeline"), "a gone surface is flagged with the jargon");
  assert.equal(jargonIn("the project timeline slipped"), null, "...matched as written, so the word itself is not");
});

// ONE NAME PER THING (2026-10-19 UI walk): the coding tools' card, its crumb and the hints that send you there say words.noun's name
test("the AI CLI agents are named by words.noun, never typed", () => {
  assert.equal(noun("cli_agents"), "AI CLI agents");
  assert.ok(placeName("ai_apps").endsWith(noun("cli_agents")), "the place and the noun say the same name");
  const typed = [];
  for (const f of fs.readdirSync(SRC).filter((f) => /\.jsx?$/.test(f) && !f.startsWith("demo")))
    for (const l of linesOf(stripComments(fs.readFileSync(path.join(SRC, f), "utf8")))) if (/AI CLI agents/.test(l)) typed.push(`${f}: ${l.slice(0, 80)}`);
  assert.deepEqual(typed, []);
});
