// WHAT TASKUARY MADE ON ITS OWN IS A TASK, IN THE ONE TASK PAGE (the owner, 2026-11-24: "reports/dashboards/ideas and tasks are the SAME CODE, not
// just consistent - the one task page, the same cards, the prompt as the input into the agent, the same box. Made-item special pages get deleted;
// only the data mapping differs"). This is that mapping, and nothing else: a report's run, a dashboard or an Advisor's idea read into the record
// TaskPage draws a task from - its head, its Came from (the item's SOURCE: the routine that runs it, its schedule, its prompt, the data it reads,
// its Edit; for an idea the mails and tasks it rests on) and its chat (the prompt that asked, as the input line; Taskuary's run, as the turn that
// answered, its content that turn's artifact). Opening it starts nothing: the box under it starts the agent, through the item's start.
// The view a run or an idea is drawn as is read here too - the spec an agent's `show` draws (viewSpec.js), never a renderer of its own.
// Pure: test/madeTask.test.mjs; drawn by TaskPage: test/onePage.test.mjs.
import { colWords, jsonRows, numOf, reportShape, reportSummary } from "./reportRows.js";
import { briefOf } from "./reportBrief.js";

// the review id the run's turn places its artifact under (GeneralWorkspace Conversation: a turn's cards are the page's nodes, by review)
export const MADE_RUN = "made:run";

// `input`: { head, text } - what asked for it, marked automated (head) with the whole prompt (text); `source`: { head, rows: [[label, value]] }
// `wide`: drawn at the chat's whole width (a dashboard is looked at - the owner, 2026-11-23: "real estate is paramount")
export function madeTask({ key, kind, label, title, when = null, channel = "", input, source, wide = false }) {
  const at = when || null;
  return { key, kind, wide, source,
    detail: { made: kind, ref: label, task: { TaskId: key, Title: String(title || ""), Kind: "general", Status: "open", Source: channel, CreatedAt: at, Summary: "", Tags: "" },
      messages: [], comments: [], runs: [], reviews: [], routes: [], checklist: [], attachments: [], links: [], artifacts: [], earlier: [] },
    list: { rev: `made:${key}`, items: [
      { kind: "line", id: `${key}:ask`, auto: input?.head || "Automated", text: String(input?.text || ""), at },
      { kind: "turn", id: `${key}:run`, state: "done", at, cards: [{ id: `${key}:card`, review: MADE_RUN, status: "shown" }] }], pending: [] } };
}

// A REPORT'S OR A DASHBOARD'S SOURCE: the routine behind it, as the Reports tab keeps it - its name, when it runs (the server's ScheduleWords),
// its prompt, what it reads (each source's type, in the Reports tab's words), where its runs go - and the way to change it
export function routineSource(row, cfg, { types = {}, edit = "Edit", kind = "report" } = {}) {
  const reads = [...new Set((cfg?.sources?.length ? cfg.sources : cfg?.type ? [cfg] : []).map((s) => types[s.type] || s.type).filter(Boolean))].join(", ");
  return { head: kind === "dashboard" ? "The dashboard" : "The report", edit: row?.SourceId != null ? { label: edit, href: `#report=${row.SourceId}` } : null,
    rows: [["Name", row?.Address || cfg?.title || cfg?.name || ""], ["Runs", row?.ScheduleWords || ""], ["Prompt", String(cfg?.ai_prompt || "").trim()],
      ["Reads", reads], ["Goes to", row?.RouteWords || ""]].filter(([, v]) => v) };
}

// AN IDEA'S SOURCE IS THE EVIDENCE IT RESTS ON (the owner, 2026-11-24): the message it was raised on, why, and each mail or task it cites - a link
// into the app (#msg=, #task=)
export const citeHref = (ref) => { const m = /^(msg|task)(\d+)$/.exec(String(ref || "")); return m ? `#${m[1]}=${m[2]}` : null; };
export function ideaSource(card) {
  const a = card?.action || {}, mid = a.mid || card?.mid, who = a.who || (card?.who !== "Advisor" ? card?.who : "");
  const cites = (a.type === "lookout" && Array.isArray(a.evidence) ? a.evidence : []).map((e) => ({ label: e?.label || e?.ref, href: citeHref(e?.ref) })).filter((e) => e.href);
  const links = [...(mid ? [{ label: who ? `${who}'s message` : "the message", href: `#msg=${mid}` }] : []), ...cites,
    ...(a.tid || card?.tid ? [{ label: "its task", href: `#task=${a.tid || card.tid}` }] : [])];
  return { head: "What it rests on", links, rows: [["Based on", a.source?.label && !mid ? a.source.label : ""], ["Why", a.why || card?.why || ""]].filter(([, v]) => v) };
}

// a tree of {type, props, children} -> {title, root, elements}: one column, a hairline between its blocks (viewSpec.css)
const view = (title, kids) => {
  const elements = {}; let n = 0;
  const put = (e) => { const id = `e${n++}`; elements[id] = { type: e.type, props: e.props || {}, children: [] }; elements[id].children = (e.children || []).map(put); return id; };
  return { title: title || "", root: put({ type: "grid", props: { cols: 1 }, children: kids.filter(Boolean) }), elements };
};
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const words = (text, title) => ({ type: "text", props: { ...(title ? { title } : {}), text } });
const BARS = 12;     // a ranking past a dozen is the table's job; the table under it holds every row

// a data report: what it found in a line, the chart its rows make (the server's pick, artifacts.chart_columns), then every row
function rowsView(rows, name) {
  const shape = reportShape(rows), { lab, val } = shape, what = lab ? `${colWords(val)} by ${colWords(lab)}` : colWords(val);
  const pts = rows.slice(0, shape.chart === "line" ? rows.length : BARS).map((r, i) => ({ label: lab ? String(r[lab] ?? "") : `#${i + 1}`, value: numOf(r[val]) ?? 0 }));
  return view(name, [words(reportSummary(rows, shape)),
    shape.chart && { type: "chart", props: { kind: shape.chart === "line" ? "line" : "bar", title: cap(what), points: pts } },
    { type: "table", props: { columns: shape.cols.map((k) => cap(colWords(k))), rows: rows.map((r) => shape.cols.map((k) => r[k] ?? null)) } }]);
}
// a brief (evening.PROMPT's shape, reportBrief.briefOf): a note on what it could not read, its roll-ups side by side, each group of items, its close
const item = (it) => `- ${[it.who && `**${it.who}**`, it.what].filter(Boolean).join(" · ") || it.text}${it.status.includes("meeting") ? " · _meeting_" : ""}${it.gist && (it.who || it.what) ? `  \n  ${it.gist}` : ""}`;
const briefView = (b, name) => view(name, [...b.notes.map((t) => ({ type: "note", props: { tone: "warning", text: t } })),
  b.rollups.length && { type: "grid", props: { cols: Math.min(b.rollups.length, 2) }, children: b.rollups.map(([k, v]) => words(v, k)) },
  ...b.groups.map((g) => words(g.items.map(item).join("\n"), g.title ? `${g.title} · ${g.items.length}` : "")), b.closing.length && words(b.closing.join(" "))]);

// {spec, owns}: a report's words as the view its turn draws, and which of the files its run carries that view already IS - the chart's
// picture, where the chart is drawn live from the rows (ONE THING, ONE PLACE: taskOutputs.carried), never drawn again under it
export function reportView(text, name = "") {
  const rows = jsonRows(text), brief = !rows && briefOf(text), chart = !!rows && !!reportShape(rows).chart;
  return { spec: rows ? rowsView(rows, name) : brief ? briefView(brief, name) : view("", [words(String(text || "").trim())]),
    owns: (a) => chart && a?.content_type === "image/svg+xml" };
}

// an Advisor's idea: what it noticed and what to do, and its pitch - what it rests on is its Came from (ideaSource)
export function ideaView(card) {
  const a = card?.action || {}, look = a.type === "lookout";
  return view("", [words(String((look ? a.next_step || a.suggest : a.suggest) || "").trim() || card?.title || "", card?.title),
    look && a.pitch && words(`**Pitch** - ${a.pitch}`)]);
}
