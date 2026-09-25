// THE DOCS SITE, BUILT. Markdown under docs/site/ becomes static HTML under site/docs/, which is
// committed and served by Cloudflare as plain assets - the same arrangement `build:demo` already
// uses, and the same rule the packaged UI follows: CI rebuilds and fails if the committed output
// is not what a fresh build produces, so nobody hand-edits the HTML or forgets to rebuild.
//
// One source of truth per thing:
//   docs/site/manifest.json   the rail's pages, in order
//   a page's `##` headings    that page's rail sub-entries, its anchors and its search crumbs
//   settings_schema.json      the whole settings reference (so it cannot drift from the app)
//
// The layout is the app's Settings page, which is what the owner asked for: a rail of pages, the
// current one open on its sections, one scrolling page beside it, and search over everything.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { marked } from "marked";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..", "..");
const SRC = path.join(ROOT, "docs", "site");
const OUT = path.join(ROOT, "site", "docs");
const read = (p) => fs.readFileSync(p, "utf8");

const manifest = JSON.parse(read(path.join(SRC, "manifest.json")));
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
// The id a heading gets, and the one the rail links to. One function, both sides - the rule the
// Settings rail needed (secId in website/src/settingsMap.js) for exactly the same reason.
// An apostrophe is dropped rather than turned into a dash, so "A task's three lives" anchors as
// `a-tasks-three-lives` and not `a-task-s-three-lives`, which is what anyone linking to it types.
const secId = (name) => String(name).toLowerCase().replace(/['’]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

/* ── the settings reference, written from the schema ─────────────────────────────────────── */
// A knob added to taskuary/settings_schema.json appears in the docs on the next build, with the
// same label, group and help text the app shows. This is the one page nobody has to remember.
const schema = JSON.parse(read(path.join(ROOT, "taskuary", "settings_schema.json")));
const owned = new Set(schema.panel_owned || []);

function settingsMarkdown() {
  const byGroup = new Map(schema.groups.map((g) => [g, []]));
  for (const [key, m] of Object.entries(schema.knobs)) (byGroup.get(m.group) || []).push([key, m]);
  const out = [];
  for (const group of schema.groups) {
    const rows = byGroup.get(group) || [];
    if (!rows.length) continue;             // "Other" is a catch-all with no knobs: not a section
    out.push(`## ${group}\n`);
    for (const [key, m] of rows) {
      out.push(`### ${m.label}\n`);
      const bits = [`\`${key}\``, `type: ${m.type}`];
      if (owned.has(key)) bits.push("set on a card at the top of the page");
      out.push(`${bits.join(" · ")}\n`);
      out.push(`${m.desc}\n`);
      if (m.options?.length) out.push(`Options: ${m.options.map((o) => `\`${o}\``).join(", ")}\n`);
      if (m.flags) out.push(`One control over: ${Object.entries(m.flags).map(([k, v]) => `**${v.label || k}** (\`${k}\`)`).join(", ")}\n`);
      if (m.help) out.push(`${m.help.split("\n").filter(Boolean).join("\n\n")}\n`);
    }
  }
  return out.join("\n");
}

/* ── markdown extensions: callouts and figures ───────────────────────────────────────────── */
// `:::rule Title` / `:::note` / `:::warn` ... `:::` - a left rule and a mono eyebrow, never a
// tinted panel. Colour identifies; it does not decorate.
const CALLOUT = { note: "Note", warn: "Careful", rule: "The rule" };
function callouts(md) {
  return md.replace(/^:::(note|warn|rule)[ \t]*(.*)$\n([\s\S]*?)^:::[ \t]*$/gm, (_m, kind, title, body) =>
    `<div class="callout ${kind}"><p class="eyebrow">${esc(title.trim() || CALLOUT[kind])}</p>\n\n${body}\n</div>\n`);
}

const renderer = new marked.Renderer();
// An image with a title becomes a figure with that title as its caption; without one it stays an
// image. The caption is the sentence under the screenshot, and it earns its place or is absent.
renderer.image = ({ href, title, text }) => {
  const img = `<img src="${esc(href)}" alt="${esc(text || "")}" loading="lazy">`;
  return title ? `<figure>${img}<figcaption>${esc(title)}</figcaption></figure>` : img;
};
// Headings carry their own anchor, and a link that appears on hover so a reader can take it.
// `function`, not an arrow: the renderer needs its own `this` to reach the parser.
renderer.heading = function ({ tokens, depth, text }) {
  const id = secId(text);
  return `<h${depth} id="${id}">${this.parser.parseInline(tokens)}<a class="anchor" href="#${id}" aria-label="Link to this section">#</a></h${depth}>\n`;
};
marked.use({ renderer, gfm: true });

/* ── one page ────────────────────────────────────────────────────────────────────────────── */
function page(entry) {
  let md = read(path.join(SRC, entry.file));
  if (entry.generated === "settings") md = md.replace("<!-- generated: settings -->", settingsMarkdown());
  else if (entry.generated) throw new Error(`${entry.file}: unknown generated block '${entry.generated}'`);
  // the lede is everything before the first section, and it is the page's own opening paragraph
  const sections = [...md.matchAll(/^## +(.+)$/gm)].map((m) => m[1].trim());
  const body = marked.parse(callouts(md));
  const text = md.replace(/```[\s\S]*?```/g, " ").replace(/[#*`|>\-]/g, " ").replace(/\s+/g, " ").trim();
  return { ...entry, sections, body, text };
}

const pages = manifest.pages.map(page);
const href = (slug) => (slug === "index" ? "./" : `./${slug}`);

function rail(current) {
  const rows = pages.map((p) => {
    const on = p.slug === current.slug;
    const secs = on
      ? p.sections.map((s) => `<a class="sec" href="#${secId(s)}" data-sec="${secId(s)}">${esc(s)}</a>`).join("")
      : p.sections.map((s) => `<a class="sec" href="${href(p.slug)}#${secId(s)}">${esc(s)}</a>`).join("");
    return `<div class="entry${on ? " on" : ""}">
      <a class="page" href="${href(p.slug)}"${on ? ' aria-current="page"' : ""}>${esc(p.title)}</a>
      ${p.sections.length ? `<button class="chev" type="button" aria-expanded="${on}" aria-label="${on ? "Hide" : "Show"} ${esc(p.title)}'s sections"></button>` : ""}
      <div class="secs"${on ? "" : ' hidden'}>${secs}</div>
    </div>`;
  });
  return rows.join("\n");
}

function html(p, i) {
  const prev = pages[i - 1], next = pages[i + 1];
  const foot = [
    prev ? `<a class="pn prev" href="${href(prev.slug)}"><span>Previous</span>${esc(prev.title)}</a>` : "<span></span>",
    next ? `<a class="pn next" href="${href(next.slug)}"><span>Next</span>${esc(next.title)}</a>` : "<span></span>",
  ].join("");
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(p.title)} — Taskuary documentation</title>
<meta name="description" content="${esc(p.desc)}">
<link rel="icon" href="/favicon.ico">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<link rel="stylesheet" href="./docs.css">
</head>
<body>
<a class="skip" href="#doc">Skip to the documentation</a>
<header class="nav">
  <div class="navwrap">
    <a class="brand" href="/"><img src="/icon.png" alt="" width="26" height="26">Taskuary</a>
    <span class="tag">a work AI assistant</span>
    <nav class="links">
      <a href="/docs/" aria-current="true">Docs</a>
      <a href="/demo/">Demo</a>
      <a href="https://github.com/ldbumble/taskuary">GitHub</a>
      <a class="btn" href="https://github.com/ldbumble/taskuary/releases/latest/download/Taskuary.exe">Download</a>
    </nav>
  </div>
</header>
<div class="shell">
  <aside class="rail" id="rail">
    <form class="search" role="search" onsubmit="return false">
      <label class="sr" for="q">Search the documentation</label>
      <input id="q" type="search" placeholder="Search the docs…" autocomplete="off">
    </form>
    <div class="results" id="results" hidden></div>
    <nav class="entries" id="entries" aria-label="Documentation">
${rail(p)}
    </nav>
    <p class="note">Everything here is stored on your own machine, in the same SQLite file as your tasks.</p>
  </aside>
  <main id="doc">
    <p class="eyebrow">${esc(p.title)}</p>
    <article>
${p.body}
    </article>
    <nav class="pager">${foot}</nav>
    <p class="stamp">Documentation for Taskuary ${esc(manifest.version)} · updated ${esc(manifest.updated)}</p>
  </main>
</div>
<script src="./docs.js"></script>
</body>
</html>
`;
}

/* ── write ───────────────────────────────────────────────────────────────────────────────── */
fs.mkdirSync(OUT, { recursive: true });
for (const f of fs.readdirSync(OUT)) if (/\.(html|json)$/.test(f)) fs.rmSync(path.join(OUT, f));
pages.forEach((p, i) => fs.writeFileSync(path.join(OUT, `${p.slug}.html`), html(p, i)));

// The search index: one entry per section, plus the page itself. The crumb is the rail's own
// wording ("Connections → Sources"), so a hit reads the same way the rail does.
const index = [];
for (const p of pages) {
  index.push({ t: p.title, c: p.title, u: href(p.slug), x: p.desc });
  for (const s of p.sections) index.push({ t: s, c: `${p.title} → ${s}`, u: `${href(p.slug)}#${secId(s)}`, x: "" });
}
// section text, for hits on words that are not in a heading
for (const p of pages) index.push({ t: "", c: p.title, u: href(p.slug), x: p.text.slice(0, 12000), body: true });
fs.writeFileSync(path.join(OUT, "search.json"), JSON.stringify(index));

fs.copyFileSync(path.join(HERE, "docs.css"), path.join(OUT, "docs.css"));
fs.copyFileSync(path.join(HERE, "docs.js"), path.join(OUT, "docs.js"));
// the decision trees, drawn by tools/render-diagrams.mjs
fs.cpSync(path.join(SRC, "img"), path.join(OUT, "img"), { recursive: true });

console.log(`docs: ${pages.length} pages, ${pages.reduce((n, p) => n + p.sections.length, 0)} sections -> site/docs`);
