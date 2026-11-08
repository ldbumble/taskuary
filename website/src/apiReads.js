// A VENDOR'S REST API, READ WITH A KEY (apireads.py): one table, taskuary/apireads.json, read by the server and by this page - a row is a
// card on Connections (in its catalogue group) and a `<type>_read` source under Reports. A new vendor is a row there, nothing here.
import reads from "../../taskuary/apireads.json" with { type: "json" };

export const READS = Object.freeze(reads.services);
export const READ_TYPES = Object.freeze(Object.keys(READS));
export const READ_LABELS = Object.freeze(Object.fromEntries(READ_TYPES.map((t) => [`${t}_read`, `${READS[t].title} — API read`])));
const borrowed = { google: "the Google Sheets card's Google sign-in", graph: "the Outlook card's Microsoft sign-in" };
// ...each row as the Connections page's card description (DATA_META's shape)
export const READ_META = Object.freeze(Object.fromEntries(Object.entries(READS).map(([t, r]) => [t, {
  title: r.title, types: [`${t}_read`],
  fields: [...(r.base ? [] : [[`address (${r.host_hint})`, "host"]]), ...(r.auth === "basic" ? [["user name", "user"]] : [])],
  secretLabel: borrowed[r.auth] ? null : `${r.key} (write-only)`, noSecret: !!borrowed[r.auth],
  desc: r.desc,
  howto: [borrowed[r.auth] ? `Nothing to paste: it reads with ${borrowed[r.auth]} - set that card up first.` : `Create one at ${r.key_page}. A read-only one is enough.`,
    ...(r.base ? [] : [`Give the address of your ${r.title}: ${r.host_hint}.`]),
    `Test makes one cheap read (GET ${r.probe}). Then a report or an agent asks any GET under the API by its path - nothing but reads is ever sent.`],
}])));
