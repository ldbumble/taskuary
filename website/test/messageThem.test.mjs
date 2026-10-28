// MESSAGE THEM (the owner's idea, trust audit F6, 2026-10-28): a People hit in Ctrl K offers the channels New's Send something can reach that
// person on, and the pick opens New's compose already addressed - the same sheet, the same road to a task. Invented Northwind people only.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { channelsFor, messageLink } from "../src/searchHits.js";
import { canvasRequestFromHash } from "../src/canvasLinks.js";

const src = (f) => fs.readFileSync(path.join(process.cwd(), "src", f), "utf8");
const TARGETS = [{ channel: "email", to: [] }, { channel: "teams", to: [{ to: "19:erin-chat", name: "Erin Blake" }] },
  { channel: "whatsapp", to: [{ to: "15550100@s.whatsapp.net", name: "Ray Colton" }] }];

test("a person's channels are the ones New can send on that know them - email by address, a chat by address or name", () => {
  assert.deepEqual(channelsFor({ to: "erin@northwind.example", title: "Erin Blake" }, TARGETS),
    [{ channel: "email", to: "erin@northwind.example", name: "Erin Blake" }, { channel: "teams", to: "19:erin-chat", name: "Erin Blake" }]);
  assert.deepEqual(channelsFor({ to: "gail@northwind.example", title: "Gail Moreno" }, TARGETS).map((w) => w.channel), ["email"]);
  assert.deepEqual(channelsFor({ to: "gail@northwind.example", title: "Gail Moreno" }, []), [], "nothing connected can send: no way");
});

test("the pick opens New's Send something addressed, through the link New already answers to", () => {
  const link = messageLink({ channel: "email", to: "erin@northwind.example", name: "Erin Blake" });
  assert.deepEqual(canvasRequestFromHash(link, 3), { kind: "new", n: 3, state: { kind: "send", channel: "email", to: "erin@northwind.example", name: "Erin Blake" } });
  assert.deepEqual(canvasRequestFromHash("#new-task", 1), { kind: "new", n: 1 }, "the bare link is as it was");
  assert.match(src("CanvasBrowse.jsx"), /initialChannel=\{state\?\.channel \|\| ""\} initialTo=\{state\?\.to \|\| ""\}/);
  assert.match(src("NewSheet.jsx"), /if \(asked && initialTo\) \{ if \(asked === "email"\) setEmailTo\(\[initialTo\]\); else setTo\(initialTo\); \}/);
  // ...and a person with nothing on record keeps the line saying so, with Message them under it
  assert.match(src("SearchEverything.jsx"), /\{nothingYet\(aloneAs\(res\)\)\}\n\s+<MessageThem person=\{hits\[0\]\} onGo=\{message\}/);
});
