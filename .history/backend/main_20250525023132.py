# stt_server.py – FastAPI + Google Cloud Speech‑to‑Text v1 (async)
# ------------------------------------------------------------------
# One‑file reference server that accepts raw PCM over a WebSocket and
# streams transcripts back in real time.  Fixes the coroutine error
# by **awaiting** streaming_recognize so we get an async‑iterator.
# ------------------------------------------------------------------

import os
import asyncio
import traceback
from typing import AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

from google.cloud import speech_v1 as speech  # v1 client family

# ─── Audio / model parameters ─────────────────────────────────────
# ▶▶  audio format must match the browser ◀◀
AUDIO_ENCODING = speech.RecognitionConfig.AudioEncoding.WEBM_OPUS
SAMPLE_RATE_HERTZ = 48_000
LANGUAGE_CODE = "en-US"
MAX_SILENCE_SEC = 5  # GCP closes stream if no chunk ≤5 s

# ─── FastAPI + CORS ───────────────────────────────────────────────
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Credential helper ────────────────────────────────────────────

def get_speech_client() -> speech.SpeechAsyncClient:
    env_key = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_key and os.path.exists(env_key):
        return speech.SpeechAsyncClient()

    local_json = os.path.join(os.path.dirname(__file__), "credentials.json")
    if os.path.exists(local_json):
        return speech.SpeechAsyncClient.from_service_account_file(local_json)

    raise FileNotFoundError(
        "No Google credentials found – set GOOGLE_APPLICATION_CREDENTIALS or place "
        "credentials.json next to stt_server.py"
    )

stt_client: speech.SpeechAsyncClient = get_speech_client()

# ─── Generator: config frame + audio chunks ───────────────────────
async def gcp_request_stream(ws: WebSocket) -> AsyncGenerator[speech.StreamingRecognizeRequest, None]:
    # 1️⃣ control message
    rec_cfg = speech.RecognitionConfig(
        encoding=AUDIO_ENCODING,
        sample_rate_hertz=SAMPLE_RATE_HERTZ,
        language_code=LANGUAGE_CODE,
        enable_automatic_punctuation=True,
    )
    stream_cfg = speech.StreamingRecognitionConfig(config=rec_cfg, interim_results=True)
    yield speech.StreamingRecognizeRequest(streaming_config=stream_cfg)

    # 2️⃣ audio messages
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if audio := msg.get("bytes"):
                yield speech.StreamingRecognizeRequest(audio_content=audio)
            # optional text commands here
    except WebSocketDisconnect:
        pass

# ─── Response forwarder ───────────────────────────────────────────
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
        print("[STT] response loop terminated:", e)

# ─── WebSocket endpoint ──────────────────────────────────────────
@app.websocket("/ws/{client_id}")
async def stt_ws(ws: WebSocket, client_id: str):
    await ws.accept()
    print(f"[WS {client_id}] connected")

    try:
        requests = gcp_request_stream(ws)
        # *** FIX: await the async call so we get an async‑iterator ***
        responses = await stt_client.streaming_recognize(requests=requests)

        forward_task = asyncio.create_task(forward_transcripts(responses, ws))
        await forward_task  # runs until socket or stream closes

    except Exception:
        traceback.print_exc()
    finally:
        if ws.client_state != WebSocketState.DISCONNECTED:
            await ws.close()
        print(f"[WS {client_id}] disconnected")

# ─── Local dev entrypoint ─────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("stt_server:app", host="0.0.0.0", port=8000, reload=True)
