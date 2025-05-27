"""
FastAPI-based WebSocket server that forwards raw PCM (LINEAR16) audio
to Google Cloud Speech-to-Text and streams transcripts back.

✓ Uses the async Speech client.
✓ Expects little-endian 16-bit PCM @ 48 kHz.
✓ Prints any InvalidArgument error Google returns so you can see it.
"""

import os, asyncio, traceback, json
from typing import AsyncGenerator, Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

from google.cloud import speech_v1 as speech
from google.api_core import exceptions as gexc

# ─── GOOGLE STT CONFIG ────────────────────────────────────────────────
AUDIO_ENCODING     = speech.RecognitionConfig.AudioEncoding.LINEAR16
SAMPLE_RATE_HERTZ  = 48_000            # must match the bytes we stream
LANGUAGE_CODE      = "en-US"
# ──────────────────────────────────────────────────────────────────────

# ─── FastAPI boilerplate ──────────────────────────────────────────────
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active connections and their speaker info
active_connections: Dict[str, dict] = {}

def get_speech_client():
    return speech.SpeechAsyncClient()

# Initialize STT client
stt_client = get_speech_client()

# ─── Request iterator generator ───────────────────────────────────────
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

# ─── Forward STT responses to the same WebSocket ─────────────────────
async def forward_transcripts(responses, ws: WebSocket):
    """Forward STT responses to the client with speaker info."""
    client_id = ws.path_params.get("client_id")
    speakers = active_connections.get(client_id, {}).get("speakers", {})
    
    async for resp in responses:
        if not resp.results:
            continue
        res = resp.results[0]
        if not res.alternatives:
            continue

        # Determine speaker based on the audio source
        # This assumes the frontend sends the source with each audio chunk
        speaker = speakers.get("panelist") if res.is_final else speakers.get("candidate")

        await ws.send_json({
            "transcript": res.alternatives[0].transcript,
            "is_final": res.is_final,
            "speaker": speaker
        })

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