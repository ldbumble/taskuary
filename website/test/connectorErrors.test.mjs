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

test("what a save says is drawn by the boxes, and a refused key does not move on", () => {
  const at = src.indexOf("const boxes = useBoxesSave({ off: simple");
  const save = src.slice(at, src.indexOf("const [fresh, setFresh]", at));
  assert.match(save, /setSaveSaid\(d\?\.error \? \{ ok: false, detail: d\.error \} : null\)/);
  assert.doesNotMatch(save, /setTest\(\{ ok: false/, "a save's failure is not written into the Test step");
  // a box's own pause never moves the card on a step; the key saved opens Test, unless the service refused it (the owner, 2026-11-05)
  assert.equal((save.match(/setStep\(/g) || []).length, 1);
  assert.match(save, /if \(keys\.includes\("Secret"\) && !d\?\.error\) setStep\(1\);/);
  // a refused save says the server's sentence, or a plain one, in the box's own tick (connectorDraft.whyNot)
  assert.match(readFileSync(new URL("../src/connectorDraft.js", import.meta.url), "utf8"), /export const whyNot = \(e\) => String\(e\?\.response\?\.data\?\.detail/);
  assert.match(src, /onBlur=\{boxes\.flush\} \/>\)\}<\/Box><\/Collapse>\s*<\/>\}\s*<TestLine test=\{saveSaid\} mt=\{0\} \/>/, "right under the boxes");
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
