import { useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";

export default function App() {
  const wsRef   = useRef(null);
  const procRef = useRef(null);
  const id      = useRef(uuidv4()).current;
  const [lines, setLines] = useState([]);

  /* ── share tab + audio, stream PCM ─────────────────────────────── */
  async function start() {
    // User selects a tab / window and MUST tick "Share tab audio"
    const display = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: true,
    });
    if (!display.getAudioTracks().length) {
      alert("Please tick 'Share tab audio' before clicking Share.");
      display.getTracks().forEach((t) => t.stop());
      return;
    }

    // Down-sample / convert to 16-kHz PCM using AudioWorklet
    const ctx = new AudioContext({ sampleRate: 48000 }); // native device rate
    const destRate = 48000;                              // keep it 48 kHz
    const src = ctx.createMediaStreamSource(display);

    // Add and create the AudioWorkletNode
    await ctx.audioWorklet.addModule('/src/audio-processor.js');
    const proc = new AudioWorkletNode(ctx, 'audio-processor');
    procRef.current = proc;

    src.connect(proc);
    // proc.connect(ctx.destination); // Not needed if we only process and send

    const ws = new WebSocket(`ws://localhost:8000/ws/${id}`);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      setLines((prev) => [
        ...prev,
        (data.is_final ? "✔ " : "… ") + data.transcript,
      ]);
    };

    // Listen for messages from the AudioWorkletProcessor
    proc.port.onmessage = (event) => {
      if (ws.readyState === 1) ws.send(event.data);
    };
  }

  /* ── stop everything ───────────────────────────────────────────── */
  function stop() {
    procRef.current?.disconnect();
    procRef.current?.port.close(); // Close the port as well
    wsRef.current?.close();
  }

  /* ── UI ────────────────────────────────────────────────────────── */
  return (
    <div style={{ padding: 24, fontFamily: "sans-serif" }}>
      <h1>Interview Copilot – Live Transcript</h1>

      <button onClick={start} style={{ padding: "8px 16px", marginRight: 8 }}>
        Share & Transcribe Tab
      </button>
      <button onClick={stop} style={{ padding: "8px 16px" }}>
        Stop
      </button>

      <div style={{ marginTop: 24, lineHeight: 1.4 }}>
        {lines.map((l, i) => (
          <p key={i}>{l}</p>
        ))}
      </div>
    </div>
  );
}
