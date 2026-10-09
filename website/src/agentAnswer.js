// THE AGENT'S ANSWER, SHORT (the owner, 2026-10-09: "I like the 7 items the agent did. that's main thing. show small list then
// click more"). The saved answer (session_artifacts.result) is a heading, a greeting, a line of intro and then its numbered
// items; the card shows one line per item and the whole of it one click away.

const SENTENCE = /^(.+?[.!?:])(\s|$)/;

// "1. Supervisor upload template. The page now has ..." -> "Supervisor upload template." - the item's own first sentence, cut short
const short = (text, max = 110) => {
  const t = String(text || "").replace(/\*\*/g, "").trim(), m = SENTENCE.exec(t);
  const s = m ? m[1] : t;
  return s.length > max ? `${s.slice(0, max - 1).trimEnd()}…` : s;
};

export function answerOutline(text) {
  let body = String(text || "").replace(/\r\n/g, "\n").trim();
  // the '# TQ-0001 - <title>' heading is the task's title (it can run over lines), not the answer
  if (body.startsWith("# ")) body = body.replace(/^# [\s\S]*?(\n\s*\n|$)/, "").trim();
  const lines = body.split("\n");
  const items = [], intro = [];
  for (const line of lines) {
    const m = /^(\d+)[.)]\s+(.+)/.exec(line);
    if (m) items.push({ n: Number(m[1]), short: short(m[2]) });
    else if (!items.length && line.trim() && !/^(hi|hello|hey|dear)\b[^.]*,?\s*$/i.test(line.trim())) intro.push(line.trim());
  }
  return { intro: intro.length ? short(intro.join(" "), 220) : "", items, full: body };
}
