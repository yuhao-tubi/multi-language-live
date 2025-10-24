# Multi-Language Live Streaming - Architecture Overview

**Last Updated:** October 22, 2025  
**Status:** Production Ready  
**Project:** Multi-Process HLS Audio Manipulation Pipeline

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [System Architecture](#system-architecture)
3. [Process Flow](#process-flow)
4. [Component Details](#component-details)
5. [Data Flow and Stream Management](#data-flow-and-stream-management)
6. [Technical Implementation](#technical-implementation)
7. [API and Control Interface](#api-and-control-interface)
8. [Configuration and Deployment](#configuration-and-deployment)
9. [Performance and Scalability](#performance-and-scalability)
10. [Future Roadmap](#future-roadmap)
11. [Related Projects](#related-projects)

---

## Executive Summary

This monorepo contains a production-ready real-time audio processing system for HLS (HTTP Live Streaming) content. The system implements a **multi-process pipeline architecture** that enables custom audio manipulation in Node.js while streaming video with zero quality loss.

### Key Capabilities

- **Real-time HLS stream processing** with custom audio effects
- **Multi-process FFmpeg pipeline** for modular audio manipulation
- **Zero video re-encoding** - video streams pass through untouched
- **Custom DSP in Node.js** - Full control over raw PCM audio buffers
- **SRS integration** - Push to production streaming server (RTMP/HLS output)
- **Web-based control** - REST API and interactive UI for pipeline management
- **Production-grade reliability** - Graceful shutdown, error cascading, backpressure handling

### Technology Stack

- **Runtime:** Node.js 18+ (TypeScript/ES2022)
- **Media Processing:** FFmpeg (4+ child processes)
- **Streaming Server:** SRS (Simple Realtime Server) 5.0+
- **Web Framework:** Express.js
- **Build System:** Nx monorepo with TypeScript compilation
- **Container Format:** Nut (for timestamp preservation between processes)

---

## System Architecture

### High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         HLS Source Stream                            │
│                  (HTTP Live Streaming - M3U8 + TS)                   │
└────────────────────────────┬────────────────────────────────────────┘
                             │ m3u8stream (Node.js)
                             ↓
┌─────────────────────────────────────────────────────────────────────┐
│                      Process 1: DEMUX (FFmpeg)                       │
│  Separates video and audio into independent streams                 │
│  Output: Nut format (preserves timestamps)                          │
└──────────────┬──────────────────────────────────┬───────────────────┘
               │                                  │
        Video (H.264)                      Audio (AAC/MP3)
               │                                  │
               │                                  ↓
               │                    ┌─────────────────────────────────┐
               │                    │ Process 2: DECODE (FFmpeg)      │
               │                    │ Decompress audio to raw PCM     │
               │                    │ Output: s16le PCM stream        │
               │                    └────────────┬────────────────────┘
               │                                 │
               │                                 ↓
               │                    ┌─────────────────────────────────┐
               │                    │  Node.js Transform Stream       │
               │                    │  Custom Audio Processing        │
               │                    │  • Echo effects                 │
               │                    │  • Gain control                 │
               │                    │  • Custom DSP algorithms        │
               │                    │  • ML model inference           │
               │                    └────────────┬────────────────────┘
               │                                 │
               │                                 ↓
               │                    ┌─────────────────────────────────┐
               │                    │ Process 3: ENCODE (FFmpeg)      │
               │                    │ Re-encode PCM to AAC            │
               │                    │ Output: AAC in Nut format       │
               │                    └────────────┬────────────────────┘
               │                                 │
               └─────────────────────────────────┘
                             │
                             ↓
               ┌─────────────────────────────────┐
               │  Process 4: REMUX (FFmpeg)      │
               │  Combine video + processed audio │
               │  Push to SRS via RTMP           │
               └────────────┬────────────────────┘
                            │
                            ↓
               ┌─────────────────────────────────┐
               │   SRS (Streaming Server)        │
               │   • RTMP ingestion              │
               │   • HLS output generation       │
               │   • Multi-protocol support      │
               └─────────────────────────────────┘
```

### Monorepo Structure

```
multi-language-live/
├── apps/
│   └── streaming-demux-remux/          # Main application
│       ├── src/
│       │   ├── main.ts                 # Express server & API
│       │   ├── MultiProcessPipeline.ts # Orchestrator
│       │   ├── processes/              # FFmpeg process wrappers
│       │   │   ├── DemuxProcess.ts     # Process 1
│       │   │   ├── DecodeProcess.ts    # Process 2
│       │   │   ├── EncodeProcess.ts    # Process 3
│       │   │   └── RemuxProcess.ts     # Process 4
│       │   └── transforms/
│       │       └── AudioProcessor.ts   # Custom audio effects
│       ├── index.html                  # Web UI
│       ├── package.json
│       └── tsconfig.json
├── docs/
│   └── ARCHITECTURE.md                 # This document
├── nx.json                             # Nx configuration
├── tsconfig.base.json                  # Base TypeScript config
└── package.json                        # Root package.json
```

---

## Process Flow

### Detailed Pipeline Flow

#### 1. **HLS Ingestion**

```typescript
// Fetch M3U8 manifest
const manifestResponse = await fetch(this.sourceUrl);
const manifestText = await manifestResponse.text();

// Parse manifest to extract variant playlists
const parser = new M3U8Parser.Parser();
parser.push(manifestText);
parser.end();

// Select variant (quality selection logic can be customized)
const selectedVariant = manifest.playlists[0];
const mediaPlaylistUrl = this._resolveUrl(this.sourceUrl, selectedVariant.uri);

// Create segment stream
this.inputStream = m3u8stream(mediaPlaylistUrl, {
  chunkReadahead: 3  // Prefetch 3 segments
});
```

**Key Points:**
- Handles both master playlists and media playlists
- Automatic segment fetching and concatenation
- Built-in retry logic for network failures

#### 2. **Process 1: Demultiplexing**

**Purpose:** Split incoming HLS stream into separate video and audio tracks

**FFmpeg Command:**
```bash
ffmpeg -i pipe:0 \
  -map 0:v -c:v copy -f nut pipe:3 \  # Video → fd 3
  -map 0:a -c:a copy -f nut pipe:4    # Audio → fd 4
```

**Key Technical Details:**
- Uses **Nut container format** to preserve PTS/DTS timestamps
- Video codec is **copied** (no re-encoding, zero quality loss)
- Audio remains compressed at this stage
- Outputs to **file descriptors 3 and 4** for parallel processing

**Implementation:**
```typescript
const ffmpegProcess = spawn('ffmpeg', args, {
  stdio: ['pipe', 'pipe', 'pipe', 'pipe', 'pipe']
  //      stdin   stdout stderr  video   audio
});

inputStream.pipe(ffmpegProcess.stdin);
const videoOut = ffmpegProcess.stdio[3] as Readable;
const audioOut = ffmpegProcess.stdio[4] as Readable;
```

#### 3. **Process 2: Audio Decoding**

**Purpose:** Decompress audio to raw PCM for custom processing

**FFmpeg Command:**
```bash
ffmpeg -f nut -i pipe:0 \
  -vn \
  -f s16le -acodec pcm_s16le \
  -ar 48000 -ac 2 \
  pipe:1
```

**PCM Format Specification:**
- **Format:** s16le (signed 16-bit little-endian)
- **Sample Rate:** 48000 Hz (configurable)
- **Channels:** 2 (stereo, configurable)
- **Byte Order:** Little-endian
- **Interleaving:** LRLRLR... (left/right alternating)

**Output Characteristics:**
- **No container headers** - pure audio samples
- **2 bytes per sample** (16-bit)
- **Frame size:** 4 bytes per stereo frame (2 channels × 2 bytes)
- **Bitrate:** 48000 Hz × 2 channels × 16 bits = 1,536 kbps

#### 4. **Node.js Audio Transform**

**Purpose:** Apply custom DSP effects that aren't available in FFmpeg

**Current Implementation:**
```typescript
class CustomAudioTransform extends Transform {
  _transform(chunk: Buffer, encoding: BufferEncoding, callback: TransformCallback) {
    // Convert to typed array
    const samples = new Int16Array(chunk.buffer, chunk.byteOffset, chunk.length / 2);
    
    // Process each stereo frame
    for (let i = 0; i < samples.length; i += this.channels) {
      for (let ch = 0; ch < this.channels; ch++) {
        let sample = samples[i + ch];
        
        // 1. Gain boost (20%)
        sample = Math.floor(sample * 1.2);
        
        // 2. Echo effect (500ms delay, 30% wet mix)
        const echoIdx = (this.echoWritePos * this.channels + ch) % this.echoBuffer.length;
        const echoSample = this.echoBuffer[echoIdx];
        sample = Math.floor(sample * 0.6 + echoSample * 0.3);
        
        // 3. Clamp to valid range
        sample = Math.min(32767, Math.max(-32768, sample));
        
        // Store in ring buffer for next echo
        this.echoBuffer[echoIdx] = sample;
        samples[i + ch] = sample;
      }
      this.echoWritePos = (this.echoWritePos + 1) % this.echoDelay;
    }
    
    this.push(Buffer.from(samples.buffer, samples.byteOffset, samples.byteLength));
    callback();
  }
}
```

**Extensibility Examples:**
- Machine learning model inference (TensorFlow.js, ONNX Runtime)
- Custom vocoder/pitch shifting algorithms
- Real-time speech-to-text or music analysis
- Dynamic EQ based on frequency analysis
- Noise reduction using custom algorithms
- Multi-band compression
- Spatial audio processing

#### 5. **Process 3: Audio Re-encoding**

**Purpose:** Compress processed PCM back to AAC for streaming

**FFmpeg Command:**
```bash
ffmpeg -f s16le -ar 48000 -ac 2 -i pipe:0 \
  -c:a aac -b:a 128k \
  -f nut pipe:1
```

**Encoding Parameters:**
- **Codec:** AAC-LC (widely supported)
- **Bitrate:** 128 kbps (configurable)
- **Output:** Nut container to preserve timestamps from decode stage

**Timestamp Handling:**
- Nut format maintains PTS continuity
- Optional `-fflags +genpts` for timestamp regeneration if needed
- Critical for A/V synchronization in final output

#### 6. **Process 4: Remuxing and RTMP Push**

**Purpose:** Combine original video with processed audio, push to SRS

**FFmpeg Command:**
```bash
ffmpeg -f nut -i pipe:3 \         # Video input (fd 3)
       -f nut -i pipe:4 \         # Audio input (fd 4)
       -map 0:v -c:v copy \       # Copy video stream
       -map 1:a -c:a copy \       # Copy audio stream
       -f flv rtmp://localhost/live/processed
```

**Key Features:**
- **FLV container** for RTMP compatibility
- Both streams are copied (no re-encoding)
- RTMP push happens in real-time (not faster-than-realtime)
- Automatic connection retry on SRS restart (via FFmpeg)

---

## Component Details

### MultiProcessPipeline Class

**Location:** `apps/streaming-demux-remux/src/MultiProcessPipeline.ts`

**Responsibilities:**
- HLS manifest parsing and variant selection
- Process lifecycle management (spawn, monitor, cleanup)
- Stream interconnection and error propagation
- Graceful shutdown orchestration

**Key Methods:**

#### `async start(): Promise<void>`
1. Fetches and parses HLS manifest
2. Creates m3u8stream for segment streaming
3. Spawns 4 FFmpeg processes in sequence
4. Connects streams via pipes
5. Sets up error handlers and monitoring
6. Marks pipeline as running

#### `async stop(): Promise<void>`
1. Sends SIGTERM to processes in reverse order (remux → encode → decode → demux)
2. Waits 500ms for graceful shutdown
3. Force kills with SIGKILL if processes don't exit
4. Cleans up stream references
5. Marks pipeline as stopped

#### `getStatus(): StatusObject`
Returns current state of pipeline and all processes

#### `getConfig(): ConfigObject`
Returns current configuration (URLs, sample rate, channels)

### Process Wrapper Functions

Each process has a dedicated wrapper function that:
- Constructs FFmpeg command arguments
- Configures stdio pipes (including extra file descriptors)
- Spawns the child process
- Monitors stderr for FFmpeg logs
- Returns process handle and output streams

**Common Pattern:**
```typescript
export function createXxxProcess(...params): { process: ChildProcess, ...streams } {
  const args = [ /* FFmpeg arguments */ ];
  const ffmpegProcess = spawn('ffmpeg', args, { stdio: [...] });
  
  // Pipe connections
  inputStream.pipe(ffmpegProcess.stdin);
  
  // Monitoring
  ffmpegProcess.stderr.on('data', (data) => {
    console.log(`[PROCESS_NAME]: ${data.toString()}`);
  });
  
  return { process: ffmpegProcess, ...outputStreams };
}
```

### Audio Transform Implementations

**Base Class:** `Transform` (from Node.js `stream` module)

**Available Transforms:**

1. **CustomAudioTransform** (Default)
   - Echo effect with 500ms delay
   - 20% gain boost
   - Ring buffer for delay implementation

2. **PassthroughAudioTransform** (Testing)
   - No processing
   - Used for baseline comparison

3. **VolumeControlTransform** (Simple)
   - Configurable gain multiplier
   - No latency added

**Switching Transforms:**
Edit `MultiProcessPipeline.ts` line 119:
```typescript
this.audioTransform = new VolumeControlTransform(this.sampleRate, this.channels, 1.5);
```

---

## Data Flow and Stream Management

### Stream Types

1. **HLS Segment Stream** (Readable)
   - Source: m3u8stream library
   - Format: MPEG-TS segments concatenated
   - Flows into: Demux stdin

2. **Video Stream** (Readable)
   - Source: Demux fd 3
   - Format: Nut container with H.264
   - Flows into: Remux fd 3

3. **Compressed Audio Stream** (Readable)
   - Source: Demux fd 4
   - Format: Nut container with AAC/MP3
   - Flows into: Decode stdin

4. **PCM Audio Stream** (Readable)
   - Source: Decode stdout
   - Format: Raw s16le PCM
   - Flows into: Audio transform

5. **Processed PCM Stream** (Readable)
   - Source: Audio transform output
   - Format: Raw s16le PCM
   - Flows into: Encode stdin

6. **Encoded Audio Stream** (Readable)
   - Source: Encode stdout
   - Format: Nut container with AAC
   - Flows into: Remux fd 4

### Backpressure Management

**Critical for Stability:**
- All streams use `.pipe()` which automatically handles backpressure
- When downstream buffer is full, upstream pauses
- Prevents memory overflow from fast producers

**Monitoring:**
```typescript
stream.on('drain', () => {
  console.log('Stream buffer drained, resuming...');
});

stream.on('pause', () => {
  console.log('Stream paused due to backpressure');
});
```

### Error Propagation

**Cascading Shutdown Strategy:**
1. Any process exit with non-zero code triggers pipeline stop
2. Stream errors trigger pipeline stop
3. Pipeline stop sends SIGTERM to all processes
4. After 500ms timeout, SIGKILL is sent
5. All event listeners are removed

**Implementation:**
```typescript
proc.on('exit', (code, signal) => {
  if (code !== 0 && code !== null) {
    console.error(`Process exited unexpectedly: code=${code}`);
    this.stop().catch(err => console.error('Emergency shutdown failed:', err));
  }
});

stream.on('error', (err) => {
  console.error('Stream error:', err);
  this.stop().catch(err => console.error('Emergency shutdown failed:', err));
});
```

---

## Technical Implementation

### Timestamp Preservation

**Challenge:** PCM decode/encode cycle loses container metadata

**Solution:** Nut container format
- Nut stores PTS/DTS timestamps
- Decode process reads Nut input, extracts timestamps
- Encode process writes Nut output, generates timestamps based on sample count
- Optional `-fflags +genpts` for timestamp regeneration

**Verification:**
```bash
# Check for timestamp warnings in FFmpeg logs
grep "Non-monotonous DTS" ffmpeg_log.txt
grep "PTS < DTS" ffmpeg_log.txt
```

### File Descriptor Management

**Standard I/O:**
- fd 0: stdin
- fd 1: stdout
- fd 2: stderr

**Custom File Descriptors:**
- fd 3: Video output (demux) / Video input (remux)
- fd 4: Audio output (demux) / Audio input (remux)

**Node.js Configuration:**
```typescript
spawn('ffmpeg', args, {
  stdio: [
    'pipe',  // fd 0 - stdin
    'pipe',  // fd 1 - stdout
    'pipe',  // fd 2 - stderr
    'pipe',  // fd 3 - custom video pipe
    'pipe'   // fd 4 - custom audio pipe
  ]
});

// Access custom pipes
const videoStream = process.stdio[3] as Readable;
const audioStream = process.stdio[4] as Readable;
```

### PCM Buffer Processing

**Reading Samples:**
```typescript
const samples = new Int16Array(chunk.buffer, chunk.byteOffset, chunk.length / 2);
```

**Frame-by-Frame Processing:**
```typescript
for (let i = 0; i < samples.length; i += channels) {
  const leftChannel = samples[i];
  const rightChannel = samples[i + 1];
  
  // Process...
  
  samples[i] = processedLeft;
  samples[i + 1] = processedRight;
}
```

**Clamping to Valid Range:**
```typescript
sample = Math.min(32767, Math.max(-32768, sample));
```

### Ring Buffer for Echo Effect

**Initialization:**
```typescript
this.echoDelay = Math.floor(sampleRate * 0.5); // 500ms
this.echoBuffer = new Int16Array(this.echoDelay * channels);
this.echoWritePos = 0;
```

**Read/Write:**
```typescript
const echoIdx = (this.echoWritePos * this.channels + ch) % this.echoBuffer.length;
const echoSample = this.echoBuffer[echoIdx];  // Read delayed sample
this.echoBuffer[echoIdx] = currentSample;     // Write current sample
this.echoWritePos = (this.echoWritePos + 1) % this.echoDelay;
```

---

## API and Control Interface

### REST API Endpoints

#### POST `/api/start`

Start the pipeline with configuration.

**Request:**
```json
{
  "sourceUrl": "https://example.com/stream.m3u8",
  "srsRtmpUrl": "rtmp://localhost/live/processed",
  "sampleRate": 48000,
  "channels": 2
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Pipeline started successfully",
  "config": {
    "sourceUrl": "https://example.com/stream.m3u8",
    "srsRtmpUrl": "rtmp://localhost/live/processed",
    "sampleRate": 48000,
    "channels": 2
  }
}
```

**Response (Error):**
```json
{
  "success": false,
  "error": "Pipeline is already running. Stop it first."
}
```

#### POST `/api/stop`

Stop the running pipeline.

**Response:**
```json
{
  "success": true,
  "message": "Pipeline stopped successfully"
}
```

#### GET `/api/status`

Get current pipeline status.

**Response:**
```json
{
  "isRunning": true,
  "config": {
    "sourceUrl": "https://example.com/stream.m3u8",
    "srsRtmpUrl": "rtmp://localhost/live/processed",
    "sampleRate": 48000,
    "channels": 2
  },
  "processes": {
    "demux": true,
    "decode": true,
    "encode": true,
    "remux": true
  }
}
```

### Web UI

**Location:** `apps/streaming-demux-remux/index.html`

**Features:**
- URL input forms for source and output
- Start/Stop buttons with state management
- Real-time status display (updates every 2 seconds)
- Integrated HLS.js player for output preview
- Responsive design

**Usage:**
1. Navigate to `http://localhost:3000`
2. Enter source HLS URL (or use default test stream)
3. Enter SRS RTMP URL (default: `rtmp://localhost/live/processed`)
4. Click "Start Pipeline"
5. Wait 5-10 seconds for SRS to generate HLS segments
6. Player automatically loads `http://localhost:8080/live/processed.m3u8`

### Command-Line Interface (Alternative)

While the web UI is recommended, you can also use curl:

```bash
# Start pipeline
curl -X POST http://localhost:3000/api/start \
  -H "Content-Type: application/json" \
  -d '{
    "sourceUrl": "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8",
    "srsRtmpUrl": "rtmp://localhost/live/processed"
  }'

# Check status
curl http://localhost:3000/api/status

# Stop pipeline
curl -X POST http://localhost:3000/api/stop
```

---

## Configuration and Deployment

### Prerequisites

1. **Node.js 18+**
   ```bash
   node --version  # Should be 18.0.0 or higher
   ```

2. **FFmpeg with AAC support**
   ```bash
   ffmpeg -version
   ffmpeg -codecs | grep aac
   ```

3. **SRS (Docker or native)**
   ```bash
   docker run -d -p 1935:1935 -p 8080:8080 --name srs ossrs/srs:5
   ```

### Installation

```bash
# Clone repository
git clone https://github.com/yourorg/multi-language-live.git
cd multi-language-live

# Install root dependencies
npm install

# Install app dependencies
cd apps/streaming-demux-remux
npm install

# Build TypeScript
npm run build
```

### Running the Application

**Development Mode (with hot reload):**
```bash
npm run dev
```

**Production Mode:**
```bash
npm run build
npm start
```

**Using Nx:**
```bash
# From monorepo root
nx dev streaming-demux-remux
nx build streaming-demux-remux
nx start streaming-demux-remux
```

### Environment Variables (Optional)

Create `.env` file in `apps/streaming-demux-remux/`:

```bash
# Server configuration
PORT=3000

# Default URLs (can be overridden via API)
DEFAULT_SOURCE_URL=https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8
DEFAULT_SRS_RTMP_URL=rtmp://localhost/live/processed

# Audio configuration
DEFAULT_SAMPLE_RATE=48000
DEFAULT_CHANNELS=2
```

### SRS Configuration

**Basic `srs.conf` (if using native SRS):**
```nginx
listen              1935;
max_connections     1000;
daemon              off;

http_server {
    enabled         on;
    listen          8080;
    dir             ./objs/nginx/html;
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

**Docker (recommended):**
```bash
docker run -d \
  -p 1935:1935 \
  -p 8080:8080 \
  --name srs \
  --restart unless-stopped \
  ossrs/srs:5
```

### NPM Scripts Reference

**Root Level (`package.json`):**
```json
{
  "scripts": {
    "build": "nx build streaming-demux-remux",
    "dev": "nx dev streaming-demux-remux",
    "start": "nx start streaming-demux-remux"
  }
}
```

**App Level (`apps/streaming-demux-remux/package.json`):**
```json
{
  "scripts": {
    "build": "tsc",
    "start": "node dist/main.js",
    "dev": "nodemon --exec ts-node src/main.ts",
    "check": "tsc --noEmit",
    "verify": "scripts/verify-setup.sh",
    "srs:start": "scripts/start-srs.sh",
    "srs:stop": "scripts/stop-srs.sh",
    "srs:restart": "scripts/restart-srs.sh",
    "srs:logs": "scripts/logs-srs.sh",
    "srs:remove": "scripts/remove-srs.sh"
  }
}
```

---

## Performance and Scalability

### Resource Usage

**CPU:**
- **Decode:** 15-30% of one core (AAC → PCM)
- **Encode:** 20-40% of one core (PCM → AAC)
- **Demux/Remux:** 5-10% of one core (stream copy)
- **Node.js Transform:** 5-15% (depends on algorithm complexity)
- **Total:** ~50-100% of one core for 1080p stream

**Memory:**
- **Each Process:** 10-30 MB
- **Node.js Buffers:** 5-10 MB
- **Total:** ~100-150 MB per pipeline instance

**Network:**
- **Input:** Depends on source bitrate (typically 2-10 Mbps)
- **Output:** Similar to input (128 kbps audio + copied video)
- **Latency Added:** 1-2 seconds (due to multi-process pipeline)

### Optimization Strategies

**Reduce CPU Usage:**
1. Lower audio bitrate: `-b:a 96k` instead of `128k`
2. Reduce sample rate: `44100 Hz` instead of `48000 Hz`
3. Use mono audio: `channels: 1`
4. Simplify audio transform (remove echo, use only gain)

**Reduce Latency:**
1. Decrease HLS segment size (SRS configuration)
2. Reduce `chunkReadahead` in m3u8stream
3. Use `-tune zerolatency` in remux process
4. Consider replacing HLS input with RTMP/SRT

**Scale to Multiple Streams:**
1. Run multiple pipeline instances (different ports)
2. Use process manager (PM2, systemd)
3. Implement load balancer for API requests
4. Consider containerization (Docker/Kubernetes)

### Monitoring and Logging

**Current Logging:**
- All FFmpeg stderr is logged with process name prefix
- Pipeline lifecycle events (start/stop/errors)
- API requests and responses

**Recommended Additions:**
- Metrics collection (Prometheus/Grafana)
- CPU/memory monitoring per process
- Stream bitrate and latency tracking
- Error rate tracking and alerting

**Example Prometheus Metrics:**
```typescript
pipelineUptime.inc();
processExitCounter.labels({ process: 'demux' }).inc();
audioLatencyHistogram.observe(latencyMs);
```

### Production Deployment Checklist

- [ ] Use process manager (PM2 with cluster mode)
- [ ] Implement health check endpoint (`/health`)
- [ ] Add request rate limiting
- [ ] Enable CORS if needed for web UI
- [ ] Use reverse proxy (nginx) for SSL/TLS
- [ ] Set up log rotation
- [ ] Configure automatic restarts on failure
- [ ] Monitor disk space (SRS HLS segments)
- [ ] Implement authentication for API endpoints
- [ ] Set up alerting (PagerDuty, Slack, etc.)

---

## Future Roadmap

### Short-Term Enhancements (Next 3 months)

1. **Multiple Audio Effects**
   - Effect selection via API parameter
   - Real-time effect switching without restart
   - Effect chaining (multiple transforms in sequence)

2. **Adaptive Quality Selection**
   - Automatic variant selection based on bandwidth
   - ABR (Adaptive Bitrate) support
   - Quality degradation fallback

3. **Enhanced Monitoring**
   - Real-time latency metrics
   - Bitrate graphs in web UI
   - Process health dashboard

4. **Additional Input/Output Formats**
   - RTMP input support (alternative to HLS)
   - WebRTC output (ultra-low latency)
   - SRT input/output

### Medium-Term Goals (3-6 months)

1. **Machine Learning Integration**
   - TensorFlow.js for audio enhancement
   - Real-time speech recognition
   - Voice isolation/removal
   - Background music detection

2. **Multi-Language Audio Support**
   - Multiple audio track processing
   - Language detection
   - Real-time translation integration
   - Audio track switching

3. **Advanced DSP Features**
   - FFT-based frequency analysis
   - Multi-band EQ with UI controls
   - Dynamic range compression
   - Noise gate and de-esser

4. **Distributed Processing**
   - Split processes across multiple machines
   - Shared storage for inter-process communication
   - Load balancing for multiple pipelines

### Long-Term Vision (6-12 months)

1. **Cloud-Native Architecture**
   - Kubernetes deployment manifests
   - Auto-scaling based on load
   - Multi-region support
   - CDN integration for outputs

2. **Plugin System**
   - Third-party audio effect plugins
   - WebAssembly-based effects
   - Effect marketplace

3. **Advanced Features**
   - Multi-stream mixing (combine multiple inputs)
   - Picture-in-picture video processing
   - Closed caption processing
   - Time-shifting and DVR capabilities

4. **Enterprise Features**
   - Multi-tenancy support
   - User management and authentication
   - Billing and usage tracking
   - SLA monitoring and guarantees

---

## Appendix

### Troubleshooting Guide

**Problem:** Pipeline fails to start

**Solutions:**
- Check FFmpeg installation: `ffmpeg -version`
- Verify SRS is running: `curl http://localhost:8080`
- Check source URL is accessible: `curl -I <source_url>`
- Review logs for specific error messages

**Problem:** Audio/Video out of sync

**Solutions:**
- Verify Nut format is being used in all inter-process pipes
- Add `-fflags +genpts` to encode process
- Check for "Non-monotonous DTS" warnings in logs
- Ensure timestamp preservation in audio transform

**Problem:** High CPU usage

**Solutions:**
- Verify video is being copied (not re-encoded)
- Simplify audio transform algorithm
- Lower audio bitrate and sample rate
- Check for infinite loops in audio processing

**Problem:** Memory leak

**Solutions:**
- Ensure all streams are properly piped (backpressure handling)
- Check for unreleased event listeners
- Verify graceful shutdown cleans up all resources
- Monitor with `process.memoryUsage()` and heap snapshots

### References

- [FFmpeg Documentation](https://ffmpeg.org/documentation.html)
- [SRS Documentation](https://ossrs.io/lts/en-us/docs/v5/doc/introduction)
- [Node.js Streams](https://nodejs.org/api/stream.html)
- [Nut Container Format](https://www.ffmpeg.org/ffmpeg-formats.html#nut)
- [HLS Specification](https://tools.ietf.org/html/rfc8216)
- [RTMP Specification](https://rtmp.veriskope.com/docs/spec/)

### Contributing

See monorepo root `README.md` for contribution guidelines.

### License

ISC

---

---

## Related Projects

### Live Media Processor Service

For production-grade live HLS processing with external audio processing integration, see **[MEDIA_SERVICE_ARCHITECTURE.md](./MEDIA_SERVICE_ARCHITECTURE.md)**.

This new service extends the concepts from this project by adding:
- **Disk-based storage** for TS segments and processed fragments
- **Batch processing** with configurable 30-second buffers
- **External audio processor integration** via WebSocket (Socket.IO)
- **Production features** including storage management, comprehensive logging, and web-based monitoring
- **Test-driven development** with Vitest framework

**Key Differences:**

| Feature | streaming-demux-remux (This) | Live Media Processor (New) |
|---------|------------------------------|----------------------------|
| Processing Mode | Real-time in-memory | Batch processing on disk |
| Audio Processing | Internal Node.js transforms | External service via WebSocket |
| Storage | None (streaming only) | Disk-based with retention policies |
| Buffer Strategy | Continuous streaming | 30s batches |
| Container Format | Nut (for streaming) | FMP4 (for fragments) |
| Use Case | Low-latency audio effects | Production multi-language processing |

---

**Document Version:** 1.0  
**Last Updated:** October 22, 2025  
**Maintained By:** Development Team

