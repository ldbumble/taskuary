// A DISPLAY NAME AS A PERSON IS CALLED (triage.person_name / waiton.person on the server): Outlook's "Doyle, Alex M. at Northwind" reads
// "Alex M. Doyle" - every place the page draws a sender's name reads it here (the owner, 2026-11-25: a "Last, First" sender read "Trust Doyle,").
// Pure, so node --test reads it.
export const personName = (name) => {
  let n = String(name || "").replace(/\s*<[^>]*>/g, "").replace(/"/g, " ").replace(/\s+/g, " ").trim();
  if (!n || n.includes("@")) return n;
  n = n.replace(/\s+at\s+[^,<>@]+$/i, "").trim();
  const parts = n.split(",");
  if (parts.length === 2 && parts[0].trim() && parts[1].trim() && parts[0].trim().split(" ").length <= 2) n = `${parts[1].trim()} ${parts[0].trim()}`;
  return n;
};
// ...and the name a message's sender goes by: its FromName as they are called, else its address
export const senderName = (m) => personName(m?.FromName) || String(m?.FromEmail || "");
export const firstName = (who) => personName(who).split(/[\s@]+/)[0] || "";
