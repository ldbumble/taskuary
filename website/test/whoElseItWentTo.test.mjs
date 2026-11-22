// WHOM A MAIL WENT TO, on Came from (the owner, 2026-11-03: "there are 2 people on this email (though you don't see recipients of the email
// in came from) and the other person will take care of it"): a plain line under the sender, no new button.
import test from "node:test";
import assert from "node:assert/strict";

import { fromStatus } from "../src/taskLayout.js";


test("the folded Came from tab carries it under its first line, and leaves it out when there is none", () => {
  assert.deepEqual(fromStatus({ channel: "Email", count: 1, to: "to you, Gail Moreno", msgs: [{ who: "Paula Vance", words: "Kindly adjust my role" }] }).lines,
    ["Email · 1 message", "to you, Gail Moreno", "Paula Vance: “Kindly adjust my role”"]);
  assert.deepEqual(fromStatus({ channel: "Email", count: 1 }).lines, ["Email · 1 message"]);
});
