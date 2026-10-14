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

export function issueUrl(title, body, max = 7500) {
  const ok = (b) => link(title, b).length <= max;
  if (ok(body)) return { url: link(title, body), cut: false };
  let b = body.replace(/<details>[\s\S]*?<\/details>\n*/, "");
  if (!ok(b)) b = b.replace(/### Error\n[\s\S]*?(?=\n### Environment|$)/, `### Error\n${NOTE}\n`);
  if (!ok(b)) {                                       // still over: the explanation itself is huge - binary-search its longest fitting head
    const m = b.match(/(### What happened\n)([\s\S]*?)(\n\n### |$)/);
    if (m) {
      const at = m.index + m[1].length, tail = `\n${NOTE}`, mk = (n) => b.slice(0, at) + m[2].slice(0, n) + tail + b.slice(at + m[2].length);
      let lo = 0, hi = m[2].length;
      while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (ok(mk(mid))) lo = mid; else hi = mid - 1; }
      b = mk(lo);
    }
  }
  return { url: link(title, b), cut: true };
}
