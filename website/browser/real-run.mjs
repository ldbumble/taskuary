// A scratch instance on the person's real CLI, kept up for a walk driven from other scripts (real-lib.mjs). Not a test: nothing here runs in CI.
import { execFileSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { existsSync, readFileSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { startHarness } from "./harness.mjs";

// ...AND NOTHING OF `npm exec` REACHES THE APP (the browser audit, 2026-11-15): run as `npm exec --package=node@22 -- node real-run.mjs`, its
// npm_config_package=node@22 rode into the server, so the server's own `npx -y <the ACP adapter>` fetched node instead and ran the adapter's
// name as a command ("'agentclientprotocol' is not recognized") - every agent of the walk fell back to its command line, a road the owner's
// machine does not take
for (const k of Object.keys(process.env)) if (/^npm_/i.test(k)) delete process.env[k];
const out = process.env.REAL_OUT || path.join(os.tmpdir(), "claude", "real");
await mkdir(out, { recursive: true });
// ...on any machine: `where` on Windows, `which -a` elsewhere (a cloud walk runs on Linux)
const WIN = process.platform === "win32", BRAIN = process.env.EVAL_BRAIN || "cli";
const where = (n) => execFileSync(WIN ? "where" : "which", WIN ? [n] : ["-a", n], { encoding: "utf8" }).trim().split(/\r?\n/).map((s) => s.trim());
const git = where("git")[0];
const real = [path.dirname(where("npx")[0])          /* the folder npx is in: an ACP adapter is launched through it */, path.dirname(git)];
// ...the person's Claude CLI's own folder only when the walk runs on it
if (BRAIN === "cli") { const claude = where("claude").find((p) => !WIN || /\.cmd$/i.test(p));
  real.unshift(WIN ? path.join(path.dirname(claude), "node_modules", "@anthropic-ai", "claude-code", "bin") : path.dirname(claude)); }
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
// WHICH AGENT THE WALK RUNS ON (EVAL_BRAIN, tools/eval): `cli` the person's real CLI (the default), `stand-in` the test CLIs (tests/fake_claude.py,
// fake_acp_server.py - free, every mechanic and no judgement), `gateway` the test CLIs with an organisation AI card picked as every job's brain
// (its address, key and model from EVAL_AI_URL/EVAL_AI_KEY/EVAL_AI_MODEL or ~/.taskuary-eval.json - never from the repo)
// ...`codex`: the person's real Codex CLI picked as the agents' brain (its own budget, not Claude's)
if (BRAIN === "codex") real.unshift(path.dirname(where("codex")[0]));
if (BRAIN === "cli" || BRAIN === "codex") process.env.TASKUARY_BROWSER_REAL_CLI = real.join(path.delimiter);
// ...the gateway's address and key, read before the server starts: its host is the one outside address the test server may reach
const GW = BRAIN !== "gateway" ? {} : (() => { const f = path.join(os.homedir(), ".taskuary-eval.json"), c = existsSync(f) ? JSON.parse(readFileSync(f, "utf8")) : {};
  return { url: process.env.EVAL_AI_URL || c.url, key: process.env.EVAL_AI_KEY || c.key, model: process.env.EVAL_AI_MODEL || c.model }; })();
if (GW.url) process.env.TASKUARY_FIXTURE_ALLOW = new URL(GW.url).hostname;
const h = await startHarness({ fresh: true });
// ...AND npx RUNS IN IT (the coding walk, 2026-11-12): APPDATA is the scratch home's, with no npm folder, so `npx -y <the ACP adapter>` failed
// and every coding session fell back to its terminal - a road the owner's own machine does not take
await mkdir(path.join(h.home, "appdata", "npm"), { recursive: true });
const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET", headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
if (BRAIN === "gateway") {
  const { url, key, model } = GW;
  if (!url || !key) throw new Error("EVAL_BRAIN=gateway needs EVAL_AI_URL and EVAL_AI_KEY (or ~/.taskuary-eval.json)");
  const r = await api("/api/setup/first-run/key", { type: "hipaa_ai", key, config: { base_url: url, ...(model ? { model, strong_model: model } : {}) } });
  console.log("ai", JSON.stringify({ ok: r.ok, why: r.why }).slice(0, 300));         // ...never the key
  if (!r.ok) throw new Error(`the gateway card did not take: ${r.why}`);
} else console.log("ai", JSON.stringify(await api("/api/setup/first-run/ai", { name: BRAIN === "codex" ? "codex" : "claude" })).slice(0, 300));
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
