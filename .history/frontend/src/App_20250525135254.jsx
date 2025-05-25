import { useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";

export default function App() {
  const wsRef   = useRef(null);
  const procRef = useRef(null);
  const id      = useRef(uuidv4()).current;
  const [lines, setLines] = useState<{ timestamp: string, speaker: string, text: string, isFinal: boolean }[]>([]);

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
    mixer.connect(ctx.destination); // Connect mixer to context destination (optional, for monitoring)

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
          // Process final result
          let timestamp = "";
          let speaker = "Unknown Speaker";
          if (data.word_info && data.word_info.length > 0) {
            // Use the start time of the first word as the segment timestamp
            const firstWord = data.word_info[0];
            const minutes = Math.floor(firstWord.start_time / 60);
            const seconds = Math.floor(firstWord.start_time % 60);
            timestamp = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
            speaker = `Speaker ${firstWord.speaker_tag}`;
          }

          setLines(prev => [
            ...prev.filter(line => line.isFinal),
            { timestamp, speaker, text: data.transcript, isFinal: true }
          ]);
        } else {
          // Process interim result - update the last line if it's not final
          setLines(prev => {
            const lastLine = prev[prev.length - 1];
            if (lastLine && !lastLine.isFinal) {
              // Update existing interim line
              const updatedLines = [...prev];
              updatedLines[updatedLines.length - 1] = { ...lastLine, text: data.transcript };
              return updatedLines;
            } else {
              // Create a new interim line (will be updated by subsequent interim results)
               let timestamp = ""; // Interim results might not have reliable timestamps/speakers until finalized
               let speaker = "...";
               // Attempt to get a provisional timestamp/speaker if word_info is available
               if (data.word_info && data.word_info.length > 0) {
                  const firstWord = data.word_info[0];
                  const minutes = Math.floor(firstWord.start_time / 60);
                  const seconds = Math.floor(firstWord.start_time % 60);
                  timestamp = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
                  speaker = `Speaker ${firstWord.speaker_tag || '...'}`;
               }
              return [...prev, { timestamp, speaker, text: data.transcript, isFinal: false }];
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
    // Stop all tracks from both streams
    if (procRef.current) {
      // Assuming we stored the original streams or source nodes with access to tracks
      // A more robust way is to store the streams themselves in refs
      // For now, let's rely on stopping the sources if they were created
      if (procRef.current.context && procRef.current.context.state !== 'closed') {
        procRef.current.context.close(); // Close the AudioContext to stop all nodes and sources
        console.log("AudioContext closed.");
      }
      procRef.current?.disconnect();
      procRef.current?.port.close(); // Close the port as well
    }

    wsRef.current?.close();

    // Need to manually stop the media tracks if the context isn't closed
    // This part needs refinement to access the original streams reliably
    // For demonstration, we'll add comments on how it *should* work if streams were accessible
    // if (micStreamRef.current) micStreamRef.current.getTracks().forEach(track => track.stop());
    // if (displayStreamRef.current) displayStreamRef.current.getTracks().forEach(track => track.stop());
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
            {l.isFinal && l.timestamp && <span>[{l.timestamp}] </span>}
            {l.isFinal && l.speaker && <span>{l.speaker}: </span>}
            {l.text}
          </p>
        ))}
      </div>
    </div>
  );
}
