// What the Sign in button is allowed to offer. Pure, so the rule is testable without React.
//
// `login` is the server's word: the recipe name for a CLI whose sign-in Taskuary knows how to
// start, or "". Same rule as `installable` - never draw a button over a road that does not exist.
export const canSignIn = (cli) => !!(cli && cli.installed && cli.login);
export const signInTitle = (cli) =>
  `Sign in to ${cli?.label || cli?.login || "this CLI"} here — it opens in a live pane, as a task on the Board`;
