import { useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";

export default function App() {
  const wsRef = useRef(null);
  const procRef = useRef(null);
  const id = useRef(uuidv4()).current;
  const [lines, setLines] = useState([]);
  const [showSetup, setShowSetup] = useState(true);
  const [speakers, setSpeakers] = useState({
    panelist: "",
    candidate: ""
  });

  /* ── share tab + audio, stream PCM ─────────────────────────────── */
  async function start() {
    let displayStream = null;
    let micStream = null;

    try {
      // Request microphone access
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      console.log("Microphone access granted.");
    } catch (error) {
      console.error("Error accessing microphone:", error);
      alert("Could not access microphone. Transcription might be limited.");
    }

    try {
      // User selects a tab / window and MUST tick "Share tab audio"
      displayStream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: true,
      });
      if (!displayStream.getAudioTracks().length) {
        alert("Please tick 'Share tab audio' before clicking Share.");
        displayStream.getTracks().forEach((t) => t.stop());
        console.log("No display audio track selected.");
        displayStream = null; // Set to null if no audio track
      }
    } catch (error) {
       console.error("Error accessing display media:", error);
       alert("Could not access display media. Make sure you allow screen recording.");
       displayStream = null; // Set to null on error
    }

    // Stop if neither stream is available
    if (!micStream && !displayStream) {
      console.error("No audio sources available.");
      return;
    }

    const ctx = new AudioContext({ sampleRate: 48000 }); // native device rate
    console.log("AudioContext created with state:", ctx.state);

    // Create source nodes for available streams
    const micSource = micStream ? ctx.createMediaStreamSource(micStream) : null;
    const displaySource = displayStream ? ctx.createMediaStreamSource(displayStream) : null;

    // Create a GainNode to mix streams
    const mixer = ctx.createGain();
    // mixer.connect(ctx.destination); // Connect mixer to context destination (optional, for monitoring) - Removed to prevent echo

    // Connect available sources to the mixer
    if (micSource) {
      micSource.connect(mixer);
      console.log("Microphone source connected to mixer.");
    }
    if (displaySource) {
      displaySource.connect(mixer);
      console.log("Display source connected to mixer.");
    }

    // Add and create the AudioWorkletNode
    try {
      await ctx.audioWorklet.addModule('/src/audio-processor.js');
      console.log("AudioWorklet module added.");
      const proc = new AudioWorkletNode(ctx, 'audio-processor');
      procRef.current = proc;
      console.log("AudioWorkletNode created.", proc);

      // Connect the mixer to the AudioWorkletNode
      mixer.connect(proc);
      console.log("Mixer connected to AudioWorkletNode.");

      const ws = new WebSocket(`ws://localhost:8000/ws/${id}`);
      wsRef.current = ws;
      console.log("WebSocket created.", ws);

      // Send speaker names when connection opens
      ws.onopen = () => {
        console.log("WebSocket connection opened.");
        ws.send(JSON.stringify({
          type: "setup",
          speakers: speakers
        }));
      };

      ws.onmessage = (ev) => {
        const data = JSON.parse(ev.data);
        console.log("Received message from WebSocket:", data);
        if (data.is_final) {
          // For final results, add a new line with speaker info
          setLines(prev => [
            ...prev.filter(line => line.isFinal),
            { 
              text: data.transcript, 
              isFinal: true,
              speaker: data.speaker // Add speaker info from backend
            }
          ]);
        } else {
          // For interim results, update the last line
          setLines(prev => {
            const lastLine = prev[prev.length - 1];
            if (lastLine && !lastLine.isFinal) {
              // Update the existing interim line
              const updatedLines = [...prev];
              updatedLines[updatedLines.length - 1] = { 
                ...lastLine, 
                text: data.transcript,
                speaker: data.speaker // Add speaker info from backend
              };
              return updatedLines;
            } else {
              // Add a new interim line if the last one was final or didn't exist
              return [...prev, { 
                text: "... " + data.transcript, 
                isFinal: false,
                speaker: data.speaker // Add speaker info from backend
              }];
            }
          });
        }
      };

      ws.onerror = (err) => {
        console.error("WebSocket error:", err);
      };

      ws.onclose = (event) => {
        console.log("WebSocket connection closed:", event.code, event.reason);
      };

      // Listen for messages from the AudioWorkletProcessor
      proc.port.onmessage = (event) => {
        if (ws.readyState === 1) {
          // Send audio data with source info
          const message = {
            type: "audio",
            source: event.data.source, // 'mic' or 'display'
            data: event.data.audio
          };
          ws.send(JSON.stringify(message));
        }
      };

      proc.port.onmessageerror = (error) => {
        console.error("AudioWorklet port message error:", error);
      };

    } catch (error) {
      console.error("Error setting up audio processing:", error);
      // Stop tracks if AudioWorklet setup fails
      if (micStream) micStream.getTracks().forEach(track => track.stop());
      if (displayStream) displayStream.getTracks().forEach(track => track.stop());
    }
  }

  function stop() {
    if (procRef.current) {
      procRef.current.disconnect();
    }
    if (wsRef.current) {
      wsRef.current.close();
    }
  }

  if (showSetup) {
    return (
      <div className="p-4 space-y-4">
        <h1 className="text-2xl font-bold">Interview Copilot</h1>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Panelist Name</label>
            <input
              type="text"
              value={speakers.panelist}
              onChange={(e) => setSpeakers(prev => ({ ...prev, panelist: e.target.value }))}
              className="w-full p-2 border rounded"
              placeholder="Enter panelist name"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Candidate Name</label>
            <input
              type="text"
              value={speakers.candidate}
              onChange={(e) => setSpeakers(prev => ({ ...prev, candidate: e.target.value }))}
              className="w-full p-2 border rounded"
              placeholder="Enter candidate name"
            />
          </div>
          <button
            onClick={() => {
              if (!speakers.panelist || !speakers.candidate) {
                alert("Please enter both panelist and candidate names");
                return;
              }
              setShowSetup(false);
              start();
            }}
            className="w-full px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Start Interview
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      <h1 className="text-2xl font-bold">Interview Copilot</h1>

      <button onClick={stop} className="px-4 py-2 bg-gray-300 rounded ml-4">
        Stop
      </button>

      <div className="mt-6 space-y-2">
        {lines.map((line, i) => (
          <div key={i} className={`p-2 rounded ${line.isFinal ? 'bg-gray-100' : 'bg-gray-50'}`}>
            {line.speaker && (
              <span className="font-bold text-blue-600">{line.speaker}: </span>
            )}
            {line.text}
          </div>
        ))}
      </div>
    </div>
  );
}