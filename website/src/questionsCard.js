// THE AGENT'S QUESTIONS, ONE CARD (taskuary/proposals.py 'questions'; the owner, 2026-11-26: an agent that interviews him asks on one card,
// answered together with one press). Its data read for the one review card (Artifact ReviewCard): each question a field of type `ask` - a pick
// where the agent gave choices, a box to type in always - and, once pressed, the same fields read-only with what he answered.
export const isAsks = (p) => p?.action === "questions";
export const asksOf = (p) => (isAsks(p) && Array.isArray(p.questions) ? p.questions : []).filter((q) => q && String(q.question || "").trim())
  .map((q) => ({ question: String(q.question).trim(), choices: (Array.isArray(q.choices) ? q.choices : []).map(String).filter(Boolean) }));
// ...what he answered, in the questions' order: the receipt's (proposals.receipt: result.answers) once pressed
export const answersOf = (receipt) => (Array.isArray(receipt?.result?.answers) ? receipt.result.answers : []).map((a) => String(a?.answer ?? ""));
export const answeredAny = (answers) => (answers || []).some((a) => String(a || "").trim());
// `answers`: his, by place; `onChange(i, value)`: given only while the card waits
export const askFields = (p, answers = [], onChange = null) => asksOf(p).map((q, i) => ({ key: `ask-${i}`, type: "ask", label: q.question, choices: q.choices,
  value: String(answers[i] ?? ""), editable: !!onChange, ...(onChange ? { onChange: (v) => onChange(i, v) } : {}) }));
export const asksLine = (p) => { const n = asksOf(p).length; return `${n} question${n === 1 ? "" : "s"} · your answers go to the agent together`; };
// the answers as the press sends them: one per question, trimmed, "" where he left one empty
export const answersFor = (p, answers = []) => asksOf(p).map((_, i) => String(answers[i] ?? "").trim());
