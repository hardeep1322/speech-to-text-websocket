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
      console.log("No audio track selected.");
      return;
    }

    console.log("Audio track obtained.", display.getAudioTracks()[0]);

    // Down-sample / convert to 16-kHz PCM using AudioWorklet
    const ctx = new AudioContext({ sampleRate: 48000 }); // native device rate
    console.log("AudioContext created with state:", ctx.state);
    const destRate = 48000;                              // keep it 48 kHz
    const src = ctx.createMediaStreamSource(display);

    // Add and create the AudioWorkletNode
    try {
      await ctx.audioWorklet.addModule('/src/audio-processor.js');
      console.log("AudioWorklet module added.");
      const proc = new AudioWorkletNode(ctx, 'audio-processor');
      procRef.current = proc;
      console.log("AudioWorkletNode created.", proc);

      src.connect(proc);
      console.log("MediaStreamSource connected to AudioWorkletNode.");

      // proc.connect(ctx.destination); // Not needed if we only process and send

      const ws = new WebSocket(`ws://localhost:8000/ws/${id}`);
      wsRef.current = ws;
      console.log("WebSocket created.", ws);

      ws.onopen = () => {
        console.log("WebSocket connection opened.");
      };

      ws.onmessage = (ev) => {
        const data = JSON.parse(ev.data);
        setLines((prev) => [
          ...prev,
          (data.is_final ? "✔ " : "… ") + data.transcript,
        ]);
        console.log("Received message from WebSocket:", data);
      };

      ws.onerror = (err) => {
        console.error("WebSocket error:", err);
      };

      ws.onclose = (event) => {
        console.log("WebSocket connection closed:", event.code, event.reason);
      };

      // Listen for messages from the AudioWorkletProcessor
      proc.port.onmessage = (event) => {
        // console.log("Received message from AudioWorkletProcessor.");
        if (ws.readyState === 1) ws.send(event.data);
      };

      proc.port.onmessageerror = (error) => {
        console.error("AudioWorklet port message error:", error);
      };


    } catch (error) {
      console.error("Error setting up audio processing:", error);
    }
  }

  /* ── stop everything ───────────────────────────────────────────── */
  function stop() {
    console.log("Stopping audio processing and WebSocket.");
    procRef.current?.disconnect();
    procRef.current?.port.close(); // Close the port as well
    wsRef.current?.close();
    // Also stop the media tracks
    // Although getDisplayMedia tracks stop automatically when sharing ends,
    // explicitly stopping them can be good practice.
    if (procRef.current && procRef.current.parameters.get('stream')) {
       const tracks = procRef.current.parameters.get('stream').getTracks();
       tracks.forEach(track => track.stop());
       console.log("Media tracks stopped.");
    }
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
