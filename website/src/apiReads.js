// A VENDOR'S REST API, READ WITH A KEY (apireads.py): one table, taskuary/apireads.json, read by the server and by this page - a row is a
// card on Connections (in its catalogue group) and a `<type>_read` source under Reports. A new vendor is a row there, nothing here.
import reads from "../../taskuary/apireads.json" with { type: "json" };

export const READS = Object.freeze(reads.services);
export const READ_TYPES = Object.freeze(Object.keys(READS));
export const READ_LABELS = Object.freeze(Object.fromEntries(READ_TYPES.map((t) => [`${t}_read`, `${READS[t].title} — API read`])));
const borrowed = { google: "the Google Sheets card's Google sign-in", graph: "the Outlook card's Microsoft sign-in",
  powerbi: "the Outlook card's Microsoft sign-in" };
// A CARD THAT SIGNS IN BY OAUTH (oauth.py, auth "oauth"): the owner's own app at the vendor - its keys save themselves, Sign in brings
// the tokens back to this computer, and nothing is ever pasted as a token. `push`: LINE and SendGrid post to an address the owner gives.
const hostLabel = { login_host: ["sign-in host - login.salesforce.com, test.salesforce.com for a sandbox, or your My Domain", "login.salesforce.com"],
  auth_host: ["sign-in host - account.docusign.com, or account-d.docusign.com for a developer account", "account.docusign.com"] };
const signIn = (t, r) => ({
  fields: [["Client ID", "client_id", "", `From ${r.oauth.console}.`],
    ["Client Secret", "client_secret", "", "The same app's secret. Paste both - each saves itself - then Sign in above."],
    ...Object.keys(r.oauth.defaults || {}).map((k) => [hostLabel[k]?.[0] || k, k, hostLabel[k]?.[1] || ""]),
    ["redirect address (optional) - an https address of your own that reaches this computer", "redirect_base", "",
      r.oauth.https ? `${r.title} takes only an https redirect: give your own tunnel's address here (https://your.host), and the redirect URL above follows it.`
        : "Leave blank: the redirect comes back to this computer."]],
  noSecret: true,
  connect: { label: `Sign in with ${r.title}`, status: (cid) => `/api/connectors/${cid}/oauth/status`, start: (cid) => `/api/connectors/${cid}/oauth/start`, post: true,
    text: `Opens ${r.title}'s consent screen in a new tab. The sign-in returns directly to Taskuary on this computer.` },
  howto: [`Register an app of your own at ${r.oauth.console}. Taskuary has no shared app: the sign-in is between you and ${r.title}.`,
    `Add the redirect URL shown on the card to the app, exactly.${r.oauth.https ? ` ${r.title} wants an https one: point a tunnel of your own at this computer and give its address under redirect address.` : ""}`,
    "Paste the app's Client ID and Client Secret - each saves itself - then press Sign in. The tokens come back here, sealed, and renew themselves.",
    `Test says which account signed in${r.desc.includes("work rail") ? " and starts the sync" : ""}. Agents and reports read with the same sign-in (GET ${r.probe} and any path under the API) - nothing but reads is sent.`],
  agent: [`The ${r.title} app is the owner's to register and the Sign in is the owner's to press. Never ask for a token, and never print one.`,
    `Reads are yours: run_tool with type ${t}_read and a "path" under the API (GET only).`],
});
// a row names its own fields (NetSuite's account and consumer key, Plaid's environment, Looker's client id); one with no base asks its
// address too unless its fields already do, and a basic one with neither a user nor fields asks the user name
const ownHost = (r) => !r.base && !r.service_host && !(r.fields || []).some((f) => f[1] === "host");
const fieldsOf = (r) => [...(ownHost(r) ? [[`address (${r.host_hint})`, "host", r.default_host || ""]] : []),
  ...(r.fields || (r.auth === "basic" && !r.user ? [["user name", "user"]] : []))];
const verb = (r) => r.probe_body !== undefined || r.post_only ? "POST" : "GET";
const reads1 = (r) => r.probe ? `Test makes one cheap read (${verb(r)} ${r.probe.replace(/\{(\w+)\}/g, "<$1>")}).`
  : `Test signs in; a read names what it looks up (${r.example}).`;
const bare = (r) => (borrowed[r.auth] && !r.key) || !!r.keyless;
const keyed = (t, r) => ({
  fields: fieldsOf(r),
  secretLabel: bare(r) ? null : `${r.key} (write-only)`, noSecret: bare(r),
  push: t === "line" || t === "sendgrid",
  howto: [...(borrowed[r.auth] ? [`${r.key ? "It" : "Nothing to paste: it"} reads with ${borrowed[r.auth]} - set that card up first.`] : []),
    ...(r.keyless ? [r.local_tls ? `Nothing to paste: start it on this computer and sign in there - ${r.host_hint}.` : `Nothing to paste: give the address of your ${r.title}: ${r.host_hint}.`]
      : r.key ? [`Get the ${r.key} from ${r.key_page}. A read-only one is enough.`] : []),
    ...(r.scope_hint ? [`That sign-in needs ${r.scope_hint}.`] : []),
    ...(ownHost(r) && !r.keyless ? [`Give the address of your ${r.title}: ${r.host_hint}.`] : []),
    ...(t === "line" || t === "sendgrid" ? [`${r.title} pushes to Taskuary, so it needs a public https address that reaches this computer - your own tunnel (cloudflared, ngrok) pointed at Taskuary's port. Point the vendor at that address followed by the path the card shows; only that path answers there, never the app.`] : []),
    `${reads1(r)} Then a report or an agent asks any read under the API by its path`
      + (r.post ? ` - a POST only to ${r.post.join(", ")}, the vendor's reads.` : " - nothing but reads is ever sent.")],
});
// ...each row as the Connections page's card description (DATA_META's shape)
export const READ_META = Object.freeze(Object.fromEntries(Object.entries(READS).map(([t, r]) => [t, {
  title: r.title, types: [`${t}_read`], desc: r.desc, ...(r.auth === "oauth" ? signIn(t, r) : keyed(t, r)),
}])));
