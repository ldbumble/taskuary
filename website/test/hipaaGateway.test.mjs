// The HIPAA AI card asked only for the access code, and this build ships no gateway address - so Connect could never work, and
// said the key was wrong (the owner, 2026-10-20: "you forgot the field to put in the url"). The card asks for the address too.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { needsGateway } from "../src/aiShelf.js";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const cv = src("ConnectorsView.jsx");

test("the card asks for the gateway address above the access code, with where it comes from", () => {
  const card = cv.slice(cv.indexOf("  hipaa_ai: {"), cv.indexOf("  groq: {"));
  assert.match(card, /fields: \[\["Gateway address", "base_url", "https:\/\/", GATEWAY_HINT\]\], secretLabel: "Access code"/);
  assert.match(cv, /const GATEWAY_HINT = "Paste the address you were sent with your access code\.";/);
});

test("setup's simple card keeps the address field for this card alone, and shows its hint", () => {
  assert.match(cv, /k !== "base_url" \|\| conn\.Type === "hipaa_ai"/);
  assert.match(cv, /\.map\(\(\[label, key, ph, helper\]\) => \(\s*<TextField key=\{key\} size="small"[^>]*helperText=\{helper\}/);
  assert.match(cv, /const ready = isAI \? \(keyless \? !!\(cfg\.model \|\| ""\)\.trim\(\) : !!secret\.trim\(\)\) && !needsGateway\(conn, cfg\)/);
});

test("Connect waits for an address only when the build ships none", () => {
  const card = { Type: "hipaa_ai", GatewayBuiltIn: false };
  assert.equal(needsGateway(card, {}), true);
  assert.equal(needsGateway(card, { base_url: "   " }), true);
  assert.equal(needsGateway(card, { base_url: "https://ai.northwind.example" }), false);
  assert.equal(needsGateway({ ...card, GatewayBuiltIn: true }, {}), false);
  assert.equal(needsGateway({ Type: "groq" }, {}), false);
});

test("the card wears Taskuary's own mark, not the shared AI sparkle", () => {
  assert.match(src("logos.jsx"), /LOGOS\.hipaa_ai = \(\{ sx \}\) => \(\s*<img src=\{`\$\{import\.meta\.env\?\.BASE_URL \?\? "\/"\}favicon\.png\?v=4`\}/);
  assert.match(src("ui.jsx"), /favicon\.png\?v=4/, "the same file TaskuaryMark draws");
});
