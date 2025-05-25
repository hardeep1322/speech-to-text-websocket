import sys
print(f"Python version: {sys.version}")
try:
    import google.cloud.speech
    print(f"google-cloud-speech version: {google.cloud.speech.__version__}")
except ImportError:
    print("google-cloud-speech library is not installed.")
except AttributeError:
    print("google-cloud-speech library is installed, but version attribute is missing (likely very old).")

# ... rest of your imports like os, asyncio, etc.

import osaudio_request_generato
import asyncio
import traceback # For detailed error logging
from typing import AsyncGenerator, Dict, Any # For type hinting
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from google.cloud.speech_v1.types import (
    RecognitionConfig,
    StreamingRecognitionConfig,
    StreamingRecognizeRequest,
    StreamingRecognizeResponse
)
from google.cloud.speech_v1 import SpeechClient
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

# --- Configuration for Google STT ---
AUDIO_ENCODING = RecognitionConfig.AudioEncoding.WEBM_OPUS
SAMPLE_RATE_HERTZ = 48000
LANGUAGE_CODE = "en-US"
# --- End Configuration ---

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def audio_request_generator(
    websocket: WebSocket,
    initial_config_request: StreamingRecognizeRequest, # This is StreamingRecognizeRequest(streaming_config=...)
    stop_event: asyncio.Event,
    client_id: str
) -> AsyncGenerator[StreamingRecognizeRequest, None]:
    yield initial_config_request # First item yielded is the config encapsulated in a request
    print(f"[{client_id}] Sent initial config to Google STT via request generator.")
    try:
        while not stop_event.is_set():
            message = await websocket.receive()
            if message.get('type') == 'websocket.disconnect':
                print(f"[{client_id}] WebSocket disconnected by client during audio receive.")
                stop_event.set()
                break
            audio_chunk = message.get('bytes')
            if audio_chunk:
                yield StreamingRecognizeRequest(audio_content=audio_chunk)
            text_message = message.get('text')
            if text_message:
                print(f"[{client_id}] Received text message from WebSocket: {text_message}")
                if text_message.upper() == "STOP_STREAMING_AUDIO":
                    print(f"[{client_id}] Received STOP_STREAMING_AUDIO command.")
                    stop_event.set()
                    break
    except WebSocketDisconnect:
        print(f"[{client_id}] WebSocket disconnected (WebSocketDisconnect exception in generator).")
    except asyncio.CancelledError:
        print(f"[{client_id}] Audio request generator cancelled.")
    except Exception as e:
        print(f"[{client_id}] Error in audio_request_generator: {type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        print(f"[{client_id}] Audio request generator finished.")
        stop_event.set()

async def process_google_stt_responses(
    responses_iterator: AsyncGenerator[StreamingRecognizeResponse, None],
    websocket: WebSocket,
    client_id: str,
    stop_event: asyncio.Event
):
    print(f"[{client_id}] Listening for STT responses...")
    try:
        async for response in responses_iterator:
            if stop_event.is_set():
                break
            if not response.results:
                continue
            result = response.results[0]
            if not result.alternatives:
                continue
            transcript = result.alternatives[0].transcript
            is_final = result.is_final
            await websocket.send_json({
                "transcript": transcript,
                "is_final": is_final,
                "client_id": client_id
            })
            if is_final:
                 print(f"[{client_id}] STT Final Transcript: '{transcript}'")
    except asyncio.CancelledError:
        print(f"[{client_id}] STT response processing cancelled.")
    except Exception as e:
        if " RST_STREAM " in str(e) or "Http2StreamFramer" in str(e) or "EOF" in str(e) or "Stream removed" in str(e):
            print(f"[{client_id}] STT stream closed/reset abruptly: {type(e).__name__}: {e}")
        else:
            print(f"[{client_id}] Error processing STT responses: {type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        print(f"[{client_id}] STT response processing finished.")
        stop_event.set()

# (Keep all other functions like audio_request_generator, process_google_stt_responses, etc., the same
# as in the previous "complete code" response where requests_iterable included the initial config message)

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    print(f"WebSocket connection accepted for client: {client_id}")
    
    credentials_path = os.path.join(os.path.dirname(__file__), "credentials.json")
    if not os.path.exists(credentials_path):
        print(f"ERROR [{client_id}]: Credentials file not found at {credentials_path}")
        await websocket.close(code=1011)
        return

    stt_client = None
    try:
        stt_client = SpeechClient.from_service_account_json(credentials_path)
        print(f"DEBUG [{client_id}]: Type of stt_client is: {type(stt_client)}")
    except Exception as e:
        print(f"ERROR [{client_id}]: Failed to initialize SpeechClient: {e}")
        traceback.print_exc()
        await websocket.close(code=1011)
        return
        
    recognition_config_proto = RecognitionConfig(
        encoding=AUDIO_ENCODING,
        sample_rate_hertz=SAMPLE_RATE_HERTZ,
        language_code=LANGUAGE_CODE,
        enable_automatic_punctuation=True,
    )
    
    streaming_config_proto = StreamingRecognitionConfig(
        config=recognition_config_proto,
        interim_results=True
    )
    
    # This is the first request message that includes the configuration.
    # Our audio_request_generator will yield this first.
    initial_stt_request_message = StreamingRecognizeRequest(streaming_config=streaming_config_proto)
    
    stop_event = asyncio.Event()

    # Use the original audio_request_generator that yields the initial_stt_request_message first
    requests_iterable = audio_request_generator(
        websocket, 
        initial_stt_request_message, 
        stop_event, 
        client_id
    )
    
    google_responses_iterator = None
    response_processor_task = None

    try:
        print(f"DEBUG [{client_id}]: Attempting to call stt_client.streaming_recognize...")
        
        # *** WORKAROUND CALL for older/problematic library versions ***
        # This attempts to satisfy SpeechHelpers.streaming_recognize(self, config, requests, ...)
        # by passing None for its 'config' argument, relying on our 'requests_iterable'
        # to correctly provide the initial config request.
        google_responses_iterator = stt_client.streaming_recognize(
            None,  # Pass None for the 'config' parameter of SpeechHelpers
            requests_iterable  # Our generator provides the config in its first yielded item
        )
        
        print(f"DEBUG [{client_id}]: Successfully called stt_client.streaming_recognize.")

        response_processor_task = asyncio.create_task(
            process_google_stt_responses(google_responses_iterator, websocket, client_id, stop_event)
        )

        await stop_event.wait()
        print(f"[{client_id}] Stop event triggered. Initiating shutdown of tasks.")

    except Exception as e:
        print(f"ERROR [{client_id}]: Error during STT setup or main handling: {type(e).__name__}: {e}")
        traceback.print_exc()
        stop_event.set()
    finally:
        # ... (rest of the finally block remains the same) ...
        print(f"[{client_id}] Cleaning up WebSocket connection and related tasks.")
        stop_event.set()

        if response_processor_task and not response_processor_task.done():
            response_processor_task.cancel()
            try:
                await response_processor_task
            except asyncio.CancelledError:
                print(f"[{client_id}] Response processor task successfully cancelled.")
            except Exception as e_task_cleanup:
                print(f"[{client_id}] Error during response_processor_task cleanup: {e_task_cleanup}")
        
        if websocket.client_state != WebSocketState.DISCONNECTED:
            try:
                await websocket.close(code=1000)
                print(f"[{client_id}] WebSocket connection closed from server-side.")
            except Exception as e_ws_close:
                print(f"ERROR [{client_id}] closing WebSocket: {e_ws_close}")
        
        print(f"[{client_id}] WebSocket endpoint processing finished for {client_id}.")

# Ensure all other functions (audio_request_generator, process_google_stt_responses, etc.)
# and imports are included as in the previous "complete code" response.
# The main change is only within the `try` block in `websocket_endpoint` for the
# `stt_client.streaming_recognize` call.
# Remember to include if __name__ == "__main__": block as well.

if __name__ == "__main__":
    import uvicorn
    print(f"Script directory (for credentials.json): {os.path.dirname(__file__)}")
    print(f"Current working directory: {os.getcwd()}")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")