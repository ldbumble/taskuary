// The agent connector's line on a CLI card (taskuary/acpadapter.py). Claude Code and Codex agents start through an npm adapter; without
// it installed every start fetches it through npx, seconds more. The server says its state (`cli.connector`, npm's cached answer); this
// says it in words and names the one press that helps, or none. Pure, so the rule is testable without React.
export const connectorLine = (cli) => {
  const c = cli?.installed && cli.connector, s = c?.status;
  if (!s) return null;
  const { have, want } = c;
  return {
    missing: { text: "Faster agent start: install the connector", state: "not installed", press: "Install" },
    update: { text: "Faster agent start: update the connector", state: `${have} installed · ${want} available`, press: "Update" },
    other: { text: "Faster agent start: install the connector", state: `${have} installed · this Taskuary runs ${want}`, press: "Install" },
    installing: { text: "Installing the agent connector…", state: "", press: "" },
    installed: { text: "Agent connector", state: `${have} installed`, press: "" },
    no_npm: { text: "Agent connector", state: "needs npm (Node.js) · agents start without it", press: "" },
  }[s] || null;
};
