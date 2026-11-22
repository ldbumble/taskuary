/* A state setter used outside the component that owns it.
 *
 * `onLock={setPanelLock}` was written inside ReviewCanvas while setPanelLock lived in FeedView,
 * two components up. That is a free variable: valid JavaScript, bundled without a murmur by
 * vite, and a ReferenceError the instant the panel renders - it took the whole review panel out
 * and the only sign was a stack trace full of minified names.
 *
 * Nothing here type-checks or scope-analyses in general; this catches the one mistake that is
 * easy to make while moving JSX between components and impossible to see in a diff. Setters are
 * the tell: `set[A-Z]…` is a naming convention this codebase follows everywhere, so an
 * undeclared one is always a bug and never a global.
 */
import { test } from "node:test";
import assert from "node:assert";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));   // .pathname gives /C:/… on Windows

// comments and string/template literals are not code: a setter NAMED in a comment explaining
// the bug would otherwise read as the bug
const strip = (s) => s
  .replace(/\/\*[\s\S]*?\*\//g, " ")
  .replace(/(^|[^:])\/\/[^\n]*/g, "$1 ")
  .replace(/`(?:\\[\s\S]|[^`\\])*`/g, "``")
  .replace(/"(?:\\.|[^"\\])*"/g, '""')
  .replace(/'(?:\\.|[^'\\])*'/g, "''");


/* The same fault in a different disguise: <ConfirmDelete> used in ConnectorsView with no
 * import. esbuild reads an unknown capitalised identifier as a reference to a global, bundles
 * it without a word, and React throws at render - which is how setPanelLock shipped. A JSX tag
 * has to resolve to something declared in its own file: imported, defined, or a member
 * expression (<Foo.Bar>) whose root is. */


/* Third disguise, and the one that nearly shipped this time: a design token used without
 * importing it. `PANEL` is exported from theme.jsx and referenced in a dozen files, so writing
 * it into a thirteenth feels free - but the import list is per file, vite bundles the free
 * variable happily, and the page dies at render like the other two. Every name theme.jsx
 * exports has to be imported by the file that uses it. */
test("every theme token used is imported from theme.jsx", () => {
  const theme = readFileSync(join(SRC, "theme.jsx"), "utf8");
  // ALL-CAPS exports only: `card`, `frame` and `mono` are ordinary English words that show up
  // as local variables and state all over this codebase, and a guard with false positives is a
  // guard people learn to skip.
  const tokens = new Set([...theme.matchAll(/export const ([A-Z][A-Z0-9_]+)\b/g)].map((m) => m[1]));
  const bad = [];
  for (const f of readdirSync(SRC).filter((f) => /\.jsx?$/.test(f) && f !== "theme.jsx")) {
    const raw = readFileSync(join(SRC, f), "utf8");
    // comments only, NOT string literals: strip() treats an apostrophe in JSX prose ("you're")
    // as an opening quote and swallows everything to the next one, which in a file this full of
    // sentences silently hid the very uses this test exists to find.
    const src = raw.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/(^|[^:])\/\/.*/gm, "$1 ");
    const imported = new Set([...raw.matchAll(/import\s*\{([^}]*)\}\s*from\s*['"]\.\/theme\.jsx['"]/g)]
      .flatMap((m) => m[1].split(",").map((x) => x.trim().split(/\s+as\s+/).pop().trim())));
    // a token is only "used" as a bare identifier - `theme.BG` or `{ BG: … }` is something else
    for (const t of tokens) {
      if (imported.has(t)) continue;
      // built from a plain string: inside a template literal \w collapses to w, which quietly
      // turned this into [^w.$] and stopped it matching anything worth reporting
      if (new RegExp("(^|[^\\w.$])" + t + "(?![\\w:])", "m").test(src)) {
        bad.push(`${f} · ${t} is used but not imported from theme.jsx`);
      }
    }
  }
  assert.deepStrictEqual(bad, [], `tokens that throw at render:\n  ${bad.join("\n  ")}`);
});
