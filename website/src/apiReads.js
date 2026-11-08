// A VENDOR'S REST API, READ WITH A KEY (apireads.py): one table, taskuary/apireads.json, read by the server and by this page - a row is a
// card on Connections (in its catalogue group) and a `<type>_read` source under Reports. A new vendor is a row there, nothing here.
import reads from "../../taskuary/apireads.json" with { type: "json" };

export const READS = Object.freeze(reads.services);
export const READ_TYPES = Object.freeze(Object.keys(READS));
export const READ_LABELS = Object.freeze(Object.fromEntries(READ_TYPES.map((t) => [`${t}_read`, `${READS[t].title} — API read`])));
const borrowed = { google: "the Google Sheets card's Google sign-in", graph: "the Outlook card's Microsoft sign-in" };
// a row that names its own fields (NetSuite's account and consumer key, Plaid's environment) says them; the rest ask for the address and user
const fieldsOf = (r) => r.fields || [...(r.base || r.service_host ? [] : [[`address (${r.host_hint})`, "host"]]), ...(r.auth === "basic" ? [["user name", "user"]] : [])];
const verb = (r) => r.probe_body !== undefined || r.post_only ? "POST" : "GET";
// ...each row as the Connections page's card description (DATA_META's shape)
export const READ_META = Object.freeze(Object.fromEntries(Object.entries(READS).map(([t, r]) => [t, {
  title: r.title, types: [`${t}_read`],
  fields: fieldsOf(r),
  secretLabel: borrowed[r.auth] || r.keyless ? null : `${r.key} (write-only)`, noSecret: !!borrowed[r.auth] || !!r.keyless,
  desc: r.desc,
  howto: [borrowed[r.auth] ? `Nothing to paste: it reads with ${borrowed[r.auth]} - set that card up first.`
    : r.keyless ? `Nothing to paste: start it on this computer and sign in there - ${r.host_hint}.` : `Get it from ${r.key_page}. A read-only one is enough.`,
    ...(r.base || r.service_host || r.fields ? [] : [`Give the address of your ${r.title}: ${r.host_hint}.`]),
    `Test makes one cheap read (${verb(r)} ${r.probe}). Then a report or an agent asks any read under the API by its path`
      + (r.post ? ` - a POST only to ${r.post.join(", ")}, the vendor's reads.` : " - nothing but reads is ever sent.")],
}])));
