// THE SETUP SWEEP (2026-10-28): setup, Connections, Settings and Reports read as a first-time owner, the approved fixes pinned here.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const cv = src("ConnectorsView.jsx");


test("the steps after Credentials are not ticked before it is", () => {
  assert.match(cv, /const creds = credsDone\(conn, cfg, m\);/);
  assert.match(cv, /label: "Inbound — what becomes work", done: creds && inboundDone\(conn, mine\)/);
  assert.match(cv, /label: "More roles — reports, agents", done: creds,/);
});
