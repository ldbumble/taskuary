// Browser preference only: changing appearance must not refetch work or restart an agent.
export const THEME_KEY = "taskuary.theme";
const valid = (v) => v === "light" || v === "dark" ? v : null;

export function createThemeController({ root = document.documentElement, storage = () => localStorage,
  media = window.matchMedia("(prefers-color-scheme: dark)"), events = window } = {}) {
  let choice = null, mode;
  try { choice = valid(storage().getItem(THEME_KEY)); } catch { /* private/embedded browsers can deny storage */ }
  const listeners = new Set();
  const apply = () => {
    const next = choice || (media.matches ? "dark" : "light");
    root.dataset.theme = next;
    root.style.colorScheme = next;
    if (next === mode) return;
    mode = next;
    listeners.forEach((f) => f());
  };
  const system = () => { if (!choice) apply(); };
  const changed = (e) => {
    if (e.key !== THEME_KEY && e.key !== null) return;
    try { if (e.storageArea && e.storageArea !== storage()) return; } catch { return; }
    choice = valid(e.newValue); apply();
  };
  apply();
  return {
    getSnapshot: () => mode,
    toggle: () => {
      choice = mode === "dark" ? "light" : "dark";
      try { storage().setItem(THEME_KEY, choice); } catch { /* keep the in-memory choice usable */ }
      apply();
    },
    subscribe: (f) => {
      if (!listeners.size) { media.addEventListener("change", system); events.addEventListener("storage", changed); }
      listeners.add(f);
      return () => {
        listeners.delete(f);
        if (!listeners.size) { media.removeEventListener("change", system); events.removeEventListener("storage", changed); }
      };
    },
  };
}
