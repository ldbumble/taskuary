// A repo inherits issue handling from the connection's inbound role until its picker is set.
// PRs and automatic agent starts remain opt-in, independent of that role.
export function githubInboundValue(config, roles, kind) {
  if (config[kind]) return config[kind];
  if (kind !== "issues") return "off";
  if (roles.has("trigger")) return "tasks";
  return roles.has("feed") ? "feed" : "off";
}
