#!/usr/bin/env python3
"""
Simple VITS Audio Processing Server

A streamlined audio processing server that provides real-time speech-to-text-to-speech (STS)
translation using VITS models for fast synthesis. Designed as a drop-in replacement for
echo-audio-processor, compatible with live-media-service.

Key Features:
- VITS-only TTS synthesis for maximum speed (2-5 seconds per fragment)
- Background noise preservation (70% TTS + 30% background)
- Duration matching using rubberband
- Sequential processing (FIFO) to maintain audio order
- Socket.IO protocol compatible with live-media-service

Author: Philip Baillargeon (Assistance by Cursor/GPT)
"""

# Set environment variables BEFORE any imports
import os
os.environ['TORCH_LOAD_WEIGHTS_ONLY'] = 'False'
os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'

import sys
import argparse
import threading
import queue
import time
import numpy as np
import socketio
from flask import Flask
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import tempfile

# Import existing translation and TTS functions
from talk_multi_coqui import (
    translate,
    synth_to_wav,
    get_speaker_voice,
    get_tts,
    get_mt,
    preprocess_text_for_tts,
    preprocess_text_for_translation,
    clean_speaker_prefix,
    detect_speaker,
    CACHE_DIR,
    sha1,
    load_cfg
)

# Import audio streaming utilities
from utils.transcription import (
    get_whisper_model,
    transcribe_audio_chunk
)
from utils.audio_streaming import (
    load_audio_file
)
from utils.speaker_detection import (
    SpeakerDetector,
    create_speaker_detector
)


class SimpleVITSServer:
    """
    Simple VITS Audio Processing Server
    
    A streamlined server that processes live audio streams through:
    1. Whisper transcription (speech-to-text)
    2. M2M100 translation (text-to-text) 
    3. VITS synthesis (text-to-speech)
    4. Background noise mixing (preserves ambient sounds)
    5. Duration matching (ensures consistent timing)
    
    Optimized for single target language processing with VITS models for maximum speed.
    """
    
    def __init__(self, args, voices_config=None):
        print(f"Initializing SimpleVITSServer with args: {args}")
        self.args = args
        
        # Single target language optimization
        targets_list = [t.strip() for t in args.targets.split(",") if t.strip()]
        if len(targets_list) != 1:
            raise ValueError(f"Single target language required, got: {targets_list}")
        self.target_lang = targets_list[0]
        self.source_lang = args.source_lang
        self.host = args.host
        self.port = args.port
        self.save_local = args.save_local
        self.output_dir = Path(args.output_dir)
        
        # Socket.IO server
        self.app = Flask(__name__)
        self.sio = socketio.Server(cors_allowed_origins="*")
        self.app.wsgi_app = socketio.WSGIApp(self.sio, self.app)
        self.connected_clients = {}  # Track connected clients
        
        # Processing state
        self.running = False
        self.fragment_count = 0
        self.processed_count = 0
        self.failed_count = 0
        
        # Pre-loaded models (single language optimization)
        self.whisper_model = None
        self.tts_model = None  # Single TTS model
        self.mt_model = None
        
        # Voice configuration
        self.voices = voices_config or {}
        
        # VITS voice configuration
        self.vits_voices = {}
        vits_config_path = Path("vits_voices.yml")
        if vits_config_path.exists():
            import yaml
            with open(vits_config_path, 'r') as f:
                self.vits_voices = yaml.safe_load(f)
            print(f"Loaded VITS voices configuration: {vits_config_path}")
        else:
            print(f"VITS voices configuration not found: {vits_config_path}")
        
        # Speaker detection (optional)
        self.speaker_detector = None
        if args.enable_speaker_detection:
            self.speaker_detector = create_speaker_detector(
                similarity_threshold=args.speaker_threshold,
                device=args.device
            )
            print(f"Speaker detection enabled (threshold: {args.speaker_threshold})")
            
            # Load speaker database if specified
            if args.speaker_config and Path(args.speaker_config).exists():
                self.speaker_detector.load_speaker_database(args.speaker_config)
        
        # Processing queue for sequential audio processing (FIFO order)
        self.processing_queue = queue.Queue()
        self.processing_thread = None
        
        # Note: Removed unused processed_audio_fragments and processed_sample_rate
        # These were intended for combining fragments but are not used in this implementation
        
        # Setup output directory if saving locally
        if self.save_local:
            self._setup_output_directory()
        
        # Setup Socket.IO event handlers
        self._setup_socket_handlers()
    
    def _setup_output_directory(self):
        """Setup output directory structure for local saving (single language)"""
        lang_dir = self.output_dir / self.target_lang
        lang_dir.mkdir(parents=True, exist_ok=True)
        print(f"Created output directory: {lang_dir}")
    
    def _setup_socket_handlers(self):
        """Setup Socket.IO server event handlers for live-media-service compatibility"""
        
        @self.sio.event
        def connect(sid, environ):
            print(f"✓ Client connected: {sid}")
            self.connected_clients[sid] = {
                'connected_at': time.time(),
                'fragments_received': 0,
                'fragments_processed': 0
            }
            print(f"   Total clients: {len(self.connected_clients)}")
        
        @self.sio.event
        def disconnect(sid):
            print(f"✓ Client disconnected: {sid}")
            if sid in self.connected_clients:
                client_stats = self.connected_clients[sid]
                print(f"   Client stats: {client_stats['fragments_received']} received, {client_stats['fragments_processed']} processed")
                del self.connected_clients[sid]
            print(f"   Remaining clients: {len(self.connected_clients)}")
        
        @self.sio.on('fragment:data')
        def fragment_data(sid, delivery):
            """Handle incoming audio fragment from live-media-service client"""
            try:
                print(f"🔔 fragment:data event received from {sid}")
                fragment = delivery.get('fragment', {})
                data = delivery.get('data', b'')
                
                if not data:
                    print(f"⚠️ Empty data received in fragment")
                    return
                
                self.fragment_count += 1
                
                # Update client stats
                if sid in self.connected_clients:
                    self.connected_clients[sid]['fragments_received'] += 1
                
                print(f"📦 Fragment {self.fragment_count} Received from {sid}:")
                print(f"  ID: {fragment.get('id', 'unknown')}")
                print(f"  Stream: {fragment.get('streamId', 'unknown')}")
                print(f"  Batch: {fragment.get('batchNumber', 'unknown')}")
                print(f"  Size: {len(data):,} bytes ({len(data) / 1024:.2f} KB)")
                print(f"  Duration: {fragment.get('duration', 0)}s")
                
                # Add to processing queue for background processing
                # Include sid so we can send response back to correct client
                self.processing_queue.put((sid, fragment, data))
                print(f"  → Added to processing queue (queue size: {self.processing_queue.qsize()})")
            except Exception as e:
                print(f"ERROR in fragment_data handler: {e}")
                import traceback
                traceback.print_exc()
    
    
    def _preload_models(self):
        """Preload Whisper, translation, and VITS TTS models for fast processing"""
        print("Preloading models...")
        
        try:
            # Load Whisper model
            print("Loading Whisper model...")
            self.whisper_model = get_whisper_model(
                self.args.whisper_model,
                self.args.device
            )
            if self.whisper_model is None:
                print("ERROR: Failed to load Whisper model")
                return False
            print("✓ Whisper model loaded")
            
            # Load MT model
            print("Loading translation model...")
            self.mt_model = get_mt(self.args.device)
            print("✓ Translation model loaded")
            
            # Load VITS TTS model for single target language (fast synthesis)
            print(f"Loading TTS model for {self.target_lang}...")
            language_config = self.voices.get(self.target_lang, {})
            
            # Use VITS model for fast synthesis (key advantage over XTTS)
            model_name = language_config.get("fast_model")
            if model_name:
                print(f"Loading VITS TTS model: {model_name}")
                self.tts_model = get_tts(model_name)
                print(f"✓ VITS TTS model loaded for {self.target_lang}")
            else:
                print(f"⚠️ No fast model configured for {self.target_lang}, falling back to standard model")
                model_name = language_config.get("model")
                if model_name:
                    print(f"Loading TTS model: {model_name}")
                    self.tts_model = get_tts(model_name)
                    print(f"✓ TTS model loaded for {self.target_lang}")
                else:
                    raise ValueError(f"No TTS model configured for {self.target_lang}")
            
            # Store the actual model name for verification
            self.actual_tts_model = model_name
            
            print("✓ All models preloaded successfully!")
            
            # Warmup models with dummy data to eliminate first-fragment delay
            print("Warming up models...")
            self._warmup_models()
            
            # Verify models are ready by testing them
            if not self._verify_models_ready():
                print("ERROR: Model verification failed")
                return False
            
            return True
            
        except Exception as e:
            print(f"ERROR: Error preloading models: {e}")
            return False
    
    def _warmup_models(self):
        """Warmup models with dummy data to eliminate first-fragment delay"""
        try:
            # Warmup Whisper with dummy audio
            dummy_audio = np.zeros(1600, dtype=np.float32)  # 0.1 second of silence
            print("Warming up Whisper...")
            transcribe_audio_chunk(dummy_audio, 16000, self.whisper_model, domain="sports")
            print("✓ Whisper warmed up")
            
            # Warmup translation model
            print("Warming up translation model...")
            if self.source_lang:
                translate("Hello world", self.target_lang, self.args.device, src=self.source_lang)
            else:
                translate("Hello world", self.target_lang, self.args.device)
            print("✓ Translation model warmed up")
            
            # Warmup TTS model
            print("Warming up TTS model...")
            synth_to_wav("Hello world", self.actual_tts_model, speaker=None, target_language=self.target_lang, voice_sample_path=None)
            print("✓ TTS model warmed up")
            
        except Exception as e:
            print(f"Warning: Model warmup failed: {e}")
    
    def _verify_models_ready(self):
        """Verify all models are ready by running a test"""
        try:
            print("Verifying models are ready...")
            
            # Test Whisper
            dummy_audio = np.zeros(1600, dtype=np.float32)
            segments = transcribe_audio_chunk(dummy_audio, 16000, self.whisper_model, domain="sports")
            print("✓ Whisper verification passed")
            
            # Test translation
            if self.source_lang:
                mt_res = translate("Test", self.target_lang, self.args.device, src=self.source_lang)
            else:
                mt_res = translate("Test", self.target_lang, self.args.device)
            print("✓ Translation verification passed")
            
            # Test TTS
            wav_path = synth_to_wav("Test", self.actual_tts_model, speaker=None, target_language=self.target_lang, voice_sample_path=None)
            if wav_path and wav_path.exists():
                wav_path.unlink()  # Clean up test file
                print("✓ TTS verification passed")
            else:
                print("✗ TTS verification failed")
                return False
            
            print("✓ All models verified and ready!")
            return True
            
        except Exception as e:
            print(f"✗ Model verification failed: {e}")
            return False

    def _processing_worker(self):
        """Sequential processing worker - maintains fragment order (FIFO) for consistent audio timing"""
        print("Sequential processing worker started")
        while self.running:
            try:
                # Process fragments one at a time in arrival order (FIFO)
                sid, fragment, data = self.processing_queue.get(timeout=1.0)
                fragment_id = fragment.get('id', 'unknown')
                print(f"Processing fragment {fragment_id} for client {sid} (sequential order)")
                
                # Process the fragment with timing
                start_time = time.time()
                processed_data = self._process_fragment(sid, fragment, data)
                processing_time = time.time() - start_time
                
                if processed_data is not None:
                    # Send processed fragment back to the specific client
                    try:
                        self.sio.emit('fragment:processed', {
                            'fragment': fragment,
                            'data': processed_data,
                            'metadata': {
                                'processingTime': processing_time,
                                'processor': 'simple-vits-server',
                                'timestamp': time.time(),
                                'processedSequentially': True  # Indicate sequential processing
                            }
                        }, room=sid)
                        print(f"✓ Sent processed fragment {fragment_id} to client {sid} (processing time: {processing_time:.2f}s)")
                        self.processed_count += 1
                        
                        # Update client stats
                        if sid in self.connected_clients:
                            self.connected_clients[sid]['fragments_processed'] += 1
                            
                    except Exception as e:
                        print(f"ERROR: Failed to send processed fragment: {e}")
                        self.failed_count += 1
                else:
                    print(f"✗ Failed to process fragment {fragment_id}")
                    self.failed_count += 1
                
                # Debug: Show processing status
                print(f"Fragment {fragment_id} completed. Queue: {self.processing_queue.qsize()}, Processed: {self.processed_count}, Failed: {self.failed_count}")
                
                print()  # Empty line between fragments
                
            except queue.Empty:
                # In server mode, we don't stop when queue is empty - keep running
                continue
            except Exception as e:
                print(f"ERROR: Processing worker error: {e}")
                import traceback
                traceback.print_exc()
        
        print("Processing worker stopped")

    def _process_fragment(self, sid: str, fragment: Dict[str, Any], data: bytes) -> Optional[bytes]:
        """
        Process a single audio fragment through the complete STS pipeline
        
        Pipeline: Audio → Transcription → Translation → TTS → Mixing → Encoding
        
        Args:
            sid: Socket ID of the client
            fragment: Fragment metadata (duration, sample rate, etc.)
            data: Binary audio data (m4s format)
            
        Returns:
            Processed audio data (m4s format) or None if processing failed
        """
        try:
            fragment_id = fragment.get('id', 'unknown')
            print(f"Processing fragment {fragment_id}...")
            
            # Extract audio from m4s data
            sample_rate = fragment.get('sampleRate', 44100)
            duration = fragment.get('duration', 30)
            if isinstance(duration, (int, float)) and duration > 100:
                duration = duration / 1000.0
            
            # Save m4s data to temporary file
            with tempfile.NamedTemporaryFile(suffix='.m4s', delete=False) as temp_file:
                temp_file.write(data)
                temp_m4s_path = temp_file.name
            
            try:
                # Extract audio using ffmpeg
                import ffmpeg
                temp_wav_path = tempfile.mkstemp(suffix='.wav')[1]
                
                (
                    ffmpeg
                    .input(temp_m4s_path)
                    .output(temp_wav_path, acodec='pcm_s16le', ac=1, ar=sample_rate)
                    .overwrite_output()
                    .run(quiet=True)
                )
                
                # Load audio data
                audio_data, actual_sample_rate = load_audio_file(temp_wav_path)
                print(f"Loaded audio: {len(audio_data)/actual_sample_rate:.1f}s at {actual_sample_rate}Hz")
                
                # Clean up temp files
                os.unlink(temp_m4s_path)
                os.unlink(temp_wav_path)
                
            except Exception as e:
                print(f"Audio extraction failed: {e}")
                return None
            
            # Detect speaker from audio (if enabled)
            detected_speaker_id = "default"
            speaker_confidence = 0.0
            if self.speaker_detector:
                detected_speaker_id, speaker_confidence = self.speaker_detector.identify_speaker(
                    audio_data, 
                    actual_sample_rate
                )
                print(f"Detected speaker: {detected_speaker_id} (confidence: {speaker_confidence:.2f})")
            
            # Transcribe audio
            print("Transcribing audio...")
            segments = transcribe_audio_chunk(
                audio_data, 
                actual_sample_rate,
                self.whisper_model,
                domain="sports"
            )
            
            if not segments:
                print("No speech detected, returning original audio")
                return self._encode_audio(audio_data, actual_sample_rate)
            
            # Combine segments
            combined_text = " ".join([seg[2] for seg in segments])
            print(f"Transcription: {combined_text}")
            
            # Check for hallucination/repetitive content
            if self._is_likely_hallucination(combined_text, duration):
                print("🚫 Skipping TTS due to detected hallucination - returning original audio")
                return self._encode_audio(audio_data, actual_sample_rate)
            
            # Detect speaker from text (fallback or additional info)
            text_speaker = detect_speaker(combined_text)
            print(f"Text-based speaker: {text_speaker}")
            
            # Use audio-based speaker detection if available, otherwise fall back to text-based
            speaker = detected_speaker_id if self.speaker_detector else text_speaker
            
            # Clean text for translation
            clean_text = clean_speaker_prefix(combined_text, speaker)
            
            # Translate
            print("Translating text...")
            preprocessed_text = preprocess_text_for_translation(clean_text)
            if self.source_lang:
                print(f"Translating from {self.source_lang} to {self.target_lang}")
                mt_res = translate(preprocessed_text, self.target_lang, self.args.device, src=self.source_lang)
            else:
                print(f"Translating (auto-detect source) to {self.target_lang}")
                mt_res = translate(preprocessed_text, self.target_lang, self.args.device)
            translated_text = mt_res['out']
            print(f"{self.target_lang}: {translated_text}")
            
            # Get voice configuration for detected speaker
            voice_config = None
            if self.speaker_detector:
                voice_config = self.speaker_detector.get_speaker_voice_config(
                    speaker, 
                    self.target_lang,
                    self.voices,
                    self.vits_voices
                )
                print(f"Voice config for {speaker}: {voice_config}")
            
            # TTS synthesis - use speaker-specific voice configuration
            print("Synthesizing audio...")
            
            # Determine TTS parameters based on voice config
            if voice_config and voice_config.get('config_type') == 'vits':
                # Use VITS-specific configuration
                model_name = voice_config.get('model', f'tts_models/{self.target_lang}/css10/vits')
                speaker_id = voice_config.get('speaker_id', 0)
                voice_sample_path = None  # VITS doesn't use voice samples
                tts_speaker = None  # VITS uses speaker_id instead
                
                print(f"Using VITS model: {model_name}, speaker_id: {speaker_id}")
                
                # Load the specific VITS model if different from current
                if hasattr(self, 'current_vits_model') and self.current_vits_model != model_name:
                    print(f"Loading VITS model: {model_name}")
                    self.current_vits_model = model_name
                    self.tts_model = get_tts(model_name)
                
                # Use VITS-specific synthesis with speaker_id
                wav_path = self._synth_to_wav_vits_with_speaker(
                    translated_text, 
                    model_name,
                    speaker_id
                )
            else:
                # Use legacy configuration
                voice_sample_path = voice_config.get('voice_sample') if voice_config else None
                tts_speaker = voice_config.get('fallback_speaker') if voice_config else None
                
                wav_path = synth_to_wav(
                    translated_text, 
                    self.actual_tts_model, 
                    speaker=tts_speaker, 
                    target_language=self.target_lang, 
                    voice_sample_path=voice_sample_path
                )
            
            if not wav_path or not wav_path.exists():
                print("TTS synthesis failed, returning original audio")
                return self._encode_audio(audio_data, actual_sample_rate)
            
            # Debug: Check if TTS file exists and has content
            file_size = wav_path.stat().st_size if wav_path.exists() else 0
            print(f"TTS file info: {wav_path}, size: {file_size} bytes")
            
            # Load synthesized audio
            import soundfile as sf
            synthesized_audio, tts_sample_rate = sf.read(str(wav_path), dtype="float32")
            
            # Clean up temp file
            wav_path.unlink()
            
            # Resample to match original sample rate if needed
            if tts_sample_rate != actual_sample_rate:
                import librosa
                synthesized_audio = librosa.resample(
                    synthesized_audio, 
                    orig_sr=tts_sample_rate, 
                    target_sr=actual_sample_rate
                )
            
            print(f"TTS audio duration: {len(synthesized_audio)/actual_sample_rate:.2f}s")
            
            # Ensure TTS audio matches original duration
            original_duration = len(audio_data) / actual_sample_rate
            tts_duration = len(synthesized_audio) / actual_sample_rate
            
            print(f"Duration matching:")
            print(f"  Original duration: {original_duration:.2f}s")
            print(f"  TTS duration: {tts_duration:.2f}s")
            
            if abs(tts_duration - original_duration) > 0.1:  # More than 100ms difference
                # Adjust speed to match original duration
                required_speed = tts_duration / original_duration
                # Cap at 2.0x to prevent quality degradation
                required_speed = max(1.0, min(2.0, required_speed))
                
                print(f"  Required speed adjustment: {required_speed:.2f}x")
                
                if required_speed > 1.0:
                    print(f"  → Speeding up audio to match original duration")
                    synthesized_audio = self._adjust_audio_speed_in_memory(synthesized_audio, actual_sample_rate, required_speed)
                else:
                    print(f"  → No speed adjustment needed (TTS duration already matches)")
            else:
                print(f"  → Duration already matches (within 100ms)")
            
            # Debug: Check TTS audio levels
            tts_max = np.max(np.abs(synthesized_audio))
            original_max = np.max(np.abs(audio_data))
            print(f"Audio levels:")
            print(f"  TTS max amplitude: {tts_max:.4f}")
            print(f"  Original max amplitude: {original_max:.4f}")
            
            # Mix TTS audio with original background noise
            print("Mixing TTS with background noise...")
            final_audio = self._mix_tts_with_background(synthesized_audio, audio_data, actual_sample_rate)
            
            # Encode as m4s
            return self._encode_audio(final_audio, actual_sample_rate)
            
        except Exception as e:
            print(f"ERROR: Error processing fragment: {e}")
            return None
    
    def _is_likely_hallucination(self, text: str, original_duration: float) -> bool:
        """
        Detect if text is likely a hallucination that should skip TTS
        
        Args:
            text: Transcribed text to check
            original_duration: Duration of the original audio in seconds
            
        Returns:
            True if likely a hallucination, False otherwise
        """
        words = text.lower().split()
        if len(words) < 10:
            return False
        
        # Check for excessive repetition
        word_counts = {}
        for word in words:
            word_counts[word] = word_counts.get(word, 0) + 1
        
        # If any word appears more than 30% of the time, likely repetitive
        max_word_count = max(word_counts.values())
        if max_word_count > len(words) * 0.3:
            word_name = max(word_counts, key=word_counts.get)
            print(f"🚫 Detected repetitive text (word '{word_name}' appears {max_word_count}/{len(words)} times)")
            return True
        
        # Check for extremely high word density (likely hallucination)
        words_per_second = len(words) / original_duration
        if words_per_second > 15:  # More than 15 words per second is unrealistic
            print(f"🚫 Detected unrealistic word density: {words_per_second:.1f} words/second")
            return True
        
        # Check for extremely long text relative to duration
        chars_per_second = len(text) / original_duration
        if chars_per_second > 100:  # More than 100 characters per second is unrealistic
            print(f"🚫 Detected unrealistic character density: {chars_per_second:.1f} chars/second")
            return True
        
        return False
    
    def _adjust_audio_speed_in_memory(self, audio_data: np.ndarray, sample_rate: int, speed_factor: float) -> np.ndarray:
        """
        Adjust audio speed using rubberband for high quality while preserving pitch
        
        Args:
            audio_data: Input audio data as numpy array
            sample_rate: Sample rate of the audio
            speed_factor: Speed adjustment factor (1.0 = no change, 2.0 = 2x faster)
            
        Returns:
            Adjusted audio data as numpy array
        """
        import subprocess
        import tempfile
        import soundfile as sf
        
        try:
            # Create temporary files for input and output
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_input:
                temp_input_path = temp_input.name
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_output:
                temp_output_path = temp_output.name
            
            try:
                # Write input audio to temporary file
                sf.write(temp_input_path, audio_data, sample_rate)
                
                # Use rubberband for high-quality time stretching
                cmd = [
                    "rubberband",
                    f"-T{speed_factor}",      # Tempo change (no space between -T and value)
                    "-p", "0",                # Keep pitch unchanged (0 semitones)
                    "-F",                     # Enable formant preservation
                    "-q",                     # Quiet mode
                    temp_input_path,
                    temp_output_path
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode != 0:
                    print(f"Warning: rubberband failed: {result.stderr}")
                    print("Falling back to original audio")
                    return audio_data
                
                # Read the adjusted audio
                adjusted_audio, _ = sf.read(temp_output_path, dtype="float32")
                
                print(f"✓ Speed adjustment applied: {len(audio_data)/sample_rate:.2f}s → {len(adjusted_audio)/sample_rate:.2f}s")
                return adjusted_audio
                
            finally:
                # Clean up temporary files
                import os
                if os.path.exists(temp_input_path):
                    os.unlink(temp_input_path)
                if os.path.exists(temp_output_path):
                    os.unlink(temp_output_path)
                    
        except Exception as e:
            print(f"Warning: Speed adjustment failed: {e}")
            print("Falling back to original audio")
            return audio_data

    def _mix_tts_with_background(self, tts_audio: np.ndarray, original_audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        Mix TTS audio with original background noise to preserve ambient sounds
        
        Args:
            tts_audio: Synthesized TTS audio
            original_audio: Original audio with background noise
            sample_rate: Sample rate of both audio streams
            
        Returns:
            Mixed audio with TTS speech over background noise
        """
        try:
            # Ensure both audio streams are the same length
            min_length = min(len(tts_audio), len(original_audio))
            tts_audio = tts_audio[:min_length]
            original_audio = original_audio[:min_length]
            
            # Simple approach: treat entire audio as speech region and mix TTS over background
            print("Using simple audio mixing (entire audio as speech region)...")
            
            # Check if mixing is disabled
            if hasattr(self, 'args') and getattr(self.args, 'no_mixing', False):
                print("Using TTS-only mode (--no-mixing flag)")
                mixed_audio = tts_audio
            else:
                # Mix TTS over entire background audio (total volume = 100%)
                tts_volume = 0.7  # TTS volume (70%)
                background_volume = 0.3  # Background volume (30%)
                
                print(f"Mixing parameters:")
                print(f"  TTS volume: {tts_volume:.1f} (70%)")
                print(f"  Background volume: {background_volume:.1f} (30%)")
                print(f"  Total volume: {tts_volume + background_volume:.1f} (100%)")
                
                # Simple mixing: TTS + reduced background (total = 100%)
                mixed_audio = (tts_audio * tts_volume) + (original_audio * background_volume)
            
            
            print(f"✓ Audio mixing complete:")
            print(f"  Final audio length: {len(mixed_audio)/sample_rate:.2f}s")
            print(f"  Mixed TTS ({tts_volume:.1f}) + Background ({background_volume:.1f})")
            
            return mixed_audio
            
        except Exception as e:
            print(f"Warning: Audio mixing failed: {e}")
            print("Falling back to TTS audio only")
            return tts_audio

    def _synth_to_wav_vits_with_speaker(self, text: str, model_name: str, speaker_id: int) -> Path:
        """
        Synthesize text to WAV using VITS model with specific speaker ID.
        
        Args:
            text: Text to synthesize
            model_name: VITS model name
            speaker_id: Speaker ID for multi-speaker VITS models
            
        Returns:
            Path to generated WAV file
        """
        import tempfile
        import os
        
        # Create temporary file
        temp_fd, temp_path = tempfile.mkstemp(suffix=".wav", prefix="vits_speaker_")
        os.close(temp_fd)
        wav = Path(temp_path)
        
        try:
            # Load TTS model
            tts = get_tts(model_name)
            
            # Preprocess text
            processed_text = preprocess_text_for_tts(text, convert_numbers=False)
            
            # Try VITS synthesis with speaker ID
            success = False
            
            # Approach 1: Try with speaker parameter
            try:
                print(f"Attempting VITS synthesis with speaker_id={speaker_id}...")
                tts.tts_to_file(text=processed_text, file_path=str(wav), speaker_id=speaker_id)
                success = True
                print(f"✓ VITS synthesis with speaker_id successful")
            except Exception as e:
                print(f"Speaker synthesis failed: {e}")
                
                # Approach 2: Try basic synthesis as fallback
                try:
                    print(f"Attempting basic VITS synthesis as fallback...")
                    tts.tts_to_file(text=processed_text, file_path=str(wav))
                    success = True
                    print(f"✓ Basic VITS synthesis successful")
                except Exception as e2:
                    print(f"Basic synthesis failed: {e2}")
                    
                    # Approach 3: Try array-based synthesis
                    try:
                        print(f"Attempting array-based VITS synthesis...")
                        audio_array = tts.tts(text=processed_text)
                        
                        import numpy as np
                        if isinstance(audio_array, list):
                            audio_array = np.array(audio_array)
                        elif not isinstance(audio_array, np.ndarray):
                            raise ValueError(f"Expected numpy array or list, got {type(audio_array)}")
                        
                        import soundfile as sf
                        sf.write(str(wav), audio_array, 22050)  # VITS models typically use 22050 Hz
                        success = True
                        print(f"✓ Array-based VITS synthesis successful")
                        
                    except Exception as e3:
                        print(f"Array-based synthesis failed: {e3}")
                        raise RuntimeError(f"All VITS synthesis methods failed: {e}, {e2}, {e3}")
            
            if not success:
                raise RuntimeError("VITS synthesis failed")
                
            return wav
            
        except Exception as e:
            print(f"Error in VITS synthesis: {e}")
            # Clean up temp file on error
            if wav.exists():
                wav.unlink()
            raise

    def _encode_audio(self, audio_data: np.ndarray, sample_rate: int) -> bytes:
        """
        Encode audio data as m4s container for live-media-service compatibility
        
        Args:
            audio_data: Processed audio as numpy array
            sample_rate: Audio sample rate
            
        Returns:
            Binary audio data in m4s format
        """
        try:
            import ffmpeg
            import io
            import soundfile as sf
            
            # Convert to int16
            audio_int16 = (audio_data * 32767).astype(np.int16)
            
            # Create in-memory WAV data
            wav_buffer = io.BytesIO()
            sf.write(wav_buffer, audio_int16, sample_rate, format='WAV')
            wav_data = wav_buffer.getvalue()
            
            # Use ffmpeg with pipe input/output to avoid temporary files
            out, _ = (
                ffmpeg
                .input('pipe:', format='wav')
                .output('pipe:', 
                       format='mp4',
                       acodec='aac',
                       ar=sample_rate,
                       ac=1,
                       movflags='frag_keyframe+empty_moov')
                .run(input=wav_data, capture_stdout=True, quiet=True)
            )
            
            processed_audio_bytes = out
            print(f"Encoded processed audio: {len(processed_audio_bytes)} bytes")
            return processed_audio_bytes
            
        except Exception as e:
            print(f"ERROR: Failed to encode m4s container: {e}")
            # Fallback to simple bytes (not ideal but prevents crashes)
            return audio_data.tobytes()

    def start_server(self):
        """Start the Socket.IO server and begin processing audio fragments"""
        print("=" * 60)
        print("Simple VITS Audio Processing Server")
        print("=" * 60)
        print(f"Host: {self.host}")
        print(f"Port: {self.port}")
        print(f"Target language: {self.target_lang}")
        if self.source_lang:
            print(f"Source language: {self.source_lang}")
        else:
            print(f"Source language: auto-detect")
        print(f"TTS model: {self.voices[self.target_lang]['fast_model']}")
        print("=" * 60)
        
        # Preload models
        if not self._preload_models():
            print("ERROR: Failed to preload models")
            return
        
        print("Starting Simple VITS server...")
        self.running = True
        
        # Start background processing thread for sequential audio processing
        self.processing_thread = threading.Thread(target=self._processing_worker)
        self.processing_thread.daemon = True
        self.processing_thread.start()
        print("✓ Processing thread started")
        
        try:
            self.app.run(host=self.host, port=self.port, debug=False)
        except KeyboardInterrupt:
            print("\nShutting down server...")
            self.running = False


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Simple VITS Audio Processing Server")
    parser.add_argument("--host", default="localhost", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind to")
    parser.add_argument("--targets", "-t", required=True, help="Target language (e.g., 'es')")
    parser.add_argument("--source-lang", "-s", default=None, help="Source language for translation (e.g., 'en', 'fr'). Defaults to auto-detect.")
    parser.add_argument("--save-local", action="store_true", help="Save processed fragments locally")
    parser.add_argument("--output-dir", default="./processed_fragments", help="Output directory for local saves")
    parser.add_argument("--config", "-c", default="coqui-voices.yaml", help="Voice configuration file")
    parser.add_argument("--whisper-model", default="base", help="Whisper model size")
    parser.add_argument("--device", default="cpu", help="Processing device")
    parser.add_argument("--no-mixing", action="store_true", help="Disable background noise mixing (TTS only)")
    parser.add_argument('--speaker-threshold', type=float, default=0.75,
                       help='Similarity threshold for speaker matching (0.0-1.0)')
    parser.add_argument('--enable-speaker-detection', action='store_true',
                       help='Enable automatic speaker detection')
    parser.add_argument('--speaker-config', type=str, default=None,
                       help='Path to speaker configuration file (optional)')
    
    args = parser.parse_args()
    
    # Load configuration
    cfg = load_cfg(args.config)
    voices = cfg.get("languages", {})
    
    # Validate target language
    targets_list = [t.strip() for t in args.targets.split(",") if t.strip()]
    for target in targets_list:
        if target not in voices:
            print(f"ERROR: No voice configured for language: {target}")
            print(f"Available languages: {list(voices.keys())}")
            sys.exit(1)
        
        if "fast_model" not in voices[target]:
            print(f"ERROR: No fast_model configured for language: {target}")
            sys.exit(1)
    
    # Create and start server
    server = SimpleVITSServer(args, voices_config=voices)
    server.start_server()


if __name__ == "__main__":
    main()