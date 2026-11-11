// evaluate an expression in the scratch instance's page (real-run.mjs): node browser/real-eval.mjs "<js expression>"
import { connect } from "./real-lib.mjs";
const { browser, page } = await connect();
console.log(JSON.stringify(await page.evaluate(process.argv[2]), null, 1));
await browser.disconnect();
