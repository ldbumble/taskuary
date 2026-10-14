// The GitHub issue, built from exactly the text the popup shows (the person may have edited it).
// The tracker link carries everything in the query string, so it has a ceiling: past `max` encoded
// characters the technical parts go first - Log, then Error - and only then the explanation's tail.
// The title and the start of "What happened" are what a maintainer needs to triage, so they stay.
const NEW = "https://github.com/ldbumble/taskuary/issues/new", NOTE = "(cut - the full report was copied to your clipboard)";

export const issueBody = (d) => `### What happened
${d.explanation}

### Where
${d.where}

### Error
${d.error}

### Environment
${d.env}

<details><summary>Log lines</summary>

${d.log}
</details>

fingerprint: ${d.fingerprint}
`;

export const fullReport = (title, body) => `${title}\n\n${body}`;

const link = (title, body) => `${NEW}?${new URLSearchParams({ title, body, labels: "bug" })}`;

// a slice that never ends in half a surrogate pair (it would encode as U+FFFD)
const head = (s, n) => { const t = s.slice(0, n); return /[\ud800-\udbff]$/.test(t) ? t.slice(0, -1) : t; };
const LOG = "<details><summary>Log lines</summary>";

export function issueUrl(title, body, max = 7500) {
  const ok = (t, b) => link(t, b).length <= max, done = (t, b) => ({ url: link(t, b), cut: true });
  // the longest n for which f(n) still holds (encoded length only grows with n)
  const fit = (n, f) => { let lo = 0, hi = n; while (lo < hi) { const m = (lo + hi + 1) >> 1; if (f(m)) lo = m; else hi = m - 1; } return lo; };
  if (ok(title, body)) return { url: link(title, body), cut: false };
  let b = body;
  const i = b.lastIndexOf(LOG), j = i < 0 ? -1 : b.indexOf("</details>", i);     // the last one: an Error may quote the tag
  if (j >= 0) b = `${b.slice(0, i)}${LOG}\n\n${NOTE}\n${b.slice(j)}`;
  if (!ok(title, b)) b = b.replace(/### Error\n[\s\S]*?(?=\n### Environment|$)/, `### Error\n${NOTE}\n`);
  if (ok(title, b)) return done(title, b);
  const m = b.match(/(### What happened\n)([\s\S]*?)(\n\n### |$)/);          // then the explanation's tail
  if (m) {
    const at = m.index + m[1].length, mk = (n) => `${b.slice(0, at)}${head(m[2], n)}\n${NOTE}${b.slice(at + m[2].length)}`;
    const n = fit(m[2].length, (k) => ok(title, mk(k)));
    if (ok(title, mk(n))) return done(title, mk(n));
  }
  const mkb = (n) => `${head(b, n)}\n${NOTE}`;                                 // headings edited away or other parts huge: cut the body itself
  b = mkb(fit(b.length, (k) => ok(title, mkb(k))));
  if (ok(title, b)) return done(title, b);
  return done(head(title, fit(title.length, (k) => ok(head(title, k), b))), b);
}
