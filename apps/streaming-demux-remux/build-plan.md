# Multi-Process HLS Audio Pipeline with SRS Integration

## Architecture Overview

**Multi-Process Pipeline Design:**

```
HLS Input → Process 1 (Demux) → Process 2 (Decode Audio) → Node.js Transform (Custom Processing) 
→ Process 3 (Re-encode) → Process 4 (Remux + Video Passthrough) → RTMP Push to SRS
```

**Key Differences from Single-Process:**

- **4 FFmpeg processes** connected via pipes through Node.js
- **Custom audio manipulation** in Node.js (raw PCM buffer processing)
- **SRS output** instead of static file serving
- **Nut format** for inter-process pipes to preserve timestamps

## Implementation Steps

### 1. Project Setup (`demo/streaming-demux-remux/`)

**Create `package.json`:**

```json
{
  "name": "streaming-demux-remux",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "build": "tsc",
    "dev": "nodemon --exec ts-node src/main.ts",
    "start": "node dist/main.js"
  }
}
```

**Dependencies:**

- Production: `m3u8-parser`, `m3u8stream`
- Dev: `typescript`, `ts-node`, `nodemon`, `@types/node`, `@types/m3u8-parser`

**Create `tsconfig.json`:**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "outDir": "./dist",
    "rootDir": "./src",
    "esModuleInterop": true,
    "strict": true,
    "skipLibCheck": true
  }
}
```

**Create `.env.example`:**

```
SOURCE_HLS_URL=https://example.com/stream/master.m3u8
SRS_RTMP_URL=rtmp://localhost/live/processed
AUDIO_SAMPLE_RATE=48000
AUDIO_CHANNELS=2
```

### 2. Core Pipeline Orchestrator (`src/MultiProcessPipeline.ts`)

**Class: `MultiProcessPipeline`**

**Properties:**

```typescript
private sourceUrl: string;
private srsRtmpUrl: string;
private processes: {
  demux: ChildProcess | null;
  decode: ChildProcess | null;
  encode: ChildProcess | null;
  remux: ChildProcess | null;
};
private inputStream: Readable | null;
private audioTransform: Transform | null;
```

**Constructor:** `constructor(sourceUrl: string, srsRtmpUrl: string, sampleRate: number, channels: number)`

**Method: `start(): Promise<void>`**

1. Fetch and parse HLS manifest using `m3u8-parser`
2. Select first variant and create `m3u8stream`
3. Spawn 4 FFmpeg processes in sequence
4. Connect pipeline: `HLS stream → demux → decode → Node.js → encode → remux → SRS`
5. Set up error handlers for all processes and streams

**Method: `stop(): Promise<void>`**

1. Send SIGTERM to all 4 processes in reverse order (remux → encode → decode → demux)
2. Wait for graceful shutdown with timeout
3. Clean up all event listeners and stream references

### 3. Process 1: Demultiplexer (`src/processes/DemuxProcess.ts`)

**Purpose:** Separate video and audio streams from HLS input

**Function: `createDemuxProcess(inputStream: Readable): { process: ChildProcess, videoOut: Readable, audioOut: Readable }`**

**FFmpeg Command:**

```typescript
[
  '-i', 'pipe:0',           // HLS input from stdin
  '-map', '0:v',            // Select video stream
  '-c:v', 'copy',           // Copy video without re-encoding
  '-f', 'nut',              // Nut container preserves timestamps
  'pipe:3',                 // Video output to fd 3
  '-map', '0:a',            // Select audio stream
  '-c:a', 'copy',           // Keep audio compressed for now
  '-f', 'nut',              // Nut container for audio
  'pipe:4'                  // Audio output to fd 4
]
```

**Stdio Configuration:** `stdio: ['pipe', 'pipe', 'pipe', 'pipe', 'pipe']`

- fd 0 (stdin): HLS input
- fd 1 (stdout): unused
- fd 2 (stderr): logs
- fd 3: video output stream
- fd 4: audio output stream

**Implementation:**

- Pipe `inputStream` to demux stdin
- Return video stream from fd 3 and audio stream from fd 4
- Monitor stderr for errors

### 4. Process 2: Audio Decoder (`src/processes/DecodeProcess.ts`)

**Purpose:** Decode compressed audio to raw PCM for Node.js processing

**Function: `createDecodeProcess(audioStream: Readable, sampleRate: number, channels: number): { process: ChildProcess, pcmOut: Readable }`**

**FFmpeg Command:**

```typescript
[
  '-f', 'nut',              // Input is Nut container with audio
  '-i', 'pipe:0',           // Audio from demux process
  '-vn',                    // No video
  '-f', 's16le',            // Signed 16-bit little-endian PCM
  '-acodec', 'pcm_s16le',   // PCM codec
  '-ar', sampleRate,        // Sample rate (e.g., 48000)
  '-ac', channels,          // Channels (e.g., 2 for stereo)
  'pipe:1'                  // PCM output to stdout
]
```

**Output Format:** Raw PCM bytes (s16le)

- 2 bytes per sample
- Interleaved channels (L, R, L, R for stereo)
- No headers, pure audio data

### 5. Custom Audio Transform (`src/transforms/AudioProcessor.ts`)

**Class: `CustomAudioTransform extends Transform`**

**Purpose:** Apply custom DSP effects to raw PCM audio in Node.js

**Constructor:** `constructor(sampleRate: number, channels: number)`

**Method: `_transform(chunk: Buffer, encoding: string, callback: Function)`**

**Processing Logic:**

```typescript
// Read 16-bit samples from buffer
const samples = new Int16Array(chunk.buffer, chunk.byteOffset, chunk.length / 2);

// Apply custom effect (example: simple gain + echo)
for (let i = 0; i < samples.length; i += channels) {
  // Process each frame (L+R for stereo)
  for (let ch = 0; ch < channels; ch++) {
    let sample = samples[i + ch];
    
    // Custom DSP: gain adjustment
    sample = Math.min(32767, Math.max(-32768, sample * 1.2));
    
    // Add echo from delay buffer (implement ring buffer)
    // Apply custom filters, analysis, ML models, etc.
    
    samples[i + ch] = sample;
  }
}

// Push modified PCM data downstream
this.push(Buffer.from(samples.buffer));
callback();
```

**Extensibility:** This is where custom audio algorithms go:

- Machine learning models
- Custom reverb/vocoder
- Real-time pitch detection
- Dynamic range compression
- Any effect not available in FFmpeg

### 6. Process 3: Audio Re-encoder (`src/processes/EncodeProcess.ts`)

**Purpose:** Re-encode PCM audio to AAC

**Function: `createEncodeProcess(pcmStream: Readable, sampleRate: number, channels: number): { process: ChildProcess, aacOut: Readable }`**

**FFmpeg Command:**

```typescript
[
  '-f', 's16le',            // Input format: raw PCM
  '-ar', sampleRate,        // Must match decode output
  '-ac', channels,          // Must match decode output
  '-i', 'pipe:0',           // PCM input from Node.js transform
  '-c:a', 'aac',            // Encode to AAC
  '-b:a', '128k',           // Audio bitrate
  '-f', 'nut',              // Nut container with timestamps
  'pipe:1'                  // Encoded audio to stdout
]
```

**Critical:** Use `-fflags +genpts` if timestamp drift occurs

### 7. Process 4: Remux and RTMP Push (`src/processes/RemuxProcess.ts`)

**Purpose:** Combine untouched video with processed audio, push to SRS

**Function: `createRemuxProcess(videoStream: Readable, audioStream: Readable, rtmpUrl: string): { process: ChildProcess }`**

**FFmpeg Command:**

```typescript
[
  '-f', 'nut',              // Video input format
  '-i', 'pipe:3',           // Original video from demux (fd 3)
  '-f', 'nut',              // Audio input format
  '-i', 'pipe:4',           // Processed audio from encoder (fd 4)
  '-map', '0:v',            // Take video from first input
  '-c:v', 'copy',           // Copy video (no re-encoding)
  '-map', '1:a',            // Take audio from second input
  '-c:a', 'copy',           // Copy audio (already AAC encoded)
  rtmpUrl                   // Push to SRS (e.g., rtmp://localhost/live/processed)
]
```

**Stdio Configuration:** `stdio: ['ignore', 'pipe', 'pipe', 'pipe', 'pipe']`

- fd 3: video input
- fd 4: audio input
- stderr: monitor for RTMP connection status

### 8. Pipeline Connection (`src/MultiProcessPipeline.ts` implementation)

**In `start()` method:**

```typescript
// 1. Fetch HLS and create segment stream
const hlsStream = m3u8stream(mediaPlaylistUrl);

// 2. Create demux process
const { process: demux, videoOut, audioOut } = createDemuxProcess(hlsStream);

// 3. Create decode process (only for audio)
const { process: decode, pcmOut } = createDecodeProcess(audioOut, this.sampleRate, this.channels);

// 4. Create custom audio transform
const audioTransform = new CustomAudioTransform(this.sampleRate, this.channels);

// 5. Create encode process
const { process: encode, aacOut } = createEncodeProcess(
  pcmOut.pipe(audioTransform), 
  this.sampleRate, 
  this.channels
);

// 6. Create remux process (takes video + processed audio)
const { process: remux } = createRemuxProcess(videoOut, aacOut, this.srsRtmpUrl);

// 7. Store all processes for lifecycle management
this.processes = { demux, decode, encode, remux };

// 8. Set up error handlers
this._setupErrorHandlers();
```

### 9. Error Handling and Synchronization

**Critical Considerations:**

**Backpressure Management:**

- All streams must respect Node.js backpressure
- Use `.pipe()` which handles this automatically
- Monitor for `drain` events if manually writing

**Timestamp Preservation:**

- Nut format maintains PTS/DTS through decode/encode cycle
- Use `-fflags +genpts` on encoder if sync issues occur
- Monitor FFmpeg logs for "Non-monotonous DTS" warnings

**Process Failure Cascade:**

- If any process exits unexpectedly, kill entire pipeline
- Log exit codes from all processes
- Implement retry logic with exponential backoff

**Error Handler Implementation:**

```typescript
private _setupErrorHandlers(): void {
  // Monitor all process exits
  Object.entries(this.processes).forEach(([name, proc]) => {
    proc.on('exit', (code, signal) => {
      console.error(`[${name}] exited: code=${code}, signal=${signal}`);
      if (code !== 0) this.stop(); // Kill entire pipeline on failure
    });
    
    proc.stderr?.on('data', (data) => {
      console.log(`[${name}]: ${data.toString()}`);
    });
  });
  
  // Handle stream errors
  this.inputStream?.on('error', (err) => {
    console.error('[HLS Input] Error:', err);
    this.stop();
  });
}
```

### 10. SRS Configuration and Testing

**SRS Setup (External Dependency):**

**Option A: Docker (Recommended)**

```bash
docker run -d -p 1935:1935 -p 1985:1985 -p 8080:8080 \
  --name srs ossrs/srs:5
```

**Option B: Native Installation**

- Document SRS installation from source/package manager
- Configuration file for RTMP ingest and HLS output

**SRS Config (`srs.conf` example):**

```nginx
listen              1935;
max_connections     1000;
daemon              off;

http_server {
    enabled         on;
    listen          8080;
}

vhost __defaultVhost__ {
    hls {
        enabled     on;
        hls_path    ./objs/nginx/html;
        hls_fragment    6;
        hls_window      60;
    }
}
```

**Testing Playback:**

- RTMP: `rtmp://localhost/live/processed`
- HLS: `http://localhost:8080/live/processed.m3u8`

### 11. Main Application (`src/main.ts`)

```typescript
import { MultiProcessPipeline } from './MultiProcessPipeline.js';

const config = {
  sourceUrl: process.env.SOURCE_HLS_URL || 'https://test-streams.example.com/master.m3u8',
  srsRtmpUrl: process.env.SRS_RTMP_URL || 'rtmp://localhost/live/processed',
  sampleRate: 48000,
  channels: 2
};

const pipeline = new MultiProcessPipeline(
  config.sourceUrl,
  config.srsRtmpUrl,
  config.sampleRate,
  config.channels
);

// Graceful shutdown
process.on('SIGINT', async () => {
  console.log('\nShutting down pipeline...');
  await pipeline.stop();
  process.exit(0);
});

// Start pipeline
console.log('Starting multi-process audio pipeline...');
console.log(`Source: ${config.sourceUrl}`);
console.log(`Output: ${config.srsRtmpUrl}`);

await pipeline.start();
```

### 12. Test Client (`index.html`)

**Updated for SRS playback:**

```html
<!DOCTYPE html>
<html>
<head>
  <title>SRS Multi-Process Pipeline Test</title>
</head>
<body>
  <h1>Live Stream with Custom Audio Processing</h1>
  
  <h2>HLS Playback</h2>
  <video id="hls-video" controls width="800"></video>
  
  <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
  <script>
    // HLS player
    if (Hls.isSupported()) {
      const hls = new Hls();
      hls.loadSource('http://localhost:8080/live/processed.m3u8');
      hls.attachMedia(document.getElementById('hls-video'));
    } else if (document.getElementById('hls-video').canPlayType('application/vnd.apple.mpegurl')) {
      // Native HLS support (Safari)
      document.getElementById('hls-video').src = 'http://localhost:8080/live/processed.m3u8';
    }
  </script>
</body>
</html>
```

## File Structure

```
demo/streaming-demux-remux/
├── src/
│   ├── main.ts                          # Application entry point
│   ├── MultiProcessPipeline.ts          # Main orchestrator class
│   ├── processes/
│   │   ├── DemuxProcess.ts              # Process 1: Demultiplexer
│   │   ├── DecodeProcess.ts             # Process 2: Audio decoder
│   │   ├── EncodeProcess.ts             # Process 3: Audio encoder
│   │   └── RemuxProcess.ts              # Process 4: Remux + RTMP push
│   └── transforms/
│       └── AudioProcessor.ts            # Custom Node.js audio transform
├── index.html                           # Test player
├── package.json
├── tsconfig.json
├── .env.example
└── README.md                            # Setup instructions
```

## Key Architectural Decisions

**Multi-Process Benefits:**

- **Custom Processing:** Full control over raw PCM audio in Node.js
- **Modularity:** Each process handles one specific task
- **Flexibility:** Easy to swap audio transform implementation

**Multi-Process Challenges:**

- **Complexity:** Managing 4 child processes and their interconnections
- **Synchronization:** Timestamp preservation requires Nut format
- **Backpressure:** Must carefully manage stream flow control
- **Debugging:** Failures can occur in any of 4 processes

**SRS Integration Benefits:**

- **Multiple Protocols:** RTMP input, HLS/WebRTC output
- **Production Ready:** Battle-tested live streaming server
- **Clustering:** SRS supports edge/origin architecture for scale

## Testing Checklist

1. Start SRS server (Docker or native)
2. Run `npm run dev` to start pipeline
3. Verify RTMP push succeeds (check SRS logs)
4. Open `index.html` in browser
5. Confirm HLS player shows modified audio
6. Check Node.js console for FFmpeg stderr logs from all 4 processes
7. Test graceful shutdown with Ctrl+C

## Performance Notes

- **CPU Usage:** Higher than single-process due to PCM decode/encode
- **Latency:** Adds ~1-2 seconds vs single-process approach
- **Memory:** Each process maintains small buffers; monitor backpressure
- **Network:** RTMP push consumes upload bandwidth

## Requirements

- FFmpeg with AAC support (`ffmpeg -codecs | grep aac`)
- SRS server running and accessible
- Node.js 18+ (for native fetch API)
- Source HLS stream with H.264 video + AAC audio