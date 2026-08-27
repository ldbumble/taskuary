// The agent raised its hand: a session that was working has gone quiet at its prompt (the
// Board's "waiting on you"), or asked a question. This is the one moment worth a sound - you
// are on another tab or another app, and the thing you delegated is now waiting on you.
//
// Sounds are synthesised with WebAudio, so there is no file to ship and nothing to fetch;
// each is a few hundred milliseconds and deliberately soft. The desktop notification is the
// browser's own (Notification API); pywebview surfaces it as the OS's.
import { useEffect, useRef } from "react";
import api from "./api";
import { IDLE_WAITING } from "./ui.jsx";

export const SOUNDS = ["off", "chime", "bell", "knock", "pop"];

let ctx = null;
const ac = () => (ctx ||= new (window.AudioContext || window.webkitAudioContext)());

const tone = (freq, at, dur, gain = 0.18, type = "sine") => {
  const c = ac(), o = c.createOscillator(), g = c.createGain();
  o.type = type; o.frequency.setValueAtTime(freq, at);
  g.gain.setValueAtTime(0, at); g.gain.linearRampToValueAtTime(gain, at + 0.012); g.gain.exponentialRampToValueAtTime(0.0008, at + dur);
  o.connect(g).connect(c.destination); o.start(at); o.stop(at + dur + 0.05);
};
const noise = (at, dur, gain = 0.25) => {
  const c = ac(), n = Math.floor(c.sampleRate * dur), b = c.createBuffer(1, n, c.sampleRate), d = b.getChannelData(0);
  for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n) ** 2;
  const s = c.createBufferSource(), g = c.createGain(), f = c.createBiquadFilter();
  f.type = "lowpass"; f.frequency.value = 900; s.buffer = b; g.gain.value = gain;
  s.connect(f).connect(g).connect(c.destination); s.start(at);
};

export function playSound(name) {
  if (!name || name === "off") return;
  try {
    const c = ac(); if (c.state === "suspended") c.resume();
    const t = c.currentTime + 0.02;
    if (name === "chime") { tone(880, t, 0.35); tone(1318.5, t + 0.16, 0.5, 0.14); }           // a fifth up, two notes
    else if (name === "bell") { tone(1046.5, t, 1.1, 0.16); tone(2093, t, 0.6, 0.05); tone(2637, t, 0.35, 0.03); } // one strike with overtones
    else if (name === "knock") { noise(t, 0.09); noise(t + 0.17, 0.09, 0.2); }                     // two soft knocks
    else if (name === "pop") { tone(520, t, 0.12, 0.2, "triangle"); tone(780, t + 0.05, 0.1, 0.12, "triangle"); }
  } catch { /* no audio device, or autoplay blocked before the first click - the toast still shows */ }
}

export async function desktopNotify(title, body, onClick) {
  if (typeof Notification === "undefined") return false;
  try {
    if (Notification.permission === "default") await Notification.requestPermission();
    if (Notification.permission !== "granted") return false;
    const n = new Notification(title, { body, silent: true, tag: title });
    if (onClick) n.onclick = () => { window.focus(); onClick(); n.close(); };
    return true;
  } catch { return false; }
}

// Watch every live agent; call onRaise({tid, ref, agent, title, asking, tail}) on the moment
// a task's agent flips from working to waiting. Only transitions fire: a session already
// parked when the page loads is old news, and a poll that misses a beat must not re-ring.
export function useHandRaise(onRaise, every = 8000) {
  const seen = useRef({});          // tid -> "working" | "waiting"
  const primed = useRef(false);
  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const { data } = await api.get("/api/runs/live", { params: { lines: 4 } });
        const now = {};
        for (const r of data.data || []) {
          const waiting = r.kind === "session" && (r.asking || (r.waiting ?? (r.idle >= IDLE_WAITING)));
          now[r.TaskId] = waiting ? "waiting" : "working";
          if (primed.current && waiting && seen.current[r.TaskId] === "working") {
            onRaise({ tid: r.TaskId, ref: `TQ-${String(r.TaskId).padStart(4, "0")}`, agent: r.AgentName, title: r.Title || "",
              asking: !!r.asking, tail: (r.tail || []).slice(-2).join(" ") });
          }
        }
        seen.current = now; primed.current = true;
      } catch { /* the server is asleep; try again next tick */ }
    };
    poll();
    const id = setInterval(() => alive && poll(), every);
    return () => { alive = false; clearInterval(id); };
  }, [onRaise, every]);
}
