# Live Audio Stream Client

A Python client that connects to the mock-media-service via Socket.IO, receives live audio fragments, processes them through the full STS pipeline (transcribe → translate → synthesize), and sends back processed audio.

## Features

- **Real-time Processing**: Processes each audio fragment as it arrives
- **Full STS Pipeline**: Transcribe → Translate → Synthesize → Send back
- **Model Verification**: Ensures all models are loaded and ready before processing
- **Clean Output**: Simple print statements that don't interfere with mock server terminal
- **Local Saving**: Optional saving of processed fragments with metadata
- **Error Handling**: Comprehensive error handling and graceful shutdown

## Installation

1. Update the conda environment to include the Socket.IO client:
```bash
conda env update -f environment.yml
```

2. Ensure all dependencies are installed:
```bash
conda activate multilingual-tts
```

## Usage

### Option 1: Separate Terminal Windows (Recommended)

```bash
# Terminal 1: Start mock-media-service in separate terminal
cd apps/sts-service
./start_service_terminal.sh

# Terminal 2: Run stream client (clean output)
cd apps/sts-service
python stream_audio_client.py --stream-id stream-1 --targets es --save-local
```

### Option 2: Background Service (Output Redirected)

```bash
# Terminal 1: Start mock-media-service in background
cd apps/sts-service
./test_stream_client.sh start-service

# Terminal 2: Run stream client
cd apps/sts-service
python stream_audio_client.py --stream-id stream-1 --targets es --save-local

# Clean up when done
./test_stream_client.sh stop-service
```

### Option 3: Manual Setup

```bash
# Terminal 1: Start mock-media-service
npx nx serve mock-media-service

# Terminal 2: Run stream client
cd apps/sts-service
python stream_audio_client.py --stream-id stream-1 --targets es --save-local
```

### Using Test Helper

```bash
cd apps/sts-service

# Check environment and dependencies
./test_stream_client.sh check

# Run full test (check + start service + run client)
./test_stream_client.sh test

# Run specific test
./test_stream_client.sh run stream-1 es true
```

## Command Line Arguments

- `--server-url`: Socket.IO server URL (default: `ws://localhost:4000`)
- `--stream-id`: Stream ID to subscribe to (default: `stream-1`)
- `--targets`: Target languages comma-separated (default: `es`)
- `--config`: Voice configuration YAML (default: `coqui-voices.yaml`)
- `--save-local`: Flag to save processed fragments locally
- `--output-dir`: Directory for saved fragments (default: `./processed_fragments`)
- `--whisper-model`: Whisper model size (default: `base`)
- `--device`: Processing device (default: `cpu`)
- `--no-cache`: Disable caching

## Model Loading and Verification

The client ensures all models are loaded and ready before starting:

1. **Whisper Model**: Loads the specified Whisper model for transcription
2. **Translation Model**: Loads M2M100 for text translation
3. **TTS Models**: Loads Coqui TTS models for each target language
4. **Model Verification**: Tests each model with sample data to ensure they're working

## Output

When `--save-local` is enabled, processed fragments are saved to:
```
{output_dir}/{stream_id}/{target_lang}/
├── fragment-0.m4s
├── fragment-0.json
├── fragment-1.m4s
├── fragment-1.json
└── ...
```

Each JSON file contains metadata about the processing:
```json
{
  "fragment_id": "stream-1-0",
  "sequence_number": 0,
  "target_language": "es",
  "processed_at": 1234567890.123,
  "original_metadata": { ... },
  "file_size": 12345
}
```

## Protocol Compliance

The client follows the mock-media-service protocol exactly:

- Connects via Socket.IO to `ws://localhost:4000`
- Subscribes to streams with `subscribe` event
- Receives `fragment:data` events with m4s audio + metadata
- Acknowledges fragments with `fragment:ack` event
- Sends processed audio back via `fragment:processed` event
- Handles `stream:complete` and disconnects gracefully

## Current Limitations

### **m4s Audio Parsing**
- **Current Status**: ✅ Implemented proper m4s/MP4 audio extraction using ffmpeg-python
- **Method**: Saves m4s data to temporary file and extracts audio using ffmpeg
- **Fallback**: Uses test audio signal if extraction fails
- **Result**: Now processes actual speech content from m4s fragments

### **Expected Behavior**
- Client receives m4s fragments and acknowledges them immediately ✅
- **Extracts actual speech audio from m4s files** ✅
- **Transcribes real speech content** ✅
- Translation and TTS synthesis work correctly ✅
- Processed audio is sent back to server ✅
- Local saving works correctly ✅

## Troubleshooting

### Model Loading Issues
- Ensure all models are downloaded (first run downloads ~2-3GB)
- Check available memory (requires 8GB+ RAM for large models)
- Use smaller Whisper model: `--whisper-model tiny`

### Connection Issues
- Verify mock-media-service is running: `curl http://localhost:4000/`
- Check available streams: `curl http://localhost:4000/streams`
- Ensure no firewall blocking port 4000

### Processing Issues
- Check voice configuration in `coqui-voices.yaml`
- Verify target languages are configured
- Use `--no-cache` to disable caching during development

## Example Output

```
============================================================
Live Audio Stream Processing Client
============================================================
Server URL: ws://localhost:4000
Stream ID: stream-1
Target languages: es
Save locally: True
Output directory: ./processed_fragments
============================================================
Preloading models...
Loading Whisper model...
✓ Whisper model loaded
Loading translation model...
✓ Translation model loaded
Loading TTS models...
Loading TTS model for es: tts_models/es/css10/vits
✓ TTS model loaded for es
✓ All models preloaded successfully!
Verifying models are ready...
✓ Whisper model verified
✓ Translation model verified
✓ TTS model verified for es
✓ All models verified and ready!
Connecting to ws://localhost:4000...
✓ Connected to server: ws://localhost:4000
Socket ID: abc123
→ Subscribing to stream: stream-1
✓ Successfully subscribed to stream: stream-1
Waiting for fragments...

📦 Fragment 1 Received:
  ID: stream-1-0
  Sequence: 0
  Size: 12,345 bytes (12.06 KB)
  Codec: aac
  Sample Rate: 44100 Hz
  Channels: 2
  Duration: 15000ms
  ✓ Acknowledged
Processing fragment 0...
Transcribed: Hello world
Transcription time: 0.45s
Processing for es: Hello world
Speaker: default
es: Hola mundo  (MT 0.85s)
TTS 0.12s
✓ Sent processed fragment 0
Saved: ./processed_fragments/stream-1/es/fragment-0.m4s
```
