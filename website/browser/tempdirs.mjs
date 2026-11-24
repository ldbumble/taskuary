import { mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

/* A TEMP FOLDER IS REMOVED BY WHOEVER MADE IT, AND BY THE NEXT ONE WHEN IT CANNOT - taskuary/spawn.py's own_temp, for node (2026-11-24:
   harness homes, fake-CLI folders and dead-end homes piled up in %TEMP%: a run killed mid-way, or a Chrome profile Windows still held at
   close, left each one behind). The folder names its maker's pid; one whose maker no longer runs is swept when the next is made. */
export const MARK = ".taskuary-maker";
const mine = new Set();
const alive = (pid) => { try { process.kill(pid, 0); return true; } catch (e) { return e.code === "EPERM"; } };

export function dropTemp(dir) {
  try { rmSync(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); } catch {}
  mine.delete(dir);
}

export function sweepTemp(prefix, root = os.tmpdir(), unmarkedMs = 86400e3) {
  let entries = [], n = 0;
  try { entries = readdirSync(root, { withFileTypes: true }); } catch { return 0; }
  for (const e of entries) {
    if (!e.isDirectory() || !e.name.startsWith(prefix)) continue;
    const d = path.join(root, e.name);
    let pid = 0;
    try { pid = parseInt(readFileSync(path.join(d, MARK), "utf8"), 10) || 0; } catch {}
    try { if (pid ? alive(pid) : Date.now() - statSync(d).mtimeMs < unmarkedMs) continue; } catch { continue; }
    try { rmSync(d, { recursive: true, force: true }); n++; } catch {}
  }
  return n;
}

export function ownTemp(prefix, root = os.tmpdir()) {
  sweepTemp(prefix, root);
  const d = mkdtempSync(path.join(root, prefix));
  writeFileSync(path.join(d, MARK), `${process.pid} node`);
  if (!mine.size) process.once("exit", () => [...mine].forEach(dropTemp));
  mine.add(d);
  return d;
}
