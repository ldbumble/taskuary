/* THE BROWSER'S OWN VOICE KEEPS LISTENING (the owner, 2026-10-28: "clicked 'use your browser voice', then hit the mic and it just turns
   right off"). Two things turned it off. The vocabulary went to Chrome as contextual-biasing phrases, which its cloud recogniser refuses
   ("phrases-not-supported") - the session ended the instant it began. And Chrome ends a session by itself (a pause, a minute's talk, a
   network blip): every end was taken as the owner's stop. Its error went only to the mic's tooltip, which nobody hovers. Now a session
   that ends while the mic is on is started again; a refused vocabulary is dropped and the mic goes on without it; a stop the browser
   will not take back says why in one line. The mic stays on until the owner presses it again or sends. */

/* NOT IN THE TASKUARY WINDOW (a user, 2026-10-29: "voice noting not working" - the mic said it could not reach the speech service).
   The desktop window is Edge's WebView2: it carries Chromium's SpeechRecognition class but no speech service behind it, so every
   session ends at once with "network", online or not. There the browser's own voice is no choice at all - the computer's own takes it
   (voice.py builtin: Windows' dictation), and only with none does the mic ask for a voice AI. */
// ...and the window is known at its first draw (the owner, 2026-11-09: "Browser voice needs an internet connection" inside the window):
// pywebview puts window.pywebview on only after the page has loaded, so a mic drawn before then took the window for a tab and offered
// the browser's voice. WebView2 carries window.chrome.webview from the start.
export const inAppWindow = (w = typeof window === "undefined" ? null : window) => !!(w && (w.pywebview || w.chrome?.webview));
export const browserRecogniser = (w = typeof window === "undefined" ? null : window) =>
  w && !inAppWindow(w) ? (w.SpeechRecognition || w.webkitSpeechRecognition || null) : null;

// A MIC FAILURE NAMES ITS FIX AS A BUTTON (the owner, 2026-11-09: "it's broken you need to show the issue?? ... just request the permission
// like a normal app and they can hit approve"): the Windows setting a line points at opens with one press, the voice shelf for the rest.
// ...and a browser whose speech service is down offers the voice this computer has instead (`other`: {label, choice} - the voice card,
// or Windows voice typing), else the voice shelf (the owner, 2026-11-16: "the browser's own speech recognition was not working")
export const micFix = (line, other = null) => {
  const s = String(line || "");
  if (/browser's speech service/i.test(s)) return other ? { label: `Use ${other.label}`, choose: other.choice } : { label: "Set up voice AI", voice: true };
  if (/microphone privacy|desktop apps access your microphone|MicrophoneUnavailable|No microphone Windows/i.test(s)) return { label: "Open microphone settings", settings: "microphone" };
  if (/Online speech recognition|speech privacy|speech service did not answer|speech recognition is off/i.test(s)) return { label: "Open speech settings", settings: "speech" };
  if (/voice AI/i.test(s)) return { label: "Set up voice AI", voice: true };
  return null;
};

// what the owner reads when the browser will not listen - null: not the owner's to fix, the mic just goes on
export const dictationError = (code) => ({
  "not-allowed": "The browser blocked the microphone - allow it in the address bar, then press the mic again",
  "service-not-allowed": "This browser's speech service will not serve this page - try Chrome, or dictate with another voice",
  // ...not "needs an internet connection" (2026-11-16): Edge 147+ answers "network" online too - its service, not the owner's line, is down
  "network": "This browser's speech service is not answering - check the internet connection, or dictate with another voice",
  // Edge 157 hears the speech (speechstart) and settles each phrase as an empty final: the microphone was fine, the service sent no words
  "blank": "This browser's speech service heard you but sent back no words - it cannot dictate in this browser",
  "audio-capture": "No microphone found - plug one in or pick it in your sound settings",
  "language-not-supported": "This browser's speech service does not hear this language - dictate with another voice",
  "no-speech": "No words heard - check the microphone is on and not muted, then press the mic and talk",
  "aborted": "Something else took the microphone - press the mic to go on",
}[code] ?? (code ? `Browser voice stopped (${code})` : null));

// errors that end dictation; the rest (a pause, a refused vocabulary) start the next session
const FATAL = new Set(["not-allowed", "service-not-allowed", "network", "audio-capture", "language-not-supported", "bad-grammar"]);
const QUICK_MS = 1500, QUICK_MAX = 3;            // a session that dies at once, three times running, is a browser that will not listen
const BLANK_MAX = 2;                             // two phrases settled with no words and none with any: the service is not transcribing

/* One dictation. `SR` the browser's recogniser class; `phrases()` makes the vocabulary's phrase list (dropped if refused). onFinal(text) for each settled
   phrase, onInterim(text) for what is still being heard ("" when none), onEnd(errLine|null) once, when it is over. */
export function dictate({ SR, lang = "en-US", phrases = null, onFinal, onInterim, onEnd, now = () => Date.now() }) {
  let on = true, r = null, fatal = null, quick = 0, began = 0, heard = false, blank = 0, usePhrases = !!phrases;
  const silent = () => dictationError(blank ? "blank" : "no-speech");   // what a mic that landed nothing says
  const finish = (line) => { if (r) { r.onresult = r.onerror = r.onend = null; } on = false; onInterim?.(""); onEnd?.(line); };
  const begin = () => {
    const s = r = new SR(); let done = 0;     // finals of this session already handed over
    s.lang = lang; s.continuous = true; s.interimResults = true;
    if (usePhrases) { try { s.phrases = phrases(); } catch { usePhrases = false; } }
    s.onresult = (e) => {
      if (s !== r) return;
      const res = Array.from(e.results);
      let i = done;
      for (; i < res.length && res[i].isFinal; i++) { const t = res[i][0]?.transcript?.trim(); if (t) { heard = true; onFinal?.(t); } else blank++; }
      done = i;
      if (!heard && blank >= BLANK_MAX) { const line = silent(); finish(line); try { s.abort(); } catch { /* already ended */ } return; }
      onInterim?.(res.slice(i).filter((x) => !x.isFinal).map((x) => x[0]?.transcript?.trim()).filter(Boolean).join(" "));
      quick = 0;
    };
    s.onerror = (e) => {
      if (s !== r) return;
      if (e.error === "phrases-not-supported") { usePhrases = false; return; }   // the session ends; the next one goes without them
      if (e.error === "aborted" && !on) return;
      if (FATAL.has(e.error) || e.error === "aborted") fatal = e.error;
    };
    s.onend = () => {
      if (s !== r || !on) return;
      onInterim?.("");
      if (fatal) return finish(dictationError(fatal));
      quick = now() - began < QUICK_MS ? quick + 1 : 0;
      if (quick >= QUICK_MAX) return finish(heard ? null : silent());
      try { began = now(); s.onresult = s.onerror = s.onend = null; begin(); } catch { finish("The browser stopped listening - press the mic to go on"); }
    };
    began = now(); s.start();
  };
  begin();
  return {
    // the owner's press: what was being said still lands (the recogniser's last result comes before its end)
    stop() {
      if (!on) return;
      on = false; const s = r;
      s.onerror = null;
      // ...and a stop with no word heard says so (2026-11-09: "you start it and end it and no words show up") - never a silent mic
      s.onend = () => { s.onresult = s.onend = null; onInterim?.(""); onEnd?.(heard ? null : silent()); };
      try { s.stop(); } catch { s.onend(); }
    },
    // a send: the words in flight would land in a box just emptied, so they are dropped
    cancel() { if (!on) return; const s = r; finish(null); try { s.abort(); } catch { /* already ended */ } },
    get on() { return on; },
  };
}
