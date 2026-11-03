// the button stress, run by hand: KINDS=draft,general MODES=once,twice ONLY=1 FILL=100 BUTTONS=done,watch OUT=<dir> node browser/stress-run.mjs
// writes <OUT>/stress-<world>.json - every press and what it left - and the screenshots beside it
import { writeFileSync } from "node:fs";
import { inventory, press, shape, stressWorld } from "./stress-buttons.mjs";

const env = (k, d) => (process.env[k] ? process.env[k].split(",") : d);
const KINDS = env("KINDS", ["general", "owed", "draft", "goal", "invite", "meet", "sent", "deferred", "todo", "watched", "blocked", "working", "asked",
  "finished", "stopped", "failed", "saved", "news", "report", "fyi"]);
const MODES = env("MODES", ["once", "twice", "thrice", "then:done"]);
const ONLY = process.env.ONLY === "1", OUT = process.env.OUT, PICK = env("BUTTONS", null), SKIP = env("SKIP", ["back"]);
const CLOSERS = new Set(["done", "close-note", "nat", "remind", "watch", "w:not_ours", "next"]);
const w = await stressWorld(null, { fill: Number(process.env.FILL || 0), only: ONLY, shots: process.env.SHOTS === "0" ? "" : OUT });
const all = [];
const save = () => writeFileSync(`${OUT}/stress-${ONLY ? "one" : "many"}.json`, JSON.stringify(all, null, 1));
try {
  for (const kind of KINDS) {
    const buttons = (await inventory(w, kind)).filter((b) => !b.off && !SKIP.includes(b.id) && (!PICK || PICK.includes(b.id)));
    console.log(`== ${kind}: ${buttons.map((b) => b.id).join(" ")}`);
    for (const b of buttons) {
      const once = {};
      for (const mode of MODES) {
        if (mode === `then:${b.id}`) continue;
        const r = await press(w, kind, b, mode);
        r.shape = shape(r.delta || {});
        if (mode === "once") once.shape = r.shape;
        else if (["twice", "thrice"].includes(mode) && once.shape && JSON.stringify(once.shape) !== JSON.stringify(r.shape)) r.problems.push(`wrote other than one press: once ${JSON.stringify(once.shape)} vs ${JSON.stringify(r.shape)}`);
        // THE WALK (walk-rules-final, 2026-10-30): a close or a put-down goes on to the row below; Send keeps the item
        if (CLOSERS.has(b.id) && !mode.startsWith("then:")) {
          if (r.card) r.problems.push("the card stayed after a close");
          if (r.below && r.on !== r.below) r.problems.push(`the walk went to ${r.on}, not the row below (${r.below})`);
          if (!r.below && r.on && ONLY) r.problems.push(`the only item went and the walk stands on ${r.on}`);
        }
        all.push(r); save();
        console.log(`${kind} ${b.id} ${mode}: ${r.problems.length ? "PROBLEMS " + r.problems.join(" || ") : "ok"} | ${JSON.stringify(r.shape)} | ${r.requests?.join(" ")} | on=${r.on} card=${r.card}${process.env.VERBOSE ? ` | said=${JSON.stringify(r.said)} chat=${r.chat}` : ""}`);
      }
    }
  }
} finally { save(); await w.h.close(); }
