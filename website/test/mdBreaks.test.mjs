// A LINE BREAK IS A LINE BREAK (the owner, 2026-11-24): an end-of-day brief wrote its five items one a line - Markdown read each single newline
// as a space and they ran together as one paragraph. Drawn through the real Md, server-rendered: each line stands where it was written.
import test from "node:test";
import assert from "node:assert/strict";

// ...no network under a server render: the one client the page talks through, answering nothing
const AXIOS = { name: "axios", setup(b) { b.onResolve({ filter: /^axios$/ }, () => ({ path: "axios", namespace: "stub" }));
  b.onLoad({ filter: /.*/, namespace: "stub" }, () => ({ loader: "js", contents: "const a = { get: async () => ({ data: {} }), post: async () => ({ data: {} }), put: async () => ({ data: {} }), interceptors: { request: { use() {} }, response: { use() {} } }, defaults: { headers: { common: {} } } }; export default { ...a, create: () => a };" })); } };
const page = async () => {
  const hold = setInterval(() => {}, 1000);      // ...the loop held open while esbuild works (Node 22 saw an empty loop)
  try {
    const { build } = await import("esbuild");
    const out = await build({ stdin: { resolveDir: new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"), loader: "jsx", contents: `
      import React from "react"; import { renderToStaticMarkup } from "react-dom/server.browser"; import { LocalFiles, Md } from "./src/md.jsx";
      export const md = (text) => renderToStaticMarkup(<Md text={text} />);
      export const mdIn = (text, tid) => renderToStaticMarkup(<LocalFiles.Provider value={{ tid }}><Md text={text} /></LocalFiles.Provider>);` },
      bundle: true, write: false, format: "esm", jsx: "automatic", platform: "node", logLevel: "silent", plugins: [AXIOS], define: { "process.env.NODE_ENV": '"production"' },
      loader: { ".css": "empty", ".png": "empty", ".svg": "empty", ".jpg": "empty", ".woff2": "empty", ".json": "json" } });
    const { writeFileSync } = await import("node:fs"), { join } = await import("node:path"), { pathToFileURL } = await import("node:url");
    const f = join((await import("../browser/tempdirs.mjs")).ownTemp("tq-md-"), "page.mjs"); writeFileSync(f, out.outputFiles[0].text);
    return import(pathToFileURL(f).href);
  } finally { clearInterval(hold); }
};
let P_; const P = { then: (a, b) => (P_ ||= page()).then(a, b) };

test("lines written one under another stay one under another, and a blank line is still a new paragraph", async () => {
  const { md } = await P;
  const html = md("What got done today\n✅ Erin Blake — the Q3 workbook — sent.\n✅ Gail Moreno — vendor terms — answered.\n\nA good day.");
  assert.match(html, /What got done today<br\/?>\s*✅ Erin Blake[^<]*<br\/?>\s*✅ Gail Moreno/);
  assert.equal((html.match(/<p>/g) || []).length, 2);
});

test("a list, a table and a code block read as before", async () => {
  const { md } = await P;
  assert.match(md("- one\n- two"), /<li>one<\/li>\s*<li>two<\/li>/);
  assert.match(md("| a | b |\n|---|---|\n| 1 | 2 |"), /<td>1<\/td>/);
  assert.doesNotMatch(md("```\nline one\nline two\n```"), /<br/);
});

// walk 20: the agent named its page as [vendor-spend-2026.html](<C:/.../outputs/TQ-0003/...>) - the markdown's URL check emptied a C: address, and
// the empty link opened a second copy of Taskuary. In the task's chat it is the file, the road a path in a code span takes; emptied, its words
test("a file of the task linked in the words opens as the file, and a link the markdown emptied is only its words", async () => {
  const { md, mdIn } = await P;
  const at = "C:/Users/alex/AppData/Local/Taskuary/scratch/outputs/TQ-0003/vendor-spend-2026.html";
  const html = mdIn(`Open [vendor-spend-2026.html](<${at}>) to see it.`, 3);
  assert.match(html, /<a href="\/api\/task-outputs\/3\/vendor-spend-2026\.html[^"]*"[^>]*data-tq-file-link=""/, html);
  assert.doesNotMatch(md(`Open [vendor-spend-2026.html](<${at}>) to see it.`), /<a /);
  assert.doesNotMatch(mdIn(`Open [x](<${at.replace("TQ-0003", "TQ-0009")}>).`, 3), /<a /, "another task's folder is not this one's file");
});

// walk 21: the same link written the Windows way - [vendor-spend-2026.html](C:\...\outputs\TQ-0002\...), no <> - drew as plain words: the
// markdown carries each backslash as %5C, and the address read as no path. A path is a path however its separators were written
test("a file of the task linked with backslashes opens as the file", async () => {
  const { mdIn } = await P;
  const at = "C:\\Users\\alex\\AppData\\Local\\Taskuary\\scratch\\outputs\\TQ-0002\\vendor-spend-2026.html";
  const html = mdIn(`Here it is: [vendor-spend-2026.html](${at})`, 2);
  assert.match(html, /<a href="\/api\/task-outputs\/2\/vendor-spend-2026\.html[^"]*"[^>]*data-tq-file-link=""/, html);
  assert.doesNotMatch(mdIn(`[x](${at.replace("TQ-0002", "TQ-0009")})`, 2), /<a /, "another task's folder is not this one's file");
});
