import assert from "node:assert/strict";
import test from "node:test";
import { inventory, press, shape, stressWorld } from "./stress-buttons.mjs";

/* EVERY ROW BUTTON, PRESSED LIKE A HURRIED HAND (the owner, 2026-11-02: "hitting all the buttons - reply, mark done, continue and everything -
   still looks smooth and no crazy stuff"; "click every button on every task with 100 tasks or 1, clicking buttons fast/slow, multiple times").
   Each item kind's buttons, found on the item as drawn, each pressed on a fresh copy once and three times fast with the mouse where the
   button stands: what the server wrote is the same as one press wrote, no page error or React warning, no error receipt, the card never comes
   back once it went, nothing scrolls sideways or is cut off, and a close or put-down walks on (the only item: the walk ends). Two worlds: the
   item alone, and the item among ~100. The full matrix (every kind, every mode, screenshots) is browser/stress-run.mjs; invented people only.
   TQ_STRESS_SHOTS=<dir> keeps a screenshot of each press at 1440x900 and 1280x800. */
const SHOTS = process.env.TQ_STRESS_SHOTS || "";
const CLOSERS = new Set(["done", "close-note", "nat", "remind", "watch", "w:not_ours", "next"]);
// the buttons that open the owner's own system dialog or a box a person fills (Attach a file, Share's places) are pressed in stress-run
const SKIP = new Set(["back", "attach", "share", "hand", "w:regular_agent", "start-agent", "send-general", "run-another"]);

async function matrix(t, world, kinds, modes) {
  const w = await stressWorld(t, { ...world, shots: SHOTS });
  const bad = [];
  for (const kind of kinds) {
    // ...and the Advisor's own lit move (advice:*) comes with its read of each copy, not with the kind: press-runs-once presses Chase them
    const buttons = (await inventory(w, kind)).filter((b) => !b.off && !SKIP.has(b.id) && !b.id.startsWith("advice:"));
    assert.ok(buttons.length, `${kind}: no buttons found`);
    for (const b of buttons) {
      let one = null;
      for (const mode of modes) {
        const r = await press(w, kind, b, mode);
        const s = shape(r.delta || {});
        if (mode === "once") one = s;
        // ...Next too: greyed while its move is out, a second press fast is no press (one move at a time, 2026-11-03)
        else if (JSON.stringify(s) !== JSON.stringify(one)) r.problems.push(`wrote other than one press: ${JSON.stringify(one)} vs ${JSON.stringify(s)}`);
        if (CLOSERS.has(b.id) && !(kind === "watched" && b.id === "watch") && (mode === "once" || b.id !== "next")) {
          if (r.card) r.problems.push("the card stayed after a close");
          if (world.only && r.on) r.problems.push(`the only item went and the walk stands on ${r.on}`);
        }
        bad.push(...r.problems.map((p) => `${kind} ${b.id} ${mode}: ${p}`));
      }
    }
  }
  assert.deepEqual(bad, [], `\n${bad.join("\n")}`);
}

test("the only item: every button once and three times fast does its work once, and a close ends the walk", { timeout: 1800000 }, (t) =>
  matrix(t, { only: true }, ["general", "draft", "fyi", "report", "invite", "meet", "finished", "blocked"], ["once", "thrice"]));

test("among a hundred items: every button once and twice fast does its work once, and a close walks on", { timeout: 1800000 }, (t) =>
  matrix(t, { fill: 100 }, ["owed", "goal", "sent", "watched", "saved", "fyi"], ["once", "twice"]));
