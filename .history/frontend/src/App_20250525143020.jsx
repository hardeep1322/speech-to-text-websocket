import { useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";

export default function App() {
  const wsRef = useRef(null);
  const procRef = useRef(null);
  const id = useRef(uuidv4()).current;
  const [lines, setLines] = useState([]);

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

      ws.onopen = () => {
        console.log("WebSocket connection opened.");
      };

      ws.onmessage = (ev) => {
        const data = JSON.parse(ev.data);
        console.log("Received message from WebSocket:", data);
        if (data.is_final) {
          // For final results, add a new line
          setLines(prev => [
            ...prev.filter(line => line.isFinal),
            { text: data.transcript, isFinal: true }
          ]);
        } else {
          // For interim results, update the last line
          setLines(prev => {
            const lastLine = prev[prev.length - 1];
            if (lastLine && !lastLine.isFinal) {
              // Update the existing interim line
              const updatedLines = [...prev];
              updatedLines[updatedLines.length - 1] = { ...lastLine, text: data.transcript };
              return updatedLines;
            } else {
              // Add a new interim line if the last one was final or didn't exist
              return [...prev, { text: "... " + data.transcript, isFinal: false }];
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
        // console.log("Received message from AudioWorkletProcessor.");
        if (ws.readyState === 1) ws.send(event.data);
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

  /* ── stop everything ───────────────────────────────────────────── */
  function stop() {
    console.log("Stopping audio processing and WebSocket.");
    if (procRef.current) {
      if (procRef.current.context && procRef.current.context.state !== 'closed') {
        procRef.current.context.close();
        console.log("AudioContext closed.");
      }
      procRef.current?.disconnect();
      procRef.current?.port.close();
    }

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
           <p key={i} style={{ fontWeight: l.isFinal ? 'normal' : 'lighter' }}>
            {l.text}
          </p>
        ))}
      </div>
    </div>
  );
}