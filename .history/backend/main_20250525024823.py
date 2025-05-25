=import { useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";

/* ------------------------------------------------------------------
   Interview Copilot – minimal front‑end
   ------------------------------------------------------------------
   * Captures tab‑audio via getDisplayMedia.
   * Automatically selects the first WebM/Opus MIME type the browser
     supports and sends raw bytes to the FastAPI backend at ws://localhost:8000.
   * Renders interim ("…") and final ("✔") transcripts returned by the
     backend.                                                       
   ------------------------------------------------------------------ */

export default function App() {
  const wsRef        = useRef(null);
  const recRef       = useRef(null);
  const clientId     = useRef(uuidv4()).current;   // stable per tab
  const [lines, setLines] = useState([]);

  /* ――― helper: pick a supported MIME type ――― */
  function pickMime() {
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm;codecs=pcm",
      "audio/webm",
    ];
    return candidates.find(MediaRecorder.isTypeSupported);
  }

  /* ――― start sharing / recording ――― */
  async function start() {
    const mimeType = pickMime();
    if (!mimeType) {
      alert("Your browser cannot record WebM audio – try Chrome 120+");
      return;
    }

    // 1️⃣ user picks the tab and MUST tick "Share tab audio"
    const display = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: true,
    });
    const audioStream = new MediaStream(display.getAudioTracks());

    // 2️⃣ MediaRecorder emits ~100‑ms Opus chunks (WebM container)
    const rec = new MediaRecorder(audioStream, { mimeType });
    recRef.current = rec;

    // 3️⃣ open WebSocket to backend (make sure backend is running!)
    const ws = new WebSocket(`ws://localhost:8000/ws/${clientId}`);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        setLines((prev) => [
          ...prev,
          `${data.is_final ? "✔" : "…"} ${data.transcript}`,
        ]);
      } catch (_) {}
    };

    // 4️⃣ stream bytes every 100 ms
    rec.ondataavailable = async (ev) => {
      if (ev.data.size && ws.readyState === 1) {
        const buf = await ev.data.arrayBuffer();
        ws.send(buf);
        console.log("sent", buf.byteLength);
      }
    };

    rec.start(100); // timeslice (ms)
  }

  /* ――― stop everything ――― */
  function stop() {
    recRef.current?.stop();
    wsRef.current?.close();
  }

  /* ――― ui ――― */
  return (
    <div className="p-6 space-y-4 text-gray-800 dark:text-white bg-white dark:bg-slate-900 min-h-screen">
      <h1 className="text-3xl font-bold">Interview Copilot</h1>

      <div className="space-x-4">
        <button onClick={start} className="px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700">
          Share & Transcribe
        </button>
        <button onClick={stop}  className="px-4 py-2 rounded bg-gray-300 hover:bg-gray-400 dark:bg-slate-700 dark:hover:bg-slate-600">
          Stop
        </button>
      </div>

      <div className="mt-6 space-y-1 whitespace-pre-wrap text-sm font-mono">
        {lines.map((l, i) => <div key={i}>{l}</div>)}
      </div>
    </div>
  );
}
