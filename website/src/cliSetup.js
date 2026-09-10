// What the Set it up button is allowed to offer. Pure, so the rule is testable without React.
//
// `setup` is the server's word: the recipe name for a CLI whose own first run Taskuary knows how
// to open, or "". Same rule as `installable` - never draw a button over a road that does not exist.
export const canSetup = (cli) => !!(cli && cli.installed && cli.setup);
export const setupTitle = (cli) =>
  `Set up ${cli?.label || cli?.setup || "this CLI"} here — it opens in a live pane and asks you for its settings and sign-in, as a task on the Board`;
