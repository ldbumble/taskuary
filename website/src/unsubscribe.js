// UNSUBSCRIBE ON AN FYI (the owner, 2026-10-22, picked from the gaps): a list that names its own way off it (`card.unsub`, read off
// its List-Unsubscribe headers at ingest - taskuary/unsubscribe.py) is left on the owner's press. One-click is done by the server;
// otherwise the list's page or mail is the owner's to finish - the desktop app opens it through the server (it has no browser of
// its own, as Report this bug), a tab opens it here.
import { howToOpen } from "./bugReportOpen.js";

export const canUnsubscribe = (item) => !!(item?.mid && item?.unsub);

export async function unsubscribeFrom(api, mid, w = typeof window === "undefined" ? null : window) {
  const { data } = await api.post(`/api/messages/${mid}/unsubscribe`, { open: howToOpen(w) === "app" });
  if (data?.link && !data.opened) w?.open?.(data.link, "_blank", "noopener");
  return data;
}
