# stt_server.py – FastAPI + Google Cloud Speech‑to‑Text v1 (async)
# -------------------------------------------------------------
# Single‑file reference implementation for live WebSocket audio
# transcription.  Works with React/JS clients that send raw PCM
# (LINEAR16, 16‑kHz mono) chunks every ≤100 ms.
# -------------------------------------------------------------

import os
import asyncio
import traceback
from typing import AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

from google.cloud import speech_v1 as speech  # *** v1 client, NOT v2 ***

# ────────────────────────────────────────────────────────────────
# Audio / model parameters – make these match your front‑end
# capture pipeline.
# ────────────────────────────────────────────────────────────────
AUDIO_ENCODING = speech.RecognitionConfig.AudioEncoding.LINEAR16  # or WEBM_OPUS
SAMPLE_RATE_HERTZ = 16_000                                      # 48_000 for Opus
LANGUAGE_CODE = "en-US"
CHUNK_MAX_SILENCE_SEC = 5                                        # GCP will close if >5 s

# ────────────────────────────────────────────────────────────────
# FastAPI setup
# ────────────────────────────────────────────────────────────────
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],   # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ────────────────────────────────────────────────────────────────
# Credential helper – looks for GOOGLE_APPLICATION_CREDENTIALS
# and falls back to ./credentials.json (same dir as this file)
# ────────────────────────────────────────────────────────────────

def get_speech_client() -> speech.SpeechAsyncClient:
    cred_env = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_env and os.path.exists(cred_env):
        return speech.SpeechAsyncClient()

    local_key = os.path.join(os.path.dirname(__file__), "credentials.json")
    if os.path.exists(local_key):
        return speech.SpeechAsyncClient.from_service_account_file(local_key)

    raise FileNotFoundError(
        "Google STT credentials not found. Set GOOGLE_APPLICATION_CREDENTIALS "
        "or place credentials.json beside stt_server.py"
    )

# Initialise once at module import so connections are pooled.
stt_client: speech.SpeechAsyncClient = get_speech_client()

# ────────────────────────────────────────────────────────────────
# Async generator: yields GCP StreamingRecognizeRequest frames
# ────────────────────────────────────────────────────────────────
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

            audio_bytes = msg.get("bytes")
            if audio_bytes:
                yield speech.StreamingRecognizeRequest(audio_content=audio_bytes)
            # you can optionally parse text commands here (e.g., STOP)
    except WebSocketDisconnect:
        pass

# ────────────────────────────────────────────────────────────────
# Response handler – sends transcripts back over the same socket
# ────────────────────────────────────────────────────────────────
async def forward_transcripts(responses, ws: WebSocket):
    try:
        async for resp in responses:
            if not resp.results:
                continue
            res = resp.results[0]
            if not res.alternatives:
                continue
            await ws.send_json({
                "transcript": res.alternatives[0].transcript,
                "is_final": res.is_final,
            })
    except Exception as e:
        # Log & swallow typical stream‑end errors (RST_STREAM, etc.)
        print("[STT] response loop terminated:", e)

# ────────────────────────────────────────────────────────────────
# WebSocket endpoint
# ────────────────────────────────────────────────────────────────
@app.websocket("/ws/{client_id}")
async def stt_endpoint(ws: WebSocket, client_id: str):
    await ws.accept()
    print(f"[WS {client_id}] connected")

    # Kick off STT stream + response forwarder concurrently
    try:
        requests = request_stream(ws)
        responses = stt_client.streaming_recognize(requests=requests)

        # Run response handler in background; meanwhile keep feeding audio
        forward_task = asyncio.create_task(forward_transcripts(responses, ws))
        await forward_task  # completes when socket closes or STT ends

    except Exception:
        traceback.print_exc()
    finally:
        if ws.client_state != WebSocketState.DISCONNECTED:
            await ws.close()
        print(f"[WS {client_id}] disconnected")

# ────────────────────────────────────────────────────────────────
# Entrypoint for local testing – `python stt_server.py`
# ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("stt_server:app", host="0.0.0.0", port=8000, reload=True)
