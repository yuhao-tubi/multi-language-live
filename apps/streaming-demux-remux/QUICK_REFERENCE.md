# Quick Reference Card

## 🚀 Start Pipeline (3 Commands)

```bash
# 1. Start SRS
docker run -d -p 1935:1935 -p 8080:8080 --name srs ossrs/srs:5

# 2. Start Pipeline
npm run dev

# 3. Open Test Player
open index.html
```

## 🎛️ NPM Scripts

```bash
npm run verify     # Check dependencies
npm run check      # TypeScript type check
npm run build      # Compile to JavaScript
npm run dev        # Development mode (hot reload)
npm start          # Production mode
```

## 📺 Playback URLs

| Protocol | URL | Latency |
|----------|-----|---------|
| HLS | `http://localhost:8080/live/processed.m3u8` | 6-10s |
| RTMP | `rtmp://localhost/live/processed` | ~2s |

## 🔧 Configuration

Create `.env` file:
```bash
SOURCE_HLS_URL=https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8
SRS_RTMP_URL=rtmp://localhost/live/processed
AUDIO_SAMPLE_RATE=48000
AUDIO_CHANNELS=2
```

## 🎵 Customize Audio Effects

Edit `src/transforms/AudioProcessor.ts`:

```typescript
_transform(chunk: Buffer, encoding: BufferEncoding, callback: TransformCallback): void {
  const samples = new Int16Array(chunk.buffer, chunk.byteOffset, chunk.length / 2);
  
  // YOUR CUSTOM AUDIO PROCESSING HERE
  for (let i = 0; i < samples.length; i++) {
    samples[i] = /* apply your effect */;
  }
  
  this.push(Buffer.from(samples.buffer));
  callback();
}
```

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| FFmpeg not found | Install: `brew install ffmpeg` (macOS) |
| SRS connection refused | Start SRS: `docker start srs` |
| Can't find module | Run: `npm install` |
| 404 on playback | Wait 10-15s after starting pipeline |
| Audio/video out of sync | Check FFmpeg logs for DTS warnings |

## 📊 Monitor Processes

All FFmpeg processes log with prefixes:
- `[DEMUX]` - Video/audio separation
- `[DECODE]` - Audio to PCM conversion
- `[ENCODE]` - PCM to AAC encoding
- `[REMUX]` - Final muxing + RTMP push

## 🛑 Stop Everything

```bash
# Stop pipeline
Ctrl+C

# Stop SRS
docker stop srs
```

## 📁 Key Files

| File | Purpose |
|------|---------|
| `src/main.ts` | Entry point |
| `src/MultiProcessPipeline.ts` | Orchestrator |
| `src/transforms/AudioProcessor.ts` | Custom audio effects |
| `src/processes/*.ts` | FFmpeg process wrappers |
| `index.html` | Test player |

## 🔗 Architecture Flow

```
HLS → Demux → Decode → Node.js → Encode → Remux → SRS
      (split)  (PCM)   (effects)  (AAC)   (RTMP)
```

## ⚡ Performance Tips

1. **Lower CPU**: Reduce sample rate to 44100 Hz
2. **Save bandwidth**: Reduce audio bitrate in `EncodeProcess.ts`
3. **Debug issues**: Set `DEBUG=true` in `.env`

## 📚 Documentation

- **Full docs**: `README.md` (377 lines)
- **Quick start**: `QUICKSTART.md` (5 minutes)
- **Implementation**: `IMPLEMENTATION_SUMMARY.md`
- **This card**: `QUICK_REFERENCE.md`

