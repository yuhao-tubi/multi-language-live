#!/usr/bin/env python3
"""
Simplified Fast Audio Server - VITS Only

This is a simplified version of the streaming audio client that only uses VITS models
to isolate and fix the TTS synthesis error. It replicates the exact protocol from
stream_audio_client.py but forces the use of fast_model (VITS) for all languages.

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
from flask import Flask
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


class SimpleVITSServer:
    """
    Simplified server that replicates stream_audio_client.py exactly but forces VITS models
    """
    
    def __init__(self, args):
        print(f"Initializing SimpleVITSServer with args: {args}")
        self.args = args
        
        # Single target language optimization
        targets_list = [t.strip() for t in args.targets.split(",") if t.strip()]
        if len(targets_list) != 1:
            raise ValueError(f"Single target language required, got: {targets_list}")
        self.target_lang = targets_list[0]
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
        self.voices = {}
        
        # Processing queue for async processing (EXACTLY like stream_audio_client.py)
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
        """Setup output directory structure for local saving (single language)"""
        lang_dir = self.output_dir / self.target_lang
        lang_dir.mkdir(parents=True, exist_ok=True)
        print(f"Created output directory: {lang_dir}")
    
    def _setup_socket_handlers(self):
        """Setup Socket.IO server event handlers (EXACTLY like stream_audio_client.py)"""
        
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
            """Handle incoming audio fragment from client (EXACTLY like stream_audio_client.py)"""
            fragment = delivery['fragment']
            data = delivery['data']
            
            self.fragment_count += 1
            
            # Update client stats
            if sid in self.connected_clients:
                self.connected_clients[sid]['fragments_received'] += 1
            
            print(f"📦 Fragment {self.fragment_count} Received from {sid}:")
            print(f"  ID: {fragment['id']}")
            print(f"  Stream: {fragment['streamId']}")
            print(f"  Batch: {fragment['batchNumber']}")
            print(f"  Size: {len(data):,} bytes ({len(data) / 1024:.2f} KB)")
            print(f"  Duration: {fragment['duration']}s")
            
            # Add to processing queue for background processing
            # Include sid so we can send response back to correct client
            self.processing_queue.put((sid, fragment, data))
            print(f"  → Added to processing queue")
    
    
    def _preload_models(self):
        """Preload all models before starting (EXACTLY like stream_audio_client.py)"""
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
            
            # Load TTS model for single target language - FORCE VITS (fast_model)
            print(f"Loading TTS model for {self.target_lang}...")
            language_config = self.voices.get(self.target_lang, {})
            
            # ALWAYS use fast_model (VITS) - this is the key difference
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
        """Sequential processing worker - maintains fragment order (EXACTLY like stream_audio_client.py)"""
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
        """Process a single fragment (EXACTLY like stream_audio_client.py)"""
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
            
            # Detect speaker
            speaker = detect_speaker(combined_text)
            print(f"Speaker: {speaker}")
            
            # Clean text for translation
            clean_text = clean_speaker_prefix(combined_text, speaker)
            
            # Translate
            print("Translating text...")
            preprocessed_text = preprocess_text_for_translation(clean_text)
            mt_res = translate(preprocessed_text, self.target_lang, self.args.device)
            translated_text = mt_res['out']
            print(f"{self.target_lang}: {translated_text}")
            
            # TTS synthesis - use the exact same function as stream_audio_client.py
            print("Synthesizing audio...")
            wav_path = synth_to_wav(translated_text, self.actual_tts_model, speaker=None, target_language=self.target_lang, voice_sample_path=None)
            
            if not wav_path or not wav_path.exists():
                print("TTS synthesis failed, returning original audio")
                return self._encode_audio(audio_data, actual_sample_rate)
            
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
            
            # Encode as m4s
            return self._encode_audio(synthesized_audio, actual_sample_rate)
            
        except Exception as e:
            print(f"ERROR: Error processing fragment: {e}")
            return None
    
    def _encode_audio(self, audio_data: np.ndarray, sample_rate: int) -> bytes:
        """Encode audio data as m4s container (EXACTLY like stream_audio_client.py)"""
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
        """Start the Socket.IO server (EXACTLY like stream_audio_client.py)"""
        print("=" * 60)
        print("Simple VITS Audio Processing Server")
        print("=" * 60)
        print(f"Host: {self.host}")
        print(f"Port: {self.port}")
        print(f"Target language: {self.target_lang}")
        print(f"TTS model: {self.voices[self.target_lang]['fast_model']}")
        print("=" * 60)
        
        # Preload models
        if not self._preload_models():
            print("ERROR: Failed to preload models")
            return
        
        print("Starting Simple VITS server...")
        self.running = True
        
        # Start background processing thread (EXACTLY like stream_audio_client.py)
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
    parser.add_argument("--save-local", action="store_true", help="Save processed fragments locally")
    parser.add_argument("--output-dir", default="./processed_fragments", help="Output directory for local saves")
    parser.add_argument("--config", "-c", default="coqui-voices.yaml", help="Voice configuration file")
    parser.add_argument("--whisper-model", default="base", help="Whisper model size")
    parser.add_argument("--device", default="cpu", help="Processing device")
    
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
    server = SimpleVITSServer(args)
    server.voices = voices
    server.start_server()


if __name__ == "__main__":
    main()