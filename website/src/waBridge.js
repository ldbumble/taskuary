// RESTART IS ONE PRESS FROM THE ERROR (the owner, 2026-10-22). The poll's error says "the WhatsApp bridge is not running ...
// - Restart bridge starts it" (messengers._wa), and that sentence is read on the connector card, in the bell and on the walk's
// card - so each of them puts the button beside it rather than sending the owner to find it somewhere else.
import api from "./api";

export const namesRestart = (text) => /Restart bridge/.test(String(text || ""));
// the same verb as the card's own Restart bridge: stop whatever holds the port, start the bridge from the code on disk
export const restartBridge = (cid) => api.post(`/api/connectors/${cid}/wa/bridge/restart`);
// unlink, set the old pairing aside, start unpaired - the pairing box then shows the QR (wabridge.pair_again)
export const pairAgain = (cid) => api.post(`/api/connectors/${cid}/wa/bridge/pair-again`);
