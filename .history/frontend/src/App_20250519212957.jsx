import { useState, useRef, useEffect } from 'react'
import { v4 as uuidv4 } from 'uuid'

function App() {
  const [isRecording, setIsRecording] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [showModal, setShowModal] = useState(false)
  const [error, setError] = useState(null)
  const [isConnected, setIsConnected] = useState(false)

  const mediaRecorderRef = useRef(null)
  const videoRef = useRef(null)
  const wsRef = useRef(null)
  const clientId = useRef(uuidv4())

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: true
      })

      // Set up video preview
      if (videoRef.current) {
        videoRef.current.srcObject = stream
      }

      // Initialize WebSocket connection
      wsRef.current = new WebSocket(`ws://localhost:8000/ws/${clientId.current}`)
      
      wsRef.current.onopen = () => {
        setIsConnected(true)
        setError(null)
      }

      wsRef.current.onmessage = (event) => {
        const data = JSON.parse(event.data)
        if (data.is_final) {
          setTranscript(prev => prev + ' ' + data.transcript)
        } else {
          // Optionally display interim results, maybe in a different color or temporary area
          // console.log('Interim result:', data.transcript);
        }
      }

      wsRef.current.onerror = (error) => {
        setError('WebSocket error: ' + error.message)
        setIsConnected(false)
        console.error('WebSocket error:', error)
      }

      wsRef.current.onclose = () => {
        setIsConnected(false)
        console.log('WebSocket connection closed')
      }

      // Set up MediaRecorder
      const mimeType = 'audio/webm;codecs=opus'
      if (!MediaRecorder.isTypeSupported(mimeType)) {
        setError(`MIME type ${mimeType} is not supported by your browser.`)
        console.error(`MIME type ${mimeType} is not supported`)
        // Stop the stream if unsupported
        stream.getTracks().forEach(track => track.stop())
        return
      }

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: mimeType
      })

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(event.data)
        }
      }

      mediaRecorder.start(200) // Send chunks every 200ms
      mediaRecorderRef.current = mediaRecorder
      setIsRecording(true)
      setShowModal(false)

      // Optional: Handle MediaRecorder errors
      mediaRecorder.onerror = (event) => {
        setError('MediaRecorder error: ' + event.error.name + ': ' + event.error.message)
        console.error('MediaRecorder error:', event.error)
        stopRecording() // Attempt to clean up
      }

    } catch (err) {
      setError('Error starting recording: ' + err.message)
      console.error('Error starting recording:', err)
    }
  }

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    if (mediaRecorderRef.current?.stream) {
      mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop())
    }
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.close()
    }
    setIsRecording(false)
    setTranscript('')
  }

  // Cleanup on component unmount
  useEffect(() => {
    return () => {
      stopRecording()
    }
  }, [])

  return (
    <div className="min-h-screen bg-darker p-4">
      <div className="max-w-7xl mx-auto">
        <header className="mb-8">
          <h1 className="text-3xl font-bold text-white">Interview Copilot</h1>
        </header>

        {!isRecording ? (
          <div className="text-center">
            <button
              onClick={() => setShowModal(true)}
              className="bg-accent hover:bg-blue-600 text-white font-bold py-2 px-4 rounded"
            >
              Start Live Transcript
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="relative">
              <video
                ref={videoRef}
                autoPlay
                className="w-full rounded-lg"
              />
              <div className="absolute top-2 right-2">
                <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
              </div>
            </div>
            <div className="bg-dark p-4 rounded-lg">
              <div className="h-full overflow-y-auto">
                <p className="whitespace-pre-wrap">{transcript}</p>
              </div>
            </div>
            <div className="col-span-2 text-center">
              <button
                onClick={stopRecording}
                className="bg-red-500 hover:bg-red-600 text-white font-bold py-2 px-4 rounded"
              >
                Stop Recording
              </button>
            </div>
          </div>
        )}

        {showModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center">
            <div className="bg-dark p-6 rounded-lg max-w-md">
              <h2 className="text-xl font-bold mb-4">Start Recording</h2>
              <p className="mb-4">
                Please select your meeting tab and make sure to check "Share tab audio" in the sharing dialog.
              </p>
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setShowModal(false)}
                  className="bg-gray-600 hover:bg-gray-700 text-white font-bold py-2 px-4 rounded"
                >
                  Cancel
                </button>
                <button
                  onClick={startRecording}
                  className="bg-accent hover:bg-blue-600 text-white font-bold py-2 px-4 rounded"
                >
                  Start
                </button>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="fixed bottom-4 right-4 bg-red-500 text-white p-4 rounded-lg">
            {error}
          </div>
        )}
      </div>
    </div>
  )
}

export default App 