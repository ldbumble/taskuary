// THE SIGNATURE IN THE REPLY BOX (signatures.py; the owner, 2026-10-28: "It should use the default signature always"): the box
// shows the block that will go under the email, so what is in it is what goes. Same test as responder.with_signature: a text
// whose tail already holds it - the drafter's, or the owner's own - is not signed twice.
const norm = (s) => String(s || "").trim();

export function hasSignature(text, sig) {
  const t = norm(text).toLowerCase(), s = norm(sig).toLowerCase();
  if (!s) return true;
  const lines = s.split("\n").map((l) => l.trim()).filter(Boolean);
  const tail = t.slice(-Math.max(400, s.length + 40));
  return tail.includes(s) || (lines.length > 0 && tail.includes(lines[0]) && tail.includes(lines[lines.length - 1]));
}

// THE WRITER'S OWN SIGN-OFF, by shape (responder.strip_signoff, as responder.signed calls it): trailing lines that are a line of the
// signature or its first word, and above a cut one a line ending in a comma - "Best,\nAlex Doyle" under a block that starts
// "Alex Doyle" was kept, and the box signed it twice (walk 2026-10-29). No word decides it: only the owner's own lines.
const bare = (l) => String(l).split(/\s+/).join(" ").replace(/^[ ,.!-]+|[ ,.!-]+$/g, "").toLowerCase();
export function stripSignoff(text, sig) {
  const ls = norm(sig).split("\n").map((l) => l.trim()).filter(Boolean);
  const keep = new Set([...ls, ...ls.map((l) => l.split(/\s+/)[0])].map(bare).filter(Boolean));
  const lines = String(text || "").replace(/\s+$/, "").split("\n");
  let n = 0;
  while (lines.length && (!lines[lines.length - 1].trim() || keep.has(bare(lines[lines.length - 1])))) n += lines.pop().trim() ? 1 : 0;
  if (n && lines.length && lines[lines.length - 1].trimEnd().endsWith(",")) lines.pop();
  return lines.join("\n").trim();
}

// an empty box opens on the signature, two lines down for the words; a draft without it gets it once, its writer's own sign-off
// taken off first - what responder.signed does to every draft the server files
export function withSignature(text, sig) {
  if (!norm(sig)) return text || "";
  if (!norm(text)) return `\n\n${norm(sig)}`;
  if (String(text).replace(/\s+$/, "").endsWith(norm(sig))) return text;
  const body = stripSignoff(text, sig) || String(text).replace(/\s+$/, "");
  return hasSignature(body, sig) ? body : `${body}\n\n${norm(sig)}`;
}

// what the owner actually wrote: a box holding only the signature is an empty box
export function withoutSignature(text, sig) {
  const t = String(text || "").replace(/\s+$/, ""), s = norm(sig);
  return s && t.endsWith(s) ? t.slice(0, -s.length).replace(/\s+$/, "") : t;
}
