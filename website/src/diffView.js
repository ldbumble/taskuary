// THE CODE AND ITS DIFF, read the way a person reviews one (the owner, 2026-11-06: "i do like you can review the code diffs if you want... i like
// the editor that you can see the code"). Pure, so node reads it: a line diff between two texts in git's own hunk shape, a unified diff read
// back per file, line numbers walked down each hunk, and a small highlighter - strings, comments, numbers, keywords - with no library behind it.

// ── two texts -> git-shaped hunks ────────────────────────────────────────────────────────────────
const linesOf = (t) => { const s = String(t ?? ""); if (!s) return []; const ls = s.replace(/\r\n/g, "\n").split("\n"); if (ls.at(-1) === "") ls.pop(); return ls; };
const CAP = 4e6;                 // past this many cells the middle reads as removed then added - a diff, if not the shortest
export function lineOps(a, b) {
  let p = 0, s = 0;
  while (p < a.length && p < b.length && a[p] === b[p]) p += 1;
  while (s < a.length - p && s < b.length - p && a[a.length - 1 - s] === b[b.length - 1 - s]) s += 1;
  const A = a.slice(p, a.length - s), B = b.slice(p, b.length - s), n = A.length, m = B.length, mid = [];
  if (n * m > CAP) mid.push(...A.map((l) => ["-", l]), ...B.map((l) => ["+", l]));
  else {
    // L[i][j]: the longest common run of A[i:] and B[j:]; walked from the top, a removal before an addition - as git writes a change
    const L = new Uint32Array((n + 1) * (m + 1)), at = (i, j) => i * (m + 1) + j;
    for (let i = n - 1; i >= 0; i -= 1) for (let j = m - 1; j >= 0; j -= 1)
      L[at(i, j)] = A[i] === B[j] ? L[at(i + 1, j + 1)] + 1 : Math.max(L[at(i + 1, j)], L[at(i, j + 1)]);
    let i = 0, j = 0;
    while (i < n || j < m) {
      if (i < n && j < m && A[i] === B[j]) { mid.push([" ", A[i]]); i += 1; j += 1; }
      else if (j >= m || (i < n && L[at(i + 1, j)] >= L[at(i, j + 1)])) { mid.push(["-", A[i]]); i += 1; }
      else { mid.push(["+", B[j]]); j += 1; }
    }
  }
  return [...a.slice(0, p).map((l) => [" ", l]), ...mid, ...a.slice(a.length - s).map((l) => [" ", l])];
}

// ...cut into hunks with `ctx` lines around each change, numbered as git numbers them (a side with no lines starts one before)
export function hunksOf(oldText, newText, ctx = 3) {
  const ops = lineOps(linesOf(oldText), linesOf(newText)), pos = [];
  let o = 1, n = 1;
  for (const [op] of ops) { pos.push([o, n]); if (op !== "+") o += 1; if (op !== "-") n += 1; }
  const changed = ops.map(([op], k) => (op === " " ? -1 : k)).filter((k) => k >= 0);
  if (!changed.length) return [];
  const groups = [[changed[0], changed[0]]];
  for (const k of changed.slice(1)) { const g = groups.at(-1); if (k - g[1] - 1 <= 2 * ctx) g[1] = k; else groups.push([k, k]); }
  return groups.map(([s, e]) => {
    const a = Math.max(0, s - ctx), b = Math.min(ops.length - 1, e + ctx), lines = ops.slice(a, b + 1).map(([op, l]) => op + l);
    const oldLines = lines.filter((l) => l[0] !== "+").length, newLines = lines.filter((l) => l[0] !== "-").length;
    return { oldStart: oldLines ? pos[a][0] : pos[a][0] - 1, oldLines, newStart: newLines ? pos[a][1] : pos[a][1] - 1, newLines, lines };
  });
}
export const headerOf = (h) => h.oldStart == null ? "@@" : `@@ -${h.oldStart}${h.oldLines === 1 ? "" : `,${h.oldLines}`} +${h.newStart}${h.newLines === 1 ? "" : `,${h.newLines}`} @@`;

// ── a unified diff read back: per file, its hunks, its counts ────────────────────────────────────
const HEAD = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$/;
// one patch's hunks - git's, numbered, or a Codex apply_patch's bare "@@ <context>", which names no line
export function patchHunks(text) {
  const out = [];
  for (const l of String(text || "").replace(/\r\n/g, "\n").split("\n")) {
    if (l.startsWith("@@")) {
      const m = HEAD.exec(l);
      out.push(m ? { oldStart: +m[1], oldLines: m[2] == null ? 1 : +m[2], newStart: +m[3], newLines: m[4] == null ? 1 : +m[4], head: l, lines: [] }
        : { oldStart: null, head: l, lines: [] });
    } else if (out.length && /^[ +\-\\]/.test(l)) out.at(-1).lines.push(l);
    else if (!out.length && /^[+-]/.test(l) && !/^(\+\+\+|---) /.test(l)) { out.push({ oldStart: null, head: "@@", lines: [l] }); }     // an added file's lines with no @@
    else if (out.length && l === "" && out.at(-1).oldStart == null) out.at(-1).lines.push(" ");      // a bare patch's blank context line
  }
  return out.map((h) => ({ ...h, lines: h.lines.at(-1) === " " && h.oldStart == null ? h.lines.slice(0, -1) : h.lines }));
}
export const stat = (hunks) => hunks.reduce((t, h) => { for (const l of h.lines) { if (l[0] === "+") t.plus += 1; else if (l[0] === "-") t.minus += 1; } return t; }, { plus: 0, minus: 0 });
// a hunk as the server's revert reads it back (landing.revert): its @@ line and the lines under it, exactly as the diff had them
export const hunkText = (h) => [h.head || headerOf(h), ...h.lines].join("\n");

export function parseUnified(text) {
  const files = [];
  for (const chunk of String(text || "").replace(/\r\n/g, "\n").split(/^(?=diff --git )/m)) {
    if (!chunk.startsWith("diff --git ")) continue;
    const to = (/^\+\+\+ b\/(.+)$/m.exec(chunk) || [])[1], from = (/^--- a\/(.+)$/m.exec(chunk) || [])[1];
    const path = to || from || (/^diff --git a\/(.+?) b\/(.+)$/m.exec(chunk) || [])[2] || "";
    const body = chunk.slice(chunk.search(/^@@/m) >= 0 ? chunk.search(/^@@/m) : chunk.length);
    const hunks = patchHunks(body).map((h, i) => ({ ...h, index: i }));
    files.push({ path, hunks, ...stat(hunks), binary: /^Binary files /m.test(chunk), added: !from && !!to, removed: !to && !!from });
  }
  return files;
}

// ── each line with its numbers, old and new - none where the hunk names no line ──────────────────
export function numbered(h) {
  let o = h.oldStart, n = h.newStart;
  const known = o != null && n != null;
  return h.lines.map((l) => {
    const op = l[0] === "\\" ? "\\" : l[0] || " ", text = l.slice(1);
    const row = { op, text, old: known && op !== "+" && op !== "\\" ? o : null, new: known && op !== "-" && op !== "\\" ? n : null };
    if (known && op !== "+" && op !== "\\") o += 1;
    if (known && op !== "-" && op !== "\\") n += 1;
    return row;
  });
}

// ── what an edit in a session's record carries, as hunks (sessionrecord._edit / codingChat.stepsFromAcp) ──
// Claude's own patch (`hunks`, line numbers and all), a Codex patch (`patch`), or the before/after the tool was handed (`parts`): a WHOLE
// file's before and after (ACP's diff content, `whole`) is cut into hunks with git's context; a snippet's lines are shown whole, unnumbered
export function editHunks(edit) {
  if (!edit) return [];
  if (Array.isArray(edit.hunks)) return edit.hunks.map((h) => ({ oldStart: h.oldStart ?? null, oldLines: h.oldLines, newStart: h.newStart ?? null, newLines: h.newLines, lines: h.lines || [] }));
  if (edit.patch != null) return patchHunks(edit.patch);
  return (edit.parts || []).flatMap((p) => edit.whole ? hunksOf(p.old, p.new)
    : hunksOf(p.old, p.new, Infinity).map((h) => ({ ...h, oldStart: null, newStart: null })));
}

// ── a light highlighter: enough colour to read code by, nothing a library would add ──────────────
const KW = {
  py: "def class return if elif else for while in not and or import from as with try except finally raise pass None True False lambda yield async await is global nonlocal del assert break continue",
  js: "const let var function return if else for while do of in new class extends import export from default async await try catch finally throw null undefined true false typeof instanceof this switch case break continue",
  sh: "if then else fi for do done while case esac function return export local in echo",
};
const LANG = { py: "py", pyw: "py", js: "js", jsx: "js", mjs: "js", cjs: "js", ts: "js", tsx: "js", json: "js", css: "js", sh: "sh", bash: "sh", ps1: "sh", yml: "sh", yaml: "sh", toml: "sh" };
export const langOf = (path) => LANG[(/\.([A-Za-z0-9]+)$/.exec(String(path || "")) || [])[1]?.toLowerCase()] || "";
const RX = {
  py: /(#.*$)|("""[^]*?"""|'''[^]*?'''|[rbfu]?"(?:[^"\\]|\\.)*"|[rbfu]?'(?:[^'\\]|\\.)*')|\b(\d[\d_.]*)\b|\b([A-Za-z_]\w*)\b/g,
  js: /(\/\/.*$|\/\*.*?\*\/)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)|\b(\d[\d_.]*)\b|\b([A-Za-z_$][\w$]*)\b/g,
  sh: /(#.*$)|("(?:[^"\\]|\\.)*"|'[^']*')|\b(\d+)\b|\b([A-Za-z_][\w-]*)\b/g,
};
const KWS = Object.fromEntries(Object.entries(KW).map(([k, v]) => [k, new Set(v.split(" "))]));
// [{t, s}]: t is "com" | "str" | "num" | "kw" | "" - the line in order, every character in exactly one piece
export function tokens(line, lang) {
  const s = String(line ?? ""), rx = RX[lang];
  if (!rx) return [{ t: "", s }];
  const out = [], push = (t, x) => { if (!x) return; const last = out.at(-1); if (last && last.t === t) last.s += x; else out.push({ t, s: x }); };
  let at = 0;
  for (const m of s.matchAll(new RegExp(rx.source, rx.flags))) {
    push("", s.slice(at, m.index));
    push(m[1] ? "com" : m[2] ? "str" : m[3] ? "num" : KWS[lang].has(m[4]) ? "kw" : "", m[0]);
    at = m.index + m[0].length;
  }
  push("", s.slice(at));
  return out;
}
