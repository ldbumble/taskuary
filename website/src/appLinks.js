// THE APP'S OWN PAGES, AS LINKS (the owner, 2026-10-15: "if i ask the assistant to help me set up the intacct api, does it just
// open the sage intacct settings page? it should"). The Assistant names a page the way every other link here does - #connector=
// intacct, #settings=policies, #report=new-agent - and the canvas already knows every one of them (canvasLinks.js). This is the
// one reader: is a link one of ours, and open it.
import { canvasRequestFromHash } from "./canvasLinks.js";

// SETUP IS A MODE, not a page the canvas opens: its link asks for it the way the top bar's Setup does (TaskHubPage's openSetup).
// Without one, "set up taskuary" typed in the chat was answered with a link to Company Hub (2026-10-16)
const SETUP = "#setup";

// an in-app page link - one the canvas opens - or null (a web address, a task link handled elsewhere, anything unknown)
export const appLink = (href) => {
  const h = String(href || "").trim();
  if (h === SETUP) return h;
  if (!h.startsWith("#") || /^#task=/.test(h)) return null;
  const req = canvasRequestFromHash(h);
  return req && req.kind === "browse" ? h : null;
};

// the page a reply names, as written: [Open the Sage Intacct connection](#connector=intacct) - else the ONE task it points at
// ([TQ-0123](#task=123)); a reply that mentions several tasks in passing opens none of them
// ...and the same for pages (2026-10-19 UI walk): the model is asked for ONE link, and a reply with two opened the first. Setup is
// never opened from a reply: it is a mode that replaces the whole page, so "open my email settings" answered with a #setup link
// swapped the chat - the answer and the composer with it - for the setup screen. Its link stays in the words, to be pressed.
export const firstAppLink = (text) => {
  const links = [...new Set([...String(text || "").matchAll(/\]\((#[^)\s]+)\)/g)].map((m) => m[1]))];
  const pages = links.map(appLink).filter(Boolean);
  if (pages.length) return pages.length === 1 && pages[0] !== SETUP ? pages[0] : null;
  const tasks = [...new Set(links.filter((h) => /^#task=\d+$/.test(h)))];
  return tasks.length === 1 ? tasks[0] : null;
};

// open it on the canvas - the same road a bell or a bookmark takes; the same link twice still opens it again
export const openAppLink = (h) => {
  const want = String(h || "").replace(/^#/, "");
  if (!want) return;
  if (`#${want}` === SETUP) { window.dispatchEvent(new Event("tq-first-run")); return; }
  if (window.location.hash.replace(/^#/, "") === want) {
    window.location.hash = "";
    setTimeout(() => { window.location.hash = want; }, 0);
  } else window.location.hash = want;
};
