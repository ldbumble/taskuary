// A source card holds TEXT; the executors take lists and objects. One conversion, both
// directions, in one place - Save and Test each used to carry their own subset, which is how a
// filter that previewed correctly could still be saved as a string.
export const NL = String.fromCharCode(10);

// Product boundary: a report only reads; a workflow writes data or keeps state. The program used
// to classify every `type: agent` source as a workflow, even when the agent only fetched GitHub
// Trending and wrote a report. Agent is an executor, so only an explicit write grant changes shelf.
export const WORKFLOW_TYPES = new Set(["zoho_monthly_invoices"]);
export const isWorkflowConfig = (cfg) => WORKFLOW_TYPES.has(cfg?.type)
  || (cfg?.type === "agent" && cfg?.access === "write");

// longest first, so ">=" is never read as ">" with a stray "=" left on the value
export const OPS = ["<=", ">=", "!=", "=", "<", ">", "like", "in", "isnull", "isnotnull"];

/* Everything that belongs to ONE source card; the rest (title, prompt, schedule) is the report
   itself. Splitting here is what lets old single-source configs load unchanged. */
export const SOURCE_KEYS = ["type", "label", "connector_id", "query", "script", "cmd", "args", "tool", "tool_args", "tail", "sheet", "pick", "region",
  "db", "url", "headers", "path", "max_rows", "server", "database", "auth", "username", "driver",
  "service", "operation", "params", "bucket", "key", "prefix", "log_group", "pattern", "hours",
  "api_version", "path_expr", "account", "container", "blob", "workspace_id",
  "filter", "select", "group", "failed_only", "days",
  "object", "fields", "filters", "order",          // Intacct - missing here is why a composed report arrived with only its title
  "agent", "skill", "prompt", "cwd", "model",      // the AI-agent source
  "num", "domains", "since", "depth", "time_range", "topic", "answer", "main", "chars"];

// "WHENDUE <= 08/31/2026" -> ["WHENDUE", "<=", "08/31/2026"]. The operator is whatever sits
// between the field and the value.
export const asFilters = (text) => String(text).split(NL).map((l) => l.trim()).filter(Boolean).map((l) => {
  const sp = l.indexOf(" ");
  if (sp < 1) return null;                       // no space = no field to speak of
  const op = OPS.find((o) => l.slice(sp + 1).trim().toLowerCase().startsWith(o));
  if (!op) return null;
  const at = l.toLowerCase().indexOf(op, sp);
  const field = l.slice(0, at).trim(), val = l.slice(at + op.length).trim();
  if (!field) return null;
  // "in" takes a list; every other operator takes the rest of the line as one value
  return [field, op, op === "in" ? val.split(",").map((x) => x.trim()).filter(Boolean) : val];
}).filter(Boolean);

/* And back OUT as lines the box can show. A plain join printed a composed
   [["WHENDUE","<=","08/31/2026"]] as "WHENDUE,<=,08/31/2026", which asFilters then dropped on
   the floor - so an AI-written filter survived right up to the moment you touched the field. */
export const filterLines = (v) => (Array.isArray(v)
  ? v.map((r) => (Array.isArray(r)
    ? [r[0], r[1], Array.isArray(r[2]) ? r[2].join(", ") : (r[2] ?? "")].join(" ").trim()
    : String(r))).join(NL)
  : (v ?? ""));

// what one field of one card shows, whatever the config happens to hold there. A csv_list is
// ONE line, so joining it with newlines showed "RECORDNOVENDORIDVENDORNAME" - a single-line
// input swallows them - and the field the label calls comma separated has to arrive that way.
export const showValue = (v, kind) => (kind === "filter_lines" ? filterLines(v)
  : Array.isArray(v) ? v.join(kind === "csv_list" ? ", " : NL)
    : (typeof v === "object" && v ? JSON.stringify(v) : (v ?? "")));

export const toShape = (src) => {
  const c = { ...src };
  if (typeof c.args === "string") c.args = c.args.split(NL).map((x) => x.trim()).filter(Boolean);
  if (typeof c.fields === "string") c.fields = c.fields.split(/[,\n]/).map((x) => x.trim()).filter(Boolean);
  if (typeof c.filters === "string") c.filters = asFilters(c.filters);
  for (const k of ["headers", "params", "tool_args"]) {
    if (typeof c[k] === "string" && c[k].trim()) { try { c[k] = JSON.parse(c[k]); } catch { /* preview will complain */ } }
  }
  if (c.max_rows) c.max_rows = Number(c.max_rows);
  for (const k of Object.keys(c)) {
    if (c[k] === "" || c[k] == null || (Array.isArray(c[k]) && !c[k].length)) delete c[k];
  }
  return c;
};

export const toSources = (cfg) => {
  if (Array.isArray(cfg.sources) && cfg.sources.length) return cfg.sources;
  const one = {};
  for (const k of SOURCE_KEYS) if (cfg[k] !== undefined && cfg[k] !== "") one[k] = cfg[k];
  return [{ type: cfg.type || "mssql", ...one }];
};

// picking a field out of Intacct's own list appends it to whatever the box holds - which is a
// list once the composer has written it and a typed string once you have edited it by hand
export const addField = (v, id) => {
  const have = Array.isArray(v) ? v : String(v || "").split(/[,\n]/).map((x) => x.trim()).filter(Boolean);
  return have.includes(id) ? have : [...have, id];
};
