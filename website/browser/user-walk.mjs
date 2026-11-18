// THE WORLD AROUND AN AGENT PLAYING THE OWNER (not a test: nothing here runs in CI). node user-walk.mjs [day.json]
// Drips a working day's mail and chat into the scratch instance (real-run.mjs) on its clock - `at` minutes after the start, times
// USER_SPEED (2 = twice as fast) - while the agent playing the owner works the app through user.mjs, never knowing what comes next.
// A reply on a thread is the same conversation as the mail before it; a file an arrival carries is written beside the walk (its text inline
// in the mail too, as a pasted export) for the player to attach when it answers.
import path from "node:path";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { existsSync, readFileSync } from "node:fs";
import { execFileSync, spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { api, sleep, out } from "./real-lib.mjs";

const day = JSON.parse(await readFile(process.argv[2] || new URL("./user-day.json", import.meta.url), "utf8"));
const speed = Number(process.env.USER_SPEED || 1), files = path.join(out, "user-files");
await mkdir(files, { recursive: true });
for (const [f, text] of Object.entries(day.files || {})) await writeFile(path.join(files, f), text);
// ...and the repository the day's CI failure is about: an invented ledger with a rounding bug and the test that catches it, a git repo on
// the player's disk as a person's checkout is - a coding task works in it
const repo = path.join(out, "ledger");
if (!existsSync(path.join(repo, ".git"))) {
  await mkdir(path.join(repo, "tests"), { recursive: true });
  await writeFile(path.join(repo, "totals.py"), "def total(amounts):\n    return round(sum(amounts))  # rounds to whole dollars\n");
  await writeFile(path.join(repo, "tests", "test_totals.py"), "from totals import total\n\ndef test_rounding():\n    assert total([10.25, 4.50]) == 14.75\n");
  for (const a of [["init", "-q"], ["add", "."], ["-c", "user.name=Alex Doyle", "-c", "user.email=alex@northwind.example", "commit", "-qm", "Totals"]]) execFileSync("git", a, { cwd: repo });
}
await writeFile(path.join(out, "user-brief.md"), [`# Who you are\n${day.persona}`, `# What you must get done today\n${day.goals.map((g) => `- ${g}`).join("\n")}`,
  `# Files you have\n${Object.keys(day.files || {}).map((f) => `- ${path.join(files, f)}`).join("\n") || "- none"}\n- the northwind/ledger checkout on your disk: ${repo}`].join("\n\n"));
// ...AND THE WEB IT SIGNS UP ON: invented vendor sites on this computer (fake_signup.py - a sign-up form, password rules, a human check, a
// code by email, a code by phone, a paid plan), each on its own loopback address; the codes they "email" arrive as mail, as a real inbox would
const SITE = 18791, INBOX = path.join(out, "sites-inbox.jsonl"), PY = process.env.TASKUARY_TEST_PYTHON || "python";
const sites = spawn(PY, [fileURLToPath(new URL("./fake_signup.py", import.meta.url)), String(SITE), INBOX], { stdio: "ignore" });
process.on("exit", () => { try { sites.kill(); } catch {} });
let inboxSeen = 0;
const relay = setInterval(async () => {
  if (!existsSync(INBOX)) return;
  const lines = readFileSync(INBOX, "utf8").split("\n").filter(Boolean);
  for (const l of lines.slice(inboxSeen)) { const m = JSON.parse(l);
    await api("/api/fixture/incoming", { from_email: m.from, from_name: m.from.split("@")[1], subject: m.subject, body: m.body }).catch(() => {}); }
  inboxSeen = lines.length;
}, 3000);
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
// ...the sites stay up, and their mail keeps coming, for as long as the player works the day
await new Promise(() => {});
