import os
import json
import asyncio
from typing import Dict, Any
from fastapi import FastAPI, WebSocket
from google.cloud.speech import RecognitionConfig, StreamingRecognitionConfig, SpeechClient, StreamingRecognizeRequest
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active WebSocket connections and their speech clients
active_connections: Dict[str, Dict[str, Any]] = {}

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    print(f"WebSocket connection accepted for client: {client_id}")
    
    # Initialize Google Speech-to-Text client with explicit credentials
    credentials_path = os.path.join(os.path.dirname(__file__), "credentials.json")
    client = SpeechClient.from_service_account_json(credentials_path)
    
    # Configure streaming recognition
    config = RecognitionConfig(
        encoding=RecognitionConfig.AudioEncoding.WEBM_OPUS,
        sample_rate_hertz=48000,
        language_code="en-US",
        enable_automatic_punctuation=True,
    )
    
    streaming_config = StreamingRecognitionConfig(
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
            # Add diagnostic prints here
            message = await websocket.receive()
            print(f"Received WebSocket message type: {message.get('type')}")
            print(f"Message keys: {message.keys()}")

            if message.get('bytes'):
                 print(f"Received BINARY message of size: {len(message['bytes'])}")
                 # print(f"First 20 bytes: {message['bytes'][:20]}") # Uncomment for more detail if needed
                 data = message['bytes']
            elif message.get('text'):
                 print(f"Received TEXT message: {message['text'][:100]}...") # Print first 100 chars
                 # If you get text here when expecting binary, this is a key issue.
                 # Depending on the text content, you might decide to ignore or handle specific messages (like socket.io probes)
                 continue # Skip processing text frames if expecting binary audio
            else:
                 print(f"Received unexpected message format: {message}")
                 continue # Skip unexpected formats

            print(f"Processing audio chunk from client {client_id} with size: {len(data)}") # <-- This should now print if binary data is received

            # Create recognition request
            request = StreamingRecognizeRequest(audio_content=data)
            
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