import { useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";

export default function App() {
  const wsRef           = useRef(null);
  const recorderRef     = useRef(null);
  const [transcripts, setTranscripts] = useState([]);
  const clientId        = useRef(uuidv4()).current;      // one id per tab

  /* 1️⃣ start sharing */
  async function startRecording() {
    // pick the tab (user must tick “Share tab audio”)
    const display = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: true,
    });

    // isolate just the audio track
    const audioStream = new MediaStream(display.getAudioTracks());

    // *** key setting: WebM Opus ***
    const rec = new MediaRecorder(audioStream, {
      mimeType: "audio/webm;codecs=opus",
      audioBitsPerSecond: 128_000,     // optional, gives stable sizes
    });
    recorderRef.current = rec;

    /* open WebSocket */
    const ws = new WebSocket(`ws://localhost:8000/ws/${clientId}`);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        setTranscripts((t) => [
          ...t,
          (data.is_final ? "✔ " : "… ") + data.transcript,
        ]);
      } catch (_) {}
    };

    /* send an ArrayBuffer every 100 ms */
    rec.ondataavailable = async (e) => {
      if (e.data.size && ws.readyState === 1) {
        const buf = await e.data.arrayBuffer();
        ws.send(buf);
        console.log("sent", buf.byteLength);
      }
    };

    rec.start(100); // → ondataavailable timeslice
  }

  /* 2️⃣ stop everything */
  function stopRecording() {
    recorderRef.current?.stop();
    wsRef.current?.close();
  }

  return (
    <div className="p-4 space-y-4">
      <h1 className="text-2xl font-bold">Interview Copilot</h1>

      <button
        onClick={startRecording}
        className="px-4 py-2 bg-blue-600 text-white rounded"
      >
        Share & Transcribe
      </button>

      <button
        onClick={stopRecording}
        className="px-4 py-2 bg-gray-300 rounded ml-4"
      >
        Stop
      </button>

      <div className="mt-6 space-y-2 text-sm">
        {transcripts.map((t, i) => (
          <p key={i}>{t}</p>
        ))}
      </div>
    </div>
  );
}
