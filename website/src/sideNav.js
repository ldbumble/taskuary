// The sidebar's buttons (the canvas redesign, docs/superpowers/specs/2026-09-29-assistant-canvas-redesign-design.md):
// New first - a new task is the one thing you start rather than browse - then the parts of the app that are browsed.
// `go` is the tab each opens until the canvas browses them itself.
export const SIDE_NAV = [
  { key: "new", label: "New", hint: "Start a task, a report or a workflow" },
  { key: "reports", label: "Reports", go: "Reports", hint: "The reports you run, and a new one" },
  { key: "connections", label: "Connections", go: "Connections", hint: "What Taskuary reads and writes - mail, chat, code, finance" },
  { key: "hub", label: "Hub", go: "Hub", hint: "What the company knows, searched" },
  { key: "settings", label: "Settings", go: "Settings", hint: "How Taskuary works for you" },
];
