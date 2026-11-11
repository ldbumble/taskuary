// A scratch instance on the person's real CLI, kept up for a walk driven from other scripts (real-lib.mjs). Not a test: nothing here runs in CI.
import { execFileSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { startHarness } from "./harness.mjs";

const out = process.env.REAL_OUT || path.join(os.tmpdir(), "claude", "real");
await mkdir(out, { recursive: true });
const where = (n) => execFileSync("where", [n], { encoding: "utf8" }).trim().split(/\r?\n/).map((s) => s.trim());
const claude = where("claude").find((p) => /\.cmd$/i.test(p)), exe = path.join(path.dirname(claude), "node_modules", "@anthropic-ai", "claude-code", "bin");
const git = where("git")[0];
process.env.TASKUARY_BROWSER_REAL_CLI = [exe, path.dirname(where("node")[0]), path.dirname(git)].join(path.delimiter);
const h = await startHarness({ fresh: true });
const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET", headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
console.log("ai", JSON.stringify(await api("/api/setup/first-run/ai", { name: "claude" })).slice(0, 300));
await api("/api/setup/dismiss", { dismissed: true });
console.log("outbox", JSON.stringify(await api("/api/fixture/outbox", {})));
const page = await h.newPage();
await page.setViewport({ width: 1280, height: 900 });
page.on("pageerror", (e) => console.log("PAGEERROR", e.message));
await page.goto(h.ui, { waitUntil: "domcontentloaded" });
await writeFile(path.join(out, "info.json"), JSON.stringify({ ui: h.ui, api: h.fixtureApi, token: h.token, home: h.home, ws: page.browser().wsEndpoint(), git, pid: process.pid }));
console.log("READY", h.ui, h.home);
const stop = path.join(out, "stop");
let n = 0;
while (!existsSync(stop)) { await new Promise((r) => setTimeout(r, 2000)); if (++n % 5 === 0) await writeFile(path.join(out, "server.log"), h.log()); }
await writeFile(path.join(out, "server.log"), h.log());
await h.close();
