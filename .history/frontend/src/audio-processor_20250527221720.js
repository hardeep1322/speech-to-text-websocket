class AudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferSize = 4096;
    this.buffer = new Float32Array(this.bufferSize);
    this.bufferIndex = 0;
  }

  process(inputs, outputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;

    const inputChannel = input[0];
    const source = inputChannel.length > 0 ? 'mic' : 'display';

    // Fill our buffer with the input data
    for (let i = 0; i < inputChannel.length; i++) {
      this.buffer[this.bufferIndex++] = inputChannel[i];

      // When buffer is full, convert to 16-bit PCM and send
      if (this.bufferIndex === this.bufferSize) {
        const pcmData = this.convertTo16BitPCM(this.buffer);
        this.port.postMessage({
          type: 'audio',
          source: source,
          audio: pcmData
        });
        this.bufferIndex = 0;
      }
    }

    return true;
  }

  convertTo16BitPCM(float32Array) {
    const pcmData = new Int16Array(float32Array.length);
    for (let i = 0; i < float32Array.length; i++) {
      // Convert float32 to int16
      const s = Math.max(-1, Math.min(1, float32Array[i]));
      pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return pcmData.buffer;
  }
}

registerProcessor('audio-processor', AudioProcessor);