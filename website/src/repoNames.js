// The repository a piece of text NAMES outright - shared by the Start panel's RepoSelect and the New card's picker, and plain JS
// so a test can import it without a JSX loader.
export const namedRepo = (rows, text) => {
  // whole words only: "ledger" names northwind/ledger, "ledgers" and "my-ledger-notes" do not
  const words = new Set(String(text || "").toLowerCase().split(/[^a-z0-9_./-]+/).map((w) => w.replace(/[./-]+$/, "")));
  const hits = new Set((rows || []).filter((r) => [r.repo, r.repo.split("/").pop()]
    .some((n) => n.length >= 4 && words.has(n.toLowerCase()))).map((r) => r.repo));
  return hits.size === 1 ? [...hits][0] : "";
};
