// Connectors, Stripe-style like Settings: a searchable landing of grouped category cards
// (AI · Messaging · Developer · Local & data), each drilling into a detail page with a
// setup WIZARD (stepper) plus Sources/management. All connectors live here - channel
// connectors (Outlook, Teams, Slack, GitHub), cloud AI APIs (Anthropic, OpenAI, Azure
// OpenAI - wired into intent triage), AI CLI agents, and scheduled report connections.
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, IconButton, InputAdornment, MenuItem, Popover, Radio, Select, Step, StepButton,
  StepContent, Stepper, Switch, TextField, Typography,
} from "@mui/material";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import AddIcon from "@mui/icons-material/Add";
import BoltIcon from "@mui/icons-material/Bolt";
import SearchIcon from "@mui/icons-material/Search";
import SyncIcon from "@mui/icons-material/Sync";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import RestartAltIcon from "@mui/icons-material/RestartAlt";
import TerminalIcon from "@mui/icons-material/Terminal";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import api from "./api";
import { PANEL, PANEL2, BORDER, DIM, FAINT, INK, mono } from "./theme.jsx";
import { ChannelIcon, StatusDot, timeAgo, Crumb, UnderTabs, Empty, FilterPills, SideRail, ConfirmDelete, Confirm } from "./ui.jsx";
import { CAN_NOTIFY } from "./notify.js";
import { hasLogo } from "./logos.jsx";
import { AgentsPage } from "./AgentsPanel.jsx";
import { TerminalPane } from "./TerminalView.jsx";
import { plannedFor } from "./connectorCatalog.js";

/* ── Get AI to set it up: the card's Guide becomes the coding agent's prompt, in a live terminal ON
   the card (taskuary/aisetup.py). The agent asks here for what only a human can fetch, saves it onto
   the card through the API and runs Test until it passes - and it is a task on the Board meanwhile. ── */
const AiSetup = ({ conn, steps, fields = [], secretLabel = "", agentSteps = [], reload }) => {
  const [sess, setSess] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => {           // the card reloads, the agent is still there: reattach
    let alive = true;
    api.get(`/api/connectors/${conn.ConnectorId}/ai-setup`).then(({ data }) => { if (alive && data.session) setSess(data.session); }).catch(() => {});
    return () => { alive = false; };
  }, [conn.ConnectorId]);
  const start = async () => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post(`/api/connectors/${conn.ConnectorId}/ai-setup`,
        { guide: steps || [], fields: (fields || []).map(([l, k]) => [l, k]), secret_label: secretLabel || "", agent_steps: agentSteps || [] });
      setSess(data);
    } catch (e) { setErr(e?.response?.data?.detail || "could not start the agent"); }
    setBusy(false);
  };
  const done = async () => {
    try { await api.post(`/api/tasks/${sess.taskId}/wrap`, {}); } catch { /* the session may already be gone */ }
    setSess(null); reload?.();
  };
  const ref = sess?.taskId ? `TQ-${String(sess.taskId).padStart(4, "0")}` : "";
  return (
    <Box sx={{ mb: 2, p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: PANEL2, display: "flex", flexDirection: "column", gap: 1 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
        <TerminalIcon sx={{ fontSize: 18, color: DIM }} />
        <Box sx={{ flex: 1, minWidth: 240 }}>
          <Typography sx={{ fontWeight: 700, fontSize: 13, color: INK }}>Get AI to set it up</Typography>
          <Typography variant="caption" sx={{ color: DIM, lineHeight: 1.5, display: "block" }}>
            Your coding agent takes the Guide as its prompt, asks you here for anything only you can fetch, saves it onto this
            card and runs Test until it passes. It sits on the Board as a task while it works.
          </Typography>
        </Box>
        {sess ? (
          <>
            <Typography variant="caption" sx={{ color: FAINT }}>{ref} on the Board</Typography>
            <Button size="small" variant="outlined" onClick={done}>Done — close the session</Button>
          </>
        ) : (
          <Button variant="contained" disableElevation disabled={busy} onClick={start}
            startIcon={busy ? <CircularProgress size={12} sx={{ color: "#fff" }} /> : <BoltIcon sx={{ fontSize: 15 }} />}>
            {busy ? "starting…" : "Get AI to set it up"}
          </Button>
        )}
      </Box>
      {err && <Alert severity="error" sx={{ fontSize: 12.5 }}>{err}</Alert>}
      {sess && <TerminalPane sid={sess.sid} height={360} />}
    </Box>
  );
};

/* ── connector metadata: channel + AI connectors (rows in the connector table) ── */
const META = {
  outlook: { group: "Messaging", channel: "email", srcLabel: "Mailboxes", srcPh: "someone@yourdomain.com",
    fields: [["tenant_id (tenant app only)", "tenant_id"], ["client_id (your own app - sign-in or tenant app)", "client_id"]],
    secretLabel: "client secret (tenant app only)",
    desc: "Your Microsoft mailbox on the Timeline through triage. Sign in with your own account - no Azure portal - or register your own app if you prefer.",
    howto: ["Sign in with Microsoft (anyone): Credentials → Sign in with Microsoft → open microsoft.com/devicelogin, enter the code, sign in with your own account and accept. That is mail, sending and calendar for your mailbox - work or personal (Outlook.com). Nobody registers anything.",
      "\"Need admin approval\": some organisations let only an admin say yes to a new app. The card then shows an approval link - forward it to your Microsoft 365 admin. They sign in, click Accept once, and everyone in the organisation can sign in from then on. It is a consent grant on Taskuary's app id, not an app registration on their side; the yellow \"unverified publisher\" note on their screen is expected.",
      "Register your own Microsoft app (optional - if your organisation only approves apps it registered itself, or you want your own name on the consent screen). portal.azure.com → Microsoft Entra ID → App registrations → New registration: name it Taskuary; Supported account types: \"Accounts in any organizational directory and personal Microsoft accounts\" (or just your organisation); Redirect URI: platform \"Mobile and desktop applications\", tick https://login.microsoftonline.com/common/oauth2/nativeclient → Register.",
      "Then: Authentication → Advanced settings → Allow public client flows = Yes → Save. API permissions → Add a permission → Microsoft Graph → Delegated permissions: offline_access, User.Read, Mail.ReadWrite, Mail.Send, Calendars.Read → Add. No client secret - a sign-in app is public by design. Copy the Application (client) ID into client_id here (under Admin?) and sign in above - or set TASKUARY_MS_CLIENT_ID on the server so every install uses it. No Partner Center and no publisher verification: those only remove the \"unverified\" label on the consent screen.",
      "Tenant app (admins - required for Teams chat reading and for mailboxes other than your own): the same App registrations → New registration, then API permissions → APPLICATION permissions Mail.Read (Mail.ReadWrite for Outlook drafts on approve or 'Mark items read at the source') and Calendars.Read → Grant admin consent; Certificates & secrets → New client secret. Enter tenant_id + client_id and paste the secret under Admin?; blank = the server's AZURE_* env vars.",
      "Mailboxes: signing in adds your own automatically. A tenant app reads every mailbox you add as a UPN under Sources.",
      "Test acquires a real Graph token and reports exactly what failed if anything - and whether the calendar can be read. Enable, and mail flows through the same triage funnel as everything else."],
    // written FOR the agent: it drives the device-code sign-in through the API and relays the code
    agent: ["Preferred road, no Azure portal: POST {base}/api/connectors/{cid}/ms/signin{hdr}. It returns user_code, verification_uri and a flow id. Tell the owner: open <verification_uri>, enter <user_code>, sign in with their own Microsoft account and Accept.",
      "Poll POST {base}/api/connectors/{cid}/ms/poll{hdr} with JSON {\"flow\": \"<flow>\"} every 5 seconds. status pending = keep waiting; status ok = the card is connected as them and their mailbox was added as a source; status error = read detail. If the error carries admin_consent_url, give the owner that link to forward to their Microsoft 365 admin, and start again at step 1 once the admin has approved.",
      "Only if the owner says they are an admin who wants a tenant app (needed for Teams chat reading or for mailboxes other than their own): ask for tenant_id, client_id and the client secret, save tenant_id and client_id in ConfigJson and the client secret as Secret.",
      "Run Test (POST {base}/api/connectors/{cid}/test{hdr}), turn the connector on (POST {base}/api/connectors{hdr} with {\"ConnectorId\": {cid}, \"Active\": true}) and say SETUP DONE."] },
  teams: { group: "Messaging", channel: "teams", srcLabel: "Users / chat ids", srcPh: "user UPN, e.g. jsmith@yourcompany.com",
    fields: [["tenant_id", "tenant_id"], ["client_id", "client_id"],
      ["Notify chat id", "notify_chat", "19:…@thread.v2", "Only for the Notifications role — the chat id from a Teams URL"]],
    secretLabel: "client secret",
    desc: "Ingest Teams chats via Graph. Leave credentials blank to reuse the Outlook connector's app.",
    howto: ["Credentials: leave everything blank and Teams automatically reuses the Outlook connector's saved Graph app (or the server's AZURE_* env vars). Only fill these to use a different app registration.",
      "App-only chat reading is a Microsoft PROTECTED API: the tenant needs Microsoft-approved Chat.Read.All - until that approval is granted, Test shows the 403 telling you so.",
      "Add the user whose chats to ingest as a UPN under Sources. Your UPN (User Principal Name) is your Microsoft 365 sign-in address - usually just your work email. Find it in Teams: click your profile picture, it's the address under your name. Or run `whoami /upn` in a terminal on a work Windows machine, or check Azure Portal → Users → your account → User principal name.",
      "A specific chat id works too (Teams web: open the chat, the 19:...@thread.v2 part of the URL).",
      "Test probes an actual chat read for the first Teams source, not just the token."],
    agent: ["GET {base}/api/connectors{hdr} and look at the outlook card: Teams reuses its app. If that card has tenant_id and client_id and a secret (a tenant app), leave this card's credentials blank. If it only carries a personal sign-in (auth = user) or nothing, say plainly that Teams chat reading needs a tenant app with the Microsoft-approved Chat.Read.All application permission, ask whether the owner is a Microsoft 365 admin who has one, and stop if not - do not invent a registration.",
      "Find the owner's UPN yourself when you can: on a domain-joined Windows machine run `whoami /upn`; otherwise ask - it is usually their work email. Add it with POST {base}/api/sources{hdr} and JSON {\"Channel\": \"teams\", \"Address\": \"<upn>\", \"ConnectorId\": {cid}, \"Active\": true}.",
      "Run Test (POST {base}/api/connectors/{cid}/test{hdr}). A 403 naming Chat.Read.All means the tenant has not been granted the protected API - report that as the blocker, it is not something to retry. Otherwise turn the connector on and say SETUP DONE."] },
  slack: { group: "Messaging", channel: "slack", srcLabel: "Channel IDs", srcPh: "C0123456789",
    fields: [], secretLabel: "bot token (xoxb-…)",
    desc: "Ingest Slack channels with a bot token - messages land on the Timeline through triage.",
    howto: ["Create a Slack app (api.slack.com/apps) → OAuth & Permissions → bot token scopes: channels:history, channels:read.",
      "Install the app to your workspace and invite the bot to the channels to ingest (/invite @yourbot).",
      "Paste the xoxb- bot token under Credentials (write-only).",
      "Add each channel ID under Sources (channel → View details → ID at the bottom).",
      "Test authenticates and probes a real channel read."],
    agent: ["The Slack app is the owner's to create (api.slack.com/apps: bot token scopes channels:history and channels:read, install to the workspace). Ask them for the xoxb- bot token and save it as Secret.",
      "List the channels yourself instead of asking for IDs: GET https://slack.com/api/conversations.list?types=public_channel,private_channel&limit=200 with header Authorization: Bearer <token>. Show the owner names, ask which to watch, and add each chosen id with POST {base}/api/sources{hdr} and JSON {\"Channel\": \"slack\", \"Address\": \"<channel id>\", \"ConnectorId\": {cid}, \"Active\": true}.",
      "Remind the owner the bot must be invited into each of those channels (/invite @bot) or the read will fail; then Test (POST {base}/api/connectors/{cid}/test{hdr}), turn the connector on, SETUP DONE."] },
  telegram: { group: "Messaging", channel: "telegram", srcLabel: "Chat IDs — only chats flipped ON become work", srcPh: "-1001234567890",
    fields: [["Notify chat id", "notify_chat", "", "Only for the Notifications role — same id the chat's Source card shows"]],
    secretLabel: "bot token (from @BotFather)",
    desc: "A Telegram bot as an inbound channel - approved chats flow through triage; approved replies go back into the same chat. Unknown chats never become work: a bot is public.",
    howto: ["Message @BotFather in Telegram → /newbot → copy the token.",
      "Paste the token under Credentials (write-only) and Test.",
      "Finding a chat id is automatic: message your bot (or add it to a group) and Sync — the chat appears under Sources with its chat id, switched OFF. Flip on the ones that are yours; messages flow from then on.",
      "Everything else stays out by design — anyone can find and message a public bot, and an unapproved stranger must never be able to put tasks on your board.",
      "For a group: add the bot to it and disable its privacy mode (@BotFather → /setprivacy) so it sees messages."],
    agent: ["Ask the owner for the bot token from @BotFather (/newbot, or /token for an existing bot) and save it as Secret; Test (POST {base}/api/connectors/{cid}/test{hdr}).",
      "Chat ids are discovered, never typed: ask the owner to send any message to the bot (or add it to the group and post there), then run a sync yourself with POST {base}/api/ingest/poll{hdr} and GET {base}/api/sources{hdr} - the chat appears as a telegram source, switched OFF.",
      "Read the new sources back to the owner and ask which are theirs; flip those on with POST {base}/api/sources{hdr} and JSON {\"SourceId\": <id>, \"Active\": true}. Never flip on a chat the owner did not name - a bot is public and strangers must not be able to put tasks on the board.",
      "For a group, remind them to disable the bot's privacy mode (@BotFather > /setprivacy) or it will not see messages. Turn the connector on and say SETUP DONE."] },
  whatsapp: { group: "Messaging", channel: "whatsapp", srcLabel: "Chat JIDs — only the chats listed here come in (a person by number@s.whatsapp.net, a group by its @g.us JID; add * to take every direct chat)", srcPh: "15551234567@s.whatsapp.net",
    fields: [["bridge URL (blank = http://127.0.0.1:8977)", "bridge_url"],
      ["Notify chat JID", "notify_chat", "15551234567@s.whatsapp.net",
       "Only for the Notifications role — the WhatsApp JID of the chat to ping"]],
    secretLabel: null,
    desc: "Your own WhatsApp, via a small bridge that runs beside Taskuary (Baileys, installed separately) - chats flow through triage, approved replies go back into the chat.",
    howto: ["Three steps, all in the Pair with your phone box above. 1 - Node 18+ on this machine (Windows: `winget install OpenJS.NodeJS.LTS`, or nodejs.org). The box checks for it and tells you if it is missing; nothing else to install.",
      "2 - The bridge starts by itself once Node is there (first time it fetches its dependency, Baileys - a minute or two). 3 - The QR appears; on your phone: WhatsApp → Linked devices → Link a device → scan. The box turns green when the phone accepts.",
      "Leave the bridge running (it survives closing the browser; a reboot stops it - the box starts it again when you open this card). Test here confirms the pairing and adds a catch-all source.",
      "The catch-all covers DIRECT chats. Group chats are opt-in: add a group's JID under Sources and only that group comes in - groups you never picked stay out of the funnel.",
      "Unofficial protocol (WhatsApp Web) - use a number you would risk; business-critical numbers belong on the official API."],
    // written FOR the agent: the machine-side work is its own; the phone is the owner's
    agent: ["Do NOT run node bridge.mjs yourself: it is a server and never returns - an agent that ran it in the foreground sat on it for five minutes. Taskuary starts it: POST {base}/api/connectors/{cid}/wa/bridge/start{hdr}. It installs the bridge's dependency when missing (a few minutes on a slow line) and launches the bridge detached.",
      "Poll GET {base}/api/connectors/{cid}/wa/status{hdr} every 5 seconds and read manager.phase: installing → starting → running; bridge becomes true when it answers. If phase is failed, read manager.detail - node missing means the owner installs Node 18+ from nodejs.org (the one install that is theirs); anything else, report it and stop.",
      "If connected is false: do NOT print the QR here (a terminal QR is too big to scan) and do NOT ask for a phone number. The card above this terminal draws the bridge's QR itself and redraws it as it rotates - tell the owner to scan it from the phone: WhatsApp > Linked devices > Link a device. Poll GET http://127.0.0.1:8977/status every 5 seconds until connected is true. Only if the owner SAYS they would rather type a code: ask for the number, restart the bridge with --phone <digits only>, and relay pairingCode from /status.",
      "Run the connector Test (POST {base}/api/connectors/{cid}/test{hdr}) - it confirms the pairing and adds the catch-all source: every DIRECT chat comes in; group chats only when their JID is added as a source.",
      "Ask the owner whether every chat should come in or only specific ones. For specific ones: have them (or someone) send a message in each wanted chat, then GET {base}/api/connectors/{cid}/wa/chats{hdr} and add each wanted JID with POST {base}/api/sources{hdr} and JSON {\"Channel\": \"whatsapp\", \"Address\": \"<jid>\", \"ConnectorId\": {cid}, \"Active\": true}. Once specific chats exist, only those come in.",
      "Turn the connector on (POST {base}/api/connectors{hdr} with {\"ConnectorId\": {cid}, \"Active\": true}), remind the owner the bridge must stay running, and say SETUP DONE."] },
  imessage: { group: "Messaging", channel: "imessage", srcLabel: "Chat ids (optional — blank takes every chat)", srcPh: "iMessage;-;+15551234567",
    fields: [["Look back this many days on first sync (blank = from now on)", "lookback_days", "", "Only read on the FIRST sync — years of private history never import by accident"],
      ["Check for new messages every N seconds (blank = the global sync interval)", "poll_seconds", "60", "A chat is slower on the ten-minute mailbox clock; 60 is a good number. Only this connector polls faster"]],
    secretLabel: null,
    desc: "The Mac's own Messages — iMessage, SMS and RCS that reach this machine. Chats flow through triage, approved replies go back into the same chat through Messages.app. macOS only.",
    howto: ["No token: Messages.app is the account. Taskuary reads the history macOS already keeps on this Mac (~/Library/Messages/chat.db) and asks Messages.app to send.",
      "Reading needs Full Disk Access — a macOS permission, granted to the app Taskuary was launched from (Terminal, iTerm, your IDE, or the python binary itself). Test tells you which one it detected, and Settings usually needs that host relaunched before it takes.",
      "System Settings → Privacy & Security → Full Disk Access → switch on (or + and add) the host Test named, then Test again. A real read of the database is the proof — not the checkbox.",
      "Sending needs Automation: the first reply makes macOS ask whether that host may control Messages. Allow it. Test never sends anything.",
      "New messages from the moment of the first sync; the optional look-back here reads a few days of history instead. Chat ids under Sources LIMIT which chats come in — blank means every chat that reaches this Mac.",
      "macOS 13 and later; macOS 12 best effort. On Linux and Windows the card stays here but Test says it needs a Mac."],
    agent: ["Check the platform first (`uname -s`). Not a Mac: say so and stop - there is nothing to set up here.",
      "Run Test (POST {base}/api/connectors/{cid}/test{hdr}) and read detail: it names the HOST that needs Full Disk Access (Terminal, iTerm, the IDE, or the python binary). That permission is the owner's to grant: System Settings > Privacy & Security > Full Disk Access, switch on (or + and add) exactly that host, then relaunch it. Ask them to do that and Test again until the read succeeds.",
      "Ask whether every chat should come in or only some; for some, add chat ids as sources (POST {base}/api/sources{hdr}, Channel imessage). Ask if they want history: lookback_days in ConfigJson reads that many days on the first sync; blank is from now on. Turn the connector on, SETUP DONE - and tell them the first reply will make macOS ask for Automation permission, which they should allow."] },
  gmail: { group: "Messaging", channel: "email", srcLabel: "Mailbox", srcPh: "you@gmail.com",
    fields: [["mailbox address", "address"],
      ["Google OAuth client id (optional — calendar)", "google_client_id", "", "Only for calendar access: an OAuth client from Google Cloud with the Calendar API enabled"],
      ["Google OAuth client secret (optional — calendar)", "google_client_secret"],
      ["Google refresh token (optional — calendar)", "google_refresh_token", "", "From the OAuth consent flow with scope calendar.readonly; with it, replies about time check this calendar too"]],
    secretLabel: "App Password (16 characters)",
    desc: "A Gmail or Google Workspace mailbox - IMAP in through triage, replies back over Gmail's own SMTP, in-thread. Optional OAuth fields add the calendar.",
    howto: ["Turn on 2-Step Verification for the Google account (App Passwords require it).",
      "Create an App Password: myaccount.google.com -> Security -> App passwords -> app: Mail.",
      "Enter the mailbox address under Credentials and paste the 16-character App Password (write-only).",
      "Test logs in and adds the mailbox as a source; new mail flows in on the next sync.",
      "Replies you approve are sent from this same address over SMTP, threaded into the conversation."],
    agent: ["Ask for the Gmail address and save it as address in ConfigJson.",
      "The App Password is the owner's to create (myaccount.google.com > Security > 2-Step Verification on, then App passwords > Mail). Ask them to paste the 16 characters here, save it as Secret, and never echo it back.",
      "Test (POST {base}/api/connectors/{cid}/test{hdr}) logs in and adds the mailbox as a source. Turn the connector on, SETUP DONE. The Google calendar fields are optional and rarely wanted - skip them unless asked."] },
  imap: { group: "Messaging", channel: "email", srcLabel: "Mailbox", srcPh: "you@yourdomain.com",
    fields: [["mailbox address", "address"], ["IMAP host (e.g. imap.yourdomain.com)", "imap_host"],
             ["SMTP host (blank = imap host with imap->smtp)", "smtp_host"],
             ["TLS certificate (blank = check it; a sha256 to accept that one; 'any' for none)", "tls_accept"]],
    secretLabel: "mailbox password",
    desc: "Any mailbox that speaks IMAP - a domain.com address, Yahoo, an ISP, your webhost. In through triage, replies out over its SMTP.",
    howto: ["Find your provider's IMAP and SMTP hostnames (usually imap./smtp. + your domain; ports 993/587).",
      "Enter the address and IMAP host under Credentials; SMTP host only if it does not follow the imap->smtp pattern.",
      "Paste the mailbox password (write-only). Providers with app passwords (Yahoo, iCloud) want those.",
      "Test logs in and adds the mailbox as a source; new mail flows in on the next sync.",
      "Shared hosting often presents a certificate in the HOST's name, not yours - the error names the certificate and gives you the fingerprint to paste into TLS certificate, the way Outlook lets you dismiss that dialog."],
    agent: ["Ask for the mailbox address. Find the hosts yourself: GET https://autoconfig.thunderbird.net/v1.1/<domain> (it returns the IMAP and SMTP hostnames for most providers), and otherwise try imap.<domain> / mail.<domain> on port 993 and smtp.<domain> on 587 with a socket probe. Only ask the owner if none answers.",
      "Microsoft-hosted mailbox (outlook.com, hotmail, Microsoft 365)? IMAP passwords no longer work there - point the owner at the Outlook card and stop.",
      "Ask for the mailbox password (Yahoo and iCloud want an app password instead) and save it as Secret; save address, imap_host and, only if it breaks the imap->smtp pattern, smtp_host in ConfigJson. Test (POST {base}/api/connectors/{cid}/test{hdr}), turn the connector on, SETUP DONE."] },
  github: { group: "Developer", channel: "github", srcLabel: "Repositories", srcPh: "org/repo",
    fields: [], secretLabel: "fine-grained PAT",
    desc: "Paste a PAT - repos are auto-discovered, feed the Board's repo picker and the coder's issue loop. Per repo, choose what issues and PRs do: tasks, feed, or off.",
    howto: ["Create a fine-grained PAT: GitHub → Settings → Developer settings → Fine-grained tokens.",
      "Repository access: the repos the agent may touch. Permissions: Issues Read+Write, Pull requests Read+Write, Metadata Read.",
      "Paste the token under Credentials - that's ALL the config: on save Taskuary discovers every repo the token reaches, adds them under Sources, and writes the repository map into SOUL.md.",
      "Everything inbound lives on ONE step — Inbound, what becomes work: the trigger/feed switch, a per-repo picker for what issues and PRs do (tasks = through triage, feed = timeline only, off = ignored), and the agent prompts. Triage sees each item's author and GitHub association, so a stranger's PR on a public repo files as FYI instead of becoming work — and github items never auto-start a coding agent; you promote the ones that deserve one.",
      "When you DO send a PR or issue to the agent, its prompt carries the standing rules you set on that same Inbound step — the PR default says judge it (useful? safe? minimal?), run the tests, report a verdict, and never merge.",
      "Test re-runs discovery and reports who it's authenticated as.",
      "Coding tasks then open an issue first, the agent works it, and closing the task closes the issue."],
    agent: ["The fine-grained PAT is the owner's to mint (GitHub > Settings > Developer settings > Fine-grained tokens: the repos the agent may touch; Issues Read+Write, Pull requests Read+Write, Metadata Read). Ask for it and save it as Secret - saving runs discovery: every reachable repo is added under Sources and the repo map is written into SOUL.md.",
      "Read the discovery result back (who it authenticated as, how many repos). If `gh` is installed here, `gh auth status` tells you which account the machine already uses - mention a mismatch.",
      "Ask which repos should make work: per repo, issues and PRs can be tasks, feed or off - the owner sets that on the Inbound step of the card; you only report what exists. Test (POST {base}/api/connectors/{cid}/test{hdr}), turn the connector on, SETUP DONE."] },
  jira: { group: "Project management", channel: "jira", srcLabel: "Site", srcPh: "yourteam.atlassian.net",
    fields: [["site URL (https://yourteam.atlassian.net)", "base_url"], ["account email (the one the token belongs to)", "email"]],
    secretLabel: "API token",
    desc: "Jira issues ASSIGNED TO YOU land on the Timeline through triage — 'assigned in Jira' and 'asked by email' end up in the one funnel.",
    howto: ["Create an API token: id.atlassian.com → Security → Create API token.",
      "Enter the site URL and the account email under Credentials, paste the token (write-only).",
      "Test authenticates as you and adds the site under Sources.",
      "From then on every sync brings in issues assigned to you (updated since the last poll) — each shows its status, priority and reporter, and links back to Jira.",
      "Nothing is written back to Jira; Taskuary only reads."] },
  asana: { group: "Project management", channel: "asana", srcLabel: "Workspace", srcPh: "added by Test",
    fields: [],
    secretLabel: "Personal Access Token",
    desc: "Asana tasks ASSIGNED TO YOU land on the Timeline through triage, linking back to Asana.",
    howto: ["Create a Personal Access Token: app.asana.com/0/my-apps → Create new token.",
      "Paste it under Credentials (write-only) — that is all the config.",
      "Test authenticates, finds your workspace and adds it under Sources.",
      "Every sync brings in open tasks assigned to you that changed since the last poll.",
      "Nothing is written back to Asana; Taskuary only reads."] },
  monday: { group: "Project management", channel: "monday", srcLabel: "Account", srcPh: "added by Test",
    fields: [["board ids to watch, comma-separated (blank = your 25 most recently used boards)", "board_ids"]],
    secretLabel: "API token",
    desc: "Monday.com items ASSIGNED TO YOU (any People column naming you) land on the Timeline through triage.",
    howto: ["Get an API token: your avatar → Developers → My access tokens (admin tokens work too).",
      "Paste it under Credentials (write-only). Test authenticates and remembers who 'you' are.",
      "Monday has no assigned-to-me API, so the poll walks boards and keeps items whose People column names you — blank config walks your 25 most recently used boards; list board ids to pin it down (the number in the board's URL).",
      "Every sync brings in your items that changed since the last poll, linking back to the board.",
      "Nothing is written back to Monday; Taskuary only reads."] },
  clickup: { group: "Project management", channel: "clickup", srcLabel: "Workspace", srcPh: "added by Test",
    fields: [],
    secretLabel: "API token (starts pk_)",
    desc: "ClickUp tasks ASSIGNED TO YOU land on the Timeline through triage, with their list, status and priority.",
    howto: ["Get a personal API token: Settings → Apps → API Token → Generate. It starts pk_ and does not expire.",
      "Paste it under Credentials (write-only). ClickUp wants the token raw, so don't add 'Bearer' — Taskuary handles the header.",
      "Test authenticates, remembers who 'you' are and which Workspace to walk, and adds it under Sources.",
      "Every sync brings in tasks assigned to you that changed since the last poll, linking back to ClickUp.",
      "Nothing is written back to ClickUp; Taskuary only reads."] },
  todoist: { group: "Project management", channel: "todoist", srcLabel: "Account", srcPh: "added by Test",
    fields: [["filter query (blank = (today | overdue))", "filter"]],
    secretLabel: "API token",
    desc: "The Todoist tasks a filter says are live — due today and overdue by default — land on the Timeline through triage.",
    howto: ["Get your API token: avatar → Settings → Integrations → Developer → copy the API token.",
      "Paste it under Credentials (write-only).",
      "Todoist is a personal list, so most tasks have no assignee and 'assigned to me' would match only shared projects. The poll asks a FILTER QUERY instead — what Todoist itself says is live.",
      "Blank means (today | overdue). Write any Todoist filter to change it: 'assigned to: me' for shared projects, '@work & 7 days', 'p1', and so on.",
      "Each task files once — Todoist has no updated-since filter, so re-runs dedupe by task id rather than re-filing edits.",
      "Nothing is written back to Todoist; Taskuary only reads."] },
  gitlab: { group: "Developer", channel: "gitlab", srcLabel: "Instance", srcPh: "added by Test",
    fields: [["instance URL (blank = https://gitlab.com)", "base_url"]],
    secretLabel: "Personal Access Token (scope: read_api)",
    desc: "GitLab issues and merge requests ASSIGNED TO YOU land on the Timeline through triage — gitlab.com or your own instance.",
    howto: ["Create a Personal Access Token: avatar → Preferences → Access tokens, scope read_api.",
      "Self-hosted? Enter the instance URL; blank means gitlab.com.",
      "Paste the token (write-only). Test authenticates as you and adds the instance under Sources.",
      "Every sync brings in issues and MRs assigned to you that changed since the last poll, linking back to GitLab.",
      "Nothing is written back to GitLab; Taskuary only reads."] },
  azdo: { group: "Developer", channel: "azdo", srcLabel: "Organization", srcPh: "added by Test",
    fields: [["organization URL (https://dev.azure.com/yourorg)", "org_url"]],
    secretLabel: "Personal Access Token (Work Items: Read)",
    desc: "Azure DevOps work items ASSIGNED TO YOU land on the Timeline through triage.",
    howto: ["Create a PAT: User settings (top right) → Personal access tokens → New, scope Work Items: Read.",
      "Enter the organization URL (https://dev.azure.com/yourorg) and paste the PAT (write-only).",
      "Test authenticates and reports how many projects the token can see.",
      "Every sync runs a WIQL 'assigned to @Me' query and brings in work items that changed since the last poll.",
      "Nothing is written back to Azure DevOps; Taskuary only reads."] },
  sentry: { group: "Developer", channel: "sentry", srcLabel: "Organization", srcPh: "added by Test",
    fields: [["organization slug (first path segment of your Sentry URLs)", "org"],
      ["base URL (blank = https://sentry.io; set for self-hosted)", "base_url"]],
    secretLabel: "auth token (org:read + event:read)",
    desc: "New unresolved Sentry errors land on the Timeline through triage — production breakage joins the same funnel as the mail about it.",
    howto: ["Create an auth token: Sentry → Settings → Auth Tokens (scopes org:read, event:read).",
      "Enter the organization slug — the first path segment in your Sentry URLs.",
      "Paste the token (write-only). Test authenticates and adds the org under Sources.",
      "Every sync brings in unresolved issues whose last-seen changed since the last poll, with count and level, linking back to Sentry."] },
  pagerduty: { group: "Developer", channel: "pagerduty", srcLabel: "Account", srcPh: "added by Test",
    fields: [],
    secretLabel: "API token",
    desc: "Open PagerDuty incidents (triggered / acknowledged) land on the Timeline through triage.",
    howto: ["Get an API token: PagerDuty → Integrations → API Access Keys (a read-only key is enough).",
      "Paste it under Credentials (write-only) — that is all the config.",
      "Test probes the incidents API and adds the account under Sources.",
      "Every sync brings in incidents opened since the last poll with status, urgency and service, linking back to PagerDuty."] },
  linear: { group: "Project management", channel: "linear", srcLabel: "Workspace", srcPh: "added by Test",
    fields: [],
    secretLabel: "API key",
    desc: "Linear issues ASSIGNED TO YOU land on the Timeline through triage.",
    howto: ["Create a personal API key: Linear → Settings → Security & access → Personal API keys.",
      "Paste it under Credentials (write-only) — that is all the config.",
      "Test authenticates as you and adds the workspace under Sources.",
      "Every sync brings in issues assigned to you that changed since the last poll, linking back to Linear.",
      "Nothing is written back to Linear; Taskuary only reads."] },
  trello: { group: "Project management", channel: "trello", srcLabel: "Account", srcPh: "added by Test",
    fields: [["API key (trello.com/power-ups/admin → your Power-Up → API key)", "api_key"]],
    secretLabel: "token (generate it from the API key page)",
    desc: "Open Trello cards ASSIGNED TO YOU land on the Timeline through triage.",
    howto: ["Get an API key: trello.com/power-ups/admin → create a Power-Up if you have none → API key.",
      "On that same page use the Token link to authorize and copy the token.",
      "Enter the API key under Credentials and paste the token (write-only).",
      "Test authenticates as you; every sync brings in your open cards whose activity changed since the last poll."] },
  notion: { group: "Project management", channel: "notion", srcLabel: "Workspace", srcPh: "added by Test",
    fields: [],
    secretLabel: "internal integration secret",
    desc: "Notion pages shared with your integration show on the Timeline as they change — a FEED by default: edits are information, not assignments.",
    howto: ["Create an internal integration at notion.so/my-integrations and copy its secret.",
      "SHARE the pages or databases you care about with the integration (page → ⋯ → Connections) — it sees nothing else.",
      "Paste the secret under Credentials (write-only). Test authenticates the integration.",
      "Every sync surfaces pages edited since the last poll. It ships as a feed; flip the trigger role on if edits should become work."] },
  discord: { group: "Messaging", channel: "discord", srcLabel: "Channel IDs", srcPh: "1234567890123456789",
    fields: [],
    secretLabel: "bot token",
    desc: "Watch Discord channels with a bot — messages land on the Timeline through triage, and approved replies post back to the channel.",
    howto: ["Create an app at discord.com/developers → Bot → Reset Token, and turn ON the Message Content intent.",
      "Invite the bot to your server with permission to read (and send, for replies in) the channels you'll watch.",
      "Paste the bot token under Credentials (write-only).",
      "Add each channel ID under Sources (Discord → Settings → Advanced → Developer Mode, then right-click a channel → Copy Channel ID).",
      "Approving a drafted reply posts it into the same channel as the bot."],
    agent: ["The Discord app and bot are the owner's to create (discord.com/developers > Bot > Reset Token, Message Content intent ON, invited to the server). Ask for the bot token and save it as Secret.",
      "List the channels yourself: GET https://discord.com/api/v10/users/@me/guilds with header Authorization: Bot <token>, then GET https://discord.com/api/v10/guilds/<id>/channels for each server; text channels have type 0. Show names, ask which to watch, add each chosen id with POST {base}/api/sources{hdr} and JSON {\"Channel\": \"discord\", \"Address\": \"<channel id>\", \"ConnectorId\": {cid}, \"Active\": true}.",
      "Test (POST {base}/api/connectors/{cid}/test{hdr}), turn the connector on, SETUP DONE."] },
  anthropic: { group: "AI — agents & models", channel: "ai", srcLabel: null,
    fields: [["model (default claude-opus-5)", "model"]], secretLabel: "API key",
    desc: "Claude via the Anthropic API - powers intent triage (task / reply-only / FYI) once enabled.",
    howto: ["Create an API key at console.anthropic.com → API keys.",
      "Paste it under Credentials (write-only). Optionally set a model - default is claude-opus-5.",
      "Test runs a real round trip through the model.",
      "Enable it and every new inbound message is classified by the model, guided by SOUL.md - the first active AI connector wins."] },
  openai: { group: "AI — agents & models", channel: "ai", srcLabel: null,
    fields: [["model (default gpt-4o-mini)", "model"]], secretLabel: "API key",
    desc: "OpenAI models for intent triage - alternative to the Anthropic connector.",
    howto: ["Create an API key at platform.openai.com.",
      "Paste it under Credentials; optionally set a model.",
      "Test runs a real round trip. Enable to wire it into triage - the first active AI connector wins."] },
  azure_openai: { group: "AI — agents & models", channel: "ai", srcLabel: null,
    fields: [["endpoint", "endpoint"], ["deployment", "deployment"], ["api_version", "api_version"]], secretLabel: "API key",
    desc: "Your Azure OpenAI deployment for intent triage - endpoint + deployment + key.",
    howto: ["Azure Portal → your Azure OpenAI resource → Keys and Endpoint.",
      "Enter the endpoint (https://YOUR-RESOURCE.openai.azure.com), the deployment name, and optionally an api_version.",
      "Paste a key under Credentials. Test runs a real round trip through the deployment."] },
  openrouter: { group: "AI — agents & models", channel: "ai", srcLabel: null,
    fields: [["model (default openrouter/auto)", "model"]], secretLabel: "API key",
    desc: "One key, the whole catalog — open-weights Llama / Qwen / Mistral and every closed model, through OpenRouter's OpenAI-compatible API.",
    howto: ["Create a key at openrouter.ai → Keys.",
      "Paste it under Credentials; optionally set a model from openrouter.ai/models (e.g. meta-llama/llama-3.3-70b-instruct). Empty = openrouter/auto picks per request.",
      "Test runs a real round trip. Enable to wire it into triage, drafts, the digest and LEARNED.md — or pick it explicitly under Settings → Triage & routing."] },
  ollama: { group: "AI — agents & models", channel: "ai", srcLabel: null,
    fields: [["base_url (default http://127.0.0.1:11434)", "base_url"], ["model — required, e.g. llama3.2 / qwen2.5", "model"]],
    secretLabel: "API key (optional — a local server rarely needs one)",
    desc: "Open-source models on YOUR machine — Ollama out of the box, or any OpenAI-compatible server (LM Studio, llama.cpp, vLLM). Your mail never leaves the box.",
    howto: ["Install Ollama (ollama.com) and pull a model: ollama pull llama3.2 — or point base_url at LM Studio (http://127.0.0.1:1234), llama.cpp or vLLM.",
      "Enter the model name (ollama list shows what's installed). No key needed for a local server.",
      "Test runs a real round trip through the local model, then Enable makes it the triage brain — or pick it under Settings → Triage & routing.",
      "For the CODING side, local models ride the CLI road instead: add any CLI that reads a prompt on stdin under AI CLI agents."],
    agent: ["Check for a local server yourself: GET http://127.0.0.1:11434/api/tags (Ollama) - and http://127.0.0.1:1234/v1/models for LM Studio. If Ollama is not installed, ask the owner once whether to install it, then do it (winget install Ollama.Ollama on Windows, brew install ollama on a Mac, the ollama.com script on Linux) and start it.",
      "If /api/tags lists no models, ask which to pull (suggest llama3.2 for a laptop, qwen2.5 for more headroom) and run `ollama pull <model>` yourself - it downloads gigabytes, so say so and wait for it.",
      "Save model (and base_url only if not the default) in ConfigJson; no Secret. Test (POST {base}/api/connectors/{cid}/test{hdr}) runs a real round trip. Turn the connector on and say SETUP DONE - and that the owner can pick it as the triage brain under Settings."] },
  /* ── AI — voice: speech to text. A voice note on WhatsApp or Telegram is transcribed by the first
     active one of these and goes through triage as text; without one it still lands, marked "not
     transcribed", with the audio attached for a later click. The same connector powers the mic in
     the prompt boxes. Cheapest hosted: Groq (free tier, ~$0.04/hour after). Best accuracy: ElevenLabs
     Scribe / Deepgram Nova-3 / OpenAI gpt-4o-transcribe. Private: Local Whisper, or any Whisper server. ── */
  gemini_stt: { group: "AI — voice", channel: "ai", srcLabel: null,
    fields: [["model (default gemini-3.5-transcribe)", "model"], ["language code (optional, e.g. en-US — blank = auto)", "language"]],
    secretLabel: "Google Gemini API key",
    desc: "Google Gemini transcription — accurate speech-to-text with native custom-vocabulary biasing for names, acronyms and system terms.",
    howto: ["Create a paid Gemini API key in Google AI Studio. Do not put the key in the browser — Taskuary stores it on this server.",
      "Paste the key under Credentials. The default gemini-3.5-transcribe model understands the shared vocabulary configured on this page.",
      "Test uploads one second of silence, transcribes it, and immediately deletes the temporary Google file. Enable to transcribe voice notes and every Taskuary mic."],
    agent: ["Ask the owner for a paid Gemini API key from Google AI Studio and save it as Secret; never expose it in browser code or output.",
      "Leave model blank for gemini-3.5-transcribe unless the owner explicitly names another transcription model. Test the card, turn it on, and say SETUP DONE."] },
  groq_stt: { group: "AI — voice", channel: "ai", srcLabel: null,
    fields: [["model (default whisper-large-v3-turbo; whisper-large-v3 is more accurate)", "model"], ["language code (optional, e.g. en — blank = auto)", "language"]],
    secretLabel: "Groq API key (gsk_…)",
    desc: "Whisper on Groq — the cheapest hosted transcription (free tier; ~$0.04 per audio hour after) and the fastest: an hour of audio in seconds.",
    howto: ["Create a key at console.groq.com → API Keys (a free account is enough to start).",
      "Paste it under Credentials (write-only). Optionally set a model: whisper-large-v3-turbo (default, cheapest) or whisper-large-v3 (more accurate).",
      "Test sends a second of silence through the real endpoint. Enable, and voice notes on WhatsApp and Telegram arrive as text; the mic in the prompt boxes works too.",
      "Audio is billed with a 10-second minimum per request; a voice note is one request."] },
  openai_stt: { group: "AI — voice", channel: "ai", srcLabel: null,
    fields: [["model (default gpt-4o-mini-transcribe; gpt-4o-transcribe or whisper-1)", "model"], ["language code (optional)", "language"]],
    secretLabel: "OpenAI API key",
    desc: "OpenAI transcription — gpt-4o-mini-transcribe is cheap ($0.003/min) and accurate; gpt-4o-transcribe is the accuracy leader on independent benchmarks.",
    howto: ["Create an API key at platform.openai.com (the same key as the OpenAI triage connector works).",
      "Paste it under Credentials; optionally set a model.",
      "Test sends a second of silence through the real endpoint. Enable to transcribe voice notes and power the mic."] },
  deepgram: { group: "AI — voice", channel: "ai", srcLabel: null,
    fields: [["model (default nova-3)", "model"], ["language code (optional; nova-3 detects it otherwise)", "language"]],
    secretLabel: "Deepgram API key",
    desc: "Deepgram Nova-3 — the fastest hosted API, ~$0.26 per audio hour, very strong accuracy, generous free credit to start.",
    howto: ["Create a key at console.deepgram.com → API Keys (new accounts get free credit).",
      "Paste it under Credentials. Test sends a second of silence through the real endpoint.",
      "Enable to transcribe voice notes and power the mic."] },
  elevenlabs_stt: { group: "AI — voice", channel: "ai", srcLabel: null,
    fields: [["model (default scribe_v2)", "model"], ["language code (optional)", "language"]],
    secretLabel: "ElevenLabs API key",
    desc: "ElevenLabs Scribe — top-tier accuracy across 99 languages, ~$0.22 per audio hour; the pick when notes arrive in several languages.",
    howto: ["Create a key at elevenlabs.io → Profile → API Keys.",
      "Paste it under Credentials. Test sends a second of silence through the real endpoint.",
      "Enable to transcribe voice notes and power the mic."] },
  stt_server: { group: "AI — voice", channel: "ai", srcLabel: null,
    fields: [["base URL (default http://127.0.0.1:8000/v1 — speaches / faster-whisper-server; whisper.cpp server uses its own port)", "base_url"],
      ["model (as the server names it, e.g. Systran/faster-whisper-small)", "model"], ["language code (optional)", "language"]],
    secretLabel: "API key (optional — a local server rarely needs one)",
    desc: "Any speech-to-text server speaking the OpenAI audio endpoint: speaches (faster-whisper), whisper.cpp server, LocalAI — audio stays on your network.",
    howto: ["Run a server: `pip install speaches` (or docker) for faster-whisper with an OpenAI-compatible API, or whisper.cpp's server with the OpenAI endpoint on, or LocalAI.",
      "Enter its base URL and the model name it serves. No key unless you put one in front of it.",
      "Test sends a second of silence. Enable to transcribe voice notes and power the mic."],
    agent: ["Check whether a server already answers: GET http://127.0.0.1:8000/v1/models (speaches) and the whisper.cpp / LocalAI ports the owner names. If none, ask which they want and install it yourself (pip install speaches, then start it as a background process); confirm /v1/models lists a model.",
      "Save base_url and model in ConfigJson (no Secret unless the server wants one), Test (POST {base}/api/connectors/{cid}/test{hdr}), turn it on, SETUP DONE."] },
  local_whisper: { group: "AI — voice", channel: "ai", srcLabel: null,
    fields: [["model size (default small; base is faster, medium is more accurate)", "model"], ["language code (optional)", "language"],
      ["device (default cpu; cuda with an NVIDIA GPU)", "device"]],
    secretLabel: null,
    desc: "Whisper on this machine, no key and no server — faster-whisper inside Taskuary. Audio never leaves the box; the first run downloads the model.",
    howto: ["On the machine running Taskuary: pip install taskuary[voice] (installs faster-whisper).",
      "Pick a model size: small is a good default on a laptop CPU; medium if you have the patience or a GPU.",
      "Test downloads the model on first use (a few hundred MB) and transcribes a second of silence. Enable, and voice notes are transcribed locally."],
    agent: ["Run `pip show faster-whisper` in the environment Taskuary runs in; if missing, install it yourself: pip install taskuary[voice]. Check for an NVIDIA GPU (nvidia-smi) and set device cuda only if there is one.",
      "Save model (small unless the owner wants otherwise) in ConfigJson, Test (POST {base}/api/connectors/{cid}/test{hdr}) - warn the owner the first Test downloads the model - turn it on, SETUP DONE."] },
};

const MSSQL_HOWTO = [
  "This card is the CONNECTION only - set it up once, Test it, and every SQL report inherits it.",
  "Local SQL Server: keep auth on Windows (trusted) - server + database is all the config. Named instance? Use HOST\INSTANCE, e.g. localhost\SQLEXPRESS.",
  "Driver auto-picks the newest installed 'ODBC Driver NN for SQL Server'; SQL logins go under auth.",
  "Build the actual reports (query + AI summary + schedule) on the REPORTS tab.",
];
const MSSQL_AGENT = [
  "Check the machine yourself first: `Get-OdbcDriver -Name '*SQL Server*'` (Windows) or `odbcinst -q -d` lists the ODBC drivers; none installed means the owner needs 'ODBC Driver 18 for SQL Server' from Microsoft - offer to install it (winget install Microsoft.msodbcsql.18) and do it if they agree.",
  "Ask for the server (HOST or HOST\\INSTANCE) and database. Probe reachability yourself (Test-NetConnection <host> -Port 1433, or the instance's port) before saving.",
  "Try Windows authentication first - auth 'windows' in ConfigJson, no Secret - because on a domain-joined machine it usually just works. Only if Test says the login failed, ask for a SQL login: auth 'sql', username in ConfigJson, the password as Secret.",
  "Save server, database, auth (and driver only to override the auto-pick) in ConfigJson, Test (POST {base}/api/connectors/{cid}/test{hdr}) - it connects for real and reports the server version - then SETUP DONE; reports are built on the Reports tab.",
];

/* ── data-connection cards that share one field-driven detail page (mssql keeps its
   bespoke driver picker). Each is the CONNECTION only - reports live on the Reports tab. */
const DATA_META = {
  database: { title: "Any database (connection string)", types: ["database"],
    fields: [["connection string", "conn_str",
      "postgresql://user:{password}@host:5432/db   ·   mysql+pymysql://…   ·   DRIVER={…};SERVER=…"]],
    secretLabel: "password for {password} (optional — write-only)",
    desc: "Postgres, MySQL, Snowflake, Oracle, anything with a connection string — URLs run through SQLAlchemy, raw ODBC strings through pyodbc.",
    howto: ["Paste the connection string: a URL (postgresql://…, mysql+pymysql://…, snowflake://…) or a raw ODBC string (DRIVER={…};SERVER=…;).",
      "Keep the password OUT of the string: write {password} where it goes and paste the real one below (stored write-only, never shown again).",
      "URL engines need their Python driver on the server: pip install taskuary[db] plus e.g. psycopg2-binary (postgres) or pymysql (mysql).",
      "Test connects for real and runs a probe (SELECT 1 — engines that need FROM DUAL can set test_query in the config).",
      "Build the actual reports (query + AI summary + schedule) on the REPORTS tab; agents with the tool role can query it too."],
    agent: ["Ask what database it is and where (engine, host, port, database name, user). Build the connection string yourself with {password} where the password goes - never the real one - and save it as conn_str in ConfigJson; ask for the password and save it as Secret.",
      "Install the Python driver yourself in the environment Taskuary runs in: `pip install taskuary[db]` plus psycopg2-binary (Postgres), pymysql (MySQL), snowflake-sqlalchemy (Snowflake) as needed; check with `pip show`. Then Test (POST {base}/api/connectors/{cid}/test{hdr}) - it runs SELECT 1; an engine that wants FROM DUAL gets test_query in ConfigJson.",
      "Say SETUP DONE and that reports are built on the Reports tab."] },
  aws: { title: "Amazon Web Services", types: ["aws", "s3_object", "cloudwatch_logs"], discovers: true,
    fields: [["access key id", "access_key_id"], ["region(s), comma-separated (e.g. us-east-2, us-east-1)", "region"]],
    secretLabel: "secret access key (write-only; blank = server env / ~/.aws / instance role)",
    desc: "S3 objects, CloudWatch logs — or ANY service call — as scheduled reports, Timeline feeds and agent tools, with your IAM keys.",
    howto: ["Create an IAM user (or use an existing one) with read access to what you'll pull: AmazonS3ReadOnlyAccess, CloudWatchLogsReadOnlyAccess, etc.",
      "Enter the access key id + region and paste the secret access key (write-only). Leave everything blank to use the server's own AWS credentials (env vars, ~/.aws, an instance role).",
      "Several regions? List them comma-separated. CloudWatch log groups exist PER REGION - the same account shows a completely different set in us-east-1 and us-east-2 - so discovery sweeps each one and every object remembers where it was found. S3 is one global namespace, listed once, and each bucket is asked for its own region so reads go to the right endpoint.",
      "The server needs boto3: pip install taskuary[aws].",
      "Test & discover calls STS (reporting which account/ARN you are) and then asks the keys what they can SEE: every S3 bucket and CloudWatch log group is listed under 'What you have access to'.",
      "Each discovered object gets its own picker: report only (the default — selectable on the Reports tab, nothing polled), feed (new objects / matching log lines appear on the Timeline), tasks (they go through triage), or off.",
      "Reports tab then offers the same objects as pipelines: S3 object (read a file or list a prefix), CloudWatch logs (grep a group), and a generic AWS call (any service + operation, e.g. athena or ec2)."],
    agent: ["Look for credentials this machine already has before asking: `aws sts get-caller-identity` (if the CLI is installed), ~/.aws/credentials, AWS_* environment variables. If they exist and the owner agrees to use them, leave the key fields blank - the server uses its own credentials.",
      "Otherwise the IAM user and keys are the owner's to create (read-only policies such as AmazonS3ReadOnlyAccess, CloudWatchLogsReadOnlyAccess); ask for the access key id and region(s), save them in ConfigJson, and the secret access key as Secret.",
      "Install boto3 yourself: `pip install taskuary[aws]`. Test & discover (POST {base}/api/connectors/{cid}/test{hdr}) reports the account and lists buckets and log groups; read that back, then SETUP DONE - what each object does (report, feed, tasks) is picked on the card."] },
  intacct: { title: "Sage Intacct", types: ["intacct", "intacct_fields", "intacct_create", "intacct_update"],
    fields: [["sender id (the integration's, issued by Sage)", "sender_id"],
      ["sender password", "sender_password"],
      ["web services user id", "user_id"],
      ["company id", "company_id"],
      ["entity / location id (optional \u2014 blank = top level)", "entity_id"]],
    secretLabel: "web services user password (write-only)",
    desc: "The general ledger, AP bills, vendors, budgets and statistical accounts over the XML gateway \u2014 read as scheduled reports, and write by object once you approve it.",
    howto: ["Intacct wants a WEB SERVICES user, not your login: Company \u2192 Admin \u2192 Web Services Users \u2192 add one, give it a role that can read what you'll report on.",
      "Then Company \u2192 Setup \u2192 Security \u2192 Web Services Authorizations and add the sender id \u2014 without this every call is refused however correct the password is.",
      "Five credentials, and they authorise different things: the SENDER pair identifies the integration (Sage issues it), the USER pair is the web services user above, and the company id picks the tenant. Only the user password is stored write-only.",
      "Multi-entity? Leave the entity id blank to sit at the top level, or name one to scope every report to it.",
      "Test logs in for real and then tries to READ \u2014 a green card that only proves the password works hides the usual failure, which is a role with permission on nothing.",
      "Build the reports on the REPORTS tab: name an object (GLENTRY, APBILL, VENDOR, GLACCOUNT\u2026), the fields you want and any filters. Nobody remembers the field ids: the source card's 'What fields does APBILL have?' asks Sage itself and lists them, custom fields included, and the same lookup is a report in its own right when you want to hear about a new one.",
      "Or just say what you want in English: at the top of the Reports tab for a whole report, or on any source card for that one card. Either way it reads the object's real field list before writing the query.",
      "Writing is the same gateway, by object: intacct_create makes a record (an AP bill, a vendor, a journal batch) and intacct_update changes one that names itself (RECORDNO). The card ships at scope READ, so nothing an agent runs can post \u2014 it proposes, you approve in Review, and the receipt carries the key Intacct assigned."],
    agent: ["Reads are yours: run_tool with type intacct (object, fields, filters) for rows, or intacct_fields to ask Sage what an object actually HAS. Never guess a field id \u2014 a wrong one is refused by the gateway.",
      "You may NOT post to the books yourself. Propose it, and say in the session what it is for: TASKUARY-PROPOSE {\"action\": \"run_tool\", \"type\": \"intacct_create\", \"object\": \"APBILL\", \"record\": {\"VENDORID\": ..., \"WHENCREATED\": ..., \"APBILLITEMS\": [{\"ACCOUNTNO\": ..., \"AMOUNT\": ...}]}}. The owner approves it in Review and it posts then, not before. intacct_update is the same road.",
      "Read the object fields BEFORE you propose a write: a refused proposal is a wasted approval."] },
  quickbooks: { title: "QuickBooks Online", types: ["quickbooks", "quickbooks_vendors", "quickbooks_accounts", "quickbooks_bill", "quickbooks_expense"],
    fields: [["Intuit app client id (developer.intuit.com → your app → Keys & credentials)", "client_id"],
      ["Intuit app client secret", "client_secret"],
      ["environment — production, or sandbox for a test company", "env", "production"],
      ["company (realm) id — filled in by Connect", "realm_id"]],
    secretLabel: "refresh token (write-only) — Connect fills it in; it rotates on every use and is saved back each time",
    desc: "The books: bills, purchases, vendors and the chart of accounts as reports and agent tools — and the first system here an agent can POST to, on your approval: an AP bill or a paid expense.",
    connect: { label: "Connect to QuickBooks", status: (cid) => `/api/connectors/${cid}/quickbooks/status`, start: (cid) => `/api/connectors/${cid}/quickbooks/authorize`,
      text: "Opens Intuit's sign-in in a new tab. Pick the company; the token lands on this card and never reaches the browser." },
    howto: ["developer.intuit.com → Dashboard → Create an app → QuickBooks Online and Payments → scope Accounting. Keys & credentials has a Development (sandbox) and a Production tab — production keys need the app's short questionnaire; sandbox keys work the same day against Intuit's test company.",
      "On that same page add the REDIRECT URI shown on this card (http://localhost:<port>/api/quickbooks/callback) — Intuit refuses a sign-in whose redirect is not registered, character for character.",
      "Paste the client id and secret here, choose production or sandbox, Save, then Connect to QuickBooks: Intuit's sign-in opens, you pick the company, and the browser comes back to Taskuary with the token. Test reads the company name and a vendor list.",
      "Reads (queries, vendors, accounts) run at the card's default scope. The two WRITES — a bill, a paid expense — need scope write on this card; below that an agent can only PROPOSE one, which lands in Review with the vendor, amount and account, and approving it posts it. That is the design: nothing reaches the books without a click until you say otherwise.",
      "Build the reports on the REPORTS tab: 'QuickBooks Online' with a query in QBO's SQL (SELECT * FROM Bill WHERE TxnDate >= '2026-08-01'), or the vendor / account lists as their own reports."],
    agent: ["GET {base}/api/connectors/{cid}/quickbooks/status{hdr}: has_app says whether the Intuit keys are saved; connected says whether a token is. Neither is yours to make - the owner creates the app at developer.intuit.com and presses Connect (a browser sign-in). Ask for the client id and secret, save them in ConfigJson, tell them the redirect URI from status to register, then ask them to press Connect on the card.",
      "Once connected, POST {base}/api/connectors/{cid}/test{hdr}. A 401 in the detail means the refresh token expired (100 days unused) - the owner presses Connect again.",
      "Never post a bill or an expense yourself: propose it (TASKUARY-PROPOSE {\"action\": \"run_tool\", \"type\": \"quickbooks_bill\", \"vendor\": ..., \"amount\": ..., \"account\": ..., \"doc_number\": ...}) and say in the session what it is for. Turn the card on, SETUP DONE."] },
  teller: { title: "Bank & card feed (Teller)", types: ["teller_accounts", "teller_transactions", "teller_balances"],
    fields: [["Teller application id (teller.io → your application)", "application_id"],
      ["environment — sandbox, development (free, real banks, 100 logins) or production", "environment", "sandbox"],
      ["client certificate path (.pem) — development and production only", "cert_path", "C:/taskuary/teller/certificate.pem"],
      ["private key path (.pem) — development and production only", "key_path", "C:/taskuary/teller/private_key.pem"]],
    secretLabel: "access token (write-only) — Connect a bank fills it in",
    desc: "What left the bank and the cards, as rows: every account under one bank login, its transactions newest first, its balances. Read-only by construction — a feed cannot move money. Schedule the transactions with 'can become work' and each new one is a message triage judges.",
    connect: { widget: "teller", label: "Connect a bank", status: (cid) => `/api/connectors/${cid}/teller/status`, enroll: (cid) => `/api/connectors/${cid}/teller/enroll`,
      text: "Opens the bank's own sign-in (Teller Connect). The token for that login lands on this card; the browser never keeps it." },
    howto: ["teller.io → sign up → create an application. The dashboard hands you an application id and, for development and production, a certificate.pem and private_key.pem — save both somewhere on this machine and put their paths on the card. Sandbox needs no certificate and accepts any login at its fake banks, which is how to try the loop first.",
      "Paste the application id, pick the environment, Save, then Connect a bank: the bank's sign-in opens in a modal, you sign in, and the access token for that login lands on this card. One card is one bank login - Add another for a second bank.",
      "Test lists the accounts under the login. Build the reports on the REPORTS tab: 'Bank & card — transactions' for one account (its last four digits) or all of them, so many days back; switch on 'can become work (triage decides)' and every new transaction arrives as a message - the front door of the card-to-books playbook (docs/beyond-code.md).",
      "The development environment is free up to 100 bank logins; production is the same code with production keys and Teller's pricing."],
    agent: ["GET {base}/api/connectors/{cid}/teller/status{hdr}: has_app says whether the application id is saved, connected whether a token is. Neither is yours to make - the owner signs up at teller.io and signs in at their bank through Connect a bank on the card. Ask for the application id and the certificate paths, save them in ConfigJson, then ask them to press Connect a bank.",
      "Once connected, POST {base}/api/connectors/{cid}/test{hdr}. A 403 means the certificate does not match the application or the token belongs to another environment. Turn the card on, SETUP DONE."] },
  prometheus: { title: "Prometheus", types: ["prometheus"],
    fields: [["base URL", "base_url", "http://prometheus.yourcompany.local:9090"]],
    secretLabel: "bearer token (optional — most Prometheus servers need none)",
    desc: "PromQL instant queries as scheduled reports and agent tools — each series comes back as a row of its labels + value.",
    howto: ["Enter the server's base URL (the address the Prometheus UI runs on, usually port 9090).",
      "Behind an auth proxy? Paste the bearer token (write-only); plain servers need nothing.",
      "Test runs a trivial query for real.",
      "Build the reports (PromQL + AI summary + schedule) on the REPORTS tab — 'up == 0' every morning is the classic."] },
  datadog: { title: "Datadog", types: ["datadog"],
    fields: [["site (blank = datadoghq.com; EU = datadoghq.eu)", "site"],
      ["application key (Organization Settings → Application Keys)", "app_key"]],
    secretLabel: "API key (write-only)",
    desc: "Your Datadog monitors and their states as scheduled reports and agent tools — trouble sorts first.",
    howto: ["Get an API key (Organization Settings → API Keys) and an application key (→ Application Keys).",
      "Enter the site if not US1 (datadoghq.eu, us3.datadoghq.com, …), the application key, and paste the API key (write-only).",
      "Test validates the key pair for real.",
      "Build the reports on the REPORTS tab: all monitors, or filtered by name — Alert and Warn states sort to the top."] },
  /* Research: the web as a report source. All four are one REST call with a key - what is NOT
     here is anything that DRIVES a browser (log in, click, fill), because that runs over CDP
     through Playwright or Stagehand and cannot be reached from an API at all. */
  exa: { title: "Exa", types: ["exa"], fields: [],
    secretLabel: "API key (write-only)",
    desc: "Neural web search with the page text already extracted — a research source for reports, and a tool an agent can call.",
    howto: ["Get a key at exa.ai → Dashboard → API Keys.",
      "Paste it here (write-only) and Test runs a real search.",
      "Build the research on the REPORTS tab: a query, how many results, optionally only certain domains or published since a date.",
      "It returns the page TEXT, not just links — so the AI summary has something to read."] },
  tavily: { title: "Tavily", types: ["tavily"], fields: [],
    secretLabel: "API key (write-only, starts tvly-)",
    desc: "Search built for agents: it can hand back a written answer with its sources beside it, not only a list of results.",
    howto: ["Get a key at tavily.com → API Keys (there is a free tier).",
      "Paste it here (write-only) and Test runs a real search.",
      "On the REPORTS tab, pick a depth: basic for a fact, advanced for a question worth two credits.",
      "The answer leads and the sources sit under it, so a claim can be checked rather than taken on faith."] },
  firecrawl: { title: "Firecrawl", types: ["firecrawl"], fields: [],
    secretLabel: "API key (write-only, starts fc-)",
    desc: "Read one page as clean markdown — the nav, the cookie banner and the footer stripped out.",
    howto: ["Get a key at firecrawl.dev → Dashboard.",
      "Paste it here (write-only) and Test reads a page for real.",
      "On the REPORTS tab, give it a URL. Good for a pricing page or a changelog you want watched.",
      "For a page behind a login it will not help — that needs a real browser session, which is not an API away."] },
  reader: { title: "Jina Reader", types: ["reader"], fields: [],
    secretLabel: "API key (optional — it works without one, a key just raises the rate limit)",
    desc: "Read any public page as markdown, with no account at all. The one research source a fresh install can try immediately.",
    howto: ["Nothing to set up: leave the key blank and it works.",
      "Test reads a page for real, key or no key.",
      "Paste a key from jina.ai only if you hit the anonymous rate limit.",
      "On the REPORTS tab, give it a URL — same shape as Firecrawl, no account required."] },
  /* Files & sheets people already keep. Both cards borrow: SharePoint the Outlook card's tenant
     app (one registration, Graph mail AND Sites), Sheets the Gmail card's Google OAuth client. The
     offer appears only when there is something to borrow - `reuse.ok` reads the other card. */
  sharepoint: { title: "SharePoint", types: ["sharepoint_list", "sharepoint_file"],
    fields: [["tenant_id (blank = reuse the Outlook card's app)", "tenant_id"], ["client_id (blank = reuse the Outlook card's app)", "client_id"],
      ["default site (optional) — e.g. contoso.sharepoint.com/sites/Ops", "site"]],
    secretLabel: "client secret (write-only; blank = reuse the Outlook card's tenant app)",
    desc: "SharePoint lists and files in document libraries as scheduled reports and agent tools, over Graph — a list's items as rows, a csv/xlsx in a library parsed to rows.",
    howto: ["One app registration with the Sites.Read.All APPLICATION permission (admin-consented) is all it needs. If the Outlook card already runs on a tenant app, leave the fields blank and it is borrowed - just add Sites.Read.All to that app in Azure Portal → App registrations → API permissions → Grant admin consent.",
      "Otherwise register one: Azure Portal → App registrations → New registration; API permissions → Microsoft Graph → Application → Sites.Read.All → Grant admin consent; Certificates & secrets → New client secret. Enter tenant_id + client_id here and paste the secret (write-only).",
      "Optionally name a default site (contoso.sharepoint.com/sites/Ops). Test authenticates, reaches the root site and, with a default site, counts its lists.",
      "Build the reports on the REPORTS tab: 'SharePoint list' (a list's items) or 'SharePoint file' (a csv/xlsx in Shared Documents; a path ending in / lists the folder)."],
    agent: ["GET {base}/api/connectors{hdr} and read the outlook card's config. If it has tenant_id, client_id and a saved secret and its auth is not 'user', this card can borrow it: leave tenant_id/client_id blank, tell the owner the app needs the Sites.Read.All application permission with admin consent (their admin adds it in Azure Portal → the app → API permissions), and Test (POST {base}/api/connectors/{cid}/test{hdr}). A 403 means that permission is missing - say so, do not retry.",
      "If Outlook is a personal sign-in or absent, the owner (or their admin) registers an app with Sites.Read.All; ask for tenant_id, client_id (ConfigJson) and the client secret (Secret).",
      "Ask for a default site URL, save it as site, Test, turn the connector on, SETUP DONE - reports are built on the Reports tab."],
    reuse: { from: "outlook", title: "Reuse the Outlook card's Microsoft app",
      text: "Outlook runs on a tenant app registration already. One registration can hold mail permissions and Sites.Read.All at once — leave the app fields blank and this card uses it. Make sure Sites.Read.All (application) is granted and admin-consented on that app.",
      clear: ["tenant_id", "client_id"],
      ok: (c) => { const k = parse(c?.ConfigJson); return !!(c && c.HasSecret && k.client_id && k.auth !== "user"); } } },
  google_sheets: { title: "Google Sheets", types: ["google_sheets"],
    fields: [["Google OAuth client id (blank = reuse the Gmail card's)", "google_client_id"],
      ["Google OAuth client secret (blank = reuse the Gmail card's)", "google_client_secret"],
      ["default spreadsheet (optional) — URL or id", "spreadsheet"]],
    secretLabel: "refresh token (write-only) — minted with spreadsheets.readonly",
    desc: "A Google Sheet's cells as rows, on a schedule or as an agent tool — the first row as the column names.",
    howto: ["Google Cloud console → APIs & Services → enable the Google Sheets API (and the Google Drive API, so Test can list your sheets) → Credentials → OAuth client ID, type Desktop app. If the Gmail card already carries a Google client (its calendar fields), leave id and secret blank here and it is reused.",
      "Mint a refresh token WITH the Sheets scope: OAuth 2.0 Playground (developers.google.com/oauthplayground) → gear icon → use your own OAuth credentials → scopes https://www.googleapis.com/auth/spreadsheets.readonly and https://www.googleapis.com/auth/drive.metadata.readonly → Authorize APIs → Exchange authorization code → copy the refresh token. A token minted for the calendar does not cover spreadsheets, which is why this card holds its own.",
      "Paste the refresh token (write-only). Share the sheets you want with the Google account you authorized as. Optionally set a default spreadsheet. Test checks the token's scopes and lists a few visible spreadsheets.",
      "Build the reports on the REPORTS tab: 'Google Sheet' with a URL or id and a range (Sheet1!A:F); blank range = the first tab."],
    agent: ["GET {base}/api/connectors{hdr} and read the gmail card's config: with google_client_id and google_client_secret present, leave those blank here - they are reused. Otherwise the owner creates an OAuth client (Desktop app) in Google Cloud console; ask for id and secret and save them in ConfigJson.",
      "The refresh token is the owner's to mint in the OAuth Playground with the spreadsheets.readonly and drive.metadata.readonly scopes (walk them through: gear → own credentials → the two scopes → Authorize → Exchange → copy refresh token). Save it as Secret; never echo it.",
      "Ask which spreadsheet is the usual one, save its URL as spreadsheet, Test (POST {base}/api/connectors/{cid}/test{hdr}) - a 403 or a scope complaint means the token was minted without the Sheets scope; mint again. Turn it on, SETUP DONE."],
    reuse: { from: "gmail", title: "Reuse the Gmail card's Google client",
      text: "The Gmail card already carries a Google OAuth client id and secret (its calendar fields). Leave those blank here and they are reused — you still mint a refresh token with the Sheets scope, because the calendar one does not cover spreadsheets.",
      clear: ["google_client_id", "google_client_secret"],
      ok: (c) => { const k = parse(c?.ConfigJson); return !!(c && k.google_client_id && k.google_client_secret); } } },
  azure: { title: "Microsoft Azure", types: ["azure", "azure_blob", "azure_logs"], discovers: true,
    fields: [["tenant_id", "tenant_id"], ["client_id", "client_id"]],
    secretLabel: "client secret (write-only; blank = reuse the Outlook connector's app)",
    desc: "Blob storage, Log Analytics (KQL) — or ANY resource via ARM — as scheduled reports, Timeline feeds and agent tools, through an app registration.",
    howto: ["Reuse the app you registered for Outlook (leave everything blank) or register a new one: Azure Portal → App registrations.",
      "Grant the app RBAC roles on what you'll pull: Reader on a subscription/resource group (ARM reads), Storage Blob Data Reader (blobs), Log Analytics Reader (logs). These are IAM role assignments, not Graph API permissions.",
      "No extra installs — tokens ride the same client-credentials road the Outlook connector uses.",
      "Test & discover authenticates (naming the subscriptions the app can see — a token with no roles is called out) and then enumerates what those roles reach: every blob container and Log Analytics workspace is listed under 'What you have access to'.",
      "Each discovered object gets its own picker: report only (the default — selectable on the Reports tab, nothing polled), feed (new blobs / new query rows appear on the Timeline), tasks (they go through triage), or off.",
      "Reports tab then offers the same objects as pipelines: Azure blob (read a file or list a container), Log Analytics (any KQL), and a generic ARM read (any resource path)."],
    agent: ["GET {base}/api/connectors{hdr} and check the outlook card: if it carries a tenant app (tenant_id, client_id, a secret) this card can reuse it with everything blank. If `az` is installed, `az account show` tells you which tenant and subscription this machine is already signed into - useful to confirm ids.",
      "Otherwise the registration and its RBAC roles (Reader, Storage Blob Data Reader, Log Analytics Reader) are the owner's admin work in the Azure portal; ask for tenant_id and client_id (ConfigJson) and the client secret (Secret) once that exists.",
      "Test & discover (POST {base}/api/connectors/{cid}/test{hdr}) names the subscriptions the app can see - none means no roles yet, say so - and lists containers and workspaces. Read it back, SETUP DONE."] },
  // The knowledge base: documents people already keep, indexed INTO Taskuary's own database (SQLite
  // FTS5) and searched by reports, agents and the reply drafter. Not a vector database connector: a
  // vector store is infrastructure somebody else runs, and one owner's documents fit a ranked
  // full-text index; an embedder can be added behind the same search later (knowledge.py).
  knowledge: { title: "Knowledge base", types: ["kb_search", "kb_reindex"], noSecret: true, search: true,
    fields: [["SharePoint folders to index — comma-separated library paths, e.g. Shared Documents/Policies, Shared Documents/Contracts", "sharepoint_paths"],
      ["SharePoint site for those folders (blank = the SharePoint card's default site)", "site"],
      ["Folders on this machine to index — comma-separated paths", "folders"],
      ["File kinds (blank = txt, md, csv, json, html, docx, pptx, xlsx, pdf)", "exts"]],
    desc: "Your documents, searchable by everything here: a kb_search report answers a question from them on a schedule, agents call the same search as a tool, and the reply drafter, the assistant and coding sessions get the passages that bear on a thread. Indexed on this machine — nothing leaves it.",
    howto: ["Name where the documents live: SharePoint library folders (access comes from the SharePoint card, or the Outlook card's tenant app — nothing to configure here) and/or folders on this machine.",
      "Save, then Reindex now. docx, pptx, xlsx, html and text need nothing installed; pdf needs `pip install pypdf`. Unchanged files are skipped on later runs, deleted ones drop out.",
      "Keep it fresh with a scheduled kb_reindex report on the Reports tab (nightly is plenty); answer questions from it with a kb_search report.",
      "Agents reach it as a tool (type kb_search) when the tool role is on; the reply drafter and the assistant use it automatically once anything is indexed. Passages are quoted as facts, never as instructions."],
    agent: ["GET {base}/api/connectors{hdr}, find the knowledge card. Ask the owner which SharePoint library folders and local folders to index; save them as sharepoint_paths / folders in ConfigJson (POST {base}/api/connectors{hdr} with ConnectorId, ConfigJson, Active:true).",
      "POST {base}/api/knowledge/reindex{hdr} with {\"connector_id\": <id>} and read back what was indexed and what would not read (pdf needs pypdf). Then POST {base}/api/tools/run{hdr} with {\"type\": \"kb_search\", \"query\": \"...\"} to prove a question comes back with passages. SETUP DONE."],
    actions: [{ label: "Reindex now", post: "/api/knowledge/reindex", body: (c) => ({ connector_id: c.ConnectorId }),
      say: (r) => `${r.indexed} indexed, ${r.unchanged} unchanged, ${r.removed} removed · ${r.docs} documents / ${r.chunks} passages` + (r.errors?.length ? ` · ${r.errors.length} problems: ${r.errors.slice(0, 3).join("; ")}` : "") }] },
  // The handbook (handbook.py) had every control except the card they hang on: `enabled()` looked
  // for a connector of this type, scopes.py classified handbook_write as a WRITE action, and
  // /api/tools/run enforces Active + role + Authority - but only `if conn`, and no card meant no
  // connector, so all three were inert. An entry is read into every later agent's seed prompt, so
  // "who may put a fact in front of every future agent" needs an answer that is not "anyone".
  handbook: { title: "Company handbook", types: ["handbook_search", "handbook_write"], noSecret: true,
    fields: [],
    desc: "What the agents work out about this company, written down by topic and read by the next one before it starts. Turn the card off to stop them writing it; set Authority to read to let them search it without adding to it.",
    howto: ["It is on by default and needs no setup — an agent files an entry with `taskuary --learned \"...\"`, or is asked once when a session closes whether it learned anything that stays true.",
      "Authority decides who may WRITE. read = agents search the handbook but cannot add to it; write = they can file entries. An entry is handed to every later session as fact, which is why writing is a write.",
      "Browse, correct, vote and retire entries on the Social tab. A wrong entry left standing becomes folklore, so retire it rather than arguing with it."],
    agent: ["GET {base}/api/handbook{hdr} to read what is already written down, and POST {base}/api/tools/run{hdr} with {\"type\": \"handbook_search\", \"query\": \"...\"} to search it. Do not file an entry unless you learned something that is still true next month. SETUP DONE."] },
};

/* A question typed on the Knowledge base card, answered from the index - the same search a
   kb_search report or an agent's tool call gets, so what the card shows is what they would see. */
function KbSearch({ conn }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState(null);
  const [busy, setBusy] = useState(false);
  const go = async () => {
    if (!q.trim()) return;
    setBusy(true);
    try { setHits((await api.get("/api/knowledge/search", { params: { q, connector_id: conn.ConnectorId, limit: 6 } })).data.data || []); }
    catch { setHits([]); }
    setBusy(false);
  };
  return (
    <Box sx={{ mt: 2, maxWidth: 560 }}>
      <Typography variant="body2" sx={{ fontWeight: 700, color: INK, mb: 0.75 }}>Ask the knowledge base</Typography>
      <Box sx={{ display: "flex", gap: 1 }}>
        <TextField size="small" fullWidth placeholder="e.g. what is our resident refund policy" value={q} sx={{ bgcolor: "#fff" }}
          onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && go()} />
        <Button variant="outlined" disabled={busy || !q.trim()} onClick={go}>{busy ? <CircularProgress size={14} /> : "Search"}</Button>
      </Box>
      {hits && hits.length === 0 && <Typography variant="caption" sx={{ color: DIM, display: "block", mt: 1 }}>nothing matched — is anything indexed yet?</Typography>}
      {(hits || []).map((h) => (
        <Box key={`${h.doc_id}-${h.seq}`} sx={{ mt: 1, p: 1, border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: PANEL2 }}>
          <Typography variant="body2" sx={{ fontWeight: 600, color: INK }}>{h.name} <Typography component="span" variant="caption" sx={{ color: DIM }}>· {h.source}/{h.path} · {(h.modified || "").slice(0, 10)}</Typography></Typography>
          <Typography variant="caption" sx={{ color: DIM, display: "block", lineHeight: 1.5 }}>{h.snippet}</Typography>
        </Box>
      ))}
    </Box>
  );
}

const WINRM_HOWTO = [
  "This card is the CONNECTION only - the machine name. Build the actual reports (script + AI summary + schedule) on the REPORTS tab.",
  "A box you can RDP into (like AZWEB01) is usually domain-joined and already reachable over WinRM with your Windows login - just enter the machine name and Test.",
  "If Test fails with 'WinRM unreachable', enable PS remoting on the remote box once: open an elevated PowerShell THERE and run Enable-PSRemoting -Force.",
  "Reports then run any PowerShell you write ON that machine (read a log, query a service, export a CSV) and the output - optionally AI-summarized - lands on the Timeline.",
];
const WINRM_AGENT = [
  "Ask for the machine name. Probe it yourself from here: `Test-WSMan <host>` (and Test-NetConnection <host> -Port 5985). Reachable: save host in ConfigJson, Test (POST {base}/api/connectors/{cid}/test{hdr}), SETUP DONE.",
  "Unreachable: remoting has to be enabled ON the remote box, by someone with an admin session there - `Enable-PSRemoting -Force` in an elevated PowerShell on that machine. You cannot do that from here without remoting; ask the owner (or their admin) to run it, then probe and Test again.",
  "Runs use the Windows login Taskuary itself runs under - if Test fails with access denied, that account needs rights on the remote box; say so rather than asking for a password, the card has none.",
];

const parse = (s) => { try { return JSON.parse(s || "{}"); } catch { return {}; } };
const NL = String.fromCharCode(10);

// A card per connection. The dot is read off the status line the card already carries -
// "off", "not set up" and "connection failing" are the only three states worth a colour.
const connState = (c) => (c.planned ? "planned"
  : /failing|test failed/.test(c.desc) ? "failing"
    : /^off|not set up|no key yet/.test(c.desc) ? "off" : "on");
const connDot = (c) => ({ planned: "#cfc9bf", failing: "#6b2733", off: "#cfc9bf", on: "#55697a" })[connState(c)];
// the whole card says its state, not just the 7px dot: a live connection wears the brand
// border on a faintly tinted ground, a failing one the alert border, an unconfigured one
// stays paper - so a wall of nine cards reads at a glance which three are actually working
const CARD_STATE = {
  on:      { border: "#47654a", bg: PANEL, width: 2 },       // the deep green the Board uses for done - unmistakable at a glance
  failing: { border: "#8a3646", bg: PANEL, width: 1.5 },     // oxblood: the one loud colour, "this is on you"
  off:     { border: BORDER, bg: PANEL, width: 1 },
  planned: { border: BORDER, bg: PANEL, width: 1 },
};

// The result of a Test, and the one failure the owner can fix from here. "boto3 is not
// installed - run: pip install boto3" is a true sentence that helps nobody at a desktop app: it
// means find a terminal, work out which Python this is, come back. The server knows both, so a
// missing package comes back structured (channels.test_connector) and this offers the button.
const TestLine = ({ test, mt = 1 }) => {
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState("");
  if (!test) return null;
  const ins = test.install;
  return (
    <Box sx={{ mt }}>
      <Typography variant="body2" sx={{ fontWeight: 600, color: test.ok ? "#47654a" : "#6b2733" }}>
        {test.ok ? "✓" : "✗"} {test.detail}{test.ms != null ? ` · ${test.ms}ms` : ""}
      </Typography>
      {ins && !done && (ins.can === false
        ? <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>{ins.why}</Typography>
        : <Button size="small" variant="outlined" disabled={busy} sx={{ mt: 0.75, fontSize: 11.5, textTransform: "none" }}
            startIcon={busy ? <CircularProgress size={12} /> : null}
            onClick={async () => {
              setBusy(true);
              try {
                const { data } = await api.post("/api/deps/install", { package: ins.package });
                setDone(`✓ ${data.name} installed — press Test again`);
              } catch (e) { setDone(e?.response?.data?.detail || `could not install ${ins.name}`); }
              setBusy(false);
            }}>{busy ? `Installing ${ins.name}…` : `Install ${ins.name}`}</Button>)}
      {done && <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>{done}</Typography>}
    </Box>
  );
};

const ConnCard = ({ c }) => (
  <Box onClick={c.planned ? undefined : c.go}
    sx={{ bgcolor: CARD_STATE[connState(c)].bg, border: `${CARD_STATE[connState(c)].width}px solid ${CARD_STATE[connState(c)].border}`, borderRadius: 2.5, p: 1.6,
      opacity: c.planned ? 0.5 : connState(c) === "off" ? 0.85 : 1, cursor: c.planned ? "default" : "pointer",
      transition: "border-color .15s, box-shadow .15s",
      ...(c.planned ? {} : { "&:hover": { boxShadow: "0 2px 8px rgba(47,107,79,.12)" } }) }}>
    <Box sx={{ display: "flex", alignItems: "center", gap: 1.1 }}>
      <Box sx={{ width: 30, height: 30, borderRadius: 2, bgcolor: "#e9e3d8", flexShrink: 0,
        display: "flex", alignItems: "center", justifyContent: "center" }}>
        {c.channel === "cli" ? <TerminalIcon sx={{ fontSize: 17, color: "#55697a" }} />
          : <ChannelIcon channel={c.channel} sx={{ fontSize: 17 }} />}
      </Box>
      <Typography noWrap sx={{ color: INK, fontWeight: 700, fontSize: 13, flex: 1, minWidth: 0 }}>{c.title}</Typography>
      <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: connDot(c), flexShrink: 0 }} />
    </Box>
    <Typography sx={{ color: FAINT, fontSize: 11.5, lineHeight: 1.5, pt: 1,
      display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
      {c.desc}
    </Typography>
  </Box>
);

// The catalog's sections, named once: the rail reads them before `groups` is built (groups
// needs the loaded connectors), and they must stay in step.
const GROUP_TITLES = ["AI — agents & models", "AI — voice", "Email", "Messaging", "Developer", "Project management",
  "Databases", "Cloud & infrastructure", "Corporate systems", "Observability", "Agentic web", "Files & sheets", "Everything else"];
// planned types read as raw identifiers on a card ("sharepoint_list"), which looks unfinished
// in a way the feature is not. Named here; anything unnamed falls back to a de-underscored key.
const PLANNED_TITLES = { google_sheets: "Google Sheets", sharepoint_list: "SharePoint list",
  smb_file: "Network file share", local_file: "File on this computer", graphql: "GraphQL",
  sqlite: "SQLite", gcp: "Google Cloud", kubernetes: "Kubernetes", grafana: "Grafana",
  elastic: "Elasticsearch", perplexity: "Perplexity", serpapi: "SerpAPI", browserbase: "Browserbase",
  netsuite: "NetSuite", sap: "SAP", workday: "Workday", adp: "ADP",
  epic: "Epic (EMR)", cerner: "Oracle Cerner (EMR)", pointclickcare: "PointClickCare (EMR)" };
const KNOWN_PLANNED = [];
const PLACED = new Set(["graphql", "sqlite", "gcp", "kubernetes", "grafana", "elastic",
  "perplexity", "serpapi", "browserbase", "google_sheets", "sharepoint_list", "smb_file", "local_file",
  "netsuite", "sap", "workday", "adp", "epic", "cerner", "pointclickcare"]);

const VoiceVocabulary = ({ onBack }) => {
  const [text, setText] = useState("");
  const [limit, setLimit] = useState(100);
  const [busy, setBusy] = useState(true);
  const [saved, setSaved] = useState("");
  const [err, setErr] = useState("");
  const [onServer, setOnServer] = useState("");   // what the server holds, to know when the box has unsaved edits
  const [genBusy, setGenBusy] = useState(false);
  const [genWhat, setGenWhat] = useState("");
  const [genEv, setGenEv] = useState(null);       // the receipts: what history was read, what the model kept
  const show = (data) => { const t = (data.terms || []).join("\n"); setText(t); setOnServer(t); setLimit(data.limit || 100); };
  useEffect(() => {
    let alive = true;
    api.get("/api/voice/vocabulary").then(({ data }) => { if (alive) { show(data); setBusy(false); } })
      .catch((e) => { if (alive) { setErr(e?.response?.data?.detail || "Could not load voice vocabulary"); setBusy(false); } });
    return () => { alive = false; };
  }, []);
  // same narration as the Docs tab: poll while it runs so the button says what it is reading
  useEffect(() => {
    if (!genBusy) return undefined;
    const t = setInterval(async () => {
      try { setGenWhat((await api.get("/api/doc/generate/status")).data.what || ""); } catch { /* status is a nicety */ }
    }, 1200);
    return () => clearInterval(t);
  }, [genBusy]);
  const terms = text.split("\n").map((x) => x.trim()).filter(Boolean);
  const save = async () => {
    setBusy(true); setErr(""); setSaved("");
    try {
      const { data } = await api.put("/api/voice/vocabulary", { terms });
      show(data); setSaved(`${(data.terms || []).length} shared term${data.terms?.length === 1 ? "" : "s"} saved`);
    } catch (e) { setErr(e?.response?.data?.detail || "Could not save voice vocabulary"); }
    setBusy(false);
  };
  // history -> names, systems, acronyms (histgen.gen_vocabulary). Your edits in the box are saved
  // first so nothing typed is lost; your terms stay, the model's fill the room left.
  const generate = async () => {
    setGenBusy(true); setErr(""); setSaved(""); setGenEv(null); setGenWhat("starting…");
    try {
      if (text !== onServer) await api.put("/api/voice/vocabulary", { terms });
      const { data } = await api.post("/api/doc/vocabulary/generate");
      show((await api.get("/api/voice/vocabulary")).data); setSaved(`✓ ${data.detail}`);
      try { setGenEv((await api.get("/api/doc/generate/status")).data.evidence || null); } catch { /* receipts optional */ }
    } catch (e) { setErr(e?.response?.data?.detail || "Could not generate from history"); }
    setGenBusy(false); setGenWhat("");
  };
  return (
    <Box sx={{ maxWidth: 760, mx: "auto" }}>
      <Crumb section="Connections" onBack={onBack} title="Shared voice vocabulary" />
      <Typography variant="body2" sx={{ color: DIM, mb: 2, lineHeight: 1.7 }}>
        One list for every AI voice connector, browser mic and voice note. Add unusual names, acronyms, products and internal system terms;
        each active provider receives the same hints automatically. Hints improve recognition but never force words into a transcript.
        Generate from history reads who writes to you and what about, and adds the names a recogniser would get wrong - your own lines stay.
      </Typography>
      <Box sx={{ border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: PANEL, p: 2 }}>
        <TextField fullWidth multiline minRows={12} value={text} onChange={(e) => setText(e.target.value)} disabled={busy || genBusy}
          label="Words and phrases" placeholder={"Taskuary\nPointClickCare\nIntacct\nTQ-0243"}
          helperText={`One term or phrase per line · up to ${limit} · 50 characters and 5 words per entry`} />
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 1.5 }}>
          <Typography variant="caption" sx={{ color: terms.length > limit ? "error.main" : FAINT }}>{terms.length}/{limit}</Typography>
          <Box sx={{ flex: 1 }} />
          <Button size="small" variant="outlined" onClick={generate} disabled={busy || genBusy || terms.length > limit}
            sx={{ fontSize: 11.5, textTransform: "none" }}
            startIcon={genBusy ? <CircularProgress size={12} /> : null}
            title="Read the last three months of mail - who writes, about what - and add the names, systems and acronyms a recogniser would misspell. Your own lines stay.">
            {genBusy ? (genWhat || "Reading your mail…") : "Generate from history"}
          </Button>
          <Button variant="contained" disableElevation onClick={save} disabled={busy || genBusy || terms.length > limit || text === onServer}>
            {busy ? "Saving…" : text === onServer ? "Saved" : "Save shared vocabulary"}
          </Button>
        </Box>
        {err && <Alert severity="error" sx={{ mt: 1.5 }}>{err}</Alert>}
        {saved && <Alert severity="success" sx={{ mt: 1.5 }}>{saved}</Alert>}
        {/* the receipts: what history was read and counted, so every added name traces back to your own mail */}
        {genEv?.length > 0 && (
          <Box sx={{ mt: 1.5, p: 1.25, bgcolor: "#fff", border: `1px solid ${BORDER}`, borderRadius: 2 }}>
            <Typography variant="caption" sx={{ color: DIM, fontWeight: 600, display: "block", mb: 0.5 }}>What it read</Typography>
            {genEv.map((l, i) => (
              <Typography key={i} variant="caption" component="div" sx={{ color: l.startsWith("  ") ? FAINT : DIM, whiteSpace: "pre-wrap", fontFamily: l.startsWith("  ") ? "monospace" : "inherit", fontSize: 11 }}>{l}</Typography>
            ))}
          </Box>
        )}
      </Box>
    </Box>
  );
};

export default function ConnectorsView() {
  const [connectors, setConnectors] = useState(null);
  const [sources, setSources] = useState([]);
  const [types, setTypes] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [q, setQ] = useState("");
  const [group, setGroup] = useState(GROUP_TITLES[0]);   // which catalog section the rail has open
  const [open, setOpen] = useState(null);   // {kind:'channel',id} | {kind:'rtype',rtype,SourceId?} | {kind:'agents'}
  const [syncing, setSyncing] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const [c, s, t] = await Promise.all([api.get("/api/connectors"), api.get("/api/sources"), api.get("/api/report-types")]);
      setConnectors(c.data.data || []); setSources(s.data.data || []); setTypes(t.data.data || []);
    } catch (e) { setErr(e?.response?.data?.detail || "Failed to load connectors"); }
  }, []);
  useEffect(() => { load(); api.get("/api/mssql/drivers").then(({ data }) => setDrivers(data.data || [])).catch(() => {}); }, [load]);

  const reports = sources.filter((x) => x.Channel === "report");
  const syncNow = async () => {
    setSyncing(true);
    try { await api.post("/api/ingest/poll"); setTimeout(() => { setSyncing(false); load(); }, 3000); }
    catch { setSyncing(false); }
  };

  const allOf = (type) => (connectors || []).filter((c) => c.Type === type);
  // Explicit cards travel by ConnectorId. A type-only deep link or credential reuse picks an
  // active instance first, then the original catalog row for backward compatibility.
  const byType = Object.fromEntries([...new Set((connectors || []).map((c) => c.Type))]
    .map((type) => [type, allOf(type).find((c) => c.Active) || allOf(type)[0]]));
  // #connector=<type> opens that card on arrival - the bell's Fix button lands here, and so can any
  // link. Consumed once, so Back does not reopen it.
  useEffect(() => {
    const m = /connector=([\w-]+)/.exec(window.location.hash || "");
    if (!m || !connectors) return;
    const t = m[1];
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    const direct = /^\d+$/.test(t) ? connectors.find((c) => c.ConnectorId === Number(t)) : byType[t];
    if (direct) setOpen({ kind: "connector", id: direct.ConnectorId });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectors]);

  if (!connectors) return <CircularProgress size={22} sx={{ m: 4 }} />;

  if (open?.kind === "agents") return <AgentsPage section="Connections" title="AI CLI agents" onBack={() => setOpen(null)} />;
  if (open?.kind === "voice-vocabulary") return <VoiceVocabulary onBack={() => setOpen(null)} />;
  if (open?.kind === "connector") {
    const conn = connectors.find((c) => c.ConnectorId === open.id);
    if (!conn) return null;
    const shared = { conn, reload: load, onBack: () => setOpen(null),
      onCreated: (id) => setOpen({ kind: "connector", id }) };
    if (conn.Type === "mssql") return <MssqlDetail key={conn.ConnectorId} {...shared} drivers={drivers} />;
    if (conn.Type === "winrm") return <WinrmDetail key={conn.ConnectorId} {...shared} />;
    if (DATA_META[conn.Type]) return <DataDetail key={conn.ConnectorId} {...shared} meta={DATA_META[conn.Type]} sources={sources} byType={byType} />;
    return <ChannelDetail key={conn.ConnectorId} {...shared} sources={sources} />;
  }

  /* ── landing: searchable grouped catalog ── */
  const chanCard = (c) => {
    const m = META[c.Type] || {};
    const srcs = m.channel && m.channel !== "ai"
      ? sources.filter((s) => s.ConnectorId === c.ConnectorId) : null;   // owned, never channel-shared
    const roles = String(c.Roles || "").split(",").filter(Boolean);
    const status = `${c.Active ? "on" : "off"}`
      + (roles.length ? ` · ${roles.map((r) => r === "notify" ? "notifications" : r).join(" + ")}` : "")
      + (srcs ? ` · ${srcs.filter((s) => s.Active).length}/${srcs.length} ${(m.srcLabel || "sources").toLowerCase()}`
        : c.HasSecret ? " · key saved"
          : ["ollama", "local_whisper"].includes(c.Type) ? " · local — no key needed"
          : c.Type === "stt_server" ? " · your server — key optional" : " · no key yet")
      + (c.LastError ? " · last test failed" : c.LastSyncAt ? ` · ok ${timeAgo(c.LastSyncAt)}` : "");
    // the product's own logo wins over the channel glyph: five AI cards sharing one sparkle,
    // or Jira and Linear both wearing 'boards', tells you nothing about which is which
    return { key: `c${c.ConnectorId}`, title: c.Name, desc: status,
      channel: hasLogo(c.Type) ? c.Type : (m.channel || c.Type),
      haystack: `${c.Name} ${c.Type} ${m.desc || ""} ${(m.howto || []).join(" ")}`,
      go: () => setOpen({ kind: "connector", id: c.ConnectorId }) };
  };
  // three shapes of card, said once instead of inline in five groups
  const dataDesc = (c, rtype) => (c?.LastError ? "connection failing" : c?.LastSyncAt ? "connection ✓" : "not set up")
    + ` · ${reports.filter((s2) => (parse(s2.ConfigJson).type || "rest") === rtype).length} reports (built on the Reports tab)`;
  const dataCards = (keys) => keys.flatMap((t) => allOf(t).filter(() => DATA_META[t]).map((c) => {
    const dm = DATA_META[t];
    return { key: `d${c.ConnectorId}`, title: c.Name, channel: t,
      desc: (c.LastError ? "connection failing" : c.LastSyncAt ? "connection ✓" : "not set up")
        + ` · ${reports.filter((s2) => dm.types.includes(parse(s2.ConfigJson).type)).length} reports (built on the Reports tab)`,
      haystack: `${dm.title} ${t} ${dm.desc} ${dm.types.join(" ")} ` + dm.howto.join(" "),
      go: () => setOpen({ kind: "connector", id: c.ConnectorId }) };
  }));
  const channelCards = (keys) => keys.flatMap((t) => allOf(t).map(chanCard));
  const specialCards = (type, title, rtype, haystack) => allOf(type).map((c) => ({
    key: `s${c.ConnectorId}`, title: c.Name || title, channel: type,
    desc: dataDesc(c, rtype), haystack,
    go: () => setOpen({ kind: "connector", id: c.ConnectorId }),
  }));
  const planned = types.filter((t) => t.status === "planned").map((t) => t.type);
  // `rest` catches whatever the server starts advertising that this file has not been taught
  // about yet, so a new planned type never silently vanishes from the catalog
  const plannedCards = (keys, rest = false) => (rest ? planned.filter((t) => !PLACED.has(t)) : keys.filter((t) => planned.includes(t)))
    .map((t) => ({ key: `p${t}`, title: PLANNED_TITLES[t] || t.replace(/_/g, " "), desc: "planned",
      channel: t, haystack: `${t} planned`, planned: true }));
  const catalogCards = (category) => plannedFor(category).map((c) => ({
    key: `catalog-${c.type}`, title: c.title, desc: `planned — ${c.desc}`, channel: c.type,
    haystack: `${c.type} ${c.title} ${c.desc} planned`, planned: true,
  }));

  const groups = [
    { title: "AI — agents & models", cards: [
      { key: "agents", title: "AI CLI agents", desc: "claude / codex / gemini — bring your own coding CLI, resumable sessions",
        channel: "cli", haystack: "ai cli agents claude codex gemini command args resume", go: () => setOpen({ kind: "agents" }) },
      ...channelCards(["anthropic", "openai", "azure_openai", "openrouter", "ollama"]),
      ...catalogCards("AI — agents & models"),
    ]},
    // speech to text: voice notes on the chat channels arrive as text, and the prompt boxes get a mic
    { title: "AI — voice",
      // what happens with NO card here is not visible anywhere else, and it looked like something was missing
      note: "Without a card here: the mic buttons still work through your browser's own recognition (Edge and Chrome ship one — free, live microphone only), and voice notes on WhatsApp/Telegram land marked not transcribed, with a Transcribe button for later. A card is what transcribes a voice-note file on the server. Free choices: Groq (free tier) or Local Whisper (no key, on this machine). Edge's voices are text-to-speech — the other direction.",
      cards: [
        { key: "voice-vocabulary", title: "Shared voice vocabulary", channel: "ai",
          desc: "one system-wide list used by every voice connector and mic",
          haystack: "custom shared voice vocabulary words phrases domain names acronyms",
          go: () => setOpen({ kind: "voice-vocabulary" }) },
        ...channelCards(["gemini_stt", "groq_stt", "openai_stt", "deepgram", "elevenlabs_stt", "stt_server", "local_whisper"]),
        ...catalogCards("AI — voice"),
      ] },
    // mail and chat are different jobs: one group held nine cards and read as a wall
    { title: "Email", cards: [...channelCards(["outlook", "gmail", "imap"]), ...catalogCards("Email")] },
    { title: "Messaging", cards: [...channelCards(["teams", "slack", "telegram", "whatsapp", "imessage", "discord"]), ...catalogCards("Messaging")] },
    { title: "Developer", cards: [...channelCards(["github", "gitlab", "azdo", "sentry", "pagerduty"]), ...catalogCards("Developer")] },
    { title: "Project management", cards: [...channelCards(["jira", "asana", "monday", "clickup", "todoist", "linear", "trello", "notion"]), ...catalogCards("Project management")] },
    /* One "Data connections" bucket held eleven cards that have nothing to do with each
       other - a SQL server, a log store and a web-search API are three different jobs, and a
       rail entry saying "11" tells you nothing about which one you came for. Split by what
       the thing IS, and the planned cards land in the group they will belong to rather than
       all together at the bottom. */
    { title: "Databases", cards: [
      ...specialCards("mssql", "Microsoft SQL Server", "mssql",
        "microsoft sql server mssql connection windows auth " + MSSQL_HOWTO.join(" ")),
      ...dataCards(["database"]), ...plannedCards(["graphql", "sqlite"]), ...catalogCards("Databases"),
    ]},
    { title: "Cloud & infrastructure", cards: [
      ...dataCards(["aws", "azure"]),
      ...specialCards("winrm", "Remote Windows (WinRM)", "winrm",
        "remote windows winrm rdp powershell remoting azweb01 " + WINRM_HOWTO.join(" ")),
      ...catalogCards("Cloud & infrastructure"),
    ]},
    { title: "Corporate systems", cards: [
      ...dataCards(["intacct", "quickbooks", "teller"]),
      ...catalogCards("Corporate systems"),
    ]},
    { title: "Observability", cards: [...dataCards(["prometheus", "datadog"]), ...catalogCards("Observability")] },
    // the web as a source: one REST call and a key each. What is deliberately NOT here is
    // anything that drives a browser - logging in, clicking - which needs CDP, not an API.
    { title: "Agentic web", cards: [...dataCards(["exa", "tavily", "firecrawl", "reader"]), ...catalogCards("Agentic web")] },
    { title: "Files & sheets", cards: [...dataCards(["knowledge", "sharepoint", "google_sheets"]), ...catalogCards("Files & sheets")] },
    { title: "Everything else", cards: [...catalogCards("Everything else"), ...plannedCards(KNOWN_PLANNED, true)] },
  ];
  const hits = q ? groups.flatMap((g) => g.cards.filter((c) => c.haystack.toLowerCase().includes(q.toLowerCase()))
    .map((c) => ({ ...c, crumb: g.title }))) : [];

  const shown = groups.find((g) => g.title === group) || groups[0];

  return (
    <SideRail title="Connections" q={q} setQ={setQ}
      placeholder="Search connectors…"
      items={groups.map((g) => ({ key: g.title, label: g.title, n: g.cards.length || null }))}
      value={group} onChange={setGroup}
      note="Keys and connection settings are stored locally, in the same SQLite file as your tasks.">
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1.5 }}>{err}</Alert>}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 2 }}>
        <Typography sx={{ color: INK, fontWeight: 800, fontSize: 15, flex: 1, minWidth: 0 }} noWrap>
          {q ? `Matches for “${q}”` : shown.title}
        </Typography>
        <Button size="small" variant="contained" disableElevation onClick={syncNow} disabled={syncing}
          startIcon={syncing ? <CircularProgress size={12} sx={{ color: "#fff" }} /> : <SyncIcon sx={{ fontSize: 15 }} />}>
          {syncing ? "Syncing…" : "Sync now"}
        </Button>
      </Box>

      {q ? (
        <Box>
          {!hits.length ? <Empty>Nothing matches “{q}”. Try a product, channel, or connection name.</Empty> : (
            <>
              <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 1 }}>
                {hits.length} {hits.length === 1 ? "result" : "results"}
              </Typography>
              <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", sm: "repeat(2, minmax(0, 1fr))", xl: "repeat(3, minmax(0, 1fr))" }, gap: 1.5 }}>
                {hits.map((r) => <ConnCard key={r.key} c={r} />)}
              </Box>
            </>
          )}
        </Box>
      ) : (
        <>
          {shown.note && (
            <Typography variant="body2" sx={{ color: DIM, mb: 1.5, maxWidth: 860, lineHeight: 1.55 }}>{shown.note}</Typography>
          )}
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", sm: "repeat(2, minmax(0, 1fr))", xl: "repeat(3, minmax(0, 1fr))" }, gap: 1.5 }}>
            {shown.cards.map((c) => <ConnCard key={c.key} c={c} />)}
          </Box>
        </>
      )}
    </SideRail>
  );
}

/* Every catalog card is an instance. Its name is the human-facing identity used everywhere
   Taskuary lists it; Add another creates a clean instance of the same connector type. */
function ConnectorIdentity({ conn, reload, onCreated }) {
  const [name, setName] = useState(conn.Name || "");
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => setName(conn.Name || ""), [conn.Name]);
  const rename = async () => {
    const value = name.trim();
    if (!value || value === conn.Name) return;
    setBusy("rename"); setErr("");
    try { await api.post("/api/connectors", { ConnectorId: conn.ConnectorId, Name: value }); await reload(); }
    catch (e) { setErr(e?.response?.data?.detail || "could not rename the connector"); }
    setBusy("");
  };
  const add = async () => {
    const value = newName.trim();
    if (!value) return;
    setBusy("add"); setErr("");
    try {
      const { data } = await api.post("/api/connectors", { Type: conn.Type, Name: value });
      await reload(); onCreated?.(data.connectorId);
    } catch (e) { setErr(e?.response?.data?.detail || "could not add the connector"); }
    setBusy("");
  };
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mb: 1.5, maxWidth: 720 }}>
      <TextField size="small" label="Connection name" value={name} onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") rename(); }} sx={{ bgcolor: "#fff", minWidth: 240 }} />
      <Button size="small" variant="outlined" disabled={busy === "rename" || !name.trim() || name.trim() === conn.Name}
        onClick={rename}>{busy === "rename" ? "Saving…" : "Save name"}</Button>
      {!adding ? (
        <Button size="small" startIcon={<AddIcon sx={{ fontSize: 14 }} />} onClick={() => setAdding(true)}>Add another</Button>
      ) : (
        <>
          <TextField size="small" autoFocus label={`New ${conn.Type} connection name`} value={newName}
            onChange={(e) => setNewName(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") add(); }}
            sx={{ bgcolor: "#fff", minWidth: 240 }} />
          <Button size="small" variant="contained" disableElevation disabled={busy === "add" || !newName.trim()}
            onClick={add}>{busy === "add" ? "Adding…" : "Add"}</Button>
          <Button size="small" onClick={() => { setAdding(false); setNewName(""); setErr(""); }}>Cancel</Button>
        </>
      )}
      {err && <Alert severity="error" sx={{ width: "100%", py: 0 }}>{err}</Alert>}
    </Box>
  );
}

/* ── "Remove connection" on every detail page: wipes creds/config, turns sources off ── */
/* The second door to a playbook (docs/beyond-code.md): the card is where you look for "what does
   this thing do for us", so it lists every playbook whose `uses:` line names this connection, and
   opens each on the Docs tab (#playbook=<slug>), where the words are edited. */
function CardPlaybooks({ type }) {
  const [books, setBooks] = useState(null);
  useEffect(() => {
    let live = true;
    api.get("/api/playbooks").then(({ data }) => { if (live) setBooks((data.data || []).filter((b) => (b.uses || []).includes(type))); })
      .catch(() => { if (live) setBooks([]); });
    return () => { live = false; };
  }, [type]);
  if (!books) return null;
  const go = (slug) => { window.location.hash = `playbook=${slug}`; };
  return (
    <Box sx={{ mt: 3, p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: PANEL }}>
      <Typography variant="caption" sx={{ color: "#6f8a6e", fontWeight: 700, letterSpacing: 1, display: "block", mb: 0.75 }}>
        PLAYBOOKS — WHAT THIS CONNECTION DOES FOR US
      </Typography>
      {books.length === 0 && (
        <Typography variant="body2" sx={{ color: DIM, mb: 1 }}>
          No playbook names this connection yet. One is drafted for you the first time an agent finishes a job with it; approve it in Review and the next such job runs on it.
        </Typography>
      )}
      {books.map((b) => (
        <Box key={b.slug} onClick={() => go(b.slug)} sx={{ display: "flex", alignItems: "baseline", gap: 1, py: 0.5, cursor: "pointer",
          "&:hover .pb-t": { textDecoration: "underline" } }}>
          <Typography className="pb-t" variant="body2" sx={{ color: INK, fontWeight: 600, whiteSpace: "nowrap" }}>{b.title}</Typography>
          <Typography variant="caption" sx={{ color: FAINT }} noWrap>when: {b.when}</Typography>
        </Box>
      ))}
      <Button size="small" variant="text" startIcon={<AddIcon sx={{ fontSize: 15 }} />} onClick={() => go(`new:${type}`)} sx={{ mt: 0.5 }}>
        New playbook for this connection
      </Button>
    </Box>
  );
}

function RemoveConnection({ conn, reload, onBack }) {
  const [confirm, setConfirm] = useState(false);
  const remove = async () => {
    await api.post(`/api/connectors/${conn.ConnectorId}/reset`);
    reload(); onBack();
  };
  // this one already asked, as a row that swapped itself for a "Sure?" - which is a different
  // shape of question from every other delete in the app. Same dialog as the rest now.
  return (
    <Box sx={{ mt: 3, pt: 1.5, borderTop: `1px solid ${BORDER}`, display: "flex", gap: 1, alignItems: "center", maxWidth: 720 }}>
      <Button size="small" startIcon={<DeleteOutlineIcon sx={{ fontSize: 15 }} />} sx={{ color: "#867f74" }}
        onClick={() => setConfirm(true)}>Remove connection</Button>
      <ConfirmDelete open={confirm} what={`the ${conn.Name || conn.Type} connection`} confirmLabel="Remove"
        consequence="Its saved credentials and settings are wiped and its sources are switched off. The card stays in the catalog, so you can set it up again from scratch."
        onClose={() => setConfirm(false)} onConfirm={remove} />
    </Box>
  );
}

/* ── Apple Messages: the two macOS permissions, as a walkthrough instead of a paragraph ──
   Both belong to macOS. Taskuary cannot grant either; what it can do is say which one is
   missing, which process macOS will list (the app Taskuary was launched from, or the python
   binary), open the right pane, and test the real operation afterwards - a checkbox in
   Settings is not proof, a SELECT on the database is. Sending is probed separately and only
   on request, because the probe is what makes macOS pop the consent prompt. */
function MacPermissions({ conn, test, busy, runTest }) {
  const [probe, setProbe] = useState(null);
  const [probing, setProbing] = useState(false);
  const [opened, setOpened] = useState("");
  const [openErr, setOpenErr] = useState({});      // per pane - a refused link under its own card
  // the host macOS lists comes back on a failed read test, a successful one, or a denied
  // probe - whichever answered last knows it
  const setup = test?.setup || probe?.setup || {};
  const code = test ? (test.ok ? "ready" : setup.code || "error") : null;
  const openPane = async (pane) => {
    setOpened(""); setOpenErr((o) => ({ ...o, [pane]: "" }));
    try {
      const { data } = await api.post("/api/platform/macos/open-settings", { pane });
      if (data?.ok) setOpened(pane); else setOpenErr((o) => ({ ...o, [pane]: data?.detail || "Settings did not open" }));
    } catch (e) { setOpenErr((o) => ({ ...o, [pane]: e?.response?.data?.detail || "Settings did not open" })); }
  };
  const runProbe = async () => {
    setProbing(true); setProbe(null); setOpenErr((o) => ({ ...o, automation: "" }));
    try { const { data } = await api.post("/api/platform/macos/probe", { what: "messages_automation" }); setProbe(data); }
    catch (e) { setProbe({ ok: false, detail: e?.response?.data?.detail || "probe call failed" }); }
    setProbing(false);
  };
  const copy = (s) => { try { navigator.clipboard.writeText(s); } catch { /* not in this context */ } };
  const host = setup.host_name || (setup.host_path ? "the Python executable" : "the process running Taskuary");
  const notMac = code === "macos_required";
  const readOk = code === "ready";
  const readNeeds = code === "full_disk_access_required";
  // only a consent failure is fixed in the Full Disk Access pane; a missing database, a locked
  // one, an unknown schema or an old macOS are not, and the button would send people to the
  // wrong place
  const fdaPane = !test || readOk || readNeeds;
  const sendOk = !!probe?.ok;
  const sendDenied = probe && !probe.ok && probe.setup?.code === "automation_denied";
  const Card = ({ title, sub: subtitle, ok, children }) => (
    <Box sx={{ border: `1px solid ${BORDER}`, borderRadius: 1.5, p: 1.5, bgcolor: PANEL2, flex: 1, minWidth: 280 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
        <StatusDot ok={!!ok} />
        <Typography sx={{ fontWeight: 700, fontSize: 13.5, color: INK }}>{title}</Typography>
        <Typography variant="caption" sx={{ color: FAINT }}>{subtitle}</Typography>
      </Box>
      {children}
    </Box>
  );
  return (
    <Box sx={{ mt: 1, maxWidth: 760 }}>
      <Typography variant="body2" sx={{ color: DIM, mb: 1.5 }}>
        Apple Messages stays on this Mac. Reading the history macOS already keeps needs <b>Full Disk Access</b>;
        asking Messages.app to send a reply needs <b>Automation</b>. macOS controls both — Taskuary cannot grant or
        bypass them, and both are granted to <b>{host}</b>, not to "Taskuary".
      </Typography>
      {notMac ? (
        <Typography variant="body2" sx={{ color: "#6b2733", fontWeight: 600 }}>✗ {test.detail}</Typography>
      ) : (
        <Box sx={{ display: "flex", gap: 1.5, flexWrap: "wrap" }}>
          <Card title="Read Messages" sub="Full Disk Access" ok={readOk}>
            <Typography variant="caption" sx={{ color: DIM, display: "block", mb: 1 }}>
              Opens the local Messages database read-only so new messages and context can enter Taskuary.
            </Typography>
            {(setup.host_name || setup.host_path) && (
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 1 }}>
                <Typography variant="caption" sx={{ color: FAINT }}>grant to:</Typography>
                <Typography sx={{ ...mono, fontSize: 12, color: INK }} noWrap>{setup.host_name || setup.host_path}</Typography>
                {setup.host_path && <IconButton size="small" onClick={() => copy(setup.host_path)} title="copy path"><ContentCopyIcon sx={{ fontSize: 13 }} /></IconButton>}
              </Box>
            )}
            <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", alignItems: "center" }}>
              {fdaPane && <Button size="small" variant="outlined" startIcon={<OpenInNewIcon sx={{ fontSize: 13 }} />} onClick={() => openPane("full_disk_access")}>
                Open Full Disk Access</Button>}
              <Button size="small" variant="contained" disableElevation disabled={busy === "test"} onClick={() => { setOpenErr((o) => ({ ...o, full_disk_access: "" })); runTest(); }}
                startIcon={busy === "test" ? <CircularProgress size={11} sx={{ color: "#fff" }} /> : <BoltIcon sx={{ fontSize: 14 }} />}>
                {!test ? "Test" : readNeeds ? "I enabled it — test again" : "Test again"}</Button>
            </Box>
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.75 }}>
              {fdaPane ? (setup.breadcrumb || "System Settings → Privacy & Security → Full Disk Access") : "not a permission problem - see the message below"}
              {readNeeds && setup.restart_may_be_required && " · macOS may only apply it after the host is quit and relaunched"}
              {opened === "full_disk_access" && " · Settings opened"}
              {openErr.full_disk_access && ` · ${openErr.full_disk_access}`}
            </Typography>
            <TestLine test={test} mt={1} />
            {!test && conn.LastError && <Typography variant="body2" sx={{ mt: 1, color: "#6b2733" }}>✗ {conn.LastError}</Typography>}
          </Card>
          <Card title="Send Messages" sub="Automation: Messages" ok={sendOk}>
            <Typography variant="caption" sx={{ color: DIM, display: "block", mb: 1 }}>
              Lets Taskuary ask Messages.app to send a reply. Testing this makes macOS ask whether {host} may control
              Messages — allow it. <b>The test sends nothing.</b> Skip it and macOS asks on the first real reply instead.
            </Typography>
            <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", alignItems: "center" }}>
              <Button size="small" variant="contained" disableElevation disabled={probing} onClick={runProbe}
                startIcon={probing ? <CircularProgress size={11} sx={{ color: "#fff" }} /> : <BoltIcon sx={{ fontSize: 14 }} />}>
                {probe ? "Test again" : "Test Automation"}</Button>
              {sendDenied && <Button size="small" variant="outlined" startIcon={<OpenInNewIcon sx={{ fontSize: 13 }} />} onClick={() => openPane("automation")}>
                Open Automation settings</Button>}
            </Box>
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.75 }}>
              System Settings → Privacy & Security → Automation → {host} → Messages
              {opened === "automation" && " · Settings opened"}
              {openErr.automation && ` · ${openErr.automation}`}
            </Typography>
            {probe && <Typography variant="body2" sx={{ mt: 1, fontWeight: 600, color: probe.ok ? "#47654a" : "#6b2733" }}>
              {probe.ok ? "✓" : "✗"} {probe.detail}</Typography>}
          </Card>
        </Box>
      )}
    </Box>
  );
}

/* ── channel / AI connector detail: setup wizard + sources ─────────────── */
function ChannelDetail({ conn, sources, reload, onBack, onCreated }) {
  const m = META[conn.Type] || { fields: [], howto: [] };
  const isAI = m.channel === "ai";
  const [tab, setTab] = useState("Setup");
  const [step, setStep] = useState(conn.HasSecret ? (conn.LastSyncAt ? 2 : 1) : 0);
  const [cfg, setCfg] = useState(parse(conn.ConfigJson));
  const [secret, setSecret] = useState("");
  const [newSrc, setNewSrc] = useState("");
  const [test, setTest] = useState(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");

  const mine = sources.filter((s) => s.ConnectorId === conn.ConnectorId);   // owned, never channel-shared

  const saveCreds = async () => {
    setBusy("save"); setMsg("");
    try {
      const body = { ConnectorId: conn.ConnectorId, ConfigJson: JSON.stringify(cfg) };
      if (secret) body.Secret = secret;
      const { data } = await api.post("/api/connectors", body);
      setMsg("saved ✓");
      if (data.discovery) {
        const d = data.discovery;
        setTest(d.error ? { ok: false, detail: d.error }
          : { ok: true, detail: `authenticated as ${d.login} · ${d.repos} repos discovered · ${d.added} sources added · repo map written to SOUL.md` });
      }
      setSecret(""); setStep(1); reload();
    } catch (e) { setMsg(""); setTest({ ok: false, detail: e?.response?.data?.detail || "save failed" }); }
    setBusy("");
  };
  const runTest = async () => {
    setBusy("test");
    try {
      const { data } = await api.post(`/api/connectors/${conn.ConnectorId}/test`);
      setTest(data);
      // Apple Messages has a second card (Automation) on this step - a passing read test must
      // not whisk the step away before the person can try the send probe
      if (data.ok && conn.Type !== "imessage") setStep(m.srcLabel ? 2 : 3);
    } catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "test call failed" }); }
    setBusy(""); reload();
  };
  const addSource = async () => {
    if (!newSrc.trim()) return;
    await api.post("/api/sources", { Channel: m.channel, Address: newSrc.trim(), ConnectorId: conn.ConnectorId, Active: true });
    setNewSrc(""); reload();
  };
  // the telegram flow says "hit Sync now" - so the button has to BE here, not on another tab
  const [srcSync, setSrcSync] = useState(false);
  // the Outlook card leads with the sign-in; the tenant-app fields (an admin's road) fold
  // away unless they are already what this card runs on
  const [adminFields, setAdminFields] = useState(conn.Type !== "outlook" || (!!cfg.client_id && cfg.auth !== "user"));
  const syncHere = async () => {
    setSrcSync(true);
    try { await api.post("/api/ingest/poll"); setTimeout(() => { setSrcSync(false); reload(); }, 3000); }
    catch { setSrcSync(false); }
  };
  const toggleSource = async (s) => { await api.post("/api/sources", { SourceId: s.SourceId, Active: !s.Active }); reload(); };
  const [delSrc, setDelSrc] = useState(null);      // a source being removed for good - off was the only option before
  const setActive = async (on) => { await api.post("/api/connectors", { ConnectorId: conn.ConnectorId, Active: on }); reload(); };

  const steps = [
    { label: "Credentials", done: !!conn.HasSecret || !m.secretLabel, body: (
      <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, maxWidth: 460, mt: 1 }}>
        {conn.Type === "outlook" && !adminFields && (
          <Button size="small" variant="text" onClick={() => setAdminFields(true)}
            sx={{ alignSelf: "flex-start", fontSize: 12, color: DIM, px: 0.5 }}>
            Admin? Use a tenant app registration instead →
          </Button>
        )}
        {conn.Type === "imap" && /@(outlook|hotmail|live|msn)\.|office365|outlook\.office/i.test(`${cfg.address || ""} ${cfg.imap_host || ""}`) && (
          <Typography variant="body2" sx={{ color: "#6b2733", fontWeight: 600 }}>
            Microsoft mailboxes no longer accept IMAP passwords — use the Outlook connector and “Sign in with Microsoft”.
          </Typography>
        )}
        {adminFields && (
          <>
            {m.fields.map(([label, key, ph, helper]) => (
              <TextField key={key} label={label} placeholder={ph || ""} value={cfg[key] || ""} sx={{ bgcolor: "#fff" }}
                helperText={helper} onChange={(e) => setCfg({ ...cfg, [key]: e.target.value })} />
            ))}
            {/* WhatsApp has no secret at all - the bridge holds the pairing, not us */}
            {m.secretLabel && (
              <TextField label={conn.HasSecret ? `${m.secretLabel} (saved — type to replace)` : m.secretLabel} type="password"
                value={secret} onChange={(e) => setSecret(e.target.value)} sx={{ bgcolor: "#fff" }}
                helperText="Write-only: stored server-side, never returned to the browser." />
            )}
            <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
              <Button variant="contained" disableElevation disabled={busy === "save"} onClick={saveCreds}>
                {busy === "save" ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : "Save & continue"}</Button>
              {msg && <Typography variant="body2" sx={{ color: "#47654a", fontWeight: 600 }}>{msg}</Typography>}
            </Box>
          </>
        )}
      </Box>
    )},
    { label: "Test", done: !!conn.LastSyncAt && !conn.LastError, body: conn.Type === "imessage" ? (
      <MacPermissions conn={conn} test={test} busy={busy} runTest={runTest} />
    ) : (
      <Box sx={{ mt: 1 }}>
        <Typography variant="body2" sx={{ color: DIM, mb: 1 }}>Live probe — token / model / channel read, for real.</Typography>
        <Button variant="contained" disableElevation disabled={busy === "test"} onClick={runTest}
          startIcon={busy === "test" ? <CircularProgress size={12} sx={{ color: "#fff" }} /> : <BoltIcon sx={{ fontSize: 15 }} />}>Test</Button>
        <TestLine test={test} mt={1} />
        {!test && conn.LastError && <Typography variant="body2" sx={{ mt: 1, color: "#6b2733" }}>✗ {conn.LastError}</Typography>}
      </Box>
    )},
    ...(m.srcLabel ? [{ label: m.srcLabel, done: mine.some((s) => s.Active), body: (
      <Box sx={{ mt: 1 }}>
        {conn.Type === "github" && (
          <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.5 }}>
            The repos this connection reaches — discovery fills the list from the PAT. What each
            repo's issues and PRs <b>do</b> (become tasks, show as feed, stay ignored) is decided in
            one place: the <b>Inbound — what becomes work</b> step below.
          </Typography>
        )}
        {conn.Type === "whatsapp" && <WaChats conn={conn} mine={mine} reload={reload} />}
        {conn.Type === "telegram" && (
          <>
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 1, maxWidth: 560 }}>
              No chat id to type: <b>message your bot</b> (or add it to a group), hit <b>Sync now</b>, and the
              chat appears below with its id — switched off. Flip on the chats that are yours; every other
              chat stays out, because a public bot can be messaged by anyone. The field at the bottom is only
              for an id you already know.
            </Typography>
            <Button size="small" variant="outlined" onClick={syncHere} disabled={srcSync} sx={{ mb: 1 }}
              startIcon={srcSync ? <CircularProgress size={11} /> : <SyncIcon sx={{ fontSize: 14 }} />}>
              {srcSync ? "Syncing…" : "Sync now — pull in chats that messaged the bot"}
            </Button>
          </>
        )}
        {mine.filter((s) => !(conn.Type === "telegram" && s.Address === "*")).map((s) => (
          <Box key={s.SourceId} sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1, borderBottom: `1px solid ${BORDER}`, flexWrap: "wrap" }}>
            <StatusDot ok={!!s.Active} />
            <Typography sx={{ ...mono, color: INK, fontSize: 13 }} noWrap>{s.Address}</Typography>
            {conn.Type === "outlook" && <MailFolders conn={conn} s={s} reload={reload} />}
            {String(s.Owner || "").startsWith("discovered:") && (
              <Typography variant="caption" sx={{ color: FAINT }} noWrap>
                {s.Owner.replace("discovered:", "").trim()}
              </Typography>
            )}
            <Box sx={{ flex: 1 }} />
            {s.LastPolledAt && <Typography variant="caption" sx={{ color: FAINT }}>polled {timeAgo(s.LastPolledAt)}</Typography>}
            <Switch checked={!!s.Active} onChange={() => toggleSource(s)} />
            <IconButton size="small" title="Remove it for good (off keeps it listed)" onClick={() => setDelSrc(s)}>
              <DeleteOutlineIcon sx={{ fontSize: 16, color: "#867f74" }} />
            </IconButton>
          </Box>
        ))}
        <ConfirmDelete open={!!delSrc} what={delSrc ? `"${delSrc.Address}"` : ""} confirmLabel="Remove"
          consequence="It is removed from this connection - nothing from it comes in until you add it again. What already arrived stays on the Timeline."
          onClose={() => setDelSrc(null)} onConfirm={async () => { await api.delete(`/api/sources/${delSrc.SourceId}`); reload(); }} />
        <Box sx={{ display: "flex", gap: 1, mt: 1.5, maxWidth: 460 }}>
          <TextField fullWidth placeholder={m.srcPh} value={newSrc} sx={{ bgcolor: "#fff" }}
            onChange={(e) => setNewSrc(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addSource()} />
          <Button variant="contained" disableElevation onClick={addSource}>Add</Button>
        </Box>
      </Box>
    )}] : []),
    ...(isAI ? [] : [
      { label: "Inbound — what becomes work", done: inboundDone(conn, mine),
        body: <InboundStep conn={conn} m={m} mine={mine} reload={reload} /> },
      { label: CAN_NOTIFY.has(conn.Type) ? "More roles — reports, agents, notifications" : "More roles — reports, agents", done: true,
        body: <RoleStep conn={conn} reload={reload}
          only={CAN_NOTIFY.has(conn.Type) ? ["report", "tool", "notify"] : ["report", "tool"]} /> },
    ]),
    ...(conn.Type === "github" ? [{ label: "Agent permissions", done: true, body: <GithubPerms conn={conn} reload={reload} /> }] : []),
    { label: "Enable", done: !!conn.Active, body: (
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mt: 1, flexWrap: "wrap" }}>
        <Switch checked={!!conn.Active} onChange={(e) => setActive(e.target.checked)} />
        <Typography variant="body2" sx={{ color: DIM }}>
          {conn.Active
            ? (isAI ? "On — wired into intent triage (the first active AI connector wins)." : "On — polling on schedule and via Sync now.")
            : "Off — flip on once Test passes."}
        </Typography>
        {/* the last step of a setup should be the first sync - not a wait for the ten-minute clock */}
        {conn.Active && !isAI && (
          <Button size="small" variant="contained" disableElevation onClick={syncHere} disabled={srcSync}
            startIcon={srcSync ? <CircularProgress size={11} sx={{ color: "#fff" }} /> : <SyncIcon sx={{ fontSize: 14 }} />}
            sx={{ background: "linear-gradient(90deg, #55697a, #7d9a7c)" }}>{srcSync ? "Syncing…" : "Sync now — see it on the Timeline"}</Button>
        )}
      </Box>
    )},
  ];

  return (
    <Box sx={{ maxWidth: 980, mx: "auto" }}>
      <Crumb section="Connections" onBack={onBack} title={conn.Name} />
      <ConnectorIdentity conn={conn} reload={reload} onCreated={onCreated} />
      {/* WhatsApp has no agent box: there is nothing for an agent to do that the pairing box does not do
          itself (install Node is the owner's; the bridge starts on its own; the QR is scanned from a phone).
          An agent handed this setup sat on the bridge process for five minutes on a tester's machine. */}
      {conn.Type !== "whatsapp" && <AiSetup conn={conn} steps={m.howto || []} fields={m.fields || []} secretLabel={m.secretLabel} agentSteps={m.agent || []} reload={reload} />}
      {/* the sign-in lives at the TOP of the card, not inside the Credentials step: a card that already
          runs on a tenant app opens on Sources, and the one button most people need was folded away */}
      {conn.Type === "outlook" && <Box sx={{ mb: 2 }}><MsSignIn conn={conn} cfg={cfg} reload={reload} onSignedIn={() => setStep(m.srcLabel ? 2 : 3)} /></Box>}
      {conn.Type === "whatsapp" && <Box sx={{ mb: 2 }}><WaPair conn={conn} reload={reload} /></Box>}
      <Typography variant="body2" sx={{ color: DIM, mb: 1.5 }}>{m.desc}</Typography>
      <UnderTabs tabs={conn.Type === "whatsapp" ? ["Setup", "Guide"] : ["Setup", "Guide", "Agent"]} value={tab} onChange={setTab} />
      {tab === "Agent" && <AgentTab steps={m.agent} />}
      {tab === "Setup" && (
        <Stepper nonLinear activeStep={step} orientation="vertical" sx={{ "& .MuiStepLabel-label": { fontSize: 13.5, fontWeight: 600 } }}>
          {steps.map((s, i) => (
            <Step key={s.label} completed={s.done}>
              <StepButton onClick={() => setStep(i)}>{s.label}</StepButton>
              <StepContent>{s.body}</StepContent>
            </Step>
          ))}
        </Stepper>
      )}
      {tab === "Guide" && <Steps steps={m.howto || []} />}
      <CardPlaybooks type={conn.Type} />
      <RemoveConnection conn={conn} reload={reload} onBack={onBack} />
    </Box>
  );
}

/* ── SQL Server detail: connection wizard + guide (reports live on the Reports tab) ── */
function MssqlDetail({ conn, drivers, reload, onBack, onCreated }) {
  const [tab, setTab] = useState("Connection");
  if (!conn) return null;
  return (
    <Box sx={{ maxWidth: 980, mx: "auto" }}>
      <Crumb section="Connections" onBack={onBack} title={conn.Name} />
      <ConnectorIdentity conn={conn} reload={reload} onCreated={onCreated} />
      <AiSetup conn={conn} steps={MSSQL_HOWTO} agentSteps={MSSQL_AGENT} reload={reload} />
      <Typography variant="body2" sx={{ color: DIM, mb: 1.5 }}>
        The connection only — build the scheduled reports (query + AI summary) on the Reports tab.
      </Typography>
      <UnderTabs tabs={["Connection", "Guide", "Agent"]} value={tab} onChange={setTab} />
      {tab === "Agent" && <AgentTab steps={MSSQL_AGENT} />}
      {tab === "Connection" && <MssqlConnection conn={conn} drivers={drivers} reload={reload} />}
      {tab === "Guide" && <Steps steps={MSSQL_HOWTO} />}
      <CardPlaybooks type={conn.Type} />
      <RemoveConnection conn={conn} reload={reload} onBack={onBack} />
    </Box>
  );
}

/* ── the SQL Server CONNECTION (set up once; reports inherit it) ────────── */
function MssqlConnection({ conn, drivers, reload }) {
  const [cfg, setCfg] = useState(parse(conn.ConfigJson));
  const [secret, setSecret] = useState("");
  const [step, setStep] = useState(conn.LastSyncAt && !conn.LastError ? 1 : 0);
  const [test, setTest] = useState(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const sqlAuth = (cfg.auth || "windows") === "sql";

  const save = async () => {
    setBusy("save"); setMsg("");
    try {
      const body = { ConnectorId: conn.ConnectorId, ConfigJson: JSON.stringify(cfg), Active: true };
      if (secret) body.Secret = secret;
      await api.post("/api/connectors", body);
      setMsg("saved ✓"); setSecret(""); setStep(1); reload();
    } catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "save failed" }); }
    setBusy("");
  };
  const runTest = async () => {
    setBusy("test");
    try { setTest((await api.post(`/api/connectors/${conn.ConnectorId}/test`)).data); }
    catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "test call failed" }); }
    setBusy(""); reload();
  };

  return (
    <Stepper nonLinear activeStep={step} orientation="vertical" sx={{ "& .MuiStepLabel-label": { fontSize: 13.5, fontWeight: 600 } }}>
      <Step completed={!!(cfg.server || conn.LastSyncAt)}>
        <StepButton onClick={() => setStep(0)}>Connection</StepButton>
        <StepContent>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, maxWidth: 460, mt: 1 }}>
            <TextField label="server" placeholder="localhost  ·  localhost\SQLEXPRESS  ·  HOST\INSTANCE" value={cfg.server || ""}
              sx={{ bgcolor: "#fff" }} onChange={(e) => setCfg({ ...cfg, server: e.target.value })} />
            <TextField label="database" placeholder="master" value={cfg.database || ""}
              sx={{ bgcolor: "#fff" }} onChange={(e) => setCfg({ ...cfg, database: e.target.value })} />
            <Select value={cfg.auth || "windows"} sx={{ bgcolor: "#fff" }} onChange={(e) => setCfg({ ...cfg, auth: e.target.value })}>
              <MenuItem value="windows" sx={{ fontSize: 12.5 }}>Windows auth (local, trusted)</MenuItem>
              <MenuItem value="sql" sx={{ fontSize: 12.5 }}>SQL login</MenuItem>
            </Select>
            {sqlAuth && <TextField label="username" value={cfg.username || ""} sx={{ bgcolor: "#fff" }}
              onChange={(e) => setCfg({ ...cfg, username: e.target.value })} />}
            {sqlAuth && <TextField label={conn.HasSecret ? "password (saved — type to replace)" : "password"} type="password"
              value={secret} onChange={(e) => setSecret(e.target.value)} sx={{ bgcolor: "#fff" }} />}
            <Select value={cfg.driver || ""} displayEmpty sx={{ bgcolor: "#fff" }} onChange={(e) => setCfg({ ...cfg, driver: e.target.value })}>
              <MenuItem value="" sx={{ fontSize: 12.5 }}>(auto — newest installed driver)</MenuItem>
              {drivers.map((d) => <MenuItem key={d} value={d} sx={{ fontSize: 12.5 }}>{d}</MenuItem>)}
            </Select>
            <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
              <Button variant="contained" disableElevation disabled={busy === "save"} onClick={save}>
                {busy === "save" ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : "Save & continue"}</Button>
              {msg && <Typography variant="body2" sx={{ color: "#47654a", fontWeight: 600 }}>{msg}</Typography>}
            </Box>
          </Box>
        </StepContent>
      </Step>
      <Step completed={!!(conn.LastSyncAt && !conn.LastError)}>
        <StepButton onClick={() => setStep(1)}>Test connection</StepButton>
        <StepContent>
          <Typography variant="body2" sx={{ color: DIM, mb: 1, mt: 0.5 }}>Connects for real and reports the server version — every scheduled report inherits this connection.</Typography>
          <Button variant="contained" disableElevation disabled={busy === "test"} onClick={runTest}
            startIcon={busy === "test" ? <CircularProgress size={12} sx={{ color: "#fff" }} /> : <BoltIcon sx={{ fontSize: 15 }} />}>Test</Button>
          <TestLine test={test} mt={1} />
          {!test && conn.LastError && <Typography variant="body2" sx={{ mt: 1, color: "#6b2733" }}>✗ {conn.LastError}</Typography>}
        </StepContent>
      </Step>
    </Stepper>
  );
}

/* ── Remote Windows (WinRM) detail: machine name + live probe; reports live on Reports ── */
function WinrmDetail({ conn, reload, onBack, onCreated }) {
  const [tab, setTab] = useState("Connection");
  const [cfg, setCfg] = useState(parse(conn?.ConfigJson));
  const [test, setTest] = useState(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  if (!conn) return null;

  const save = async () => {
    setBusy("save"); setMsg("");
    try {
      await api.post("/api/connectors", { ConnectorId: conn.ConnectorId, ConfigJson: JSON.stringify(cfg), Active: true });
      setMsg("saved ✓"); reload();
    } catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "save failed" }); }
    setBusy("");
  };
  const runTest = async () => {
    setBusy("test");
    try { setTest((await api.post(`/api/connectors/${conn.ConnectorId}/test`)).data); }
    catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "test call failed" }); }
    setBusy(""); reload();
  };

  return (
    <Box sx={{ maxWidth: 980, mx: "auto" }}>
      <Crumb section="Connections" onBack={onBack} title={conn.Name} />
      <ConnectorIdentity conn={conn} reload={reload} onCreated={onCreated} />
      <AiSetup conn={conn} steps={WINRM_HOWTO} fields={[["machine name", "host"]]} agentSteps={WINRM_AGENT} reload={reload} />
      <Typography variant="body2" sx={{ color: DIM, mb: 1.5 }}>
        Run PowerShell ON a machine you can RDP into (your Windows credentials) — the connection only;
        build the scheduled reports on the Reports tab.
      </Typography>
      <UnderTabs tabs={["Connection", "Guide", "Agent"]} value={tab} onChange={setTab} />
      {tab === "Guide" && <Steps steps={WINRM_HOWTO} />}
      {tab === "Agent" && <AgentTab steps={WINRM_AGENT} />}
      {tab === "Connection" && (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, maxWidth: 460, mt: 1 }}>
          <TextField label="machine name" placeholder="AZWEB01" value={cfg.host || ""} sx={{ bgcolor: "#fff" }}
            onChange={(e) => setCfg({ ...cfg, host: e.target.value })} />
          <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
            <Button variant="contained" disableElevation disabled={busy === "save"} onClick={save}>
              {busy === "save" ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : "Save"}</Button>
            <Button variant="outlined" disabled={busy === "test" || !cfg.host} onClick={runTest}
              startIcon={busy === "test" ? <CircularProgress size={12} /> : <BoltIcon sx={{ fontSize: 15 }} />}>Test</Button>
            {msg && <Typography variant="body2" sx={{ color: "#47654a", fontWeight: 600 }}>{msg}</Typography>}
          </Box>
          <TestLine test={test} mt={0} />
          {!test && conn.LastError && <Typography variant="body2" sx={{ color: "#6b2733" }}>✗ {conn.LastError}</Typography>}
        </Box>
      )}
      <CardPlaybooks type={conn.Type} />
      <RemoveConnection conn={conn} reload={reload} onBack={onBack} />
    </Box>
  );
}

/* ── What each DISCOVERED cloud object does. Same shape as the GitHub card's per-repo
   pickers, and the same reason: one bucket is a report source, the next should put every
   new file on the Timeline - that is a per-OBJECT decision, not a per-connection one.
   'report' is the default and polls nothing: the object is simply available on the
   Reports tab. Picking saves instantly. ── */
const CLOUD_MODES = [
  ["report", "report only — selectable on the Reports tab, never polled"],
  ["feed", "feed — new items appear on the Timeline, never become work"],
  ["tasks", "tasks — new items go through triage and can become work"],
  ["off", "off — ignored entirely"],
];
// prefix -> (short type label, filter pill label). The prefix IS the type, so one place
// turns s3://… into "S3 bucket" for the row and "S3 buckets" for the pill.
const OBJ_TYPES = {
  "s3://": ["S3 bucket", "S3 buckets"],
  "logs://": ["CloudWatch log group", "log groups"],
  "blob://": ["blob container", "blob containers"],
  "law://": ["Log Analytics workspace", "workspaces"],
};
const objType = (addr) => Object.keys(OBJ_TYPES).find((p) => addr.startsWith(p)) || "";
const regionOf = (s) => { try { return JSON.parse(s.ConfigJson || "{}").region || ""; } catch { return ""; } };
const OBJ_KIND = (addr) => (OBJ_TYPES[objType(addr)] || ["object"])[0];
const objName = (addr) => addr.slice(objType(addr).length) || addr;
const PAGE_OBJ = 40;   // a 100-row wall is not a list; the rest is one click away

function CloudObjects({ conn, meta, objects, reload }) {
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");     // "" = every type
  const [mode, setMode] = useState("");     // "" = every mode
  const [limit, setLimit] = useState(PAGE_OBJ);
  const [bulk, setBulk] = useState("");
  const setOne = async (s, m) => {
    await api.post("/api/sources", { SourceId: s.SourceId, ConfigJson: JSON.stringify({ ...parse(s.ConfigJson), mode: m }) });
    reload();
  };
  const rediscover = async () => {
    setBusy(true);
    try { await api.post(`/api/connectors/${conn.ConnectorId}/test`); } catch { /* the card shows the error */ }
    setBusy(false); reload();
  };
  const modeOf = (s) => parse(s.ConfigJson).mode || "report";
  const needle = q.trim().toLowerCase();
  const shown = objects.filter((s) => (!kind || objType(s.Address) === kind)
    && (!mode || modeOf(s) === mode)
    && (!needle || s.Address.toLowerCase().includes(needle)));
  // the type pills only offer types this connection actually discovered
  const kinds = Object.keys(OBJ_TYPES).filter((p) => objects.some((s) => objType(s.Address) === p));
  // one decision for a whole filtered set: 46 buckets where 40 are amplify noise is a
  // search for "amplify" and one click, not 40 dropdowns
  const setAllShown = async (m) => {
    setBulk(m);
    for (const s of shown) {
      await api.post("/api/sources", { SourceId: s.SourceId, ConfigJson: JSON.stringify({ ...parse(s.ConfigJson), mode: m }) });
    }
    setBulk(""); reload();
  };
  return (
    <Box sx={{ mt: 3, maxWidth: 760 }}>
      <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13.5 }}>
        What you have access to — and what each one does
      </Typography>
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5, mb: 1 }}>
        Discovery asks your {meta.title.includes("Azure") ? "app registration" : "keys"} what they can see and lists
        it here. Everything arrives as <b>report only</b>: available to the Reports tab, nothing polled. Switch one
        to <b>feed</b> or <b>tasks</b> and Taskuary starts watching it on every sync.
      </Typography>
      <Button size="small" variant="outlined" onClick={rediscover} disabled={busy} sx={{ mb: 1.5 }}
        startIcon={busy ? <CircularProgress size={11} /> : <SyncIcon sx={{ fontSize: 14 }} />}>
        {busy ? "Discovering…" : objects.length ? "Re-run discovery" : "Discover what I can access"}
      </Button>
      {!objects.length ? (
        <Empty>Nothing discovered yet — save the credentials above and press Discover.</Empty>
      ) : (
        <>
          <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap", mb: 1 }}>
            <TextField size="small" placeholder="search by name…" value={q}
              onChange={(e) => { setQ(e.target.value); setLimit(PAGE_OBJ); }}
              sx={{ bgcolor: "#fff", width: 230 }}
              InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon sx={{ fontSize: 16, color: FAINT }} /></InputAdornment> }} />
            {kinds.length > 1 && (
              <FilterPills value={kind} onChange={(v) => { setKind(v); setLimit(PAGE_OBJ); }}
                options={[{ key: "", label: "all", n: objects.length },
                  ...kinds.map((p) => ({ key: p, label: OBJ_TYPES[p][1],
                    n: objects.filter((s) => objType(s.Address) === p).length }))]} />
            )}
            <FilterPills value={mode} onChange={(v) => { setMode(v); setLimit(PAGE_OBJ); }}
              options={[{ key: "", label: "any mode" },
                ...CLOUD_MODES.map(([v]) => ({ key: v, label: v }))
                  .filter((o) => objects.some((s) => modeOf(s) === o.key))]} />
          </Box>
          <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap", mb: 0.5 }}>
            <Typography variant="caption" sx={{ color: FAINT }}>
              {shown.length === objects.length ? `${objects.length} objects`
                : `${shown.length} of ${objects.length} shown`}
            </Typography>
            {shown.length > 0 && shown.length < objects.length && (
              <>
                <Typography variant="caption" sx={{ color: FAINT }}>· set all {shown.length} shown to</Typography>
                {CLOUD_MODES.map(([v, label]) => (
                  <Box key={v} component="span" title={label}
                    onClick={() => !bulk && setAllShown(v)}
                    sx={{ fontSize: 11, fontWeight: 700, color: bulk ? FAINT : "#55697a", cursor: bulk ? "default" : "pointer",
                      "&:hover": { textDecoration: bulk ? "none" : "underline" } }}>
                    {bulk === v ? `${v}…` : v}
                  </Box>
                ))}
              </>
            )}
          </Box>
          {!shown.length && <Empty>Nothing matches that search.</Empty>}
          {shown.slice(0, limit).map((s) => (
            <Box key={s.SourceId} sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1, borderBottom: `1px solid ${BORDER}` }}>
              <Box sx={{ minWidth: 0, flex: 1 }}>
                <Typography sx={{ ...mono, color: INK, fontSize: 12.5 }} noWrap title={s.Address}>{objName(s.Address)}</Typography>
                <Typography variant="caption" sx={{ color: FAINT }}>
                  {OBJ_KIND(s.Address)}
                  {/* two regions can hold log groups with the SAME name - without this they are
                      two identical rows and no way to tell which one you just switched on */}
                  {regionOf(s) ? ` · ${regionOf(s)}` : ""}
                  {s.LastPolledAt ? ` · polled ${timeAgo(s.LastPolledAt)}` : ""}
                </Typography>
              </Box>
              <Select size="small" value={modeOf(s)} onChange={(e) => setOne(s, e.target.value)}
                sx={{ fontSize: 11.5, height: 26, minWidth: 108, ".MuiSelect-select": { py: 0.4 } }}>
                {CLOUD_MODES.map(([v, label]) => (
                  <MenuItem key={v} value={v} sx={{ fontSize: 12 }} title={label}>{v}</MenuItem>
                ))}
              </Select>
            </Box>
          ))}
          {shown.length > limit && (
            <Button size="small" onClick={() => setLimit(limit + PAGE_OBJ * 2)} sx={{ mt: 1 }}>
              show {Math.min(PAGE_OBJ * 2, shown.length - limit)} more of {shown.length - limit}
            </Button>
          )}
        </>
      )}
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 1 }}>
        <b>feed</b> and <b>tasks</b> watch for what is NEW since the last sync: a bucket reports each new object, a
        log group batches the matching lines into one item, a workspace runs its saved query. An object nothing
        discovered can still be typed in by hand as a report source on the Reports tab.
      </Typography>
    </Box>
  );
}

/* ── shared detail for the DATA_META cards (database / aws / azure): fields + write-only
   secret + live Test; the connection only - reports are built on the Reports tab. ── */
/* A card whose credential is minted by signing in at the provider (QuickBooks): the box says
   what the provider's app must carry (the redirect URI), whether we are connected and to which
   company, and one button that opens the sign-in. The token comes back server-side. */
function OAuthConnect({ conn, meta, reload }) {
  const [st, setSt] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const load = useCallback(async () => { try { setSt((await api.get(meta.connect.status(conn.ConnectorId))).data); } catch { /* the card still works */ } }, [conn.ConnectorId, meta]);
  useEffect(() => { load(); }, [load]);
  // the sign-in happens in another tab; poll while it is likely underway so the box flips to
  // "connected" without a refresh
  useEffect(() => { if (!busy) return undefined; const id = setInterval(load, 3000); const stop = setTimeout(() => setBusy(false), 180000); return () => { clearInterval(id); clearTimeout(stop); }; }, [busy, load]);
  useEffect(() => { if (st?.connected) setBusy(false); }, [st?.connected]);
  // Teller Connect is a script on THIS page, not a redirect: it opens the bank's sign-in in a
  // modal and calls back with the token, which goes straight to the server and nowhere else
  const teller = async () => {
    if (!window.TellerConnect) {
      await new Promise((ok, no) => { const s = document.createElement("script"); s.src = st.connect_js; s.onload = ok; s.onerror = () => no(new Error("Teller Connect did not load - is cdn.teller.io reachable from here?")); document.head.appendChild(s); });
    }
    setBusy(true);
    const tc = window.TellerConnect.setup({
      applicationId: st.application_id, environment: st.environment, products: ["transactions", "balance"],
      onSuccess: async (enr) => {
        try {
          await api.post(meta.connect.enroll(conn.ConnectorId), { access_token: enr.accessToken, enrollment_id: enr.enrollment?.id, institution: enr.enrollment?.institution?.name });
          await load(); reload();
        } catch (e) { setErr(e?.response?.data?.detail || "the token did not save"); }
        setBusy(false);
      },
      onExit: () => setBusy(false),
    });
    tc.open();
  };
  const go = async () => {
    setErr("");
    try {
      if (meta.connect.widget === "teller") return await teller();
      const { data } = await api.get(meta.connect.start(conn.ConnectorId)); window.open(data.url, "_blank", "noopener"); setBusy(true);
    } catch (e) { setErr(e?.response?.data?.detail || e?.message || "could not start the sign-in"); }
  };
  return (
    <Box sx={{ p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: PANEL2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
        <Button variant="contained" disableElevation disabled={!st?.has_app || busy} onClick={go}
          title={st?.has_app ? meta.connect.text : "save the app's client id and secret first"}>
          {busy ? <><CircularProgress size={12} sx={{ color: "#fff", mr: 1 }} /> waiting for the sign-in…</> : st?.connected ? "Reconnect" : meta.connect.label}
        </Button>
        {st?.connected
          ? <Typography variant="body2" sx={{ color: "#47654a", fontWeight: 600 }}>✓ Connected{st.realm_id ? ` · company ${st.realm_id}` : ""}{st.institution ? ` · ${st.institution}` : ""}{(st.env || st.environment) === "sandbox" ? " · sandbox" : ""}</Typography>
          : <Typography variant="body2" sx={{ color: DIM }}>{st?.has_app ? "keys saved — not connected yet" : "paste the application's keys below and Save first"}</Typography>}
      </Box>
      {st?.redirect_uri && (
        <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.75, lineHeight: 1.6 }}>
          The Intuit app must list this redirect URI, exactly: <Box component="code" sx={{ ...mono, fontSize: 11, color: INK, bgcolor: "#fff", px: 0.6, borderRadius: 0.75, border: `1px solid ${BORDER}` }}>{st.redirect_uri}</Box>
        </Typography>
      )}
      {err && <Typography variant="body2" sx={{ color: "#6b2733", mt: 0.75 }}>✗ {err}</Typography>}
    </Box>
  );
}

function DataDetail({ conn, meta, sources, reload, onBack, onCreated, byType = {} }) {
  const [tab, setTab] = useState("Connection");
  const [cfg, setCfg] = useState(parse(conn?.ConfigJson));
  const [secret, setSecret] = useState("");
  const [test, setTest] = useState(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  if (!conn) return null;
  const objects = (sources || []).filter((s) => s.Channel === conn.Type && s.ConnectorId === conn.ConnectorId);
  // the borrow offer: only when the OTHER card actually has something to lend (a tenant app, a
  // Google client) - an offer to reuse nothing is worse than no offer
  const canReuse = !!(meta.reuse && meta.reuse.ok(byType[meta.reuse.from]));
  const useShared = async () => {
    const next = { ...cfg }; (meta.reuse.clear || []).forEach((k) => { delete next[k]; });
    setCfg(next); setBusy("save"); setMsg("");
    try {
      await api.post("/api/connectors", { ConnectorId: conn.ConnectorId, ConfigJson: JSON.stringify(next), Active: true });
      setMsg(`saved — using the ${meta.reuse.from} card's app ✓`);
      setBusy("test");
      setTest((await api.post(`/api/connectors/${conn.ConnectorId}/test`)).data);
    } catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "could not switch to the shared app" }); }
    setBusy(""); reload();
  };

  const save = async () => {
    setBusy("save"); setMsg("");
    try {
      const body = { ConnectorId: conn.ConnectorId, ConfigJson: JSON.stringify(cfg), Active: true };
      if (secret) body.Secret = secret;
      await api.post("/api/connectors", body);
      setMsg("saved ✓"); setSecret(""); reload();
    } catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "save failed" }); }
    setBusy("");
  };
  const runTest = async () => {
    setBusy("test");
    try { setTest((await api.post(`/api/connectors/${conn.ConnectorId}/test`)).data); }
    catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "test call failed" }); }
    setBusy(""); reload();
  };

  return (
    <Box sx={{ maxWidth: 980, mx: "auto" }}>
      <Crumb section="Connections" onBack={onBack} title={conn.Name} />
      <ConnectorIdentity conn={conn} reload={reload} onCreated={onCreated} />
      <AiSetup conn={conn} steps={meta.howto || []} fields={meta.fields || []} secretLabel={meta.secretLabel} agentSteps={meta.agent || []} reload={reload} />
      <Typography variant="body2" sx={{ color: DIM, mb: 1.5 }}>
        {meta.desc} The connection only — build the scheduled reports on the Reports tab.
      </Typography>
      <UnderTabs tabs={["Connection", "Guide", "Agent"]} value={tab} onChange={setTab} />
      {tab === "Guide" && <Steps steps={meta.howto} />}
      {tab === "Agent" && <AgentTab steps={meta.agent} />}
      {tab === "Connection" && (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, maxWidth: 560, mt: 1 }}>
          {canReuse && (
            <Box sx={{ p: 1.25, border: `1px dashed ${BORDER}`, borderRadius: 2, bgcolor: PANEL2 }}>
              <Typography variant="body2" sx={{ fontWeight: 700, color: INK }}>{meta.reuse.title}</Typography>
              <Typography variant="caption" sx={{ color: DIM, display: "block", lineHeight: 1.5, mb: 0.75 }}>{meta.reuse.text}</Typography>
              <Button size="small" variant="outlined" disabled={!!busy} onClick={useShared}>Use it — save and test</Button>
            </Box>
          )}
          {meta.connect && <OAuthConnect conn={conn} meta={meta} reload={reload} />}
          {meta.fields.map(([label, key, ph]) => (
            <TextField key={key} label={label} placeholder={ph} value={cfg[key] || ""} sx={{ bgcolor: "#fff" }}
              multiline={key === "conn_str"} minRows={key === "conn_str" ? 2 : undefined}
              onChange={(e) => setCfg({ ...cfg, [key]: e.target.value })} />
          ))}
          {!meta.noSecret && <TextField label={conn.HasSecret ? `${meta.secretLabel} — saved, type to replace` : meta.secretLabel}
            type="password" value={secret} onChange={(e) => setSecret(e.target.value)} sx={{ bgcolor: "#fff" }}
            helperText="Write-only: stored server-side, never returned to the browser." />}
          <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
            <Button variant="contained" disableElevation disabled={busy === "save"} onClick={save}>
              {busy === "save" ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : "Save"}</Button>
            <Button variant="outlined" disabled={busy === "test"} onClick={runTest}
              startIcon={busy === "test" ? <CircularProgress size={12} /> : <BoltIcon sx={{ fontSize: 15 }} />}>
              {meta.discovers ? "Test & discover" : "Test"}</Button>
            {/* a card's own verbs (the knowledge base's Reindex): one POST, the answer said in a line */}
            {(meta.actions || []).map((a) => (
              <Button key={a.label} variant="outlined" disabled={!!busy} onClick={async () => {
                setBusy(a.label); setMsg("");
                try { const r = (await api.post(a.post, a.body ? a.body(conn) : {})).data; setMsg(a.say ? a.say(r) : "done ✓"); }
                catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || `${a.label} failed` }); }
                setBusy(""); reload();
              }}>{busy === a.label ? <CircularProgress size={12} /> : a.label}</Button>
            ))}
            {msg && <Typography variant="body2" sx={{ color: "#47654a", fontWeight: 600 }}>{msg}</Typography>}
          </Box>
          {meta.search && <KbSearch conn={conn} />}
          <TestLine test={test} mt={0} />
          {!test && conn.LastError && <Typography variant="body2" sx={{ color: "#6b2733" }}>✗ {conn.LastError}</Typography>}
        </Box>
      )}
      {tab === "Connection" && meta.discovers && (
        <CloudObjects conn={conn} meta={meta} objects={objects} reload={reload} />
      )}
      <CardPlaybooks type={conn.Type} />
      <RemoveConnection conn={conn} reload={reload} onBack={onBack} />
    </Box>
  );
}

/* What a connection IS to the hub. Three independent jobs - a system can do all three,
   or just be something the agents are allowed to touch. */
const ROLE_META = {
  trigger: ["Inbound trigger — creates work", "Poll it for new items, run them through triage, open tasks and draft replies. This is what turns a connection into work (mail, chats, GitHub issues…)."],
  feed: ["Timeline feed — shows, never assigns", "Poll it and show every new item on the Timeline, but stop there: no triage, no AI call, no task. Good for GitHub issues or a chatty channel you want to SEE without being handed."],
  report: ["Report source", "Selectable on the Reports tab: query it on a schedule and put the (optionally AI-summarized) result on the Timeline."],
  tool: ["Agent tool", "Named for the agents in SOUL.md as a system they may use — pull data from it, create and update things in it while working a task."],
  notify: ["Notifications", "The outbound direction: Taskuary pushes a ping into this chat when something needs you. Name the chat in Credentials; what qualifies is Settings → Notifications."],
};

// The GitHub DECISIONS live on the GitHub card: is GitHub the issue tracker for tasks (agents
// open/update issues as the team expects) and may agents push/deploy on their own. These were
// buried in Settings as global switches, which read as Taskuary behavior instead of what they
// are - how this team uses this connector. Either can be on without the other.
const GITHUB_PERMS = [
  ["use_as_tracker", "GitHub is the issue tracker",
   "On: your team runs on GitHub issues, so agents open and update them for the work they do. Off (default): Taskuary is the tracker - the task is the record - and agents never create issues or tracker items unless a task's ask explicitly says to."],
  ["agents_push", "Agents may push / deploy",
   "On: agents push and deploy as the work needs. Off (default): commits stay local for your review - you push - and only a task whose ask explicitly says to push may. Force-pushes and archived repositories stay forbidden either way."],
  ["reply_comments", "Reply to issue/PR authors",
   "On: questions from GitHub get a drafted reply, finished work drafts a close-out note, and approving one posts it as a PUBLIC comment on the issue/PR. Off (default): GitHub items never get reply drafts - questions file with their triage reason, finished work just closes with its report, and nothing is ever posted to a public thread on your behalf."],
];

const GithubPerms = ({ conn, reload }) => {
  const cfg = JSON.parse(conn.ConfigJson || "{}");
  const toggle = async (key) => {
    await api.post("/api/connectors", { ConnectorId: conn.ConnectorId,
      ConfigJson: JSON.stringify({ ...cfg, [key]: !cfg[key] }) });
    reload();
  };
  return (
    <Box sx={{ mt: 1, maxWidth: 620 }}>
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.5 }}>
        OUTBOUND — what the coding agent may do <b>on GitHub</b> while it works your tasks. Unrelated
        to the <b>Inbound</b> step above, which only controls what comes <b>in</b> to your timeline.
      </Typography>
      {GITHUB_PERMS.map(([key, label, desc]) => (
        <Box key={key} sx={{ display: "flex", alignItems: "flex-start", gap: 1.5, py: 1.25, borderBottom: `1px solid ${BORDER}` }}>
          <Switch checked={!!cfg[key]} onChange={() => toggle(key)} sx={{ mt: -0.5 }} />
          <Box sx={{ minWidth: 0 }}>
            <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13 }}>{label}</Typography>
            <Typography variant="body2" sx={{ color: DIM }}>{desc}</Typography>
          </Box>
        </Box>
      ))}
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 1 }}>
        Both land in the instruction every agent session is seeded with, and in the SOUL.md line
        describing this connection. A task whose ask explicitly says "open an issue" or "push"
        may always do so, whatever these say.
      </Typography>
    </Box>
  );
};

const useRoles = (conn, reload) => {
  const roles = new Set(String(conn.Roles || "").split(",").filter(Boolean));
  const toggle = async (r) => {
    const next = new Set(roles);
    if (next.has(r)) next.delete(r); else next.add(r);
    // a trigger already puts its items on the timeline; holding both would just be a
    // contradiction the poller has to resolve
    if (r === "trigger" && next.has("trigger")) next.delete("feed");
    if (r === "feed" && next.has("feed")) next.delete("trigger");
    await api.post("/api/connectors", { ConnectorId: conn.ConnectorId, Roles: [...next].join(",") });
    reload();
  };
  return [roles, toggle];
};

const RoleRow = ({ on, onToggle, label, desc }) => (
  <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.5, py: 1.25, borderBottom: `1px solid ${BORDER}` }}>
    <Switch checked={on} onChange={onToggle} sx={{ mt: -0.5 }} />
    <Box sx={{ minWidth: 0 }}>
      <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13 }}>{label}</Typography>
      <Typography variant="body2" sx={{ color: DIM }}>{desc}</Typography>
    </Box>
  </Box>
);

/* Authority: the ceiling on what an agent may do THROUGH this connection, once it is a tool.
   The role says the agents may use Jira; this says whether they may close a ticket in it.
   Read is the safe floor and the default for every tracker - a connection only gains a verb
   when the owner hands it over. */
const SCOPE_META = {
  read: ["Read only", "Look, never touch: list, fetch, search, query. Nothing upstream changes. The safe default."],
  write: ["Read and write", "The everyday work as well: create, update, comment, assign, complete, send. No deleting, no closing, no running code."],
  admin: ["Full authority", "Everything, including the destructive and the structural: delete, close, archive, manage access, run scripts on a box. Hand this over deliberately."],
};
const SCOPE_KEYS = ["read", "write", "admin"];

const AuthorityRow = ({ conn, reload }) => {
  const fallback = String(conn.ScopeDefault || "read").toLowerCase();
  const current = String(conn.Scope || "").toLowerCase();
  const [busy, setBusy] = useState(false);
  const set = async (s) => {
    setBusy(true);
    try { await api.post("/api/connectors", { ConnectorId: conn.ConnectorId, Scope: s }); reload(); }
    finally { setBusy(false); }
  };
  return (
    <Box sx={{ pt: 1.5 }}>
      <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13 }}>Authority — how far the agents may reach</Typography>
      <Typography variant="body2" sx={{ color: DIM, mb: 1 }}>
        Only bites when this is an agent tool. An action nobody has classified counts as write,
        so a read-only connection stays read-only even for a verb we have never seen.
      </Typography>
      {SCOPE_KEYS.map((s) => (
        <Box key={s} sx={{ display: "flex", alignItems: "flex-start", gap: 1.5, py: 1, borderBottom: `1px solid ${BORDER}` }}>
          <Radio checked={(current || fallback) === s} disabled={busy} onChange={() => set(s)} sx={{ mt: -0.75 }} />
          <Box sx={{ minWidth: 0 }}>
            <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13 }}>
              {SCOPE_META[s][0]}{!current && fallback === s ? " — default" : ""}
            </Typography>
            <Typography variant="body2" sx={{ color: DIM }}>{SCOPE_META[s][1]}</Typography>
          </Box>
        </Box>
      ))}
    </Box>
  );
};

const RoleStep = ({ conn, reload, only }) => {
  const [roles, toggle] = useRoles(conn, reload);
  const keys = only || Object.keys(ROLE_META);
  const chat = String(parse(conn.ConfigJson).notify_chat || "").trim();
  return (
    <Box sx={{ mt: 1, maxWidth: 620 }}>
      {keys.map((key) => (
        <RoleRow key={key} on={roles.has(key)} onToggle={() => toggle(key)}
          label={ROLE_META[key][0]} desc={ROLE_META[key][1]} />
      ))}
      {keys.includes("notify") && roles.has("notify") && (
        <Typography variant="caption" sx={{ color: chat ? "#47654a" : "#55697a", display: "block", mt: 1, lineHeight: 1.45 }}>
          {chat
            ? `Pinging chat ${chat} · what goes out is Settings → Notifications`
            : "Name the chat in Credentials, or pings have nowhere to go."}
        </Typography>
      )}
      {keys.includes("tool") && <AuthorityRow conn={conn} reload={reload} />}
    </Box>
  );
};

/* ── the ONE inbound page: the switch, what each source's items do, and the agent prompt.
   These three used to live on three different steps (Role, Repositories, Credentials) and
   read as three unrelated settings - they are one decision: what from here becomes work,
   and what the agent is told about it. ── */
const GH_PROMPTS = [
  ["prompt_pr", "When the task came from a PULL REQUEST",
   "blank = the built-in: judge it — useful? safe? minimal? — check out the branch, run the tests, report a verdict; never merge"],
  ["prompt_issue", "When the task came from an ISSUE",
   "blank = the built-in: reproduce it, fix it when the fix is contained, otherwise report what it would take"],
];
const TASK_PROMPT = [["task_prompt", "For every task from this connection",
  "optional — rides into the agent's instructions alongside the message itself; blank = nothing extra"]];
const PROMPTABLE = new Set(["outlook", "teams", "slack", "telegram", "whatsapp", "imessage", "gmail", "imap",
  "jira", "asana", "monday"]);
const promptsFor = (t) => (t === "github" ? GH_PROMPTS : PROMPTABLE.has(t) ? TASK_PROMPT : []);

const ghInboundExplicit = (mine) => mine.some((s) => {
  const c = parse(s.ConfigJson);
  return ["tasks", "feed"].includes(c.issues) || ["tasks", "feed"].includes(c.prs);
});
const inboundDone = (conn, mine) => {
  const roles = new Set(String(conn.Roles || "").split(",").filter(Boolean));
  return roles.has("trigger") || roles.has("feed") || (conn.Type === "github" && ghInboundExplicit(mine));
};

// Bulk processing: rank it, don't clear it. One switch per connector, explained in place -
// the whole idea is a paragraph, and a paragraph belongs next to the switch it explains.
const BULK_HELP = (
  <Box sx={{ p: 1.75, maxWidth: 380 }}>
    <Typography variant="body2" sx={{ fontWeight: 700, mb: 0.75 }}>Bulk processing</Typography>
    <Typography variant="body2" sx={{ fontSize: 12.5, lineHeight: 1.55, mb: 1 }}>
      <b>clear</b> — every task from here is worked in arrival order until the queue is empty. Right when the
      inbox <i>is</i> the job.
    </Typography>
    <Typography variant="body2" sx={{ fontSize: 12.5, lineHeight: 1.55, mb: 1 }}>
      <b>rank</b> — tasks from here join one value-ordered queue instead of racing for a session. The top
      <i> K</i> are worked (<i>K</i> = <b>Agents at once</b> in Settings); when one finishes, the most valuable
      waiting task slides in, and a new arrival re-ranks the queue rather than joining its tail. Nothing is
      dropped — a low value waits.
    </Typography>
    <Typography variant="body2" sx={{ fontSize: 12.5, lineHeight: 1.55 }}>
      Value is <b>words first</b>: addressed to you or merely cc’d, how many people, whether a colleague has
      already replied, urgency, who the author is on a code host. With two or more waiting, one call to the
      triage brain orders the head of the queue and adds its own reason. You see it on the Timeline’s funnel
      bar and can pin any card to the top or push it back.
    </Typography>
  </Box>
);

const MODES = [
  ["clear", "One by one", "Every task from here goes to an agent as it arrives, in arrival order. When all agent slots are busy, the next ones queue - first in, first out - until the inbox is clear. Right when the inbox IS the job."],
  ["rank", "Ranked together", "Tasks from here join one queue ordered by value - addressed to you or merely cc’d, how many people, whether a colleague replied, urgency, who the author is - and only the top K are worked at once (K = Agents at once in Settings). A new arrival re-ranks the queue rather than joining its tail; nothing is dropped, lower value waits. Right when you are cc'd on most of it and a few things matter."],
];

/* ── Which folders a mailbox reads. Only the Inbox was ever read, and a rule that files vendor mail
   into "Vendors" made that mail invisible here. The chooser lists the mailbox's folders (Graph) and
   keeps the picks on the source; the Inbox alone is the default. ── */
const MailFolders = ({ conn, s, reload }) => {
  const cfg = parse(s.ConfigJson);
  const chosen = new Set((cfg.folders || []).length ? cfg.folders : ["inbox"]);
  const [open, setOpen] = useState(false);
  const [list, setList] = useState(null);
  const [err, setErr] = useState("");
  const load = async () => {
    setOpen(true);
    if (list) return;
    try { const { data } = await api.get(`/api/connectors/${conn.ConnectorId}/mail/folders`, { params: { mailbox: s.Address } }); setList(data.data); }
    catch (e) { setErr(e?.response?.data?.detail || "could not list folders"); setList([]); }
  };
  const toggle = async (id) => {
    const next = new Set(chosen); next.has(id) ? next.delete(id) : next.add(id);
    if (!next.size) return;                                       // a mailbox that reads nothing is a switched-off mailbox
    await api.post("/api/sources", { SourceId: s.SourceId, ConfigJson: JSON.stringify({ ...cfg, folders: [...next] }) }); reload();
  };
  const label = chosen.size === 1 && chosen.has("inbox") ? "Inbox only" : `${chosen.size} folder${chosen.size === 1 ? "" : "s"}`;
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, flexWrap: "wrap" }}>
      <Button size="small" onClick={() => (open ? setOpen(false) : load())} sx={{ fontSize: 11, textTransform: "none", color: DIM, py: 0, minWidth: 0 }}>
        {label} {open ? "▴" : "▾"}
      </Button>
      {open && (
        <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", alignItems: "center" }}>
          {list === null && <CircularProgress size={11} />}
          {err && <Typography variant="caption" sx={{ color: "#6b2733" }}>{err}</Typography>}
          {(list || []).map((f) => (
            <Box key={f.id} onClick={() => toggle(f.id)}
              sx={{ px: 0.9, py: 0.2, borderRadius: 99, cursor: "pointer", fontSize: 11, userSelect: "none",
                fontWeight: chosen.has(f.id) ? 700 : 500, bgcolor: chosen.has(f.id) ? "#eae4d8" : "#fff",
                color: chosen.has(f.id) ? "#55697a" : DIM, border: `1px solid ${chosen.has(f.id) ? "#d8cfbe" : BORDER}` }}>
              {f.name}{f.count ? <Box component="span" sx={{ color: FAINT, ml: 0.5 }}>{f.count}</Box> : null}
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
};

/* ── WhatsApp pairing, on the card. The bridge serves its QR at /status and WhatsApp rotates it
   every ~20 seconds, so this polls and redraws; a terminal QR is too big to scan and a phone
   number is nothing to type into a chat. Paired = the box says who, and stops polling. ── */
/* ── WhatsApp pairing: three steps that drive themselves. 1 Node on the machine (the only thing the
   owner installs - the box says how and re-checks on its own); 2 the bridge, which the box starts the
   moment Node is there (no button to find, no agent to wait on); 3 the QR, scanned from the phone.
   A tester's agent-driven setup spun for five minutes on step 2; a person should never see that. ── */
const WaPair = ({ conn, reload }) => {
  const [st, setSt] = useState(null);
  const kicked = useRef(false);
  const startBridge = useCallback(async () => { try { await api.post(`/api/connectors/${conn.ConnectorId}/wa/bridge/start`); } catch { /* status polling shows the failure */ } }, [conn.ConnectorId]);
  useEffect(() => {
    let alive = true, wasConnected = null;
    const tick = async () => {
      if (!alive) return;
      try {
        const { data } = await api.get(`/api/connectors/${conn.ConnectorId}/wa/status`);
        if (!alive) return;
        setSt(data);
        if (data.connected && wasConnected === false) reload?.();     // just paired: the card's status line changes
        wasConnected = !!data.connected;
        // Node is there and the bridge is not: start it, once per visit - the owner opened this card to pair
        if (data.bridge === false && data.node && !kicked.current && !["installing", "starting", "failed"].includes(data.manager?.phase)) { kicked.current = true; startBridge(); }
        setTimeout(tick, data.connected ? 30000 : data.bridge === false ? (data.node ? 3000 : 6000) : 4000);
      } catch { if (alive) { setSt({ connected: false, bridge: false }); setTimeout(tick, 8000); } }
    };
    tick();
    return () => { alive = false; };
  }, [conn.ConnectorId, reload, startBridge]);
  if (!st) return null;
  const phase = st.manager?.phase, busy = ["installing", "starting"].includes(phase);
  const stepNo = st.connected ? 4 : st.bridge === false ? (st.node ? 2 : 1) : 3;
  const StepLine = ({ n, label, state }) => (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.5 }}>
      <Box sx={{ width: 18, height: 18, borderRadius: "50%", fontSize: 11, fontWeight: 800, display: "grid", placeItems: "center",
        bgcolor: state === "done" ? "#47654a" : state === "now" ? "#55697a" : "#e6e2dc", color: state === "todo" ? DIM : "#fff" }}>{state === "done" ? "✓" : n}</Box>
      <Typography variant="body2" sx={{ fontSize: 13, fontWeight: state === "now" ? 700 : 500, color: state === "todo" ? DIM : INK }}>{label}</Typography>
      {state === "now" && busy && <CircularProgress size={11} sx={{ color: DIM }} />}
    </Box>
  );
  const stateOf = (n) => (n < stepNo ? "done" : n === stepNo ? "now" : "todo");
  return (
    <Box sx={{ p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: PANEL2, display: "flex", gap: 2, alignItems: "flex-start", flexWrap: "wrap" }}>
      <Box sx={{ flex: 1, minWidth: 240 }}>
        <Typography sx={{ fontWeight: 700, fontSize: 13, color: INK }}>Pair with your phone</Typography>
        {!st.connected && (
          <Box sx={{ mb: 1 }}>
            <StepLine n={1} label="Node 18+ on this machine" state={stateOf(1)} />
            <StepLine n={2} label={phase === "installing" ? "Fetching the bridge (a minute or two, first time only)" : "The bridge is running"} state={stateOf(2)} />
            <StepLine n={3} label="Scan the QR from your phone" state={stateOf(3)} />
          </Box>
        )}
        {/* the bridge's own controls, whatever state it is in. A bridge that wedged, or one started before
            the code on disk changed, is fixed HERE - the log's "start it: cd taskuary/whatsapp && node bridge.mjs"
            sent people to a shell for a button's worth of work. The pairing survives a restart: it lives in
            the auth folder, not the process. */}
        <Box sx={{ display: "flex", gap: 1, mt: 0.75, mb: 0.75, flexWrap: "wrap", alignItems: "center" }}>
          <Button size="small" variant="outlined" startIcon={<RestartAltIcon sx={{ fontSize: 15 }} />} disabled={busy}
            title="Stop the running bridge (ours, or one started by hand - found by its port) and start it again from the code on disk. You stay paired."
            onClick={async () => { try { await api.post(`/api/connectors/${conn.ConnectorId}/wa/bridge/restart`); } catch { /* status polling shows the outcome */ } }}>
            Restart bridge
          </Button>
          {st.bridge === false && st.node && !busy && phase !== "failed" && (
            <Button size="small" variant="contained" disableElevation startIcon={<PlayArrowIcon sx={{ fontSize: 15 }} />} onClick={startBridge}>Start bridge</Button>
          )}
          <Typography variant="caption" sx={{ color: FAINT }}>
            {st.connected ? "connected" : st.bridge === false ? "bridge not running" : "bridge up, not paired"}{st.manager?.phase ? ` · ${st.manager.phase}` : ""}
          </Typography>
        </Box>
        {st.connected ? (
          <Box sx={{ mt: 0.5 }}>
            <Typography variant="body2" sx={{ color: "#47654a", fontWeight: 600 }}>✓ Paired{st.me ? ` as ${st.me}` : ""}{st.phone ? ` · ${st.phone}` : ""} — the bridge is connected. Test, then enable.</Typography>
          </Box>
        ) : st.bridge === false && !st.node ? (
          <Typography variant="caption" sx={{ color: DIM, lineHeight: 1.6, display: "block" }}>
            Node is not installed here, and it is the one thing Taskuary cannot install for you. In a terminal:
            <Box component="code" sx={{ ...mono, display: "block", my: 0.5, p: 0.75, bgcolor: "#fff", border: `1px solid ${BORDER}`, borderRadius: 1, fontSize: 12 }}>winget install OpenJS.NodeJS.LTS</Box>
            (or download the LTS from nodejs.org and run the installer). This box re-checks every few seconds and moves on by itself once Node is there.
          </Typography>
        ) : st.bridge === false ? (
          <Box>
            <Typography variant="caption" sx={{ color: phase === "failed" ? "#a33" : DIM, lineHeight: 1.5, display: "block", mb: 0.75 }}>
              {phase === "installing" ? "Fetching the bridge's dependency (Baileys, not bundled on purpose). The QR appears here the moment the bridge is up."
                : phase === "failed" ? `The bridge could not start: ${st.manager.detail}`
                : "Starting the bridge…"}
            </Typography>
            {phase === "failed" && (
              <Button size="small" variant="contained" disableElevation startIcon={<PlayArrowIcon sx={{ fontSize: 15 }} />} onClick={startBridge}>Try again</Button>
            )}
          </Box>
        ) : st.pairing_code ? (
          <Typography variant="body2" sx={{ color: INK, mt: 0.5 }}>
            Enter this code on your phone — WhatsApp → Linked devices → Link a device → Link with phone number:
            <Box component="span" sx={{ ...mono, fontSize: 22, fontWeight: 800, letterSpacing: 3, display: "block", mt: 0.5 }}>{st.pairing_code}</Box>
          </Typography>
        ) : (
          <Typography variant="caption" sx={{ color: DIM, lineHeight: 1.5, display: "block", mt: 0.5 }}>
            On your phone: <b>WhatsApp → Linked devices → Link a device</b>, and scan this. It refreshes by itself as WhatsApp rotates it;
            this box turns green the moment the phone accepts. Nothing to type, no phone number to share.
          </Typography>
        )}
      </Box>
      {!st.connected && st.qr_svg && (
        <Box component="img" src={st.qr_svg} alt="WhatsApp pairing QR" sx={{ width: 220, height: 220, borderRadius: 1, bgcolor: "#fff", border: `1px solid ${BORDER}` }} />
      )}
    </Box>
  );
};

/* ── WhatsApp: the chats the bridge has seen, offered as sources. "Only this group" needs the
   group's JID and there is no directory to browse - the JID appears the moment someone writes in
   the chat. The catch-all covers direct chats; a group only comes in once its JID is added. ── */
const WaChats = ({ conn, mine, reload }) => {
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState("");
  const load = useCallback(async () => {
    try { const { data } = await api.get(`/api/connectors/${conn.ConnectorId}/wa/chats`); setRows(data.data); setErr(""); }
    catch (e) { setRows([]); setErr(e?.response?.data?.detail || "could not reach the bridge"); }
  }, [conn.ConnectorId]);
  useEffect(() => { load(); }, [load]);
  const have = new Set(mine.map((s) => s.Address));
  const add = async (jid) => {
    await api.post("/api/sources", { Channel: "whatsapp", Address: jid, ConnectorId: conn.ConnectorId, Active: true }); reload();
  };
  return (
    <Box sx={{ mb: 1.5, maxWidth: 620 }}>
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.75 }}>
        Chats the bridge has seen since it started — <b>write something in the chat you want</b> (or have someone else), refresh,
        and add it. Direct chats come in on their own; a <b>group</b> joins the funnel only when you add it here.
        <Button size="small" onClick={load} sx={{ ml: 1, fontSize: 11, textTransform: "none", py: 0 }}>refresh</Button>
      </Typography>
      {err && <Typography variant="caption" sx={{ color: "#6b2733", display: "block" }}>✗ {err}</Typography>}
      {rows && !rows.length && !err && <Typography variant="caption" sx={{ color: FAINT }}>nothing seen yet — send a message in a chat and refresh</Typography>}
      {(rows || []).map((r) => (
        <Box key={r.jid} sx={{ display: "flex", alignItems: "center", gap: 1, py: 0.5, borderBottom: `1px solid ${BORDER}` }}>
          <Chip size="small" label={r.group ? "group" : "chat"} sx={{ height: 18, fontSize: 10 }} />
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography variant="body2" sx={{ color: INK, fontWeight: 600 }} noWrap>{r.name || r.jid}</Typography>
            <Typography variant="caption" sx={{ ...mono, color: FAINT, fontSize: 10.5 }} noWrap>{r.jid} · {r.n} msg · {r.last}{r.snippet ? ` · “${r.snippet}”` : ""}</Typography>
          </Box>
          {have.has(r.jid) ? <Typography variant="caption" sx={{ color: "#47654a", fontWeight: 600 }}>✓ source</Typography>
            : <Button size="small" variant="outlined" onClick={() => add(r.jid)} sx={{ fontSize: 11.5, whiteSpace: "nowrap" }}>Add as source</Button>}
        </Box>
      ))}
    </Box>
  );
};

/* ── Sign in with Microsoft: Graph for a regular user, no Azure portal (taskuary/msauth.py).
   A code, microsoft.com/devicelogin, their own account; this box polls until they are done. ── */
const MsSignIn = ({ conn, cfg, reload, onSignedIn }) => {
  const [flow, setFlow] = useState(null);      // {flow, user_code, verification_uri, interval}
  const [state, setState] = useState("");      // "" | ok | error
  const [detail, setDetail] = useState("");
  const [busy, setBusy] = useState(false);
  const [adminUrl, setAdminUrl] = useState("");   // the link IT clicks once; shown when Microsoft says "Need admin approval" or on request
  const signedIn = cfg.auth === "user" && conn.HasSecret;
  useEffect(() => {
    if (!flow) return undefined;
    let alive = true;
    const wait = Math.max(2, flow.interval || 5) * 1000;
    const tick = async () => {
      if (!alive) return;
      try {
        const { data } = await api.post(`/api/connectors/${conn.ConnectorId}/ms/poll`, { flow: flow.flow });
        if (!alive) return;
        if (data.status === "pending") { setTimeout(tick, wait); return; }
        setFlow(null);
        if (data.status === "ok") {
          setState("ok"); setDetail(`Signed in as ${data.name || data.account} — ${data.account} is under Mailboxes below and the first sync is running; mail lands on the Timeline in a minute.`);
          reload(); onSignedIn?.();
        }
        else { setState("error"); setDetail(data.detail || "the sign-in did not complete"); if (data.admin_consent_url) setAdminUrl(data.admin_consent_url); }
      } catch (e) { if (!alive) return; setFlow(null); setState("error"); setDetail(e?.response?.data?.detail || "the sign-in did not complete"); }
    };
    const id = setTimeout(tick, wait);
    return () => { alive = false; clearTimeout(id); };
  }, [flow, conn.ConnectorId, reload]);
  const start = async () => {
    setBusy(true); setState(""); setDetail("");
    try { const { data } = await api.post(`/api/connectors/${conn.ConnectorId}/ms/signin`); setFlow(data); }
    catch (e) { setState("error"); setDetail(e?.response?.data?.detail || "could not start the sign-in"); }
    setBusy(false);
  };
  const signout = async () => { await api.post(`/api/connectors/${conn.ConnectorId}/ms/signout`); setState(""); setDetail(""); setAdminUrl(""); reload(); };
  const copy = (s) => { try { navigator.clipboard?.writeText(s); } catch { /* it is on screen anyway */ } };
  const adminLink = async () => {
    try { const { data } = await api.get(`/api/connectors/${conn.ConnectorId}/ms/adminlink`); setAdminUrl(data.url); }
    catch (e) { setState("error"); setDetail(e?.response?.data?.detail || "could not build the approval link"); }
  };
  return (
    <Box sx={{ p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: PANEL2, display: "flex", flexDirection: "column", gap: 1 }}>
      <Typography sx={{ fontWeight: 700, fontSize: 13, color: INK }}>Sign in with Microsoft</Typography>
      <Typography variant="caption" sx={{ color: DIM, lineHeight: 1.5 }}>
        Your own account, your own mailbox — mail, sending and calendar. No Azure portal, no tenant id, no secret;
        work and personal (Outlook.com) accounts both work. Teams chat reading still needs the tenant app.
      </Typography>
      {signedIn ? (
        <Box sx={{ display: "flex", gap: 1.5, alignItems: "center", flexWrap: "wrap" }}>
          <Typography variant="body2" sx={{ color: "#47654a", fontWeight: 600 }}>✓ Signed in as {cfg.name ? `${cfg.name} · ` : ""}{cfg.account}</Typography>
          <Button size="small" variant="outlined" onClick={signout}>Sign out</Button>
        </Box>
      ) : flow ? (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
          <Typography variant="body2" sx={{ color: INK }}>
            1. Open <a href={flow.verification_uri} target="_blank" rel="noreferrer">{String(flow.verification_uri).replace("https://", "")}</a> and enter this code:
          </Typography>
          <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
            <Typography sx={{ ...mono, fontSize: 26, fontWeight: 800, letterSpacing: 3, color: INK, px: 1.5, py: 0.5,
              bgcolor: "#fff", border: `1px solid ${BORDER}`, borderRadius: 1.5 }}>{flow.user_code}</Typography>
            <IconButton size="small" onClick={() => copy(flow.user_code)} title="copy the code"><ContentCopyIcon sx={{ fontSize: 15 }} /></IconButton>
            <Button size="small" variant="contained" disableElevation component="a" href={flow.verification_uri} target="_blank" rel="noreferrer"
              endIcon={<OpenInNewIcon sx={{ fontSize: 14 }} />}>Open the sign-in page</Button>
          </Box>
          <Typography variant="caption" sx={{ color: DIM, display: "flex", alignItems: "center", gap: 0.75 }}>
            <CircularProgress size={11} /> 2. Sign in with your Microsoft account and accept — this page finishes by itself.
          </Typography>
        </Box>
      ) : (
        <Box sx={{ display: "flex", gap: 1.5, alignItems: "center", flexWrap: "wrap" }}>
          <Button variant="contained" disableElevation disabled={busy} onClick={start}>
            {busy ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : "Sign in with Microsoft"}</Button>
          {!adminUrl && <Button size="small" onClick={adminLink} sx={{ fontSize: 11.5, textTransform: "none", color: DIM }}>Does IT have to approve apps? Get the admin link</Button>}
        </Box>
      )}
      {detail && <Typography variant="body2" sx={{ fontWeight: 600, color: state === "ok" ? "#47654a" : "#6b2733" }}>
        {state === "ok" ? "✓" : "✗"} {detail}</Typography>}
      {adminUrl && !signedIn && (
        <Box sx={{ p: 1.25, border: `1px dashed ${BORDER}`, borderRadius: 1.5, bgcolor: "#fff", display: "flex", flexDirection: "column", gap: 0.5 }}>
          <Typography variant="body2" sx={{ fontWeight: 700, color: INK }}>Approval link for your Microsoft 365 admin</Typography>
          <Typography variant="caption" sx={{ color: DIM, lineHeight: 1.5 }}>
            Forward this to whoever runs your Microsoft 365. They sign in, click Accept once, and everyone in your organisation can
            sign in above. It is a consent grant, not an app registration - nothing to build on their side. Then click Sign in with Microsoft again.
          </Typography>
          <Box sx={{ display: "flex", gap: 0.5, alignItems: "center" }}>
            <Typography sx={{ ...mono, fontSize: 11, color: INK, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{adminUrl}</Typography>
            <IconButton size="small" onClick={() => copy(adminUrl)} title="copy the link"><ContentCopyIcon sx={{ fontSize: 15 }} /></IconButton>
            <IconButton size="small" component="a" href={adminUrl} target="_blank" rel="noreferrer" title="open it (if you are the admin)"><OpenInNewIcon sx={{ fontSize: 15 }} /></IconButton>
          </Box>
        </Box>
      )}
    </Box>
  );
};

const ProcessingStep = ({ conn, reload, n }) => {
  const [cfg, setCfg] = useState(parse(conn.ConfigJson));
  const [anchor, setAnchor] = useState(null);
  useEffect(() => { setCfg(parse(conn.ConfigJson)); }, [conn.ConfigJson]);
  const mode = cfg.bulk === "rank" ? "rank" : "clear";
  const set = async (v) => {
    const next = { ...cfg, bulk: v }; setCfg(next);
    await api.post("/api/connectors", { ConnectorId: conn.ConnectorId, ConfigJson: JSON.stringify(next) }); reload();
  };
  return (
    <Box sx={{ mt: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        <Typography variant="caption" sx={{ ...mono, color: FAINT, letterSpacing: 1, fontSize: 10 }}>
          {n} · PROCESSING — ONE BY ONE, OR RANKED TOGETHER
        </Typography>
        <IconButton size="small" onClick={(e) => setAnchor(e.currentTarget)} title="How the two modes work" sx={{ p: 0.25 }}>
          <InfoOutlinedIcon sx={{ fontSize: 14, color: FAINT }} />
        </IconButton>
        <Popover open={!!anchor} anchorEl={anchor} onClose={() => setAnchor(null)}
          anchorOrigin={{ vertical: "bottom", horizontal: "left" }} transformOrigin={{ vertical: "top", horizontal: "left" }}>
          {BULK_HELP}
        </Popover>
      </Box>
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5, mb: 0.75 }}>
        How tasks from this connection reach the agents. Applies to every task it creates; the Timeline’s funnel bar and the Board’s Queued lane follow it.
      </Typography>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "minmax(0, 1fr) minmax(0, 1fr)" }, gap: 1 }}>
        {MODES.map(([v, title, desc]) => (
          <Box key={v} onClick={() => set(v)}
            sx={{ p: 1.25, borderRadius: 2, cursor: "pointer", bgcolor: PANEL,
              border: `${mode === v ? 1.5 : 1}px solid ${mode === v ? "#6f8a6e" : BORDER}`,
              "&:hover": { borderColor: "#6f8a6e" } }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
              <Radio size="small" checked={mode === v} sx={{ p: 0 }} />
              <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13 }}>{title}</Typography>
              {v === "clear" && <Typography variant="caption" sx={{ color: FAINT }}>default</Typography>}
            </Box>
            <Typography variant="caption" sx={{ color: DIM, display: "block", mt: 0.5, lineHeight: 1.5 }}>{desc}</Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
};

const InboundStep = ({ conn, m, mine, reload }) => {
  const [roles, toggle] = useRoles(conn, reload);
  const [cfg, setCfg] = useState(parse(conn.ConfigJson));
  const [saved, setSaved] = useState("");
  const [ask, setAsk] = useState(null);           // the public-repo question, asked in-app
  useEffect(() => { setCfg(parse(conn.ConfigJson)); }, [conn.ConfigJson]);
  const gh = conn.Type === "github";
  const on = roles.has("trigger") || roles.has("feed") || (gh && ghInboundExplicit(mine));
  const prompts = promptsFor(conn.Type);
  const savePrompts = async () => {
    await api.post("/api/connectors", { ConnectorId: conn.ConnectorId, ConfigJson: JSON.stringify(cfg) });
    setSaved("saved ✓"); setTimeout(() => setSaved(""), 2500); reload();
  };
  return (
    <Box sx={{ mt: 1, maxWidth: 640 }}>
      {/* 1 — the switch: does this connection create work at all */}
      <Typography variant="caption" sx={{ ...mono, color: FAINT, letterSpacing: 1, fontSize: 10 }}>
        1 · DOES IT CREATE WORK
      </Typography>
      {["trigger", "feed"].map((key) => (
        <RoleRow key={key} on={roles.has(key)} onToggle={() => toggle(key)}
          label={ROLE_META[key][0]} desc={ROLE_META[key][1]} />
      ))}

      {/* 2 — github only: what each repo's items do, overriding the switch per repo */}
      {gh && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="caption" sx={{ ...mono, color: FAINT, letterSpacing: 1, fontSize: 10 }}>
            2 · PER REPO — WHAT ISSUES AND PRS DO
          </Typography>
          <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5, mb: 0.5 }}>
            <b>tasks</b> = through triage, <b>feed</b> = shown on the Timeline only, <b>off</b> = ignored.
            The third picker says <b>whose</b> items may start a coding agent by themselves: <b>team</b> =
            owners, members and collaborators; <b>contributors</b> adds anyone who has had a change merged;
            <b>anyone</b> = every author. Everyone else’s items still become tasks for you to promote.
            A picker set here pulls that repo whatever the switches above say; picking saves instantly.
          </Typography>
          {mine.filter((s) => s.Active).map((s) => {
            const gc = parse(s.ConfigJson);
            return (
              <Box key={s.SourceId} sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1, borderBottom: `1px solid ${BORDER}` }}>
                <Typography sx={{ ...mono, color: INK, flex: 1, fontSize: 13 }} noWrap>{s.Address}</Typography>
                {gc.private === false && <Chip size="small" label="public" sx={{ height: 18, fontSize: 9.5, bgcolor: "#f1e1da", color: "#6b2733" }} />}
                {["issues", "prs", "auto"].map((kind) => (
                  <Select key={kind} size="small" value={gc[kind] || (kind === "issues" ? "tasks" : "off")}
                    sx={{ fontSize: 11.5, height: 26, ".MuiSelect-select": { py: 0.4 } }}
                    onChange={(e) => {
                      const v = e.target.value;
                      const apply = async () => {
                        await api.post("/api/sources", { SourceId: s.SourceId, ConfigJson: JSON.stringify({ ...gc, [kind]: v }) });
                        reload();
                      };
                      // a public repo: anyone on the internet can open a PR, and with this on each one
                      // may start an agent (the session cap still holds - Settings → Agents at once, 4 by default)
                      if (kind === "auto" && v !== "off" && gc.private !== true) {
                        const who = v === "anyone" ? "any author's" : v === "contributors" ? "any past contributor's" : "any team member's";
                        setAsk({ title: `${s.Address} is ${gc.private === false ? "a public repo" : "not known to be private"}`,
                          text: `With "${v}" on, ${who} PR or issue can start a coding agent by itself. Uncontrolled PRs mean uncontrolled agents, limited only by the session cap (Settings → Agents at once).`,
                          label: `Turn on "${v}" anyway`, onConfirm: apply });
                        return;
                      }
                      apply();
                    }}>
                    {(kind === "auto" ? ["off", "team", "contributors", "anyone"] : ["tasks", "feed", "off"]).map((v) => (
                      <MenuItem key={v} value={v} sx={{ fontSize: 12 }}>
                        {kind === "prs" ? "PRs" : kind === "issues" ? "issues" : "agent"}: {v}</MenuItem>
                    ))}
                  </Select>
                ))}
              </Box>
            );
          })}
        </Box>
      )}
      {/* processing: one by one, or ranked together - every inbound card, whether on or not */}
      {ask && <Confirm open title={ask.title} text={ask.text} confirmLabel={ask.label} onConfirm={ask.onConfirm} onClose={() => setAsk(null)} />}
      <ProcessingStep conn={conn} reload={reload} n={gh ? "3" : "2"} />
      {/* the standing prompt, right where inbound is decided */}
      {prompts.length > 0 && (
        <Box sx={{ mt: 2, opacity: on ? 1 : 0.5 }}>
          <Typography variant="caption" sx={{ ...mono, color: FAINT, letterSpacing: 1, fontSize: 10 }}>
            {gh ? "4" : "3"} · WHAT THE AGENT IS TOLD ABOUT WORK FROM HERE
            {on ? "" : " — turn inbound on above first"}
          </Typography>
          {prompts.map(([key, label, hint]) => (
            <TextField key={key} fullWidth multiline minRows={2} label={label} helperText={hint}
              value={cfg[key] || ""} onChange={(e) => setCfg({ ...cfg, [key]: e.target.value })}
              sx={{ bgcolor: "#fff", mt: 1.5 }} />
          ))}
          <Box sx={{ display: "flex", gap: 1, alignItems: "center", mt: 1.5 }}>
            <Button size="small" variant="contained" disableElevation onClick={savePrompts}>Save prompts</Button>
            {saved && <Typography variant="body2" sx={{ color: "#47654a", fontWeight: 600 }}>{saved}</Typography>}
          </Box>
        </Box>
      )}
    </Box>
  );
};

/* What "Get AI to set it up" hands the coding agent. The Guide is written for a person; these
   steps are written for the agent - and where a card has none, the agent works from the Guide
   under the one standing rule the caption states. */
const AgentTab = ({ steps }) => (
  <Box>
    <Typography variant="body2" sx={{ color: DIM, mb: 1, maxWidth: 720, mx: "auto" }}>
      What <b>Get AI to set it up</b> hands your coding agent, on top of one standing rule: anything on this machine —
      installs, starting processes, commands, config, the API — is the agent's own job; only your accounts, phone,
      browser or admin console are yours to do. {steps?.length ? "These steps are written for the agent:" :
        "This connector has no agent-specific steps yet, so the agent works from the Guide under that rule."}
    </Typography>
    {!!steps?.length && <Steps steps={steps} />}
  </Box>
);

const Steps = ({ steps }) => (
  <Box sx={{ maxWidth: 720, mx: "auto" }}>
    {steps.map((step, i) => (
      <Box key={i} sx={{ display: "flex", gap: 1.5, py: 1.25, borderBottom: `1px solid ${BORDER}` }}>
        <Box sx={{ ...mono, width: 24, height: 24, borderRadius: "50%", bgcolor: "#eae4d8", color: "#55697a",
          fontSize: 12, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>{i + 1}</Box>
        <Typography variant="body2" sx={{ color: INK, lineHeight: 1.55 }}>{step}</Typography>
      </Box>
    ))}
  </Box>
);
