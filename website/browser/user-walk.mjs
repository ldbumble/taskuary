// THE WORLD AROUND AN AGENT PLAYING THE OWNER (not a test: nothing here runs in CI). node user-walk.mjs [day.json]
// Drips a working day's mail and chat into the scratch instance (real-run.mjs) on its clock - `at` minutes after the start, times
// USER_SPEED (2 = twice as fast) - while the agent playing the owner works the app through user.mjs, never knowing what comes next.
// A reply on a thread is the same conversation as the mail before it; a file an arrival carries is written beside the walk (its text inline
// in the mail too, as a pasted export) for the player to attach when it answers.
import path from "node:path";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { api, sleep, out } from "./real-lib.mjs";

const day = JSON.parse(await readFile(process.argv[2] || new URL("./user-day.json", import.meta.url), "utf8"));
const speed = Number(process.env.USER_SPEED || 1), files = path.join(out, "user-files");
await mkdir(files, { recursive: true });
for (const [f, text] of Object.entries(day.files || {})) await writeFile(path.join(files, f), text);
await writeFile(path.join(out, "user-brief.md"), [`# Who you are\n${day.persona}`, `# What you must get done today\n${day.goals.map((g) => `- ${g}`).join("\n")}`,
  `# Files you have\n${Object.keys(day.files || {}).map((f) => `- ${path.join(files, f)}`).join("\n") || "- none"}`].join("\n\n"));
const thread = (s) => String(s || "").replace(/^\s*(re|fw|fwd)\s*:\s*/i, "").trim().toLowerCase();
const t0 = Date.now();
for (const a of [...day.arrivals].sort((x, y) => x.at - y.at)) {
  const wait = t0 + (a.at * 60000) / speed - Date.now();
  if (wait > 0) await sleep(wait);
  const [, name, email] = /^(.*?)\s*<(.+)>$/.exec(a.from) || [, a.from, ""];
  const body = a.attach && day.files?.[a.attach] ? `${a.body}\n\n--- ${a.attach} ---\n${day.files[a.attach]}` : a.body;
  const got = await api("/api/ingest/push", { channel: a.channel, subject: a.subject || "", body, from_name: name, ...(email ? { from_email: email } : {}),
    conversation_id: `day-${a.channel}-${thread(a.subject) || name}` });
  console.log(`[${((Date.now() - t0) / 60000).toFixed(1)}m] ${a.channel} from ${name}: ${a.subject || a.body.slice(0, 40)} -> ${JSON.stringify(got).slice(0, 120)}`);
}
console.log("the day's arrivals are all in");
