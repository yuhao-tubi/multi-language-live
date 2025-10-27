# Setting Up a New Stream with SRS Using STS-Service

This guide will walk you through setting up a live stream with the SRS service using the STS-service as an audio processor for real-time translation.

## Overview

The architecture consists of three main components:

```
HLS Input → Live Media Service → STS Service (Audio Processing) → SRS Output
```

1. **Live Media Service** - Fetches HLS, demuxes audio/video, sends audio to processor, remuxes, and publishes
2. **STS Service** - Transcribes, translates, and synthesizes speech
3. **SRS Server** - Outputs HLS/FLV streams

## Prerequisites

- Node.js 20+ installed
- Python 3.10+ installed  
- Docker installed (for SRS)
- FFmpeg 4.0+ installed
- `rubberband-cli` installed (for audio processing)

### Install System Dependencies

**macOS:**
```bash
brew install ffmpeg rubberband
```

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg rubberband-cli
```

## Step 1: Start SRS Server

SRS (Simple Realtime Server) is the streaming server that outputs your processed stream.

```bash
cd apps/live-media-service
./scripts/start-srs.sh
```

This will:
- Start SRS in a Docker container
- Listen on ports: 1935 (RTMP), 8080 (HTTP), 10080 (SRT)
- Configure SRT streaming support

Verify SRS is running:
```bash
docker ps | grep srs
curl http://localhost:1985/api/v1/versions
```

## Step 2: Start STS Service

The STS service handles speech-to-speech translation. You need to set it up first.

### Install STS Service Dependencies

```bash
cd apps/sts-service

# Create and activate conda environment
conda env create -f environment.yml
conda activate multilingual-tts

# If you encounter issues, use the fallback environment
# conda env create -f force_working_environment.yml
# conda activate multilingual-tts

# Verify installation
python test_coqui_installation.py
```

### Start STS Server

You have two options:

**Option A: Full STS Server** (with voice cloning, slower but higher quality)
```bash
cd apps/sts-service
python stream_audio_client.py --targets es --device mps
```

**Option B: Simple VITS Server** (faster processing, no voice cloning)
```bash
cd apps/sts-service
python simple_vits_server.py --targets es --device mps
```

**Configuration Options:**
- `--targets es` - Target language (Spanish). Can also use `fr`, `de`, `it`, `pt`, `zh`, `ja`, `ko`
- `--device mps` - Use Apple Silicon GPU (use `cuda` for NVIDIA, `cpu` for CPU-only)
- `--whisper-model tiny` - Faster processing (use `base`, `small`, `medium`, `large` for better accuracy)
- `--config coqui-voices.yaml` - Custom voice configuration
- `--save-local` - Save processed audio locally

The server will start on `http://localhost:5000` and listen for audio processing requests.

## Step 3: Start Live Media Service

This service orchestrates the entire pipeline - fetching HLS, processing audio, and publishing to SRS.

### Install Dependencies

```bash
cd apps/live-media-service
npm install
```

### Start the Service

```bash
npm run dev
```

The service will start on `http://localhost:3000`

## Step 4: Configure and Start a Stream

### Option A: Using the Web UI (Recommended)

1. Open `http://localhost:3000` in your browser
2. Configure the pipeline:
   - **HLS Source URL**: Your input stream (e.g., `https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8`)
   - **Stream ID**: Unique identifier (e.g., `my-stream`)
   - **Buffer Duration**: 10-30 seconds (smaller = less latency, larger = more stable)
   - **Audio Processor URL**: `http://localhost:5000` (STS service)
3. Click **▶️ Start Pipeline**
4. Wait 30-40 seconds for the first processed segment
5. Click **▶️ Load Stream** to view the output

### Option B: Using the REST API

```bash
curl -X POST http://localhost:3000/api/pipeline/start \
  -H "Content-Type: application/json" \
  -d '{
    "sourceUrl": "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8",
    "streamId": "my-stream",
    "bufferDuration": 10,
    "audioProcessorUrl": "http://localhost:5000"
  }'
```

### Check Status

```bash
curl http://localhost:3000/api/pipeline/status
```

### Stop the Stream

```bash
curl -X POST http://localhost:3000/api/pipeline/stop
```

## Step 5: View the Output

Once the pipeline is running, you can view the processed stream:

**From SRS web player:**
```
http://localhost:8080/players/srs_player.html?stream=my-stream.m3u8
```

**Direct HLS URL:**
```
http://localhost:8080/live/my-stream.m3u8
```

**Using VLC or other HLS player:**
```
vlc http://localhost:8080/live/my-stream.m3u8
```

## Complete Setup Summary

```bash
# Terminal 1: SRS Server
cd apps/live-media-service
./scripts/start-srs.sh

# Terminal 2: STS Service
cd apps/sts-service
conda activate multilingual-tts
python stream_audio_client.py --targets es --device mps

# Terminal 3: Live Media Service
cd apps/live-media-service
npm run dev

# Terminal 4: Open browser
# Navigate to http://localhost:3000
# Configure and start the pipeline
```

## Advanced Configuration

### Environment Variables

Create a `.env` file in `apps/live-media-service/`:

```bash
# HLS Source
SOURCE_URL=https://your-stream.m3u8
STREAM_ID=my-stream

# Buffer Configuration
BUFFER_DURATION=10

# Audio Processor (STS Service)
AUDIO_PROCESSOR_URL=http://localhost:5000

# SRS Configuration
SRS_RTMP_URL=rtmp://localhost/live/${STREAM_ID}
SRS_HTTP_PORT=8080
SRS_SRT_PORT=10080

# Storage
STORAGE_PATH=./storage
LOG_LEVEL=info
LOG_MODULE_FILTER=  # Leave empty to show all modules
```

### STS Service Configuration

Edit `apps/sts-service/coqui-voices.yaml` to customize TTS voices:

```yaml
languages:
  es:
    model: "tts_models/es/css10/vits"
    multi_speaker: false
  fr:
    model: "tts_models/fr/css10/vits"
    multi_speaker: false
```

### Performance Optimization

**For Faster Processing:**
```bash
# Use smaller Whisper model
python stream_audio_client.py --targets es --whisper-model tiny --device mps

# Reduce buffer duration
# Set BUFFER_DURATION=10 in live-media-service
```

**For Better Quality:**
```bash
# Use larger Whisper model
python stream_audio_client.py --targets es --whisper-model small --device mps

# Increase buffer duration  
# Set BUFFER_DURATION=30 in live-media-service
```

## Troubleshooting

### STS Service Issues

**Port already in use:**
```bash
lsof -i :5000
# Kill the process or change port in STS service
```

**Models not downloading:**
- First run downloads models (~2-3GB)
- Check network connectivity
- Verify disk space

**Processing too slow:**
```bash
# Use smaller models
python stream_audio_client.py --targets es --whisper-model tiny --device mps
```

### Live Media Service Issues

**Cannot connect to STS:**
```bash
# Verify STS is running
curl http://localhost:5000

# Check STS logs
# Look for "Server ready!" message
```

**SRS not receiving stream:**
```bash
# Check SRS logs
docker logs -f srs

# Verify SRT connection
# Look for "publish" events in SRS logs
```

**FFmpeg errors:**
```bash
# Verify FFmpeg installation
ffmpeg -version

# Check FFmpeg path in .env
FFMPEG_PATH=/usr/local/bin/ffmpeg
```

### Storage Issues

**Disk full:**
```bash
# Clean old files
cd apps/live-media-service
./scripts/clean-storage.sh

# Or via API
curl -X POST http://localhost:3000/api/storage/clean
```

## Monitoring

### View Logs

**Live Media Service:**
```bash
tail -f apps/live-media-service/storage/logs/combined.log
```

**STS Service:**
Logs appear directly in the terminal

**SRS:**
```bash
docker logs -f srs
```

### Check Pipeline Status

```bash
curl http://localhost:3000/api/pipeline/status | jq
```

### Monitor SRS Streams

```bash
curl http://localhost:1985/api/v1/streams/
```

## Example: Complete Workflow

Here's a complete example of setting up a Spanish-translated stream:

```bash
# 1. Start SRS
cd apps/live-media-service
./scripts/start-srs.sh

# 2. Start STS for Spanish translation
cd ../sts-service
conda activate multilingual-tts
python stream_audio_client.py --targets es --whisper-model base --device mps

# 3. Start Live Media Service
cd ../live-media-service
npm run dev

# 4. Start pipeline (from another terminal)
curl -X POST http://localhost:3000/api/pipeline/start \
  -H "Content-Type: application/json" \
  -d '{
    "sourceUrl": "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8",
    "streamId": "spanish-news",
    "bufferDuration": 15,
    "audioProcessorUrl": "http://localhost:5000"
  }'

# 5. Wait 30-45 seconds, then view output
open http://localhost:8080/players/srs_player.html?stream=spanish-news.m3u8
```

## Next Steps

- Explore different target languages
- Experiment with voice cloning (Joe Buck voice samples available)
- Adjust buffer sizes for your latency requirements
- Monitor processing metrics
- Scale up with multiple STS instances for different languages

## Additional Resources

- [STS Service README](../apps/sts-service/README.md)
- [Live Media Service README](../apps/live-media-service/README.md)
- [Async Speech-to-Speech Architecture](./ASYNC_SPEECH_TO_SPEECH.md)
- [Media Service Implementation Plan](./MEDIA_SERVICE_IMPLEMENTATION_PLAN.md)

