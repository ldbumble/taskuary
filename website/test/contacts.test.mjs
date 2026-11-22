// ONE READ OF EVERYONE PER MINUTE (the overnight walk, 2026-10-26): a draft's To and Cc rows each read /api/people, and every press of
// Next that drew a draft asked for the whole list twice. readContacts is the real function; the pickers' wiring is read from the source.
import test from "node:test";
import assert from "node:assert/strict";

import { CONTACTS_MS, forgetContacts, readContacts } from "../src/contacts.js";


test("pickers drawn together share one read; a minute later, or after a failure, it is read again", async () => {
  forgetContacts();
  let n = 0, fail = false;
  const get = async () => { n++; if (fail) throw new Error("offline"); return { data: { data: [{ Email: "erin@northwind.example" }] } }; };
  const [a, b] = await Promise.all([readContacts(get, 1000), readContacts(get, 1500)]);
  assert.equal(n, 1); assert.deepEqual(a, b);
  await readContacts(get, 1000 + CONTACTS_MS + 1); assert.equal(n, 2);
  forgetContacts(); fail = true;
  await assert.rejects(readContacts(get, 5000)); fail = false;
  assert.equal((await readContacts(get, 5001)).length, 1); assert.equal(n, 4);
});
