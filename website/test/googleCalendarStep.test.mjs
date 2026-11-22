// SIGN IN WITH GOOGLE on the Gmail card (the owner, 2026-11-15: mail and calendar through Google's own sign-in, beside the App Password):
// one box at the top of the card - it opens Google, finishes by itself - on the install's OWN Google client, as Microsoft: a card
// without one lists the steps to make it and holds its two boxes. Never a button that says it cannot.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const src = (f) => fs.readFileSync(path.join(import.meta.dirname, "../src", f), "utf8");


test("a Gmail card signed in with Google ticks Credentials without an App Password", () => {
  assert.match(src("ConnectorsView.jsx"), /\(!!conn\.HasSecret \|\| \(conn\.Type === "gmail" && savedOn\(conn, "google_refresh_token"\)\)\) && !!conn\.LastSyncAt && !conn\.LastError\)/);
});
