# STS Audio Processing Server

A real-time Speech-to-Text-to-Speech (STS) server that processes live audio streams through transcription, translation, and synthesis. Acts as a drop-in replacement for echo-audio-processor, compatible with live-media-service without requiring any changes to the media service.

## 🚀 Key Features

- **Socket.IO Server**: Compatible with live-media-service protocol
- **Sequential Processing**: Processes fragments one at a time in arrival order (FIFO)
- **Hallucination Detection**: Automatically skips corrupted/repetitive audio content
- **Optimized Performance**: Fast TTS synthesis with quality controls
- **Single Language Focus**: Optimized for one target language per server instance

## 🎯 Core Capabilities

- **Multilingual Translation**: Uses Facebook's M2M100 model for high-quality translation
- **Speaker Detection**: Automatically detects speakers from audio content
- **Adaptive Speed Control**: Adjusts TTS speed to match original audio duration exactly
- **High-Quality Audio**: Uses rubberband for professional audio processing
- **Smart Preprocessing**: Handles hyphenated words, time expressions, and abbreviations
- **Caching System**: Caches translations and audio for improved performance
- **Real-time Processing**: Processes audio fragments with precise timing alignment
- **Enhanced Transcription**: Upgraded Whisper models with domain-specific prompts and confidence scoring
- **Smart Utterance Detection**: Real-time adaptive silence detection with intelligent segment splitting
- **Voice Cloning**: XTTS-v2 voice cloning with custom voice samples
- **Silence Detection**: Automatically skips silent audio fragments
- **Memory Management**: Automatic cleanup and garbage collection
- **Model Warmup**: Pre-loads models to eliminate first-fragment latency

## 📋 Requirements

### System Dependencies
- **rubberband-cli** (required for audio speed adjustment)
  - macOS: `brew install rubberband`
  - Ubuntu/Debian: `sudo apt-get install rubberband-cli`
  - Windows: Download from [breakfastquay.com](https://breakfastquay.com/rubberband/)

### Python Dependencies
- Python 3.10+
- PyTorch
- Coqui TTS
- Transformers (M2M100)
- Audio processing libraries (sounddevice, soundfile)
- faster-whisper (for audio transcription)
- ffmpeg-python (for video file support)
- pydub (for audio mixing)

## 🛠️ Installation

### Option 1: Conda Environment (Recommended)

```bash
# Clone the repository
git clone <repository-url>
cd live-caption-test

# Install system dependency first
brew install rubberband  # macOS
# or sudo apt-get install rubberband-cli  # Linux

# Try the main environment first
conda env create -f environment.yml
conda activate multilingual-tts

# If you encounter issues, try the working environment
# conda env create -f force_working_environment.yml
# conda activate multilingual-tts

# Test installation
python test_coqui_installation.py
```

> **⚠️ Installation Issues?** If you encounter problems with `environment.yml`, try `force_working_environment.yml` which contains a known working configuration. If you see errors like "issubclass() arg 1 must be a class", see [FIX_INSTALLATION.md](FIX_INSTALLATION.md) for a quick automated fix.

### Option 2: Pip Installation

```bash
# Clone the repository
git clone <repository-url>
cd live-caption-test

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## 🎯 Usage

### Available Servers

This project provides two different server implementations:

1. **`stream_audio_client.py`** - Full-featured STS server with voice cloning and advanced features
2. **`simple_vits_server.py`** - Simplified VITS-based server for faster processing

### STS Server (Primary Use Case)

The STS server acts as a drop-in replacement for echo-audio-processor, processing live audio streams from live-media-service.

#### Quick Start

**Full STS Server (stream_audio_client.py):**
```bash
# Start STS server for Spanish translation
python stream_audio_client.py --targets es

# Start with GPU acceleration (Apple Silicon)
python stream_audio_client.py --targets es --device mps

# Start with custom configuration
python stream_audio_client.py --targets es --config coqui-voices.yaml --device mps
```

**Simple VITS Server (simple_vits_server.py):**
```bash
# Start simple server for Spanish translation
python simple_vits_server.py --targets es

# Start with GPU acceleration
python simple_vits_server.py --targets es --device mps
```

#### Complete Integration with Live-Media-Service

1. **Start the STS Server** (choose one):
   ```bash
   cd apps/sts-service
   # Option 1: Full STS server
   python stream_audio_client.py --targets es --device mps
   
   # Option 2: Simple VITS server (faster)
   python simple_vits_server.py --targets es --device mps
   ```

2. **Start Live-Media-Service** (in another terminal):
   ```bash
   cd apps/live-media-service
   npm run dev
   ```

3. **Configure Live-Media-Service**:
   - Open `http://localhost:3000`
   - Set **Audio Processor URL** to: `http://localhost:5000`
   - Set **Buffer Duration** to your desired chunk size (e.g., 15 seconds)
   - Start streaming

#### Server Configuration Options

**Full STS Server (stream_audio_client.py):**
```bash
# Basic server startup
python stream_audio_client.py --targets es

# With GPU acceleration
python stream_audio_client.py --targets es --device mps    # Apple Silicon
python stream_audio_client.py --targets es --device cuda   # NVIDIA GPU

# Custom voice configuration
python stream_audio_client.py --targets es --config custom-voices.yaml

# Disable caching (for development)
python stream_audio_client.py --targets es --no-cache

# Save processed audio locally (uses more memory)
python stream_audio_client.py --targets es --save-local

# Fast TTS mode (VITS models - much faster, no voice cloning)
python stream_audio_client.py --targets es --fast-tts

# Different Whisper model sizes
python stream_audio_client.py --targets es --whisper-model base    # Default
python stream_audio_client.py --targets es --whisper-model small   # Better accuracy
python stream_audio_client.py --targets es --whisper-model tiny    # Faster processing
```

**Simple VITS Server (simple_vits_server.py):**
```bash
# Basic server startup
python simple_vits_server.py --targets es

# With GPU acceleration
python simple_vits_server.py --targets es --device mps    # Apple Silicon
python simple_vits_server.py --targets es --device cuda   # NVIDIA GPU

# Different Whisper model sizes
python simple_vits_server.py --targets es --whisper-model base    # Default
python simple_vits_server.py --targets es --whisper-model small   # Better accuracy
python simple_vits_server.py --targets es --whisper-model tiny    # Faster processing
```

#### Supported Target Languages

Currently optimized for single-language processing. Supported languages:

- `es` - Spanish
- `fr` - French  
- `de` - German
- `it` - Italian
- `pt` - Portuguese
- `zh` - Chinese
- `ja` - Japanese
- `ko` - Korean
- `hi` - Hindi

#### TTS Performance Modes

**Full STS Server (stream_audio_client.py):**
- **Standard Mode (Default)**: Uses XTTSv2 models with voice cloning, supports custom voice samples (Joe Buck voice), higher quality but slower processing (8-16 seconds per fragment)
- **Fast TTS Mode (`--fast-tts`)**: Uses VITS models (much faster), no voice cloning (uses default voices), lower quality but significantly faster (2-5 seconds per fragment), ideal for performance testing and real-time streaming

**Simple VITS Server (simple_vits_server.py):**
- **VITS Mode Only**: Always uses VITS models for maximum speed
- No voice cloning capabilities
- Fastest processing (2-5 seconds per fragment)
- Ideal for high-throughput scenarios
- Lower memory usage
- **Duration Matching**: Uses rubberband to ensure returned audio matches original duration
- **Background Noise Preservation**: Mixes TTS audio with original background noise to maintain ambient sounds

#### Performance Optimizations

The STS server includes several optimizations:

- **Sequential Processing**: Guarantees fragments are processed and returned in arrival order
- **Hallucination Detection**: Automatically skips repetitive/corrupted audio
- **Silence Detection**: Skips silent fragments to save processing time
- **Fast TTS Synthesis**: 2.0x synthesis speed with quality controls
- **Fast TTS Mode**: VITS models for maximum speed (no voice cloning)
- **Speed Adjustment Cap**: Maximum 2.0x speed adjustment to prevent quality loss
- **Memory Management**: No file saving by default, automatic cleanup after each fragment
- **Model Warmup**: Pre-loads models to eliminate first-fragment latency

### Legacy Applications

#### VTT Processing

```bash
# Interactive mode - translate and speak text
python talk_multi_coqui.py

# Process VTT file with real-time timing
python talk_multi_coqui.py --vtt sample_vtt_files/livestream_sample.vtt

# Enable adaptive speed control for precise timing
python talk_multi_coqui.py --vtt sample_vtt_files/livestream_sample.vtt --adaptive-speed

# Multiple target languages
python talk_multi_coqui.py --targets es,fr,de --vtt sample_vtt_files/livestream_sample.vtt
```

### Audio Streaming (NEW!)

```bash
# Basic audio streaming with Spanish translation
python talk_audio_stream.py --audio path/to/audio.wav --targets es

# Video file with multiple languages and custom settings
python talk_audio_stream.py --audio video.mp4 --targets es,fr --delay 8.0 --mix-volume 0.7

# Use smaller Whisper model for faster processing
python talk_audio_stream.py --audio audio.wav --targets es --whisper-model tiny

# Create output video with mixed audio
python talk_audio_stream.py --audio input.mp4 --targets es --output dubbed_output.mp4
```

**Smart Utterance Detection Features:**
- **Adaptive Silence Detection**: Automatically adjusts to background noise levels
- **Intelligent Segment Splitting**: Splits long utterances at natural boundaries (sentences, punctuation)
- **Maximum Duration Limits**: Prevents overly long segments (8s max) for efficient processing
- **Real-time Processing**: Processes audio as it streams with minimal delay

### Enhanced Transcription Testing

```bash
# Test transcription with enhanced features (no audio synthesis)
python test_transcription.py livestream-sample/live-stream-segment-sample-audio.wav

# Use different Whisper model sizes
python test_transcription.py audio.wav --model small  # Better accuracy
python test_transcription.py audio.wav --model tiny   # Faster processing

# Test different domains
python test_transcription.py audio.wav --domain sports
python test_transcription.py audio.wav --domain news
python test_transcription.py audio.wav --domain interview

# Use GPU acceleration (if available)
python test_transcription.py audio.wav --device mps   # Apple Silicon
python test_transcription.py audio.wav --device cuda  # NVIDIA GPU

# Hide detailed results
python test_transcription.py audio.wav --no-details
```

### Translation Testing

```bash
# Test specific phrases
python test_translation.py "TEN-YARD penalty"
python test_translation.py "NOW 1:54 REMAINING"

# Interactive testing mode
python test_translation.py --interactive

# Run built-in test cases
python test_translation.py
```

## ⚙️ Configuration

Edit `coqui-voices.yaml` to configure TTS models and voices for different languages:

```yaml
languages:
  es:
    model: "tts_models/es/css10/vits"
    multi_speaker: false
  fr:
    model: "tts_models/fr/css10/vits"
    multi_speaker: false
```

## 📁 Project Structure

```
live-caption-test/
├── stream_audio_client.py       # Full STS server (primary)
├── simple_vits_server.py        # Simple VITS server (fast)
├── talk_multi_coqui.py          # Main VTT processing application
├── talk_audio_stream.py         # NEW: Audio streaming transcription
├── test_translation.py          # Translation testing tool
├── coqui-voices.yaml           # TTS model configuration
├── environment.yml              # Conda environment (primary)
├── force_working_environment.yml # Known working environment (fallback)
├── requirements.txt             # Pip requirements
├── utils/                       # Utilities
│   ├── __init__.py
│   ├── text_processing.py       # Text preprocessing
│   ├── transcription.py         # NEW: Whisper transcription
│   └── audio_streaming.py       # NEW: Audio mixing and playback
├── sample_vtt_files/            # Sample VTT files
│   ├── livestream_sample.vtt
│   ├── sample_sports_commentary.vtt
│   └── test_multi_speaker.vtt
└── livestream-sample/           # Sample audio files
    ├── live-stream-segment-sample-audio.wav
    └── live-stream-segment-sample.ts
```

## 🎵 Audio Streaming Arguments

### `talk_audio_stream.py` Options

- `--audio, -a`: Path to audio/video file (required)
- `--targets, -t`: Target languages (comma-separated, default: es)
- `--delay, -d`: Playback delay in seconds (default: 8.0)
- `--mix-volume, -v`: Volume level for translated audio 0.0-1.0 (default: 0.8)
- `--whisper-model`: Whisper model size - tiny,base,small,medium,large (default: base)
- `--device`: Device for Whisper - cpu,cuda,mps (default: cpu)
- `--output, -o`: Output video file path (optional)
- `--config, -c`: Voice configuration YAML (default: coqui-voices.yaml)
- `--no-cache`: Disable translation/TTS caching

## 🔧 Text Preprocessing

The system includes intelligent text preprocessing to improve translation quality:

- **Hyphenated Words**: "TEN-YARD" → "TEN YARD"
- **Time Expressions**: "1:54 REMAINING" → "one minutes fifty-four seconds remaining"
- **Abbreviations**: "NBA" → "N B A", "vs" → "versus"
- **Punctuation**: Cleans smart quotes, handles ellipsis, etc.

## 🎵 Audio Processing

### VTT Processing
- **High-Quality Synthesis**: Uses Coqui TTS models
- **Speed Adjustment**: Rubberband for professional time-stretching
- **Speaker-Specific Voices**: Different voices per detected speaker
- **Real-time Playback**: Synchronized with VTT timing

### Audio Streaming (NEW!)
- **Real-time Transcription**: Uses faster-whisper for streaming audio transcription
- **Delayed Playback**: Buffers audio with configurable delay for translation processing
- **Audio Mixing**: Overlays translated audio on original content
- **Video Support**: Processes video files by extracting audio track
- **Multi-threaded**: Parallel processing of transcription, translation, and TTS

## 🐛 Troubleshooting

### STS Server Issues

1. **Server won't start**: Check if port 5000 is available
   ```bash
   lsof -i :5000  # Check what's using port 5000
   ```

2. **Live-media-service can't connect**: Verify STS server is running
   ```bash
   curl http://localhost:5000  # Should return HTML page
   ```

3. **Processing too slow**: Use GPU acceleration and smaller models
   ```bash
   python stream_audio_client.py --targets es --device mps --whisper-model tiny
   ```

4. **Queue building up**: Reduce buffer duration in live-media-service or use faster processing
   - Set Buffer Duration to 10 seconds instead of 15-20 seconds
   - Use `--whisper-model tiny` for faster transcription

5. **Hallucination detection too aggressive**: Adjust thresholds in `_is_likely_hallucination()` method

6. **TTS character limit warnings**: Text truncation should prevent this, but check for very long translations

### General Issues

1. **rubberband not found**: Install rubberband-cli system package first
2. **PyTorch compatibility**: The code automatically handles PyTorch 2.6+ compatibility with Coqui TTS
3. **CUDA/GPU Issues**: Automatically falls back to CPU/MPS
4. **Audio Device Issues**: Check your audio device settings
5. **Model Download**: First run downloads models (~2-3GB)
6. **Memory Usage**: Requires 8GB+ RAM for large models
7. **faster-whisper not found**: Install with `pip install faster-whisper`
8. **ffmpeg-python not found**: Install with `pip install ffmpeg-python`
9. **Audio streaming latency**: Increase `--delay` parameter for slower systems
10. **Whisper model too slow**: Use `--whisper-model tiny` for faster processing

### Performance Tips

#### STS Server Optimization
- Use GPU acceleration: `--device mps` (Apple Silicon) or `--device cuda` (NVIDIA)
- Use smaller Whisper models: `--whisper-model tiny` for faster processing
- Reduce buffer duration in live-media-service to 10-15 seconds
- Monitor queue length in server logs - if building up, reduce processing load
- Use `--no-cache` during development, enable caching in production

#### General Optimization
- Close other applications to free up memory for large models
- Use `--adaptive-speed` for VTT files to match timing exactly
- For audio streaming: Use `--whisper-model tiny` for faster transcription
- Increase `--delay` parameter if translation/TTS can't keep up
- Smart utterance detection automatically optimizes segment lengths

## 📊 Example Output

### STS Server Processing

```
============================================================
STS Audio Processing Server
============================================================
Host: localhost
Port: 5000
Target language: es
Save locally: False
============================================================
Preloading models...
Loading Whisper model...
✓ Whisper model loaded
Loading translation model...
Loading multilingual MT (M2M100 418M) on mps…
✓ Translation model moved to MPS
✓ Translation model loaded
Loading TTS model for es...
✓ TTS model loaded for es
✓ All models preloaded successfully!
Warming up models...
✓ Whisper model warmed up
✓ Translation model warmed up
✓ TTS model warmed up
✓ All models verified and ready!
Starting STS server on localhost:5000...
✓ Server ready! Waiting for connections...

✓ Client connected: A0SbjjoE4EsBSq9DAAAB
📦 Fragment 1 Received from A0SbjjoE4EsBSq9DAAAB:
  ID: test-stream_batch-0
  Size: 164,494 bytes (160.64 KB)
  Duration: 10s
  → Added to processing queue

Processing fragment test-stream_batch-0...
Extracting audio from m4s data: 164494 bytes
✓ Audio extraction successful (Method 1)
Sending audio to Whisper: 160139 samples, 10.01s
Whisper returned 2 segments
Original speech rate: 22.3 words/second (223 words in 10.01s)
🚫 Detected repetitive text (word 'sports' appears 45/223 times)
🚫 Skipping TTS due to detected hallucination - returning original audio
✓ Sent processed fragment test-stream_batch-0 to client A0SbjjoE4EsBSq9DAAAB (processing time: 0.27s)

📦 Fragment 2 Received from A0SbjjoE4EsBSq9DAAAB:
  ID: test-stream_batch-1
  Size: 164,438 bytes (160.58 KB)
  Duration: 10s
  → Added to processing queue

Processing fragment test-stream_batch-1...
Extracting audio from m4s data: 164438 bytes
✓ Audio extraction successful (Method 1)
Sending audio to Whisper: 160139 samples, 10.01s
Whisper returned 2 segments
Original speech rate: 1.5 words/second (15 words in 10.01s)
Combined transcription: That's it off to Jacobs and he is in for Packers Touchdowns his second today.
Transcription time: 0.77s
Processing for es: That's it off to Jacobs and he is in for Packers Touchdowns his second today.
Translating text...
es: Eso es lo que pasa a Jacobs y él está en para Packers Touchdowns su segundo hoy.  (MT 0.80s)
🚀 Fast TTS Synthesis with speed=2.0x
Using voice cloning with sample: ./voice_samples/joe_buck_voice_sample.wav
  Baseline TTS duration: 5.20s
  Required speed adjustment: 1.00x
  → No speed adjustment needed (TTS duration already matches)
TTS 6.64s
✓ Sent processed fragment test-stream_batch-1 to client A0SbjjoE4EsBSq9DAAAB (processing time: 8.57s)
```

### VTT Processing
```
Segment 14/18: NOW 1:54 REMAINING
Speaker: default
es: Ahora un minuto cincuenta y cuatro segundos restantes  (MT 0.91s; src=en)
Using voice: tts_models/es/css10/vits (single-speaker) for default
 > Text splitted to sentences.
['Ahora un minuto cincuenta y cuatro segundos restantes']
 > Processing time: 0.252547025680542
 > Real-time factor: 0.07273591844639435
TTS 0.26s → playing es…
```

### Audio Streaming (NEW!)
```
Processing audio file: livestream-sample/live-stream-segment-sample-audio.wav
Target languages: es
Delay: 8.0s, Mix volume: 0.8
Loaded audio: 60.0s at 16000Hz
Starting transcription...
Transcribing chunk: 0.0s - 5.0s
Transcribed: On Detroit side of the 50.
Time: 0.0s - 2.5s
Processing segment: On Detroit side of the 50.
Speaker: default
es: En el lado de Detroit de los cincuenta.  (MT 0.85s)
TTS 0.12s → adding to audio queue
Added es audio to mixer at 0.0s
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Coqui TTS](https://github.com/coqui-ai/TTS) for high-quality text-to-speech
- [Facebook M2M100](https://github.com/facebookresearch/fairseq) for multilingual translation
- [Rubberband](https://breakfastquay.com/rubberband/) for audio processing
