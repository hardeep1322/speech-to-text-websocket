import { useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";

export default function App() {
  const wsRef = useRef(null);
  const id = useRef(uuidv4()).current;
  const [lines, setLines] = useState([]);

  async function start() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const context = new AudioContext({ sampleRate: 16000 });

    const source = context.createMediaStreamSource(stream);
    const processor = context.createScriptProcessor(4096, 1, 1);

    source.connect(processor);
    processor.connect(context.destination);

    const ws = new WebSocket(`ws://localhost:8000/ws/${id}`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setLines((prev) => [
        ...prev,
        (data.is_final ? "✔ " : "… ") + data.transcript,
      ]);
    };

    processor.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);
      const buffer = new Int16Array(input.length);
      for (let i = 0; i < input.length; i++) {
        const s = Math.max(-1, Math.min(1, input[i]));
        buffer[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      }

      if (ws.readyState === WebSocket.OPEN) {
        ws.send(buffer.buffer);
        console.log("sent", buffer.length * 2, "bytes");
      }
    };
  }

  function stop() {
    wsRef.current?.close();
  }

  return (
    <div className="p-4 space-y-4">
      <h1 className="text-2xl font-bold">Interview Copilot</h1>

      <button
        onClick={start}
        className="px-4 py-2 bg-blue-600 text-white rounded"
      >
        Start Mic
      </button>

      <button
        onClick={stop}
        className="px-4 py-2 bg-gray-300 rounded ml-4"
      >
        Stop
      </button>

      <div className="mt-6 space-y-1 text-sm">
        {lines.map((line, index) => (
          <p key={index}>{line}</p>
        ))}
      </div>
    </div>
  );
}
