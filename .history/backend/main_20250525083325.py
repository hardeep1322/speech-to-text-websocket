"""
FastAPI-based WebSocket server that forwards raw PCM (LINEAR16) audio
to Google Cloud Speech-to-Text and streams transcripts back.

✓ Uses the async Speech client.
✓ Expects little-endian 16-bit PCM @ 48 kHz.
✓ Prints any InvalidArgument error Google returns so you can see it.
"""

import os, asyncio, traceback
from typing import AsyncGenerator, Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

from google.cloud import speech_v1 as speech
from google.api_core import exceptions as gexc
from google.cloud.speech import enums, types

# ─── GOOGLE STT CONFIG ────────────────────────────────────────────────
AUDIO_ENCODING     = speech.RecognitionConfig.AudioEncoding.LINEAR16
SAMPLE_RATE_HERTZ  = 48_000            # must match the bytes we stream
LANGUAGE_CODE      = "en-US"
# ──────────────────────────────────────────────────────────────────────

# ─── FastAPI boilerplate ──────────────────────────────────────────────
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active WebSocket connections and their speech clients
active_connections: Dict[str, Dict[str, Any]] = {}

def get_stt_client() -> speech.SpeechAsyncClient:
    # prefer GOOGLE_APPLICATION_CREDENTIALS env var, otherwise local file
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return speech.SpeechAsyncClient()
    local = os.path.join(os.path.dirname(__file__), "credentials.json")
    if os.path.exists(local):
        return speech.SpeechAsyncClient.from_service_account_file(local)
    raise FileNotFoundError(
        "Set GOOGLE_APPLICATION_CREDENTIALS or place credentials.json next to stt_server.py"
    )

stt_client = get_stt_client()

# ─── Request iterator generator ───────────────────────────────────────
async def request_stream(ws: WebSocket) -> AsyncGenerator[speech.StreamingRecognizeRequest, None]:
    cfg = speech.RecognitionConfig(
        encoding=AUDIO_ENCODING,
        sample_rate_hertz=SAMPLE_RATE_HERTZ,
        language_code=LANGUAGE_CODE,
        enable_automatic_punctuation=True,
    )
    streaming_cfg = speech.StreamingRecognitionConfig(config=cfg, interim_results=True)
    yield speech.StreamingRecognizeRequest(streaming_config=streaming_cfg)

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if audio := msg.get("bytes"):
                # Expect ~4800 bytes per 256-ms chunk (4096 samples * 2 B)
                yield speech.StreamingRecognizeRequest(audio_content=audio)
    except WebSocketDisconnect:
        pass

# ─── Forward STT responses to the same WebSocket ─────────────────────
async def forward_responses(responses, ws: WebSocket):
    async for resp in responses:
        if not resp.results:
            continue
        res = resp.results[0]
        if not res.alternatives:
            continue
        await ws.send_json(
            {
                "transcript": res.alternatives[0].transcript,
                "is_final": res.is_final,
            }
        )

# ─── WebSocket endpoint ───────────────────────────────────────────────
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    
    # Initialize Google Speech-to-Text client
    client = speech.SpeechClient()
    
    # Configure streaming recognition
    config = types.RecognitionConfig(
        encoding=enums.RecognitionConfig.AudioEncoding.WEBM_OPUS,
        sample_rate_hertz=48000,
        language_code="en-US",
        enable_automatic_punctuation=True,
    )
    
    streaming_config = types.StreamingRecognitionConfig(
        config=config,
        interim_results=True
    )
    
    # Store connection info
    active_connections[client_id] = {
        "websocket": websocket,
        "client": client,
        "streaming_config": streaming_config,
        "stream": None
    }
    
    try:
        while True:
            # Receive audio data from client
            data = await websocket.receive_bytes()
            
            # Create recognition request
            request = types.StreamingRecognizeRequest(audio_content=data)
            
            # Get or create recognition stream
            if active_connections[client_id]["stream"] is None:
                stream = active_connections[client_id]["client"].streaming_recognize(
                    active_connections[client_id]["streaming_config"]
                )
                active_connections[client_id]["stream"] = stream
                
                # Start background task to process responses
                asyncio.create_task(process_responses(client_id, stream))
            
            # Send request to Google STT
            active_connections[client_id]["stream"].send(request)
            
    except Exception as e:
        print(f"Error in WebSocket connection: {str(e)}")
    finally:
        # Cleanup
        if client_id in active_connections:
            if active_connections[client_id]["stream"]:
                active_connections[client_id]["stream"].close()
            del active_connections[client_id]

async def process_responses(client_id: str, stream):
    try:
        for response in stream:
            if not response.results:
                continue
                
            result = response.results[0]
            if not result.alternatives:
                continue
                
            transcript = result.alternatives[0].transcript
            is_final = result.is_final
            
            # Send transcript back to client
            if client_id in active_connections:
                await active_connections[client_id]["websocket"].send_json({
                    "transcript": transcript,
                    "is_final": is_final
                })
    except Exception as e:
        print(f"Error processing responses: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
