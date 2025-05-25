"""
FastAPI-based WebSocket server that forwards raw PCM (LINEAR16) audio
to Google Cloud Speech-to-Text and streams transcripts back.

✓ Uses the async Speech client.
✓ Expects little-endian 16-bit PCM @ 48 kHz.
✓ Prints any InvalidArgument error Google returns so you can see it.
"""

import os, asyncio, traceback
from typing import AsyncGenerator

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
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_stt_client() -> speech.SpeechAsyncClient:
    # Check for credentials in multiple locations
    possible_locations = [
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),  # Environment variable
        os.path.join(os.path.dirname(__file__), "credentials.json"),  # Local file
        os.path.join(os.path.dirname(__file__), "gen-lang-client-0769471387-17a4f9d05aee.json"),  # Specific file
    ]
    
    # Filter out None values and check each location
    for cred_path in filter(None, possible_locations):
        if os.path.exists(cred_path):
            print(f"Using credentials from: {cred_path}")
            return speech.SpeechAsyncClient.from_service_account_file(cred_path)
    
    # If no credentials found, provide helpful error message
    error_msg = """
    No Google Cloud credentials found! Please do one of the following:
    1. Set GOOGLE_APPLICATION_CREDENTIALS environment variable to point to your credentials file
    2. Place your credentials.json file in the backend directory
    3. Place your gen-lang-client-0769471387-17a4f9d05aee.json file in the backend directory
    """
    raise FileNotFoundError(error_msg)

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
@app.websocket("/ws/{cid}")
async def stt_socket(ws: WebSocket, cid: str):
    await ws.accept()
    print(f"[WS {cid}] connected")

    try:
        responses = await stt_client.streaming_recognize(
            requests=request_stream(ws)
        )
        print("[STT] stream established ✅")
        await forward_responses(responses, ws)

    except gexc.InvalidArgument as e:
        # The detailed protobuf message pinpoints the incorrect field
        print("⚠️  Google InvalidArgument:", e.message)
    except Exception:
        traceback.print_exc()
    finally:
        if ws.client_state != WebSocketState.DISCONNECTED:
            await ws.close()
        print(f"[WS {cid}] disconnected")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
