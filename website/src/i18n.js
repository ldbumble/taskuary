import messages from "./pt-BR.json" with { type: "json" };

let locale = "pt-BR";
const listeners = new Set();
export const getLocale = () => locale;
export const subscribeLocale = (listener) => { listeners.add(listener); return () => listeners.delete(listener); };
export function setLocale(value) {
  const next = value === "en" ? "en" : "pt-BR";
  if (next === locale) return;
  locale = next;
  for (const listener of listeners) listener();
}
export function t(english, values = {}) {
  const text = locale !== "en" && Object.hasOwn(messages, english) ? messages[english] : english;
  return typeof text === "string" ? text.replace(/\{(\w+)\}/g, (match, key) => Object.hasOwn(values, key) ? String(values[key]) : match) : text;
}
// Metadata is presentation only. Never replace canonical groups, option values or setting keys.
export function localized(metadata, field) {
  return metadata?.i18n?.[locale]?.[field] ?? t(metadata?.[field]);
}
export function groupLabel(schema, group) {
  return schema?.group_labels?.[locale]?.[group] ?? t(group);
}
export async function loadLocale(api) {
  const { data } = await api.get("/api/settings");
  const rows = data.data ?? data;
  setLocale(Array.isArray(rows) ? rows.find((row) => row.Name === "locale")?.Value : "pt-BR");
}
export async function saveLocale(api, value) {
  if (!["pt-BR", "en"].includes(value)) throw new TypeError("Unsupported locale");
  await api.patch("/api/settings", { name: "locale", value });
  setLocale(value);
}
