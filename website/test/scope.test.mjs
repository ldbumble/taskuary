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

// setTimeout and friends are the platform's, not this component's; ALL_CAPS blocks are module
// constants rather than components
const GLOBALS = new Set(["setTimeout", "setInterval", "setImmediate"]);

// a component starts at a CamelCase top-level const/function; its body runs to the next one, so
// a helper defined INSIDE a component counts as part of it - which is exactly the scope it has
const componentsOf = (src) => {
  const starts = [...src.matchAll(/^(?:export\s+)?(?:const|function)\s+([A-Z]\w*)\s*[=(]/gm)]
    .map((m) => ({ name: m[1], at: m.index }));
  return starts.filter((s) => /^[A-Z][a-z]/.test(s.name))
    .map((s) => ({ name: s.name, body: src.slice(s.at, starts[starts.indexOf(s) + 1]?.at ?? src.length) }));
};

// Only three things DECLARE a setter: the component's own props, a useState pair, or a plain
// const. Matching a bare `{ setX }` anywhere was the trap - `onLock={setPanelLock}` is a JSX
// attribute whose VALUE is the free variable, and reading it as a declaration made the check
// pass on the exact bug it was written for.
const declaredIn = (body) => {
  const props = body.slice(0, body.indexOf("=>") + 1 || 0);      // the parameter list, nothing past it
  return new Set([
    ...[...props.matchAll(/(set[A-Z]\w*)/g)].map((m) => m[1]),
    ...[...body.matchAll(/\[\s*\w+\s*,\s*(set\w+)\s*\]/g)].map((m) => m[1]),          // useState pair
    ...[...body.matchAll(/(?:const|let|var)\s+(set\w+)\s*=/g)].map((m) => m[1]),
    ...[...body.matchAll(/(?:const|let|var)\s*\{([^}]*)\}\s*=/g)]                     // const { setX } = …
      .flatMap((m) => [...m[1].matchAll(/(set[A-Z]\w*)/g)].map((x) => x[1])),
  ]);
};

test("every state setter is declared in the component that uses it", () => {
  const bad = [];
  for (const f of readdirSync(SRC).filter((f) => f.endsWith(".jsx"))) {
    const src = strip(readFileSync(join(SRC, f), "utf8"));
    for (const { name, body } of componentsOf(src)) {
      const declared = declaredIn(body);
      // (?<!\.) - obj.setItem() is a method on something, not a free variable
      for (const used of new Set([...body.matchAll(/(?<![.\w])set[A-Z]\w*/g)].map((m) => m[0]))) {
        if (!declared.has(used) && !GLOBALS.has(used)) {
          bad.push(`${f} · <${name}> uses ${used}, which nothing there declares`);
        }
      }
    }
  }
  assert.deepStrictEqual(bad, [], `free variables that throw at render:\n  ${bad.join("\n  ")}`);
});

/* The same fault in a different disguise: <ConfirmDelete> used in ConnectorsView with no
 * import. esbuild reads an unknown capitalised identifier as a reference to a global, bundles
 * it without a word, and React throws at render - which is how setPanelLock shipped. A JSX tag
 * has to resolve to something declared in its own file: imported, defined, or a member
 * expression (<Foo.Bar>) whose root is. */
test("every component used in JSX is declared in that file", () => {
  const bad = [];
  for (const f of readdirSync(SRC).filter((f) => f.endsWith(".jsx"))) {
    const raw = readFileSync(join(SRC, f), "utf8");
    const src = strip(raw);
    // declarations come off the RAW source: strip() reads an apostrophe in JSX text ("every
    // source's rows") as a string quote and swallows what follows, which hid two real
    // declarations and reported them as missing. Uses still come off the stripped copy, where
    // a component merely NAMED in a comment cannot masquerade as a use.
    const known = new Set([
      // imported: both `import X from` and the named `{ A, B as C }` forms
      ...[...raw.matchAll(/import\s+(\w+)\s*(?:,|from)/g)].map((m) => m[1]),
      ...[...raw.matchAll(/import\s*\{([^}]*)\}\s*from/g)]
        .flatMap((m) => m[1].split(",").map((x) => x.trim().split(/\s+as\s+/).pop().trim())),
      // declared here
      ...[...raw.matchAll(/(?:const|let|var|function|class)\s+([A-Z]\w*)/g)].map((m) => m[1]),
    ]);
    for (const tag of new Set([...src.matchAll(/<([A-Z]\w*)/g)].map((m) => m[1]))) {
      if (!known.has(tag)) bad.push(`${f} · <${tag}> is used but never imported or defined there`);
    }
  }
  assert.deepStrictEqual(bad, [], `components that throw at render:\n  ${bad.join("\n  ")}`);
});
