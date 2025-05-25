# Troubleshooting Guide

This document outlines the key errors encountered during the setup and running of the Interview Copilot application and the steps taken to resolve them.

## Initial Issues & Code Reversion

**Problem:** The user reported an error in the terminal and requested to revert the code to a previous state.

**Troubleshooting:** Since the specific error was not initially captured, the decision was made to revert the codebase using the available history in the `.history` directory.

**Resolution:** The backend (`main.py`, `requirements.txt`) and some frontend files were restored to versions from the `.history` directory. This involved:
* Listing contents of `.history`, `.history/backend`, and `.history/frontend` to identify potential restoration points.
* Reading the content of selected historical files.
* Replacing the current files with the historical versions using the `edit_file` tool.

**Post-Reversion Steps:** After restoring files, it's crucial to ensure dependencies match the reverted code. The following commands were necessary:

```bash
# In the backend directory
cd backend
.\venv\Scripts\activate # or source venv/bin/activate on Linux/macOS
pip install -r requirements.txt
```

```bash
# In the frontend directory
cd frontend
npm install
```

## ImportError: cannot import name 'enums' from 'google.cloud.speech'

**Problem:** After reverting the code and attempting to run the backend server, the following error appeared:

```
ImportError: cannot import name 'enums' from 'google.cloud.speech' (C:\Users\Hardeep\OneDrive\Desktop\Cursor interview copoilet\backend\venv\Lib\site-packages\google\cloud\speech\__init__.py)
```

**Explanation:** This error indicated that the installed version of the `google-cloud-speech` Python library did not expose `enums` and `types` directly under the `google.cloud.speech` namespace. This is typical of changes in library versions where the import paths are modified.

**Resolution:** The import statement and subsequent usage in `backend/main.py` were updated to align with the structure of the installed library. The incorrect import:

```python
from google.cloud.speech import enums, types
```

was removed, and the code was modified to use objects directly from the `google.cloud.speech_v1` client, which was already imported as `speech`:

```python
from google.cloud import speech_v1 as speech
# ... later in code ...
config = speech.RecognitionConfig(...)
streaming_config = speech.StreamingRecognitionConfig(...)
request = speech.StreamingRecognizeRequest(...)
```

**Action:** Used the `edit_file` tool to modify `backend/main.py` to reflect the correct import and usage.

## google.auth.exceptions.DefaultCredentialsError: File ... was not found

**Problem:** After fixing the import error, a new error related to Google Cloud credentials appeared when starting the backend server:

```
google.auth.exceptions.DefaultCredentialsError: File C:\Users\Hardeep\Downloads\gen-lang-client-0769471387-17a4f9d05aee.json was not found.
```

**Explanation:** The application was attempting to load Google Cloud credentials from a specific file path (`C:\Users\Hardeep\Downloads\gen-lang-client-0769471387-17a4f9d05aee.json`), but the file was not found at that location. The `get_stt_client` function in `backend/main.py` had logic to find credentials, but it wasn't correctly locating the file.

**Resolution:** The `get_stt_client` function in `backend/main.py` was made more robust to check for the credentials file in multiple common or expected locations, including the specific file name mentioned in the error and a standard `credentials.json` in the backend directory, in addition to the `GOOGLE_APPLICATION_CREDENTIALS` environment variable. A more informative error message was also added if no credentials file is found.

**Action:** Used the `edit_file` tool to modify the `get_stt_client` function in `backend/main.py`. Instructed the user to place their Google Cloud credentials JSON file in the `backend` directory.

**Final Steps to Run:**

1.  Place your Google Cloud credentials JSON file (`credentials.json` or the file mentioned in the error) inside the `backend` directory.
2.  In the backend directory, ensure the virtual environment is activated and dependencies are installed:
    ```bash
    cd backend
    .\venv\Scripts\activate # or source venv/bin/activate on Linux/macOS
    pip install -r requirements.txt
    ```
3.  Start the backend server:
    ```bash
    python -m uvicorn main:app --reload
    ```
4.  In a separate terminal, navigate to the frontend directory and start the frontend development server:
    ```bash
    cd frontend
    npm install # Only needed if you haven't run it recently or changed package.json
    npm run dev
    ```
5.  Open your browser to `http://localhost:5173` (using Chrome 120+ for tab audio capture).

## Issue: No transcription from Google Meet, but works for other sources (e.g., YouTube)

**Problem:** The application could successfully transcribe audio from sources like YouTube tabs when using `Share & Transcribe Tab`, but no transcription output was received when attempting the same with a Google Meet tab.

**Initial Observation:** The browser console showed a deprecation warning related to `ScriptProcessorNode` being used in the frontend's audio processing.

**Step 1: Address ScriptProcessorNode Deprecation**

*   **Action:** Refactored the frontend code (`frontend/src/App.jsx`) to replace `ScriptProcessorNode` with the recommended `AudioWorkletNode` and created a separate `frontend/src/audio-processor.js` file for the audio processing logic.
*   **Result:** The deprecation warning was resolved, but the issue with Google Meet transcription persisted. No errors were immediately visible in the console after this change, suggesting the audio pipeline setup was syntactically correct.

**Step 2: Add Logging to Audio Pipeline**

*   **Action:** Added extensive `console.log` statements in `frontend/src/App.jsx` and `frontend/src/audio-processor.js` to trace the audio stream from capture (`getDisplayMedia`) through the `AudioContext` and into the `AudioWorkletNode`.
*   **Result:** Logs confirmed that `getDisplayMedia` was initiated, an audio track was potentially selected (depending on user action in the browser prompt), the `AudioContext`, `AudioWorklet` module, and `AudioWorkletNode` were successfully created and connected. However, logs within the `AudioWorkletProcessor`'s `process` method were not appearing when capturing from Google Meet, indicating audio data was not reaching the processor.

**Step 3: Identify Potential Discrepancy with Google Meet Audio Capture**

*   **Reasoning:** Standard browser `getDisplayMedia` for tab audio can sometimes be inconsistent or blocked by complex web applications like Google Meet, which may have specific ways of handling audio internally.
*   **Observation (from similar applications):** Noticed that other successful live transcription applications often request microphone access in addition to or instead of relying solely on tab audio capture.

**Step 4: Combine Microphone Audio with Tab Audio**

*   **Action:** Modified the `frontend/src/App.jsx` `start` function to also request microphone access (`navigator.mediaDevices.getUserMedia`). Created a `MediaStreamSource` for the microphone stream. Used a `GainNode` as a simple mixer to combine the audio streams from both the display (if audio was captured) and the microphone (if access was granted). Connected this mixer to the `AudioWorkletNode`.
*   **Result:** By combining the microphone audio (a reliable source for the user's own speech within a meeting) with the potentially inconsistent tab audio, the application was able to receive sufficient audio data in the `AudioWorkletProcessor` to generate transcripts from Google Meet sessions.

**Resolution:** The issue was resolved by incorporating microphone audio capture and mixing it with the tab audio stream before processing and sending to the backend. This provides a more robust audio source, especially when dealing with complex web applications like Google Meet where `getDisplayMedia` tab audio capture may be unreliable. 