// THE DOCS SITE'S THREE-WAY AGREEMENT, same rule the Settings rail needed: what the rail draws,
// what the page stamps an id on, and what search says the path is must come from one place. Here
// that place is a page's own `##` headings, so these tests mostly check that nothing got written
// twice - plus the thing prose rots by, a cross-reference that no longer points at anything.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");
const SRC = path.join(ROOT, "docs", "site");
const OUT = path.join(ROOT, "site", "docs");
const read = (p) => fs.readFileSync(p, "utf8");
const manifest = JSON.parse(read(path.join(SRC, "manifest.json")));
const schema = JSON.parse(read(path.join(ROOT, "taskuary", "settings_schema.json")));
const built = Object.fromEntries(manifest.pages.map((p) => [p.slug, read(path.join(OUT, `${p.slug}.html`))]));
const idsOf = (html) => new Set([...html.matchAll(/ id="([^"]+)"/g)].map((m) => m[1]));
// the same rule the build uses: an apostrophe is dropped, not turned into a dash
const secId = (s) => s.toLowerCase().replace(/['’]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
// marked escapes an apostrophe on the way out, so a label carrying one is compared as HTML
const asHtml = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/'/g, "&#39;").replace(/"/g, "&quot;");

test("the manifest and the source files are the same list", () => {
  const listed = manifest.pages.map((p) => p.file).sort();
  const onDisk = fs.readdirSync(SRC).filter((f) => f.endsWith(".md")).sort();
  assert.deepEqual(listed, onDisk, "a page nobody lists is never built; a listed page with no file fails the build");
  for (const p of manifest.pages) {
    for (const field of ["slug", "file", "title", "desc"]) assert.ok(p[field], `${p.file} lacks ${field}`);
  }
  assert.equal(new Set(manifest.pages.map((p) => p.slug)).size, manifest.pages.length, "slugs are the URLs - they cannot repeat");
  assert.ok(manifest.version && manifest.updated, "the footer stamp needs both, or a stale page cannot say so");
});

test("every built page carries the whole rail, and marks itself", () => {
  for (const p of manifest.pages) {
    const html = built[p.slug];
    for (const other of manifest.pages) {
      assert.ok(html.includes(`>${asHtml(other.title)}</a>`), `${p.slug} does not list ${other.title}`);
    }
    assert.match(html, /aria-current="page"/, `${p.slug} does not mark itself in the rail`);
  }
});

test("a section is a heading, a rail entry and a search crumb at once", () => {
  const index = JSON.parse(read(path.join(OUT, "search.json")));
  for (const p of manifest.pages) {
    const md = read(path.join(SRC, p.file));
    const heads = [...md.matchAll(/^## +(.+)$/gm)].map((m) => m[1].trim());
    if (p.generated) continue;              // its sections come from the schema, covered below
    const ids = idsOf(built[p.slug]);
    for (const h of heads) {
      const id = secId(h);
      assert.ok(ids.has(id), `${p.slug}: heading "${h}" has no anchor`);
      assert.ok(built[p.slug].includes(`data-sec="${id}"`), `${p.slug}: "${h}" is not in the rail`);
      assert.ok(index.some((e) => e.c === `${p.title} → ${h}`), `${p.slug}: "${h}" has no search crumb`);
    }
  }
});

test("every cross-reference still points at something", () => {
  // The way prose rots: a section is renamed and four other pages quietly stop working.
  const pageIds = Object.fromEntries(manifest.pages.map((p) => [p.slug, idsOf(built[p.slug])]));
  const slugs = new Set(manifest.pages.map((p) => p.slug));
  let checked = 0;
  for (const p of manifest.pages) {
    const md = read(path.join(SRC, p.file));
    for (const [, href] of md.matchAll(/\]\(([^)\s]+)\)/g)) {
      if (/^(https?:|mailto:)/.test(href)) continue;
      checked += 1;
      const [target, anchor] = href.split("#");
      const slug = target === "" ? p.slug : target;
      assert.ok(slugs.has(slug), `${p.file}: link to "${href}" names no page`);
      if (anchor) assert.ok(pageIds[slug].has(anchor), `${p.file}: link to "${href}" names no section on that page`);
    }
  }
  assert.ok(checked > 10, "the pages are supposed to refer to each other");
});

test("every image the docs show is actually there", () => {
  for (const p of manifest.pages) {
    for (const [, src] of read(path.join(SRC, p.file)).matchAll(/!\[[^\]]*\]\(([^)\s]+)/g)) {
      if (/^https?:/.test(src)) continue;
      assert.ok(fs.existsSync(path.join(OUT, src)), `${p.file}: ${src} is not in site/docs`);
    }
  }
});

test("the settings reference is the schema, not a copy of it", () => {
  const html = built.settings, ids = idsOf(html);
  assert.ok(!read(path.join(SRC, "settings.md")).includes("### "),
    "the knobs are generated - writing one by hand is how the page starts drifting");
  const used = schema.groups.filter((g) => Object.values(schema.knobs).some((k) => k.group === g));
  for (const g of used) {
    assert.ok(ids.has(secId(g)), `group "${g}" is missing`);
  }
  assert.ok(!ids.has("other"), "Other holds no knobs by design, so it is not a section");
  for (const [key, m] of Object.entries(schema.knobs)) {
    assert.ok(html.includes(`<code>${key}</code>`), `${key} is a setting the docs never name`);
    assert.ok(html.includes(asHtml(m.label)), `${key}'s label "${m.label}" is missing`);
  }
});

test("the search index covers the pages and their sections", () => {
  const index = JSON.parse(read(path.join(OUT, "search.json")));
  for (const p of manifest.pages) {
    assert.ok(index.some((e) => e.u.endsWith(p.slug === "index" ? "./" : p.slug) && e.t === p.title),
      `${p.slug} cannot be found by its own name`);
  }
  assert.ok(index.some((e) => e.body && e.x.length > 500), "body text is indexed, or only headings are findable");
});

test("the page works without its script", () => {
  // Only the highlight and the search need docs.js; the rail itself must be real links.
  for (const p of manifest.pages) {
    const at = built[p.slug].indexOf('id="entries"');
    const rail = built[p.slug].slice(at, built[p.slug].indexOf("</nav>", at));   // the header has a <nav> too
    assert.ok(!/onclick=/i.test(rail), `${p.slug}: the rail must not depend on a click handler`);
    assert.ok(rail.includes('class="sec" href="'), `${p.slug}: section entries must be links`);
  }
});
