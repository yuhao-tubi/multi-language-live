# Live Media Service

A production-ready Node.js service for processing live HLS streams with real-time audio manipulation. Fetches HLS segments, demuxes audio/video, sends audio to external processors, and republishes to SRS.

## 🎯 Features

- ✅ **HLS Stream Ingestion** - Fetch and buffer live HLS streams
- ✅ **Intelligent Buffering** - Accumulate segments into 30-second batches
- ✅ **FFmpeg Integration** - Demux/remux with zero video re-encoding
- ✅ **WebSocket Communication** - Real-time audio processing via Socket.IO
- ✅ **SRS Publishing** - RTMP output to Simple Realtime Server
- ✅ **REST API** - Full control via HTTP endpoints
- ✅ **Web UI** - Beautiful monitoring dashboard
- ✅ **Test-Driven** - Comprehensive unit tests with Vitest
- ✅ **Production-Ready** - Logging, error handling, graceful shutdown

## 🚀 Quick Start

### Prerequisites

- Node.js 20+ (LTS)
- FFmpeg 4.0+
- Docker (for SRS)

### Installation

```bash
# Install dependencies
npm install

# Copy environment configuration
cp .env.example .env

# Edit .env with your settings
nano .env
```

### Start SRS Server

```bash
# Start SRS in Docker
./scripts/start-srs.sh

# Verify SRS is running
curl http://localhost:1985/api/v1/versions
```

### Start Echo Audio Processor (for testing)

```bash
# In a new terminal
cd ../echo-audio-processor
npm install
npm run dev
```

### Start Live Media Service

```bash
# Development mode
npm run dev

# Production mode
npm run build
npm start
```

### Access Web UI

Open http://localhost:3000 in your browser.

## 📋 Architecture

### System Overview

```
┌─────────────────────┐
│   HLS Source        │  (Input)
└──────────┬──────────┘
           │
           ↓
┌─────────────────────┐
│  StreamFetcher      │  Fetch segments, buffer 30s
└──────────┬──────────┘
           │ batch:ready
           ↓
┌─────────────────────┐
│  AudioProcessor     │  Demux → video.fmp4 + audio.fmp4
└──────────┬──────────┘
           │ audio:sent
           ↓
┌─────────────────────┐
│  External Processor │  Process audio (translation, etc.)
└──────────┬──────────┘
           │ audio:processed
           ↓
┌─────────────────────┐
│  Remuxer            │  Combine video + processed audio
└──────────┬──────────┘
           │ remux:complete
           ↓
┌─────────────────────┐
│  StreamPublisher    │  Publish to SRS via RTMP
└──────────┬──────────┘
           │
           ↓
┌─────────────────────┐
│  SRS Server         │  Output HLS/FLV/RTMP
└─────────────────────┘
```

### Core Modules

#### 1. StreamFetcher
- Fetches HLS manifest (M3U8)
- Downloads TS segments
- Buffers segments until 30s threshold
- Emits `batch:ready` events

#### 2. AudioProcessor
- Concatenates TS segments
- Demuxes with FFmpeg: TS → video.fmp4 + audio.fmp4
- Sends audio via WebSocket to external processor
- Receives processed audio back

#### 3. Remuxer
- Combines video + processed audio
- Outputs FMP4 with both streams
- Maintains A/V sync

#### 4. StreamPublisher
- Continuous RTMP streaming to SRS
- FFmpeg concat demuxer for seamless playback
- Handles reconnection and errors

#### 5. PipelineOrchestrator
- Coordinates all modules
- Event-driven architecture
- Error handling and recovery
- Status reporting

## 🔌 API Reference

### Start Pipeline

```bash
POST /api/pipeline/start
Content-Type: application/json

{
  "sourceUrl": "https://example.com/stream.m3u8",
  "streamId": "my-stream",
  "bufferDuration": 30,
  "audioProcessorUrl": "http://localhost:5000"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Pipeline started successfully",
  "status": { ... }
}
```

### Stop Pipeline

```bash
POST /api/pipeline/stop
```

### Get Status

```bash
GET /api/pipeline/status
```

**Response:**
```json
{
  "isRunning": true,
  "phase": "fetching",
  "streamId": "my-stream",
  "sourceUrl": "https://...",
  "stats": {
    "segmentsFetched": 45,
    "batchesProcessed": 3,
    "fragmentsPublished": 2,
    "bytesProcessed": 15728640,
    "currentBufferSize": 20.5
  },
  "lastError": null,
  "startTime": "2025-10-24T12:00:00Z",
  "uptime": 180
}
```

### Health Check

```bash
GET /api/health
```

## ⚙️ Configuration

### Environment Variables

```bash
# Server
PORT=3000
NODE_ENV=production

# HLS Source
SOURCE_URL=https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8
STREAM_ID=test-stream

# Buffer
BUFFER_DURATION_SECONDS=30

# Audio Processor
AUDIO_PROCESSOR_URL=http://localhost:5000

# SRS
SRS_RTMP_URL=rtmp://localhost/live
SRS_HTTP_API=http://localhost:1985/api/v1

# Storage
STORAGE_BASE_PATH=./storage

# FFmpeg
FFMPEG_PATH=/usr/local/bin/ffmpeg

# Logging
LOG_LEVEL=info
LOG_FORMAT=json
LOG_TO_FILE=true
LOG_TO_CONSOLE=true
```

## 🧪 Testing

```bash
# Run all tests
npm test

# Watch mode
npm run test:watch

# Coverage report
npm run test:coverage
```

### Test Coverage

- ✅ StorageService: 18 tests
- ✅ BufferManager: 21 tests
- ✅ StreamFetcher: 12 tests
- **Total: 51 tests passing**

## 📦 Project Structure

```
apps/live-media-service/
├── src/
│   ├── main.ts                    # Express server + REST API
│   ├── modules/
│   │   ├── StreamFetcher.ts       # HLS fetching & buffering
│   │   ├── AudioProcessor.ts      # Demux & WebSocket
│   │   ├── Remuxer.ts             # Video + audio combining
│   │   ├── StreamPublisher.ts     # RTMP publishing
│   │   └── PipelineOrchestrator.ts # Coordinates modules
│   ├── services/
│   │   ├── storage.service.ts     # File management
│   │   ├── buffer-manager.service.ts # 30s accumulation
│   │   └── socket-client.service.ts # WebSocket client
│   ├── types/
│   │   ├── index.ts               # Type definitions
│   │   └── protocol.ts            # WebSocket protocol
│   └── utils/
│       ├── config.ts              # Configuration loader
│       └── logger.ts              # Winston logger
├── tests/
│   └── unit/                      # Unit tests
├── public/
│   └── index.html                 # Web UI
├── scripts/
│   ├── start-srs.sh              # Start SRS
│   ├── stop-srs.sh               # Stop SRS
│   └── clean-storage.sh          # Clean storage
├── storage/                       # Runtime storage (gitignored)
├── .env.example                   # Example environment
├── package.json
├── tsconfig.json
├── vitest.config.ts
└── README.md
```

## 🔧 Development

### Adding a New Module

1. Create module in `src/modules/`
2. Extend EventEmitter
3. Add to PipelineOrchestrator
4. Write unit tests
5. Update types

### Debugging

```bash
# View FFmpeg output
LOG_LEVEL=debug npm run dev

# Monitor SRS
./scripts/logs-srs.sh

# Check storage
ls -lh storage/
```

## 🐛 Troubleshooting

### FFmpeg Not Found

```bash
# macOS
brew install ffmpeg

# Ubuntu
sudo apt-get install ffmpeg

# Or specify path in .env
FFMPEG_PATH=/usr/local/bin/ffmpeg
```

### SRS Connection Failed

```bash
# Check SRS is running
docker ps | grep srs

# Restart SRS
./scripts/restart-srs.sh

# Check SRS logs
./scripts/logs-srs.sh
```

### Audio Processor Not Connected

```bash
# Verify echo-audio-processor is running
curl http://localhost:5000

# Check WebSocket connection
AUDIO_PROCESSOR_URL=http://localhost:5000 npm run dev
```

### Storage Full

```bash
# Clean old files
./scripts/clean-storage.sh

# Or via API
curl -X POST http://localhost:3000/api/storage/clean
```

## 📚 Related Projects

- **echo-audio-processor** - Simple test service for audio processing
- **mock-media-service** - Original WebSocket protocol reference
- **sts-service** - Speech-to-speech translation service (Python)

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📄 License

MIT License - see LICENSE file for details

## 🙏 Acknowledgments

- Built with [Node.js](https://nodejs.org/)
- Media processing by [FFmpeg](https://ffmpeg.org/)
- Streaming by [SRS](https://ossrs.io/)
- WebSocket by [Socket.IO](https://socket.io/)
- Testing by [Vitest](https://vitest.dev/)

---

**Status:** ✅ Production Ready  
**Version:** 1.0.0  
**Last Updated:** October 24, 2025

Made with ❤️ for real-time live streaming

