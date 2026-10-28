/* THE BROWSER'S OWN VOICE KEEPS LISTENING (the owner, 2026-10-28: "clicked 'use your browser voice', then hit the mic and it just turns
   right off"). Two things turned it off. The vocabulary went to Chrome as contextual-biasing phrases, which its cloud recogniser refuses
   ("phrases-not-supported") - the session ended the instant it began. And Chrome ends a session by itself (a pause, a minute's talk, a
   network blip): every end was taken as the owner's stop. Its error went only to the mic's tooltip, which nobody hovers. Now a session
   that ends while the mic is on is started again; a refused vocabulary is dropped and the mic goes on without it; a stop the browser
   will not take back says why in one line. The mic stays on until the owner presses it again or sends. */

// what the owner reads when the browser will not listen - null: not the owner's to fix, the mic just goes on
export const dictationError = (code) => ({
  "not-allowed": "The browser blocked the microphone - allow it in the address bar, then press the mic again",
  "service-not-allowed": "This browser will not lend its voice to this page - try Chrome or Edge, or set up a voice AI",
  "network": "Browser voice needs an internet connection - it could not reach the browser's speech service",
  "audio-capture": "No microphone found - plug one in or pick it in your sound settings",
  "language-not-supported": "The browser's voice does not hear this language - set up a voice AI instead",
  "no-speech": "No speech heard - press the mic and talk",
  "aborted": "Something else took the microphone - press the mic to go on",
}[code] ?? (code ? `Browser voice stopped (${code})` : null));

// errors that end dictation; the rest (a pause, a refused vocabulary) start the next session
const FATAL = new Set(["not-allowed", "service-not-allowed", "network", "audio-capture", "language-not-supported", "bad-grammar"]);
const QUICK_MS = 1500, QUICK_MAX = 3;            // a session that dies at once, three times running, is a browser that will not listen

/* One dictation. `SR` the browser's recogniser class; `phrases()` makes the vocabulary's phrase list (dropped if refused). onFinal(text) for each settled
   phrase, onInterim(text) for what is still being heard ("" when none), onEnd(errLine|null) once, when it is over. */
export function dictate({ SR, lang = "en-US", phrases = null, onFinal, onInterim, onEnd, now = () => Date.now() }) {
  let on = true, r = null, fatal = null, quick = 0, began = 0, heard = false, usePhrases = !!phrases;
  const finish = (line) => { if (r) { r.onresult = r.onerror = r.onend = null; } on = false; onInterim?.(""); onEnd?.(line); };
  const begin = () => {
    const s = r = new SR(); let done = 0;     // finals of this session already handed over
    s.lang = lang; s.continuous = true; s.interimResults = true;
    if (usePhrases) { try { s.phrases = phrases(); } catch { usePhrases = false; } }
    s.onresult = (e) => {
      if (s !== r) return;
      const res = Array.from(e.results);
      let i = done;
      for (; i < res.length && res[i].isFinal; i++) { const t = res[i][0]?.transcript?.trim(); if (t) { heard = true; onFinal?.(t); } }
      done = i;
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
      if (quick >= QUICK_MAX) return finish(heard ? null : dictationError("no-speech"));
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
      s.onend = () => { s.onresult = s.onend = null; onInterim?.(""); onEnd?.(null); };
      try { s.stop(); } catch { s.onend(); }
    },
    // a send: the words in flight would land in a box just emptied, so they are dropped
    cancel() { if (!on) return; const s = r; finish(null); try { s.abort(); } catch { /* already ended */ } },
    get on() { return on; },
  };
}
