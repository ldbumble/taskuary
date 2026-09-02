// Brand marks for the connector catalog. A product named on a card should wear its OWN
// logo - a bug glyph for Jira and the same bar chart for six different databases read as
// "not finished yet". These are hand-drawn simplified marks (iconic geometry and official
// brand colors, clean at 20px), not the vendors' official asset files: nominative use to
// identify what each connection talks to. Anything without a mark here falls back to the
// tinted Material glyph in ui.jsx.
import React from "react";

// Every logo is a 24x24 viewBox and colors itself (multi-color where the real mark is),
// so `sx.color` deliberately does NOT tint them - only `fontSize` sizes them.
const S = ({ children, sx }) => (
  <svg viewBox="0 0 24 24" width="1em" height="1em" aria-hidden
    style={{ fontSize: sx?.fontSize ?? 15, display: "block", flexShrink: 0 }}>
    {children}
  </svg>
);

// Monogram tiles for brands whose marks are wordmarks or too intricate at 20px: the brand's
// own colour and initial, which is how their favicons read at this size anyway.
const T = ({ p, bg, fg = "#fff", text, size = 11, weight = 800 }) => (
  <S {...p}>
    <rect x="2" y="2" width="20" height="20" rx="5" fill={bg} />
    <text x="12" y="12" textAnchor="middle" dominantBaseline="central" fontSize={size} fontWeight={weight}
      fontFamily="IBM Plex Sans, system-ui, sans-serif" fill={fg}>{text}</text>
  </S>
);

export const LOGOS = {
  // dark slate, not the brand mid-tone: on oat paper the lighter envelope read as disabled
  email: (p) => (
    <S {...p}>
      <rect x="1.5" y="4.5" width="21" height="15" rx="2.5" fill="#3a4a58" />
      <path fill="none" stroke="#fffdfb" strokeWidth="1.9" strokeLinejoin="round" d="M3.8 7.3l8.2 6.2 8.2-6.2" />
    </S>
  ),
  outlook: (p) => (
    <S {...p}>
      <rect x="6" y="4" width="16" height="16" rx="2" fill="#0F6CBD" />
      <path fill="#fff" d="M9 8.5h10v7a1 1 0 0 1-1 1h-8v-8zm1.2 1.2v5.6h7.6v-5.6l-3.8 2.6-3.8-2.6z" />
      <rect x="2" y="7" width="10" height="10" rx="1.5" fill="#28A8EA" />
      <ellipse cx="7" cy="12" rx="2.6" ry="3.1" fill="none" stroke="#fff" strokeWidth="1.6" />
    </S>
  ),
  teams: (p) => (
    <S {...p}>
      <rect x="2" y="6" width="13" height="13" rx="2" fill="#5059C9" />
      <path fill="#fff" d="M5.2 9.5h6.6v1.6H9.6v5.4H7.4v-5.4H5.2z" />
      <circle cx="18.5" cy="8" r="2.4" fill="#7B83EB" />
      <path fill="#7B83EB" d="M15.5 11.5h5.2a1.3 1.3 0 0 1 1.3 1.3v3.4a3 3 0 0 1-3 3h-.3a4.6 4.6 0 0 0 .2-1.4v-6.3z" />
    </S>
  ),
  whatsapp: (p) => (
    <S {...p}>
      {/* the familiar mark: a speech bubble with a tail at lower-left and a handset inside - the
          old path was a blob at 17px */}
      <circle cx="12" cy="12" r="11" fill="#25D366" />
      <path fill="#fff" d="M12 4.6a7.3 7.3 0 0 0-6.3 11l-1.1 4 4.1-1.1A7.3 7.3 0 1 0 12 4.6zm0 1.5a5.8 5.8 0 1 1-3 10.8l-.3-.2-2.4.6.6-2.3-.2-.3A5.8 5.8 0 0 1 12 6.1zm-2.4 2.8c-.2 0-.5.1-.8.4-.3.3-.8.8-.8 1.8s.8 2.1.9 2.3c.1.1 1.6 2.5 3.8 3.4 1.9.8 2.3.6 2.7.6.4-.1 1.3-.6 1.5-1.1.2-.6.2-1 .1-1.1l-.5-.3-1.5-.7c-.2-.1-.4-.1-.5.1l-.7.9c-.1.2-.3.2-.5.1-.7-.3-1.4-.8-2-1.3-.5-.5-1-1.2-1.2-1.7-.1-.2 0-.3.1-.4l.4-.4.3-.5c.1-.2 0-.3 0-.5l-.7-1.6c-.1-.3-.3-.3-.5-.3h-.4z" />
    </S>
  ),
  gmail: (p) => (
    <S {...p}>
      <rect x="2" y="5" width="20" height="14" rx="1.5" fill="#fff" stroke="#e0dcd4" />
      <path fill="#EA4335" d="M2 6.5v1.6l10 6.6 10-6.6V6.5L12 13z" />
      <path fill="#4285F4" d="M2 8.1V19h4.2v-8.1z" />
      <path fill="#34A853" d="M17.8 10.9V19H22V8.1z" />
      <path fill="#FBBC04" d="M2 6.5 6.2 9.3V5.7z" /><path fill="#C5221F" d="M22 6.5 17.8 9.3V5.7z" />
    </S>
  ),
  imap: (p) => (
    <S {...p}>
      <rect x="2" y="5" width="20" height="14" rx="2" fill="#6e685f" />
      <path fill="none" stroke="#fff" strokeWidth="1.7" strokeLinejoin="round" d="M4 7.5l8 6 8-6" />
    </S>
  ),
  clickup: (p) => (
    <S {...p}>
      <path fill="#7B68EE" d="M4 15.5l2.6-2c1.6 2 3.2 3 5.4 3s3.8-1 5.4-3l2.6 2c-2.2 2.9-4.9 4.4-8 4.4s-5.8-1.5-8-4.4z" />
      <path fill="#FF3E9C" d="M12 4l6.6 5.7-2.1 2.4L12 8.3l-4.5 3.8-2.1-2.4z" />
    </S>
  ),
  todoist: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="5" fill="#E44332" />
      <path fill="none" stroke="#fff" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" d="M5.5 10.2l4.2 2.3 8.8-5.1M5.5 14.2l4.2 2.3 8.8-5.1" />
    </S>
  ),
  netsuite: (p) => <T p={p} bg="#125580" text="NS" size={9.5} />,
  quickbooks: (p) => <T p={p} bg="#2CA01C" text="qb" size={10.5} />,
  teller: (p) => <T p={p} bg="#1a1a1a" text="T" size={12} />,
  sap: (p) => <T p={p} bg="#0FAAFF" text="SAP" size={8.5} />,
  workday: (p) => <T p={p} bg="#F38B00" text="W" size={12} />,
  adp: (p) => <T p={p} bg="#D0271D" text="ADP" size={8} />,
  epic: (p) => <T p={p} bg="#B71C1C" text="E" size={12} />,
  cerner: (p) => <T p={p} bg="#C74634" text="C" size={12} />,
  pointclickcare: (p) => <T p={p} bg="#00A3E0" text="PCC" size={7.5} />,
  gcp: (p) => <T p={p} bg="#4285F4" text="G" size={12} />,
  kubernetes: (p) => <T p={p} bg="#326CE5" text="k8s" size={8.5} />,
  grafana: (p) => <T p={p} bg="#F46800" text="G" size={12} />,
  elastic: (p) => <T p={p} bg="#FEC514" fg="#262521" text="es" size={10.5} />,
  perplexity: (p) => <T p={p} bg="#20808D" text="P" size={12} />,
  serpapi: (p) => <T p={p} bg="#3F51B5" text="S" size={12} />,
  browserbase: (p) => <T p={p} bg="#F45B22" text="bb" size={10.5} />,
  sqlite: (p) => <T p={p} bg="#0F80CC" text="sql" size={8.5} />,
  local_file: (p) => (
    <S {...p}>
      <path fill="#a09787" d="M6 2h8l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" />
      <path fill="#e9e3d8" d="M14 2v5h5z" />
    </S>
  ),
  anthropic: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="5" fill="#D97757" />
      <path fill="#fff" d="M10.6 6.5h2.8L18 17.5h-2.6l-.9-2.4H9.5l-.9 2.4H6l4.6-11zm.2 6.6h3.4L12.5 8.8l-1.7 4.3z" />
    </S>
  ),
  openai: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="5" fill="#0f0f0f" />
      <circle cx="12" cy="12" r="5.6" fill="none" stroke="#fff" strokeWidth="1.8" />
      <path fill="none" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" d="M12 6.4v3.2M12 14.4v3.2M6.9 9.2l2.8 1.6M14.3 13.2l2.8 1.6M6.9 14.8l2.8-1.6M14.3 10.8l2.8-1.6" />
    </S>
  ),
  azure_openai: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="5" fill="#0078D4" />
      <path fill="#fff" d="M11.2 6h3.1l4.2 12h-2.9l-.9-2.7h-4.6L8.6 18H5.7l5.5-12zm.4 6.9h3.1l-1.5-4.6-1.6 4.6z" />
    </S>
  ),
  openrouter: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="5" fill="#6467F2" />
      <path fill="none" stroke="#fff" strokeWidth="1.9" strokeLinecap="round" d="M5.5 12h3.2c2.6 0 3.2-4 6-4H17M5.5 12h3.2c2.6 0 3.2 4 6 4H17" />
      <path fill="#fff" d="M16.4 5.6L19.6 8l-3.2 2.4zM16.4 13.6l3.2 2.4-3.2 2.4z" />
    </S>
  ),
  ollama: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="5" fill="#f4f1ea" stroke="#d8d2c6" />
      <path fill="#262521" d="M8.2 5.4c.7 0 1.2 1.1 1.3 2.5a3.9 3.9 0 0 1 5 0c.1-1.4.6-2.5 1.3-2.5.8 0 1.3 1.6 1.1 3.4 1 .9 1.6 2.1 1.6 3.4 0 .8-.2 1.5-.6 2.1.4.6.6 1.4.6 2.2v2h-1.8v-2c0-.6-.2-1.1-.5-1.5-.9.8-2.2 1.3-3.7 1.3s-2.8-.5-3.7-1.3c-.3.4-.5.9-.5 1.5v2H6.5v-2c0-.8.2-1.6.6-2.2-.4-.6-.6-1.3-.6-2.1 0-1.3.6-2.5 1.6-3.4-.2-1.8.3-3.4 1.1-3.4zm3.8 4.2c-1.9 0-3.4 1.2-3.4 2.7s1.5 2.7 3.4 2.7 3.4-1.2 3.4-2.7-1.5-2.7-3.4-2.7zm-1.2 1.6a.7.7 0 1 1 0 1.4.7.7 0 0 1 0-1.4zm2.4 0a.7.7 0 1 1 0 1.4.7.7 0 0 1 0-1.4z" />
    </S>
  ),
  // ── AI — voice: speech to text. Brand tiles where the brand has a mark; a waveform for the
  //    two that are "a Whisper somewhere" - one with a plug (a server), one with a house (local).
  groq_stt: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="5" fill="#F55036" />
      <path fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" d="M15.6 10.2A4 4 0 1 0 12 15.9h2.4a1.6 1.6 0 0 1 1.6 1.6V19" />
    </S>
  ),
  openai_stt: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="5" fill="#0f0f0f" />
      <circle cx="12" cy="12" r="5.6" fill="none" stroke="#fff" strokeWidth="1.8" />
      <path fill="none" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" d="M12 6.4v3.2M12 14.4v3.2M6.9 9.2l2.8 1.6M14.3 13.2l2.8 1.6M6.9 14.8l2.8-1.6M14.3 10.8l2.8-1.6" />
    </S>
  ),
  deepgram: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="5" fill="#13EF93" />
      <path fill="#0b1f19" d="M8 6.5h4.2c3.2 0 5.3 2.2 5.3 5.5s-2.1 5.5-5.3 5.5H8V6.5zm2.6 2.4v6.2h1.5c1.7 0 2.7-1.2 2.7-3.1s-1-3.1-2.7-3.1h-1.5z" />
    </S>
  ),
  elevenlabs_stt: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="5" fill="#000" />
      <rect x="8" y="6.5" width="2.6" height="11" rx=".6" fill="#fff" />
      <rect x="13.4" y="6.5" width="2.6" height="11" rx=".6" fill="#fff" />
    </S>
  ),
  stt_server: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="5" fill="#55697a" />
      <path fill="none" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" d="M5.5 12h1.2M8.4 9v6M11.2 6.5v11M14 8.5v7M16.8 10.5v3M19 12h-.6" />
    </S>
  ),
  local_whisper: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="5" fill="#6f8a6e" />
      <path fill="#fff" d="M12 5.2l6.2 5.2h-1.7v2.2h-9v-2.2H5.8z" opacity=".95" />
      <path fill="none" stroke="#fff" strokeWidth="1.7" strokeLinecap="round" d="M7.4 16.5v2M9.7 14.8v3.7M12 13.6v4.9M14.3 14.8v3.7M16.6 16.5v2" />
    </S>
  ),
  cli: (p) => (
    <S {...p}>
      <rect x="2" y="3" width="20" height="18" rx="3" fill="#1e1e2e" />
      <path fill="none" stroke="#a6e3a1" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" d="M6.5 8.5l3.5 3.5-3.5 3.5" />
      <path stroke="#cdd6f4" strokeWidth="1.9" strokeLinecap="round" d="M12 15.5h5.5" />
    </S>
  ),
  github: (p) => (
    <S {...p}>
      <circle cx="12" cy="12" r="10" fill="#24292f" />
      <path fill="#fff" d="M12 5.8a6.2 6.2 0 0 0-1.96 12.08c.31.06.42-.13.42-.3v-1.1c-1.72.37-2.09-.73-2.09-.73-.28-.72-.69-.91-.69-.91-.56-.38.04-.37.04-.37.62.04.95.64.95.64.55.95 1.45.68 1.8.52.06-.4.22-.68.39-.83-1.37-.16-2.82-.69-2.82-3.06 0-.68.24-1.23.64-1.66-.07-.16-.28-.79.06-1.64 0 0 .52-.17 1.7.63a5.9 5.9 0 0 1 3.1 0c1.18-.8 1.7-.63 1.7-.63.34.85.13 1.48.06 1.64.4.43.64.98.64 1.66 0 2.38-1.45 2.9-2.83 3.05.22.19.42.57.42 1.15v1.7c0 .17.11.36.43.3A6.2 6.2 0 0 0 12 5.8z" />
    </S>
  ),
  slack: (p) => (
    <S {...p}>
      <rect x="7.2" y="2" width="3.5" height="20" rx="1.75" fill="#36C5F0" />
      <rect x="13.3" y="2" width="3.5" height="20" rx="1.75" fill="#2EB67D" />
      <rect x="2" y="7.2" width="20" height="3.5" rx="1.75" fill="#ECB22E" />
      <rect x="2" y="13.3" width="20" height="3.5" rx="1.75" fill="#E01E5A" />
    </S>
  ),
  telegram: (p) => (
    <S {...p}>
      <circle cx="12" cy="12" r="10" fill="#229ED9" />
      <path fill="#fff" d="M17.4 7.3l-1.9 9.1c-.14.64-.53.8-1.07.5l-2.94-2.17-1.42 1.37c-.16.16-.29.29-.58.29l.21-2.97 5.4-4.88c.23-.2-.05-.32-.36-.12l-6.67 4.2-2.88-.9c-.62-.2-.63-.62.13-.92l11.2-4.32c.52-.19.97.12.8.92z" />
    </S>
  ),
  // Messages: the bubble on its green rounded square, the same white-glyph-on-brand-shape
  // as the Telegram and WhatsApp marks beside it, so the row reads at one fidelity at 15px
  imessage: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="4.6" fill="#34C759" />
      <path fill="#fff" d="M12 6.6C8.2 6.6 5.6 8.9 5.6 11.7c0 1.6.85 3 2.2 3.9-.15.8-.55 1.6-1.1 2.2 1.3-.15 2.45-.6 3.35-1.3.6.2 1.25.3 1.95.3 3.8 0 6.4-2.3 6.4-5.1S15.8 6.6 12 6.6z" />
    </S>
  ),
  discord: (p) => (
    <S {...p}>
      <path fill="#5865F2" d="M19.6 6.3a15.6 15.6 0 0 0-3.9-1.2l-.26.53c1.2.35 2.25.85 3.2 1.47a12.4 12.4 0 0 0-9.3 0c.95-.62 2-1.12 3.2-1.47L12.3 5.1a15.6 15.6 0 0 0-3.9 1.2C5.9 10.1 5.2 13.8 5.5 17.4a15.4 15.4 0 0 0 4.7 2.4l.6-1c-.77-.29-1.5-.66-2.15-1.12l.44-.36a11.1 11.1 0 0 0 9.4 0l.44.36c-.65.46-1.38.83-2.15 1.12l.6 1a15.4 15.4 0 0 0 4.7-2.4c.35-4.2-.55-7.9-2.4-11.1zM9.6 15c-.92 0-1.68-.85-1.68-1.9s.74-1.9 1.68-1.9c.94 0 1.7.86 1.68 1.9 0 1.05-.75 1.9-1.68 1.9zm5.1 0c-.92 0-1.68-.85-1.68-1.9s.74-1.9 1.68-1.9c.94 0 1.7.86 1.68 1.9 0 1.05-.74 1.9-1.68 1.9z" />
    </S>
  ),
  gitlab: (p) => (
    <S {...p}>
      <path fill="#E24329" d="M12 21.6l3.5-10.8H8.5z" />
      <path fill="#FC6D26" d="M12 21.6L8.5 10.8H3.6z" />
      <path fill="#FCA326" d="M3.6 10.8l-1.06 3.27a.72.72 0 0 0 .26.8L12 21.6z" />
      <path fill="#E24329" d="M3.6 10.8h4.9L6.4 4.3a.36.36 0 0 0-.69 0z" />
      <path fill="#FC6D26" d="M12 21.6l3.5-10.8h4.9z" />
      <path fill="#FCA326" d="M20.4 10.8l1.06 3.27a.72.72 0 0 1-.26.8L12 21.6z" />
      <path fill="#E24329" d="M20.4 10.8h-4.9l2.1-6.5a.36.36 0 0 1 .69 0z" />
    </S>
  ),
  jira: (p) => (
    <S {...p}>
      <path fill="#2684FF" d="M12 1.8l8.6 8.6a1.2 1.2 0 0 1 0 1.7L12 20.7l-3.1-3.1L14.4 12 8.9 6.5z" />
      <path fill="#0052CC" d="M12 8.9l3.1 3.1L12 15.1 8.9 12z" />
      <path fill="#2684FF" opacity=".7" d="M8.9 6.5L5.8 3.4 2 7.2l3.1 3.1zm0 11L5.8 20.6 2 16.8l3.1-3.1z" />
    </S>
  ),
  azdo: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="3.4" fill="#0078D4" />
      <path fill="#fff" d="M8.3 8.1c1.4 0 2.4.9 3.1 1.9l.6.9.6-.9c.7-1 1.7-1.9 3.1-1.9 2.1 0 3.6 1.7 3.6 3.9s-1.5 3.9-3.6 3.9c-1.4 0-2.4-.9-3.1-1.9l-.6-.9-.6.9c-.7 1-1.7 1.9-3.1 1.9-2.1 0-3.6-1.7-3.6-3.9s1.5-3.9 3.6-3.9zm0 1.9c-1 0-1.7.9-1.7 2s.7 2 1.7 2c.7 0 1.3-.5 1.9-1.4l.4-.6-.4-.6c-.6-.9-1.2-1.4-1.9-1.4zm7.4 0c-.7 0-1.3.5-1.9 1.4l-.4.6.4.6c.6.9 1.2 1.4 1.9 1.4 1 0 1.7-.9 1.7-2s-.7-2-1.7-2z" />
    </S>
  ),
  asana: (p) => (
    <S {...p}>
      <circle cx="12" cy="6.4" r="3.5" fill="#F06A6A" />
      <circle cx="5.9" cy="16" r="3.5" fill="#F06A6A" />
      <circle cx="18.1" cy="16" r="3.5" fill="#F06A6A" />
    </S>
  ),
  monday: (p) => (
    <S {...p}>
      <rect x="2.6" y="7" width="4.4" height="10" rx="2.2" fill="#FF3D57" />
      <rect x="9.8" y="7" width="4.4" height="10" rx="2.2" fill="#FFCB00" />
      <rect x="17" y="7" width="4.4" height="10" rx="2.2" fill="#00CA72" />
    </S>
  ),
  linear: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="4.6" fill="#5E6AD2" />
      <g fill="#fff">
        <path d="M6.1 14.9l6.2 6.2q-1.1.1-1.9 0L6.1 16.8z" opacity=".9" />
        <path d="M5.2 11.2l9.9 9.9q-1 .3-2 .4L4.8 13.2q.1-1 .4-2z" />
        <path d="M6.6 7.9l11.7 11.7q-.8.6-1.6 1L5.6 9.5q.4-.8 1-1.6z" />
        <path d="M9.7 5.6l10.9 10.9q-.4.9-1 1.6L8.1 6.6q.7-.6 1.6-1z" />
      </g>
    </S>
  ),
  trello: (p) => (
    <S {...p}>
      <rect x="2.5" y="2.5" width="19" height="19" rx="3.2" fill="#0079BF" />
      <rect x="5.4" y="5.6" width="5.6" height="11.2" rx="1.1" fill="#fff" />
      <rect x="13" y="5.6" width="5.6" height="7" rx="1.1" fill="#fff" />
    </S>
  ),
  notion: (p) => (
    <S {...p}>
      <rect x="2.6" y="2.6" width="18.8" height="18.8" rx="3" fill="#fff" stroke="#37352F" strokeWidth="1.4" />
      <path fill="#37352F" d="M8.2 7.4v9.2h1.85v-5.75l4.05 5.75h1.7V7.4h-1.85v5.55L9.95 7.4z" />
    </S>
  ),
  sentry: (p) => (
    <S {...p}>
      <path fill="#362D59" d="M13.55 2.7a1.8 1.8 0 0 0-3.1 0L7.5 7.8l2 1.15 2.95-5.1 8.2 14.2h-3.4a10.6 10.6 0 0 0-3.05-6.4l-1.65 1.65a8.3 8.3 0 0 1 2.4 4.75h-2.3a6 6 0 0 0-1.75-3.1l-1.65 1.65a3.8 3.8 0 0 1 1.1 1.45H4.9l2.6-4.5-2-1.15-2.95 5.1A1.8 1.8 0 0 0 4.1 21.3h16a1.8 1.8 0 0 0 1.55-2.7z" />
    </S>
  ),
  pagerduty: (p) => (
    <S {...p}>
      <path fill="#06AC38" d="M4.7 2.9h6.1c3.9 0 6.4 2 6.4 5.4s-2.6 5.5-6.6 5.5H7.9v3.4H4.7zm3.2 8.1h2.6c2.2 0 3.4-.95 3.4-2.65 0-1.75-1.25-2.6-3.4-2.6H7.9z" />
      <rect x="4.7" y="18.4" width="3.2" height="2.7" fill="#06AC38" />
    </S>
  ),
  // AWS has no standalone symbol - the smile IS the recognizable half, and the "aws"
  // wordmark under it turns to mud at 20px, so the square carries the smile alone
  aws: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="3.4" fill="#FF9900" />
      <path fill="#fff" d="M4.6 13.4c3.2 2.4 7.2 3.7 11.2 3.7 1.5 0 3-.2 4.4-.6.5-.15.85.4.35.8-1.9 1.5-4.6 2.3-7 2.3-3.7 0-7.3-1.5-9.9-4.2-.5-.5-.05-1.2.5-.9l.45.3z" />
      <path fill="#fff" d="M17.2 12.5c.9-.4 2-.25 2.35.15.4.5-.05 2.2-.85 3.1-.25.3-.6.1-.5-.25.35-.9.75-2.2.45-2.5-.3-.3-1.8-.15-2.55-.05-.3.05-.4-.25-.1-.4z" />
    </S>
  ),
  azure: (p) => (
    <S {...p}>
      <path fill="#0078D4" d="M9.15 3.4h4.4L8.9 17.35l-6.4 1.05z" />
      <path fill="#0078D4" opacity=".7" d="M15.75 3.4h-2.2l-1.5 4.35 4.35 12.85H21.5z" />
      <path fill="#0078D4" d="M12.05 7.75L6.3 19.85l9.6-1.05 4.35 1.8-8.2-12.85z" opacity=".85" />
    </S>
  ),
  /* Sage's mark is a leaf-ish arrow in their green; simplified to the shape that survives
     at 20px - the swoop and the counter, on the brand square. */
  intacct: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="4.2" fill="#00D639" />
      <path fill="#0A1E14" d="M17.8 8.3c-1.5-1.5-3.8-2-5.9-1.4-2.4.7-4 2.7-4 5 0 1.5.8 2.6 2.4 3.2l2.6 1c.7.3 1 .6 1 1.1 0 .7-.7 1.2-1.8 1.2-1.3 0-2.5-.5-3.5-1.5l-1.4 1.9c1.4 1.3 3.1 2 5 2 2.7 0 4.6-1.5 4.6-3.8 0-1.5-.8-2.6-2.5-3.3l-2.6-1c-.6-.25-.9-.55-.9-1 0-.75.8-1.35 2-1.35 1.1 0 2.2.4 3.1 1.2z" />
    </S>
  ),
  prometheus: (p) => (
    <S {...p}>
      <circle cx="12" cy="12" r="10" fill="#E6522C" />
      <path fill="#fff" d="M12 4.6c1.3 1.9 1 3.2.2 4.3-.8 1.1-1.3 2.2-1.3 3.3 0 1.6 1.1 2.6 2.4 2.6-1.9.9-4.3-.3-4.3-2.8 0-1.3.6-2.3 1.2-3.3.8-1.2 1.4-2.4 1.8-4.1z" />
      <rect x="7.2" y="15.6" width="9.6" height="1.8" rx=".9" fill="#fff" />
      <path fill="#fff" d="M8.6 18.4h6.8c-.35 1.05-1.6 1.7-3.4 1.7s-3.05-.65-3.4-1.7z" />
    </S>
  ),
  datadog: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="3.4" fill="#632CA6" />
      <path fill="#fff" d="M17.4 6.2l-2.2 1.5-1.7-2.7-1.2 4.6-1.15-1.2-3.6 1 1.5 1.7-1.3 4 1.5-.55-.45 1.35 1.6-.5 1.5 1.75.4-2.3 1.1.6-.3-2.05 1.6-1.2-1.4-.55 1.9-1.05-1.5-.5 2.35-1.6zm-5.5 8.1l-1.35-1.5.85-2.55 1.55 1.6-.35 2.15z" />
    </S>
  ),
  mssql: (p) => (
    <S {...p}>
      <ellipse cx="12" cy="5.6" rx="8" ry="2.8" fill="#A4373A" />
      <path fill="#CC2927" d="M4 5.6v12.8c0 1.55 3.58 2.8 8 2.8s8-1.25 8-2.8V5.6c0 1.55-3.58 2.8-8 2.8s-8-1.25-8-2.8z" />
      <ellipse cx="12" cy="5.6" rx="8" ry="2.8" fill="#E8E8E8" opacity=".25" />
      <path fill="#fff" d="M9.6 11.6c1.1-.5 2.6-.4 3.4.4.5.5.6 1.3.1 1.9-.7.9-2.2 1-3.2.6.9.15 2 0 2.4-.55.25-.35.15-.8-.2-1.05-.75-.55-2.1-.45-3-.3z" />
    </S>
  ),
  graphql: (p) => (
    <S {...p}>
      <path stroke="#E10098" strokeWidth="1.1" fill="none" d="M12 3.2l7.6 4.4v8.8L12 20.8 4.4 16.4V7.6z" />
      <path stroke="#E10098" strokeWidth="1.1" fill="none" d="M12 3.9L5.2 15.7h13.6z" />
      <g fill="#E10098">
        <circle cx="12" cy="3.4" r="1.7" /><circle cx="19.6" cy="7.8" r="1.7" />
        <circle cx="19.6" cy="16.2" r="1.7" /><circle cx="12" cy="20.6" r="1.7" />
        <circle cx="4.4" cy="16.2" r="1.7" /><circle cx="4.4" cy="7.8" r="1.7" />
      </g>
    </S>
  ),
  google_sheets: (p) => (
    <S {...p}>
      <path fill="#0F9D58" d="M14.2 2H6.6A1.6 1.6 0 0 0 5 3.6v16.8A1.6 1.6 0 0 0 6.6 22h10.8a1.6 1.6 0 0 0 1.6-1.6V6.8z" />
      <path fill="#fff" opacity=".3" d="M14.2 2v3.2a1.6 1.6 0 0 0 1.6 1.6H19z" />
      <path fill="#fff" d="M8.2 10.4h7.6v7.2H8.2zm1.3 1.3v1.35h2.2v-1.35zm3.5 0v1.35h2.2v-1.35zm-3.5 2.6v1.4h2.2v-1.4zm3.5 0v1.4h2.2v-1.4z" />
    </S>
  ),
  sharepoint_list: (p) => (
    <S {...p}>
      <circle cx="9.4" cy="8.4" r="5.6" fill="#036C70" />
      <circle cx="15.4" cy="12" r="5.2" fill="#1A9BA1" />
      <circle cx="11.6" cy="17.4" r="4.4" fill="#37C6D0" />
      <rect x="3" y="9.6" width="10.4" height="10.4" rx="1.2" fill="#03787C" />
      <path fill="#fff" d="M6.1 12.2h4.2v1.15H6.1zm0 2.2h4.2v1.15H6.1zm0 2.2h4.2v1.15H6.1z" />
    </S>
  ),
  /* ── Agentic web. Four cards were sharing one grey Material glyph, which is exactly the
     "not finished yet" the note at the top of this file is about. Simplified marks in each
     product's own brand colour, drawn to be legible at 15px. ── */
  exa: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="5" fill="#1A1A1A" />
      <path fill="#fff" d="M12 5.4l1.5 4.1 4.1 1.5-4.1 1.5L12 16.6l-1.5-4.1L6.4 11l4.1-1.5z" />
      <circle cx="12" cy="11" r="1.5" fill="#1A1A1A" />
      <path stroke="#fff" strokeWidth="1.6" strokeLinecap="round" d="M16.4 15.4l2.6 2.9" />
    </S>
  ),
  tavily: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="5" fill="#6C4CF1" />
      <path fill="#fff" d="M12 6.2c2.9 1.6 4.4 3.7 4.4 6.2A4.4 4.4 0 0 1 12 18a4.4 4.4 0 0 1-4.4-5.6c0-2.5 1.5-4.6 4.4-6.2z" />
      <path fill="#6C4CF1" opacity=".35" d="M12 9.4c1.4.9 2.1 2 2.1 3.3A2.1 2.1 0 0 1 12 15z" />
    </S>
  ),
  firecrawl: (p) => (
    <S {...p}>
      <path fill="#F0500C" d="M12 2.2c3.1 3 4.7 5.6 4.7 7.9 0 1.2-.4 2.2-1.2 3 .5-1.9.2-3.5-1-4.9.2 2.5-.7 4.3-2.6 5.6-1.3.9-2 2-2 3.2 0 1.6 1 2.8 2.7 3.4a5.9 5.9 0 0 1-5.5-1.9 6.6 6.6 0 0 1-1.8-4.6c0-3.3 2.2-6.9 6.7-11.7z" />
      <path fill="#FFA24D" d="M12.6 12.6c1.4 1.4 2.1 2.7 2.1 3.9 0 1.6-1 2.8-2.7 3.4 1.9-.2 3.4-1 4.4-2.4.7-1 1-2.1.9-3.3-.6.8-1.4 1.3-2.4 1.5.2-1.1-.1-2.1-1-3.1z" />
    </S>
  ),
  // Jina Reader: the "read this page for me" one, so the mark is a page rather than a bird
  reader: (p) => (
    <S {...p}>
      <rect x="2" y="2" width="20" height="20" rx="5" fill="#111" />
      <path fill="#fff" d="M6.6 7.4h4.6a1.4 1.4 0 0 1 1.4 1.4v8.2a2.2 2.2 0 0 0-1.6-.7H6.6z" />
      <path fill="#fff" opacity=".62" d="M17.4 7.4h-4.6A1.4 1.4 0 0 0 11.4 8.8v8.2a2.2 2.2 0 0 1 1.6-.7h4.4z" />
      <path stroke="#111" strokeWidth="1.1" strokeLinecap="round" d="M8 10.2h2.4M8 12.3h2.4M13.6 10.2H16M13.6 12.3H16" />
    </S>
  ),
  /* ── the plumbing cards, also stuck on the fallback glyph ── */
  winrm: (p) => (
    <S {...p}>
      <path fill="#0078D4" d="M3 5.1l7.9-1.1v7.6H3zm8.9-1.2L21 2.6v8.9h-9.1zM3 12.6h7.9v7.5L3 19zm8.9 0H21v8.8l-9.1-1.2z" />
      <path stroke="#fff" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" fill="none" d="M5.4 15.2l1.6 1.6-1.6 1.6" />
    </S>
  ),
  database: (p) => (
    <S {...p}>
      <g fill="#6b6459">
        <ellipse cx="12" cy="5.6" rx="7.4" ry="2.8" />
        <path d="M4.6 8.4v3.4c0 1.55 3.31 2.8 7.4 2.8s7.4-1.25 7.4-2.8V8.4c0 1.55-3.31 2.8-7.4 2.8s-7.4-1.25-7.4-2.8z" />
        <path d="M4.6 14.4v3.4c0 1.55 3.31 2.8 7.4 2.8s7.4-1.25 7.4-2.8v-3.4c0 1.55-3.31 2.8-7.4 2.8s-7.4-1.25-7.4-2.8z" />
      </g>
      <ellipse cx="12" cy="5.6" rx="4.4" ry="1.4" fill="#b3aa9a" />
    </S>
  ),
  smb_file: (p) => (
    <S {...p}>
      <path fill="#8a8276" d="M2.6 6.4a1.6 1.6 0 0 1 1.6-1.6h4l1.8 2h9.4A1.6 1.6 0 0 1 21 8.4v9.2a1.6 1.6 0 0 1-1.6 1.6H4.2a1.6 1.6 0 0 1-1.6-1.6z" />
      <path fill="#b3aa9a" d="M2.6 10.2h18.8v7.4a1.6 1.6 0 0 1-1.6 1.6H4.2a1.6 1.6 0 0 1-1.6-1.6z" />
      <g fill="#fff"><circle cx="8" cy="14.6" r="1.5" /><circle cx="16" cy="14.6" r="1.5" /></g>
      <path stroke="#fff" strokeWidth="1.2" d="M8 14.6h8" />
    </S>
  ),
};

LOGOS.sharepoint = LOGOS.sharepoint_list;      // the card is "SharePoint"; the list mark is the brand mark
export const hasLogo = (k) => !!LOGOS[k];
export const Logo = ({ name, sx }) => (LOGOS[name] ? LOGOS[name]({ sx }) : null);
