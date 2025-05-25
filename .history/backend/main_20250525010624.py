import sys
print(f"Python version: {sys.version}")
try:
    import google.cloud.speech
    print(f"google-cloud-speech version: {google.cloud.speech.__version__}")
except ImportError:
    print("ERROR: google-cloud-speech library is not installed.")
    sys.exit(1)
except AttributeError:
    print("ERROR: google-cloud-speech library is installed, but version attribute is missing (likely very old).")
    sys.exit(1)

import os
import asyncio
import traceback # For detailed error logging
from typing import AsyncGenerator, Dict, Any # For type hinting

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

from google.cloud.speech_v1.types import (
    RecognitionConfig,
    StreamingRecognitionConfig,
    StreamingRecognizeRequest,
    StreamingRecognizeResponse
)
from google.cloud.speech_v1 import SpeechClient

# --- Configuration for Google STT ---
# Ensure these match what your browser is sending.
AUDIO_ENCODING = RecognitionConfig.AudioEncoding.WEBM_OPUS # Or LINEAR16, etc.
SAMPLE_RATE_HERTZ = 48000  # Or 16000 for LINEAR16 usually
LANGUAGE_CODE = "en-US"
# --- End Configuration ---

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Your React dev server
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
    # This generator yields the initial config request, then audio chunks from the WebSocket.
    try:
        print(f"[{client_id}] GEN: Yielding initial config request...")
        yield initial_config_request
        print(f"[{client_id}] GEN: Successfully yielded initial config request.")

        while not stop_event.is_set():
            print(f"[{client_id}] GEN: Waiting for WebSocket message (state: {websocket.client_state})...")
            message = await websocket.receive()
            print(f"[{client_id}] GEN: Received WebSocket message raw: {message}")

            if message.get('type') == 'websocket.disconnect':
                print(f"[{client_id}] GEN: WebSocket disconnected by client (message type 'websocket.disconnect').")
                stop_event.set()
                break

            audio_chunk = message.get('bytes')
            if audio_chunk:
                # print(f"[{client_id}] GEN: Yielding audio chunk of size {len(audio_chunk)}") # Verbose
                yield StreamingRecognizeRequest(audio_content=audio_chunk)
            
            text_message = message.get('text')
            if text_message:
                print(f"[{client_id}] GEN: Received text message from WebSocket: {text_message}")
                if text_message.upper() == "STOP_STREAMING_AUDIO":
                    print(f"[{client_id}] GEN: Received STOP_STREAMING_AUDIO command.")
                    stop_event.set()
                    break
            
            if not audio_chunk and not text_message and message.get('type') != 'websocket.disconnect':
                print(f"[{client_id}] GEN: Received unhandled WebSocket message type or empty message: {message}")

    except WebSocketDisconnect:
        print(f"[{client_id}] GEN: WebSocketDisconnect exception caught directly in generator!")
    except asyncio.CancelledError:
        print(f"[{client_id}] GEN: Audio request generator was cancelled.")
    except Exception as e:
        print(f"[{client_id}] GEN: Unexpected exception in generator: {type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        print(f"[{client_id}] GEN: Audio request generator finishing (stop_event: {stop_event.is_set()}).")
        if not stop_event.is_set():
            print(f"[{client_id}] GEN: Setting stop_event in finally block.")
            stop_event.set()

async def process_google_stt_responses(
    responses_iterator: AsyncGenerator[StreamingRecognizeResponse, None],
    websocket: WebSocket,
    client_id: str,
    stop_event: asyncio.Event
):
    """
    Processes responses from Google STT and sends transcripts back to the client.
    """
    print(f"[{client_id}] RES: Listening for STT responses...")
    try:
        async for response in responses_iterator:
            if stop_event.is_set():
                print(f"[{client_id}] RES: Stop event detected, breaking response loop.")
                break
            if not response.results:
                continue
            
            result = response.results[0]
            if not result.alternatives:
                continue
            
            transcript = result.alternatives[0].transcript
            is_final = result.is_final
            
            # print(f"[{client_id}] RES: Sending transcript: '{transcript}' (Final: {is_final})") # Verbose
            await websocket.send_json({
                "transcript": transcript,
                "is_final": is_final,
                "client_id": client_id
            })
            if is_final:
                 print(f"[{client_id}] RES: STT Final Transcript: '{transcript}'")

    except asyncio.CancelledError:
        print(f"[{client_id}] RES: STT response processing task cancelled.")
    except Exception as e:
        # Check for common gRPC stream-ending errors
        err_str = str(e).lower()
        if "rst_stream" in err_str or \
           "http2streamframer" in err_str or \
           "eof" in err_str or \
           "stream removed" in err_str or \
           "cancelled" in err_str or \
           "unavailable" in err_str: # Often seen when server closes stream
            print(f"[{client_id}] RES: STT stream closed/reset or unavailable: {type(e).__name__}: {e}")
        else:
            print(f"[{client_id}] RES: Error processing STT responses: {type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        print(f"[{client_id}] RES: STT response processing finished (stop_event: {stop_event.is_set()}).")
        if not stop_event.is_set():
            print(f"[{client_id}] RES: Setting stop_event in finally block.")
            stop_event.set()


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    print(f"WebSocket connection accepted for client: {client_id}")
    
    # Define credentials path relative to this file
    # Ensure 'credentials.json' is in the same directory as this script.
    base_dir = os.path.dirname(os.path.abspath(__file__))
    credentials_path = os.path.join(base_dir, "credentials.json")
    
    if not os.path.exists(credentials_path):
        print(f"ERROR [{client_id}]: Credentials file not found at {credentials_path}")
        await websocket.close(code=1011) # Internal Server Error
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
        # model="telephony", # Example: consider specifying a model
        # use_enhanced=True, # Example: for enhanced models (check pricing)
    )
    
    streaming_config_proto = StreamingRecognitionConfig(
        config=recognition_config_proto,
        interim_results=True
    )
    
    # This is the first request message that includes the configuration.
    initial_stt_request_message = StreamingRecognizeRequest(streaming_config=streaming_config_proto)
    
    stop_event = asyncio.Event()

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
        
        # Standard call for recent google-cloud-speech versions:
        # The 'requests_iterable' (audio_request_generator) provides the
        # StreamingRecognizeRequest with the streaming_config as its first item.
        google_responses_iterator = stt_client.streaming_recognize(
            requests=requests_iterable
        )
        
        print(f"DEBUG [{client_id}]: Successfully called stt_client.streaming_recognize.")

        response_processor_task = asyncio.create_task(
            process_google_stt_responses(google_responses_iterator, websocket, client_id, stop_event)
        )

        # Wait for either the response processor to finish or an explicit stop signal
        await stop_event.wait()
        print(f"[{client_id}] Main handler: Stop event triggered or task completed.")

    except Exception as e:
        print(f"ERROR [{client_id}]: Error during STT setup or main WebSocket handling: {type(e).__name__}: {e}")
        traceback.print_exc()
        stop_event.set() # Ensure other tasks are signalled to stop
    finally:
        print(f"[{client_id}] Main handler: Cleaning up WebSocket connection and related tasks (stop_event: {stop_event.is_set()}).")
        if not stop_event.is_set(): # Ensure stop_event is set for cleanup
             print(f"[{client_id}] Main handler: Setting stop_event in finally block.")
             stop_event.set()

        if response_processor_task and not response_processor_task.done():
            print(f"[{client_id}] Main handler: Cancelling response processor task.")
            response_processor_task.cancel()
            try:
                await response_processor_task
            except asyncio.CancelledError:
                print(f"[{client_id}] Main handler: Response processor task successfully cancelled.")
            except Exception as e_task_cleanup:
                print(f"[{client_id}] Main handler: Error during response_processor_task cleanup: {e_task_cleanup}")
        else:
            print(f"[{client_id}] Main handler: Response processor task was None or already done.")
        
        if websocket.client_state != WebSocketState.DISCONNECTED:
            try:
                print(f"[{client_id}] Main handler: Closing WebSocket connection from server-side.")
                await websocket.close(code=1000) # Normal closure
            except Exception as e_ws_close:
                print(f"ERROR [{client_id}] Main handler: Error closing WebSocket: {e_ws_close}")
        else:
            print(f"[{client_id}] Main handler: WebSocket already disconnected.")
        
        print(f"[{client_id}] Main handler: WebSocket endpoint processing finished for {client_id}.")

if __name__ == "__main__":
    import uvicorn
    print(f"Script directory (for credentials.json): {os.path.dirname(os.path.abspath(__file__))}")
    # print(f"Current working directory: {os.getcwd()}") # For additional context if needed
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")