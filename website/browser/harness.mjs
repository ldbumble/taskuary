import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import puppeteer from "puppeteer-core";

const here = path.dirname(fileURLToPath(import.meta.url));
const website = path.resolve(here, "..");
const repository = path.resolve(website, "..");
const forbiddenPorts = new Set([7787, 7790]);

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

// `taken`: ports this harness already holds - the OS can hand the same free port back to two asks in a row, and the start
// refused ("fixture ports must be unique") about once in many CI runs (2026-10-05)
async function freePort(taken = new Set()) {
  for (;;) {
    const port = await new Promise((resolve, reject) => {
      const socket = net.createServer();
      socket.unref();
      socket.once("error", reject);
      socket.listen(0, "127.0.0.1", () => {
        const found = socket.address().port;
        socket.close(() => resolve(found));
      });
    });
    if (!forbiddenPorts.has(port) && !taken.has(port)) return port;
  }
}

function executable() {
  const named = [process.env.TASKUARY_BROWSER_EXECUTABLE, process.env.PUPPETEER_EXECUTABLE_PATH]
    .filter(Boolean);
  const candidates = process.platform === "win32"
    ? [
        "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
        "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
      ]
    : process.platform === "darwin"
      ? [
          "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
          "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
      : ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/microsoft-edge"];
  const found = [...named, ...candidates].find((candidate) => existsSync(candidate));
  if (!found) {
    throw new Error("No installed Chrome or Edge found. Set TASKUARY_BROWSER_EXECUTABLE to its executable path.");
  }
  return found;
}

function loggedProcess(command, args, options) {
  const child = spawn(command, args, { ...options, shell: false, windowsHide: true });
  let output = "";
  let spawnError = null;
  const save = (chunk) => { output = (output + chunk.toString()).slice(-12000); };
  child.stdout?.on("data", save);
  child.stderr?.on("data", save);
  child.on("error", (error) => { spawnError = error; save(`${error.message}\n`); });
  child.output = () => output;
  child.spawnError = () => spawnError;
  return child;
}

async function stopProcess(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  const closed = new Promise((resolve) => child.once("exit", resolve));
  child.kill();
  await Promise.race([closed, delay(3000)]);
  if (child.exitCode === null && child.signalCode === null) {
    child.kill("SIGKILL");
    await Promise.race([closed, delay(3000)]);
  }
}

async function waitFor(label, probe, child, timeout = 25000) {
  const end = Date.now() + timeout;
  let last;
  while (Date.now() < end) {
    if (child?.spawnError?.()) throw new Error(`${label} could not start: ${child.spawnError().message}`);
    if (child && (child.exitCode !== null || child.signalCode !== null)) {
      throw new Error(`${label} exited before it became ready\n${child.output()}`);
    }
    try {
      const value = await probe();
      if (value) return value;
    } catch (error) {
      last = error;
    }
    await delay(100);
  }
  throw new Error(`${label} did not become ready${last ? `: ${last.message}` : ""}\n${child?.output?.() || ""}`);
}

async function waitHttp(url, child, headers = {}) {
  return waitFor(url, async () => {
    const response = await fetch(url, { headers });
    return response.ok ? response : null;
  }, child);
}

export async function startHarness() {
  const backendPort = await freePort();
  const frontendPort = await freePort(new Set([backendPort]));
  if (backendPort === frontendPort || forbiddenPorts.has(backendPort) || forbiddenPorts.has(frontendPort)) {
    throw new Error("fixture ports must be unique and must never use live Taskuary/bridge ports");
  }

  const home = await mkdtemp(path.join(os.tmpdir(), "taskuary-phase0-browser-"));
  const browserProfile = path.join(home, "browser-profile");
  const appData = path.join(home, "appdata");
  const localAppData = path.join(home, "localappdata");
  const codexHome = path.join(home, "codex");
  const claudeHome = path.join(home, "claude");
  const agentBrowserHome = path.join(home, "agent-browser");
  const userHome = path.join(home, "user");
  const xdgConfig = path.join(home, "xdg-config");
  const xdgCache = path.join(home, "xdg-cache");
  const xdgData = path.join(home, "xdg-data");
  await Promise.all([browserProfile, appData, localAppData, codexHome, claudeHome, agentBrowserHome, userHome, xdgConfig, xdgCache, xdgData]
    .map((folder) => mkdir(folder)));

  const fixtureApi = `http://127.0.0.1:${backendPort}`;
  const ui = `http://127.0.0.1:${frontendPort}`;
  const python = process.env.TASKUARY_TEST_PYTHON || (process.platform === "win32" ? "python" : "python3");
  const isolated = {
    ...process.env,
    TASKUARY_HOME: home,
    TASKUARY_DEMO: "1",
    TASKUARY_PORT: String(backendPort),
    TASKUARY_API: fixtureApi,
    TASKUARY_TOKEN: "phase0-browser-owner-token",
    APPDATA: appData,
    LOCALAPPDATA: localAppData,
    HOME: userHome,
    USERPROFILE: userHome,
    XDG_CONFIG_HOME: xdgConfig,
    XDG_CACHE_HOME: xdgCache,
    XDG_DATA_HOME: xdgData,
    CODEX_HOME: codexHome,
    CLAUDE_CONFIG_DIR: claudeHome,
    AGENT_BROWSER_HOME: agentBrowserHome,
    OPENAI_API_KEY: "",
    ANTHROPIC_API_KEY: "",
    NO_PROXY: "127.0.0.1,localhost",
    PYTHONUNBUFFERED: "1",
  };

  let backend;
  let frontend;
  let browser;
  try {
    backend = loggedProcess(python, [path.join(here, "fixture_server.py")], {
      cwd: repository,
      env: isolated,
      stdio: ["ignore", "pipe", "pipe"],
    });
    const token = isolated.TASKUARY_TOKEN;
    await waitHttp(`${fixtureApi}/api/health`, backend, { "X-Taskuary-Token": token });
    if (!backend.output().includes("PHASE0_FIXTURE_NETWORK_GUARD=blocked")) {
      throw new Error(`fixture backend did not prove its outbound socket guard\n${backend.output()}`);
    }

    const vite = path.join(website, "node_modules", "vite", "bin", "vite.js");
    frontend = loggedProcess(process.execPath, [vite, "--host", "127.0.0.1", "--port", String(frontendPort), "--strictPort"], {
      cwd: website,
      env: isolated,
      stdio: ["ignore", "pipe", "pipe"],
    });
    await waitHttp(ui, frontend);

    browser = await puppeteer.launch({
      executablePath: executable(),
      headless: true,
      userDataDir: browserProfile,
      // Chrome on Windows will not start with APPDATA/USERPROFILE pointed at a scratch dir (it exits, and puppeteer
      // reports "The browser is already running"). TASKUARY_BROWSER_PLAIN_ENV=1 hands the BROWSER alone the real
      // environment for a local run; the app server stays isolated either way, and CI never sets it.
      env: process.env.TASKUARY_BROWSER_PLAIN_ENV ? process.env : isolated,
      args: [
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-sync",
        "--metrics-recording-only",
        "--no-first-run",
        "--no-default-browser-check",
      ],
    });

    const pages = new Set();
    const newPage = async () => {
      const page = await browser.newPage();
      pages.add(page);
      await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
      await page.evaluateOnNewDocument((fixtureTokenValue) => {
        localStorage.setItem("taskuary_token", fixtureTokenValue);
      }, token);
      await page.evaluateOnNewDocument((allowedHttpOrigin) => {
        const NativeWebSocket = window.WebSocket;
        const allowed = allowedHttpOrigin.replace(/^http/, "ws");
        class FixtureWebSocket extends NativeWebSocket {
          constructor(url, protocols) {
            const target = new URL(url, window.location.href);
            if (target.origin !== allowed) throw new Error(`browser fixture blocked websocket ${target.origin}`);
            if (protocols === undefined) super(target.href);
            else super(target.href, protocols);
          }
        }
        window.WebSocket = FixtureWebSocket;
      }, ui);

      const escaped = [];
      const blockedAssets = [];
      await page.setRequestInterception(true);
      const fixtureRequestGuard = (request) => {
        const url = request.url();
        const protocol = new URL(url).protocol;
        if (["data:", "blob:", "about:"].includes(protocol) || new URL(url).origin === ui) {
          request.continue();
        } else if (["fonts.googleapis.com", "fonts.gstatic.com"].includes(new URL(url).hostname)) {
          blockedAssets.push(url);
          request.abort("blockedbyclient");
        } else {
          escaped.push(url);
          request.abort("blockedbyclient");
        }
      };
      page.on("request", fixtureRequestGuard);
      page.fixtureRequestGuard = fixtureRequestGuard;
      page.fixtureEscapes = escaped;
      page.fixtureBlockedAssets = blockedAssets;
      page.on("close", () => pages.delete(page));
      return page;
    };

    const close = async () => {
      await browser?.close().catch(() => {});
      await stopProcess(frontend);
      await stopProcess(backend);
      const prefix = path.join(os.tmpdir(), "taskuary-phase0-browser-");
      if (path.resolve(home).startsWith(path.resolve(prefix))) await rm(home, { recursive: true, force: true }).catch(() => {});
    };

    return { backendPort, frontendPort, fixtureApi, ui, home, token, backend, frontend, newPage, close };
  } catch (error) {
    await browser?.close().catch(() => {});
    await stopProcess(frontend);
    await stopProcess(backend);
    await rm(home, { recursive: true, force: true }).catch(() => {});
    throw error;
  }
}

export async function bodyText(page) {
  return page.evaluate(() => document.body.innerText);
}

export async function clickNav(page, label) {
  // THE TABS ARE GONE (the canvas redesign, 0.3.7.0): Reports, Connections, Hub and Settings are the sidebar's buttons and
  // open as browse cards in the Assistant's canvas; the Board is the top bar's one switch, and so is the way back.
  const sidebar = { Reports: "reports", Connections: "connections", Hub: "hub", Settings: "settings" }[label];
  if (sidebar || label === "Board" || label === "Assistant" || label === "Timeline") {
    const done = await page.evaluate((key, want) => {
      const visible = (el) => el && el.getBoundingClientRect().width > 0;
      const sw = document.querySelector("[data-tq-view-switch]");
      const onBoard = sw?.getAttribute("data-tq-view-switch") === "assistant";
      if (want === "Board") { if (!onBoard) sw?.click(); return !!sw; }
      if (onBoard) sw.click();                               // back to the Assistant first
      if (!key) return true;
      const nav = document.querySelector(`[data-tq-nav="${key}"]`);
      if (!visible(nav)) document.querySelector('[aria-label="The Timeline"]')?.click();   // a phone keeps it in the drawer
      const again = document.querySelector(`[data-tq-nav="${key}"]`);
      again?.click();
      return !!again;
    }, sidebar || null, label);
    if (!done) throw new Error(`navigation item not found: ${label}`);
    return;
  }
  const clicked = await page.evaluate((wanted) => {
    // The count badge rides INSIDE the pill (a MUI Badge hung outside it was clipped by the
    // strip's own scroller), so the tab that has one reads "Tasks3" here, not "Tasks". Strip a
    // trailing count before comparing - otherwise a tab becomes unclickable the day it grows one.
    const name = (node) => node.textContent.trim().replace(/\s*\d+\+?$/, "");
    const node = [...document.querySelectorAll("#tqTopNav div")]
      .find((candidate) => name(candidate) === wanted
        && candidate.getBoundingClientRect().width > 0
        && candidate.getBoundingClientRect().height > 0);
    node?.click();
    return Boolean(node);
  }, label);
  if (!clicked) throw new Error(`navigation item not found: ${label}`);
}

// A settings RAIL entry - a page, a section, or one of Docs' documents. These are divs, not
// buttons, so the button-based helpers in the tests cannot reach them.
export async function clickRail(page, label) {
  // THE CANVAS (0.3.7.0) has no Settings rail: the same entries are the cards of a Settings browse card's list - a
  // document open over its list goes Back first, then the card with that title is opened
  if (!(await page.$("#tqSettingsRail"))) {
    // a rail GROUP heading is the list's grouping in the canvas: "clicking" it is being on the list
    if (["Operator documents", "Profiles", "Playbooks"].includes(label)) {
      await page.evaluate(() => document.querySelector("[data-tq-browse-back]")?.click());
      await page.waitForSelector("[data-tq-browse-card]");
      return;
    }
    const card = (wanted) => [...document.querySelectorAll("[data-tq-browse-card]")].find((c) =>
      (c.querySelector("p")?.textContent || "").trim() === wanted && c.getBoundingClientRect().width > 0);
    await page.waitForFunction((src, wanted) => {
      if (new Function("return " + src)()(wanted)) return true;
      document.querySelector("[data-tq-browse-back]")?.click();
      return false;
    }, { polling: 300, timeout: 20000 }, card.toString(), label);
    await page.evaluate((src, wanted) => new Function("return " + src)()(wanted).click(), card.toString(), label);
    return;
  }
  const find = (wanted) => {
    const rail = document.getElementById("tqSettingsRail")?.parentElement;
    return [...(rail?.querySelectorAll("div") || [])].find((d) => d.textContent.trim() === wanted
      && d.childElementCount === 0 && d.getBoundingClientRect().width > 0);
  };
  await page.waitForFunction(`(${find})(${JSON.stringify(label)}) != null`);
  await page.evaluate((wanted, src) => { new Function("return " + src)()(wanted).click(); },
    label, find.toString());
}

export async function waitForBody(page, text, timeout = 10000) {
  try {
    await page.waitForFunction((wanted) => document.body.innerText.includes(wanted), { timeout }, text);
  } catch (error) {
    const rendered = (await bodyText(page)).slice(0, 1200);
    throw new Error(`did not render ${JSON.stringify(text)} at ${page.url()}\n${rendered}`, { cause: error });
  }
}
