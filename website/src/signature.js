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

// an empty box opens on the signature, two lines down for the words; a draft without it gets it once
export function withSignature(text, sig) {
  if (!norm(sig)) return text || "";
  if (!norm(text)) return `\n\n${norm(sig)}`;
  return hasSignature(text, sig) ? text : `${String(text).replace(/\s+$/, "")}\n\n${norm(sig)}`;
}

// what the owner actually wrote: a box holding only the signature is an empty box
export function withoutSignature(text, sig) {
  const t = String(text || "").replace(/\s+$/, ""), s = norm(sig);
  return s && t.endsWith(s) ? t.slice(0, -s.length).replace(/\s+$/, "") : t;
}
