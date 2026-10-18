// A workflow as steps (taskuary/flow.py): the list the editor edits, and the words a run is read back in. Pure, so the editor's
// rules - ids that never move, an agent only last, a token only for a step above - are tested without a browser.
import { toShape } from "./sourceShape.js";

export const KINDS = ["source", "ai", "task", "draft", "agent"];
export const KIND_WORDS = { source: "Read/write a system", ai: "AI judgment", task: "Open a task", draft: "Draft a message", agent: "Hand to an agent" };
export const USES_AI = new Set(["ai", "draft", "agent"]);       // what "no AI used" is counted from (flow.tally)
export const STEP_KEYS = ["id", "kind", "label", "only_if"];
export const ONLY_IF = [["yes", "answered yes"], ["no", "answered no"], ["rows", "has rows"], ["empty", "came back empty"]];
const TOKEN = /\{\{\s*([^{}\n]{1,120}?)\s*\}\}/g;

export const BLANKS = {
  source: { type: "database", query: "" },
  ai: { prompt: "", output: "yes_no" },
  task: { title: "", summary: "" },
  draft: { channel: "email", to: "", about: "", subject: "" },
  agent: { prompt: "" },
};

// the steps a run walks: the saved list, or the one agent step a prompt-only workflow always was (flow.steps_of)
export const stepsOf = (cfg) => Array.isArray(cfg?.flow) && cfg.flow.length ? cfg.flow
  : [{ id: "s1", kind: "agent", label: "Agent works it", prompt: cfg?.prompt || "", skill: cfg?.skill || "" }];
export const isLoneAgent = (flow) => !flow?.length || (flow.length === 1 && flow[0].kind === "agent");
// the editor shows steps once the config has a list - even an empty one being started
export const asSteps = (cfg) => Array.isArray(cfg?.flow) && !(cfg.flow.length === 1 && cfg.flow[0].kind === "agent");

// "s1", "s2", ... - never reused within a list, so a token keeps pointing at the step it was written for
export const nextId = (flow) => `s${Math.max(0, ...(flow || []).map((s) => Number(/^s(\d+)$/.exec(s.id || "")?.[1]) || 0)) + 1}`;

export const newStep = (kind, flow) => ({ id: nextId(flow), kind, label: "", ...structuredCloneish(BLANKS[kind] || {}) });
const structuredCloneish = (o) => JSON.parse(JSON.stringify(o));

// an agent step is always last: a new step goes above it, and a new agent step replaces nothing - it is refused when one exists
export const insertStep = (flow, at, kind) => {
  const list = [...(flow || [])];
  const agentAt = list.findIndex((s) => s.kind === "agent");
  if (kind === "agent" && agentAt >= 0) return list;
  const where = kind === "agent" ? list.length : agentAt >= 0 ? Math.min(at, agentAt) : Math.min(at, list.length);
  list.splice(where, 0, newStep(kind, list));
  return list;
};

export const moveStep = (flow, i, d) => {
  const j = i + d, list = [...flow];
  if (j < 0 || j >= list.length || list[i].kind === "agent" || list[j].kind === "agent") return list;
  [list[i], list[j]] = [list[j], list[i]];
  // a step that now sits above the step its only_if reads can no longer read it
  return list.map((s, n) => s.only_if && list.findIndex((x) => x.id === s.only_if.step) >= n ? { ...s, only_if: undefined } : s);
};

export const removeStep = (flow, i) => {
  const gone = flow[i]?.id;
  return flow.filter((_, n) => n !== i).map((s) => s.only_if?.step === gone ? { ...s, only_if: undefined } : s);
};

export const canAddAgent = (flow) => !(flow || []).some((s) => s.kind === "agent");

// what a later step can say about step `i`'s output, by kind - the Insert output menu
export const tokensOf = (s) => {
  const t = (x) => `{{${s.id}${x}}}`;
  const base = [[t(".head"), "its headline"]];
  if (s.kind === "source") return [[t(""), "the rows it read"], [t(".rows"), "how many rows"], ...base];
  if (s.kind === "ai" && s.output === "yes_no") return [[t(".answer"), "yes or no"], [t(".why"), "why"]];
  if (s.kind === "ai" && s.output === "fields") return (s.fields || []).map((f) => [t(`.fields.${f}`), f]);
  if (s.kind === "ai") return [[t(""), "its answer"]];
  if (s.kind === "task") return [[t(".head"), "the task's TQ number"]];
  return base;
};
export const tokensFor = (flow, i) => (flow || []).slice(0, i).map((s, n) => ({ id: s.id, n: n + 1, label: s.label || KIND_WORDS[s.kind], tokens: tokensOf(s) }));

// tokens that name a step not above this one - the server refuses them (flow.validate); the card says so first
export const badRefs = (flow, i) => {
  const above = new Set((flow || []).slice(0, i).flatMap((s) => [s.id, slug(s.label)]));
  const s = flow?.[i] || {};
  const text = JSON.stringify(Object.fromEntries(Object.entries(s).filter(([k]) => !STEP_KEYS.includes(k))));
  return [...text.matchAll(TOKEN)].map((m) => m[1].split(".")[0].trim()).filter((r) => !["inputs", "run"].includes(r) && !above.has(r) && !above.has(slug(r)));
};
export const slug = (x) => String(x || "").toLowerCase().replace(/[_-]/g, " ").split(/\s+/).filter(Boolean).join(" ");
// v1 pastes text into a query - the editor says so where it happens
// an earlier step's output in a query or filter (flow.pasted_sql): never saved - what a step read could rewrite the SQL. The owner's
// inputs and the run's own facts ({{inputs.x}}, {{run.date}}) may fill one.
export const tokenInQuery = (s) => s?.kind === "source"
  && [s.query, s.filter].some((v) => [...String(v || "").matchAll(/\{\{\s*([^{}.\s]+)/g)].some((m) => !["inputs", "run"].includes(m[1])));

// what the owner still has to fill in before Save means anything (the server's flow.validate has the last word)
export const missingIn = (s) => s.kind === "source" ? (!s.type ? "a system" : "")
  : s.kind === "ai" ? (!String(s.prompt || "").trim() ? "a prompt" : s.output === "fields" && !(s.fields || []).length ? "the fields it fills" : "")
    : s.kind === "task" ? (!String(s.title || "").trim() ? "a title" : "")
      : s.kind === "draft" ? (!String(s.to || "").trim() ? "who it goes to" : !String(s.about || "").trim() ? "what it is about" : "")
        : s.kind === "agent" ? (!String(s.prompt || s.skill || "").trim() ? "what the agent does" : "") : "";
export const firstMissing = (flow) => {
  const i = (flow || []).findIndex((s) => missingIn(s));
  return i < 0 ? "" : `step ${i + 1} needs ${missingIn(flow[i])}`;
};

// the list as it is saved: a source step's text fields in the executor's shapes (sourceShape.toShape), empties dropped
export const toSaved = (flow) => (flow || []).map((s) => {
  const keep = Object.fromEntries(STEP_KEYS.filter((k) => s[k] !== undefined && s[k] !== "").map((k) => [k, s[k]]));
  const rest = Object.fromEntries(Object.entries(s).filter(([k]) => !STEP_KEYS.includes(k)));
  const body = s.kind === "source" ? toShape(rest) : Object.fromEntries(Object.entries(rest).filter(([, v]) => v !== "" && v != null && !(Array.isArray(v) && !v.length)));
  return { ...keep, label: s.label || KIND_WORDS[s.kind], ...body };
});

// ── a run, read back ───────────────────────────────────────────────────────────────────────────────────────────────────
export const STATUS = { repaired: "failed, then repaired", ok: "done", failed: "failed", skipped: "skipped", waiting: "waiting for your yes", dry: "test only" };
export const secs = (ms) => `${((ms || 0) / 1000).toFixed(1)}s`;
export const recHead = (r) => !r ? "" : r.status === "failed" ? `failed: ${r.error || ""}`
  : r.status === "waiting" ? "waiting for your yes" : r.head || STATUS[r.status] || "";
export const tally = (recs) => {
  const ran = (recs || []).filter((r) => !["skipped", "repaired"].includes(r.status));
  const ai = ran.filter((r) => USES_AI.has(r.kind)).length;
  const ms = (recs || []).reduce((n, r) => n + (r.ms || 0), 0), fixed = (recs || []).some((r) => r.status === "repaired");
  // a repair is a model call too (flow.repair): "no AI used" over a run that repaired itself would be untrue
  return `Ran ${ran.length} step${ran.length === 1 ? "" : "s"} in ${secs(ms)}, ${ai ? `${ai} with AI` : fixed ? "AI only for the repair" : "no AI used"}`;
};
// `short`: where the failed step's own row already says the error, the line above it does not say it again
export const runWords = (recs, short = false) => {
  const i = (recs || []).findIndex((r) => r.status === "failed" || r.status === "waiting");
  if (i < 0) return tally(recs);
  // the step's own number: a repaired record is the same step tried again, not a step of its own (Step 3 failed on a one-step run)
  const n = recs.slice(0, i).filter((r) => r.status !== "repaired").length + 1;
  return recs[i].status === "failed" ? `Step ${n} failed${short ? "" : `: ${recs[i].error || ""}`}` : `Waiting for your yes on step ${n}`;
};
// what the editor's last tests came to - a test never writes, so it never says "ran"
export const testWords = (recs) => {
  const bad = (recs || []).findIndex((r) => r.status === "failed");
  if (bad >= 0) return `Step ${bad + 1} failed - its output is on the step.`;
  const dry = (recs || []).filter((r) => r.status === "dry").length;
  return `${recs.length} step${recs.length === 1 ? "" : "s"} have output below${dry ? `; ${dry} would write, so ${dry === 1 ? "it" : "they"} only said what ${dry === 1 ? "it" : "they"} would do` : ""}.`;
};
// the last record per step id, for "Test this step" to start from (the last run's, then each test as it comes back)
export const outputsOf = (recs) => Object.fromEntries((recs || []).filter((r) => r?.id).map((r) => [r.id, r]));
// a workflow is a goal (flow.repair_mode): auto is the default - a fix that keeps the goal and reaches nowhere new is kept at once
export const REPAIR = [["auto", "Fix it and carry on while the goal stays the same - ask me otherwise"],
  ["propose", "Always ask me before changing a step"], ["off", "Off - a failed run just stops and says which step"]];
export const failedRun = (r) => !!(r?.failed && (r.steps || []).some((x) => x.status === "failed"));

// a repair the owner has not kept yet: which keys of which step it changed, so the card can mark them
export const diffKeys = (was, now) => {
  const a = Object.fromEntries((was || []).map((s) => [s.id, s]));
  const out = {};
  for (const s of now || []) {
    const old = a[s.id];
    if (!old) { out[s.id] = new Set(["*"]); continue; }
    const keys = new Set([...Object.keys(old), ...Object.keys(s)].filter((k) => JSON.stringify(old[k]) !== JSON.stringify(s[k])));
    if (keys.size) out[s.id] = keys;
  }
  return out;
};

// ── a workflow that only reads is a report (the owner, 2026-10-18) ──────────────────────────────────────────────────────
// Every workflow run is a task, because a workflow DOES something. Steps that only read and judge - nothing written, opened, drafted
// or handed on - are a report; the editor says so and offers the report built from the same reads (flow.only_reads / as_report).
// `types` is /api/report-types, which says per type whether a step of it writes; a type it does not vouch for counts as a write.
export const onlyReads = (flow, types = []) => {
  const reads = new Set((types || []).filter((t) => t.writes === false).map((t) => t.type));
  return !!flow?.length && flow.every((s) => s.kind === "ai" || (s.kind === "source" && reads.has(s.type)));
};
export const asReport = (cfg) => {
  const steps = (cfg?.flow || []).filter(Boolean);
  const reads = steps.filter((s) => s.kind === "source");
  const strip = (s) => Object.fromEntries(Object.entries(s).filter(([k]) => !STEP_KEYS.includes(k)));
  const srcs = toSaved(reads).map((s) => ({ ...strip(s), label: s.label || s.type }));
  const key = Object.fromEntries(reads.map((s) => [s.id, `[${s.type}.${slug(s.label || s.type)}]`]));
  const prompt = steps.filter((s) => s.kind === "ai")
    .map((s) => String(s.prompt || "").replace(TOKEN, (_, t) => (t.includes(".") ? "" : key[t.trim()] || "")).trim()).filter(Boolean).join("\n\n");
  const out = { title: cfg?.title || "", ...(prompt ? { ai_prompt: prompt } : {}),
    ...Object.fromEntries(["cron", "daily_at", "every_minutes", "on_startup"].filter((k) => cfg?.[k]).map((k) => [k, cfg[k]])) };
  return srcs.length === 1 ? { ...out, ...srcs[0] } : { ...out, type: srcs[0]?.type || "rest", sources: srcs };
};
export const REPORT_WORDS = "These steps only read data and tell you about it, so this is a report, not a workflow - a workflow does something "
  + "(moves data, opens work, drafts what goes out), and every run of one is a task.";

// "Turn into steps": the composer is asked with what the workflow already says, so its draft keeps the job's words
export const askFor = (cfg, names = {}) => [cfg?.title && `${cfg.title}.`, cfg?.prompt,
  (cfg?.uses || []).length ? `It works in: ${(cfg.uses || []).map((u) => names[u] || `connection ${u}`).join(", ")}.` : "",
  cfg?.ask_first && `Ask first before: ${cfg.ask_first}.`, cfg?.done_when && `Done when: ${cfg.done_when}.`,
  "Build it as steps: code for every read and write, AI only for the judgement."].filter(Boolean).join(" ");
