import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// SAVED SECRETS STAY HIDDEN ON EVERY CARD (the UI audit, 2026-10-21): the Gmail card's OAuth client secret and refresh token were
// drawn as plain boxes by the mail card's Credentials step - only the generic card masked a write-only key
const src = readFileSync(new URL("../src/ConnectorsView.jsx", import.meta.url), "utf8");


test("reusing the Gmail card's client reads a saved secret it is never sent, and clears its own by name", () => {
  assert.match(src, /ok: \(c\) => !!\(c && parse\(c\.ConfigJson\)\.google_client_id && savedOn\(c, "google_client_secret"\)\)/);
  assert.match(src, /if \(\(conn\.WriteOnlyKeys \|\| \[\]\)\.includes\(k\)\) next\[k\] = null; else delete next\[k\];/);
});
