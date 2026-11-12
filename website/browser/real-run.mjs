// A scratch instance on the person's real CLI, kept up for a walk driven from other scripts (real-lib.mjs). Not a test: nothing here runs in CI.
import { execFileSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { existsSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { startHarness } from "./harness.mjs";

const out = process.env.REAL_OUT || path.join(os.tmpdir(), "claude", "real");
await mkdir(out, { recursive: true });
const where = (n) => execFileSync("where", [n], { encoding: "utf8" }).trim().split(/\r?\n/).map((s) => s.trim());
const claude = where("claude").find((p) => /\.cmd$/i.test(p)), exe = path.join(path.dirname(claude), "node_modules", "@anthropic-ai", "claude-code", "bin");
const git = where("git")[0];
const real = [exe, path.dirname(where("npx")[0])          /* the folder npx is in: an ACP adapter is launched through it */, path.dirname(git)];
// THE AGENTS' BROWSER, KEPT IN THE SCRATCH HOME (REAL_BROWSER=1; a walk of the browser): the CLI signs in from the person's own profile, and the
// browser driver keeps its sessions under whatever profile it is run with - so it is run through a stand-in of its name that hands it the
// scratch profile (the folder above AGENT_BROWSER_HOME, harness.mjs). Nothing of a walk is written to the person's own driver folder.
// ...REAL_EXTRA_PATH: more folders of programs - an ACP adapter installed in a scratch folder (npm i --prefix), found on PATH as the owner's own
if (process.env.REAL_EXTRA_PATH) real.unshift(...process.env.REAL_EXTRA_PATH.split(path.delimiter));
if (process.env.REAL_BROWSER === "own") real.push(path.dirname(where("agent-browser")[0]));
else if (process.env.REAL_BROWSER) {
  const exe = path.join(path.dirname(where("agent-browser")[0]), "node_modules", "agent-browser", "bin", "agent-browser-win32-x64.exe"), shim = path.join(out, "shim");
  await mkdir(shim, { recursive: true });
  await writeFile(path.join(shim, "agent-browser.cmd"), `@echo off
for %%I in ("%AGENT_BROWSER_HOME%\\..") do set "USERPROFILE=%%~fI"
set "HOME=%USERPROFILE%"
"${exe}" %*
`);
  await writeFile(path.join(shim, "agent-browser"), `#!/bin/sh
USERPROFILE="$(cygpath -w "$(dirname "$(cygpath -u "$AGENT_BROWSER_HOME")")")"; HOME="$USERPROFILE"; export USERPROFILE HOME
exec "$(cygpath -u '${exe}')" "$@"
`);
  real.unshift(shim);
}
// THE `taskuary` COMMAND OF THIS CHECKOUT (worker 8, 2026-11-12: a walk's coding agent ran the INSTALLED build's `taskuary --reply` and
// heard its old words): a stand-in of that name first on PATH runs this checkout's cli - terminal.own_command then finds it and adds nothing
{ const repo = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")), "..", ".."), bin = path.join(out, "twbin");
  const py = execFileSync(process.env.TASKUARY_TEST_PYTHON || "python", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  await mkdir(bin, { recursive: true });
  await writeFile(path.join(bin, "taskuary.cmd"), `@echo off\r\nset "PYTHONPATH=${repo}"\r\n"${py}" -m taskuary.cli %*\r\n`);
  await writeFile(path.join(bin, "taskuary"), `#!/bin/sh\nPYTHONPATH='${repo.replace(/\\/g, "/")}' exec "$(cygpath -u '${py}')" -m taskuary.cli "$@"\n`);
  real.unshift(bin); }
process.env.TASKUARY_BROWSER_REAL_CLI = real.join(path.delimiter);
const h = await startHarness({ fresh: true });
// ...AND npx RUNS IN IT (the coding walk, 2026-11-12): APPDATA is the scratch home's, with no npm folder, so `npx -y <the ACP adapter>` failed
// and every coding session fell back to its terminal - a road the owner's own machine does not take
await mkdir(path.join(h.home, "appdata", "npm"), { recursive: true });
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
const stop = path.join(out, "stop"), again = path.join(out, "restart");
let n = 0;
while (!existsSync(stop)) { await new Promise((r) => setTimeout(r, 1000)); if (++n % 10 === 0) await writeFile(path.join(out, "server.log"), h.log());
  // ...`restart` beside it: the server stopped and started again on the same home and port, the page left open (real-conv's `restart` step)
  if (existsSync(again)) { await writeFile(path.join(out, `server-${Date.now()}.log`), h.log()); await h.restart({ down: 1500 }); rmSync(again, { force: true }); console.log("RESTARTED"); } }
await writeFile(path.join(out, "server.log"), h.log());
await h.close();
