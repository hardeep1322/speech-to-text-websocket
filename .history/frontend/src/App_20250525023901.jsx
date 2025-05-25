import { useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";

export default function App() {
  const wsRef       = useRef(null);
  const recRef      = useRef(null);
  const clientId    = useRef(uuidv4()).current;
  const [lines, setLines] = useState([]);

  async function start() {
    // 1. user picks the tab and ticks “Share tab audio”
    const display = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: true,
    });
    const audioStream = new MediaStream(display.getAudioTracks());

    // 2. create MediaRecorder → OGG/Opus @ 48 kHz
    const rec = new MediaRecorder(audioStream, {
      mimeType: "audio/ogg;codecs=opus",
      audioBitsPerSecond: 128_000,
    });
    recRef.current = rec;

    // 3. open WebSocket to backend
    const ws = new WebSocket(`ws://localhost:8000/ws/${clientId}`);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      setLines((prev) => [
        ...prev,
        (data.is_final ? "✔ " : "… ") + data.transcript,
      ]);
    };

    // 4. send every 100 ms
    rec.ondataavailable = async (e) => {
      if (e.data.size && ws.readyState === 1) {
        const buf = await e.data.arrayBuffer();
        ws.send(buf);
        console.log("sent", buf.byteLength);
      }
    };

    rec.start(100);
  }

  function stop() {
    recRef.current?.stop();
    wsRef.current?.close();
  }

  return (
    <div className="p-4 space-y-4">
      <h1 className="text-2xl font-bold">Interview Copilot</h1>

      <button onClick={start} className="px-4 py-2 bg-blue-600 text-white rounded">
        Share &amp; Transcribe
      </button>
      <button onClick={stop}  className="px-4 py-2 bg-gray-300 rounded ml-4">
        Stop
      </button>

      <div className="mt-6 space-y-1 text-sm">
        {lines.map((l, i) => <p key={i}>{l}</p>)}
      </div>
    </div>
  );
}
