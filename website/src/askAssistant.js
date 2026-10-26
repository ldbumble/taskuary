// THE BELL HANDS A FAILURE TO THE CHAT (the owner, 2026-10-26: "it should have button to ... ask assistant to fix the error connection
// or diagnose the issue"). Said as a line the owner could have typed, so the troubleshooter (troubleshoot.py) takes it the way it takes
// "whatsapp isn't working". Held until the Assistant is there to take it: pressed from the Board, it is not mounted yet.
let pending = null;
export const askAssistant = (text) => { pending = text; window.dispatchEvent(new Event("tq-ask")); };
export const takeAsk = () => { const t = pending; pending = null; return t; };
