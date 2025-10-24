# Live Media Processor - Quick Start Guide

**5-Minute Overview** | [Full Architecture](./MEDIA_SERVICE_ARCHITECTURE.md) | [Implementation Plan](./MEDIA_SERVICE_IMPLEMENTATION_PLAN.md)

---

## What Is This?

A **production-ready service** that processes live HLS streams with external audio processing:

```
HLS Stream → Fetch & Buffer (30s) → Demux → Send Audio → External Processor
                                              ↓
SRS Output ← Publish ← Remux ← Receive Processed Audio ←┘
```

**Use Cases:**
- Real-time translation of live sports commentary
- Multi-language audio tracks for live events
- Voice enhancement/noise reduction for live streams
- Automated transcription and dubbing pipelines

---

## Architecture at a Glance

### 4 Core Modules

```
┌─────────────────────┐
│  1. StreamFetcher   │  Fetches HLS, saves TS segments, buffers 30s
└──────────┬──────────┘
           │ batch:ready event
           ↓
┌─────────────────────┐
│  2. AudioProcessor  │  Demux TS → FMP4, send audio via WebSocket
└──────────┬──────────┘
           │ audio:processed event
           ↓
┌─────────────────────┐
│  3. Remuxer         │  Combine video + processed audio
└──────────┬──────────┘
           │ remux:complete event
           ↓
┌─────────────────────┐
│  4. StreamPublisher │  Publish to SRS via RTMP
└─────────────────────┘
```

### Key Technologies

- **Node.js 18+** + TypeScript
- **FFmpeg** for demux/remux
- **Socket.IO** for WebSocket communication
- **Express.js** for REST API
- **SRS** for RTMP/HLS output
- **Vitest** for testing

---

## Quick Setup (3 Steps)

### 1. Install & Configure

```bash
# Clone repo
cd multi-language-live/apps

# Create project (Phase 1 of implementation)
nx generate @nx/node:application live-media-processor

# Install dependencies
cd live-media-processor
npm install express socket.io-client m3u8stream m3u8-parser winston
npm install -D @types/express vitest typescript

# Create .env
cat > .env << EOF
SOURCE_URL=https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8
STREAM_ID=test-stream
AUDIO_PROCESSOR_URL=ws://localhost:5000
SRS_RTMP_URL=rtmp://localhost/live/test-stream
BUFFER_DURATION=30
STORAGE_PATH=./storage
EOF
```

### 2. Start Services

```bash
# Terminal 1: Start SRS
docker run -d -p 1935:1935 -p 8080:8080 --name srs ossrs/srs:5

# Terminal 2: Start echo audio processor (for testing)
cd apps/echo-audio-processor
npm start

# Terminal 3: Start live media processor
cd apps/live-media-processor
npm start
```

### 3. Test It Out

```bash
# Start pipeline via API
curl -X POST http://localhost:3000/api/pipeline/start \
  -H "Content-Type: application/json" \
  -d '{
    "sourceUrl": "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8",
    "streamId": "test-stream",
    "audioProcessorUrl": "ws://localhost:5000",
    "srsRtmpUrl": "rtmp://localhost/live/test-stream",
    "bufferDuration": 30
  }'

# Check status
curl http://localhost:3000/api/pipeline/status

# View output (wait 30-40 seconds for first batch)
open http://localhost:8080/players/srs_player.html?stream=test-stream.m3u8
```

Or use the **Web UI**: `http://localhost:3000`

---

## File Structure (Final)

```
apps/live-media-processor/
├── src/
│   ├── main.ts                      # Express server
│   ├── modules/
│   │   ├── StreamFetcher.ts         # HLS fetching
│   │   ├── AudioProcessor.ts        # Demuxing
│   │   ├── Remuxer.ts               # Remuxing
│   │   ├── StreamPublisher.ts       # SRS publishing
│   │   └── PipelineOrchestrator.ts  # Coordination
│   ├── services/
│   │   ├── socket-client.service.ts # WebSocket client
│   │   ├── storage.service.ts       # Disk management
│   │   └── buffer-manager.service.ts # 30s buffer
│   ├── types/                       # TypeScript types
│   └── utils/                       # Logger, config
├── tests/
│   ├── unit/                        # Unit tests
│   └── integration/                 # Integration tests
├── storage/                         # Runtime data
│   ├── original_stream/             # TS segments
│   └── processed_fragments/         # FMP4 files
├── public/
│   └── index.html                   # Web UI
└── scripts/                         # Utility scripts

apps/echo-audio-processor/           # Test service
└── src/
    └── main.ts                      # Echo server
```

---

## How It Works

### Step-by-Step Flow

1. **Fetch HLS Stream** (StreamFetcher)
   - Download M3U8 manifest
   - Fetch TS segments continuously
   - Save to `storage/original_stream/{stream-id}/segment-N.ts`
   - Accumulate duration until 30s

2. **Process Batch** (AudioProcessor)
   - Concatenate 30s of TS segments
   - FFmpeg demux: `TS → video.fmp4 + audio.fmp4`
   - Save to `storage/processed_fragments/{stream-id}/batch-N/`
   - Send `audio.fmp4` to external processor via WebSocket

3. **External Processing**
   - External service receives audio fragment
   - Processes it (transcription, translation, voice cloning, etc.)
   - Returns processed audio via WebSocket

4. **Remux** (Remuxer)
   - Receive processed audio from WebSocket
   - Load corresponding `video.fmp4` from disk
   - FFmpeg remux: `video.fmp4 + processed_audio.fmp4 → output.fmp4`
   - Pass to publisher

5. **Publish** (StreamPublisher)
   - Convert FMP4 to FLV
   - Push to SRS via RTMP: `rtmp://localhost/live/{stream-id}`
   - SRS generates HLS output: `http://localhost:8080/live/{stream-id}.m3u8`

### Timing Example

```
Time:  0s    6s   12s   18s   24s   30s   32s   37s   42s   44s
       |-----|-----|-----|-----|-----|-----|-----|-----|-----|
Fetch: [seg1][seg2][seg3][seg4][seg5]
                                      |
                                      v (batch ready)
Demux:                                [FFmpeg 2s]
                                              |
                                              v
Socket:                                       [Send audio]
                                                    |
                                                    v
Process:                                            [External 5s]
                                                         |
                                                         v
Remux:                                                   [FFmpeg 2s]
                                                              |
                                                              v
Publish:                                                      [RTMP]

Total: 30s buffer + 2s demux + 5s process + 2s remux = 39s latency
```

---

## Key Features

✅ **Disk-Based Storage** - All segments and fragments saved for recovery  
✅ **Configurable Buffer** - 30s default, adjust via `BUFFER_DURATION`  
✅ **External Processing** - WebSocket protocol for any audio processor  
✅ **Zero Video Re-encoding** - Video stream copied, only audio processed  
✅ **Production-Ready** - Error handling, logging, graceful shutdown  
✅ **Web UI** - Real-time monitoring and debugging  
✅ **TDD Approach** - Vitest with >90% coverage target  
✅ **REST API** - Programmatic control  

---

## API Reference

### Start Pipeline

```bash
POST /api/pipeline/start
Content-Type: application/json

{
  "sourceUrl": "https://example.com/stream.m3u8",
  "streamId": "my-stream",
  "audioProcessorUrl": "ws://processor:5000",
  "srsRtmpUrl": "rtmp://localhost/live/my-stream",
  "bufferDuration": 30
}
```

### Get Status

```bash
GET /api/pipeline/status

Response:
{
  "isRunning": true,
  "streamFetcher": {
    "segmentsDownloaded": 142,
    "accumulatedDuration": 18.5,
    "currentBatchNumber": 4
  },
  "audioProcessor": { "batchesProcessed": 4 },
  "remuxer": { "batchesRemuxed": 3 },
  "streamPublisher": { "fragmentsPublished": 3 }
}
```

### Stop Pipeline

```bash
POST /api/pipeline/stop
```

### Clean Storage

```bash
POST /api/storage/clean
Content-Type: application/json

{
  "streamId": "my-stream",
  "keepLast": 5
}
```

---

## Testing Strategy

### Test-Driven Development (TDD)

```bash
# Write test first
cat > tests/unit/StreamFetcher.test.ts << EOF
describe('StreamFetcher', () => {
  it('should emit batch:ready after 30s', async () => {
    const fetcher = new StreamFetcher({ bufferDuration: 30 });
    const promise = new Promise(resolve => fetcher.on('batch:ready', resolve));
    await fetcher.start();
    const result = await promise;
    expect(result.batchNumber).toBe(0);
  });
});
EOF

# Run test (fails)
npm test -- StreamFetcher.test.ts

# Implement feature
# ...

# Run test (passes)
npm test -- StreamFetcher.test.ts
```

### Test Commands

```bash
# All tests
npm test

# Unit tests only
npm test -- tests/unit/

# Integration tests
npm test -- tests/integration/

# Coverage
npm run test:coverage

# Watch mode (for TDD)
npm run test:watch
```

### Test Structure

```
tests/
├── unit/
│   ├── StreamFetcher.test.ts
│   ├── AudioProcessor.test.ts
│   ├── Remuxer.test.ts
│   ├── StreamPublisher.test.ts
│   ├── BufferManager.test.ts
│   └── StorageService.test.ts
├── integration/
│   ├── pipeline.test.ts
│   ├── socket-protocol.test.ts
│   └── srs-publishing.test.ts
└── fixtures/
    ├── test-segments/
    └── expected-outputs/
```

---

## Common Issues

### "Pipeline not starting"

```bash
# Check dependencies
ffmpeg -version
docker ps | grep srs

# Check logs
tail -f storage/logs/combined.log

# Verify source URL
curl -I "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"
```

### "No output in SRS"

```bash
# Wait 30-40 seconds for first batch
# Check SRS
curl http://localhost:8080/api/v1/streams/

# Check logs for errors
grep ERROR storage/logs/combined.log
```

### "WebSocket not connecting"

```bash
# Check echo processor is running
lsof -i :5000

# Test WebSocket directly
npm install -g wscat
wscat -c ws://localhost:5000
```

### "Disk full"

```bash
# Clean old batches
curl -X POST http://localhost:3000/api/storage/clean

# Or manually
rm -rf storage/processed_fragments/*/batch-0
```

---

## Performance

### Resource Usage (Per Stream)

- **CPU:** 50-80% of one core
- **Memory:** 200-400 MB
- **Disk Write:** 2-10 MB/s
- **Storage:** ~36 GB per hour (1080p)

### Optimization Tips

1. **Reduce Buffer:** 20s instead of 30s
2. **Lower Resolution:** Use lower quality source
3. **Faster Processor:** Optimize external audio processing
4. **Cleanup:** Enable `AUTO_CLEANUP=true` in .env
5. **Hardware Accel:** Use FFmpeg `-hwaccel` for GPU

---

## Next Steps

### For Development

1. 📖 Read [MEDIA_SERVICE_ARCHITECTURE.md](./MEDIA_SERVICE_ARCHITECTURE.md)
2. 📋 Follow [MEDIA_SERVICE_IMPLEMENTATION_PLAN.md](./MEDIA_SERVICE_IMPLEMENTATION_PLAN.md)
3. 🏗️ Start with Phase 1 (Core Infrastructure)
4. ✅ Write tests first (TDD)
5. 🔄 Implement incrementally

### For Deployment

1. 🐳 Build Docker images
2. ⚙️ Configure production environment
3. 🔐 Set up authentication
4. 📊 Configure monitoring (Prometheus/Grafana)
5. 🚀 Deploy to production

### For Integration

1. 🔌 Build your audio processor following the protocol
2. 📡 Test with echo processor first
3. 🧪 Add comprehensive tests
4. 📈 Monitor performance
5. 🎛️ Tune buffer size and parameters

---

## Resources

### Documentation
- [Architecture Overview](./MEDIA_SERVICE_ARCHITECTURE.md) - Complete technical architecture
- [Implementation Plan](./MEDIA_SERVICE_IMPLEMENTATION_PLAN.md) - Step-by-step development guide
- [Mock Media Service Protocol](../apps/mock-media-service/PROTOCOL.md) - WebSocket protocol spec

### References
- [FFmpeg Documentation](https://ffmpeg.org/documentation.html)
- [Socket.IO Client API](https://socket.io/docs/v4/client-api/)
- [SRS Documentation](https://ossrs.io/)
- [Vitest Documentation](https://vitest.dev/)

### Example Implementations
- `apps/streaming-demux-remux/` - FFmpeg pipeline reference
- `apps/mock-media-service/` - WebSocket protocol reference

---

## Support & Contributing

### Getting Help

1. Check [Troubleshooting](#common-issues) section
2. Review logs in `storage/logs/`
3. Search existing issues
4. Create detailed bug report

### Contributing

1. Read implementation plan
2. Follow TDD approach
3. Maintain >90% coverage
4. Update documentation
5. Submit PR with tests

---

**Quick Start Version:** 1.0  
**Last Updated:** October 24, 2025  
**Ready to Build:** ✅

🚀 **Let's build this!** Start with the [Implementation Plan](./MEDIA_SERVICE_IMPLEMENTATION_PLAN.md)

