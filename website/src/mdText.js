// What md.jsx decides from the text alone, kept out of the JSX so a node test can pin it.

// what an emoji-sectioned digest does NOT have: markdown headings, tables, bold, list markers - and the code
// fences, inline code and links a chat answer carries. A reply that was only an ascii diagram in a fence read as
// prose: every line its own paragraph, the spacing collapsed, the boxes in pieces (2026-10-06).
export const looksMd = (s) => /^#{1,6} |^\s*\|.*\|\s*$|\*\*[^*]+\*\*|^\s*[-*] |^\s*\d+\. |^\s*```|`[^`\n]+`|\[[^\]\n]+\]\([^)\s]+\)/m.test(String(s || ""));

// a task's ref is one word: "TQ-0001" broke at its hyphen in a narrow table column, the ref on two lines
export const REF = /\b(TQ-\d+)\b/;
export const refParts = (s) => String(s).split(REF);              // odd indexes are the refs
