import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { SIGN_LABEL, signState } from "../src/videoSignIn.js";

// a video tool card's Sign in (videotools.sign_in): one press, then "Signed in" once every CLI that has the server says so
const url = "https://mcp.vendor.example/mcp", cli = (added, signed_in = false, signing_in = false) => ({ here: true, added, signed_in, signing_in });

test("the button follows what each CLI that has the server says", () => {
  assert.equal(signState({ url, clis: { claude: cli(false), codex: cli(false) } }), "");           // nothing added: no button
  assert.equal(signState({ url, clis: { claude: cli(true), codex: cli(false) } }), "out");
  assert.equal(signState({ url, clis: { claude: cli(true, false, true), codex: cli(true, true) } }), "signing");
  assert.equal(signState({ url, clis: { claude: cli(true, true), codex: cli(false) } }), "in");
  assert.equal(signState({ skill: { name: "video-use" } }), "");                                     // a skill alone signs in nowhere
  assert.equal(signState({ url, demo: true }), "demo");
  assert.deepEqual([SIGN_LABEL.out, SIGN_LABEL.in], ["Sign in", "Signed in"]);
});

test("the card presses the sign-in road and asks again while the browser page is open", () => {
  const src = readFileSync(new URL("../src/ConnectorsView.jsx", import.meta.url), "utf8");
  assert.match(src, /press\("\/sign-in"/);
  assert.match(src, /if \(sign !== "signing"\) return undefined; const h = setInterval\(look/);
  assert.match(src, /This is the demo - nothing signs in here\./);
});
