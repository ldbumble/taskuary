// Today's meetings, drawn the moment the page is: the strip used to fetch on mount and pop in a beat
// later, pushing the day's summary down under it (the owner, 2026-09-23: "the calendar widget does not
// load right away and then reloads with it. Show it right away"). The last answer is kept - in memory
// for a tab switch, in the browser for a reload - and shown at once while a fresh one is fetched. Only
// TODAY's answer is ever shown: a stale day's meetings are worse than none.
import { useEffect, useState } from "react";
import api from "./api.js";

const KEY = "taskuary_calendar_today";
const today = () => new Date().toLocaleDateString("en-CA");        // YYYY-MM-DD, local
let held = null, flight = null;
const subs = new Set();

const saved = () => {
  try { const v = JSON.parse(window.localStorage.getItem(KEY) || "null"); return v?.date === today() ? v : null; }
  catch { return null; }
};
const keep = (data) => {
  held = data;
  try { window.localStorage.setItem(KEY, JSON.stringify(data)); } catch { /* private window: memory only */ }
  subs.forEach((f) => f(data));
};

export const cachedToday = () => (held?.date === today() ? held : (held = saved()));

export function refreshToday() {
  if (!flight) flight = api.get("/api/calendar/today")
    .then(({ data }) => keep({ ...data, date: data?.date || today() }))
    .catch(() => { if (!cachedToday()) keep({ date: today(), events: [] }); })
    .finally(() => { flight = null; });
  return flight;
}

export function useCalendarToday() {
  const [data, setData] = useState(cachedToday);
  useEffect(() => {
    subs.add(setData);
    refreshToday();
    return () => { subs.delete(setData); };
  }, []);
  return data;
}
