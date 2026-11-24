// WHERE A TEXT CHANGED, IN THE TEXT (the owner, 2026-11-24: "show also where it changed in the full text"): the new words whole, each run he
// would not find in the old marked added, and each old run that is gone marked at the place it stood - word by word, as tracked changes read.
// [{t: "same" | "add" | "del", s}] in reading order; the "same" and "add" parts joined are the new text exactly. No React, so it runs under node.
// ...a word and the space after it are one token: matched apart, the spaces between two rewrites stitched them into one word salad
const tokens = (s) => String(s ?? "").match(/\S+\s*|\s+/g) || [];
const words = (s) => (s.match(/\S+/g) || []).length;
const MAX = 4e6;                // ...past this many cells the middle is one removed run and one added run between their shared ends

export function wordDiff(was, now) {
  // ...matched by the word alone, written as the new text has it: "end." last in the old is "end. " before what he adds after it
  const a = tokens(was), b = tokens(now), A = a.map((t) => t.trim()), B = b.map((t) => t.trim());
  let lo = 0, ea = a.length, eb = b.length;
  while (lo < ea && lo < eb && A[lo] === B[lo]) lo++;
  while (ea > lo && eb > lo && A[ea - 1] === B[eb - 1]) { ea--; eb--; }
  const out = [], push = (t, s) => { if (!s) return; const l = out[out.length - 1]; if (l?.t === t) l.s += s; else out.push({ t, s }); };
  push("same", b.slice(0, lo).join(""));
  const x = a.slice(lo, ea), y = b.slice(lo, eb), X = A.slice(lo, ea), Y = B.slice(lo, eb), n = x.length, m = y.length;
  if (n * m > MAX) { push("del", x.join("")); push("add", y.join("")); }
  else {
    // the longest run the two share (LCS), read back from its end table
    const L = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = X[i] === Y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
    let i = 0, j = 0;
    while (i < n || j < m) {
      if (i < n && j < m && X[i] === Y[j]) { push("same", y[j]); i++; j++; }
      else if (i < n && (j >= m || L[i + 1][j] >= L[i][j + 1])) push("del", x[i++]);       // ...what went before what came, as tracked changes read
      else push("add", y[j++]);
    }
  }
  push("same", b.slice(eb).join(""));
  // ...and a word or two kept between two changes is part of one rewrite: what went said whole, then what came, never every other word
  const said = []; let del = "", add = "";
  const flush = () => { if (del) said.push({ t: "del", s: del }); if (add) said.push({ t: "add", s: add }); del = add = ""; };
  out.forEach((p, k) => {
    if (p.t === "del") del += p.s; else if (p.t === "add") add += p.s;
    else if ((del || add) && k < out.length - 1 && words(p.s) < 3) { del += p.s; add += p.s; }
    else { flush(); said.push(p); }
  });
  flush();
  return said;
}
export const hasChange = (parts) => parts.some((p) => p.t !== "same");
// ...as spans of the new text for the box he types in (ui.DraftField `marks`): [start, end, "add"] over each added run, [at, at, "del"] where
// a removed run stood - kept as he types, read again from the words in the box
export const changeMarks = (parts) => {
  const out = []; let at = 0;
  for (const p of parts) { if (p.t === "del") out.push([at, at, "del"]); else { if (p.t === "add") out.push([at, at + p.s.length, "add"]); at += p.s.length; } }
  return out;
};
