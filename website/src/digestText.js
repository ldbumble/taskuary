// Morning-digest text has two valid shapes: the AI's compact emoji sections, or the labelled
// evidence blocks attached when that AI call fails. Keep the parser presentation-only: it groups
// and labels what is already there, but never decides whether a person or topic is relevant.
const RAW_HEADINGS = [
  ["MEETINGS TODAY", "📅 Meetings today"],
  ["THEIR ASKS YOU HAVE NOT ANSWERED", "🙋 People want"],
  ["MY OPEN LOOPS", "🔁 Follow up"],
  ["WAITING ON THE OWNER", "⏳ Waiting on you"],
  ["WHAT PEOPLE SAID", "💬 What people said"],
  ["OUT OF OFFICE", "🌴 Out of office"],
  ["WHAT ARRIVED", "📥 What arrived"],
  ["WHAT THE OWNER HAS ALREADY DECIDED", "📌 Memory in effect"],
  ["OPEN WORK", "🚀 In flight"],
  ["FINISHED THIS WINDOW", "✅ Finished"],
  ["VERDICTS GIVEN THIS WINDOW", "📌 Decisions"],
  ["WHAT THE ASSIST" + "ANT ALREADY RAISED", "💡 New ideas"],
  ["THE ASSIST" + "ANT'S NOTES TO ITSELF", "🗒️ Advisor context"],
  ["THE WINDOW IN NUMBERS", "📊 At a glance"],
];

const emojiHeading = (line) => /^\s*\p{Extended_Pictographic}/u.test(line);
const rawHeading = (line) => RAW_HEADINGS.find(([raw]) => line.trimStart().startsWith(raw));
const cleanItem = (line) => line.trim().replace(/^[-*]\s+/, "").replace(/^\d+[.)]\s+/, "");

export function digestSections(text) {
  const sections = [];
  let current = null;
  let meta = "";
  const section = (title) => {
    current = sections.find((s) => s.title === title);
    if (!current) { current = { title, items: [] }; sections.push(current); }
  };
  for (const raw of String(text || "").replace(/\r/g, "").split("\n")) {
    const line = raw.trimEnd();
    if (!line.trim() || line.trim() === "--- raw data ---") continue;
    if (/^NOW:\s*/.test(line)) { meta = line.replace(/^NOW:\s*/, ""); continue; }
    const mapped = rawHeading(line);
    if (mapped) { section(mapped[1]); continue; }
    if (emojiHeading(line)) { section(line.trim().replace(/[:\s]+$/, "")); continue; }
    // This is the second line of one legacy internal heading, not a digest item.
    if (/^\s*and the mail they quote is already decided\):?$/i.test(line)) continue;
    const item = cleanItem(line);
    if (!item || /^\(none\)$/i.test(item)) continue;
    if (!current) section("📊 At a glance");
    // Indented quote/detail lines belong to the person or meeting immediately above them.
    if (/^\s{4,}/.test(raw) && current.items.length) current.items[current.items.length - 1] += `\n${item}`;
    else current.items.push(item);
  }
  return { meta, sections: sections.filter((s) => s.items.length) };
}

export function parseDigest(text) {
  const body = String(text || "").replace(/\r/g, "").trim();
  const failed = /^\((?:AI summary failed|AI prompt set, but no active AI connector|the model returned an empty summary)/i.test(body);
  if (!failed) return { error: "", source: "", ...digestSections(body) };
  const lines = body.split("\n");
  const sourceAt = lines.findIndex((line) => /^NOW:\s*/.test(line));
  const errorLines = lines.slice(0, sourceAt < 0 ? lines.length : sourceAt).filter((line) => line.trim());
  const error = errorLines.join(" ")
    .replace(/^\(AI summary failed:\s*/i, "")
    .replace(/^\(AI prompt set, but no active AI connector\s*-?\s*/i, "No active AI connector. ")
    .replace(/^\(the model returned an empty summary\s*-?\s*/i, "The model returned an empty summary. ")
    .replace(/\)\s*$/, "").trim();
  const source = sourceAt < 0 ? "" : lines.slice(sourceAt).join("\n");
  return { error: error.slice(0, 360), source, ...digestSections(source) };
}
