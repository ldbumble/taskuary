// The AI CLI agents card on Connections, said from the CLIs themselves (/api/cli/connections). It wore "Installed" and the live
// border whatever was connected, so with every CLI disconnected it still read as in use (the owner, 2026-10-15: "i disconnected
// the cli tools but still shows installed???"). Connected is what makes it on; installed alone is off, and says so. And connected
// is a saved connection to a CLI that IS here: one to a CLI nobody installed read "Connected: Claude Code" on a fresh install (2026-10-20)
export const cliCardOf = (clis) => {
  if (!clis) return {};
  const on = clis.filter((c) => c.configured && c.installed), here = clis.filter((c) => c.installed);
  if (on.length) return { state: "on", desc: `Connected: ${on.map((c) => c.label || c.name).join(", ")}` };
  return { state: "off", desc: here.length ? `${here.length} installed on this computer · none connected - open to connect one`
    : "None installed - open to install a coding CLI" };
};
