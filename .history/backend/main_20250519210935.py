import os
import json
import asyncio
from typing import Dict, Any
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import speech
from google.cloud.speech import enums, types

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