// The sidebar's buttons (the canvas redesign, docs/superpowers/specs/2026-09-29-assistant-canvas-redesign-design.md):
// New first - a new task is the one thing you start rather than browse - then the parts of the app that are browsed.
// `go` is the tab each opens until the canvas browses them itself.
// ABOUT YOU beside Settings, where Docs was reached (the owner, 2026-11-06): your docs, playbooks and what was learned, on one page -
// the Hub stays its own, the deep detail of the projects you work on
export const SIDE_NAV = [
  { key: "new", label: "New", hint: "Start a task, a report or a routine" },
  { key: "reports", label: "Reports", go: "Reports", hint: "The reports you run, and a new one" },
  { key: "connections", label: "Connections", go: "Connections", hint: "What Taskuary reads and writes - mail, chat, code, finance" },
  { key: "hub", label: "Hub", go: "Hub", hint: "What the company knows, searched" },
  { key: "about", label: "About you", go: "About", hint: "How you sound, how you do your job, and what Taskuary has learned about you" },
  { key: "settings", label: "Settings", go: "Settings", hint: "How Taskuary works for you" },
];
