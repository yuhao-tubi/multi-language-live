# Live Multilingual Audio

A real-time multilingual text-to-speech system with speaker detection and adaptive speed control for VTT files and audio/video streaming. This tool translates live captions/subtitles and synthesizes them with high-quality audio using Coqui TTS and M2M100 translation models.

## 🚀 Features

- **Multilingual Translation**: Uses Facebook's M2M100 model for high-quality translation
- **Speaker Detection**: Automatically detects speakers from VTT files (CAPS names)
- **Adaptive Speed Control**: Adjusts TTS speed to match VTT timing exactly
- **High-Quality Audio**: Uses rubberband for professional audio processing
- **Smart Preprocessing**: Handles hyphenated words, time expressions, and abbreviations
- **Caching System**: Caches translations and audio for improved performance
- **Real-time Processing**: Processes VTT files with precise timing alignment
- **Audio Streaming**: Real-time transcription of audio/video files with delayed playback
- **Audio Mixing**: Overlay translated audio on original content with volume control
- **Enhanced Transcription**: Upgraded Whisper models with domain-specific prompts and confidence scoring
- **Smart Utterance Detection**: Real-time adaptive silence detection with intelligent segment splitting
- **Voice Cloning**: XTTS-v2 voice cloning with custom voice samples

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

# Create and activate conda environment
conda env create -f environment.yml
conda activate multilingual-tts

# Test installation
python test_coqui_installation.py
```

> **⚠️ Installation Issues?** If you see errors like "issubclass() arg 1 must be a class", see [FIX_INSTALLATION.md](FIX_INSTALLATION.md) for a quick automated fix.

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

### Main Application

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
├── talk_multi_coqui.py          # Main VTT processing application
├── talk_audio_stream.py         # NEW: Audio streaming transcription
├── test_translation.py          # Translation testing tool
├── coqui-voices.yaml           # TTS model configuration
├── environment.yml              # Conda environment
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

### Common Issues

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

- Use `--no-cache` to disable caching during development
- Enable `--adaptive-speed` for VTT files to match timing exactly
- Close other applications to free up memory for large models
- For audio streaming: Use `--whisper-model tiny` for faster transcription
- Increase `--delay` parameter if translation/TTS can't keep up
- Smart utterance detection automatically optimizes segment lengths

## 📊 Example Output

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
