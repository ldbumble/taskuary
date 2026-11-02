// A RIGHT-CLICK FIXES A TYPO (TQ-1251: "taskuary is catching the typos, but not allowing me to edit them by clicking on it"). The
// desktop window had its web view's own menu off - where the spelling suggestions live - and desktop.allow_text_menus turns it back on.
// This keeps that menu where it belongs: in a box you type in, or over text you selected (Copy). Anywhere else a right-click still does
// nothing, as before. A browser tab is left alone: its menu was never off.

export const typedInto = (el) => {
  for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
    if (n.isContentEditable) return true;
    const tag = n.tagName;
    if (tag === "TEXTAREA") return !n.readOnly && !n.disabled;
    if (tag === "INPUT") return !n.readOnly && !n.disabled && !/^(button|checkbox|color|file|hidden|image|radio|range|reset|submit)$/i.test(n.type || "");
  }
  return false;
};

// true: the menu stays shut for this right-click
export const shutMenu = (target, w = window) => !!w.pywebview && !typedInto(target) && !String(w.getSelection?.() || "").trim();

export const installTextMenu = (doc = typeof document === "undefined" ? null : document) => {
  if (!doc || doc.__tqTextMenu) return () => {};
  doc.__tqTextMenu = true;
  const on = (e) => { if (!e.defaultPrevented && shutMenu(e.target, doc.defaultView)) e.preventDefault(); };
  doc.addEventListener("contextmenu", on);
  return () => { doc.__tqTextMenu = false; doc.removeEventListener("contextmenu", on); };
};
