// A look at the walk's open page without driving it: node real-peek.mjs <name> [top|end|<px>] [reload] - the chat scrolled there, a screenshot,
// the task's head (its chip), the rail row, the box's hint and the server's word for "working", then the chat's words.
import { api, connect, shot, chat, sleep } from "./real-lib.mjs";
const [name, where = "end", reload] = process.argv.slice(2);
const { browser, page } = await connect();
if (reload) { await page.reload({ waitUntil: "domcontentloaded" }); await sleep(6000); }
await page.evaluate((w) => { const vp = document.querySelector("[data-tq-task-page] .tq-aui-viewport"); if (vp) vp.scrollTop = w === "top" ? 0 : w === "end" ? vp.scrollHeight : Number(w); }, where);
await sleep(400);
const tid = Number((await page.evaluate(() => location.hash)).match(/task=(\d+)/)?.[1]);
const srv = tid ? await api(`/api/tasks/${tid}/conversation`) : {};
console.log(await shot(page, name));
console.log(JSON.stringify(await page.evaluate(() => ({ head: (document.querySelector("[data-tq-task-page]")?.innerText || "").split("\n").filter(Boolean).slice(0, 4).join(" | "),
  rail: [...document.querySelectorAll("[data-tq-row]")].map((e) => e.innerText.replace(/\s+/g, " ")).find((t) => /TQ-/.test(t)) || "",
  box: document.querySelector("[data-tq-task-page] .tq-aui-input")?.getAttribute("placeholder") || "", dots: !!document.querySelector("[data-tq-task-page] [data-tq-working]") }))),
  "| server working", srv.working, "| items", (srv.items || []).map((x) => `${x.kind}${x.state ? ":" + x.state : ""}`).slice(-4).join(" "));
console.log((await chat(page)).slice(-(Number(process.env.CHAT_TAIL) || 500)));
await browser.disconnect();
