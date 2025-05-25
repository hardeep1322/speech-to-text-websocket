// src/App.jsx
import { useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";

/* pick the first mime-type this browser supports */
function pickMimeType() {
  const candidates = [
    "audio/webm;codecs=opus",   // Chrome / Edge on Windows, macOS, Linux
    "audio/webm",               // fallback (still Opus @ 48 kHz)
  ];
  return candidates.find(t => MediaRecorder.isTypeSupported(t));
}

export default function App() {
  const wsRef   = useRef(null);
  const recRef  = useRef(null);
  const id      = useRef(uuidv4()).current;   // stays constant for this tab
  const [lines, setLines] = useState([]);

  /* ── START sharing ─────────────────────────────────────────── */
  async function start() {
    const mimeType = pickMimeType();
    if (!mimeType) {
      alert("This browser cannot record WebM/Opus audio.");
      return;
    }

    // 1️⃣ user selects the meeting tab (tick “Share tab audio”!)
    const display = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: true,
    });
    const audioStream = new MediaStream(display.getAudioTracks());

    // 2️⃣ MediaRecorder emits Opus @ 48 kHz in WebM chunks
    const rec = new MediaRecorder(audioStream, { mimeType });
    recRef.current = rec;

    // 3️⃣ WebSocket to the FastAPI backend
    const ws = new WebSocket(`ws://localhost:8000/ws/${id}`);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        setLines(prev => [
          ...prev,
          (data.is_final ? "✔ " : "… ") + data.transcript,
        ]);
      } catch (_) { /* ignore non-JSON */ }
    };

    // 4️⃣ send each chunk (100 ms) as raw bytes
    rec.ondataavailable = async (e) => {
      if (e.data.size && ws.readyState === 1) {
        const buf = await e.data.arrayBuffer();
        ws.send(buf);
        console.log("sent", buf.byteLength);
      }
    };

    rec.start(100);                   // 100 ms timeslice
  }

  /* ── STOP everything ───────────────────────────────────────── */
  function stop() {
    recRef.current?.stop();
    wsRef.current?.close();
  }

  /* ── UI ─────────────────────────────────────────────────────── */
  return (
    <div className="p-4 space-y-4">
      <h1 className="text-2xl font-bold">Interview Copilot</h1>

      <button
        onClick={start}
        className="px-4 py-2 bg-blue-600 text-white rounded"
      >
        Share & Transcribe
      </button>

      <button
        onClick={stop}
        className="px-4 py-2 bg-gray-300 rounded ml-4"
      >
        Stop
      </button>

      <div className="mt-6 space-y-1 text-sm">
        {lines.map((l, i) => <p key={i}>{l}</p>)}
      </div>
    </div>
  );
}
