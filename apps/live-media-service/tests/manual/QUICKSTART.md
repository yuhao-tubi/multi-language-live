# Quick Start: StreamPublisher Test

## 🚀 Run the Test in 3 Steps

### 1. Start SRS Server
```bash
cd apps/live-media-service
./scripts/start-srs.sh
```

### 2. Run the Test
```bash
npm run test:stream-publisher
```

### 3. Watch the Stream
```bash
ffplay rtmp://localhost/live/test-stream
```

---

## 📺 What You'll See

The test will:
- Find all batch files in `storage/processed_fragments/output/test-stream/`
- Publish them at 30-second intervals (simulating real-time)
- Show progress updates and statistics
- Demonstrate sliding window cleanup

**Example Output:**
```
🎬 StreamPublisher Playback Test
================================

📁 Found 13 batch files
⏱️  Total stream duration: 6:30 (390s)

✅ Publisher started successfully
📺 Stream URL: rtmp://localhost/live/test-stream

[0:00] Publishing batch 0...
📡 Fragment 0 published (1/13 - 7.7%)
⏳ Waiting 30s before next fragment...

[0:30] Publishing batch 1...
📡 Fragment 1 published (2/13 - 15.4%)
...
```

---

## ⚠️ Prerequisites

- ✅ SRS server running on `rtmp://localhost/live`
- ✅ Batch files in `storage/processed_fragments/output/test-stream/`
- ✅ Each batch is ~30 seconds duration

---

## 🎮 Controls

- **Stop test**: Press `Ctrl+C` (graceful shutdown)
- **Change stream ID**: Edit `CONFIG.streamId` in the test file
- **Adjust cleanup**: Edit `CONFIG.maxSegmentsToKeep` (default: 3)
- **Disable cleanup**: Set `CONFIG.enableCleanup = false`

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| No batch files | Check `storage/processed_fragments/output/test-stream/` |
| SRS not running | Run `./scripts/start-srs.sh` |
| Can't watch stream | Wait 5-10s for buffering, try VLC or OBS |
| FFmpeg errors | Check batch files are valid MP4 (H.264/AAC) |

---

## 📖 Full Documentation

See [README.md](./README.md) for detailed documentation.

