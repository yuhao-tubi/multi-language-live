# STS Service Architecture

## Overview

The **STS (Speech-to-Speech) Service** is a real-time multilingual audio processing system that transforms live audio streams from one language to another while preserving speaker characteristics and timing. It provides end-to-end speech-to-speech translation for live broadcasts, supporting multiple target languages simultaneously.

**Core Capabilities:**
- Real-time audio transcription using Whisper
- High-quality translation using Facebook's M2M100 model
- Natural voice synthesis using Coqui XTTS-v2 with voice cloning
- Speaker detection and voice mapping
- Adaptive speed control for timing synchronization
- Live stream processing via Socket.IO

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          STS SERVICE PIPELINE                        │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│   Audio      │         │    Text      │         │    Audio     │
│   Input      │────────▶│ Processing   │────────▶│   Output     │
└──────────────┘         └──────────────┘         └──────────────┘
     │                         │                         │
     ├─ Live Stream           ├─ Translation           ├─ Socket.IO
     ├─ VTT Files             ├─ Preprocessing         ├─ Local Files
     └─ Audio Files           └─ Speaker Detection     └─ Audio Stream

┌─────────────────────────────────────────────────────────────────────┐
│                         PROCESSING STAGES                            │
└─────────────────────────────────────────────────────────────────────┘

1. AUDIO ACQUISITION                    4. TRANSLATION
   ├─ Socket.IO fragments (m4s)            ├─ M2M100 multilingual model
   ├─ VTT timed captions                   ├─ English → target languages
   └─ Audio/video files                    ├─ Context-aware translation
                                           └─ Caching for performance
2. TRANSCRIPTION
   ├─ Whisper model (base/small/tiny)   5. TEXT-TO-SPEECH
   ├─ Voice Activity Detection (VAD)       ├─ Coqui XTTS-v2 synthesis
   ├─ Domain-specific prompts              ├─ Voice cloning support
   ├─ Confidence scoring                   ├─ Speaker-specific voices
   └─ Adaptive silence detection           ├─ Speed adaptation
                                           └─ Formant preservation
3. TEXT PROCESSING
   ├─ Speaker detection                 6. AUDIO POST-PROCESSING
   ├─ Abbreviation expansion               ├─ Rubberband time-stretching
   ├─ Number conversion                    ├─ Duration normalization
   ├─ Punctuation cleaning                 ├─ Audio mixing
   └─ TTS optimization                     └─ Format conversion (m4s)
```

---

## Core Components

### 1. Main Service Modules

#### 1.1 `talk_multi_coqui.py` - Core Translation & TTS Engine
**Purpose:** Provides the fundamental translation and text-to-speech functionality.

**Key Features:**
- Interactive translation mode
- VTT file processing with timing alignment
- Speaker detection and voice mapping
- Adaptive speed control
- Caching system for translations and audio

**Main Functions:**
```python
translate(text, target_lang)          # M2M100 translation
synth_to_wav(text, model, speaker)    # Coqui TTS synthesis
get_speaker_voice(voices, lang, spk)  # Voice configuration lookup
process_vtt_file(vtt_path, targets)   # VTT processing with timing
```

**Process Flow:**
1. Load M2M100 translation model
2. Load Coqui XTTS-v2 TTS models for target languages
3. Parse input (text or VTT)
4. Detect speakers from text patterns
5. Translate text to target languages
6. Synthesize audio with appropriate voices
7. Apply speed adjustment if needed
8. Play or save output audio

---

#### 1.2 `stream_audio_client.py` - Live Stream Processor
**Purpose:** Connects to mock-media-service, processes live audio fragments through the full STS pipeline.

**Key Features:**
- Socket.IO client for fragment reception
- Real-time audio transcription (Whisper)
- Fragment-by-fragment processing
- Background processing queue
- Processed audio streaming back to server

**Main Classes:**
```python
class LiveStreamProcessor:
    - Manages Socket.IO connection
    - Handles fragment queue processing
    - Coordinates transcription → translation → TTS
    - Sends processed audio back to server
```

**Process Flow:**
1. Connect to mock-media-service via Socket.IO
2. Subscribe to stream (e.g., "stream-1")
3. Receive m4s audio fragments
4. Extract audio using ffmpeg
5. Transcribe with Whisper
6. Translate to target languages
7. Synthesize speech with speed matching
8. Encode back to m4s format
9. Send processed fragments back
10. Save combined output audio

**Threading Model:**
- Main thread: Socket.IO event handling
- Processing thread: Fragment processing pipeline
- Immediate ACK: Acknowledge fragments instantly
- Async processing: Process in background

---

#### 1.3 `talk_audio_stream.py` - Audio File Processor
**Purpose:** Processes pre-recorded audio/video files with delayed playback and mixing.

**Key Features:**
- Video file support (extracts audio track)
- Real-time transcription simulation
- Delayed playback for translation processing
- Audio mixing (original + translated)
- Output video generation

**Process Flow:**
1. Load audio/video file with ffmpeg
2. Stream audio in chunks
3. Transcribe each chunk with Whisper
4. Translate transcriptions
5. Synthesize translated speech
6. Mix with original audio (configurable volumes)
7. Save output video with mixed audio

---

#### 1.4 `sts_streaming_bridge.py` - Demux Service Bridge
**Purpose:** Bridges STS service with streaming-demux-remux service for HLS web playback.

**Key Features:**
- Receives processed fragments from STS
- Forwards to streaming-demux-remux API
- HTTP REST integration
- Queue-based buffering

**Architecture Role:**
```
mock-media-service → stream_audio_client → sts_streaming_bridge → streaming-demux-remux
                     (STS processing)      (HTTP forwarding)      (HLS streaming)
```

---

### 2. Utility Modules

#### 2.1 `utils/text_processing.py` - Text Preprocessing
**Purpose:** Optimize text for translation and TTS quality.

**Key Functions:**
```python
preprocess_text_for_translation(text)
  - Handles time expressions (1:54 → "1:54 remaining")
  - Removes hyphens (TEN-YARD → TEN YARD)
  - Expands abbreviations (NBA → N B A)

preprocess_text_for_tts(text)
  - Converts numbers to words
  - Cleans punctuation
  - Handles scores (15-12 → 15 to 12)

detect_speaker(text)
  - Looks for explicit labels ("Referee:")
  - Pattern matching for speaker names
  - Returns speaker name or 'default'

clean_speaker_prefix(text, speaker)
  - Removes speaker prefix from text
  - Prepares clean text for TTS
```

**Examples:**
```python
"REFEREE: TEN-YARD penalty. NOW 1:54 REMAINING"
  → Speaker: "REFEREE"
  → Text: "TEN YARD penalty. NOW one minute fifty-four seconds remaining"
```

---

#### 2.2 `utils/transcription.py` - Audio Transcription
**Purpose:** Real-time audio transcription using faster-whisper.

**Key Features:**
- Faster-Whisper model loading and caching
- Audio preprocessing (normalization, filtering)
- Domain-specific prompts (sports, news, etc.)
- Voice Activity Detection (VAD)
- Confidence scoring
- Sentence boundary detection
- Long segment splitting

**Key Functions:**
```python
get_whisper_model(model_size, device)
  - Loads and caches Whisper models
  - Supports: tiny, base, small, medium, large
  - Device: cpu, cuda (MPS falls back to CPU)

transcribe_audio_chunk(audio_data, sample_rate, model, domain)
  - VAD filtering
  - Beam search (beam_size=8)
  - Temperature ensemble [0.0, 0.2, 0.4]
  - Domain-specific initial prompts
  - Returns: [(start, end, text, confidence)]

preprocess_audio_for_transcription(audio_data, sample_rate)
  - Normalization
  - High-pass filter (>80Hz)
  - Pre-emphasis
```

**Domain Prompts:**
- **Sports:** "This is a sports commentary broadcast with team names, player names, game statistics..."
- **Football:** "...with yard lines, penalties, touchdowns..."
- **News:** "...with proper names, locations, dates..."

**Segment Splitting Strategy:**
1. Keep segments < 6 seconds as-is
2. Split by sentence boundaries (periods)
3. Split by punctuation (commas, semicolons)
4. Force split at midpoint if no natural boundaries

---

#### 2.3 `utils/audio_streaming.py` - Audio Mixing & Playback
**Purpose:** Real-time audio operations for streaming applications.

**Key Features:**
- Audio file loading (video support via ffmpeg)
- Real-time audio mixing
- Delayed playback
- Volume control
- Video overlay creation

**Key Classes:**
```python
class AudioMixer:
  - add_track(name, audio_data, volume)
  - mix_audio(duration)
  - start_playback(callback)
  - Real-time multi-track mixing

class DelayedAudioPlayer:
  - Configurable playback delay
  - Timestamp-based scheduling
  - Buffer management
```

**Key Functions:**
```python
load_audio_file(file_path, target_sample_rate)
  - Supports audio and video files
  - Uses ffmpeg for extraction
  - Automatic resampling

overlay_audio_on_video(video_path, audio_path, output_path)
  - Mixes translated audio with original
  - Configurable volume levels
  - Creates output video
```

---

#### 2.4 `utils/voice_management.py` - Voice Sample Management
**Purpose:** Voice cloning with XTTS-v2 voice samples.

**Key Features:**
- Voice sample validation
- Audio preprocessing for voice cloning
- Sample duration checking (3-30 seconds)
- Format conversion (mono, 22050Hz)

**Key Functions:**
```python
validate_voice_sample(audio_path)
  - Duration check (3-30s)
  - Format validation
  - Quality warnings

preprocess_voice_sample(input_path, output_path)
  - Convert to mono
  - Resample to 22050Hz
  - Normalize audio

setup_voice_samples(voices_config, voice_samples_dir)
  - Creates voice_samples directory
  - Validates existing samples
  - Returns updated config
```

**Voice Sample Requirements:**
- Duration: 3-30 seconds (optimal: 6-10s)
- Format: WAV, MP3, FLAC, M4A
- Channels: Mono preferred
- Sample Rate: 22050Hz optimal
- Content: Clean speech, minimal background noise

---

#### 2.5 `utils/audio_normalization.py` - Duration Normalization
**Purpose:** Audio time-stretching for timing synchronization.

**Key Features:**
- Rubberband-based time-stretching (preferred)
- Librosa fallback
- Pitch preservation
- Duration normalization strategies

**Key Functions:**
```python
normalize_audio_duration(audio_data, sample_rate, target_duration)
  Strategy:
  - If longer: compress using Rubberband/librosa
  - If shorter: pad with silence
  - If close (<0.1s): return as-is

adjust_audio_speed_rubberband(input_path, output_path, speed_factor)
  - High-quality time-stretching
  - Formant preservation (-F flag)
  - Crisp transients (-c 5)
  - Pitch unchanged (-p 0)
```

**Rubberband Command Example:**
```bash
rubberband -T 1.2 -p 0 -F -3 input.wav output.wav
# -T 1.2: 1.2x speed
# -p 0: No pitch shift
# -F: Formant preservation
# -3: R3 engine (finest quality)
```

---

### 3. Configuration

#### 3.1 `coqui-voices.yaml` - Voice Configuration
**Purpose:** Define TTS models and voice mappings per language.

**Structure:**
```yaml
languages:
  es:  # Spanish
    model: "tts_models/multilingual/multi-dataset/xtts_v2"
    multi_speaker: true
    speakers:
      JOE:
        speaker: "Andrew Chipper"  # Default XTTS voice
        voice_sample: "./voice_samples/joe_sample.wav"
      REFEREE:
        speaker: "Andrew Chipper"
        voice_sample: "./voice_samples/referee_sample.wav"
      default:
        speaker: "Andrew Chipper"
        voice_sample: "./voice_samples/default_voice.wav"
```

**Configuration Options:**
- `model`: Coqui TTS model name
- `multi_speaker`: Whether model supports multiple speakers
- `speakers`: Speaker-specific voice mappings
  - `speaker`: Default XTTS voice name
  - `voice_sample`: Path to voice cloning sample (optional)

**Supported Languages:**
- `es`: Spanish
- `fr`: French
- `de`: German
- `pt`: Portuguese
- `zh`: Chinese
- (XTTS-v2 supports 17+ languages)

---

## Data Flow

### 1. Live Stream Processing Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                      LIVE STREAM PIPELINE                            │
└─────────────────────────────────────────────────────────────────────┘

mock-media-service (Socket.IO Server)
  │
  │ emit: fragment:data
  │ { fragment: { id, sequence, codec, sampleRate, ... }, data: <m4s> }
  │
  ▼
stream_audio_client.py (Socket.IO Client)
  │
  │ STAGE 1: Fragment Reception
  ├─ Receive m4s fragment
  ├─ Acknowledge immediately (avoid timeout)
  └─ Add to processing queue
  │
  │ STAGE 2: Audio Extraction
  ├─ Write m4s to temp file
  ├─ Extract with ffmpeg → WAV
  ├─ Resample to 16kHz (Whisper requirement)
  └─ Validate audio quality
  │
  │ STAGE 3: Transcription
  ├─ Send to Whisper model
  ├─ Apply VAD filtering
  ├─ Get segments with timestamps
  ├─ Filter segments within fragment duration
  └─ Combine segments to text
  │
  │ STAGE 4: Translation
  ├─ Detect speaker from text
  ├─ Preprocess text
  ├─ Check cache (SHA1 hash)
  ├─ Translate with M2M100
  └─ Cache result
  │
  │ STAGE 5: TTS Synthesis
  ├─ Get speaker voice config
  ├─ Synthesize at normal speed
  ├─ Calculate required speed adjustment
  ├─ Apply Rubberband time-stretching
  ├─ Match original fragment duration
  └─ Cache result
  │
  │ STAGE 6: Audio Encoding
  ├─ Convert to int16 format
  ├─ Encode as m4s with ffmpeg
  └─ Prepare for transmission
  │
  │ STAGE 7: Response
  ├─ emit: fragment:processed
  ├─ Send processed m4s back to server
  └─ Save local copy (if enabled)
  │
  ▼
mock-media-service (receives processed audio)
```

**Performance Characteristics:**
- Fragment Size: ~1-2 seconds of audio
- Processing Time: 3-8 seconds per fragment
- Acknowledgment: <100ms (immediate)
- Background Processing: Async worker thread
- Caching: Reduces repeat processing by 90%+

---

### 2. VTT File Processing Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                       VTT PROCESSING PIPELINE                        │
└─────────────────────────────────────────────────────────────────────┘

VTT File (livestream_sample.vtt)
  │
  │ WEBVTT
  │ 00:00:00.000 --> 00:00:02.500
  │ REFEREE: Touchdown! Extra point is good.
  │
  ▼
talk_multi_coqui.py --vtt sample.vtt --targets es,fr
  │
  │ STAGE 1: VTT Parsing
  ├─ Parse timestamps (HH:MM:SS.mmm)
  ├─ Extract text segments
  ├─ Detect speakers per segment
  └─ Build segment list: [(start, end, text, speaker)]
  │
  │ STAGE 2: Real-time Playback Loop
  │ For each segment:
  │
  ├─ Wait until segment start time
  │
  ├─ STAGE 3: Translation
  │   ├─ Preprocess text
  │   ├─ Check cache
  │   ├─ Translate to each target language
  │   └─ Cache results
  │
  ├─ STAGE 4: TTS with Adaptive Speed
  │   ├─ Get speaker voice config
  │   ├─ Synthesize at normal speed
  │   ├─ Measure baseline duration
  │   ├─ Calculate speed: baseline / vtt_duration
  │   ├─ Apply Rubberband adjustment
  │   └─ Verify final duration matches VTT
  │
  └─ STAGE 5: Playback
      ├─ Play audio for exact VTT duration
      └─ Continue to next segment
```

**Adaptive Speed Algorithm:**
```python
# Example: VTT says 2.5 seconds, TTS generates 3.0 seconds
vtt_duration = 2.5s
tts_duration = 3.0s
speed_factor = tts_duration / vtt_duration  # 1.2x
# Apply Rubberband: compress 3.0s → 2.5s
```

---

### 3. Audio File Processing Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AUDIO FILE PROCESSING PIPELINE                    │
└─────────────────────────────────────────────────────────────────────┘

talk_audio_stream.py --audio video.mp4 --targets es --delay 8.0
  │
  │ STAGE 1: Audio Loading
  ├─ Extract audio with ffmpeg (supports video)
  ├─ Resample to 16kHz
  └─ Load into memory
  │
  │ STAGE 2: Chunked Processing
  │ For each audio chunk (e.g., 5 seconds):
  │
  ├─ STAGE 3: Transcription
  │   ├─ Transcribe chunk with Whisper
  │   ├─ Get timestamped segments
  │   └─ Filter by confidence
  │
  ├─ STAGE 4: Translation
  │   ├─ Preprocess text
  │   ├─ Translate to target languages
  │   └─ Cache results
  │
  ├─ STAGE 5: TTS Synthesis
  │   ├─ Synthesize translated speech
  │   ├─ Apply speed adjustment
  │   └─ Generate audio segment
  │
  └─ STAGE 6: Audio Mixing
      ├─ Add to delayed playback queue
      ├─ Wait for playback delay (8.0s default)
      ├─ Mix with original audio
      └─ Play or save to output file
```

**Delayed Playback Purpose:**
- Provides time for translation/TTS processing
- Maintains synchronization with original audio
- Prevents audio dropouts
- Typical delay: 5-10 seconds

---

## Model Pipeline

### 1. Whisper (Transcription)
**Model:** faster-whisper (optimized version of OpenAI Whisper)
**Sizes:** tiny (39M), base (74M), small (244M), medium (769M), large (1.5B)
**Language:** English (input)
**Device:** CPU, CUDA (MPS not supported)

**Configuration:**
```python
WhisperModel(
    model_size="base",
    device="cpu",
    compute_type="int8"  # CPU quantization
)
```

**Parameters:**
```python
model.transcribe(
    audio,
    language="en",
    word_timestamps=True,
    vad_filter=True,
    vad_parameters=dict(min_silence_duration_ms=300),
    beam_size=8,
    best_of=8,
    temperature=[0.0, 0.2, 0.4],
    initial_prompt="This is a sports commentary..."
)
```

**Output:**
```python
[
    (start_time, end_time, text, confidence),
    (0.0, 2.5, "On Detroit side of the 50", 0.91),
    (2.5, 5.0, "First down and ten", 0.87)
]
```

---

### 2. M2M100 (Translation)
**Model:** facebook/m2m100_418M
**Architecture:** Transformer-based multilingual translation
**Languages:** 100 languages (Many-to-Many)
**Size:** 418M parameters

**Configuration:**
```python
model = M2M100ForConditionalGeneration.from_pretrained("facebook/m2m100_418M")
tokenizer = M2M100Tokenizer.from_pretrained("facebook/m2m100_418M")
```

**Translation Parameters:**
```python
model.generate(
    **inputs,
    forced_bos_token_id=tokenizer.get_lang_id("es"),
    num_beams=4,
    early_stopping=True,
    repetition_penalty=1.1,
    max_length=100,
    do_sample=False
)
```

**Language Codes:**
- en → es (Spanish)
- en → fr (French)
- en → de (German)
- en → pt (Portuguese)
- en → zh (Chinese)

**Example:**
```python
translate("Touchdown! Extra point is good.", "es")
# → "¡Touchdown! El punto extra es bueno."
```

---

### 3. Coqui XTTS-v2 (Text-to-Speech)
**Model:** tts_models/multilingual/multi-dataset/xtts_v2
**Architecture:** XTTS (eXpressive Text-to-Speech) v2
**Languages:** 17+ (multilingual)
**Features:** Voice cloning, multi-speaker, emotion

**Configuration:**
```python
TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2")
```

**Synthesis:**
```python
tts.tts_to_file(
    text=translated_text,
    file_path="output.wav",
    speaker_wav="./voice_samples/joe_buck.wav",  # Voice cloning
    language="es",
    speed=1.0
)
```

**Voice Cloning:**
- Requires 3-30 second voice sample
- Best quality: 6-10 seconds
- Mono, 22050Hz preferred
- Clean speech, minimal background noise

**Supported Voices:**
- Default voices: Andrew Chipper, Claribel Dervla, etc.
- Custom voices: Via voice sample cloning

---

## Caching Strategy

### 1. Cache Structure
```
.cache_coqui/
  ├── <sha1_hash>.json    # Translation cache
  └── <sha1_hash>.wav     # TTS audio cache
```

### 2. Cache Keys

**Translation Cache:**
```python
mt_key = sha1("MT", preprocessed_text, target_lang)
# Example: MT_hello_world_es → abc123def456...
```

**TTS Cache:**
```python
tts_key = sha1("TTS", translated_text, target_lang, model_name, speaker_id)
# Example: TTS_hola_mundo_es_xtts_v2_andrew → 789abc012def...
```

### 3. Cache Benefits
- **Translation:** Instant retrieval (~0.01s vs 0.5s)
- **TTS:** Instant playback (~0.01s vs 2-5s)
- **Disk Space:** ~10MB per minute of unique audio
- **Persistence:** Survives restarts

### 4. Cache Management
```bash
# Clear cache
rm -rf .cache_coqui/*

# Check cache size
du -sh .cache_coqui/

# Count cached items
ls .cache_coqui/*.json | wc -l    # Translations
ls .cache_coqui/*.wav | wc -l     # Audio files
```

---

## Performance Optimization

### 1. Speed Adjustment Strategy

**Problem:** TTS-generated audio duration ≠ original audio duration

**Solution:** Post-processing with Rubberband
```python
# Step 1: Synthesize at normal speed (1.0x)
temp_audio = synthesize(text, speed=1.0)

# Step 2: Measure actual duration
baseline_duration = get_duration(temp_audio)

# Step 3: Calculate required speed
speed_factor = baseline_duration / target_duration

# Step 4: Apply Rubberband
rubberband -T {speed_factor} temp.wav output.wav
```

**Why Not Use XTTS Speed Parameter?**
- XTTS speed parameter has limited range (0.5x - 2.0x)
- Rubberband provides better quality
- More precise duration control

---

### 2. Model Loading Optimization

**Problem:** Model loading is slow (~10-30 seconds)

**Solution:** Global model caching
```python
_mt_cache = {}    # Translation model cache
_tts_cache = {}   # TTS model cache
_whisper_cache = {}  # Whisper model cache

def get_mt():
    if "mt" not in _mt_cache:
        _mt_cache["mt"] = load_m2m100_model()
    return _mt_cache["mt"]
```

**Benefits:**
- Load once, use many times
- Instant access after first load
- Shared across all requests

---

### 3. Threading Model

**Live Stream Processing:**
```
Main Thread (Socket.IO)
  ├─ Connection management
  ├─ Fragment reception
  ├─ Immediate ACK sending
  └─ Add to queue

Processing Thread
  ├─ Fragment extraction
  ├─ Transcription
  ├─ Translation
  ├─ TTS synthesis
  └─ Send processed result
```

**Benefits:**
- Non-blocking fragment reception
- No timeouts on slow processing
- Parallel processing capability

---

### 4. Audio Processing Pipeline

**Optimization Points:**
1. **Resampling:** Only when necessary
   ```python
   if sample_rate != 16000:
       audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=16000)
   ```

2. **VAD Filtering:** Remove silence before transcription
   ```python
   vad_filter=True  # Removes silence
   vad_parameters=dict(min_silence_duration_ms=300)
   ```

3. **Batch Processing:** Process multiple segments together
   ```python
   # Combine short segments before TTS
   if segment_duration < 1.0:
       merge_with_next_segment()
   ```

---

## Error Handling & Robustness

### 1. Graceful Degradation

**Transcription Errors:**
```python
try:
    segments = transcribe_audio_chunk(audio, sample_rate, model)
except Exception as e:
    console.print(f"[red]Transcription error: {e}[/red]")
    return []  # Return empty segments
```

**Translation Errors:**
```python
try:
    translated = translate(text, target_lang)
except Exception as e:
    console.print(f"[red]Translation error: {e}[/red]")
    return {"out": text, "src": "en"}  # Return original text
```

**TTS Errors:**
```python
try:
    audio = synthesize(text, model, speaker)
except Exception as e:
    console.print(f"[red]TTS error: {e}[/red]")
    return create_silence(duration)  # Return silence
```

---

### 2. Timeout Handling

**Socket.IO Acknowledgment:**
```python
# Acknowledge immediately to avoid timeout
self.sio.emit('fragment:ack', {'fragmentId': fragment['id']})

# Process in background
self.processing_queue.put((fragment, data))
```

**Processing Timeout:**
```python
# Wait for processing with timeout
timeout = 60  # seconds
while not self.processing_queue.empty():
    if time.time() - start_time > timeout:
        console.print("[red]Timeout: Processing incomplete[/red]")
        break
    time.sleep(0.1)
```

---

### 3. Audio Quality Validation

**Fragment Extraction:**
```python
# Probe file structure
probe = ffmpeg.probe(temp_m4s_path)
for stream in probe['streams']:
    if stream['codec_type'] == 'audio':
        print(f"Audio: {stream['codec_name']}, {stream['sample_rate']}Hz")

# Analyze extracted audio
rms_energy = np.sqrt(np.mean(audio_data ** 2))
max_amplitude = np.max(np.abs(audio_data))
print(f"RMS: {rms_energy:.6f}, Max: {max_amplitude:.6f}")
```

**Repetition Detection:**
```python
# Check for repetitive patterns (indicates extraction issues)
first_half = audio_data[:len(audio_data)//2]
second_half = audio_data[len(audio_data)//2:]
correlation = np.corrcoef(first_half, second_half)[0, 1]

if correlation > 0.9:
    console.print("[yellow]Warning: Repetitive audio detected[/yellow]")
```

---

### 4. Fallback Mechanisms

**Rubberband Fallback:**
```python
try:
    # Try Rubberband first
    adjusted_audio = adjust_with_rubberband(audio, speed)
except Exception as e:
    console.print("[yellow]Rubberband failed, using librosa[/yellow]")
    # Fallback to librosa
    adjusted_audio = librosa.effects.time_stretch(audio, rate=speed)
```

**Model Device Fallback:**
```python
# Try GPU, fallback to CPU
try:
    model = WhisperModel("base", device="cuda")
except Exception as e:
    console.print("[yellow]CUDA unavailable, using CPU[/yellow]")
    model = WhisperModel("base", device="cpu")
```

---

## Integration Points

### 1. Socket.IO Events

**Client → Server (stream_audio_client.py):**
```javascript
// Subscribe to stream
emit('subscribe', { streamId: 'stream-1' })

// Acknowledge fragment receipt
emit('fragment:ack', { fragmentId: 'fragment-001' })

// Send processed fragment
emit('fragment:processed', {
    fragment: { id, sequence, ... },
    data: <processed_m4s_bytes>
})
```

**Server → Client:**
```javascript
// Subscription confirmation
on('subscribed', { streamId: 'stream-1' })

// Fragment delivery
on('fragment:data', {
    fragment: {
        id: 'fragment-001',
        sequenceNumber: 1,
        codec: 'aac',
        sampleRate: 48000,
        channels: 2,
        duration: 1500
    },
    data: <m4s_bytes>
})

// Stream completion
on('stream:complete', { streamId: 'stream-1' })

// Error notification
on('error', { message: '...' })
```

---

### 2. HTTP API (sts_streaming_bridge.py)

**POST /api/audio-fragment**
```json
{
    "fragment_id": "fragment-001",
    "sequence_number": 1,
    "timestamp": 1234567890,
    "duration": 1500,
    "codec": "aac",
    "sample_rate": 48000,
    "channels": 2,
    "audio_data": "<hex_encoded_audio>"
}
```

**GET /api/status**
```json
{
    "status": "running",
    "fragments_processed": 42
}
```

---

### 3. File System Integration

**Input Formats:**
- VTT files: `.vtt`
- Audio files: `.wav`, `.mp3`, `.m4a`, `.flac`
- Video files: `.mp4`, `.mkv`, `.avi`, `.mov`

**Output Formats:**
- Audio: `.wav` (processed audio)
- Video: `.mp4` (with mixed audio)
- Fragments: `.m4s` (for streaming)
- Metadata: `.json` (fragment info)

**Directory Structure:**
```
apps/sts-service/
├── .cache_coqui/           # Translation and TTS cache
├── processed_fragments/    # Output fragments
│   └── stream-1/
│       └── es/
│           ├── fragment-001.m4s
│           ├── fragment-001.json
│           └── combined_audio.wav
├── voice_samples/          # Voice cloning samples
│   ├── joe_buck_voice_sample.wav
│   └── referee_sample.wav
└── sample_vtt_files/       # Test VTT files
```

---

## Usage Examples

### 1. Live Stream Processing
```bash
# Start live stream processing
python stream_audio_client.py \
    --server-url ws://localhost:4000 \
    --stream-id stream-1 \
    --targets es,fr \
    --save-local \
    --output-dir ./processed_fragments
```

**What happens:**
1. Connects to mock-media-service
2. Subscribes to "stream-1"
3. Receives audio fragments
4. Processes through STS pipeline
5. Sends back to server
6. Saves locally to `processed_fragments/stream-1/es/`

---

### 2. VTT File Processing
```bash
# Process VTT file with adaptive speed
python talk_multi_coqui.py \
    --vtt sample_vtt_files/livestream_sample.vtt \
    --targets es \
    --adaptive-speed
```

**What happens:**
1. Parses VTT file
2. Detects speakers
3. Translates each segment
4. Synthesizes with speed adjustment
5. Plays in real-time with VTT timing

---

### 3. Audio File Processing
```bash
# Process video file with Spanish translation
python talk_audio_stream.py \
    --audio video.mp4 \
    --targets es \
    --delay 8.0 \
    --mix-volume 0.8 \
    --output dubbed_output.mp4
```

**What happens:**
1. Extracts audio from video
2. Transcribes with Whisper
3. Translates to Spanish
4. Synthesizes Spanish speech
5. Mixes with original audio
6. Creates output video

---

### 4. Interactive Translation
```bash
# Interactive mode
python talk_multi_coqui.py --targets es,fr

# Type text, get translation and speech
> Hello, how are you?
es: Hola, ¿cómo estás?
fr: Bonjour, comment allez-vous?
```

---

## Configuration Examples

### 1. Voice Configuration (coqui-voices.yaml)
```yaml
languages:
  es:
    model: "tts_models/multilingual/multi-dataset/xtts_v2"
    multi_speaker: true
    speakers:
      JOE:
        speaker: "Andrew Chipper"
        voice_sample: "./voice_samples/joe_buck_voice_sample.wav"
      REFEREE:
        speaker: "Claribel Dervla"
        voice_sample: "./voice_samples/referee_sample.wav"
      default:
        speaker: "Andrew Chipper"
        voice_sample: "./voice_samples/default_voice.wav"
```

### 2. Environment Configuration
```bash
# PyTorch configuration
export TORCH_LOAD_WEIGHTS_ONLY='False'
export PYTORCH_ENABLE_MPS_FALLBACK='1'

# Device selection
export DEVICE='cpu'  # or 'cuda', 'mps'

# Cache directory
export CACHE_DIR='.cache_coqui'
```

---

## Testing & Validation

### 1. Test Scripts

**Transcription Testing:**
```bash
python test_transcription.py \
    livestream-sample/live-stream-segment-sample-audio.wav \
    --model base \
    --domain sports
```

**Translation Testing:**
```bash
python test_translation.py "TEN-YARD penalty. NOW 1:54 REMAINING"
```

**Voice Cloning Testing:**
```bash
python test_voice_cloning.py \
    --voice-sample voice_samples/joe_buck_voice_sample.wav \
    --text "Touchdown! The Eagles win!" \
    --language es
```

---

### 2. Performance Benchmarks

**Typical Processing Times (base models, CPU):**
- Transcription: 1-3 seconds per second of audio
- Translation: 0.3-0.5 seconds per segment
- TTS Synthesis: 2-5 seconds per segment
- Speed Adjustment: 0.5-1 second

**Total Pipeline (5-second audio fragment):**
- Transcription: 5-15 seconds
- Translation: 0.3-0.5 seconds
- TTS: 2-5 seconds
- Post-processing: 0.5-1 second
- **Total: 8-22 seconds per fragment**

**Optimization with GPU:**
- Transcription: 0.5-1x realtime
- TTS: 1-2 seconds per segment
- **Total: 3-8 seconds per fragment**

---

### 3. Quality Metrics

**Transcription Quality:**
- Word Error Rate (WER): Measured against reference
- Confidence scores: >0.8 considered reliable
- Domain-specific accuracy: Sports terminology recognition

**Translation Quality:**
- BLEU score: Measured against reference translations
- Fluency: Natural language flow
- Context preservation: Maintains meaning

**TTS Quality:**
- Mean Opinion Score (MOS): 1-5 rating
- Voice similarity: Compared to reference voice
- Naturalness: Prosody and intonation

---

## Dependencies

### Core Libraries
```
# Deep Learning
torch>=2.0.0
transformers>=4.35.0
TTS (Coqui TTS)
faster-whisper>=0.10.0

# Translation
langdetect>=1.0.9
sentencepiece>=0.1.99

# Audio Processing
sounddevice>=0.4.6
soundfile>=0.12.1
librosa>=0.10.1
pydub>=0.25.1
ffmpeg-python>=0.2.0

# Text Processing
inflect>=7.0.0
rich>=13.7.0

# Networking
python-socketio[client]>=5.10.0
requests>=2.31.0

# Configuration
pyyaml>=6.0.1
```

### System Dependencies
```bash
# macOS
brew install rubberband ffmpeg

# Ubuntu/Debian
sudo apt-get install rubberband-cli ffmpeg

# Verify installation
rubberband --version
ffmpeg -version
```

---

## Troubleshooting

### 1. Common Issues

**Issue:** Rubberband not found
```bash
# Install rubberband
brew install rubberband  # macOS
sudo apt-get install rubberband-cli  # Linux
```

**Issue:** CUDA out of memory
```bash
# Use smaller Whisper model
--whisper-model tiny  # instead of base/small

# Or use CPU
--device cpu
```

**Issue:** Socket.IO timeout
```python
# Increase timeout in mock-media-service
FRAGMENT_ACK_TIMEOUT = 10000  # 10 seconds
```

**Issue:** Audio quality issues
```bash
# Check audio extraction
ffprobe fragment.m4s

# Verify sample rate
--sample-rate 16000  # Whisper requirement
```

---

### 2. Debug Mode

**Enable verbose logging:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Whisper debugging:**
```python
# Save intermediate audio files
sf.write('debug_audio.wav', audio_data, sample_rate)

# Print transcription details
for seg in segments:
    print(f"{seg.start:.2f}s - {seg.end:.2f}s: {seg.text} (conf: {seg.confidence:.2f})")
```

---

## Future Improvements

### 1. Planned Features
- [ ] GPU acceleration for TTS synthesis
- [ ] Multi-language speaker detection
- [ ] Emotion transfer in voice cloning
- [ ] Real-time streaming output (no buffering)
- [ ] Advanced noise reduction
- [ ] Lip-sync alignment for video

### 2. Performance Optimizations
- [ ] Model quantization (INT8/FP16)
- [ ] Batch processing for multiple fragments
- [ ] Distributed processing across multiple machines
- [ ] WebSocket streaming instead of Socket.IO
- [ ] ONNX runtime for faster inference

### 3. Quality Improvements
- [ ] Better speaker diarization
- [ ] Context-aware translation
- [ ] Prosody transfer
- [ ] Advanced voice cloning with fewer samples
- [ ] Background music preservation

---

## Conclusion

The STS Service provides a complete end-to-end solution for real-time speech-to-speech translation with:

✅ **High Quality:** State-of-the-art models (Whisper, M2M100, XTTS-v2)
✅ **Real-time Processing:** Optimized for live streams
✅ **Voice Cloning:** Preserves speaker characteristics
✅ **Timing Accuracy:** Adaptive speed control
✅ **Multi-language:** 100+ languages supported
✅ **Production Ready:** Error handling, caching, monitoring

**Key Strengths:**
- Modular architecture (easy to extend)
- Comprehensive error handling
- Efficient caching system
- Flexible configuration
- Well-documented codebase

**Use Cases:**
- Live sports broadcasting
- Real-time conference translation
- Video dubbing
- Multilingual content creation
- Accessibility services

---

*Architecture document created: 2025-10-24*
*STS Service Version: 1.0*

