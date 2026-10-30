// WHAT THE AGENT DID, in the owner's words - one step model every backend maps into.
//
// The general agent's canvas drew its trace as the machine wrote it: a row per tool call reading "Read C:\Users\...\StatusBoard.js",
// a whole shell script with the token header in it, and then an "Agent progress" box saying the same commands again with a Python key
// list under them (the owner, 2026-10-21: "make the output on the general agent canvas more readable, not some greps and gets").
//
// Every backend already arrives as the same trace events - tool_call {name, args}, tool_result, progress, live - from claude's
// stream-json, codex's JSONL, opencode, kimi, an ACP CLI (agents.acp_tracer) and an API connector's own web searches (llm.watching).
// Here each becomes a step {kind, summary, detail, status}: the summary is built mechanically from the tool's name and its arguments -
// a file name instead of a path, the search's query, a page's host, a task's id - and never by guessing intent from words. The raw call
// and its output stay in `detail`, which the canvas keeps behind the row's disclosure for debugging.
import { forScreen } from "./agentMarkers.js";
import { plural } from "./timeWords.js";

const flat = (s) => String(s || "").split(/\s+/).join(" ").trim();
const clip = (s, n = 90) => { const t = flat(s); return t.length > n ? `${t.slice(0, n - 1)}…` : t; };
const quoted = (s) => `'${clip(s, 60)}'`;
const parts = (p) => String(p || "").replace(/[\\/]+$/, "").split(/[\\/]+/).filter(Boolean);
export const baseName = (p) => parts(p).pop() || String(p || "");
const parent = (p) => { const x = parts(p); return x.length > 1 ? x[x.length - 2] : ""; };
const hostOf = (u) => (/^https?:\/\/(?:www\.)?([^/?#:]+)/i.exec(String(u || "")) || [])[1] || "";
const key = (name) => String(name || "").toLowerCase().replace(/[^a-z0-9]/g, "");
const prog = (w) => String(w || "").split(/[\\/]/).pop().toLowerCase().replace(/\.(exe|cmd|bat|ps1)$/, "");

// ── a shell command, read the way a person skims it ─────────────────────────────────────────────
// Split at the operators outside quotes; a segment after a pipe only filters what came before it.
const segments = (cmd) => {
  const out = []; let cur = "", q = null, piped = false;
  const push = (nextPiped) => { if (cur.trim()) out.push({ text: cur.trim(), piped }); cur = ""; piped = nextPiped; };
  const s = String(cmd || "");
  for (let i = 0; i < s.length; i += 1) {
    const c = s[i];
    if (q) { if (c === q) q = null; else if (c === "\\" && q === '"') { cur += c + (s[i + 1] || ""); i += 1; continue; } cur += c; continue; }
    if (c === '"' || c === "'") { q = c; cur += c; continue; }
    if (c === "\\" && s[i + 1] === "\n") { i += 1; continue; }
    if ((c === "&" || c === "|") && s[i + 1] === c) { push(false); i += 1; continue; }
    if (c === ";" || c === "\n") { push(false); continue; }
    if (c === "|") { push(true); continue; }
    if (c === "&") { push(false); continue; }
    cur += c;
  }
  push(false);
  return out;
};
const words = (seg) => {
  const out = []; let cur = "", q = null, has = false;
  for (let i = 0; i < seg.length; i += 1) {
    const c = seg[i];
    if (q) { if (c === q) q = null; else cur += c; continue; }
    if (c === '"' || c === "'") { q = c; has = true; continue; }
    if (/\s/.test(c)) { if (cur || has) out.push(cur); cur = ""; has = false; continue; }
    cur += c;
  }
  if (cur || has) out.push(cur);
  return out;
};
const SHELLS = new Set(["bash", "sh", "zsh", "dash", "powershell", "pwsh", "cmd"]);
const QUIET = new Set(["cd", "pushd", "popd", "export", "set", "echo", "printf", "true", "false", "sleep", "mkdir", "for", "while",
  "if", "fi", "done", "local", "source", ".", "test", "[", "read", "rm", "cp", "mv", "touch", "trap", "unset", "clear", "write-host"]);
const READERS = new Set(["cat", "type", "head", "tail", "sed", "less", "more", "get-content", "gc", "nl", "bat", "awk"]);
const GREPS = new Set(["rg", "grep", "egrep", "fgrep", "findstr", "ag", "ack", "select-string", "sls"]);
const LISTS = new Set(["ls", "dir", "find", "tree", "get-childitem", "gci", "fd"]);
const FETCH = new Set(["curl", "wget", "iwr", "invoke-webrequest", "irm", "invoke-restmethod", "http", "https"]);
const SNIPPET = { python: "Python", python3: "Python", py: "Python", node: "Node", deno: "Deno", ruby: "Ruby", perl: "Perl" };
const LEAD = new Set(["do", "then", "else", "time", "sudo", "env", "!", "{", "(", "exec", "nohup", "xargs"]);

const taskuaryCall = (path, cmd) => {
  const [where, query = ""] = path.split("?");
  const bits = where.split("/").filter(Boolean);
  const param = (k) => { const m = new RegExp(`(?:^|&)${k}=([^&]*)`).exec(query); try { return m ? decodeURIComponent(m[1].replace(/\+/g, " ")) : ""; } catch { return m[1]; } };
  if (bits[0] === "search") { const q = param("q"); return { kind: "mail", summary: q && !q.includes("$") ? `Searched your mail for ${quoted(q)}` : "Searched your mail", q }; }
  if (bits[0] === "tasks" && /^\d+$/.test(bits[1] || "")) return { kind: "task", summary: `Opened TQ-${bits[1].padStart(4, "0")}` };
  if (bits[0] === "tasks") return { kind: "task", summary: "Looked at your task list" };
  if (bits[0] === "messages" && /^\d+$/.test(bits[1] || "")) return { kind: "mail", summary: `Opened message ${bits[1]}` };
  if (bits[0] === "tools" && bits[1] === "run") { const t = (/"type"\s*:\s*"([\w.-]+)"/.exec(cmd) || [])[1]; return { kind: "data", summary: t ? `Looked up data in ${t}` : "Looked up data in a connected system" }; }
  return { kind: "data", summary: `Looked up ${(bits[0] || "data").replace(/[-_]/g, " ")} in Taskuary` };
};

// AGENT-BROWSER IN WORDS, from its own fixed grammar (browsergate.LOOKS / TYPES lists the same verbs): Codex and Gemini read "Ran
// agent-browser click" with no page or target, while Claude was saved only by its own Bash description (2026-10-25)
const AB_VALUED = new Set(["--session", "--profile", "--state", "--args", "--user-agent", "--proxy", "--executable-path", "--cdp",
  "--idle-timeout", "--headers", "--timeout", "--restore", "--device", "--color-scheme", "--download-path"]);
const AB_LOOKS = new Set(["snapshot", "get", "read", "screenshot", "is", "wait", "console", "errors", "tabs", "tab", "highlight", "hover"]);
const AB_ACTIONS = new Set(["click", "dblclick", "press", "fill", "type", "check", "uncheck", "hover", "focus", "select"]);
const AB_SAID = { back: "Went back a page", forward: "Went forward a page", reload: "Reloaded the page", scroll: "Scrolled the page",
  scrollintoview: "Scrolled the page", close: "Closed the browser", click: "Clicked on the page", dblclick: "Clicked on the page",
  press: "Pressed a key on the page", fill: "Typed into a box", type: "Typed into a box", check: "Ticked a box", uncheck: "Unticked a box",
  select: "Chose an option", upload: "Uploaded a file", keyboard: "Typed on the page", pdf: "Saved the page as a PDF" };
export const browserStep = (args) => {
  const a = [];
  for (let i = 0; i < args.length; i += 1) {
    if (AB_VALUED.has(args[i])) { i += 1; continue; }
    if (!String(args[i]).startsWith("-")) a.push(args[i]);
  }
  const [verb = "", ...rest] = a.map(String), v = verb.toLowerCase();
  const step = (summary, more = {}) => ({ kind: "page", summary, browser: true, ...more });
  if (["open", "goto", "navigate"].includes(v)) { const host = hostOf(rest[0]) || hostOf(`https://${rest[0] || ""}`); return step(host ? `Opened ${host}` : "Opened a page", { host }); }
  if (AB_LOOKS.has(v)) return step("Looked at the page");
  if (v === "find") {
    // find <locator> <value> <action> [text]: a role's own name may sit before the action ("button "Pay now" click") or after it
    const ai = rest.findIndex((w, i) => i >= 2 && AB_ACTIONS.has(w.toLowerCase())), act = ai >= 0 ? rest[ai].toLowerCase() : "";
    const value = (ai > 2 && rest.slice(2, ai).join(" ")) || (rest[0] !== "role" && rest[1]) || (ai >= 0 && rest.slice(ai + 1).join(" ")) || rest[1];
    if (["fill", "type"].includes(act)) return step(value ? `Typed into ${quoted(value)}` : "Typed into a box");
    if (["click", "dblclick", "press"].includes(act)) return step(value ? `Clicked ${quoted(value)}` : "Clicked on the page");
    return step(value ? `Looked for ${quoted(value)} on the page` : "Looked at the page");
  }
  return step(AB_SAID[v] || (v ? `Used the browser (${v})` : "Used the browser"));
};

const commandStep = (cmd, depth = 0) => {
  const found = [];
  for (const seg of segments(cmd)) {
    if (seg.piped) continue;
    let w = words(seg.text);
    if (/^[A-Za-z_]\w*=\(/.test(w[0] || "")) continue;                       // an array being set up: H=(-H "...")
    while (w.length && (LEAD.has(w[0]) || /^[A-Za-z_]\w*=/.test(w[0]))) w = w.slice(1);
    if (!w.length || !/^[\w.:\/~+-]+$/.test(w[0])) continue;                 // only a word that can name a program
    const p = prog(w[0]), args = w.slice(1), plain = args.filter((a) => !a.startsWith("-"));
    if (SHELLS.has(p) && depth < 2) {
      const at = args.findIndex((a) => /^(-l?c|-command|\/c)$/i.test(a));
      const inner = at >= 0 ? args.slice(at + 1).join(" ") : "";
      if (inner) { const s = commandStep(inner, depth + 1); if (s) found.push(s); continue; }
    }
    if (QUIET.has(p)) continue;
    if (p === "agent-browser" || (["npx", "pnpm", "bunx"].includes(p) && prog(plain[0]) === "agent-browser")) {
      found.push(browserStep(p === "agent-browser" ? args : args.slice(args.indexOf(plain[0]) + 1))); continue;
    }
    if (FETCH.has(p)) {
      const url = args.find((a) => /^https?:\/\//i.test(a) || a.includes("/api/"));
      if (!url) { found.push({ kind: "run", summary: `Ran ${p}` }); continue; }
      const api = url.indexOf("/api/"), host = hostOf(url);
      if (api >= 0 && (!host || /^(localhost|127\.0\.0\.1)$/i.test(host))) found.push(taskuaryCall(url.slice(api + 5), seg.text));
      else found.push({ kind: "page", summary: `Read a page on ${host || clip(url, 40)}`, host });
      continue;
    }
    if (READERS.has(p) && plain.length) { const f = plain[plain.length - 1]; found.push({ kind: "read", summary: `Read ${baseName(f)}`, file: f }); continue; }
    if (GREPS.has(p) || (p === "git" && args[0] === "grep")) {
      const e = args.indexOf("-e"), pat = e >= 0 ? args[e + 1] : plain[p === "git" ? 1 : 0];
      found.push({ kind: "search", summary: pat ? `Searched files for ${quoted(pat)}` : "Searched files", pattern: pat }); continue;
    }
    if (LISTS.has(p)) { const d = plain[0]; found.push({ kind: "list", summary: d && d !== "." ? `Listed the files in ${baseName(d)}` : "Listed the files here" }); continue; }
    if (SNIPPET[p] && args.some((a) => a === "-c" || a === "-e")) { found.push({ kind: "run", summary: `Ran a ${SNIPPET[p]} snippet`, filler: true }); continue; }
    const sub = args[0] && /^[a-z][\w.-]{0,24}$/i.test(args[0]) ? ` ${SNIPPET[p] ? baseName(args[0]) : args[0]}` : "";
    found.push({ kind: "run", summary: `Ran ${p}${sub}`, filler: !!SNIPPET[p] });
  }
  // a snippet that only reshapes what a fetch brought back is not a step of its own
  const real = found.filter((s) => !s.filler);
  const use = real.length ? real : found;
  if (!use.length) return null;
  return { ...use[0], summary: use.length > 1 ? `${use[0].summary}, and ${use.length - 1} more` : use[0].summary };
};

// ── a tool call, by its name and arguments ───────────────────────────────────────────────────────
const fileOf = (a) => a.file_path || a.filePath || a.absolute_path || a.path || a.file || a.notebook_path || "";
const firstUrl = (s) => (/https?:\/\/[^\s"')]+/.exec(String(s || "")) || [])[0] || "";
const TOOLS = {
  read: ["read", "readfile", "view", "readmanyfiles", "openfile", "catfile"],
  search: ["grep", "searchfilecontent", "searchtext", "rg", "codebasesearch", "grepsearch"],
  list: ["glob", "ls", "listdirectory", "listdir", "list", "find", "findfiles"],
  web: ["websearch", "googlewebsearch", "searchweb", "googlesearch", "webquery"],
  page: ["webfetch", "fetch", "fetchurl", "readurl", "browse", "openurl"],
  run: ["bash", "shell", "runshellcommand", "execute", "shellcommand", "powershell", "terminal", "execcommand", "runcommand", "localshell"],
  edit: ["edit", "multiedit", "replace", "strreplace", "strreplacebasededittool", "applypatch", "notebookedit", "filechange", "patch"],
  write: ["write", "writefile", "createfile"],
  helper: ["task", "agent", "subagent", "dispatchagent"],
  plan: ["todowrite", "updateplan", "plan", "todoread"],
  sync: ["syncmessages"],
};
const KIND = Object.fromEntries(Object.entries(TOOLS).flatMap(([k, names]) => names.map((n) => [n, k])));

export const describeCall = (name, args = {}) => {
  const a = args && typeof args === "object" ? args : {};
  const mcp = /^mcp__(.+?)__(.+)$/.exec(String(name || ""));
  let kind = KIND[key(mcp ? mcp[2] : name)] || "";
  // an ACP "search" is either kind, and says which by what it was given: a pattern searches files, a query searches the web
  if (kind === "search" && a.query && !a.pattern) kind = "web";
  if (key(name) === "search" && !kind) kind = a.pattern ? "search" : "web";
  const cmd = a.command || a.cmd || a.script;
  if (kind === "run" || (!kind && cmd)) {
    const s = commandStep(Array.isArray(cmd) ? cmd.join(" ") : cmd);
    // ...Claude's own words for a browser step ("Press the pay button for invoice INV-1001") say more than the verb does
    if (s && s.kind !== "run" && !(s.browser && a.description)) return s;
    if (a.description) return { kind: s?.browser ? "page" : "run", summary: clip(a.description) };
    return s || { kind: "run", summary: "Ran a command" };
  }
  if (kind === "read") { const f = fileOf(a); return { kind, summary: f ? `Read ${baseName(f)}` : "Read a file", file: f }; }
  if (kind === "search") { const pat = a.pattern || a.query || a.regex; return { kind, summary: pat ? `Searched files for ${quoted(pat)}` : "Searched files", pattern: pat }; }
  if (kind === "list") { const g = a.pattern || a.glob, d = a.path || a.dir_path || a.directory; return { kind, summary: g ? `Looked for files matching ${quoted(g)}` : d ? `Listed the files in ${baseName(d)}` : "Listed the files" }; }
  if (kind === "web") { const q = a.query || a.q || a.search_term; return { kind, summary: q ? `Searched the web for ${quoted(q)}` : "Searched the web", q }; }
  if (kind === "page") { const host = hostOf(a.url || firstUrl(a.prompt)); return { kind, summary: host ? `Read a page on ${host}` : "Read a web page", host }; }
  if (kind === "edit" || kind === "write") {
    const changes = Array.isArray(a.changes) ? a.changes : [];
    if (changes.length > 1) return { kind: "edit", summary: `Changed ${changes.length} files` };
    const f = fileOf(a) || changes[0]?.path || "";
    return { kind: "edit", summary: f ? `${kind === "write" ? "Wrote" : "Edited"} ${baseName(f)}` : "Changed a file", file: f };
  }
  if (kind === "helper") return { kind, summary: a.description ? `Handed part of the work to a helper: ${clip(a.description, 70)}` : "Handed part of the work to a helper" };
  if (kind === "plan") { const n = (a.todos || a.plan || []).length; return { kind, summary: n ? `Updated its plan (${n} steps)` : "Updated its plan" }; }
  if (kind === "sync") return { kind, summary: `Checked for new mail${a.new ? ` (${a.new} new)` : ""}` };
  // anything else: its own name in words, and the one argument a person would want - a query, a host, a file
  const label = String(mcp ? mcp[2] : a.title || name || "a tool").replace(/[_-]+/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2").trim();
  const target = a.query ? quoted(a.query) : hostOf(a.url) || (fileOf(a) ? baseName(fileOf(a)) : "");
  return { kind: "tool", summary: `Used ${label}${mcp ? ` (${mcp[1].replace(/[_-]+/g, " ")})` : ""}${target ? ` on ${target}` : ""}` };
};

// a mail search's own answer says how many it found - read off the JSON it returned, when it is JSON
const countOf = (out) => {
  let j; try { j = JSON.parse(String(out || "").replace(/ ⏎ /g, "\n")); } catch { return null; }
  const list = Array.isArray(j) ? j : ["data", "results", "items", "messages", "hits"].map((k) => j?.[k]).find(Array.isArray);
  return list ? list.length : null;
};
const rawOf = (name, args) => {
  const a = args && typeof args === "object" ? args : {};
  const cmd = a.command || a.cmd;
  if (cmd) return `$ ${Array.isArray(cmd) ? cmd.join(" ") : cmd}`;
  return `${name} ${JSON.stringify(a, null, 2)}`;
};

// ── the trace, as steps ──────────────────────────────────────────────────────────────────────────
const ECHO = /^(→ |· |✗ |session started\b)/;            // agents._live_line's own rows for a tool call, its result, the init line
export function stepsOf(trace, { answer = "", keepStart = true } = {}) {
  const events = trace || [];
  // A structured backend says everything twice: its tool call and text as events, and the same again as readable `live` lines for
  // the terminal pane. Only a CLI that streams nothing structured is read off its lines - decided over the whole trace, not by
  // which came first, so the line written before the first tool call no longer slipped into the box as raw text.
  const structured = events.some((e) => e?.type === "tool_call" || e?.type === "progress");
  const steps = [], byId = new Map();
  const say = (kind, text) => {
    const t = forScreen(text);
    if (!t) return;
    const last = steps[steps.length - 1];
    if (kind === "said" && last?.kind === "said" && last.live) { last.summary += `\n${t}`; return; }
    steps.push({ id: `${kind}-${steps.length}`, kind, summary: t, detail: "", status: "done", live: kind === "said" && !structured });
  };
  for (const e of events) {
    if (!e) continue;
    if (e.type === "tool_call") {
      const args = e.detail?.args || e.detail || {};
      const id = e.detail?.tool_call_id || `${e.name}-${steps.length}`;
      const d = describeCall(e.name, args);
      const step = { id, ...d, raw: rawOf(e.name || "tool", args), output: "", status: "running" };
      byId.set(id, step); steps.push(step);
    } else if (e.type === "tool_result") {
      const step = byId.get(e.detail?.tool_call_id || e.name);
      if (!step) continue;
      step.status = e.detail?.is_error ? "error" : "done";
      step.output = String(e.detail?.result || "");
      if (step.kind === "mail" && step.q !== undefined) { const n = countOf(step.output); if (n !== null) step.count = n; }
    } else if (e.type === "progress" && e.detail) {
      const name = String(e.name || "");
      if (name === "thinking" || name === "reasoning") {
        const t = flat(forScreen(e.detail));
        if (t) steps.push({ id: `thought-${steps.length}`, kind: "thought", summary: clip(t, 140), detail: t.length > 140 ? t : "", status: "done" });
      } else if (name === "text" || name === "agent_message") say("said", e.detail);
      else say("note", e.detail);
    } else if (e.type === "live" && !structured && e.detail && !ECHO.test(String(e.detail))) {
      say("said", e.detail);
    } else if (e.type === "start" && keepStart) {
      steps.push({ id: `start-${steps.length}`, kind: "note", summary: `Started ${e.session?.provider || "the selected agent"}`, detail: "", status: "done" });
    } else if (e.type === "error") {
      steps.push({ id: `error-${steps.length}`, kind: "error", summary: `⚠ ${e.detail?.result || e.error || "The assistant could not answer."}`, detail: "", status: "error" });
    }
  }
  // what it said that the answer says again is the answer: a CLI's final text streams in as progress too
  // ...paragraph by paragraph: the streamed text has the reply draft taken out where the filed answer keeps it, so the whole never
  // matched and a general turn's answer showed twice, once without its draft and once with it (the overnight QA, 2026-10-30)
  const said = flat(forScreen(answer));
  const inAnswer = (t) => { const ps = String(t || "").split(/\n\s*\n/).map(flat).filter(Boolean); return ps.length > 0 && ps.every((p) => said.includes(p)); };
  const kept = said ? steps.filter((s) => s.kind !== "said" || !inAnswer(s.summary)) : steps;
  return group(kept).map(({ raw, output, live, q, host, file, pattern, count, ...s }) => s);
}

// ── consecutive calls of one kind read as one line ───────────────────────────────────────────────
const listOf = (xs, n = 3) => { const u = [...new Set(xs.filter(Boolean))]; return u.length > n ? `${u.slice(0, n).join(", ")} and ${u.length - n} more` : u.join(", "); };
const together = (run) => {
  const k = run[0].kind, n = run.length;
  if (k === "read") {
    const dirs = new Set(run.map((s) => parent(s.file)));
    return dirs.size === 1 && [...dirs][0] ? `Read ${n} files in ${[...dirs][0]}/` : `Read ${n} files`;
  }
  if (k === "search") return `Searched files for ${listOf(run.map((s) => s.pattern && quoted(s.pattern)))}`;
  if (k === "web") return `Searched the web for ${listOf(run.map((s) => s.q && quoted(s.q)))}`;
  if (k === "page") { const h = [...new Set(run.map((s) => s.host).filter(Boolean))]; return h.length === 1 ? `Read ${n} pages on ${h[0]}` : `Read ${n} pages (${listOf(h)})`; }
  if (k === "mail" && run.every((s) => s.q !== undefined)) return `Searched your mail for ${listOf(run.map((s) => s.q && !s.q.includes("$") && quoted(s.q)))}`;
  if (k === "edit") return `Changed ${n} files`;
  return run.every((s) => s.summary === run[0].summary) ? `${run[0].summary} (${n} times)` : null;
};
const statusOf = (run) => run.some((s) => s.status === "running") ? "running" : run.some((s) => s.status === "error") ? "error" : "done";
const detailOf = (s) => [s.raw, s.output && `→ ${s.output.length > 1500 ? `${s.output.slice(0, 1500)}…` : s.output}`].filter(Boolean).join("\n");
const withCount = (summary, run) => run[0].kind === "mail" && run.every((s) => s.count !== undefined)
  ? `${summary} (${plural(run.reduce((t, s) => t + s.count, 0), "result")})` : summary;

function group(steps) {
  const out = [];
  for (let i = 0; i < steps.length;) {
    const s = steps[i];
    if (!("raw" in s)) { out.push(s); i += 1; continue; }
    let j = i + 1;
    while (j < steps.length && "raw" in steps[j] && steps[j].kind === s.kind
           && (["read", "search", "web", "page", "edit"].includes(s.kind) || steps[j].summary === s.summary
               || (s.kind === "mail" && s.q !== undefined && steps[j].q !== undefined))) j += 1;
    const run = steps.slice(i, j);
    const summary = run.length > 1 ? together(run) : null;
    if (run.length > 1 && summary) out.push({ ...s, id: run.map((x) => x.id).join("+"), summary: withCount(summary, run), status: statusOf(run), detail: run.map(detailOf).join("\n\n") });
    else for (const x of run) out.push({ ...x, summary: withCount(x.summary, [x]), detail: detailOf(x) });
    i = j;
  }
  return out;
}

// the steps that are the agent's WORK - what the canvas folds into rows; prose stands on its own
export const isWork = (s) => !["said", "note", "error", "thought"].includes(s.kind);
