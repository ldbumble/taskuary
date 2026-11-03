// AN FYI ROW SAYS ITS THING ONCE.
//
// The card drew the item's title and then its gist underneath. For mail those are a subject and a
// body and the two lines earn their place - but an assistant's idea has no subject: the funnel files
// the sentence as the title AND the body gist, so the card printed the same sentence twice, truncated
// at two different points, and the eye had nowhere to land (the owner, 2026-09-14: "they eyes don't
// focus on one thing").
import { pictureWords } from "./mailLinks.js";

export const norm = (s) => String(s || "").replace(/\s+/g, " ").trim().toLowerCase();

// The second line, or nothing: a gist that merely restates the line above it is not a second fact.
// Compared on the opening words, because the two are cut to different lengths (140 and 240).
// ...and a mail that is only a picture says so, never "[image: ...]" (mailLinks.pictureWords)
export const gistFor = (item, n = 48) => {
  const gist = pictureWords(item?.summary || item?.preview).trim();
  if (!gist) return "";
  const a = norm(gist), b = norm(item?.title);
  if (!b) return gist;
  const head = Math.min(n, a.length, b.length);
  return a.slice(0, head) === b.slice(0, head) ? "" : gist;
};
