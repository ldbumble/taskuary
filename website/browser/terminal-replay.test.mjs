import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { bodyText, startHarness } from "./harness.mjs";

async function waitUntil(predicate, timeout = 5000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error("timed out waiting for terminal websocket frames");
}

test("P0-BROWSER terminal replay becomes visible and accepts fixture input", { timeout: 120000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const session = await page.createCDPSession();
  await session.send("Network.enable");
  const sentFrames = [];
  const receivedFrames = [];
  session.on("Network.webSocketFrameSent", ({ response }) => sentFrames.push(response.payloadData));
  session.on("Network.webSocketFrameReceived", ({ response }) => receivedFrames.push(response.payloadData));

  // the demo's agent session, found by its title: the demo world is written out item by item and its numbering
  // moves with it (2026-09-23 put this task at #6 and left #4 an invoice reply with no terminal at all)
  const tasks = await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json();
  // (2026-10-17: the GL reconciliation became a general agent's conversation - the census issue is the coding replay)
  const gl = (tasks.data || []).find((t) => t.Kind === "coding" && /census sync/.test(t.Title) && !["done", "dropped"].includes(t.Status));
  assert.ok(gl, "the demo world has no census sync session to replay");
  const replayStarted = performance.now();
  await page.goto(`${harness.ui}/#task=${gl.TaskId}`, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector(".xterm-helper-textarea", { timeout: 15000 });
  await page.waitForFunction(() => !document.body.innerText.includes("restoring the session"), { timeout: 10000 });
  const rendered = await bodyText(page);
  assert.equal(rendered.includes("closed"), false, "fixture terminal websocket closed during replay");
  assert.ok(receivedFrames.some((frame) => {
    try { return JSON.parse(frame).type === "ready"; } catch { return false; }
  }), "terminal replay did not reach its ready barrier");
  assert.ok(receivedFrames.some((frame) => {
    try { const message = JSON.parse(frame); return message.type === "out" && message.replay === true; } catch { return false; }
  }), "terminal websocket did not identify its initial output as replay");
  assert.match(await page.$eval(".xterm-rows", (node) => node.textContent), /census sync|census_sync/,
    "replayed terminal content was not visibly rendered");
  const replayVisibleMs = Math.round(performance.now() - replayStarted);
  assert.ok(replayVisibleMs <= 10000, `terminal replay took ${replayVisibleMs}ms to become visible`);

  const inputStarted = performance.now();
  await page.click(".xterm-helper-textarea");
  await page.keyboard.type("phase-zero-terminal-input");
  const typed = () => sentFrames.flatMap((frame) => {
    try {
      const message = JSON.parse(frame);
      return message.type === "in" ? [message.data] : [];
    } catch {
      return [];
    }
  }).join("");
  await waitUntil(() => typed().includes("phase-zero-terminal-input"));
  const inputEmissionMs = Math.round(performance.now() - inputStarted);
  assert.ok(typed().includes("phase-zero-terminal-input"), "typed terminal input was not emitted over the fixture websocket");
  assert.ok(inputEmissionMs <= 1500, `terminal input emission took ${inputEmissionMs}ms`);

  const readyBeforeReload = receivedFrames.filter((frame) => {
    try { return JSON.parse(frame).type === "ready"; } catch { return false; }
  }).length;
  const reconnectStarted = performance.now();
  await page.reload({ waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector(".xterm-helper-textarea", { timeout: 15000 });
  await page.waitForFunction(() => !document.body.innerText.includes("restoring the session"), { timeout: 10000 });
  await waitUntil(() => receivedFrames.filter((frame) => {
    try { return JSON.parse(frame).type === "ready"; } catch { return false; }
  }).length > readyBeforeReload);
  const readyAfterReload = receivedFrames.filter((frame) => {
    try { return JSON.parse(frame).type === "ready"; } catch { return false; }
  }).length;
  const reconnectMs = Math.round(performance.now() - reconnectStarted);
  assert.ok(readyAfterReload > readyBeforeReload, "terminal reconnect did not reach a new ready barrier");
  assert.ok(reconnectMs <= 10000, `terminal reconnect took ${reconnectMs}ms`);
  assert.match(await page.$eval(".xterm-rows", (node) => node.textContent), /census sync|census_sync/,
    "terminal reconnect did not visibly restore replay content");
  assert.deepEqual(page.fixtureEscapes, [], `browser attempted non-fixture requests: ${page.fixtureEscapes.join(", ")}`);
  t.diagnostic(JSON.stringify({ fixture: "actual Taskuary --demo Replay; no PTY/worker; fixture intentionally ignores input",
    sentFrames: sentFrames.length, receivedFrames: receivedFrames.length, reconnectReady: readyAfterReload,
    timings: { replayVisibleMs, inputEmissionMs, reconnectMs } }));
});

// The owner's pane, 2026-10-21: a Claude session long into one hook, reopened, showed its spinner over a bare cursor and a
// stray number - the input box and footer gone. A CLI animating one line rewrites only that line, so the bytes that drew the
// box fell off the front of the server's bounded scrollback. tests/test_pane_keeps_the_screen.py holds the seed to pyte;
// this holds it to xterm itself, the emulator the pane IS: for each CLI kind's fake session (three scrollbacks of spinner
// after one paint), xterm seeded with the reopened pane's replay and xterm that saw the whole session show the same rows
// and cursor - and still do after the CLI's next paint, and after a full-screen TUI leaves the alternate screen.
test("a reopened pane shows the screen the CLI left, per CLI kind, in a real xterm", { timeout: 180000 }, async (t) => {
  const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
  const python = process.env.TASKUARY_TEST_PYTHON || (process.platform === "win32" ? "python" : "python3");
  const make = [
    "import sys, json; sys.path[:0] = ['.', 'tests']",
    "import test_pane_keeps_the_screen as T",
    "from taskuary import terminal",
    "out = {}",
    "for k in list(T.KINDS) + ['alt']:",
    "    t, body = T._run(k)",
    "    out[k] = {'body': body, 'seed': terminal.replay_text(t), 'next': (T.KINDS.get(k) or T.alt)()[1](10 ** 6) + 'hello'}",
    "json.dump({'rows': T.ROWS, 'cols': T.COLS, 'kinds': out}, sys.stdout)",
  ].join("\n");
  const fixture = JSON.parse(execFileSync(python, ["-c", make], { cwd: repository, encoding: "utf8", maxBuffer: 64 << 20 }));
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.goto(`${harness.ui}/`, { waitUntil: "domcontentloaded", timeout: 20000 });
  const got = await page.evaluate(async ({ rows, cols, kinds }) => {
    const { Terminal } = await import("/@id/@xterm/xterm");
    const { Unicode11Addon } = await import("/@id/@xterm/addon-unicode11");
    const screen = async (...parts) => {
      const term = new Terminal({ rows, cols, scrollback: 1000, allowProposedApi: true });
      term.loadAddon(new Unicode11Addon()); term.unicode.activeVersion = "11";       // as the pane measures (TerminalView)
      for (const p of parts) await new Promise((resolve) => term.write(p, resolve));
      const b = term.buffer.active, shown = [];
      for (let y = 0; y < rows; y++) shown.push(b.getLine(b.baseY + y)?.translateToString(true) ?? "");
      const out = { type: b.type, shown, cursor: [b.cursorY, b.cursorX] };
      term.dispose();
      return out;
    };
    const res = {};
    for (const [kind, { body, seed, next }] of Object.entries(kinds)) {
      res[kind] = { pane: await screen(seed), truth: await screen(body), paneNext: await screen(seed, next), truthNext: await screen(body, next),
                    paneLeft: await screen(seed, "\x1b[?1049l"), truthLeft: await screen(body, "\x1b[?1049l") };
    }
    return res;
  }, fixture);
  for (const [kind, r] of Object.entries(got)) {
    assert.deepEqual(r.pane, r.truth, `${kind}: the reopened pane is not the screen the CLI left`);
    assert.match(r.pane.shown.at(-1), /bypass permissions on/, `${kind}: the footer is gone`);
    assert.match(r.pane.shown.at(-2), /╰/, `${kind}: the input box is gone`);
    assert.deepEqual(r.paneNext, r.truthNext, `${kind}: the CLI's next paint landed elsewhere on the reopened pane`);
    assert.deepEqual(r.paneLeft.shown, r.truthLeft.shown, `${kind}: leaving the alternate screen showed something else`);
  }
  assert.equal(got.alt.pane.type, "alternate");
  assert.deepEqual(page.fixtureEscapes, [], `browser attempted non-fixture requests: ${page.fixtureEscapes.join(", ")}`);
});
