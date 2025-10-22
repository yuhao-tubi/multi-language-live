# Async Speech-to-Speech Processing Architecture

**Status:** Design Document  
**Last Updated:** October 22, 2025  
**Target:** Multi-Process HLS Audio Pipeline

---

## Overview

This document outlines the architectural changes needed to support **asynchronous Speech-to-Speech (S2S) processing** in the audio pipeline. Unlike the current synchronous PCM transform, S2S services introduce:

- **Variable latency** (100ms to 5+ seconds)
- **Async API calls** (HTTP/WebSocket/gRPC)
- **Buffering requirements** (for alignment)
- **A/V synchronization challenges**

---

## Table of Contents

1. [Current vs. Proposed Architecture](#current-vs-proposed-architecture)
2. [Architectural Challenges](#architectural-challenges)
3. [Solution Approaches](#solution-approaches)
4. [Recommended Implementation](#recommended-implementation)
5. [Code Examples](#code-examples)
6. [A/V Sync Strategies](#av-sync-strategies)
7. [Testing & Monitoring](#testing--monitoring)

---

## Current vs. Proposed Architecture

### Current (Synchronous Transform)

```
PCM In → Transform (sync, <1ms latency) → PCM Out
         ↓
         Instant processing per chunk
```

**Characteristics:**
- Frame-by-frame processing
- Predictable latency (~1ms per chunk)
- No buffering needed
- Simple backpressure handling

### Proposed (Async S2S Service)

```
PCM In → Buffer → S2S API Call → Wait for response → Align → PCM Out
         ↓        ↓               ↓                   ↓
         Queue    Async call      100ms-5s latency    Sync with video
```

**Characteristics:**
- Must buffer input audio
- Variable latency per request
- Requires output alignment
- Complex A/V sync management

---

## Architectural Challenges

### 1. **Variable Latency**
- S2S services take 100ms-5s to respond
- Latency varies based on:
  - Audio chunk length
  - Service load
  - Network conditions
  - Processing complexity (translation, etc.)

### 2. **Audio Continuity**
- Must send audio in appropriate chunks (1-5 seconds typical)
- Output must be continuous (no gaps or overlaps)
- Need to handle partial results or errors

### 3. **Video Buffer Management**
- Video stream continues while audio is processed
- Must buffer video to wait for audio
- Risk of buffer overflow if S2S is too slow

### 4. **A/V Synchronization**
- Output audio duration may differ from input
  - Translation changes word count
  - Different speaking rates
  - Pauses and silence handling
- Must align processed audio with original video timing

### 5. **Failure Handling**
- S2S service timeouts
- Rate limiting
- API errors
- Network issues

---

## Solution Approaches

### Approach 1: Delay-and-Align (Recommended for Live Streams)

**Strategy:** Buffer both video and audio, process audio async, then remux with alignment

```
Input Stream
  ├─→ Video → Buffer (delay by S2S latency) → Remux
  └─→ Audio → S2S Processing (async) ────────→ Remux
```

**Pros:**
- Maintains real-time streaming
- Handles variable latency
- Can recover from S2S failures

**Cons:**
- Adds fixed latency (buffer delay)
- Complex buffer management
- Memory overhead

### Approach 2: Stretch/Compress Audio (Best for Translation)

**Strategy:** Process audio async, then time-stretch output to match original duration

```
Audio → S2S → Time-stretch to original duration → Remux with original video
```

**Pros:**
- Perfect A/V sync
- Works with any S2S output length

**Cons:**
- Time-stretching can affect quality
- More CPU intensive
- Requires additional FFmpeg processing

### Approach 3: Replace-and-Republish (Simplest)

**Strategy:** Accept increased latency, process entirely, then re-stream

```
Full segment → Demux → S2S process all audio → Remux → Output with delay
```

**Pros:**
- Simple implementation
- Guaranteed consistency
- No complex buffering

**Cons:**
- High latency (not real-time)
- Not suitable for live streaming
- Better for VOD processing

---

## Recommended Implementation

We recommend **Approach 1 (Delay-and-Align)** with adaptive buffering for live streaming use cases.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    HLS Input Stream                              │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         v
                   ┌─────────────┐
                   │   Demux     │
                   └──┬──────┬───┘
                      │      │
               Video  │      │ Audio
                      │      │
                      v      v
            ┌──────────────┐ ┌────────────────────────────┐
            │ Video Buffer │ │  Audio Decode → PCM        │
            │ (Ring Buffer)│ └──────────┬─────────────────┘
            └──────┬───────┘            │
                   │                    v
                   │          ┌─────────────────────────────┐
                   │          │   Async S2S Transform       │
                   │          │  ┌────────────────────────┐ │
                   │          │  │ 1. Buffer PCM chunks   │ │
                   │          │  │ 2. Call S2S API        │ │
                   │          │  │ 3. Wait for response   │ │
                   │          │  │ 4. Align timestamps    │ │
                   │          │  │ 5. Output with sync    │ │
                   │          │  └────────────────────────┘ │
                   │          └──────────┬──────────────────┘
                   │                     │
                   │                     v
                   │          ┌──────────────────┐
                   │          │  Audio Encode    │
                   │          └─────────┬────────┘
                   │                    │
                   └────────────────────┘
                            │
                            v
                      ┌──────────┐
                      │  Remux   │
                      └────┬─────┘
                           │
                           v
                      ┌─────────┐
                      │   SRS   │
                      └─────────┘
```

### Key Components

#### 1. **Video Buffer**
- Ring buffer to hold video frames
- Size: `S2S_MAX_LATENCY + SAFETY_MARGIN` (e.g., 10 seconds)
- Drops oldest frames if S2S falls behind

#### 2. **Async S2S Transform**
- Buffers audio chunks (1-3 seconds recommended)
- Makes async API calls
- Queues results with timestamps
- Outputs aligned with video timing

#### 3. **Timestamp Alignment Manager**
- Tracks input/output timing
- Handles duration mismatches
- Inserts silence or trims as needed

---

## Code Examples

### 1. Video Buffer Implementation

```typescript
import { Readable, PassThrough } from 'stream';

/**
 * Ring buffer for video frames with configurable delay
 */
export class VideoDelayBuffer extends PassThrough {
  private buffer: Buffer[] = [];
  private maxBufferMs: number;
  private bufferStartTime: number | null = null;
  
  constructor(maxBufferMs: number = 10000) {
    super();
    this.maxBufferMs = maxBufferMs;
  }
  
  _transform(chunk: Buffer, encoding: BufferEncoding, callback: TransformCallback) {
    const now = Date.now();
    
    if (!this.bufferStartTime) {
      this.bufferStartTime = now;
    }
    
    // Add to buffer with timestamp
    this.buffer.push(chunk);
    
    // Calculate buffer duration (estimate based on chunk rate)
    const bufferDurationMs = now - this.bufferStartTime;
    
    // If buffer is full, start releasing frames
    if (bufferDurationMs >= this.maxBufferMs) {
      const oldestChunk = this.buffer.shift();
      if (oldestChunk) {
        this.push(oldestChunk);
      }
    }
    
    callback();
  }
  
  // Force flush remaining buffer (for shutdown)
  flushBuffer() {
    while (this.buffer.length > 0) {
      const chunk = this.buffer.shift();
      if (chunk) {
        this.push(chunk);
      }
    }
  }
}
```

### 2. Async S2S Transform

```typescript
import { Transform, TransformCallback } from 'stream';
import { performance } from 'perf_hooks';

interface S2SConfig {
  apiUrl: string;
  apiKey: string;
  chunkDurationMs: number;
  maxConcurrentRequests: number;
}

interface AudioChunk {
  data: Buffer;
  startTime: number;
  endTime: number;
  sampleCount: number;
}

export class AsyncS2STransform extends Transform {
  private config: S2SConfig;
  private sampleRate: number;
  private channels: number;
  
  private inputBuffer: Buffer[] = [];
  private inputBufferSamples: number = 0;
  private targetSamplesPerChunk: number;
  
  private processingQueue: AudioChunk[] = [];
  private outputQueue: Map<number, Buffer> = new Map(); // keyed by startTime
  private currentOutputTime: number = 0;
  
  private activeRequests: number = 0;
  private requestCounter: number = 0;
  
  constructor(sampleRate: number, channels: number, config: S2SConfig) {
    super();
    this.sampleRate = sampleRate;
    this.channels = channels;
    this.config = config;
    
    // Calculate samples per chunk (e.g., 2 seconds = 96000 samples at 48kHz stereo)
    this.targetSamplesPerChunk = Math.floor(
      (config.chunkDurationMs / 1000) * sampleRate * channels
    );
    
    console.log(`[S2S] Initialized: ${config.chunkDurationMs}ms chunks, ` +
                `${this.targetSamplesPerChunk} samples per chunk`);
  }
  
  async _transform(chunk: Buffer, encoding: BufferEncoding, callback: TransformCallback) {
    try {
      // Accumulate input buffer
      this.inputBuffer.push(chunk);
      this.inputBufferSamples += chunk.length / 2; // 16-bit samples
      
      // Process when we have enough samples
      while (this.inputBufferSamples >= this.targetSamplesPerChunk) {
        await this.processChunk();
      }
      
      // Try to output any ready chunks
      this.outputReadyChunks();
      
      callback();
    } catch (error) {
      callback(error instanceof Error ? error : new Error(String(error)));
    }
  }
  
  async _flush(callback: TransformCallback) {
    try {
      // Process remaining buffer
      if (this.inputBufferSamples > 0) {
        await this.processChunk();
      }
      
      // Wait for all pending requests
      while (this.activeRequests > 0) {
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      
      // Output remaining chunks
      this.outputReadyChunks(true);
      
      callback();
    } catch (error) {
      callback(error instanceof Error ? error : new Error(String(error)));
    }
  }
  
  private async processChunk(): Promise<void> {
    // Extract chunk from buffer
    const chunkSamples = Math.min(this.targetSamplesPerChunk, this.inputBufferSamples);
    const chunkBytes = chunkSamples * 2;
    
    let extracted = Buffer.alloc(chunkBytes);
    let offset = 0;
    
    while (offset < chunkBytes && this.inputBuffer.length > 0) {
      const buf = this.inputBuffer[0];
      const bytesNeeded = chunkBytes - offset;
      const bytesAvailable = buf.length;
      
      if (bytesAvailable <= bytesNeeded) {
        buf.copy(extracted, offset);
        offset += bytesAvailable;
        this.inputBuffer.shift();
      } else {
        buf.copy(extracted, offset, 0, bytesNeeded);
        this.inputBuffer[0] = buf.subarray(bytesNeeded);
        offset += bytesNeeded;
      }
    }
    
    this.inputBufferSamples -= chunkSamples;
    
    // Create audio chunk metadata
    const audioChunk: AudioChunk = {
      data: extracted,
      startTime: this.currentOutputTime,
      endTime: this.currentOutputTime + (chunkSamples / this.sampleRate / this.channels),
      sampleCount: chunkSamples
    };
    
    this.currentOutputTime = audioChunk.endTime;
    
    // Wait if too many concurrent requests
    while (this.activeRequests >= this.config.maxConcurrentRequests) {
      await new Promise(resolve => setTimeout(resolve, 10));
    }
    
    // Process async (don't await)
    this.processSpeechToSpeech(audioChunk);
  }
  
  private async processSpeechToSpeech(chunk: AudioChunk): Promise<void> {
    const requestId = this.requestCounter++;
    this.activeRequests++;
    
    console.log(`[S2S] Request ${requestId}: Processing ${chunk.sampleCount} samples ` +
                `(${(chunk.endTime - chunk.startTime).toFixed(2)}s)`);
    
    try {
      const startTime = performance.now();
      
      // Call S2S API (example with fetch)
      const response = await fetch(this.config.apiUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/octet-stream',
          'Authorization': `Bearer ${this.config.apiKey}`,
          'X-Sample-Rate': this.sampleRate.toString(),
          'X-Channels': this.channels.toString(),
        },
        body: chunk.data,
      });
      
      if (!response.ok) {
        throw new Error(`S2S API error: ${response.status} ${response.statusText}`);
      }
      
      const processedAudio = Buffer.from(await response.arrayBuffer());
      const endTime = performance.now();
      
      console.log(`[S2S] Request ${requestId}: Complete in ${(endTime - startTime).toFixed(0)}ms, ` +
                  `output ${processedAudio.length} bytes`);
      
      // Handle duration mismatch
      const outputSamples = processedAudio.length / 2;
      const inputSamples = chunk.sampleCount;
      const durationRatio = outputSamples / inputSamples;
      
      if (Math.abs(durationRatio - 1.0) > 0.1) {
        console.warn(`[S2S] Duration mismatch: output is ${(durationRatio * 100).toFixed(0)}% ` +
                     `of input (${outputSamples} vs ${inputSamples} samples)`);
      }
      
      // Store in output queue
      this.outputQueue.set(chunk.startTime, processedAudio);
      
    } catch (error) {
      console.error(`[S2S] Request ${requestId} failed:`, error);
      
      // Fallback: output silence or original audio
      console.warn(`[S2S] Using silence for failed chunk`);
      const silence = Buffer.alloc(chunk.data.length);
      this.outputQueue.set(chunk.startTime, silence);
      
    } finally {
      this.activeRequests--;
    }
  }
  
  private outputReadyChunks(final: boolean = false): void {
    // Output chunks in order
    const sortedTimes = Array.from(this.outputQueue.keys()).sort((a, b) => a - b);
    
    for (const time of sortedTimes) {
      // Only output if this is the next expected chunk (or final flush)
      if (final || this.outputQueue.has(time)) {
        const chunk = this.outputQueue.get(time);
        if (chunk) {
          this.push(chunk);
          this.outputQueue.delete(time);
        }
      }
    }
  }
}
```

### 3. Updated Pipeline Integration

```typescript
// In MultiProcessPipeline.ts

import { VideoDelayBuffer } from './transforms/VideoDelayBuffer.js';
import { AsyncS2STransform } from './transforms/AsyncS2STransform.js';

export class MultiProcessPipeline {
  // ... existing properties ...
  
  private videoBuffer: VideoDelayBuffer | null = null;
  private s2sTransform: AsyncS2STransform | null = null;
  
  async start(): Promise<void> {
    // ... existing HLS setup ...
    
    // Step 5: Create demux process (UNCHANGED)
    const demuxResult = createDemuxProcess(this.inputStream);
    this.processes.demux = demuxResult.process;
    
    // Step 6: Create video buffer (NEW)
    console.log('[PIPELINE] Creating video delay buffer...');
    this.videoBuffer = new VideoDelayBuffer(10000); // 10 second buffer
    demuxResult.videoOut.pipe(this.videoBuffer);
    
    // Step 7: Create decode process (UNCHANGED)
    const decodeResult = createDecodeProcess(
      demuxResult.audioOut,
      this.sampleRate,
      this.channels
    );
    this.processes.decode = decodeResult.process;
    
    // Step 8: Create async S2S transform (CHANGED)
    console.log('[PIPELINE] Creating async S2S transform...');
    this.s2sTransform = new AsyncS2STransform(
      this.sampleRate,
      this.channels,
      {
        apiUrl: process.env.S2S_API_URL || 'https://api.s2s-service.com/process',
        apiKey: process.env.S2S_API_KEY || '',
        chunkDurationMs: 2000, // 2 second chunks
        maxConcurrentRequests: 3
      }
    );
    
    // Step 9: Create encode process (UNCHANGED)
    const processedPcm = decodeResult.pcmOut.pipe(this.s2sTransform);
    const encodeResult = createEncodeProcess(
      processedPcm,
      this.sampleRate,
      this.channels
    );
    this.processes.encode = encodeResult.process;
    
    // Step 10: Create remux process with buffered video (CHANGED)
    const remuxResult = createRemuxProcess(
      this.videoBuffer,  // Use buffered video instead of direct
      encodeResult.aacOut,
      this.srsRtmpUrl
    );
    this.processes.remux = remuxResult.process;
    
    // ... rest of setup ...
  }
  
  async stop(): Promise<void> {
    // Flush video buffer before stopping
    if (this.videoBuffer) {
      this.videoBuffer.flushBuffer();
    }
    
    // ... existing stop logic ...
  }
}
```

---

## A/V Sync Strategies

### Strategy 1: Fixed Delay Buffer (Simple)

Set video delay to match maximum expected S2S latency:

```typescript
const VIDEO_DELAY_MS = 5000; // 5 seconds
const videoBuffer = new VideoDelayBuffer(VIDEO_DELAY_MS);
```

**Pros:** Simple, predictable  
**Cons:** Always adds maximum latency even if S2S is fast

### Strategy 2: Adaptive Buffer (Recommended)

Adjust video buffer based on actual S2S performance:

```typescript
export class AdaptiveVideoBuffer extends PassThrough {
  private buffer: Array<{ chunk: Buffer; timestamp: number }> = [];
  private targetDelayMs: number = 3000;
  private measuredLatencies: number[] = [];
  
  updateTargetDelay(latencyMs: number) {
    this.measuredLatencies.push(latencyMs);
    
    // Keep last 10 measurements
    if (this.measuredLatencies.length > 10) {
      this.measuredLatencies.shift();
    }
    
    // Set target to 95th percentile + safety margin
    const sorted = [...this.measuredLatencies].sort((a, b) => a - b);
    const p95Index = Math.floor(sorted.length * 0.95);
    this.targetDelayMs = sorted[p95Index] + 1000; // +1s safety margin
    
    console.log(`[VIDEO_BUFFER] Adjusted delay to ${this.targetDelayMs}ms`);
  }
  
  _transform(chunk: Buffer, encoding: BufferEncoding, callback: TransformCallback) {
    const now = Date.now();
    this.buffer.push({ chunk, timestamp: now });
    
    // Release chunks older than target delay
    while (this.buffer.length > 0) {
      const oldest = this.buffer[0];
      if (now - oldest.timestamp >= this.targetDelayMs) {
        this.push(oldest.chunk);
        this.buffer.shift();
      } else {
        break;
      }
    }
    
    callback();
  }
}
```

### Strategy 3: Time-Stretching Output

If S2S output duration doesn't match input, use FFmpeg time-stretching:

```typescript
// Add a time-stretch process after encode
export function createTimeStretchProcess(
  audioStream: Readable,
  targetDuration: number,
  actualDuration: number
): { process: ChildProcess; audioOut: Readable } {
  
  const stretchFactor = targetDuration / actualDuration;
  
  const args = [
    '-f', 'nut',
    '-i', 'pipe:0',
    '-af', `atempo=${stretchFactor}`, // Time stretch
    '-f', 'nut',
    'pipe:1'
  ];
  
  const ffmpegProcess = spawn('ffmpeg', args, {
    stdio: ['pipe', 'pipe', 'pipe']
  });
  
  audioStream.pipe(ffmpegProcess.stdin);
  
  return {
    process: ffmpegProcess,
    audioOut: ffmpegProcess.stdout as Readable
  };
}
```

---

## Testing & Monitoring

### Key Metrics to Track

```typescript
interface PipelineMetrics {
  // S2S Performance
  s2sLatencyMs: number[];
  s2sSuccessRate: number;
  s2sErrors: number;
  
  // Buffer Status
  videoBufferSizeBytes: number;
  audioBufferSizeBytes: number;
  
  // Sync Status
  avSyncOffsetMs: number;
  droppedVideoFrames: number;
  audioGapsMs: number;
  
  // Throughput
  inputBitrate: number;
  outputBitrate: number;
}
```

### Logging Implementation

```typescript
class PipelineMonitor {
  private metrics: PipelineMetrics;
  
  logS2SRequest(startTime: number, endTime: number, success: boolean) {
    const latency = endTime - startTime;
    this.metrics.s2sLatencyMs.push(latency);
    
    if (success) {
      this.metrics.s2sSuccessRate = 
        (this.metrics.s2sSuccessRate * 0.95) + 0.05;
    } else {
      this.metrics.s2sSuccessRate *= 0.95;
      this.metrics.s2sErrors++;
    }
    
    console.log(`[METRICS] S2S latency: ${latency}ms, ` +
                `success rate: ${(this.metrics.s2sSuccessRate * 100).toFixed(1)}%`);
  }
  
  checkAVSync() {
    // Parse FFmpeg remux logs for A/V sync info
    // Log warnings if drift exceeds thresholds
  }
}
```

### Test Suite

```bash
# Test 1: Sync verification with test pattern
npm run test:av-sync

# Test 2: S2S latency simulation
npm run test:s2s-latency -- --latency=2000

# Test 3: Error handling
npm run test:s2s-failures -- --error-rate=0.1

# Test 4: Load test
npm run test:concurrent-streams -- --count=10
```

---

## Migration Path

### Phase 1: Implement Video Buffer (Week 1)
- [ ] Add `VideoDelayBuffer` class
- [ ] Integrate into pipeline
- [ ] Test with existing sync transform
- [ ] Verify no regression

### Phase 2: Async S2S Transform (Week 2)
- [ ] Implement `AsyncS2STransform` base class
- [ ] Add mock S2S service for testing
- [ ] Test with various latencies
- [ ] Implement error handling

### Phase 3: Integration (Week 3)
- [ ] Connect real S2S service
- [ ] Implement adaptive buffering
- [ ] Add monitoring and metrics
- [ ] Load testing

### Phase 4: Production (Week 4)
- [ ] Deploy to staging
- [ ] Performance tuning
- [ ] Documentation
- [ ] Production rollout

---

## Configuration

### Environment Variables

```bash
# S2S Service
S2S_API_URL=https://api.s2s-service.com/process
S2S_API_KEY=your_api_key_here
S2S_CHUNK_DURATION_MS=2000
S2S_MAX_CONCURRENT_REQUESTS=3

# Buffer Configuration
VIDEO_BUFFER_SIZE_MS=10000
ADAPTIVE_BUFFER=true

# Performance
S2S_TIMEOUT_MS=10000
S2S_RETRY_ATTEMPTS=2
```

### API Configuration

```typescript
interface S2SServiceConfig {
  apiUrl: string;
  apiKey: string;
  timeout: number;
  retryAttempts: number;
  chunkDurationMs: number;
  maxConcurrentRequests: number;
}
```

---

## Troubleshooting

### Problem: S2S service too slow, video buffer overflows

**Solution:** 
- Increase video buffer size
- Reduce S2S chunk duration (smaller chunks = faster response)
- Add more concurrent requests
- Consider faster S2S service

### Problem: Audio gaps in output

**Solution:**
- Check S2S error rate
- Implement better fallback (silence or original audio)
- Reduce concurrent requests to avoid rate limiting

### Problem: A/V gradually drifts out of sync

**Solution:**
- Implement adaptive buffer adjustment
- Add time-stretching for output alignment
- Monitor FFmpeg remux logs for sync warnings

---

## References

- [FFmpeg atempo filter](https://ffmpeg.org/ffmpeg-filters.html#atempo)
- [Node.js Transform Streams](https://nodejs.org/api/stream.html#stream_class_stream_transform)
- [Speech-to-Speech APIs](https://platform.openai.com/docs/guides/speech-to-speech) (example)

---

**Next Steps:**
1. Choose S2S service provider
2. Implement video buffer
3. Create async transform with mock S2S
4. Test and tune buffer sizes
5. Deploy to production


