// Which channels can actually carry a ping. Mirrors outbound.py notify_targets exactly -
// anything else wearing the notify role is a switch that goes nowhere, so we neither offer
// it on the connector card nor count it as a working setup here.
export const CAN_NOTIFY = new Set(["telegram", "whatsapp", "teams"]);

const cfg = (s) => { try { return JSON.parse(s || "{}"); } catch { return {}; } };
export const notifyChat = (c) => String(cfg(c.ConfigJson).notify_chat || "").trim();
export const hasNotifyRole = (c) => String(c.Roles || "").split(",").includes("notify");

// One verdict for Settings → Notifications: is this actually wired up, and if not, what is
// missing. Pure, because the awkward cases are exactly the ones worth testing - a role with
// no chat, a named chat on a connector that is switched OFF, and a stale role left behind on
// a channel that cannot send (the card no longer offers the switch, so it cannot be cleared).
export function notifyState(connectors, level = "needs_me", phoneApprovals = false) {
  const all = (connectors || []).filter(hasNotifyRole);
  const able = all.filter((c) => CAN_NOTIFY.has(c.Type));
  const named = able.filter((c) => c.Active && notifyChat(c));
  const phoneNamed = named.filter((c) => c.Type === "telegram" || c.Type === "whatsapp");
  const asleep = able.filter((c) => !c.Active && notifyChat(c));
  const unnamed = able.filter((c) => !notifyChat(c));
  const stale = all.filter((c) => !CAN_NOTIFY.has(c.Type));
  const names = (cs) => cs.map((c) => c.Name).join(", ");
  const note = stale.length ? ` ${names(stale)} still carries the role but cannot send — clear it on its card.` : "";
  const one = (cs) => cs.length === 1;
  if (level === "off") return { kind: "off", targets: [], stale,
    text: "Pushes are off — nothing is sent, even if a chat is named." + note };
  if (named.length) return { kind: "pinging", targets: named, stale,
    text: `Pinging ${named.map((c) => `${c.Name} · ${notifyChat(c)}`).join(" · ")}`
      + (phoneApprovals && phoneNamed.length ? " — reply there to answer agents or approve drafts" : "")
      + (phoneApprovals && !phoneNamed.length ? " — phone replies need a Telegram or WhatsApp notify chat" : "") + note };
  if (asleep.length) return { kind: "inactive", targets: asleep, stale,
    text: `${names(asleep)} ${one(asleep) ? "names a chat but is" : "name chats but are"} switched off`
      + ` — enable ${one(asleep) ? "it" : "them"} on the connector card.` + note };
  if (unnamed.length) return { kind: "unnamed", targets: unnamed, stale,
    text: `${names(unnamed)} ${one(unnamed) ? "has" : "have"} the Notifications role, but no chat is named yet`
      + " — set it under Connectors → Credentials." + note };
  return { kind: "none", targets: [], stale,
    text: "No notify chat yet — on a Telegram, WhatsApp or Teams card, add the Notifications role"
      + " and name the chat in Credentials." + note };
}
