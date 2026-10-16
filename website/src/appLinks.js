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
export const firstAppLink = (text) => {
  const links = [...String(text || "").matchAll(/\]\((#[^)\s]+)\)/g)].map((m) => m[1]);
  const page = links.map(appLink).find(Boolean);
  if (page) return page;
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
