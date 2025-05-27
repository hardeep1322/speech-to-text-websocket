"""
FastAPI-based WebSocket server that forwards raw PCM (LINEAR16) audio
to Google Cloud Speech-to-Text and streams transcripts back.

✓ Uses the async Speech client.
✓ Expects little-endian 16-bit PCM @ 48 kHz.
✓ Prints any InvalidArgument error Google returns so you can see it.
"""

import os, asyncio, traceback, json
from typing import AsyncGenerator, Dict
from collections import deque
from datetime import datetime, timedelta
import google.generativeai as genai

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

from google.cloud import speech_v1 as speech
from google.api_core import exceptions as gexc

# Configure Gemini
GEMINI_API_KEY = "AIzaSyB_OvO66xl-JoZ9OLbhNfQ1Xl_QWZGhcxs"
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Audio / model parameters
AUDIO_ENCODING = speech.RecognitionConfig.AudioEncoding.LINEAR16
SAMPLE_RATE_HERTZ = 48000
LANGUAGE_CODE = "en-US"
SUMMARY_INTERVAL = 30  # seconds

# FastAPI setup
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active connections and their data
active_connections: Dict[str, dict] = {}

def get_speech_client():
    return speech.SpeechAsyncClient()

# Initialize STT client
stt_client = get_speech_client()

def format_timestamp(seconds: float) -> str:
    """Convert seconds to MM:SS format"""
    minutes = int(seconds // 60)
    seconds = int(seconds % 60)
    return f"{minutes:02d}:{seconds:02d}"

async def generate_summary(transcript_lines: list, ws: WebSocket, client_id: str):
    """Generate a summary using Gemini and send it to the client"""
    try:
        # Format transcript as conversation
        conversation = "\n".join([
            f"{line['speaker']}: {line['text']}"
            for line in transcript_lines
        ])

        # Generate summary using Gemini
        prompt = f"""Summarize the following 30-second conversation between a candidate and a panel. Be concise and return 3–4 bullet points.

Conversation:
{conversation}"""

        response = await model.generate_content_async(prompt)
        summary = response.text

        # Send summary to client
        await ws.send_json({
            "type": "summary",
            "timestamp": format_timestamp(transcript_lines[-1]["timestamp"]),
            "text": summary
        })

    except Exception as e:
        print(f"Error generating summary: {str(e)}")

async def request_stream(ws: WebSocket) -> AsyncGenerator[speech.StreamingRecognizeRequest, None]:
    """First yields the config frame, then raw audio chunks."""
    
    # 1️⃣ control frame
    rec_cfg = speech.RecognitionConfig(
        encoding=AUDIO_ENCODING,
        sample_rate_hertz=SAMPLE_RATE_HERTZ,
        language_code=LANGUAGE_CODE,
        enable_automatic_punctuation=True,
    )
    stream_cfg = speech.StreamingRecognitionConfig(config=rec_cfg, interim_results=True)
    yield speech.StreamingRecognizeRequest(streaming_config=stream_cfg)

    # 2️⃣ audio frames
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break

            if msg.get("type") == "websocket.receive":
                if msg.get("text"):
                    # Handle setup message with speaker names
                    try:
                        data = json.loads(msg["text"])
                        if data.get("type") == "setup":
                            client_id = ws.path_params.get("client_id")
                            active_connections[client_id]["speakers"] = data["speakers"]
                            continue
                    except json.JSONDecodeError:
                        pass

                if msg.get("bytes"):
                    # Handle audio data
                    audio_bytes = msg["bytes"]
                    yield speech.StreamingRecognizeRequest(audio_content=audio_bytes)

    except WebSocketDisconnect:
        pass

async def forward_transcripts(responses, ws: WebSocket):
    """Forward STT responses to the client with speaker info."""
    client_id = ws.path_params.get("client_id")
    speakers = active_connections.get(client_id, {}).get("speakers", {})
    start_time = datetime.now()
    transcript_buffer = deque(maxlen=100)  # Store last 100 lines
    
    async for resp in responses:
        if not resp.results:
            continue
        res = resp.results[0]
        if not res.alternatives:
            continue

        # Calculate timestamp
        elapsed_seconds = (datetime.now() - start_time).total_seconds()
        timestamp = format_timestamp(elapsed_seconds)

        # Determine speaker based on the audio source
        speaker = speakers.get("panelist") if res.is_final else speakers.get("candidate")

        # Create transcript line
        transcript_line = {
            "type": "transcript",
            "timestamp": timestamp,
            "speaker": speaker,
            "text": res.alternatives[0].transcript,
            "is_final": res.is_final,
            "timestamp_seconds": elapsed_seconds
        }

        # Add to buffer if final
        if res.is_final:
            transcript_buffer.append(transcript_line)

        # Send transcript to client
        await ws.send_json(transcript_line)

        # Check if it's time to generate a summary
        if res.is_final and elapsed_seconds % SUMMARY_INTERVAL < 1:  # Within 1 second of interval
            # Get last 30 seconds of transcript
            recent_lines = [
                line for line in transcript_buffer
                if line["timestamp_seconds"] > elapsed_seconds - SUMMARY_INTERVAL
            ]
            if recent_lines:
                await generate_summary(recent_lines, ws, client_id)

# ─── WebSocket endpoint ───────────────────────────────────────────────
@app.websocket("/ws/{client_id}")
async def stt_ws(ws: WebSocket, client_id: str):
    await ws.accept()
    print(f"[WS {client_id}] connected")

    # Initialize connection data
    active_connections[client_id] = {
        "speakers": {},
        "stream": None
    }

    try:
        requests = request_stream(ws)
        responses = await stt_client.streaming_recognize(requests=requests)

        forward_task = asyncio.create_task(forward_transcripts(responses, ws))
        await forward_task  # runs until socket or stream closes

    except Exception:
        traceback.print_exc()
    finally:
        if ws.client_state != WebSocketState.DISCONNECTED:
            await ws.close()
        if client_id in active_connections:
            del active_connections[client_id]
        print(f"[WS {client_id}] disconnected")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)