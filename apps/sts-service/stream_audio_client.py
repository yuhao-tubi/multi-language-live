#!/usr/bin/env python3
"""
Live Audio Stream Processing Client

This script connects to the mock-media-service via Socket.IO, receives live audio fragments,
processes them through the full STS pipeline (transcribe → translate → synthesize), and 
sends back processed audio with optional local saving.

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
import json
import numpy as np
import socketio
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import yaml
import tempfile
import signal

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

# Import audio utilities
from utils.audio_normalization import get_audio_duration

# Import audio streaming utilities
from utils.transcription import (
    get_whisper_model,
    transcribe_audio_chunk
)
from utils.audio_streaming import (
    load_audio_file,
    create_silence
)
from utils.voice_management import setup_voice_samples


class LiveStreamProcessor:
    """
    Main processor for live audio stream with real-time transcription and translation
    """
    
    def __init__(self, args):
        print(f"Initializing LiveStreamProcessor with args: {args}")
        self.args = args
        self.targets = [t.strip() for t in args.targets.split(",") if t.strip()]
        self.server_url = args.server_url
        self.stream_id = args.stream_id
        self.save_local = args.save_local
        self.output_dir = Path(args.output_dir)
        
        # Socket.IO client
        self.sio = socketio.Client()
        self.connected = False
        self.subscribed = False
        
        # Processing state
        self.running = False
        self.fragment_count = 0
        self.processed_count = 0
        self.failed_count = 0
        self.total_fragments_expected = 0
        
        # Pre-loaded models
        self.whisper_model = None
        self.tts_models = {}  # Cache for TTS models
        self.mt_model = None
        
        # Voice configuration
        self.voices = {}
        
        # Processing queue for async processing
        self.processing_queue = queue.Queue()
        self.processing_thread = None
        
        # Store processed audio fragments for combining at the end
        self.processed_audio_fragments: List[np.ndarray] = []
        self.processed_sample_rate = None
        
        # Setup output directory if saving locally
        if self.save_local:
            self._setup_output_directory()
        
        # Setup Socket.IO event handlers
        self._setup_socket_handlers()
    
    def _setup_output_directory(self):
        """Setup output directory structure for local saving"""
        for target_lang in self.targets:
            lang_dir = self.output_dir / self.stream_id / target_lang
            lang_dir.mkdir(parents=True, exist_ok=True)
            print(f"Created output directory: {lang_dir}")
    
    def _setup_socket_handlers(self):
        """Setup Socket.IO event handlers"""
        
        @self.sio.event
        def connect():
            print(f"✓ Connected to server: {self.server_url}")
            print(f"Socket ID: {self.sio.sid}")
            self.connected = True
            
            # Subscribe to stream
            print(f"→ Subscribing to stream: {self.stream_id}")
            self.sio.emit('subscribe', {'streamId': self.stream_id})
        
        @self.sio.event
        def subscribed(data):
            print(f"✓ Successfully subscribed to stream: {data['streamId']}")
            print("Waiting for fragments...\n")
            self.subscribed = True
        
        @self.sio.on('fragment:data')
        def fragment_data(delivery):
            """Handle incoming audio fragment"""
            fragment = delivery['fragment']
            data = delivery['data']
            
            self.fragment_count += 1
            
            print(f"📦 Fragment {self.fragment_count} Received:")
            print(f"  ID: {fragment['id']}")
            print(f"  Sequence: {fragment['sequenceNumber']}")
            print(f"  Size: {len(data):,} bytes ({len(data) / 1024:.2f} KB)")
            print(f"  Codec: {fragment['codec']}")
            print(f"  Sample Rate: {fragment['sampleRate']} Hz")
            print(f"  Channels: {fragment['channels']}")
            print(f"  Duration: {fragment['duration']}ms")
            
            # Acknowledge receipt IMMEDIATELY to avoid timeout
            self.sio.emit('fragment:ack', {'fragmentId': fragment['id']})
            print(f"  ✓ Acknowledged immediately")
            
            # Add to processing queue for background processing
            self.processing_queue.put((fragment, data))
            print(f"  → Added to processing queue")
        
        @self.sio.on('stream:complete')
        def stream_complete(data):
            print("=" * 60)
            print(f"✓ Stream completed: {data['streamId']}")
            print(f"  Total fragments received: {self.fragment_count}")
            print(f"  Successfully processed: {self.processed_count}")
            print(f"  Failed processing: {self.failed_count}")
            print("=" * 60)
            
            # Wait for processing to complete
            self._wait_for_processing_complete()
            
            # Disconnect
            try:
                self.sio.disconnect()
            except Exception as e:
                print(f"Warning: Error during disconnect: {e}")
        
        @self.sio.on('error')
        def error(error_data):
            print(f"✗ Error: {error_data}")
            if 'availableStreams' in error_data:
                print(f"Available streams: {error_data['availableStreams']}")
        
        @self.sio.on('disconnect')
        def disconnect():
            if self.connected:  # Only print once
                print(f"✓ Disconnected from server")
            self.connected = False
            # Don't set self.running = False here - let processing continue
    
    def _wait_for_processing_complete(self):
        """Wait for all fragments to be processed"""
        print("Waiting for processing to complete...")
        
        # Wait for processing queue to empty
        timeout = 60  # 60 second timeout (increased from 30)
        start_time = time.time()
        
        while not self.processing_queue.empty():
            if time.time() - start_time > timeout:
                print("ERROR: Timeout waiting for processing queue to empty")
                break
            time.sleep(0.1)
        
        # Wait for all fragments to actually be processed
        total_expected = self.fragment_count
        print(f"Waiting for {total_expected} fragments to complete processing...")
        while (self.processed_count + self.failed_count) < total_expected:
            if time.time() - start_time > timeout:
                print(f"ERROR: Timeout waiting for processing to complete. Expected: {total_expected}, Processed: {self.processed_count}, Failed: {self.failed_count}")
                print(f"Queue size: {self.processing_queue.qsize()}")
                break
            print(f"Waiting... Processed: {self.processed_count}, Failed: {self.failed_count}, Expected: {total_expected}, Queue: {self.processing_queue.qsize()}")
            time.sleep(1)
        
        # Wait for processing thread to finish current work
        if self.processing_thread and self.processing_thread.is_alive():
            print("Waiting for processing thread to finish...")
            self.processing_thread.join(timeout=30)  # Wait up to 30 more seconds
        
        print("✓ Processing complete!")
    
    def _preload_models(self):
        """Preload all models before starting"""
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
            self.mt_model = get_mt()
            print("✓ Translation model loaded")
            
            # Load TTS models for each target language
            print("Loading TTS models...")
            for target_lang in self.targets:
                language_config = self.voices.get(target_lang, {})
                model_name = language_config.get("model")
                if model_name and model_name not in self.tts_models:
                    print(f"Loading TTS model for {target_lang}: {model_name}")
                    self.tts_models[model_name] = get_tts(model_name)
                    print(f"✓ TTS model loaded for {target_lang}")
            
            print("✓ All models preloaded successfully!")
            
            # Verify models are ready by testing them
            if not self._verify_models_ready():
                print("ERROR: Model verification failed")
                return False
            
            return True
            
        except Exception as e:
            print(f"ERROR: Error preloading models: {e}")
            return False
    
    def _verify_models_ready(self):
        """Verify all models are loaded and ready for processing"""
        print("Verifying models are ready...")
        
        try:
            # Test Whisper model
            test_audio = np.zeros(1600, dtype=np.float32)  # 0.1 second of silence
            segments = transcribe_audio_chunk(test_audio, 16000, self.whisper_model, domain="sports")
            print("✓ Whisper model verified")
            
            # Test MT model
            test_text = "Hello world"
            mt_res = translate(test_text, self.targets[0])
            if 'out' in mt_res:
                print("✓ Translation model verified")
            else:
                print("ERROR: Translation model test failed")
                return False
            
            # Test TTS model for first target language
            if self.targets:
                target_lang = self.targets[0]
                language_config = self.voices.get(target_lang, {})
                model_name = language_config.get("model")
                if model_name and model_name in self.tts_models:
                    # Test TTS with a simple phrase
                    test_tts_text = "Test"
                    speaker = detect_speaker(test_tts_text)
                    model_name, tts_speaker, voice_sample = get_speaker_voice(self.voices, target_lang, speaker)
                    
                    # This is a quick test - we don't need to actually synthesize
                    print(f"✓ TTS model verified for {target_lang}")
                else:
                    print(f"ERROR: TTS model not found for {target_lang}")
                    return False
            
            print("✓ All models verified and ready!")
            return True
            
        except Exception as e:
            print(f"ERROR: Model verification failed: {e}")
            return False
    
    def _process_fragment(self, fragment: Dict[str, Any], data: bytes) -> Optional[bytes]:
        """
        Process a single audio fragment through the full pipeline
        
        Args:
            fragment: Fragment metadata
            data: Binary audio data (m4s format)
            
        Returns:
            Processed audio data (m4s format) or None if processing failed
        """
        try:
            # Extract audio from m4s data using ffmpeg
            # m4s files are MPEG-4 audio containers that need proper parsing
            sample_rate = fragment['sampleRate']
            duration = fragment['duration'] / 1000.0  # Convert ms to seconds
            
            print(f"Processing fragment {fragment['sequenceNumber']}...")
            print(f"Extracting audio from m4s data: {len(data)} bytes")
            
            # Save m4s data to temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.m4s', delete=False) as temp_file:
                temp_file.write(data)
                temp_m4s_path = temp_file.name
            
            try:
                # Extract audio using ffmpeg
                import ffmpeg
                
                print(f"Extracting audio from: {temp_m4s_path}")
                print(f"Target sample rate: {sample_rate} Hz")
                
                # First, probe the file to see what's actually in it
                try:
                    probe = ffmpeg.probe(temp_m4s_path)
                    print("File probe results:")
                    for stream in probe['streams']:
                        if stream['codec_type'] == 'audio':
                            print(f"  Audio stream: {stream['codec_name']}, {stream['sample_rate']}Hz, {stream['channels']} channels")
                            print(f"  Duration: {stream.get('duration', 'unknown')}s")
                except Exception as e:
                    print(f"Probe failed: {e}")
                
                # Extract audio from m4s file - try different approaches
                try:
                    # Method 1: Direct extraction with original parameters
                    out, _ = (
                        ffmpeg
                        .input(temp_m4s_path)
                        .output('pipe:', format='wav', acodec='pcm_s16le', ac=1, ar=sample_rate)
                        .run(capture_stdout=True, quiet=True)
                    )
                    print("✓ Audio extraction successful (Method 1)")
                except Exception as e:
                    print(f"Method 1 failed: {e}")
                    # Method 2: Try with original sample rate
                    try:
                        out, _ = (
                            ffmpeg
                            .input(temp_m4s_path)
                            .output('pipe:', format='wav', acodec='pcm_s16le', ac=1)
                            .run(capture_stdout=True, quiet=True)
                        )
                        print("✓ Audio extraction successful (Method 2 - original sample rate)")
                    except Exception as e2:
                        print(f"Method 2 failed: {e2}")
                        raise e2
                
                # Convert to numpy array
                audio_data = np.frombuffer(out, np.int16).astype(np.float32) / 32768.0
                
                print(f"Extracted audio: {len(audio_data)} samples, {len(audio_data)/sample_rate:.2f}s at {sample_rate}Hz")
                
                # Debug: Analyze audio characteristics
                rms_energy = np.sqrt(np.mean(audio_data ** 2))
                max_amplitude = np.max(np.abs(audio_data))
                print(f"Audio analysis - RMS: {rms_energy:.6f}, Max: {max_amplitude:.6f}")
                
                # Check for repetitive patterns
                if len(audio_data) > 1000:
                    mid_point = len(audio_data) // 2
                    first_half = audio_data[:mid_point]
                    second_half = audio_data[mid_point:mid_point*2] if mid_point*2 <= len(audio_data) else audio_data[mid_point:]
                    
                    if len(first_half) == len(second_half):
                        correlation = np.corrcoef(first_half, second_half)[0, 1]
                        print(f"Audio correlation (first/second half): {correlation:.3f}")
                        
                        if correlation > 0.9:
                            print("WARNING: Audio appears highly repetitive - this might indicate extraction issues!")
                
                # Debug sample generation removed to avoid file clutter
                
            except Exception as e:
                print(f"ERROR: Failed to extract audio from m4s: {e}")
                print("Falling back to test audio signal...")
                
                # Fallback to test audio signal
                t = np.linspace(0, duration, int(sample_rate * duration), False)
                frequency = 440  # A4 note
                audio_data = 0.3 * np.sin(2 * np.pi * frequency * t).astype(np.float32)
                print(f"Created test audio: {len(audio_data)} samples, {duration:.2f}s at {sample_rate}Hz")
                print("NOTE: Using test audio signal as fallback")
            
            finally:
                # Clean up temporary file
                import os
                try:
                    os.unlink(temp_m4s_path)
                except:
                    pass
            
            # Resample audio to 16kHz for Whisper (Whisper expects 16kHz)
            target_sample_rate = 16000
            if sample_rate != target_sample_rate:
                print(f"Resampling audio from {sample_rate}Hz to {target_sample_rate}Hz")
                import librosa
                audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=target_sample_rate)
                sample_rate = target_sample_rate
                
                # Resampled audio file generation removed to avoid file clutter
            
            # Transcribe audio
            t0 = time.time()
            print(f"Sending audio to Whisper: {len(audio_data)} samples, {len(audio_data)/sample_rate:.2f}s")
            print(f"Audio range: {np.min(audio_data):.6f} to {np.max(audio_data):.6f}")
            print(f"Expected fragment duration: {duration:.2f}s")
            
            segments = transcribe_audio_chunk(
                audio_data, 
                sample_rate, 
                self.whisper_model, 
                domain="sports"
            )
            t1 = time.time()
            
            print(f"Whisper returned {len(segments)} segments")
            
            # Calculate speech rate from original audio
            original_duration = len(audio_data) / sample_rate
            total_words = sum(len(seg[2].split()) for seg in segments)
            speech_rate = total_words / original_duration if original_duration > 0 else 0
            print(f"Original speech rate: {speech_rate:.1f} words/second ({total_words} words in {original_duration:.2f}s)")
            
            # Filter segments to only include those within the expected fragment duration
            expected_duration_seconds = duration  # duration is already in seconds
            filtered_segments = []
            for i, (start, end, text, confidence) in enumerate(segments):
                print(f"  Segment {i}: {start:.1f}s-{end:.1f}s: '{text}' (conf: {confidence:.2f})")
                if start < expected_duration_seconds:
                    # Truncate segment if it extends beyond expected duration
                    truncated_end = min(end, expected_duration_seconds)
                    if truncated_end > start:
                        filtered_segments.append((start, truncated_end, text, confidence))
                        print(f"    → Included (truncated to {truncated_end:.1f}s)")
                    else:
                        print(f"    → Excluded (beyond fragment duration)")
                else:
                    print(f"    → Excluded (starts after fragment duration)")
            
            segments = filtered_segments
            print(f"After filtering: {len(segments)} segments within {expected_duration_seconds:.2f}s")
            
            if not segments:
                print("No speech detected in fragment")
                return data  # Return original data if no speech
            
            # Combine all segments into single text
            combined_text = " ".join([seg[2] for seg in segments])
            print(f"Combined transcription: {combined_text[:100]}{'...' if len(combined_text) > 100 else ''}")
            print(f"Transcription time: {t1-t0:.2f}s")
            
            # Process each target language
            processed_audio_data = []
            
            for target_lang in self.targets:
                # Detect speaker
                speaker = detect_speaker(combined_text)
                clean_text = clean_speaker_prefix(combined_text, speaker)
                
                print(f"Processing for {target_lang}: {clean_text}")
                print(f"Speaker: {speaker}")
                
                # Translate text
                t2 = time.time()
                preprocessed_text = preprocess_text_for_translation(clean_text)
                print(f"Processing for {target_lang}: {preprocessed_text[:100]}...")
                print(f"Speaker: {speaker}")
                print(f"Text length: {len(preprocessed_text)} characters")
                
                # Use cache if available
                mt_key = sha1("MT", preprocessed_text, target_lang)
                mt_path = CACHE_DIR / f"{mt_key}.json"
                
                if self.args.no_cache or not mt_path.exists():
                    print(f"Translating text...")
                    mt_res = translate(preprocessed_text, target_lang)
                    print(f"Translation result keys: {mt_res.keys()}")
                    if not self.args.no_cache:
                        mt_path.write_text(
                            json.dumps(mt_res, ensure_ascii=False), 
                            encoding="utf-8"
                        )
                else:
                    print(f"Using cached translation from {mt_path}")
                    mt_res = json.loads(mt_path.read_text("utf-8"))
                
                t3 = time.time()
                print(f"{target_lang}: {mt_res['out']}  (MT {t3-t2:.2f}s)")
                
                # Synthesize audio
                model_name, tts_speaker, voice_sample = get_speaker_voice(
                    self.voices, target_lang, speaker
                )
                
                # Use the same approach as talk_multi_coqui.py: synthesize at normal speed, then post-process
                # This is more effective than trying to use XTTS speed parameter alone
                original_duration = len(audio_data) / sample_rate
                translated_text = mt_res["out"]
                
                print(f"Using post-processing speed adjustment approach:")
                print(f"  Original duration: {original_duration:.1f}s")
                print(f"  Target duration: {original_duration:.1f}s")
                
                
                # Include speed in cache key
                tts_key = sha1("TTS", mt_res["out"], target_lang, model_name, str(tts_speaker), "post_process")
                wav_path = CACHE_DIR / f"{tts_key}.wav"
                
                if self.args.no_cache or not wav_path.exists():
                    # First synthesize at normal speed
                    temp_wav = synth_to_wav(
                        mt_res["out"], 
                        model_name, 
                        speaker=tts_speaker, 
                        target_language=target_lang, 
                        voice_sample_path=voice_sample,
                        speed=1.0  # Always synthesize at normal speed
                    )
                    
                    # Get baseline duration by loading the audio file
                    import soundfile as sf
                    temp_audio, temp_sample_rate = sf.read(str(temp_wav), dtype="float32")
                    baseline_duration = get_audio_duration(temp_audio, temp_sample_rate)
                    print(f"  Baseline TTS duration: {baseline_duration:.2f}s")
                    
                    # Calculate required speed to match original duration
                    required_speed = baseline_duration / original_duration
                    # Clamp speed to reasonable range (0.5x to 3.0x)
                    required_speed = max(0.5, min(3.0, required_speed))
                    
                    print(f"  Required speed adjustment: {required_speed:.2f}x")
                    
                    # Apply speed adjustment via post-processing using Rubber Band
                    wav_path = self._adjust_audio_speed(temp_wav, wav_path, required_speed)
                    
                    # Clean up temp file
                    Path(temp_wav).unlink()
                    
                    if not self.args.no_cache:
                        tmp = wav_path
                        wav_path = CACHE_DIR / f"{tts_key}.wav"
                        Path(tmp).rename(wav_path)
                
                t4 = time.time()
                print(f"TTS {t4-t3:.2f}s")
                
                # Load synthesized audio
                import soundfile as sf
                synthesized_audio, tts_sample_rate = sf.read(str(wav_path), dtype="float32")
                
                # Resample to match original sample rate if needed
                if tts_sample_rate != sample_rate:
                    import librosa
                    synthesized_audio = librosa.resample(
                        synthesized_audio, 
                        orig_sr=tts_sample_rate, 
                        target_sr=sample_rate
                    )
                
                # Use audio at its natural length (no duration normalization)
                final_duration = get_audio_duration(synthesized_audio, sample_rate)
                print(f"TTS audio duration: {final_duration:.2f}s (natural length)")
                
                # Store processed audio fragment for combining at the end
                self.processed_audio_fragments.append(synthesized_audio.copy())
                if self.processed_sample_rate is None:
                    self.processed_sample_rate = sample_rate
                
                # Save individual processed audio chunk for verification
                chunk_filename = f"processed_chunk_{fragment['sequenceNumber']:03d}_{target_lang}.wav"
                chunk_path = self.output_dir / self.stream_id / target_lang / chunk_filename
                chunk_path.parent.mkdir(parents=True, exist_ok=True)
                
                import soundfile as sf
                sf.write(str(chunk_path), synthesized_audio, sample_rate)
                print(f"💾 Saved individual chunk: {chunk_path}")
                print(f"   Duration: {final_duration:.2f}s, Samples: {len(synthesized_audio)}")
                
                # Convert back to int16 format and encode as m4s container
                processed_audio = (synthesized_audio * 32767).astype(np.int16)
                
                # Encode as proper m4s container using ffmpeg (in-memory processing)
                import ffmpeg
                
                try:
                    # Use ffmpeg to create proper m4s container directly from numpy array
                    # Convert numpy array to bytes for ffmpeg input
                    import io
                    import soundfile as sf
                    
                    # Create in-memory WAV data
                    wav_buffer = io.BytesIO()
                    sf.write(wav_buffer, processed_audio, sample_rate, format='WAV')
                    wav_data = wav_buffer.getvalue()
                    
                    # Use ffmpeg with pipe input/output to avoid temporary files
                    out, _ = (
                        ffmpeg
                        .input('pipe:', format='wav')
                        .output('pipe:', 
                               format='mp4',
                               acodec='aac',
                               ar=sample_rate,
                               ac=fragment['channels'],
                               movflags='frag_keyframe+empty_moov')
                        .run(input=wav_data, capture_stdout=True, quiet=True)
                    )
                    
                    processed_audio_bytes = out
                    print(f"Encoded processed audio: {len(processed_audio_bytes)} bytes")
                    
                except Exception as e:
                    print(f"ERROR: Failed to encode m4s container: {e}")
                    # Fallback to simple bytes (not ideal but prevents crashes)
                    processed_audio_bytes = processed_audio.tobytes()
                
                processed_audio_data.append((target_lang, processed_audio_bytes))
                
                # Save locally if requested
                if self.save_local:
                    self._save_processed_fragment(fragment, target_lang, processed_audio_bytes)
            
            # For now, return the first processed audio (could be enhanced to mix multiple languages)
            if processed_audio_data:
                return processed_audio_data[0][1]  # Return first language's audio
            else:
                return data  # Return original if no processing
            
        except Exception as e:
            print(f"ERROR: Error processing fragment: {e}")
            return None
    
    def _save_processed_fragment(self, fragment: Dict[str, Any], target_lang: str, processed_data: bytes):
        """Save processed fragment locally"""
        try:
            # Create filename
            filename = f"fragment-{fragment['sequenceNumber']}.m4s"
            output_path = self.output_dir / self.stream_id / target_lang / filename
            
            # Save audio data
            with open(output_path, 'wb') as f:
                f.write(processed_data)
            
            # Save metadata
            metadata = {
                'fragment_id': fragment['id'],
                'sequence_number': fragment['sequenceNumber'],
                'target_language': target_lang,
                'processed_at': time.time(),
                'original_metadata': fragment,
                'file_size': len(processed_data)
            }
            
            metadata_path = output_path.with_suffix('.json')
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            print(f"Saved: {output_path}")
            
        except Exception as e:
            print(f"ERROR: Error saving fragment: {e}")
    
    def _processing_worker(self):
        """Worker thread for processing fragments"""
        print("Processing worker started")
        while self.running:
            try:
                fragment, data = self.processing_queue.get(timeout=1.0)
                print(f"Processing worker: Starting fragment {fragment['sequenceNumber']}")
                
                # Process the fragment
                processed_data = self._process_fragment(fragment, data)
                
                if processed_data is not None:
                    # Send processed fragment back to server
                    try:
                        self.sio.emit('fragment:processed', {
                            'fragment': fragment,
                            'data': processed_data
                        })
                        print(f"✓ Sent processed fragment {fragment['sequenceNumber']}")
                        self.processed_count += 1
                    except Exception as e:
                        print(f"ERROR: Failed to send processed fragment: {e}")
                        self.failed_count += 1
                else:
                    print(f"✗ Failed to process fragment {fragment['sequenceNumber']}")
                    self.failed_count += 1
                
                # Debug: Show processing status
                print(f"Fragment {fragment['sequenceNumber']} completed. Queue: {self.processing_queue.qsize()}, Processed: {self.processed_count}, Failed: {self.failed_count}, Expected: {self.fragment_count}")
                
                print()  # Empty line between fragments
                
            except queue.Empty:
                # Check if we should stop (no more fragments expected and queue is empty)
                print(f"Queue empty timeout - Connected: {self.connected}, Queue size: {self.processing_queue.qsize()}")
                if not self.connected and self.processing_queue.empty():
                    # Double-check: make sure we've processed all expected fragments
                    if (self.processed_count + self.failed_count) >= self.fragment_count and self.fragment_count > 0:
                        print(f"All fragments processed ({self.processed_count + self.failed_count}/{self.fragment_count}), stopping worker")
                        break
                    else:
                        print(f"Queue empty but not all fragments processed ({self.processed_count + self.failed_count}/{self.fragment_count}), continuing...")
                        # Wait a bit longer for remaining fragments to be processed
                        time.sleep(2)
                continue
            except Exception as e:
                print(f"ERROR: Processing worker error: {e}")
        
        print("Processing worker stopped")
    
    def _adjust_audio_speed(self, input_path: Path, output_path: Path, speed_factor: float) -> Path:
        """
        Adjust audio speed using rubberband for high quality while preserving pitch
        
        Args:
            input_path: Path to input audio file
            output_path: Path to save adjusted audio
            speed_factor: Speed multiplier (1.0 = normal, 2.0 = double speed, 0.5 = half speed)
        
        Returns:
            Path to the adjusted audio file
        """
        import subprocess
        
        # Use rubberband for high-quality time stretching
        cmd = [
            "rubberband",
            "-T", str(speed_factor),  # Tempo change (1/speed_factor for time stretch)
            "-p", "0",                # Keep pitch unchanged (0 semitones)
            "-F",                     # Enable formant preservation
            "-3",                     # Use R3 (finer) engine for best quality
            str(input_path),
            str(output_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Warning: rubberband failed: {result.stderr}")
            print("Falling back to copying original file")
            # Fallback: just copy the original file
            import shutil
            shutil.copy2(input_path, output_path)
        
        return output_path
    
    def _combine_and_save_processed_audio(self):
        """Combine all processed audio fragments into a single WAV file"""
        if not self.processed_audio_fragments:
            print("No processed audio fragments to combine")
            return
        
        print(f"\n🎵 Combining {len(self.processed_audio_fragments)} processed audio fragments...")
        
        try:
            # Combine all audio fragments
            combined_audio = np.concatenate(self.processed_audio_fragments)
            total_duration = len(combined_audio) / self.processed_sample_rate
            
            print(f"Combined audio: {len(combined_audio)} samples, {total_duration:.2f}s at {self.processed_sample_rate}Hz")
            
            # Save as WAV file
            output_filename = f"combined_processed_audio_natural_{self.stream_id}_{int(time.time())}.wav"
            output_path = self.output_dir / output_filename
            
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save the combined audio
            import soundfile as sf
            sf.write(str(output_path), combined_audio, self.processed_sample_rate)
            
            print(f"✅ Combined audio saved: {output_path}")
            print(f"   Duration: {total_duration:.2f}s")
            print(f"   Sample rate: {self.processed_sample_rate}Hz")
            print(f"   Channels: {combined_audio.shape[1] if len(combined_audio.shape) > 1 else 1}")
            
        except Exception as e:
            print(f"❌ Error combining audio fragments: {e}")
    
    def run(self):
        """Main run method"""
        print("=" * 60)
        print("Live Audio Stream Processing Client")
        print("=" * 60)
        print(f"Server URL: {self.server_url}")
        print(f"Stream ID: {self.stream_id}")
        print(f"Target languages: {', '.join(self.targets)}")
        print(f"Save locally: {self.save_local}")
        if self.save_local:
            print(f"Output directory: {self.output_dir}")
        print("=" * 60)
        
        try:
            # Preload models
            if not self._preload_models():
                print("ERROR: Failed to preload models, aborting")
                return
            
            # Start processing thread
            self.running = True
            self.processing_thread = threading.Thread(target=self._processing_worker)
            self.processing_thread.start()
            print("✓ Processing thread started")
            
            # Connect to server
            print(f"Connecting to {self.server_url}...")
            self.sio.connect(self.server_url)
            
            # Wait for completion
            self.sio.wait()
            
        except KeyboardInterrupt:
            print("\nProcessing interrupted by user")
        except Exception as e:
            print(f"ERROR: {e}")
        finally:
            self._cleanup()
    
    def _cleanup(self):
        """Clean up resources"""
        self.running = False
        
        if self.processing_thread:
            self.processing_thread.join()
        
        # Combine and save all processed audio fragments
        self._combine_and_save_processed_audio()
        
        if self.connected:
            try:
                self.sio.disconnect()
            except Exception as e:
                print(f"Warning: Error during disconnect: {e}")
        
        print("✓ Cleanup complete")

def main():
    """Main entry point"""
    print("Starting main entry point")
    ap = argparse.ArgumentParser(description="Live Audio Stream Processing Client")
    ap.add_argument("--server-url", default="ws://localhost:4000", help="Socket.IO server URL")
    ap.add_argument("--stream-id", default="stream-1", help="Stream ID to subscribe to")
    ap.add_argument("--targets", "-t", default="es", help="Comma-separated target languages")
    ap.add_argument("--config", "-c", default="coqui-voices.yaml", help="Voice configuration YAML")
    ap.add_argument("--save-local", action="store_true", help="Save processed fragments locally")
    ap.add_argument("--output-dir", default="./processed_fragments", help="Directory for saved fragments")
    ap.add_argument("--whisper-model", default="base", help="Whisper model size")
    ap.add_argument("--device", default="cpu", help="Processing device")
    ap.add_argument("--no-cache", action="store_true", help="Disable caching")
    
    args = ap.parse_args()
    
    # Load configuration
    cfg = load_cfg(args.config)
    voices = cfg.get("languages", {})
    
    # Set up voice samples directory
    voices = setup_voice_samples(voices, cfg.get("voice_samples", {}).get("directory", "./voice_samples"))
    
    # Validate targets
    targets = [t.strip() for t in args.targets.split(",") if t.strip()]
    missing = [t for t in targets if t not in voices]
    if missing:
        print(f"ERROR: No Coqui voice configured for: {', '.join(missing)}")
        print(f"Add them under 'languages:' in {args.config}.")
        sys.exit(2)
    
    # Check Whisper model availability
    if get_whisper_model(args.whisper_model, args.device) is None:
        print("ERROR: Failed to load Whisper model. Check installation.")
        sys.exit(1)
    
    # Create and run processor
    processor = LiveStreamProcessor(args)
    processor.voices = voices
    processor.run()

if __name__ == "__main__":
    main()
