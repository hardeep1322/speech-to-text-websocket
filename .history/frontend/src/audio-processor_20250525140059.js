class AudioProcessor extends AudioWorkletProcessor {
  process(inputs, outputs, parameters) {
    console.log("AudioProcessor process called.");
    const input = inputs[0];
    if (!input || input.length === 0) {
      console.log("AudioProcessor process: No input.");
      return true;
    }
    const inputChannel = input[0]; // Assuming mono audio
    if (!inputChannel || inputChannel.length === 0) {
      console.log("AudioProcessor process: No input channel.");
      return true;
    }

    // Convert Float32 [-1,1] to little-endian 16-bit PCM
    const pcm = new Int16Array(inputChannel.length);
    for (let i = 0; i < inputChannel.length; i++) {
      const s = Math.max(-1, Math.min(1, inputChannel[i]));
      pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }

    // Send the PCM data back to the main thread
    console.log("AudioProcessor: Posting message to main thread.");
    this.port.postMessage(pcm.buffer, [pcm.buffer]);

    return true;
  }
}

registerProcessor('audio-processor', AudioProcessor); 