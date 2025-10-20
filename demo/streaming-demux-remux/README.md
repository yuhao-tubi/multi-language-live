# Multi-Process HLS Audio Pipeline with SRS Integration

A high-performance Node.js/TypeScript application that performs real-time custom audio processing on HLS streams using a multi-process FFmpeg pipeline and pushes the output to SRS (Simple Realtime Server).

## Architecture

```
HLS Input → Demux → Decode → Node.js Audio Transform → Encode → Remux → RTMP → SRS
           (FFmpeg)  (FFmpeg)  (Custom PCM Processing)   (FFmpeg)  (FFmpeg)
```

### Pipeline Stages

1. **Demux Process**: Separates video and audio streams from HLS input
2. **Decode Process**: Decodes compressed audio to raw PCM for custom processing
3. **Node.js Transform**: Applies custom audio effects (echo, gain, etc.)
4. **Encode Process**: Re-encodes PCM back to AAC
5. **Remux Process**: Combines original video with processed audio and pushes to SRS via RTMP

### Key Features

- ✅ **Custom Audio Processing**: Full control over raw PCM audio in Node.js
- ✅ **Zero Video Re-encoding**: Video passes through untouched for maximum quality
- ✅ **SRS Integration**: Push to production-ready streaming server
- ✅ **Multi-Protocol Output**: RTMP, HLS via SRS
- ✅ **Timestamp Preservation**: Uses Nut format to maintain A/V sync
- ✅ **Graceful Shutdown**: Proper cleanup of all processes

## Requirements

### Software Dependencies

- **Node.js** 18+ (for native fetch API)
- **FFmpeg** with AAC support
- **SRS** (Simple Realtime Server) 5.0+

### Check FFmpeg Installation

```bash
# Check FFmpeg is installed
ffmpeg -version

# Verify AAC codec support
ffmpeg -codecs | grep aac
```

### Install FFmpeg (if needed)

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install ffmpeg
```

**Windows:**
Download from [ffmpeg.org](https://ffmpeg.org/download.html)

## SRS Setup

### Option 1: Docker (Recommended)

```bash
# Start SRS container
docker run -d \
  -p 1935:1935 \
  -p 1985:1985 \
  -p 8080:8080 \
  --name srs \
  ossrs/srs:5

# Check SRS logs
docker logs -f srs

# Stop SRS
docker stop srs
docker rm srs
```

### Option 2: Native Installation

**macOS (Homebrew):**
```bash
brew install srs
srs -c /usr/local/etc/srs/srs.conf
```

**Ubuntu/Debian:**
```bash
# Install dependencies
sudo apt-get install -y gcc make g++ patch unzip perl

# Download and build SRS
wget https://github.com/ossrs/srs/archive/v5.0-release.tar.gz
tar -xzf v5.0-release.tar.gz
cd srs-5.0-release/trunk
./configure
make
sudo make install

# Start SRS
./objs/srs -c conf/srs.conf
```

### SRS Configuration (Optional)

Create custom `srs.conf`:

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
    # HLS configuration
    hls {
        enabled     on;
        hls_path    ./objs/nginx/html;
        hls_fragment    6;
        hls_window      60;
    }
}
```

## Installation

```bash
# Navigate to project directory
cd demo/streaming-demux-remux

# Install dependencies
npm install

# Build TypeScript (optional for development)
npm run build
```

## Usage

### Quick Start

1. **Start the web server:**

```bash
# Development mode (auto-restart on code changes)
npm run dev

# OR Production mode
npm run build
npm start
```

The server will automatically find an available port (trying 3000 first, then 3001, 3002, etc.) and display:

```
🌐 Server running at: http://localhost:3000

📖 API Endpoints:
   POST http://localhost:3000/api/start
   POST http://localhost:3000/api/stop
   GET  http://localhost:3000/api/status

🎨 Web UI:
   Open http://localhost:3000/ in your browser
```

2. **Open the Web UI:**

Open `http://localhost:3000` in your browser (or whatever port was displayed).

3. **Configure and start the pipeline:**

- Enter your **Source HLS URL** (default: `https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8`)
- Enter your **SRS RTMP Output URL** (default: `rtmp://localhost/live/processed`)
- Click **"▶️ Start Pipeline"**

4. **Watch the output:**

After the pipeline starts (wait ~5-10 seconds), the HLS player on the same page will automatically connect to `http://localhost:8080/live/processed.m3u8` and begin playback.

5. **Stop the pipeline:**

Click **"⏹️ Stop Pipeline"** when done, or press `Ctrl+C` in the terminal to shut down the server.

### Test Streams

Some public HLS test streams you can use:

- Mux Test Stream: `https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8`
- Big Buck Bunny: `https://test-streams.mux.dev/x36xhzz/url_0/193039199_mp4_h264_aac_hd_7.m3u8`

### API Endpoints

The server provides REST API endpoints for programmatic control:

#### POST /api/start

Start the pipeline with custom configuration.

**Request Body:**
```json
{
  "sourceUrl": "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8",
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
    "sourceUrl": "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8",
    "srsRtmpUrl": "rtmp://localhost/live/processed",
    "sampleRate": 48000,
    "channels": 2
  }
}
```

#### POST /api/stop

Stop the running pipeline.

**Response (Success):**
```json
{
  "success": true,
  "message": "Pipeline stopped successfully"
}
```

#### GET /api/status

Get current pipeline status.

**Response:**
```json
{
  "isRunning": true,
  "config": {
    "sourceUrl": "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8",
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

### Using the API with curl

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

## Customizing Audio Processing

The custom audio transform is located in `src/transforms/AudioProcessor.ts`.

### Current Implementation

The default `CustomAudioTransform` class applies:
- **Gain boost**: 20% volume increase
- **Echo effect**: 500ms delay with 30% wet mix

### Adding Your Own Effects

Edit `src/transforms/AudioProcessor.ts`:

```typescript
_transform(chunk: Buffer, encoding: BufferEncoding, callback: TransformCallback): void {
  const samples = new Int16Array(chunk.buffer, chunk.byteOffset, chunk.length / 2);

  for (let i = 0; i < samples.length; i += this.channels) {
    for (let ch = 0; ch < this.channels; ch++) {
      let sample = samples[i + ch];
      
      // YOUR CUSTOM PROCESSING HERE
      // Examples:
      // - Apply ML model for noise reduction
      // - Implement custom reverb algorithm
      // - Real-time pitch detection
      // - Dynamic range compression
      
      samples[i + ch] = sample;
    }
  }

  this.push(Buffer.from(samples.buffer));
  callback();
}
```

### Alternative Transforms

The file includes alternative implementations:

- `PassthroughAudioTransform`: No processing (for testing)
- `VolumeControlTransform`: Simple volume adjustment

To use an alternative, edit `src/MultiProcessPipeline.ts`:

```typescript
// Replace this line:
this.audioTransform = new CustomAudioTransform(this.sampleRate, this.channels);

// With:
this.audioTransform = new VolumeControlTransform(this.sampleRate, this.channels, 1.5);
```

## Project Structure

```
demo/streaming-demux-remux/
├── src/
│   ├── main.ts                      # Application entry point
│   ├── MultiProcessPipeline.ts      # Main orchestrator class
│   ├── processes/
│   │   ├── DemuxProcess.ts          # FFmpeg demultiplexer
│   │   ├── DecodeProcess.ts         # FFmpeg audio decoder
│   │   ├── EncodeProcess.ts         # FFmpeg audio encoder
│   │   └── RemuxProcess.ts          # FFmpeg remuxer + RTMP push
│   └── transforms/
│       └── AudioProcessor.ts        # Custom Node.js audio processing
├── index.html                       # Test player with HLS.js
├── package.json
├── tsconfig.json
├── .env.example
└── README.md
```

## Troubleshooting

### Pipeline fails to start

1. **Check FFmpeg**: `ffmpeg -version`
2. **Check SRS is running**: `curl http://localhost:8080/api/v1/versions`
3. **Verify source URL**: Try accessing the HLS URL in a browser
4. **Check logs**: All FFmpeg processes log to console with `[DEMUX]`, `[DECODE]`, `[ENCODE]`, `[REMUX]` prefixes

### Audio/Video out of sync

- The pipeline uses Nut format to preserve timestamps
- If sync issues persist, try adding `-fflags +genpts` to the encode process
- Check FFmpeg logs for "Non-monotonous DTS" warnings

### SRS connection fails

```bash
# Verify SRS is listening on RTMP port
netstat -an | grep 1935

# Test RTMP connection
ffmpeg -re -i test.mp4 -c copy rtmp://localhost/live/test
```

### Video player shows "404 Not Found"

- Wait 10-15 seconds after starting the pipeline for SRS to generate HLS segments
- Check SRS logs for incoming RTMP connection
- Verify SRS HTTP server is running: `curl http://localhost:8080`

### High CPU usage

This is expected with multi-process architecture:
- **Decode**: CPU-intensive (AAC → PCM)
- **Encode**: CPU-intensive (PCM → AAC)
- **Video passthrough**: Minimal CPU (stream copy)

To reduce CPU:
- Lower audio bitrate in `EncodeProcess.ts` (`-b:a 96k` instead of `128k`)
- Reduce sample rate to 44100 Hz
- Use mono audio (`AUDIO_CHANNELS=1`)

## Performance Notes

- **Latency**: Adds ~1-2 seconds vs single-process approach
- **CPU Usage**: Higher due to PCM decode/encode cycles
- **Memory**: Each process maintains small buffers (~1-2 MB per process)
- **Network**: RTMP push consumes upload bandwidth (depends on bitrate)

## Development

### Run in Development Mode

```bash
npm run dev
```

This uses `nodemon` to auto-restart on file changes.

### Build for Production

```bash
npm run build
npm start
```

### Type Checking

```bash
npm run check
```

Runs TypeScript compiler in check-only mode to verify types without generating output.

## License

ISC

## Contributing

This is a demonstration project. Feel free to fork and customize for your needs.

## References

- [FFmpeg Documentation](https://ffmpeg.org/documentation.html)
- [SRS Documentation](https://ossrs.io/lts/en-us/docs/v5/doc/introduction)
- [m3u8stream](https://github.com/fent/node-m3u8stream)
- [Node.js Streams](https://nodejs.org/api/stream.html)

