# Troubleshooting Guide

This document outlines the key issues encountered during the development of the Interview Copilot application and the steps taken to successfully resolve them, bringing the application to a functional state for live transcription from YouTube and Google Meet.

## 1. Initial Project Setup and Google Cloud Credentials

**Problem:** Getting the backend server to start and connect to Google Cloud Speech-to-Text.

**Resolution:**
*   Initialized a Git repository (`git init`) and configured user identity (`git config --global user.email`, `git config --global user.name`).
*   Ensured necessary Python dependencies were listed in `requirements.txt` and installed (`pip install -r requirements.txt`).
*   Made the `get_stt_client` function in `backend/main.py` more robust to locate Google Cloud credentials (`credentials.json` or specified file) in multiple standard/expected locations.
*   Verified Google Cloud Speech-to-Text API is enabled and billing is active for the associated GCP project.

**Relevant Tech/Methods:** Git, Python, FastAPI, Google Cloud Speech-to-Text API, `google-cloud-speech` library, File System operations (`os.path`), Environment Variables.

## 2. Google Meet Transcription Not Working (Initial State)

**Problem:** While basic transcription worked for YouTube tabs, capturing audio from Google Meet did not produce transcripts.

**Initial Observation:** A frontend console warning indicated the use of the deprecated `ScriptProcessorNode`.

**Resolution:**
*   Replaced the deprecated `ScriptProcessorNode` in `frontend/src/App.jsx` with the modern Web Audio API `AudioWorkletNode` for audio processing.
*   Created a separate `frontend/src/audio-processor.js` file containing the `AudioWorkletProcessor` logic for converting Float32 audio to 16-bit PCM.
*   Modified the frontend `start` function to capture audio from *both* `navigator.mediaDevices.getUserMedia` (microphone) and `navigator.mediaDevices.getDisplayMedia` (tab audio).
*   Used a Web Audio API `GainNode` as a mixer to combine the audio streams from the microphone and the display before sending to the `AudioWorkletNode`.
*   Removed the connection from the mixer to the `AudioContext` destination (`ctx.destination`) to prevent audio echo.

**Relevant Tech/Methods:** Web Audio API (`AudioContext`, `MediaStreamSource`, `GainNode`, `AudioWorklet`, `AudioWorkletNode`, `AudioWorkletProcessor`), `navigator.mediaDevices.getUserMedia`, `navigator.mediaDevices.getDisplayMedia`, JavaScript.

## 3. Attempt to Add Timestamps and Speaker Identification

**Problem:** Attempting to enable timestamp and speaker diarization features in the Google Cloud Speech-to-Text API configuration led to the application stopping all transcription output, even for sources that previously worked.

**Resolution:**
*   Diagnosed through backend logging that no responses were being received from the Google Cloud Speech-to-Text API after enabling these features.
*   Concluded that the issue was likely related to the Google Cloud project configuration, billing, quotas, or a compatibility problem with the specific API features and streaming conditions.
*   **Action Taken (Reversal):** Reverted the backend code (`backend/main.py`) to its state before requesting timestamp and speaker diarization to restore basic transcription functionality.

**Relevant Tech/Methods:** Google Cloud Speech-to-Text API configuration (`enable_word_time_offsets`, `enable_speaker_diarization`, `diarization_speaker_count`), Backend logging.

## 4. Frontend Display Issue (After Restoring Backend)

**Problem:** Although the backend was successfully receiving audio and sending transcriptions (verified in frontend console logs), the text was not appearing on the web page.

**Resolution:**
*   Identified that the frontend's `ws.onmessage` handler in `frontend/src/App.jsx` was not correctly updating the `lines` state to render the incoming transcript segments.
*   Modified the `ws.onmessage` logic to properly handle interim and final transcript results received from the backend, updating the `lines` state array with the received text.

**Relevant Tech/Methods:** React `useState`, WebSocket `onmessage` handling, JavaScript array manipulation.

## Conclusion

The application now successfully provides basic live transcription from both YouTube and Google Meet by capturing and mixing microphone and tab audio on the frontend and sending it to the backend for processing by the Google Cloud Speech-to-Text API configured for basic transcription. Issues encountered with advanced features were resolved by reverting to a stable configuration, and frontend display problems were fixed by correcting state update logic. 