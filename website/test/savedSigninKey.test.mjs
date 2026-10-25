import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// the owner, 2026-10-25: "Yes: TOTP codes in the sign-in vault". A saved sign-in's row keeps its authenticator key - write-only: the
// row says one is kept, the key goes out once to the owner-only route, and nothing ever reads it back
test("a saved sign-in's row keeps or drops its authenticator key, and never shows it", () => {
  const ss = read("SavedSignins.jsx");
  assert.match(ss, /api\.post\(`\/api\/signins\/\$\{encodeURIComponent\(site\)\}\/code`, \{ key: value \}\)/);
  assert.match(ss, /\{r\.code \? "Remove authenticator key" : "Add authenticator key"\}/);
  assert.match(ss, /\{r\.code \? " · authenticator code" : ""\}/, "the row says one is kept");
  assert.match(ss, /<TextField size="small" type="password" autoComplete="off"/, "typed as a secret, never autofilled");
  assert.match(ss, /error=\{!!keyErr\} helperText=\{keyErr \|\| " "\}/, "a mistyped key is said under its box");
  assert.doesNotMatch(ss, /api\.get\(`\/api\/signins\/[^`]*\/code`/, "no read of a key");
  // Remove still says Removing… only for a removal, not while a key saves
  assert.match(ss, /busy === r\.site && what === "remove" \? "Removing…" : "Remove"/);
});
