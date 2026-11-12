// A look at the walk's open page without driving it: node real-peek.mjs <name> [top|end|<px>] [reload] - the chat scrolled there, a screenshot,
// the task's head (its chip), the rail row, the box's hint and the server's word for "working", then the chat's words.
import { api, connect, open, shot, chat, sleep } from "./real-lib.mjs";
const [name, where = "end", reload] = process.argv.slice(2);
const { browser, page } = await connect();
// WHICH TASK: the one the page has open, by its own head (TQ-0007) - the address keeps no task once the page has taken it, so a reload
// came back to the desk with no task and the peek read nothing. TID names it where no task is open
const openTid = () => page.evaluate(() => Number((document.querySelector("[data-tq-task-page]")?.innerText.match(/TQ-0*(\d+)/) || [])[1]) || 0);
const tid = Number(process.env.TID) || await openTid();
if (reload) { await page.reload({ waitUntil: "domcontentloaded" }); await sleep(3000);
  if (tid && await openTid() !== tid) { await open(page, tid); await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 60000 }).catch(() => console.log("FINDING: the task did not open after the reload")); }
  await sleep(3000); }
await page.evaluate((w) => { const vp = document.querySelector("[data-tq-task-page] .tq-aui-viewport"); if (vp) vp.scrollTop = w === "top" ? 0 : w === "end" ? vp.scrollHeight : Number(w); }, where);
await sleep(400);
const srv = tid ? await api(`/api/tasks/${tid}/conversation`) : {};
const state = tid ? (await api(`/api/tasks/${tid}`))?.state ?? "" : "";
console.log(await shot(page, name));
console.log(JSON.stringify(await page.evaluate((ref) => ({ head: (document.querySelector("[data-tq-task-page]")?.innerText || "").split("\n").filter(Boolean).slice(0, 4).join(" | "),
  // ...the task's own row on the rail: its title line names the task, the line under it says where it stands
  rail: [...document.querySelectorAll(".t")].filter((e) => !e.closest("[data-tq-task-page]") && e.innerText.includes(ref)).map((e) => e.parentElement.innerText.replace(/\s+/g, " ").slice(0, 200))[0] || "",
  box: document.querySelector("[data-tq-task-page] .tq-aui-input")?.getAttribute("placeholder") || "", dots: !!document.querySelector("[data-tq-task-page] [data-tq-working]") }), `TQ-${String(tid).padStart(4, "0")}`)),
  "| server working", srv.working, "| state", state, "| items", (srv.items || []).map((x) => `${x.kind}${x.state ? ":" + x.state : ""}`).slice(-4).join(" "));
console.log((await chat(page)).slice(-(Number(process.env.CHAT_TAIL) || 500)));
await browser.disconnect();
