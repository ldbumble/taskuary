// A look at the walk's open page without driving it: node real-peek.mjs <name> [top|end|<px>] - the chat scrolled there, a screenshot, its words.
import { connect, shot, chat, sleep } from "./real-lib.mjs";
const [name, where = "end"] = process.argv.slice(2);
const { browser, page } = await connect();
await page.evaluate((w) => { const vp = document.querySelector("[data-tq-task-page] .tq-aui-viewport"); if (vp) vp.scrollTop = w === "top" ? 0 : w === "end" ? vp.scrollHeight : Number(w); }, where);
await sleep(400);
console.log(await shot(page, name)); console.log((await chat(page)).slice(0, Number(process.env.CHAT_HEAD) || 1500));
await browser.disconnect();
