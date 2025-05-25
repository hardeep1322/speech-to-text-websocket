# stt_server.py – FastAPI + Google Cloud Speech‑to‑Text (async, OGG/Opus)
# ------------------------------------------------------------------------------
# This single file accepts Opus audio chunks over a WebSocket and streams live
# transcripts back to the same socket.  Matches MediaRecorder mimeType:
#     "audio/ogg;codecs=opus"  at 48 kHz
# ------------------------------------------------------------------------------

import os
import asyncio
import traceback
from typing import AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

from google.cloud import speech_v1 as speech  # v1 client family

# ─── Audio / model parameters ────────────────────────────────────────────────
AUDIO_ENCODING = speech.RecognitionConfig.AudioEncoding.WEBM_OPUS  # <‑‑ key change
SAMPLE_RATE_HERTZ = 48_000  # WebM Opus is always 48 kHz                                        # 48 kHz for Opus
LANGUAGE_CODE = "en-US"

# ─── FastAPI + CORS ─────────────────────────────────────────────────────────
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Credential helper ──────────────────────────────────────────────────────

def get_speech_client() -> speech.SpeechAsyncClient:
    creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if creds and os.path.exists(creds):
        return speech.SpeechAsyncClient()

    local_key = os.path.join(os.path.dirname(__file__), "credentials.json")
    if os.path.exists(local_key):
        return speech.SpeechAsyncClient.from_service_account_file(local_key)

    raise FileNotFoundError(
        "Google STT credentials not found. Set GOOGLE_APPLICATION_CREDENTIALS "
        "or place credentials.json next to stt_server.py"
    )

stt_client: speech.SpeechAsyncClient = get_speech_client()

# ─── Generator: config frame + audio chunks ─────────────────────────────────
async def gcp_request_stream(ws: WebSocket) -> AsyncGenerator[speech.StreamingRecognizeRequest, None]:
    """Yield the initial config request, then audio chunk requests."""

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
            if audio := msg.get("bytes"):
                yield speech.StreamingRecognizeRequest(audio_content=audio)
    except WebSocketDisconnect:
        pass

# ─── Response forwarder ─────────────────────────────────────────────────────
async def forward_transcripts(responses, ws: WebSocket):
    try:
        async for resp in responses:
            print("[STT] got response frame")  # debug
            if not resp.results:
                continue
            res = resp.results[0]
            if not res.alternatives:
                continue
            text = res.alternatives[0].transcript
            print("[STT] text:", text)         # debug
            await ws.send_json({
                "transcript": text,
                "is_final": res.is_final,
            })
    except Exception as e:
        # Typical gRPC stream shutdown errors are safe to ignore
        print("[STT] response loop terminated:", e)

# ─── WebSocket endpoint ─────────────────────────────────────────────────────
@app.websocket("/ws/{client_id}")
async def stt_ws(ws: WebSocket, client_id: str):
    await ws.accept()
    print(f"[WS {client_id}] connected")

    try:
        requests = gcp_request_stream(ws)
        responses = await stt_client.streaming_recognize(requests=requests)
        forward_task = asyncio.create_task(forward_transcripts(responses, ws))
        await forward_task

    except Exception:
        traceback.print_exc()
    finally:
        if ws.client_state != WebSocketState.DISCONNECTED:
            await ws.close()
        print(f"[WS {client_id}] disconnected")

# ─── Local dev entrypoint ───────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("stt_server:app", host="0.0.0.0", port=8000, reload=True)
