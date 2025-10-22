import { Transform, TransformCallback } from 'stream';

/**
 * Custom Audio Transform
 * Applies custom DSP effects to raw PCM audio in Node.js
 * 
 * Input: Raw PCM s16le (signed 16-bit little-endian)
 * Output: Modified PCM s16le
 * 
 * This is where you can implement custom audio effects:
 * - Machine learning models
 * - Custom reverb/vocoder
 * - Real-time pitch detection
 * - Dynamic range compression
 * - Any effect not available in FFmpeg
 */

export class CustomAudioTransform extends Transform {
  private sampleRate: number;
  private channels: number;
  private echoBuffer: Int16Array;
  private echoDelay: number; // in samples
  private echoWritePos: number = 0;

  constructor(sampleRate: number, channels: number) {
    super();
    this.sampleRate = sampleRate;
    this.channels = channels;

    // Initialize echo buffer (500ms delay)
    this.echoDelay = Math.floor(sampleRate * 0.5); // 500ms delay
    this.echoBuffer = new Int16Array(this.echoDelay * channels);
    this.echoBuffer.fill(0);
  }

  _transform(chunk: Buffer, encoding: BufferEncoding, callback: TransformCallback): void {
    try {
      // Convert buffer to 16-bit signed integer array
      const samples = new Int16Array(
        chunk.buffer, 
        chunk.byteOffset, 
        chunk.length / 2
      );

      // Process audio samples
      for (let i = 0; i < samples.length; i += this.channels) {
        // Process each frame (all channels)
        for (let ch = 0; ch < this.channels; ch++) {
          const sampleIdx = i + ch;
          let sample = samples[sampleIdx];

          // Apply gain adjustment (boost by 20%)
          sample = Math.floor(sample * 1.2);

          // Add echo effect from delay buffer
          const echoIdx = (this.echoWritePos * this.channels + ch) % this.echoBuffer.length;
          const echoSample = this.echoBuffer[echoIdx];
          
          // Mix original with echo (60% original + 30% echo)
          sample = Math.floor(sample * 0.6 + echoSample * 0.3);

          // Clamp to valid 16-bit range
          sample = Math.min(32767, Math.max(-32768, sample));

          // Store current sample in echo buffer for future use
          this.echoBuffer[echoIdx] = sample;

          // Write processed sample back
          samples[sampleIdx] = sample;
        }

        // Advance echo buffer write position
        this.echoWritePos = (this.echoWritePos + 1) % this.echoDelay;
      }

      // Push modified PCM data downstream
      this.push(Buffer.from(samples.buffer, samples.byteOffset, samples.byteLength));
      callback();
    } catch (err) {
      callback(err instanceof Error ? err : new Error(String(err)));
    }
  }
}

/**
 * Alternative: Simple passthrough transform (for testing)
 * Uncomment to use this instead of the echo effect
 */
export class PassthroughAudioTransform extends Transform {
  constructor(sampleRate: number, channels: number) {
    super();
  }

  _transform(chunk: Buffer, encoding: BufferEncoding, callback: TransformCallback): void {
    // Simply pass data through without modification
    this.push(chunk);
    callback();
  }
}

/**
 * Alternative: Volume control transform
 */
export class VolumeControlTransform extends Transform {
  private gain: number;

  constructor(sampleRate: number, channels: number, gain: number = 1.5) {
    super();
    this.gain = gain;
  }

  _transform(chunk: Buffer, encoding: BufferEncoding, callback: TransformCallback): void {
    try {
      const samples = new Int16Array(
        chunk.buffer, 
        chunk.byteOffset, 
        chunk.length / 2
      );

      for (let i = 0; i < samples.length; i++) {
        let sample = samples[i] * this.gain;
        samples[i] = Math.min(32767, Math.max(-32768, Math.floor(sample)));
      }

      this.push(Buffer.from(samples.buffer, samples.byteOffset, samples.byteLength));
      callback();
    } catch (err) {
      callback(err instanceof Error ? err : new Error(String(err)));
    }
  }
}

