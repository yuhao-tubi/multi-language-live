# Live Media Service - Implementation Plan

**Document:** Implementation Checklist and Development Guide  
**Created:** October 24, 2025  
**Architecture Reference:** [MEDIA_SERVICE_ARCHITECTURE.md](./MEDIA_SERVICE_ARCHITECTURE.md)

---

## Quick Reference

### What We're Building

A production-ready live HLS stream processor that:
1. Fetches live HLS streams → saves TS segments to disk
2. Accumulates 30-second batches → demuxes into video + audio FMP4
3. Sends audio to external processor via WebSocket → receives processed audio back
4. Remuxes video + processed audio → publishes to SRS via RTMP
5. Provides web UI for monitoring and debugging

### Key Technologies

- **Node.js 22+** (LTS) with TypeScript
- **FFmpeg** for media processing
- **Socket.IO** for WebSocket communication  
- **Express.js** for REST API
- **SRS** for RTMP/HLS output
- **Vitest** for TDD
- **Winston** for logging

---

## Project Structure Overview

```
apps/live-media-service/
├── src/
│   ├── main.ts                           # Express server entry point
│   ├── modules/                          # Core processing modules
│   │   ├── StreamFetcher.ts              # 1. HLS fetching & buffering
│   │   ├── AudioProcessor.ts             # 2. Demux & WebSocket sender
│   │   ├── Remuxer.ts                    # 3. Video + Audio combining
│   │   ├── StreamPublisher.ts            # 4. SRS publishing
│   │   └── PipelineOrchestrator.ts       # Coordinates all modules
│   ├── services/
│   │   ├── socket-client.service.ts      # WebSocket client
│   │   ├── storage.service.ts            # Disk management
│   │   ├── buffer-manager.service.ts     # 30s buffer logic
│   │   └── srs.service.ts                # SRS control
│   ├── types/
│   │   ├── index.ts                      # Type definitions
│   │   └── protocol.ts                   # WebSocket protocol types
│   └── utils/
│       ├── logger.ts                     # Winston logger
│       └── config.ts                     # Config loader
├── tests/
│   ├── unit/                             # Unit tests
│   │   ├── StreamFetcher.test.ts
│   │   ├── AudioProcessor.test.ts
│   │   ├── Remuxer.test.ts
│   │   ├── StreamPublisher.test.ts
│   │   ├── BufferManager.test.ts
│   │   └── StorageService.test.ts
│   ├── integration/                      # Integration tests
│   │   ├── pipeline.test.ts
│   │   └── socket-protocol.test.ts
│   └── fixtures/                         # Test data
│       └── test-segments/
├── storage/                              # Runtime storage (gitignored)
│   ├── original_stream/
│   ├── processed_fragments/
│   └── logs/
├── scripts/
│   ├── start-srs.sh
│   ├── stop-srs.sh
│   └── clean-storage.sh
├── public/
│   └── index.html                        # Web UI
├── .env.example
├── package.json
├── tsconfig.json
├── vitest.config.ts
└── README.md
```

---

## Implementation Phases

### ✅ Phase 1: Core Infrastructure (Week 1-2)

**Goal:** Set up project scaffold, utilities, and basic services

**Tasks:**
- [ ] Create project structure with Nx
- [ ] Set up TypeScript configuration (ES2023, NodeNext)
- [ ] Install dependencies (express, socket.io-client, winston, etc.)
- [ ] Configure Vitest for testing
- [ ] Implement StorageService with directory management
- [ ] Implement BufferManager for 30s accumulation
- [ ] Create Logger utility with Winston
- [ ] Write unit tests for utilities (>90% coverage)
- [ ] Create SRS startup/stop scripts
- [ ] Create .env.example with all variables
- [ ] Test SRS connectivity

**Deliverables:**
```bash
✓ apps/live-media-service/ structure created
✓ package.json with all dependencies
✓ vitest.config.ts configured
✓ src/services/storage.service.ts + tests
✓ src/services/buffer-manager.service.ts + tests
✓ src/utils/logger.ts + tests
✓ scripts/start-srs.sh working
✓ All unit tests passing
```

**Testing Commands:**
```bash
npm test -- tests/unit/StorageService.test.ts
npm test -- tests/unit/BufferManager.test.ts
npm run test:coverage
```

---

### ✅ Phase 2: Stream Fetcher Module (Week 2-3)

**Goal:** Implement HLS fetching with 30s buffering

**Tasks:**
- [ ] Create StreamFetcher class with EventEmitter
- [ ] Implement HLS manifest parsing (m3u8-parser)
- [ ] Implement segment downloading (m3u8stream)
- [ ] Save segments to disk with proper naming
- [ ] Integrate BufferManager for accumulation
- [ ] Emit 'batch:ready' when 30s reached
- [ ] Add error handling and retry logic
- [ ] Implement graceful shutdown
- [ ] Write comprehensive unit tests
- [ ] Integration test with real HLS stream
- [ ] Document StreamFetcher API

**Key Code Snippet:**
```typescript
export class StreamFetcher extends EventEmitter {
  async start(): Promise<void> {
    // 1. Parse M3U8
    const manifest = await this.parseManifest(this.sourceUrl);
    
    // 2. Create segment stream
    this.segmentStream = m3u8stream(manifest.playlists[0].uri);
    
    // 3. Listen for segments
    this.segmentStream.on('data', async (chunk) => {
      const segment = await this.saveSegment(chunk);
      const batch = this.bufferManager.addSegment(segment);
      
      if (batch) {
        this.emit('batch:ready', batch);
      }
    });
  }
}
```

**Testing Commands:**
```bash
npm test -- tests/unit/StreamFetcher.test.ts
npm test -- tests/integration/hls-fetching.test.ts
```

**Deliverables:**
```bash
✓ src/modules/StreamFetcher.ts implemented
✓ HLS fetching working with test stream
✓ 30s batches emitted correctly
✓ Segments saved to disk
✓ All tests passing (unit + integration)
```

---

### ✅ Phase 3: Audio Processor Module (Week 3-4)

**Goal:** Demux TS batches and send audio via WebSocket

**Tasks:**
- [ ] Create AudioProcessor class
- [ ] Implement TS concatenation for batch segments
- [ ] Implement FFmpeg demux (TS → video.fmp4 + audio.fmp4)
- [ ] Save demuxed files to disk
- [ ] Create SocketClientService for WebSocket communication
- [ ] Implement fragment sending (follow protocol)
- [ ] Handle processed audio reception
- [ ] Add error handling for FFmpeg and WebSocket
- [ ] Write unit tests for demux operations
- [ ] Write integration tests with mock WebSocket server
- [ ] Document protocol usage

**Key FFmpeg Command:**
```bash
ffmpeg -i input.ts \
  -map 0:v -c:v copy -f mp4 -movflags frag_keyframe+empty_moov video.fmp4 \
  -map 0:a -c:a copy -f mp4 -movflags frag_keyframe+empty_moov audio.fmp4
```

**Key Code Snippet:**
```typescript
export class AudioProcessor extends EventEmitter {
  async processBatch(batchNumber: number, segments: SegmentMetadata[]): Promise<void> {
    // 1. Concatenate segments
    const concatenated = await this.concatenateSegments(segments);
    
    // 2. Demux
    const { videoPath, audioPath } = await this.demux(concatenated, batchNumber);
    
    // 3. Read audio
    const audioBuffer = await fs.readFile(audioPath);
    
    // 4. Send via WebSocket
    const fragment = this.createFragment(batchNumber, audioBuffer);
    await this.socketClient.sendFragment(fragment, audioBuffer);
    
    this.emit('audio:sent', { batchNumber, videoPath, audioPath });
  }
}
```

**Testing Commands:**
```bash
npm test -- tests/unit/AudioProcessor.test.ts
npm test -- tests/integration/socket-protocol.test.ts
```

**Deliverables:**
```bash
✓ src/modules/AudioProcessor.ts implemented
✓ src/services/socket-client.service.ts implemented
✓ FFmpeg demux working correctly
✓ WebSocket communication functional
✓ Mock-media-service protocol followed
✓ All tests passing
```

---

### ✅ Phase 4: Echo Audio Processor (Test Service) (Week 4)

**Goal:** Build simple echo service for testing

**Tasks:**
- [ ] Create apps/echo-audio-processor/ project
- [ ] Implement Socket.IO server
- [ ] Listen for 'fragment:data' events
- [ ] Immediately echo back as 'fragment:processed'
- [ ] Add minimal logging
- [ ] Write basic tests
- [ ] Document usage

**Implementation:**
```typescript
// apps/echo-audio-processor/src/main.ts
import { Server } from 'socket.io';

const io = new Server(5000, { cors: { origin: '*' } });

io.on('connection', (socket) => {
  console.log(`[ECHO] Client connected: ${socket.id}`);
  
  socket.on('fragment:data', ({ fragment, data }) => {
    console.log(`[ECHO] Received: ${fragment.id}`);
    
    // Echo back after 100ms
    setTimeout(() => {
      socket.emit('fragment:processed', { fragment, data });
      console.log(`[ECHO] Sent back: ${fragment.id}`);
    }, 100);
  });
});
```

**Testing:**
```bash
cd apps/echo-audio-processor
npm start &

# Test with live-media-service
cd ../live-media-service
npm start
```

**Deliverables:**
```bash
✓ apps/echo-audio-processor/ created
✓ Socket.IO server working
✓ Echo functionality verified
✓ README with usage instructions
```

---

### ✅ Phase 5: Remuxer Module (Week 4-5)

**Goal:** Combine processed audio with video

**Tasks:**
- [ ] Create Remuxer class
- [ ] Implement processed audio reception handler
- [ ] Save processed audio to disk
- [ ] Implement FFmpeg remux (video.fmp4 + audio.fmp4 → output.fmp4)
- [ ] Emit 'remux:complete' event
- [ ] Handle missing video files
- [ ] Add retry logic for failed remux
- [ ] Write unit tests
- [ ] Write integration tests
- [ ] Document remux process

**Key FFmpeg Command:**
```bash
ffmpeg -i video.fmp4 -i processed_audio.fmp4 \
  -map 0:v -c:v copy \
  -map 1:a -c:a copy \
  -f mp4 -movflags frag_keyframe+empty_moov \
  output.fmp4
```

**Key Code Snippet:**
```typescript
export class Remuxer extends EventEmitter {
  async onProcessedAudioReceived(
    batchNumber: number, 
    processedAudioBuffer: Buffer
  ): Promise<void> {
    // 1. Save processed audio
    const processedAudioPath = this.getProcessedAudioPath(batchNumber);
    await fs.writeFile(processedAudioPath, processedAudioBuffer);
    
    // 2. Load video
    const videoPath = this.getVideoPath(batchNumber);
    
    // 3. Remux
    const outputPath = this.getOutputPath(batchNumber);
    await this.remux(videoPath, processedAudioPath, outputPath);
    
    this.emit('remux:complete', { batchNumber, outputPath });
  }
}
```

**Testing Commands:**
```bash
npm test -- tests/unit/Remuxer.test.ts
npm test -- tests/integration/remux.test.ts
```

**Deliverables:**
```bash
✓ src/modules/Remuxer.ts implemented
✓ FFmpeg remux working
✓ Proper A/V sync verified
✓ All tests passing
```

---

### ✅ Phase 6: Stream Publisher Module (Week 5-6)

**Goal:** Publish to SRS via RTMP

**Tasks:**
- [ ] Create StreamPublisher class
- [ ] Implement RTMP connection to SRS
- [ ] Implement fragment publishing
- [ ] Handle connection failures and reconnection
- [ ] Add backpressure handling
- [ ] Monitor SRS output availability
- [ ] Write unit tests (with mock SRS)
- [ ] Write integration tests (with real SRS)
- [ ] Document publishing process

**Key FFmpeg Command:**
```bash
# Option 1: Continuous with concat demuxer
ffmpeg -re -f concat -safe 0 -i pipe:0 \
  -c:v copy -c:a copy \
  -f flv rtmp://localhost/live/stream-id

# Option 2: Per-fragment
ffmpeg -re -i output.fmp4 \
  -c:v copy -c:a copy \
  -f flv rtmp://localhost/live/stream-id
```

**Key Code Snippet:**
```typescript
export class StreamPublisher extends EventEmitter {
  async start(): Promise<void> {
    this.ffmpegProcess = spawn('ffmpeg', [
      '-re', '-f', 'concat', '-safe', '0', '-i', 'pipe:0',
      '-c:v', 'copy', '-c:a', 'copy',
      '-f', 'flv', this.srsRtmpUrl
    ]);
    
    this.isPublishing = true;
  }
  
  async publishFragment(fragmentPath: string): Promise<void> {
    this.ffmpegProcess?.stdin?.write(`file '${fragmentPath}'\n`);
    this.emit('fragment:published', { fragmentPath });
  }
}
```

**Testing Commands:**
```bash
npm test -- tests/unit/StreamPublisher.test.ts
npm test -- tests/integration/srs-publishing.test.ts

# Verify output
curl http://localhost:8080/live/test-stream.m3u8
```

**Deliverables:**
```bash
✓ src/modules/StreamPublisher.ts implemented
✓ RTMP publishing working
✓ SRS output playable
✓ All tests passing
```

---

### ✅ Phase 7: Pipeline Orchestrator (Week 6-7)

**Goal:** Coordinate all modules

**Tasks:**
- [ ] Create PipelineOrchestrator class
- [ ] Initialize all modules with configuration
- [ ] Set up event handlers between modules
- [ ] Implement start/stop lifecycle
- [ ] Add error propagation and recovery
- [ ] Implement graceful shutdown
- [ ] Create status aggregation
- [ ] Write integration tests for full pipeline
- [ ] Load testing (multiple streams)
- [ ] Document orchestration flow

**Key Code Snippet:**
```typescript
export class PipelineOrchestrator {
  private setupEventHandlers(): void {
    // Stream Fetcher → Audio Processor
    this.streamFetcher.on('batch:ready', async ({ batchNumber, segments }) => {
      await this.audioProcessor.processBatch(batchNumber, segments);
    });
    
    // Audio Processor → Remuxer
    this.audioProcessor.on('audio:processed', async ({ batchNumber, processedAudioBuffer }) => {
      await this.remuxer.onProcessedAudioReceived(batchNumber, processedAudioBuffer);
    });
    
    // Remuxer → Stream Publisher
    this.remuxer.on('remux:complete', async ({ batchNumber, outputPath }) => {
      await this.streamPublisher.publishFragment(outputPath);
    });
    
    // Error handling
    [this.streamFetcher, this.audioProcessor, this.remuxer, this.streamPublisher]
      .forEach(module => module.on('error', (error) => this.handleError(error)));
  }
}
```

**Testing Commands:**
```bash
npm test -- tests/integration/pipeline.test.ts
npm run test:e2e
```

**Deliverables:**
```bash
✓ src/modules/PipelineOrchestrator.ts implemented
✓ Full pipeline working end-to-end
✓ Error handling verified
✓ Graceful shutdown working
✓ Integration tests passing
```

---

### ✅ Phase 8: REST API & Server (Week 7)

**Goal:** Build Express.js API for control

**Tasks:**
- [ ] Create Express server in main.ts
- [ ] Implement POST /api/pipeline/start
- [ ] Implement POST /api/pipeline/stop
- [ ] Implement GET /api/pipeline/status
- [ ] Implement GET /api/storage/stats
- [ ] Implement POST /api/storage/clean
- [ ] Add request validation
- [ ] Add error handling middleware
- [ ] Add CORS support
- [ ] Write API tests with Supertest
- [ ] Document API endpoints with examples

**Key Code Snippet:**
```typescript
// src/main.ts
const app = express();
app.use(express.json());

let pipeline: PipelineOrchestrator | null = null;

app.post('/api/pipeline/start', async (req, res) => {
  const config = req.body;
  pipeline = new PipelineOrchestrator(config);
  await pipeline.start();
  res.json({ success: true, message: 'Pipeline started' });
});

app.get('/api/pipeline/status', (req, res) => {
  const status = pipeline?.getStatus() || { isRunning: false };
  res.json(status);
});

app.listen(3000, () => {
  console.log('Server running on http://localhost:3000');
});
```

**Testing Commands:**
```bash
npm test -- tests/api/endpoints.test.ts

# Manual testing
curl -X POST http://localhost:3000/api/pipeline/start \
  -H "Content-Type: application/json" \
  -d '{"sourceUrl":"...","streamId":"test"}'
```

**Deliverables:**
```bash
✓ src/main.ts with Express server
✓ All API endpoints implemented
✓ Request validation working
✓ API tests passing
✓ API documentation written
```

---

### ✅ Phase 9: Web UI (Week 8)

**Goal:** Create debugging and monitoring interface

**Tasks:**
- [ ] Create HTML/CSS/JS structure
- [ ] Build configuration form
- [ ] Implement start/stop controls
- [ ] Add real-time status display
- [ ] Implement WebSocket log streaming
- [ ] Add storage statistics display
- [ ] Add cleanup controls
- [ ] Integrate HLS.js player for output preview
- [ ] Make responsive design
- [ ] Test on different browsers
- [ ] Document UI features

**Key Features:**
```html
<!-- public/index.html -->
<div class="control-panel">
  <h2>Pipeline Control</h2>
  <form id="config-form">
    <input type="text" id="source-url" placeholder="HLS Source URL">
    <input type="text" id="stream-id" placeholder="Stream ID">
    <input type="number" id="buffer-duration" value="30">
    <button type="submit">Start Pipeline</button>
    <button type="button" id="stop-btn">Stop</button>
  </form>
</div>

<div class="status-panel">
  <h2>Status</h2>
  <div id="status-display">
    <!-- Real-time updates via WebSocket -->
  </div>
</div>

<div class="log-viewer">
  <h2>Live Logs</h2>
  <div id="logs">
    <!-- Streaming logs via WebSocket -->
  </div>
</div>

<div class="player-panel">
  <h2>Output Preview</h2>
  <video id="hls-player"></video>
</div>
```

**Testing:**
```bash
# Start server and open in browser
npm start
open http://localhost:3000
```

**Deliverables:**
```bash
✓ public/index.html created
✓ WebSocket log streaming working
✓ Real-time status updates
✓ HLS player integration
✓ Responsive design
✓ User guide in README
```

---

### ✅ Phase 10: Testing & Documentation (Week 8-9)

**Goal:** Complete test coverage and documentation

**Tasks:**
- [ ] Achieve >90% unit test coverage
- [ ] Complete all integration tests
- [ ] Add end-to-end tests
- [ ] Performance benchmarking
- [ ] Load testing (stress test)
- [ ] Write comprehensive README
- [ ] Write API documentation
- [ ] Write deployment guide
- [ ] Create troubleshooting guide
- [ ] Add inline code documentation

**Test Coverage Goals:**
```bash
✓ Unit Tests: >90% coverage
✓ Integration Tests: All modules
✓ E2E Tests: Complete pipeline
✓ Performance Tests: Resource usage
✓ Load Tests: Multiple concurrent streams
```

**Documentation Checklist:**
```bash
✓ README.md with quick start
✓ ARCHITECTURE.md (this document)
✓ API.md with all endpoints
✓ DEPLOYMENT.md with setup guide
✓ TROUBLESHOOTING.md
✓ Inline JSDoc comments
✓ Example configurations
```

**Testing Commands:**
```bash
npm run test:coverage
npm run test:e2e
npm run test:load
```

**Deliverables:**
```bash
✓ All tests passing
✓ Coverage >90%
✓ Complete documentation
✓ Performance benchmarks documented
```

---

## Development Guidelines

### Code Standards

1. **TypeScript Strict Mode**
   ```json
   {
     "compilerOptions": {
       "target": "ES2023",
       "module": "NodeNext",
       "moduleResolution": "NodeNext",
       "lib": ["ES2023"],
       "strict": true,
       "noImplicitAny": true,
       "strictNullChecks": true,
       "esModuleInterop": true,
       "skipLibCheck": true,
       "forceConsistentCasingInFileNames": true
     }
   }
   ```

2. **Naming Conventions**
   - Classes: PascalCase (e.g., `StreamFetcher`)
   - Methods: camelCase (e.g., `processBatch`)
   - Constants: UPPER_SNAKE_CASE (e.g., `BUFFER_DURATION`)
   - Files: kebab-case (e.g., `stream-fetcher.ts`)

3. **Error Handling**
   - Always use try-catch for async operations
   - Emit 'error' events from EventEmitters
   - Log errors with stack traces
   - Include context in error messages

4. **Logging Standards**
   ```typescript
   logger.debug(`[MODULE] Detailed debug info`);
   logger.info(`[MODULE] Important event`);
   logger.warn(`[MODULE] Warning condition`);
   logger.error(`[MODULE] Error occurred:`, error);
   ```

### Testing Standards

1. **Test File Naming**
   - Unit: `ComponentName.test.ts`
   - Integration: `feature-name.test.ts`
   - E2E: `pipeline.e2e.test.ts`

2. **Test Structure**
   ```typescript
   describe('ComponentName', () => {
     beforeEach(() => { /* setup */ });
     afterEach(() => { /* cleanup */ });
     
     it('should do something specific', () => {
       // Arrange
       // Act
       // Assert
     });
   });
   ```

3. **Test Coverage Requirements**
   - Unit tests: >90% coverage
   - All public methods tested
   - Error paths tested
   - Edge cases covered

### Git Workflow

1. **Branch Naming**
   - Feature: `feature/stream-fetcher`
   - Bugfix: `fix/buffer-overflow`
   - Test: `test/audio-processor`

2. **Commit Messages**
   ```
   feat(stream-fetcher): implement 30s buffer accumulation
   
   - Add BufferManager integration
   - Emit batch:ready event when threshold reached
   - Add unit tests for buffer logic
   ```

3. **PR Guidelines**
   - One feature per PR
   - All tests passing
   - Coverage maintained >90%
   - Documentation updated
   - Reviewer approval required

---

## Environment Setup

### Prerequisites

```bash
# Node.js (LTS)
node --version  # 22+

# FFmpeg
ffmpeg -version  # 4.0+

# Docker (for SRS)
docker --version
```

### Quick Start

```bash
# 1. Install dependencies
npm install

# 2. Create environment file
cd apps/live-media-service
cp .env.example .env

# 3. Start SRS
./scripts/start-srs.sh

# 4. Start echo processor (terminal 1)
cd apps/echo-audio-processor
npm start

# 5. Start main service (terminal 2)
cd apps/live-media-service
npm run dev

# 6. Open web UI
open http://localhost:3000
```

### Development Workflow

```bash
# Run tests in watch mode
npm run test:watch

# Run specific test file
npm test -- StreamFetcher.test.ts

# Check coverage
npm run test:coverage

# Build for production
npm run build

# Run production build
npm start
```

---

## Success Criteria

### Phase Completion Checklist

Each phase is considered complete when:
- [ ] All code implemented per specification
- [ ] All unit tests written and passing
- [ ] Integration tests written and passing
- [ ] Code coverage >90%
- [ ] Documentation updated
- [ ] Code reviewed and approved
- [ ] No linting errors
- [ ] Performance benchmarks met

### Final Delivery Criteria

Project is ready for production when:
- [ ] All phases completed
- [ ] End-to-end tests passing
- [ ] Load tests passing (5+ concurrent streams)
- [ ] Documentation complete
- [ ] Deployment guide verified
- [ ] Security review passed
- [ ] Performance benchmarks documented
- [ ] Monitoring dashboards created

---

## Resources & References

### Documentation
- [MEDIA_SERVICE_ARCHITECTURE.md](./MEDIA_SERVICE_ARCHITECTURE.md) - Complete architecture
- [streaming-demux-remux/README.md](../apps/streaming-demux-remux/README.md) - **LEGACY** reference implementation
- [mock-media-service/PROTOCOL.md](../apps/mock-media-service/PROTOCOL.md) - WebSocket protocol

### External References
- [FFmpeg Documentation](https://ffmpeg.org/documentation.html)
- [Socket.IO Client API](https://socket.io/docs/v4/client-api/)
- [Vitest Documentation](https://vitest.dev/)
- [SRS Documentation](https://ossrs.io/)

### Test Streams
- Mux Test Stream: `https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8`
- Big Buck Bunny: `http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4`

---

## Next Steps

1. **Review this plan** with the team
2. **Set up project structure** (Phase 1)
3. **Begin TDD approach** - write tests first
4. **Implement incrementally** - one module at a time
5. **Continuous integration** - test after each module
6. **Document as you go** - don't leave it for later

---

**Document Version:** 1.0  
**Last Updated:** October 24, 2025  
**Ready to Begin:** ✅ Yes

Let's build something great! 🚀

