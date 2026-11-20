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
import stepKinds from "../../taskuary/stepkinds.json" with { type: "json" };
import ownTools from "../../taskuary/owntools.json" with { type: "json" };
import { forOwner } from "./stepWhy.js";

const flat = (s) => String(s || "").split(/\s+/).join(" ").trim();
const clip = (s, n = 90) => { const t = flat(s); return t.length > n ? `${t.slice(0, n - 1)}…` : t; };
const quoted = (s) => `'${clip(s, 60)}'`;
// ...A PATTERN WRITTEN IN A SEARCH'S OWN SYNTAX is no words to him (design round 4, 2026-11-19: "Searched files for 'import.*spawn|def run\(|...'"):
// only plain words are quoted
const plainPat = (p) => !!p && !/[|\()[\]{}^$*+?]/.test(String(p));
const searched = (p) => (plainPat(p) ? `Searched files for ${quoted(p)}` : "Searched files");
// ...and a file pattern by the words in it (design round 5, 2026-11-19: "Looked for files matching '**/*sync*'"): an ending is the kind of file,
// any other word what its name holds
const globSaid = (g) => { const w = String(g || "").split(/[\/]/).pop().replace(/[*?[\]{}]+/g, " ").trim();
  return /^\.\w{1,8}$/.test(w) ? `Looked for ${w} files` : w && !/\s/.test(w) ? `Looked for files named like ${quoted(w)}` : "Looked for files"; };
const parts = (p) => String(p || "").replace(/[\\/]+$/, "").split(/[\\/]+/).filter(Boolean);
export const baseName = (p) => parts(p).pop() || String(p || "");
// `$d`, `$env:TEMP`, `%TEMP%`: the shell fills these in, so they name nothing a person can read ("Listed the files in $d", 2026-11-03)
const named = (p) => !!p && !/\$|%\w+%/.test(String(p));
// A FILE TASKUARY SEEDED FOR THE TASK reads as what is in it, never its name (the walk, 2026-11-17: "Reading TQ-0006.stranger.md"):
// origin.stranger_file_path names it, and it holds the sender's own words
const seeded = (f) => /^TQ-\d+\.stranger\.md$/i.test(baseName(f));
// what reading a file said, by whichever tool read it - a Read call or a `cat` in a shell
const readSaid = (f) => (seeded(f) ? "Read what the sender wrote" : named(f) ? `Read ${baseName(f)}` : "Read a file");
const parent = (p) => { const x = parts(p); return x.length > 1 ? x[x.length - 2] : ""; };
// ...past any `user:password@` the address carries: a host is all a person needs, and a sign-in in a URL is a secret
// ...A VALUE THE SHELL FILLS IN AS IT RUNS ("$q" in a loop, "${TERM}", "%Q%") is none the step can say: "Searching your mail for '$q'" stood in
// the steps (design round 6, D3). A price ("$519") is a value all the same
const filled = (v) => (/\$\{?[A-Za-z_]|%[A-Za-z_]\w*%/.test(String(v || "")) ? "" : v);
// ...and never one the shell fills in as it runs ("127.0.0.$i" in a loop - the walk, 2026-11-19): none a step can say (filled)
const hostOf = (u) => filled((/^https?:\/\/(?:[^/@\s]*@)?(?:www\.)?([^/?#:@]+)/i.exec(String(u || "")) || [])[1] || "");
// WHERE A FETCH WENT, host and path (the owner, 2026-11-05: "it has to show what it's working on ... like pulling from url's"): never its query
// string or fragment, where tokens ride, nor a path segment that reads as a key (long, letters and digits mixed)
const KEYLIKE = /^(?=.*\d)(?=.*[A-Za-z])[\w~.=-]{24,}$/;
const unesc = (p) => { try { return decodeURIComponent(p); } catch { return p; } };
export const pageOf = (u) => {
  const m = /^https?:\/\/(?:[^/@\s]*@)?(?:www\.)?([^/?#:@]+)(?::\d+)?([^?#\s]*)/i.exec(String(u || "").trim());
  if (!m || !filled(m[1])) return "";
  const path = m[2].split("/").filter(Boolean).map((p) => (KEYLIKE.test(p) ? "…" : unesc(p))).join("/");
  return clip(path ? `${m[1]}/${path}` : m[1], 64);
};
const key = (name) => String(name || "").toLowerCase().replace(/[^a-z0-9]/g, "");
const prog = (w) => String(w || "").split(/[\\/]/).pop().toLowerCase().replace(/\.(exe|cmd|bat|ps1)$/, "");

// ── a shell command, read the way a person skims it ─────────────────────────────────────────────
// Split at the operators outside quotes; a segment after a pipe only filters what came before it.
// ...and a heredoc's body is the file being written, not commands: its lines read as "and 3 more" steps, its quotes broke the split
const HEREDOC = /<<-?[ \t]*(['"]?)(\w+)\1([^\n]*)\n[\s\S]*?\n[ \t]*\2[ \t]*(?=\n|$)/g;
// ...and a PowerShell here-string (@'...'@ | python -) is the script piped on, never its lines as commands ("Ran from", "Ran import")
const HERESTRING = /@(['"])\r?\n[\s\S]*?\r?\n\1@/g, FED = "__script__";
const segments = (cmd) => {
  const out = []; let cur = "", q = null, piped = false;
  const push = (nextPiped) => { if (cur.trim()) out.push({ text: cur.trim(), piped }); cur = ""; piped = nextPiped; };
  const s = String(cmd || "").replace(HEREDOC, `$3 ${FED}`).replace(HERESTRING, FED);
  for (let i = 0; i < s.length; i += 1) {
    const c = s[i];
    if (q) { if (c === q) q = null; else if (c === "\\" && q === '"') { cur += c + (s[i + 1] || ""); i += 1; continue; } cur += c; continue; }
    if (c === '"' || c === "'") { q = c; cur += c; continue; }
    if (c === "\\" && s[i + 1] === "\n") { i += 1; continue; }
    if ((c === "&" || c === "|") && s[i + 1] === c) { push(false); i += 1; continue; }
    if (c === ";" || c === "\n") { push(false); continue; }
    if (c === "|") { push(true); continue; }
    // ...and a block's braces (`foreach (...) { agent-browser tab $t }`, `function X { ... }`, `if (...) { ... }`): the commands inside are steps of
    // their own, the line opening it none (design round 5, 2026-11-19: "Ran foreach (2 times)", "Running function Inspect-VendorForm") - never a
    // `${var}` or a `{}` an argument carries
    if (c === "{" && /^\s?$/.test(s[i + 1] || "") && /^[\s)]?$/.test(s[i - 1] || "")) { push(false); continue; }
    if (c === "}" && /^[\s;]?$/.test(s[i - 1] || "") && /^[\s;)]?$/.test(s[i + 1] || "")) { push(false); continue; }
    // `2>&1`, `>&2`, `&>`: a redirect, not a command running in the background - its `1` read as a step of its own ("and 1 more")
    if (c === "&" && (s[i - 1] === ">" || s[i + 1] === ">")) { cur += c; continue; }
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
  "if", "fi", "done", "local", "source", ".", "test", "[", "read", "rm", "cp", "mv", "touch", "trap", "unset", "clear", "write-host",
  // ...and PowerShell's own words around a command, and its echo
  "foreach", "elseif", "switch", "try", "catch", "finally", "param", "return", "write-output"]);
const READERS = new Set(["cat", "type", "head", "tail", "sed", "less", "more", "get-content", "gc", "nl", "bat", "awk"]);
const GREPS = new Set(["rg", "grep", "egrep", "fgrep", "findstr", "ag", "ack", "select-string", "sls"]);
const LISTS = new Set(["ls", "dir", "find", "tree", "get-childitem", "gci", "fd"]);
const FETCH = new Set(["curl", "wget", "iwr", "invoke-webrequest", "irm", "invoke-restmethod", "http", "https"]);
const SNIPPET = { python: "Python", python3: "Python", py: "Python", node: "Node", deno: "Deno", ruby: "Ruby", perl: "Perl" };
const LEAD = new Set(["do", "then", "else", "time", "sudo", "env", "!", "{", "(", "exec", "nohup", "xargs"]);
// WHAT A FILE COMMAND DID, in words (ACP step 1, 2026-11-06: an agent's own PowerShell read "Ran remove-item notes.txt", "Ran rename-item
// README.md"). Its targets are its words that are not options. A delete, move or copy is the least step in a line (`minor`: below even
// a snippet - `mkdir out && cp a out && python build.py` reads as the build, as it did when cp was QUIET), but alone it says what it did
const DELETES = new Set(["rm", "del", "erase", "rmdir", "rd", "remove-item", "ri", "unlink"]);
const MOVES = new Set(["mv", "move", "move-item", "mi", "ren", "rename", "rename-item", "rni"]);
const COPIES = new Set(["cp", "copy", "copy-item", "cpi"]);
const APPENDS = new Set(["add-content", "ac"]), WRITES = new Set(["set-content", "sc", "out-file", "new-item", "ni"]);
// where a move went: its new name, or - the same name in another folder - that folder ("Moved README.md to docs/")
const whither = (f, t) => (baseName(f) === baseName(t) && parent(t) ? `${parent(t)}/` : baseName(t));
const fileStep = (p, plain) => {
  const t = plain.filter((x) => !/^\d+$/.test(x)), [a, b] = t, n = (x) => (named(x) ? baseName(x) : "a file");
  if (DELETES.has(p)) return { kind: "delete", summary: t.length > 1 ? `Deleted ${t.length} files` : a ? `Deleted ${n(a)}` : "Deleted a file", file: a, minor: true };
  if (MOVES.has(p)) {
    const renamed = /^ren/.test(p) || (a && b && parent(a) === parent(b));
    return { kind: "move", summary: a && b ? `${renamed ? "Renamed" : "Moved"} ${n(a)} to ${named(b) ? whither(a, b) : "a file"}` : a ? `Moved ${n(a)}` : "Moved a file", file: a, minor: true };
  }
  if (COPIES.has(p)) return { kind: "move", summary: a && b ? `Copied ${n(a)} to ${named(b) ? whither(a, b) : "a file"}` : "Copied a file", file: a, minor: true };
  if (APPENDS.has(p) || WRITES.has(p)) return { kind: "edit", summary: a && named(a) ? `${APPENDS.has(p) ? "Edited" : "Wrote"} ${baseName(a)}` : "Wrote a file", file: a, vague: !named(a) };
  return null;
};

const taskuaryCall = (path, cmd) => {
  const [where, query = ""] = path.split("?");
  const bits = where.split("/").filter(Boolean);
  const param = (k) => { const m = new RegExp(`(?:^|&)${k}=([^&]*)`).exec(query); try { return m ? decodeURIComponent(m[1].replace(/\+/g, " ")) : ""; } catch { return m[1]; } };
  if (bits[0] === "search") { const q = filled(param("q")); return { kind: "mail", summary: q ? `Searched your mail for ${quoted(q)}` : "Searched your mail", q }; }
  if (bits[0] === "tasks" && /^\d+$/.test(bits[1] || "")) return { kind: "task", summary: `Opened TQ-${bits[1].padStart(4, "0")}` };
  if (bits[0] === "tasks") return { kind: "task", summary: "Looked at your task list" };
  if (bits[0] === "messages" && /^\d+$/.test(bits[1] || "")) return { kind: "mail", summary: `Opened message ${bits[1]}` };
  if (bits[0] === "tools" && bits[1] === "run") { const t = (/"type"\s*:\s*"([\w.-]+)"/.exec(cmd) || [])[1]; return { kind: "data", summary: t ? `Looked up data in ${t}` : "Looked up data in a connected system" }; }
  return { kind: "data", summary: `Looked up ${(bits[0] || "data").replace(/[-_]/g, " ")} in Taskuary` };
};

// ...and TASKUARY'S OWN COMMAND, by its flags (cli.py's grammar): "Running taskuary, and 4 more" stood in the steps (the 2026-11-18 walk) - the
// app's own name is never the step, what was asked of it is
const OWN_CLI = { "--search": (v) => ({ kind: "mail", summary: v ? `Searched your mail for ${quoted(v)}` : "Searched your mail" }),
  "--message": () => ({ kind: "mail", summary: "Read a message in full" }), "--memory": () => ({ kind: "data", summary: "Read what you have told it to keep" }),
  "--remember": () => ({ kind: "data", summary: "Kept a fact you told it" }), "--reply": () => ({ kind: "edit", summary: "Drafted the reply" }),
  "--reply-file": () => ({ kind: "edit", summary: "Drafted the reply" }), "--draft": () => ({ kind: "edit", summary: "Drafted an email" }),
  "--draft-file": () => ({ kind: "edit", summary: "Drafted an email" }),
  "--check-back": () => ({ kind: "task", summary: "Set a check-back" }), "--done": () => ({ kind: "task", summary: "Said the task is done" }),
  "--learned": () => ({ kind: "data", summary: "Posted to the Hub" }), "--sign-form": () => ({ kind: "edit", summary: "Filled in a form" }) };
// ...the agent's own note on the wall (--note) is ITS words for what the line is doing: the step, whatever else ran with it (`own`)
OWN_CLI["--note"] = (v) => (v ? { kind: "plan", summary: clip(v, 120), own: true } : { kind: "plan", summary: "Left a note on the wall" });
OWN_CLI["--board"] = () => ({ kind: "data", summary: "Read what earlier agents left on the wall" });
// ...EVERY FLAG OF ITS GRAMMAR SAYS WHAT IT DID (the walk, 2026-11-19: "Looked something up in Taskuary" said nothing)
Object.assign(OWN_CLI, { "--withdraw-draft": () => ({ kind: "edit", summary: "Took back its draft" }),
  "--reply-not-needed": () => ({ kind: "task", summary: "Said no reply is needed" }), "--no-reply": () => ({ kind: "task", summary: "Said no reply is needed" }),
  "--waiting-on": () => ({ kind: "task", summary: "Said what the task waits on" }), "--follow-up": () => ({ kind: "task", summary: "Picked the task up again" }),
  "--propose": () => ({ kind: "task", summary: "Proposed a step for your yes" }), "--slot": () => ({ kind: "edit", summary: "Drafted an email" }),
  "--use-repo": () => ({ kind: "task", summary: "Picked the repository to work in" }), "--guide": (v) => ({ kind: "data", summary: v ? `Read the ${v.replace(/[_-]+/g, " ")} guide` : "Read its instructions" }),
  "--prompts": () => ({ kind: "data", summary: "Read its instructions" }), "--browser": () => ({ kind: "page", summary: "Used the browser" }),
  "--upvote": () => ({ kind: "data", summary: "Voted on a Hub post" }), "--downvote": () => ({ kind: "data", summary: "Voted on a Hub post" }),
  "--comment": () => ({ kind: "data", summary: "Commented on a Hub post" }) });
const ownCli = (args) => { const i = args.findIndex((a) => OWN_CLI[a]), flag = args.find((a) => /^--[a-z]/.test(a));
  return i < 0 ? { kind: "data", summary: flag ? `Asked Taskuary for ${flag.slice(2).replace(/-/g, " ")}` : "Ran Taskuary's command" } : OWN_CLI[args[i]](args[i + 1] && !args[i + 1].startsWith("-") ? filled(args[i + 1]) : ""); };

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
  if (["open", "goto", "navigate"].includes(v)) { const host = hostOf(rest[0]) || hostOf(`https://${rest[0] || ""}`); return step(host ? `Opened ${host} in the browser` : "Opened a page in the browser", { host, doing: host ? `Opening ${host} in the browser` : "Opening a page in the browser" }); }
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

const andList = (xs) => (xs.length < 2 ? xs.join("") : xs.length === 2 ? `${xs[0]} and ${xs[1]}` : `${xs.slice(0, 2).join(", ")} and ${plural(xs.length - 2, "more file")}`);
const commandStep = (cmd, depth = 0) => {
  const found = [], made = new Set();
  for (const seg of segments(cmd)) {
    let w = words(seg.text);
    // ...a piped segment only filters what came before it, and a script handed on (a heredoc, a here-string) is no command of its own
    if (seg.piped || (w[0] === FED && w.length === 1)) continue;
    w = w.filter((x) => x !== FED);
    if (/^[A-Za-z_]\w*=\(/.test(w[0] || "")) continue;                       // an array being set up: H=(-H "...")
    while (w.length && (LEAD.has(w[0]) || /^[A-Za-z_]\w*=/.test(w[0]))) w = w.slice(1);
    if (/^\$[\w:]+$/.test(w[0] || "") && w[1] === "=") w = w.slice(2);       // PowerShell's `$landing = agent-browser snapshot`
    // ...a function the line defines is no step, nor a call of it: its body's commands are (design round 5, 2026-11-19)
    if (prog(w[0]) === "function") { if (w[1]) made.add(prog(w[1])); continue; }
    if (w.length && /^\(+[\w-]/.test(w[0])) w = [w[0].replace(/^\(+/, ""), ...w.slice(1)];       // `(Get-ChildItem ...).Count`
    if (!w.length || !/^[\w.:\/\\~+-]+$/.test(w[0]) || !/[A-Za-z]/.test(w[0])) continue;   // only a word that can name a program (C:\...\cmd.exe too)
    const p = prog(w[0]), args = w.slice(1), plain = args.filter((a) => !a.startsWith("-"));
    if (made.has(p)) continue;
    if (SHELLS.has(p) && depth < 2) {
      const at = args.findIndex((a) => /^(-l?c|-command|\/c)$/i.test(a));
      const inner = at >= 0 ? args.slice(at + 1).join(" ") : "";
      if (inner) { const s = commandStep(inner, depth + 1); if (s) found.push(s); continue; }
    }
    const f = fileStep(p, plain);
    if (f) { found.push(f); continue; }
    if (QUIET.has(p)) continue;
    if (p === "agent-browser" || (["npx", "pnpm", "bunx"].includes(p) && prog(plain[0]) === "agent-browser")) {
      found.push(browserStep(p === "agent-browser" ? args : args.slice(args.indexOf(plain[0]) + 1))); continue;
    }
    if (p === "taskuary") { found.push(ownCli(args)); continue; }
    if (FETCH.has(p)) {
      const url = args.find((a) => /^https?:\/\//i.test(a) || a.includes("/api/"));
      if (!url) { found.push({ kind: "run", summary: `Ran ${p}` }); continue; }
      const api = url.indexOf("/api/"), host = hostOf(url);
      if (api >= 0 && (!host || /^(localhost|127\.0\.0\.1)$/i.test(host))) found.push(taskuaryCall(url.slice(api + 5), seg.text));
      else { const at = pageOf(url); found.push({ kind: "page", summary: at ? `Read ${at}` : "Read a web page", doing: at ? `Reading ${at}` : "Reading a web page", host }); }
      continue;
    }
    // `cat > desk.svg` WRITES desk.svg: it read "Read <<EOF" (the stress test, 2026-11-02)
    const to = args.findIndex((a) => /^>>?$/.test(a)), into = to >= 0 ? args[to + 1] : (args.find((a) => /^>>?[^>&]/.test(a)) || "").replace(/^>+/, "");
    if (READERS.has(p) && into && !/^(\/dev\/null|nul|\$null)$/i.test(into)) { found.push({ kind: "edit", summary: named(into) ? `Wrote ${baseName(into)}` : "Wrote a file", file: into, vague: !named(into) }); continue; }
    // ...its file, never the line count it was given (`Get-Content totals.py -TotalCount 290` read "Read 290")
    const files = plain.filter((a) => !/^\d+$/.test(a));
    if (READERS.has(p) && files.length) { const f = files[files.length - 1]; found.push({ kind: "read", summary: readSaid(f), file: f, vague: !named(f) }); continue; }
    if (GREPS.has(p) || (p === "git" && args[0] === "grep")) {
      const e = args.indexOf("-e"), pat = e >= 0 ? args[e + 1] : plain[p === "git" ? 1 : 0];
      found.push({ kind: "search", summary: searched(pat), pattern: pat, asked: plain }); continue;
    }
    if (LISTS.has(p)) {
      // ...and a pattern (`-Filter 'notes*'`, `ls *.zip`) is what it looked for, never a folder: "Listed the files in notes*" (2026-11-03)
      const d = plain.find((a) => !/[*?]/.test(a)), g = plain.find((a) => /[*?]/.test(a));
      if (g) { found.push({ kind: "list", summary: globSaid(g), vague: true, asked: plain }); continue; }
      // ...and `ls -la notes.zip` looked at one file: "Listed the files in notes.zip" read the zip as a folder
      if (d && named(d) && /\.[A-Za-z0-9]{1,5}$/.test(baseName(d))) { found.push({ kind: "list", summary: `Looked at ${baseName(d)}`, vague: true, asked: plain }); continue; }
      found.push({ kind: "list", summary: !d || d === "." ? "Listed the files here" : named(d) ? `Listed the files in ${baseName(d)}` : "Listed the files", vague: !!d && !named(d), asked: plain });
      continue;
    }
    // ...anything else it ran is shown as the command itself (ranCmd): here it only weighs against the line's other steps - a snippet least
    found.push({ kind: "run", summary: `Ran ${seg.text}`, filler: !!SNIPPET[p] });
  }
  // ...the agent's own words for the line (a wall note) say what all of it was for
  const own = found.find((s) => s.own);
  if (own) return own;
  // a snippet that only reshapes what a fetch brought back is not a step of its own
  const real = found.filter((s) => !s.filler && !s.minor), more = found.filter((s) => !s.minor);
  // ...and the same words once: two looks at the page are "Looked at the page", never "..., and 1 more"
  const all = real.length ? real : more.length ? more : found, use = all.filter((s, i) => all.findIndex((x) => x.summary === s.summary) === i);
  if (!use.length) return null;
  // ...files it read in one line are named together: "Read totals.py and notes.sql"
  const reads = use[0].kind === "read" ? use.filter((s) => s.kind === "read" && !s.vague) : [], rest = use.length - Math.max(reads.length, 1);
  const lead = reads.length > 1 ? `Read ${andList([...new Set(reads.map((s) => baseName(s.file)))])}` : use[0].summary;
  return { ...use[0], summary: rest > 0 ? `${lead}, and ${rest} more` : lead };
};

// A COMMAND WITH NO WORDS OF ITS OWN IS SHOWN AS ITSELF (the owner, 2026-11-19: "Ran a command", "Ran git", "Ran foreach, and 1 more" - "If not exact
// detail show what it's doing? other chats do this description thing much better"): the line the shell was handed, short, in a code span
// (`code`); a script of many lines by its language and length - the language of the program that runs it, read off the command, never its words
const LANG = { ...SNIPPET, bash: "Bash", sh: "shell", zsh: "Zsh", powershell: "PowerShell", pwsh: "PowerShell", cmd: "batch" };
const unq = (t) => (/^"[\s\S]*"$/.test(t) ? t.slice(1, -1).replace(/\\"/g, '"') : /^'[\s\S]*'$/.test(t) ? t.slice(1, -1) : t);
// ...the shell it was handed to is no part of it: Codex's `powershell.exe -Command "..."`, `bash -lc '...'`, `cmd /c ...`, as a string or an array
const unwrap = (cmd) => {
  const xs = Array.isArray(cmd) ? cmd.map(String) : null, at = xs ? xs.findIndex((a) => /^(-l?c|-command|\/c)$/i.test(a)) : -1;
  if (xs && at > 0 && SHELLS.has(prog(xs[0]))) return { text: xs.slice(at + 1).join(" "), shell: prog(xs[0]) };
  const s = xs ? xs.join(" ") : String(cmd || "");
  const m = /^\s*("[^"]+"|'[^']+'|\S+)(?:\s+-(?!l?c\b|command\b)\w+)*\s+(-l?c|-command|\/c)\s+([\s\S]+)$/i.exec(s), sh = m && prog(unq(m[1]));
  return m && SHELLS.has(sh) ? { text: unq(m[3].trim()), shell: sh } : { text: s, shell: "" };
};
const ranCmd = (cmd, tool) => {
  const { text, shell } = unwrap(cmd), t = text.replace(/\r/g, "").trim(), lines = t.split("\n").filter((l) => l.trim());
  if (!t) return { kind: "run", summary: "Ran a command it did not show" };
  if (lines.length === 1) { const code = clip(t, 80); return { kind: "run", summary: `Ran ${code}`, code }; }
  // ...a script fed to a program (a heredoc, a here-string piped on, `python -c "..."`) is in that program's language, and only its body counts
  const fedTo = (/^['"]@\s*\|\s*(\S+)/m.exec(t) || [])[1], first = prog(words(lines[0])[0] || ""), body = t.match(HEREDOC) || t.match(HERESTRING);
  const lang = LANG[prog(fedTo || "")] || (SNIPPET[first] && LANG[first]) || LANG[shell] || LANG[first] || LANG[key(tool)];
  const n = body ? body[0].split("\n").length - 2 : lines.length;
  return { kind: "run", summary: `Ran ${lang ? `a ${lang} script` : "a script"} (${plural(n, "line")})` };
};

// ── a tool call, by its name and arguments ───────────────────────────────────────────────────────
const fileOf = (a) => a.file_path || a.filePath || a.absolute_path || a.path || a.file || a.notebook_path || "";
const firstUrl = (s) => (/https?:\/\/[^\s"')]+/.exec(String(s || "")) || [])[0] || "";
const TOOLS = {
  read: ["read", "readfile", "view", "readmanyfiles", "openfile", "catfile", "fileread"],
  search: ["grep", "searchfilecontent", "searchtext", "rg", "codebasesearch", "grepsearch"],
  list: ["glob", "ls", "listdirectory", "listdir", "list", "find", "findfiles", "fileslist"],
  web: ["websearch", "googlewebsearch", "searchweb", "googlesearch", "webquery"],
  page: ["webfetch", "fetch", "fetchurl", "readurl", "browse", "openurl"],
  run: ["bash", "shell", "runshellcommand", "execute", "shellcommand", "powershell", "terminal", "execcommand", "runcommand", "localshell"],
  edit: ["edit", "multiedit", "replace", "strreplace", "strreplacebasededittool", "applypatch", "notebookedit", "filechange", "patch", "fileedit"],
  write: ["write", "writefile", "createfile", "filewrite"],
  helper: ["task", "agent", "subagent", "dispatchagent"],
  // ACP's own kinds for a tool call (agents.ACPSteps names a call by its kind when the agent gives no tool name)
  delete: ["delete", "deletefile", "removefile"],
  move: ["move", "movefile", "renamefile"],
  think: ["think"],
  plan: ["todowrite", "updateplan", "plan", "todoread"],
  sync: ["syncmessages"],
};
const SHOWN = { table: "a table", chart: "a chart", checklist: "a checklist", list: "a list", steps: "the steps", stats: "the figures" };
const asked = (w) => (w ? ` for ${quoted(w)}` : ""), asking = (w) => (w ? ` for "${clip(w, 60)}"` : "");
const OWN = {
  mytask: () => ({ kind: "task", summary: "Looked at the task's emails" }),
  searchmessages: (a) => ({ kind: "mail", summary: `Searched your mail${asked(a.words || a.subject || a.sender)}`,
    doing: `Searching your mail${asking(a.words || a.subject || a.sender)}`, q: a.words || a.subject || a.sender || "" }),
  readmessage: () => ({ kind: "mail", summary: "Read an email" }),
  readattachment: () => ({ kind: "read", summary: "Read an attachment" }),
  searchtasks: (a) => ({ kind: "task", summary: `Searched your tasks${asked(a.words)}`, doing: `Searching your tasks${asking(a.words)}` }),
  person: (a) => ({ kind: "mail", summary: a.name ? `Looked up ${clip(a.name, 40)} in your mail` : "Looked up a person in your mail" }),
  searchknowledge: (a) => ({ kind: "read", summary: `Searched your documents${asked(a.text)}`, doing: `Searching your documents${asking(a.text)}` }),
  ownermemory: () => ({ kind: "data", summary: "Read what Taskuary has learned about you" }),
  calendar: () => ({ kind: "data", summary: "Looked at your calendar" }),
  listsystems: () => ({ kind: "data", summary: "Looked at your connected systems" }),
  runsystem: (a) => ({ kind: "data", summary: a.type ? `Looked up data in ${clip(a.type, 30)}` : "Looked up data in a connected system" }),
  proposereply: () => ({ kind: "edit", summary: "Drafted a reply" }),
  proposeemail: () => ({ kind: "edit", summary: "Drafted an email" }),
  replynotneeded: () => ({ kind: "plan", summary: "Marked the reply as not needed" }),
  signform: () => ({ kind: "edit", summary: "Filled in and signed a form" }),
  propose: () => ({ kind: "plan", summary: "Asked for your yes" }),
  // ...a view by what it shows - its own title, the file it put up, its kind - never "a view" (the walk, 2026-11-17: "Showing you a view")
  show: (a) => { const el = a.elements?.[a.root] || {}, t = a.title || el.props?.title, fs = [a.files || []].flat().filter(Boolean);
    return { kind: "plan", summary: t ? `Showed you ${quoted(t)}` : fs.length ? `Showed you ${baseName(fs[0])}${fs.length > 1 ? `, and ${fs.length - 1} more` : ""}`
      : SHOWN[el.type] ? `Showed you ${SHOWN[el.type]}` : "Laid it out for you" }; },
  // ...and where it works (repochoice.py): the one line the chat shows for the agent's pick - "Working in northwind/ledger - <why>"
  userepo: (a) => { const w = String(a.path_or_name || "").trim(), at = /[\\/]/.test(w) && !/^[\w.-]+\/[\w.-]+$/.test(w) ? baseName(w) : w;
    return { kind: "plan", summary: `Working in ${at || "a checkout"}${a.why ? ` - ${clip(a.why, 100)}` : ""}` }; },
  findrepos: (a) => ({ kind: "list", summary: `Looked for the code on this computer${asked(a.query)}` }),
  // ...AND EVERY OTHER TOOL OF ITS OWN, by what it did (design round 4, 2026-11-19): the rest fell to "Used <name> (taskuary) on ..."
  guide: () => ({ kind: "read", summary: "Read how Taskuary does it" }),
  remember: () => ({ kind: "data", summary: "Kept a fact you told it" }),
  todos: () => ({ kind: "plan", summary: "Updated the to-do list" }),
  checkback: (a) => ({ kind: "task", summary: a.when ? `Set itself to look again ${clip(a.when, 30)}` : "Set itself to look again later" }),
  remind: (a) => ({ kind: "task", summary: a.when ? `Set a reminder for ${clip(a.when, 30)}` : "Set a reminder" }),
  newtask: (a) => ({ kind: "task", summary: a.title ? `Started a task: ${clip(a.title, 60)}` : "Started a task of its own" }),
  askstronger: () => ({ kind: "plan", summary: "Asked for a second opinion" }),
  notepeers: () => ({ kind: "plan", summary: "Left a note for another agent" }),
  proposeland: () => ({ kind: "plan", summary: "Set up how the work lands" }),
  withdrawdraft: () => ({ kind: "plan", summary: "Took back something it had set up" }),
  answerinvite: (a) => ({ kind: "edit", summary: a.answer ? `Set up the answer to the invite (${clip(a.answer, 20)})` : "Set up the answer to the invite" }),
  setupmeeting: () => ({ kind: "edit", summary: "Set up a meeting" }),
  share: () => ({ kind: "edit", summary: "Set up a share" }),
};
// ...AND AN AI CARD'S OWN HANDS (apiagent.py) in the words the CLI's take (design round 5, 2026-11-19: the API walk read "Used browser open on ..."):
// its browser through the browser's own grammar, the sign-up and its tool finder by what they did
const API_HANDS = {
  browseropen: (a) => browserStep(["open", a.url || ""]), browserlook: () => browserStep(["snapshot"]), browserclick: () => browserStep(["click"]),
  browserfill: () => browserStep(["fill"]), browserpress: () => browserStep(["press"]), browserscreenshot: () => browserStep(["screenshot"]),
  browsersignup: () => ({ kind: "page", summary: "Sent the sign-up form", browser: true }),
  findtools: () => ({ kind: "plan", summary: "Looked for the right tool" }),
};
const KIND = Object.fromEntries(Object.entries(TOOLS).flatMap(([k, names]) => names.map((n) => [n, k])));

// ...and every label is built from PARSED arguments: a call whose arguments came as a JSON string (Codex's function_call, an OpenAI-style
// tool call) read as none, so a draft fell through to "Running a command" and a write to its own text (the walk, 2026-11-17)
const parsed = (x) => { if (typeof x !== "string") return x && typeof x === "object" ? x : {}; try { const j = JSON.parse(x); return j && typeof j === "object" ? j : {}; } catch { return {}; } };
// a server's tool by its own name: Claude's mcp__server__tool, and Codex's server__tool
const serverOf = (name) => /^(?:mcp__)?(.+?)__(.+)$/.exec(String(name || ""));
// ...and whether a call is one of Taskuary's own tools: its server is taskuary, or a bare name of the tool table (owntools.json, pinned to
// agenttools.TOOLS: the general agent's calls carry no server) - the one kind of step whose output is a Taskuary refusal, with the agent's own
// NEXT_STEP line (stepWhy.whyFailed). Never OWN: that is the labels this page has words for, and 14 tools had none (the robustness judge)
const OWN_NAMES = new Set(ownTools.tools);
export const ownTool = (name) => { const mcp = serverOf(name); return mcp ? key(mcp[1]) === "taskuary" : OWN_NAMES.has(String(name || "")); };
export const describeCall = (name, args = {}) => {
  const a = parsed(args);
  const mcp = serverOf(name);
  // TASKUARY'S OWN TOOLS (agenttools.TOOLS), by what each one is for, BEFORE any guess from its arguments: a draft kept without them was
  // read as a command ("Running a command" for an email, 2026-11-17)
  const own = OWN[key(mcp ? mcp[2] : name)];
  if (!mcp && API_HANDS[key(name)]) return API_HANDS[key(name)](a);
  if (own && (!mcp || key(mcp[1]) === "taskuary")) return own(a);
  let kind = KIND[key(mcp ? mcp[2] : name)] || "";
  // ...a helper an ACP agent started names itself by where it runs (codex-acp's "Start subagent history_probe", agentPath /root/history_probe)
  if (!kind && a.agentPath) return { kind: "helper", summary: `Handed part of the work to a helper: ${clip(baseName(a.agentPath).replace(/[_-]+/g, " "), 60)}` };
  // an ACP "search" is either kind, and says which by what it was given: a pattern searches files, a query searches the web
  if (kind === "search" && a.query && !a.pattern) kind = "web";
  if (key(name) === "search" && !kind) kind = a.pattern ? "search" : "web";
  const cmd = a.command || a.cmd || a.script;
  if (kind === "run" || (!kind && cmd)) {
    // ...A LINE CUT SHORT FOR THE CHAT (sessionrecord.ARG_N, its "…") IS NOT READ AS IF IT WERE WHOLE (walk 8, 2026-11-20: a script's edits, cut
    // mid-quote, read 'Read f"Headcount {hc} (…'): its own words say it, else the line itself
    const line = Array.isArray(cmd) ? cmd.join(" ") : String(cmd), s = line.endsWith("…") ? null : commandStep(line);
    // ...Claude's own words for a browser step ("Press the pay button for invoice INV-1001") say more than the verb does
    // ...and so do its words for a step whose file or folder the shell had yet to fill in ($d)
    if (s && s.kind !== "run" && !((s.browser || s.vague) && a.description)) return s;
    if (a.description) return { kind: s?.browser ? "page" : s?.vague ? s.kind : "run", summary: clip(a.description), ...(s?.vague && s.asked ? { asked: s.asked } : {}) };
    return ranCmd(cmd, name);
  }
  if (kind === "read") { const f = fileOf(a); return { kind, summary: f ? readSaid(f) : "Read a file", file: f }; }
  if (kind === "search") { const pat = a.pattern || a.query || a.regex; return { kind, summary: searched(pat), pattern: pat }; }
  if (kind === "list") { const g = a.pattern || a.glob, d = a.path || a.dir_path || a.directory; return { kind, summary: g ? globSaid(g) : d ? `Listed the files in ${baseName(d)}` : "Listed the files" }; }
  if (kind === "web") { const q = a.query || a.q || a.search_term;
    return { kind, summary: q ? `Searched the web for ${quoted(q)}` : "Searched the web", doing: q ? `Searching the web for "${clip(q, 60)}"` : "Searching the web", q }; }
  if (kind === "page") { const u = a.url || firstUrl(a.prompt), at = pageOf(u);
    return { kind, summary: at ? `Read ${at}` : "Read a web page", doing: at ? `Reading ${at}` : "Reading a web page", host: hostOf(u) }; }
  if (kind === "edit" || kind === "write") {
    const changes = Array.isArray(a.changes) ? a.changes : [];
    if (changes.length > 1) return { kind: "edit", summary: `Changed ${changes.length} files` };
    const f = fileOf(a) || changes[0]?.path || "";
    return { kind: "edit", summary: f ? `${kind === "write" ? "Wrote" : "Edited"} ${baseName(f)}` : "Changed a file", file: f };
  }
  if (kind === "delete") { const f = fileOf(a); return { kind, summary: named(f) ? `Deleted ${baseName(f)}` : "Deleted a file", file: f }; }
  if (kind === "move") {
    const f = fileOf(a) || a.source || a.from, t = a.to || a.destination || a.new_path || a.newPath;
    return { kind, summary: named(f) && named(t) ? `Moved ${baseName(f)} to ${whither(f, t)}` : named(f) ? `Moved ${baseName(f)}` : "Moved a file", file: f };
  }
  // a model's planning step: the agent's own title for it says what it thought about ("Planning the budget summary")
  if (kind === "think") return { kind: "plan", summary: a.title && !/^think$/i.test(a.title) ? clip(a.title, 80) : "Thought it through" };
  if (kind === "helper") return { kind, summary: a.description ? `Handed part of the work to a helper: ${clip(a.description, 70)}` : "Handed part of the work to a helper" };
  if (kind === "plan") { const n = (a.todos || a.plan || []).length; return { kind, summary: n ? `Updated its plan (${n} steps)` : "Updated its plan" }; }
  // ...whatever channel the task came in on - a WhatsApp task read "Checking for new mail" (the owner, 2026-11-05: "this is not mail")
  if (kind === "sync") return { kind, summary: a.new ? `Found ${plural(a.new, "new message")} on the thread` : "Checked the thread for new messages" };
  // ...an ACP call named only by its title is in words already - the agent's own ("Checking the build output"), never "Used <them>"
  // - kept as its name (conversation.acp_steps) or beside the kind "other" (agents.ACPSteps)
  const titled = a.title || (/\s/.test(String(name || "").trim()) && !Object.values(a).some(Boolean) ? name : "");
  if (!mcp && titled && ["other", key(titled)].includes(key(name))) return { kind: "tool", summary: clip(titled) };
  // anything else: its own name in words, and the one argument a person would want - a query, a host, a file
  const label = String(mcp ? mcp[2] : a.title || name || "a tool").replace(/[_-]+/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2").trim();
  const target = a.query ? quoted(a.query) : hostOf(a.url) || (fileOf(a) ? baseName(fileOf(a)) : "");
  return { kind: "tool", summary: `Used ${label}${mcp ? ` (${mcp[1].replace(/[_-]+/g, " ")})` : ""}${target ? ` on ${target}` : ""}` };
};

// WHAT IT IS DOING NOW, said as it happens (the owner, 2026-11-05: "look how other chat libraries show intermediately the tool calls"): a step's
// own `doing` where its words differ ("Searching the web for "…""), else its summary's verb in the present - "Read notes.md" is "Reading notes.md"
const ING = { Read: "Reading", Searched: "Searching", Wrote: "Writing", Edited: "Editing", Ran: "Running", Opened: "Opening", Looked: "Looking",
  Listed: "Listing", Changed: "Changing", Typed: "Typing", Clicked: "Clicking", Used: "Using", Handed: "Handing", Updated: "Updating",
  Checked: "Checking", Went: "Going", Reloaded: "Reloading", Scrolled: "Scrolling", Closed: "Closing", Pressed: "Pressing", Ticked: "Ticking",
  Unticked: "Unticking", Chose: "Choosing", Uploaded: "Uploading", Saved: "Saving", Started: "Starting", Drafted: "Drafting", Marked: "Marking",
  Filled: "Filling", Asked: "Asking", Showed: "Showing", Deleted: "Deleting", Moved: "Moving", Renamed: "Renaming", Copied: "Copying",
  Thought: "Thinking", Laid: "Laying" };
export const present = (s) => { const t = String(s || ""), m = /^([A-Z][a-z]+)\b/.exec(t); return m && ING[m[1]] ? ING[m[1]] + t.slice(m[1].length) : t; };
// the row's words: what it is doing while it runs, what it did once done
export const stepLabel = (s) => (s?.status === "running" ? s.doing || present(s.summary) : s?.summary || "");

// a mail search's own answer says how many it found - read off the JSON it returned, when it is JSON
const countOf = (out) => {
  let j; try { j = JSON.parse(String(out || "").replace(/ ⏎ /g, "\n")); } catch { return null; }
  const list = Array.isArray(j) ? j : ["data", "results", "items", "messages", "hits"].map((k) => j?.[k]).find(Array.isArray);
  return list ? list.length : null;
};
const rawOf = (name, args) => {
  const a = parsed(args);
  const cmd = a.command || a.cmd;
  if (cmd) return `$ ${Array.isArray(cmd) ? cmd.join(" ") : cmd}`;
  return `${name} ${JSON.stringify(a, null, 2)}`;
};

// A LOOK THAT FOUND NOTHING ANSWERED (the desktop stress test, 2026-11-03): `ls notes*` with no match exits non-zero, and red "failed"
// read as something gone wrong. A list or search step that says nothing past its exit code, or whose every line is the OS saying the
// very thing it was asked for is not there, found none. Any other line - a flag it did not take, a folder it was not asked about, and
// a refusal like Permission denied even on the path it was asked for (the owner, 2026-11-03) - is a failure
const NOT_THERE = /no such file or directory|cannot find (the )?(path|file)|does not exist|file not found|no matches found/i;
const foundNone = (s) => {
  if (!["list", "search"].includes(s.kind)) return false;
  const lines = s.output.split(/\r?\n| ⏎ /).map((l) => l.trim()).filter((l) => l && !/^exit code -?\d+$/i.test(l));
  const asked = (s.asked || []).map((a) => String(a).replace(/^['"]|['"]$/g, "")).filter((a) => a.length > 1);
  return lines.every((l) => NOT_THERE.test(l) && asked.some((a) => l.includes(a) || l.includes(baseName(a))));
};

// ── the trace, as steps ──────────────────────────────────────────────────────────────────────────
// a thought's paragraphs, each one line - a header the model set in bold (Codex's `**Checking the dates**`) reads as its words
const thoughtsOf = (text) => String(text || "").split(/\n\s*\n/).map((p) => flat(forScreen(p)).replace(/^\*\*(.+)\*\*$/, "$1")).filter(Boolean);
const ECHO = /^(→ |· |✗ |session started\b)/;            // agents._live_line's own rows for a tool call, its result, the init line
// A QUICK ANSWER'S RAW OBJECT (selfclose.RAW, stored before 2026-11-13) is its fields, filed as the answer - never words of its working, whichever line carries it: a
// CLI's readable `live` line was the object cut at 300 characters, drawn under Taskuary (the owner, 2026-11-03)
const RETRY = /^Can't reach Claude's servers right now/;      // agents._live_line's line for Claude's own api_retry
const QUICK_RAW =/^\s*(?:```(?:json)?\s*)?\{\s*"(?:report|draft|question|done|escalate|why)"\s*:/i;
// a CLI's own plumbing, never a step of the work: Claude's ToolSearch loads a tool it has not loaded yet ("Used Tool Search on
// 'select:WebSearch'", ACP step 1, 2026-11-06) - the call it loads it for is the step. ONE LIST, the server's too (conversation._said, the walks
// 2026-11-17): it kept a stopped turn for a ToolSearch this page drew as nothing - a "1 step" trail for 100 ms, then gone
const MACHINERY = new Set(stepKinds.machinery);
// ...and a shell line of Taskuary's own that is no step either - a tick (stepkinds.json `commands`): a to-do ticked is never narrated
const TICK = new RegExp(stepKinds.commands, "i");
export function stepsOf(trace, { answer = "", keepStart = true } = {}) {
  const events = trace || [];
  // A structured backend says everything twice: its tool call and text as events, and the same again as readable `live` lines for
  // the terminal pane. Only a CLI that streams nothing structured is read off its lines - decided over the whole trace, not by
  // which came first, so the line written before the first tool call no longer slipped into the box as raw text.
  const structured = events.some((e) => e?.type === "tool_call" || e?.type === "progress");
  const steps = [], byId = new Map(), called = new Set();
  const say = (kind, text) => {
    const t = forScreen(text);
    if (!t || QUICK_RAW.test(t)) return;
    const last = steps[steps.length - 1];
    // ...and Claude's retries while it cannot reach its servers are ONE line, the newest try's: each was appended to the last, seven
    // "Can't reach Claude's servers ... (n of 10)" run together under Taskuary (the desktop run, 2026-11-04)
    if (RETRY.test(t)) {
      const was = steps.find((x) => x.retry);
      if (was) was.summary = t; else steps.push({ id: `retry-${steps.length}`, kind: "note", summary: t, detail: "", status: "done", retry: true });
      return;
    }
    if (kind === "said" && last?.kind === "said" && last.live) { last.summary += `\n${t}`; return; }
    steps.push({ id: `${kind}-${steps.length}`, kind, summary: t, detail: "", status: "done", live: kind === "said" && !structured });
  };
  // ...EACH THOUGHT ITS OWN ROW (the owner's live turn, 2026-11-18: "Reviewing the vendor snapshots Planning the roll-up"): a message of
  // reasoning holds its paragraphs - Codex sends a header each - and flattened they ran together as one sentence
  const think = (ts, live) => ts.forEach((t) => steps.push({ id: `thought-${steps.length}`, kind: "thought", summary: clip(t, 140), detail: t.length > 140 ? t : "", status: "done", ...(live ? { live } : {}) }));
  const dropLive = () => { while (steps.at(-1)?.kind === "thought" && steps.at(-1).live) steps.pop(); };
  for (const e of events) {
    if (!e) continue;
    if (e.type === "tool_call") {
      const args = e.detail?.args || e.detail || {};
      called.add(e.name);
      if (MACHINERY.has(key(String(e.name || "").split("__").pop())) || TICK.test([parsed(args).command || parsed(args).cmd || ""].flat().join(" "))) continue;
      const id = e.detail?.tool_call_id || `${e.name}-${steps.length}`;
      const d = describeCall(e.name, args);
      // ...its outcome in a few words and the same call made again, as the server's one reading of the turn says (chatlog.tool_rows)
      const step = { id, ...d, tool: e.name, raw: rawOf(e.name || "tool", args), output: String(e.detail?.output || ""), status: "running", own: ownTool(e.name),
        ...(e.detail?.outcome ? { outcome: e.detail.outcome } : {}), ...(e.detail?.why ? { why: e.detail.why } : {}), ...(e.detail?.times > 1 ? { times: e.detail.times } : {}),
        ...(d.kind === "helper" && args.description ? { task: clip(args.description, 70) } : {}) };
      // A HELPER'S OWN CALLS GO UNDER ITS ROW (the owner, 2026-11-06: "it's spinning but not the last thing ... shouldn't it be in order? unless
      // it's in parallel"): a call naming the helper call it runs under (`parent`: stream-json's parent_tool_use_id, ACP's parentToolUseId)
      // is that helper's step, never one of the main agent's interleaved with it
      const host = e.detail?.parent && byId.get(e.detail.parent);
      byId.set(id, step);
      if (host) (host.kids ||= []).push(step); else steps.push(step);
    } else if (e.type === "tool_result") {
      const step = byId.get(e.detail?.tool_call_id || e.name);
      if (!step) continue;
      step.output = String(e.detail?.result || "") || step.erred || "";
      if (step.erred) continue;
      // a step Taskuary HELD for the owner's yes (shellgate, browsergate) did not fail: it waits - red "failed" over a held delete read
      // as something gone wrong (the desktop stress test, 2026-11-03); a call the server marked as put to the owner says how it stands (`state`)
      step.status = e.detail?.state || (!e.detail?.is_error ? "done" : /Taskuary held this for the owner/.test(step.output) ? "held" : foundNone(step) ? "none" : "error");
      if (step.kind === "mail" && step.q !== undefined) { const n = countOf(step.output); if (n !== null) step.count = n; }
    } else if (e.type === "progress" && e.detail) {
      const name = String(e.name || "");
      if (name === "thinking" || name === "reasoning") {
        const ts = thoughtsOf(e.detail);
        if (ts.length) dropLive();     // ...the whole paragraph in its snapshots' place
        think(ts, false);
      } else if (name === "text" || name === "agent_message") say("said", e.detail);
      else say("note", e.detail);
    } else if (e.type === "live" && e.name === "writing") {
      // ...the answer as it streams is the turn's line of what it is doing (conversation `doing`), never words drawn twice
    } else if (e.type === "live" && e.name === "thinking") {
      // ...a thought still being written (agents.ACPSteps): ONE open thought its snapshots update, never words said
      const ts = thoughtsOf(e.detail || "");
      if (ts.length) { dropLive(); think(ts, true); }
    } else if (e.type === "live" && !structured && e.detail && !ECHO.test(String(e.detail))) {
      say("said", e.detail);
    } else if (e.type === "start" && keepStart) {
      steps.push({ id: `start-${steps.length}`, kind: "note", summary: `Started ${e.session?.provider || "the selected agent"}`, detail: "", status: "done" });
    } else if (e.type === "error") {
      // ...A FAILED CALL IS ITS OWN STEP, FAILED: one plain line, its output folded under it (design round 4, 2026-11-19: a filed turn kept the
      // failure as a note of its own, "⚠ Exit code 127 ⏎ which: no python3 in (...a PATH 600 characters long)", red under "Ran which python3")
      const call = e.name && [...byId.values()].reverse().find((s) => s.tool === e.name && s.status !== "error");
      // ...whichever comes first: the chat hands a turn's results in after its calls (chatStream.turnParts), so the result never undoes it
      if (call) { call.status = "error"; call.erred = String(e.detail?.result || e.error || ""); call.output = call.erred || call.output; continue; }
      // ...A TOOL'S REFUSAL IS THE AGENT'S (design round 5, 2026-11-19: a tick refused for a missing argument stood in the chat as "⚠ ``` `item`
      // was not given Next: call tick again ... The input schema is: {...}"): one a call of this turn names - a plumbing call no row stands
      // for, or one already failed - reaches the agent only; he sees at most its row, retried
      if (e.name && called.has(e.name)) continue;
      // ...one no call names says what happened, never the agent's next step (stepWhy.forOwner)
      steps.push({ id: `error-${steps.length}`, kind: "error", summary: `⚠ ${forOwner(e.detail?.result || e.error, ownTool(e.name)) || "Taskuary could not answer."}`, detail: "", status: "error" });
    }
  }
  // what it said that the answer says again is the answer: a CLI's final text streams in as progress too
  // ...paragraph by paragraph: the streamed text has the reply draft taken out where the filed answer keeps it, so the whole never
  // matched and a general turn's answer showed twice, once without its draft and once with it (the overnight QA, 2026-10-30)
  // A RETRY THAT WORKED IS NO FAILURE (the stress test, 2026-11-02): the agent's own retried steps wore red "failed" though it recovered.
  // A failed call the same step later did without error is `recovered` - a quiet word; red stays for a failure nothing made good
  steps.forEach((s, i) => { if (s.status === "error" && "raw" in s
    && steps.slice(i + 1).some((x) => "raw" in x && x.kind === s.kind && x.summary === s.summary && x.status === "done")) s.status = "recovered"; });
  // ...and a call STILL AT WORK while a later one already finished runs ALONGSIDE them - in parallel, said so; steps stay in the order they began
  steps.forEach((s, i) => { if (s.status === "running" && "raw" in s && steps.slice(i + 1).some((x) => "raw" in x && x.status !== "running")) s.alongside = true; });
  const said = flat(forScreen(answer));
  const inAnswer = (t) => { const ps = String(t || "").split(/\n\s*\n/).map(flat).filter(Boolean); return ps.length > 0 && ps.every((p) => said.includes(p)); };
  const kept = said ? steps.filter((s) => s.kind !== "said" || !inAnswer(s.summary)) : steps;
  return group(kept).map(tidy);
}
const tidy = ({ raw, output, live, q, host, file, pattern, count, asked, retry, kids, task, ...s }) => {
  if (s.kind !== "helper" || !(kids?.length || task)) return s;
  // ...a helper reads by its own work: at it, "Handing part of the work to a helper: …"; done, the work itself in plain words - "Fetch Boston
  // catering prices · 4 steps" (walk 5, 2026-11-19: "helper: … (done)" said the machinery, not the work) - its steps under it
  const ks = kids?.length ? group(kids).map(tidy) : [], n = ks.filter(isWork).length;
  const summary = s.status === "running" ? s.summary : `${task || "Part of the work"}${s.status === "error" ? " - it did not finish" : ""}${n ? ` · ${plural(n, "step")}` : ""}`;
  return { ...s, summary, ...(ks.length ? { kids: ks } : {}) };
};

// ── consecutive calls of one kind read as one line ───────────────────────────────────────────────
const listOf = (xs, n = 3) => { const u = [...new Set(xs.filter(Boolean))]; return u.length > n ? `${u.slice(0, n).join(", ")} and ${u.length - n} more` : u.join(", "); };
const together = (run) => {
  const k = run[0].kind, n = run.length;
  // ...by their names, never the folder they sit in (walk 8: "Read 2 files in TQ-0001/" - the task's own outputs folder, Taskuary's word)
  if (k === "read") return run.every((s) => named(s.file)) ? `Read ${andList([...new Set(run.map((s) => baseName(s.file)))])}` : `Read ${n} files`;
  if (k === "search") { const ws = listOf(run.map((s) => plainPat(s.pattern) && quoted(s.pattern))); return ws ? `Searched files for ${ws}` : "Searched files"; }
  if (k === "web") return `Searched the web for ${listOf(run.map((s) => s.q && quoted(s.q)))}`;
  // ...pages read, never the agent's own browser at work: two looks at its page read "Read 2 web pages" (design round 5, 2026-11-19)
  if (k === "page" && !run.some((s) => s.browser)) { const h = [...new Set(run.map((s) => s.host).filter(Boolean))]; return h.length === 1 ? `Read ${n} pages on ${h[0]}` : h.length ? `Read ${n} pages (${listOf(h)})` : `Read ${n} web pages`; }
  if (k === "mail" && run.every((s) => s.q !== undefined)) return `Searched your mail for ${listOf(run.map((s) => s.q && !s.q.includes("$") && quoted(s.q)))}`;
  if (k === "edit") return `Changed ${n} files`;
  return run.every((s) => s.summary === run[0].summary) ? `${run[0].summary} (${n} times)` : null;
};
const statusOf = (run) => run.some((s) => s.status === "running") ? "running" : run.some((s) => s.status === "error") ? "error"
  : run.some((s) => s.status === "held") ? "held" : run.some((s) => s.status === "refused") ? "refused" : run.some((s) => s.status === "recovered") ? "recovered" : run.every((s) => s.status === "none") ? "none" : "done";
const detailOf = (s) => [s.raw, s.output && `→ ${s.output.length > 1500 ? `${s.output.slice(0, 1500)}…` : s.output}`].filter(Boolean).join("\n");
const withCount = (summary, run) => run[0].kind === "mail" && run.every((s) => s.count !== undefined)
  ? `${summary} (${plural(run.reduce((t, s) => t + s.count, 0), "result")})` : summary;

function group(steps) {
  const out = [];
  for (let i = 0; i < steps.length;) {
    const s = steps[i];
    if (!("raw" in s) || s.kids?.length) { out.push(s); i += 1; continue; }
    let j = i + 1;
    while (j < steps.length && "raw" in steps[j] && !steps[j].kids?.length && steps[j].kind === s.kind
           // ..."(2 times)" only for the same command: two scripts of one length are two
           && (["read", "search", "web", "page", "edit"].includes(s.kind) || (steps[j].summary === s.summary && (s.kind !== "run" || steps[j].raw === s.raw))
               || (s.kind === "mail" && s.q !== undefined && steps[j].q !== undefined))) j += 1;
    const run = steps.slice(i, j);
    const summary = run.length > 1 ? together(run) : null;
    // ...and a run still under way is doing its NEWEST call: "Reading 3 files" said less than "Reading BudgetTable.js"
    const last = run[run.length - 1], doing = last.status === "running" ? last.doing || present(last.summary) : present(summary || "");
    if (run.length > 1 && summary) out.push({ ...s, id: run.map((x) => x.id).join("+"), summary: withCount(summary, run), doing, status: statusOf(run), detail: run.map(detailOf).join("\n\n"),
      // ...and the server's why of the newest try that failed rides on the merged row (say.step_why) - the page's reading is the fallback only
      ...(run.some((x) => x.why) ? { why: run.filter((x) => x.why).at(-1).why } : {}) });
    else for (const x of run) out.push({ ...x, summary: withCount(x.summary, [x]), detail: detailOf(x) });
    i = j;
  }
  return out;
}

// the steps that are the agent's WORK - what the canvas folds into rows; prose stands on its own
export const isWork = (s) => !["said", "note", "error", "thought"].includes(s.kind);
