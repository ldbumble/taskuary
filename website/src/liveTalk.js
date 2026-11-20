// LIVE INTERACTION (taskuary/livevoice.py): one live voice session at a time, over local WebRTC to this Taskuary (Pipecat SmallWebRTC - no
// Daily or LiveKit account). It lives here, not in a component, so it carries on when New opens the task his first words made: that task's
// Talk button finds the session waiting for a task (`waiting`) and binds it. The state is what the button shows: off, connecting,
// listening, thinking, speaking.
import api from "./api.js";

const S = { pc: null, pcId: "", dc: null, ping: null, audio: null, stream: null, state: "off", tid: null, waiting: false, why: "", onNew: null };
const subs = new Set();
const tell = () => subs.forEach((f) => f(snapshot()));
export const snapshot = () => ({ state: S.state, tid: S.tid, waiting: S.waiting, why: S.why });
export const watch = (f) => { subs.add(f); f(snapshot()); return () => subs.delete(f); };
const set = (patch) => { Object.assign(S, patch); tell(); };

// ...his words on New, before there is a task: New's own road makes it (onNew), and the task it opens binds the session (bind)
function heard(msg) {
  if (msg?.tq === "state") set({ state: msg.state });
  else if (msg?.tq === "new") { set({ waiting: true }); S.onNew?.(String(msg.text || "")); }
}

const gathered = (pc) => new Promise((ok) => {
  if (pc.iceGatheringState === "complete") return ok();
  const done = () => { if (pc.iceGatheringState === "complete") { pc.removeEventListener("icegatheringstatechange", done); ok(); } };
  pc.addEventListener("icegatheringstatechange", done);
  setTimeout(ok, 3000);                 // ...a local connection needs no more than the host candidates
});

export async function start({ taskId = null, onNew = null } = {}) {
  if (S.pc) await stop();
  set({ state: "connecting", tid: taskId, waiting: false, why: "", onNew });
  try {
    const { data: st } = await api.get("/api/live/status");
    if (!st.ready) throw new Error(st.why);
    S.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    const pc = new RTCPeerConnection();
    S.pc = pc;
    S.dc = pc.createDataChannel("taskuary-live");
    S.dc.onmessage = (e) => { try { heard(JSON.parse(e.data)); } catch { /* a keep-alive or a message not for the button */ } };
    S.dc.onopen = () => { S.ping = setInterval(() => { try { S.dc?.send(`ping: ${Date.now()}`); } catch { /* closing */ } }, 1000); };
    // ...audio first, then video: the order Pipecat's SmallWebRTC reads transceivers in (audio 0, video 1)
    pc.addTransceiver(S.stream.getAudioTracks()[0], { direction: "sendrecv" });
    pc.addTransceiver("video", { direction: "recvonly" });
    pc.ontrack = (e) => {
      if (e.track.kind !== "audio") return;
      S.audio = S.audio || Object.assign(new Audio(), { autoplay: true });
      S.audio.srcObject = new MediaStream([e.track]);
      S.audio.play?.().catch(() => null);
    };
    pc.onconnectionstatechange = () => { if (["failed", "closed"].includes(pc.connectionState) && S.pc === pc) stop("the connection dropped"); };
    await pc.setLocalDescription(await pc.createOffer());
    await gathered(pc);
    const { data } = await api.post("/api/live/offer", { sdp: pc.localDescription.sdp, type: pc.localDescription.type, task_id: taskId });
    S.pcId = data.pc_id;
    await pc.setRemoteDescription({ sdp: data.sdp, type: data.type });
    if (S.state === "connecting") set({ state: "listening" });
  } catch (e) {
    await stop(e?.response?.data?.detail || e?.message || "Talk did not start");
  }
}

export async function bind(taskId) {
  if (!S.pcId || !S.waiting) return;
  set({ tid: taskId, waiting: false });
  try { await api.post(`/api/live/${S.pcId}/bind`, { task_id: taskId }); } catch { /* the session ended meanwhile: its button says off */ }
}

export async function stop(why = "") {
  const { pc, pcId } = S;
  clearInterval(S.ping);
  S.stream?.getTracks().forEach((t) => t.stop());
  try { pc?.close(); } catch { /* already closed */ }
  Object.assign(S, { pc: null, pcId: "", dc: null, ping: null, stream: null, onNew: null });
  if (S.audio) S.audio.srcObject = null;
  set({ state: "off", tid: null, waiting: false, why });
  if (pcId) await api.post(`/api/live/${pcId}/stop`).catch(() => null);
}
