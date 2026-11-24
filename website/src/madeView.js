// WHAT TASKUARY MADE ON ITS OWN, AS A VIEW (the owner, 2026-11-23: "it should be the same codebase json render as the action cards and artifacts"):
// a report's run and an Advisor's idea are read ONCE here into the spec an agent's `show` draws (viewSpec.js, ViewSpec.jsx) - a data report's
// rows as its line, chart and table; a brief as its roll-ups and groups; words as words - so the Agent tab draws them with the one view renderer,
// in the one frame. Pure: test/madeView.test.mjs.
import { colWords, jsonRows, numOf, reportShape, reportSummary } from "./reportRows.js";
import { briefOf } from "./reportBrief.js";

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

// {spec, owns}: a report's words as the view the Agent tab draws, and which of the files its run carries that view already IS - the chart's
// picture, where the chart is drawn live from the rows (ONE THING, ONE PLACE: taskOutputs.carried), never drawn again under it
export function reportView(text, name = "") {
  const rows = jsonRows(text), brief = !rows && briefOf(text), chart = !!rows && !!reportShape(rows).chart;
  return { spec: rows ? rowsView(rows, name) : brief ? briefView(brief, name) : view("", [words(String(text || "").trim())]),
    owns: (a) => chart && a?.content_type === "image/svg+xml" };
}

// an Advisor's idea: what it noticed and what to do, then what it rests on - each message or task it cites a link into the app (#msg=, #task=)
export function ideaView(card) {
  const a = card?.action || {}, look = a.type === "lookout", mid = a.mid || card?.mid, why = a.why || card?.why;
  const who = a.who || (card?.who !== "Advisor" ? card?.who : ""), from = mid ? `[${who ? `${who}'s message` : "the message"} ↗](#msg=${mid})` : a.source?.label || "";
  const cites = (look && Array.isArray(a.evidence) ? a.evidence : []).filter((e) => /^(msg|task)\d+$/.test(String(e?.ref || "")))
    .map((e) => `[${e.label || e.ref} ↗](#${e.ref.replace(/^(msg|task)/, "$1=")})`);
  const facts = [["Pitch", look && a.pitch], ["Based on", (from || why) && [from, why].filter(Boolean).join(": ")], ["Rests on", cites.join(" · ")]]
    .filter(([, v]) => v).map(([k, v]) => `**${k}** - ${v}`).join("\n\n");
  return view("", [words(String((look ? a.next_step || a.suggest : a.suggest) || "").trim() || card?.title || "", card?.title), facts && words(facts)]);
}
