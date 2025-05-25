import { useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";

export default function App() {
  const wsRef   = useRef(null);
  const procRef = useRef(null);
  const id      = useRef(uuidv4()).current;
  const [lines, setLines] = useState([]);

  /* ── share tab + audio, stream PCM ─────────────────────────────── */
  async function start() {
    // User selects a tab / window and MUST tick “Share tab audio”
    const display = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: true,
    });
    if (!display.getAudioTracks().length) {
      alert("Please tick 'Share tab audio' before clicking Share.");
      display.getTracks().forEach((t) => t.stop());
      return;
    }

    // Down-sample / convert to 16-kHz PCM
    const ctx = new AudioContext({ sampleRate: 48000 }); // native device rate
    const destRate = 48000;                              // keep it 48 kHz
    const src = ctx.createMediaStreamSource(display);
    const proc = ctx.createScriptProcessor(4096, 1, 1);
    procRef.current = proc;

    src.connect(proc);
    proc.connect(ctx.destination);

    const ws = new WebSocket(`ws://localhost:8000/ws/${id}`);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      setLines((prev) => [
        ...prev,
        (data.is_final ? "✔ " : "… ") + data.transcript,
      ]);
    };

    proc.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0); // Float32 [-1,1]
      // Convert to little-endian 16-bit PCM
      const pcm = new Int16Array(input.length);
      for (let i = 0; i < input.length; i++) {
        const s = Math.max(-1, Math.min(1, input[i]));
        pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      if (ws.readyState === 1) ws.send(pcm.buffer);
    };
  }

  /* ── stop everything ───────────────────────────────────────────── */
  function stop() {
    procRef.current?.disconnect();
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
