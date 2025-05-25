import os
import asyncio
from typing import AsyncGenerator # For type hinting
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from google.cloud.speech_v1.types import ( # More specific import for clarity
    RecognitionConfig,
    StreamingRecognitionConfig,
    StreamingRecognizeRequest,
    StreamingRecognizeResponse # For type hinting responses
)
from google.cloud.speech_v1 import SpeechClient # Explicit v1 import
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState # For checking websocket state

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Your React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Configuration for Google STT ---
# Ensure these match what your browser is sending.
# Common for browser WebAudio:
#   - If sending raw PCM: LINEAR16, sample_rate_hertz=16000 or 44100
#   - If sending WebM/Opus: WEBM_OPUS, sample_rate_hertz=48000 (as in your original code)
AUDIO_ENCODING = RecognitionConfig.AudioEncoding.WEBM_OPUS
SAMPLE_RATE_HERTZ = 48000
LANGUAGE_CODE = "en-US"
# --- End Configuration ---

async def audio_request_generator(
    websocket: WebSocket,
    initial_config_request: StreamingRecognizeRequest,
    stop_event: asyncio.Event
) -> AsyncGenerator[StreamingRecognizeRequest, None]:
    """
    Async generator that yields STT requests: first config, then audio data from WebSocket.
    """
    yield initial_config_request
    print(f"[{websocket.scope.get('client_id', 'UnknownClient')}] Sent initial config to Google STT.")
    try:
        while not stop_event.is_set():
            message = await websocket.receive() # Expects dict: {'type': 'websocket.receive', 'bytes': b'...' or 'text': '...'}
            
            if message.get('type') == 'websocket.disconnect':
                print(f"[{websocket.scope.get('client_id', 'UnknownClient')}] WebSocket disconnected by client during audio receive.")
                stop_event.set()
                break
            
            audio_chunk = message.get('bytes')
            if audio_chunk:
                if not audio_chunk: # Skip empty audio chunks
                    continue
                yield StreamingRecognizeRequest(audio_content=audio_chunk)
            
            text_message = message.get('text')
            if text_message:
                # You can implement control messages here, e.g., a custom "stop" signal
                print(f"[{websocket.scope.get('client_id', 'UnknownClient')}] Received text message from WebSocket: {text_message}")
                if text_message.upper() == "STOP_STREAMING_AUDIO":
                    print(f"[{websocket.scope.get('client_id', 'UnknownClient')}] Received STOP_STREAMING_AUDIO command.")
                    stop_event.set()
                    break
    except WebSocketDisconnect:
        print(f"[{websocket.scope.get('client_id', 'UnknownClient')}] WebSocket disconnected (WebSocketDisconnect exception in generator).")
    except asyncio.CancelledError:
        print(f"[{websocket.scope.get('client_id', 'UnknownClient')}] Audio request generator cancelled.")
    except Exception as e:
        print(f"[{websocket.scope.get('client_id', 'UnknownClient')}] Error in audio_request_generator: {type(e).__name__}: {e}")
    finally:
        print(f"[{websocket.scope.get('client_id', 'UnknownClient')}] Audio request generator finished.")
        stop_event.set() # Ensure stop_event is set on any exit path

async def process_google_stt_responses(
    responses_iterator: AsyncGenerator[StreamingRecognizeResponse, None],
    websocket: WebSocket,
    client_id: str,
    stop_event: asyncio.Event
):
    """
    Processes responses from Google STT and sends transcripts back to the client.
    """
    print(f"[{client_id}] Listening for STT responses...")
    try:
        async for response in responses_iterator:
            if stop_event.is_set(): # Check if we need to stop early
                break
            if not response.results:
                continue
            
            result = response.results[0]
            if not result.alternatives:
                continue
            
            transcript = result.alternatives[0].transcript
            is_final = result.is_final
            
            # print(f"[{client_id}] STT: '{transcript}' (Final: {is_final})") # Verbose logging
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
        if " RST_STREAM " in str(e) or "Http2StreamFramer" in str(e) or "EOF" in str(e) or "Stream removed" in str(e): # Common gRPC stream errors
            print(f"[{client_id}] STT stream closed/reset abruptly: {type(e).__name__}: {e}")
        else:
            print(f"[{client_id}] Error processing STT responses: {type(e).__name__}: {e}")
    finally:
        print(f"[{client_id}] STT response processing finished.")
        stop_event.set() # Signal other tasks to stop if this one finishes/errors


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    websocket.scope['client_id'] = client_id # Store client_id in scope for logging
    print(f"WebSocket connection accepted for client: {client_id}")
    
    credentials_path = os.path.join(os.path.dirname(__file__), "credentials.json")
    if not os.path.exists(credentials_path):
        print(f"ERROR [{client_id}]: Credentials file not found at {credentials_path}")
        await websocket.close(code=1008) # Policy Violation or 1011 (Internal Error)
        return

    try:
        stt_client = SpeechClient.from_service_account_json(credentials_path)
    except Exception as e:
        print(f"ERROR [{client_id}]: Failed to initialize SpeechClient: {e}")
        await websocket.close(code=1011) # Internal server error
        return
        
    recognition_config = RecognitionConfig(
        encoding=AUDIO_ENCODING,
        sample_rate_hertz=SAMPLE_RATE_HERTZ,
        language_code=LANGUAGE_CODE,
        enable_automatic_punctuation=True,
        # model="telephony", # Consider specifying model for your use case (e.g., "telephony", "medical_dictation")
        # use_enhanced=True, # For enhanced models (might incur higher costs)
    )
    
    streaming_config = StreamingRecognitionConfig(
        config=recognition_config,
        interim_results=True  # Get intermediate results for live feedback
    )
    
    # The first request to Google STT must contain the configuration
    initial_stt_request = StreamingRecognizeRequest(streaming_config=streaming_config)
    
    stop_event = asyncio.Event() # Event to signal all tasks to stop

    # Create the asynchronous generator for STT requests from WebSocket audio
    requests_iterable = audio_request_generator(websocket, initial_stt_request, stop_event)
    
    google_responses_iterator = None
    try:
        # This is the main call to Google STT. It takes the async generator of requests.
        google_responses_iterator = stt_client.streaming_recognize(requests=requests_iterable)
    except Exception as e:
        print(f"ERROR [{client_id}]: Failed to start Google STT streaming_recognize call: {e}")
        await websocket.close(code=1011)
        return

    # Create a task to process responses from Google STT and send them back to the client
    response_processor_task = asyncio.create_task(
        process_google_stt_responses(google_responses_iterator, websocket, client_id, stop_event)
    )

    try:
        # Wait until the stop_event is set. This can be triggered by:
        # - WebSocket disconnection (in audio_request_generator or main loop)
        # - Errors in any task
        # - "STOP_STREAMING_AUDIO" command
        await stop_event.wait()
        print(f"[{client_id}] Stop event triggered. Initiating shutdown of tasks.")

    except Exception as e: # Catch any unexpected errors in this main handling scope
        print(f"ERROR [{client_id}] in main WebSocket handler: {e}")
        stop_event.set() # Ensure shutdown is triggered
    finally:
        print(f"[{client_id}] Cleaning up WebSocket connection and related tasks.")
        stop_event.set() # Ensure it's set for all tasks to see

        # Gracefully cancel and await the response processor task
        if response_processor_task and not response_processor_task.done():
            response_processor_task.cancel()
            try:
                await response_processor_task
            except asyncio.CancelledError:
                print(f"[{client_id}] Response processor task successfully cancelled.")
            except Exception as e_task_cleanup: # Catch errors during task cleanup
                print(f"[{client_id}] Error during response_processor_task cleanup: {e_task_cleanup}")
        
        # The audio_request_generator will stop because:
        # 1. stop_event is set.
        # 2. The WebSocket connection it's reading from closes.
        # 3. The `google_responses_iterator` (which consumes it) is closed/exhausted,
        #    often due to the gRPC stream ending.

        # Ensure WebSocket is closed if not already
        if websocket.client_state != WebSocketState.DISCONNECTED:
            try:
                await websocket.close(code=1000) # Normal closure
                print(f"[{client_id}] WebSocket connection closed from server-side.")
            except Exception as e_ws_close:
                print(f"ERROR [{client_id}] closing WebSocket: {e_ws_close}")
        
        print(f"[{client_id}] WebSocket endpoint processing finished.")

if __name__ == "__main__":
    import uvicorn
    # Make sure 'credentials.json' is in the same directory as this script,
    # or provide the correct path.
    print(f"Script directory (for credentials.json): {os.path.dirname(__file__)}")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")