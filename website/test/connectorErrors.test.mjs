// The 2026-10-19 UI walk, on the connector cards: a GitHub token refused on Save printed "401 Client Error: Unauthorized for url:
// https://api.github.com/user" into the Test step - folded shut under the Save just pressed - Slack's card said "invalid_auth", and
// Credentials was ticked over the key the service had just turned down. The words are the server's (channels.plain_failure,
// LastErrorPlain - tests/test_plain_failures.py); this pins where the card draws them and when it ticks.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../src/ConnectorsView.jsx", import.meta.url), "utf8");

test("a card's red line is the plain words, never the raw LastError", () => {
  assert.doesNotMatch(src, /✗ \{conn\.LastError\}/, "every red line reads LastErrorPlain first");
  assert.equal((src.match(/✗ \{conn\.LastErrorPlain \|\| conn\.LastError\}/g) || []).length >= 5, true);
});

test("what Save says is drawn under Save, and a refused key does not move on", () => {
  const at = src.indexOf("const saveCreds = async");
  const save = src.slice(at, src.indexOf("const runTest", at));
  assert.match(save, /if \(d\?\.error\) setSaveSaid\(\{ ok: false, detail: d\.error \}\)/);
  assert.doesNotMatch(save, /setTest\(\{ ok: false/, "a save's failure is not written into the Test step");
  assert.match(save, /plainError\(e,/, "a refused save says the server's sentence, or a plain one");
  assert.match(src, /"Save & continue"\}<\/Button>\s*\{msg && [^\n]*\n\s*<\/Box>\s*<TestLine test=\{saveSaid\} mt=\{0\} \/>/, "right under the button");
});

test("Credentials is ticked only after a Test passed on them", () => {
  assert.match(src, /const creds = credsDone\(conn, cfg, m\);/);
  assert.match(src, /label: "Credentials", done: creds,/);
  assert.match(src, /: !m\.secretLabel \|\| \(!!conn\.HasSecret && !!conn\.LastSyncAt && !conn\.LastError\);/);
});

// ...and a card with no key is ticked by its own proof, not by having none (the UX walk, 2026-10-22)
test("ChatGPT ticks Credentials once signed in, WhatsApp once a read went through the pairing", () => {
  const body = src.match(/const credsDone = (\(conn, cfg, m\) => [\s\S]*?);\n/)[1];
  const credsDone = new Function(`return ${body}`)();
  const none = { secretLabel: null }, read = { LastSyncAt: "2026-10-22 09:00", LastError: null };
  assert.equal(credsDone({ Type: "chatgpt" }, {}, none), false);
  assert.equal(credsDone({ Type: "chatgpt", HasSecret: true }, { auth: "user" }, none), true);
  assert.equal(credsDone({ Type: "whatsapp" }, {}, none), false);
  assert.equal(credsDone({ Type: "whatsapp", ...read, LastError: "not paired" }, {}, none), false);
  assert.equal(credsDone({ Type: "whatsapp", ...read }, {}, none), true);
  assert.equal(credsDone({ Type: "slack" }, {}, { secretLabel: "Bot token" }), false);
  assert.equal(credsDone({ Type: "slack", HasSecret: true, ...read }, {}, { secretLabel: "Bot token" }), true);
});
