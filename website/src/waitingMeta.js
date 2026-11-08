// WORK THAT WAITS ON YOU ELSEWHERE (taskuary/waiting.py, on the inboxes road): each source's card - what to paste, what Test does, what
// comes in. The Connections page spreads these into its META and draws each in its catalogue group (waitingIn). Vendor menu paths are
// written in words, so no sentence here types another app's path as if it were ours.
const reads = (v) => `Nothing is changed in ${v}; Taskuary only reads.`;
const FORMS = ["form ids to watch (comma-separated - Test lists yours)", "forms"];
const form = (v, where, also = []) => ({
  group: "Everything else", channel: "", srcLabel: "Account", srcPh: "added by Test", fields: [FORMS, ...also],
  desc: `New ${v} responses on the forms you pick come in with every answer, and are sorted like everything else that comes in.`,
  howto: [where, "Paste it (write-only) and press Test: it signs in and lists your forms with their ids. Put the ids to watch on the card.",
    `Every sync brings in the responses submitted since the last one, question by question. A respondent is a stranger's words: nothing starts on one by itself until you trust the source.`,
    reads(v)],
});

const M = {
  typeform: { ...form("Typeform", "Typeform: your account, then Personal tokens - generate one with forms:read and responses:read."), secretLabel: "personal access token" },
  jotform: { ...form("Jotform", "Jotform: your avatar, then API - Create new key (read access).", [["EU data centre (yes if your account is on eu.jotform.com)", "eu"]]), secretLabel: "API key" },
  surveymonkey: { ...form("SurveyMonkey", "developer.surveymonkey.com, then My Apps - create a private app with the View Surveys and View Responses scopes; its settings show the access token."), secretLabel: "access token" },
  google_forms: { ...form("Google Forms", "Nothing to paste: it reads with the Google Sheets card's sign-in. Mint that card's refresh token with forms.responses.readonly and forms.body.readonly as well."),
    fields: [["form ids to watch (from docs.google.com/forms/d/<id>/edit, comma-separated)", "forms"]], secretLabel: null },
  helpscout: { group: "Project management", channel: "", srcLabel: "Help desk", srcPh: "added by Test",
    fields: [["app id (your profile, then My Apps)", "app_id"]], secretLabel: "app secret",
    desc: "Active Help Scout conversations ASSIGNED TO YOU come in and are sorted like everything else that comes in.",
    howto: ["Help Scout: your profile, then My Apps - Create My App (any redirect address). It shows an app id and an app secret.",
      "Enter the app id and paste the secret (write-only). Test signs in as you.",
      "Every sync brings in active conversations assigned to you that changed, with the customer and a preview, linking back to Help Scout.",
      "A customer's conversation is a stranger's words: nothing starts on it by itself until you trust them.", reads("Help Scout")] },
  front: { group: "Project management", channel: "", srcLabel: "Workspace", srcPh: "added by Test",
    fields: [["your Front email (the teammate whose assigned conversations come in)", "email"]], secretLabel: "API token",
    desc: "Open Front conversations ASSIGNED TO YOU come in with the latest message, and are sorted like everything else that comes in.",
    howto: ["Front: your company settings, then Developers - API tokens - Create API token with read access to shared resources.",
      "Enter the email you sign in to Front with and paste the token (write-only). Test finds you as a teammate.",
      "Every sync brings in conversations assigned to you, with the newest message, linking back to Front.",
      "A message from a contact is a stranger's words; one from a teammate is a colleague's.", reads("Front")] },
  aircall: { group: "Everything else", channel: "", srcLabel: "Lines", srcPh: "added by Test",
    fields: [["API ID", "api_id"], ["your Aircall email", "email"]], secretLabel: "API token",
    desc: "Missed calls and voicemails on YOUR Aircall lines come in (with Aircall's transcript where you have it), sorted like everything else.",
    howto: ["Aircall dashboard: Integrations & API, then API Keys - Generate an API key. It shows an API ID and an API token.",
      "Enter the API ID and your email, paste the token (write-only). Test finds you and your lines.",
      "Every sync brings in inbound calls on your lines that were missed or left a voicemail. A caller is a stranger's words until you trust the source.", reads("Aircall")] },
  ringcentral: { group: "Everything else", channel: "", srcLabel: "Extension", srcPh: "added by Test",
    fields: [["app client id (developers.ringcentral.com, JWT auth flow)", "client_id"], ["app client secret", "client_secret"]], secretLabel: "JWT credential",
    desc: "Voicemails (with RingCentral's transcript), texts and missed calls to YOUR extension come in and are sorted like everything else.",
    howto: ["developers.ringcentral.com: create a REST API app with the JWT auth flow and the Read Messages and Read Call Log permissions.",
      "Your profile there, then Credentials - Create JWT for your own user. Enter the app's client id and secret, paste the JWT (write-only).",
      "Every sync brings in new inbound voicemails, texts and missed calls. A caller is a stranger's words until you trust the source.", reads("RingCentral")] },
  gorgias: { group: "Project management", channel: "", srcLabel: "Helpdesk", srcPh: "added by Test",
    fields: [["domain (the \"yourstore\" in yourstore.gorgias.com)", "domain"], ["your Gorgias email (the key's user)", "email"]], secretLabel: "API key",
    desc: "Open Gorgias tickets ASSIGNED TO YOU come in and are sorted like everything else that comes in.",
    howto: ["Gorgias: your settings, then REST API - it shows the base address, your username (email) and lets you create an API key.",
      "Enter the domain and your email, paste the key (write-only). Test reads the account.",
      "Every sync brings in open tickets assigned to you that changed. A shopper is a stranger's words until you trust them.", reads("Gorgias")] },
  dialpad: { group: "Everything else", channel: "", srcLabel: "Company", srcPh: "added by Test",
    fields: [["your Dialpad email", "email"]], secretLabel: "API key",
    desc: "Missed calls and voicemails to YOU on Dialpad come in with Dialpad's transcript, sorted like everything else that comes in.",
    howto: ["Dialpad admin: My Company, then Authentication - API keys - Add a key.",
      "Enter your email and paste the key (write-only). Test finds you.",
      "Every sync brings in inbound calls to you that were missed or left a voicemail. A caller is a stranger's words until you trust the source.", reads("Dialpad")] },
  tally: { ...form("Tally", "Tally: your settings, then API keys - Create API key."), secretLabel: "API key" },
  lever: { group: "Corporate systems", channel: "", srcLabel: "Account", srcPh: "added by Test",
    fields: [["your Lever email", "email"]], secretLabel: "API key",
    desc: "Lever candidates YOU OWN come in when they change stage, and are sorted like everything else that comes in.",
    howto: ["Lever: its settings, then Integrations and API - API credentials - Generate new key, with read access to Opportunities and Users.",
      "Enter your email and paste the key (write-only). Test finds you.",
      "Every sync brings in candidates you own that changed since the last one, with their stage, linking back to Lever.", reads("Lever")] },
};

// ...each card is its own channel, like zendesk's
export const WAITING_META = Object.freeze(Object.fromEntries(Object.entries(M).map(([t, m]) => [t, { ...m, channel: t }])));
export const WAITING_TYPES = Object.freeze(Object.keys(WAITING_META));
export const waitingIn = (group) => WAITING_TYPES.filter((t) => WAITING_META[t].group === group);
