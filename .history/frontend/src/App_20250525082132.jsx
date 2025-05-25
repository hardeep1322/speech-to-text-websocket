import { useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";

export default function App() {
  const wsRef = useRef(null);
  const procRef = useRef(null);
  const id = useRef(uuidv4()).current;
  const [lines, setLines] = useState([]);

  /* ────────────────────────────────────────────── */
  async function startTabShare() {
    // 1️⃣ User picks a tab / window and ticks “Share tab AUDIO”
    const display = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: true,
    });

    // If the user forgot to enable audio, warn and abort.
    if (!display.getAudioTracks().length) {
      alert("⚠️ You must tick 'Share tab audio' before clicking Share.");
      display.getTracks().forEach((t) => t.stop());
      return;
    }

    // 2️⃣ Create AudioContext to down-sample & capture PCM
    const context = new AudioContext({ sampleRate: 16000 });
    const src = context.createMediaStreamSource(display);
    const proc = context.createScriptProcessor(4096, 1, 1);
    procRef.current = proc;

    src.connect(proc);
    proc.connect(context.destination);

    // 3️⃣ Open WebSocket to backend
    const ws = new WebSocket(`ws://localhost:8000/ws/${id}`);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      setLines((prev) => [
        ...prev,
        (data.is_final ? "✔ " : "… ") + data.transcript,
      ]);
    };

    // 4️⃣ Convert floats → 16-bit PCM and send
    proc.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);
      const pcm = new Int16Array(input.length);
      for (let i = 0; i < input.length; i++) {
        const s = Math.max(-1, Math.min(1, input[i]));
        pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(pcm.buffer);
        // console.log("sent", pcm.byteLength, "bytes");
      }
    };
  }

  /* ────────────────────────────────────────────── */
  function stop() {
    procRef.current?.disconnect();
    wsRef.current?.close();
  }

  /* ────────────────────────────────────────────── */
  return (
    <div className="p-4 space-y-4">
      <h1 className="text-2xl font-bold">Interview Copilot</h1>

      <button
        onClick={startTabShare}
        className="px-4 py-2 bg-blue-600 text-white rounded"
      >
        Share &amp; Transcribe Tab
      </button>

      <button
        onClick={stop}
        className="px-4 py-2 bg-gray-300 rounded ml-4"
      >
        Stop
      </button>

      <div className="mt-6 space-y-1 text-sm">
        {lines.map((l, idx) => (
          <p key={idx}>{l}</p>
        ))}
      </div>
    </div>
  );
}
