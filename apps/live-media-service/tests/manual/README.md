# Manual Tests

This directory contains manual integration tests for the Live Media Service.

## StreamPublisher Playback Test

**File:** `stream-publisher-playback.test.ts`

### Purpose

This test validates the `StreamPublisher` module by reading pre-recorded batch files and publishing them to an SRS RTMP server at real-time pace (30 seconds per clip). This simulates a live streaming scenario without requiring an actual HLS source.

### Prerequisites

1. **SRS Server Running**
   ```bash
   cd apps/live-media-service
   ./scripts/start-srs.sh
   ```

2. **Batch Files Available**
   - Location: `storage/processed_fragments/output/test-stream/`
   - Files should be named: `batch-0.mp4`, `batch-1.mp4`, etc.
   - Each batch should be approximately 30 seconds duration

### Running the Test

#### Option 1: Using npm script (Recommended)
```bash
cd apps/live-media-service
npm run test:stream-publisher
```

#### Option 2: Using the shell script directly
```bash
cd apps/live-media-service
./scripts/test-stream-publisher.sh
```

#### Option 3: Using tsx directly
```bash
cd apps/live-media-service
npx tsx tests/manual/stream-publisher-playback.test.ts
```

### What the Test Does

1. **Initialization**
   - Scans the `test-stream` directory for batch files
   - Validates that batch files exist
   - Creates a `StreamPublisher` instance

2. **Publishing**
   - Starts the FFmpeg process with stdin piping
   - Publishes each batch file sequentially
   - Waits 30 seconds between each batch (simulating real-time)
   - Tracks progress and displays statistics

3. **Monitoring**
   - Listens to publisher events (`fragment:published`, `error`, `reconnecting`, etc.)
   - Displays progress updates
   - Shows elapsed time and completion percentage

4. **Cleanup**
   - Demonstrates the sliding window cleanup feature
   - Keeps only the last N segments on disk (configurable)
   - Gracefully stops the publisher

### Watching the Stream

While the test is running, you can watch the stream using:

**FFplay (recommended for testing):**
```bash
ffplay rtmp://localhost/live/test-stream
```

**VLC:**
1. Open VLC
2. Media → Open Network Stream
3. Enter: `rtmp://localhost/live/test-stream`
4. Click Play

**OBS Studio:**
1. Add Source → Media Source
2. Uncheck "Local File"
3. Input: `rtmp://localhost/live/test-stream`

### Configuration

Edit the `CONFIG` object in the test file to customize:

```typescript
const CONFIG = {
  streamId: 'test-stream',              // RTMP stream identifier
  srsRtmpUrl: 'rtmp://localhost/live',  // SRS server URL
  batchDirectory: '...',                 // Path to batch files
  fragmentDurationSeconds: 30,           // Seconds per batch
  maxReconnectAttempts: 3,               // Reconnection attempts
  reconnectDelayMs: 2000,                // Delay between reconnects
  maxSegmentsToKeep: 3,                  // Sliding window size
  enableCleanup: true,                   // Enable cleanup
  cleanupSafetyBuffer: 2,                // Extra segments to keep
};
```

### Expected Output

```
🎬 StreamPublisher Playback Test
================================

📁 Found 13 batch files:
   - batch-0.mp4 (8.41 MB)
   - batch-1.mp4 (8.52 MB)
   ...

⏱️  Total stream duration: 6:30 (390s)
🎯 Publishing rate: 30s per fragment

🔧 Initializing StreamPublisher...
✅ Publisher started successfully

📺 Stream URL: rtmp://localhost/live/test-stream
💡 You can watch with: ffplay rtmp://localhost/live/test-stream

🎬 Starting playback...

[0:00] Publishing batch 0...
📡 Fragment 0 published (1/13 - 7.7%)
⏳ Waiting 30s before next fragment...

[0:30] Publishing batch 1...
📡 Fragment 1 published (2/13 - 15.4%)
...

═══════════════════════════════════
📊 Playback Complete
═══════════════════════════════════
✅ Published: 13/13 fragments
⏱️  Total time: 6:30
📡 Stream: rtmp://localhost/live/test-stream

✅ Test completed successfully!
```

### Features Demonstrated

- ✅ **Stdin Piping**: Direct FFmpeg stdin piping for efficient streaming
- ✅ **Real-time Pacing**: Publishes at correct rate (30s per fragment)
- ✅ **Event Handling**: Monitors all publisher events
- ✅ **Reconnection Logic**: Handles FFmpeg failures with auto-reconnect
- ✅ **Sliding Window Cleanup**: Automatically removes old segments
- ✅ **Graceful Shutdown**: Clean stop with SIGINT/SIGTERM handling
- ✅ **Progress Tracking**: Shows completion percentage and statistics

### Troubleshooting

**No batch files found:**
- Ensure batch files exist in `storage/processed_fragments/output/test-stream/`
- Check file naming: must be `batch-N.mp4` format

**SRS connection failed:**
- Verify SRS is running: `curl http://localhost:1985/api/v1/versions`
- Check RTMP port 1935 is available: `lsof -i :1935`
- Review SRS logs: `docker logs srs` or check SRS log directory

**FFmpeg errors:**
- Check FFmpeg is installed: `ffmpeg -version`
- Review FFmpeg logs in the console output
- Ensure batch files are valid MP4 with H.264/AAC codecs

**Stream playback issues:**
- Wait 5-10 seconds for initial buffering
- Check network: `ping localhost`
- Try different player (FFplay, VLC, OBS)
- Review SRS streams: `http://localhost:1985/api/v1/streams/`

### Stopping the Test

Press `Ctrl+C` to gracefully stop the test at any time. The publisher will:
1. Stop accepting new fragments
2. Close the FFmpeg stdin stream
3. Terminate the FFmpeg process
4. Clean up resources
5. Exit with appropriate status code

### Integration with CI/CD

This is a **manual** test and is not included in the automated test suite because it:
- Requires external dependencies (SRS server)
- Runs for several minutes (real-time pacing)
- Needs large media files

For automated testing, see the unit tests in `tests/unit/`.

