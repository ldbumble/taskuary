// THE CHECK-BACK ON A TASK, IN A FEW WORDS (the owner, 2026-11-06): "Checks back Tue 9 AM" - the day short, the hour without ":00", a date
// once it is a week or more away. The agent sets it (checkback.py); the chip's × cancels it. Pure, so node --test reads it.
import { asUtc, dtf, tzNow } from "./dates.js";

const opt = (o) => (tzNow() ? { ...o, timeZone: tzNow() } : o);
// `task`: the row (CheckBackAt, CheckBackWhat, Status) - null with none waiting or a closed task, as the server reads it (checkback.of_task)
export const checkBackOf = (task) => {
  const at = String(task?.CheckBackAt || "").trim();
  return at && !["done", "dropped"].includes(task?.Status) ? { at, what: String(task?.CheckBackWhat || "").trim() } : null;
};
export const checkBackWhen = (at, now = new Date()) => {
  const d = at ? asUtc(at) : null;
  if (!d || Number.isNaN(d.getTime())) return "";
  const time = dtf("en-US", opt({ hour: "numeric", minute: "2-digit" })).format(d).replace(":00", "");
  const day = d - now >= 6.5 * 86400000 ? dtf("en-US", opt({ month: "short", day: "numeric" })).format(d) : dtf("en-US", opt({ weekday: "short" })).format(d);
  return `${day} ${time}`;
};
export const checkBackLine = (at, now) => { const w = checkBackWhen(at, now); return w ? `Checks back ${w}` : ""; };
