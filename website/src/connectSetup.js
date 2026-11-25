// The connection a card's Connect opens (outbound.connect_fix's `#connector=<type>`) - '' for a link that is not one connection's own card
// (Email's section, the images section): those still open where they point.
export const setupType = (href) => (/^#connector=([a-z0-9_-]+)$/i.exec(String(href || "")) || [])[1]?.toLowerCase() || "";

// WHICH CARD A CONNECTION'S SETUP IS - one answer for the Connections page and for the setup a card's Connect brings up under it
// (ConnectorsView.ConnectionCard). The inline one drew the mail form for every type: a LinkedIn or Bluesky card (a data card, its own
// fields, Test and sign-in) came up as a lone greyed Connect with nothing to fill. `data`: the data cards' table, `tools`: the agent tools'.
// `inline`: a mailbox under a card is the short form (one Connect that signs in, tests and reads), as on the first run.
const OWN = { mssql: "mssql", winrm: "winrm", reason_network: "reason", agent_desktop: "desktop" };
export const MAIL_CARDS = ["outlook", "gmail", "imap"];
export const cardKind = (type, { data = {}, tools = new Set() } = {}, inline = false) =>
  OWN[type] || (tools.has(type) ? "tool" : data[type] ? "data" : inline && MAIL_CARDS.includes(type) ? "mail" : "channel");
