import React, { useState } from "react";
import { Alert, Box, Button, MenuItem, TextField, Typography } from "@mui/material";
import { Crumb, MicButton, useVoiceReady } from "./ui.jsx";
import { browserRecogniser } from "./dictation.js";
import { chooseVoice, voiceChoice } from "./voiceChoice.js";
import api from "./api";

export default function BuiltinVoice({ onBack }) {
  const voice = useVoiceReady();
  const [choice, setChoice] = useState(voiceChoice);
  const [text, setText] = useState("");
  const [interim, setInterim] = useState("");
  const [active, setActive] = useState(false);
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false);
  const check = async () => {
    setChecking(true); setError("");
    try { await api.get("/api/voice/status", { params: { builtin: true, refresh: true } }); voice?.recheck(); }
    catch { setError("Could not check voice availability. Try again."); }
    finally { setChecking(false); }
  };
  const browser = !!browserRecogniser();
  const select = (value) => {
    try { chooseVoice(value); setChoice(value); setError(""); }
    catch { setError("This window could not save the microphone choice. Allow site storage and try again."); }
  };
  return <Box sx={{ p: 3, maxWidth: 720 }} data-tq-builtin-voice>
    <Crumb onBack={onBack} label="Windows / browser voice" />
    <Typography variant="h6" sx={{ my: 2 }}>Built-in dictation</Typography>
    <Typography sx={{ mb: 2 }}>Use Windows speech recognition or this browser's speech service for live microphone dictation. No API key or additional voice provider is needed. Windows and browser speech may send audio to their own online services. This choice applies to microphone buttons in this browser or Taskuary window; voice-note files keep their existing transcription settings.</Typography>
    <Typography sx={{ mb: 2 }}>
      Windows: {!voice ? "checking" : voice.builtin?.ask ? "needs Online speech recognition enabled" : voice.builtin ? "available on this computer" : "unavailable here"}.
      {" "}Browser: {browser ? "API available; test below to check its service" : "unavailable in this window; try an Edge or Chrome tab"}.
    </Typography>
    <TextField select fullWidth label="Microphone provider" value={choice} disabled={active || !voice}
      onChange={(e) => select(e.target.value)}>
      <MenuItem value="auto">Automatic</MenuItem>
      <MenuItem value="windows" disabled={!voice?.builtin}>Windows speech recognition</MenuItem>
      <MenuItem value="browser" disabled={!browser}>Browser speech recognition</MenuItem>
    </TextField>
    <Typography sx={{ my: 2 }}>Selecting Windows or Browser uses only that service, even if a voice AI card is connected. Automatic uses a connected voice card first, then browser or Windows speech.</Typography>
    {error && <Alert severity="error">{error}</Alert>}
    <Button onClick={check} disabled={active || checking || !voice}>{checking ? "Checking availability…" : "Check availability again"}</Button>
    {choice === "auto" ? <Alert severity="info">Choose Windows or Browser above to test built-in dictation.</Alert> : <>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, my: 2 }}>
        <MicButton key={choice} onText={(line) => setText((old) => old ? `${old} ${line}` : line)}
          onInterim={setInterim} onActive={setActive} />
        <Typography>Press the mic, speak a sentence, then press stop. Test words stay here.</Typography>
      </Box>
      <TextField fullWidth multiline minRows={3} label="Microphone test" value={text} onChange={(e) => setText(e.target.value)} />
      {interim && <Typography sx={{ mt: 1 }}>{interim}</Typography>}
    </>}
    <Typography sx={{ mt: 2 }}>If Windows cannot listen, check Settings → Privacy &amp; security → Speech (Online speech recognition) and Microphone (desktop app access). In a browser, allow microphone access for this page.</Typography>
  </Box>;
}
