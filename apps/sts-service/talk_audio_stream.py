#!/usr/bin/env python3
"""
Real-Time Audio Streaming Transcription and Translation

This script transcribes audio/video files in real-time using faster-whisper,
feeds transcribed segments to the existing translation/TTS pipeline, and
provides delayed playback with audio mixing for synchronized dubbing.

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
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from rich.console import Console
import yaml

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

# Import new audio streaming utilities
from utils.transcription import (
    get_whisper_model
)
from utils.audio_streaming import (
    load_audio_file,
    create_audio_mixer,
    DelayedAudioPlayer,
    overlay_audio_on_video,
    create_silence
)
from utils.voice_management import setup_voice_samples

console = Console()

class AudioStreamProcessor:
    """
    Main processor for real-time audio streaming with transcription and translation
    """
    
    def __init__(self, targets: List[str], voices: Dict, args):
        self.targets = targets
        self.voices = voices
        self.args = args
        self.delay = getattr(args, 'delay', 8.0)
        self.mix_volume = getattr(args, 'mix_volume', 0.8)
        
        # Threading components
        self.transcription_queue = queue.Queue()
        self.translation_queue = queue.Queue()
        self.audio_queue = queue.Queue()
        self.running = False
        
        # Audio components
        self.delayed_player = None
        self.original_audio = None
        self.sample_rate = None
        self.mixed_audio = None
        self.playback_started = False
        
        # Pre-loaded models
        self.whisper_model = None
        self.tts_models = {}  # Cache for TTS models
        self.mt_model = None
        
        # Real-time utterance detection state
        self.audio_buffer = np.array([])  # Buffer for incoming audio
        self.buffer_duration = 2.0  # Keep 2 seconds of audio in buffer
        self.buffer_samples = int(self.buffer_duration * 16000)  # Will be updated with actual sample rate
        self.last_processed_time = 0.0
        self.current_utterance_start = None
        self.silence_start_time = None
        self.in_silence = False
        self.energy_history = []  # Track energy history for adaptive threshold
        self.max_energy_history = 50  # Keep last 50 energy measurements
        
        # Sequential audio placement to prevent overlaps
        self.last_audio_end_time = 0.0  # Track where the last translated audio ended
        
        
        # Processing threads
        self.transcription_thread = None
        self.translation_thread = None
        self.audio_thread = None
        self.playback_thread = None
        
    def process_audio_file(self, audio_path: str):
        """
        Process audio file with real-time transcription and translation
        
        Args:
            audio_path: Path to audio/video file
        """
        console.print(f"[green]Processing audio file: {audio_path}[/green]")
        console.print(f"[green]Target languages:[/green] " + ", ".join(f"[bold]{t}[/bold]" for t in self.targets))
        console.print(f"[green]Delay: {self.delay}s, Mix volume: {self.mix_volume}[/green]")
        console.print("[yellow]Press Ctrl+C to stop processing[/yellow]\n")
        
        try:
            # Load audio file
            self.original_audio, self.sample_rate = load_audio_file(audio_path)
            
            # Preload all models before starting
            if not self._preload_models():
                console.print("[red]Failed to preload models, aborting[/red]")
                return
            
            # Initialize components
            self.delayed_player = DelayedAudioPlayer(self.delay, self.sample_rate)
            
            # Initialize mixed audio track
            self.mixed_audio = self.original_audio.copy()
            
            # Start processing
            self.running = True
            self._start_threads()
            
            # Start transcription
            self._start_transcription()
            
            # Wait for completion or interruption
            self._wait_for_completion()
            
            # Save mixed audio to temporary file for video overlay
            self._save_mixed_audio()
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Processing interrupted by user[/yellow]")
        except Exception as e:
            console.print(f"[red]Error processing audio: {e}[/red]")
        finally:
            self._cleanup()
    
    def _start_threads(self):
        """Start all processing threads"""
        # Translation thread
        self.translation_thread = threading.Thread(target=self._translation_worker)
        self.translation_thread.start()
        
        # Audio processing thread
        self.audio_thread = threading.Thread(target=self._audio_worker)
        self.audio_thread.start()
        
        # Real-time playback thread
        self.playback_thread = threading.Thread(target=self._playback_worker)
        self.playback_thread.start()
        
        # Note: Delayed player not needed with mixed audio approach
        
        console.print("[green]Started all processing threads[/green]")
    
    def _preload_models(self):
        """Preload all models before starting playback"""
        console.print("[green]Preloading models...[/green]")
        
        try:
            # Load Whisper model
            console.print("[dim]Loading Whisper model...[/dim]")
            from utils.transcription import get_whisper_model
            self.whisper_model = get_whisper_model(
                getattr(self.args, 'whisper_model', 'base'),
                getattr(self.args, 'device', 'cpu')
            )
            if self.whisper_model is None:
                console.print("[red]Failed to load Whisper model[/red]")
                return False
            console.print("[green]✓ Whisper model loaded[/green]")
            
            # Load MT model
            console.print("[dim]Loading translation model...[/dim]")
            from talk_multi_coqui import get_mt
            self.mt_model = get_mt()
            console.print("[green]✓ Translation model loaded[/green]")
            
            # Load TTS models for each target language
            console.print("[dim]Loading TTS models...[/dim]")
            from talk_multi_coqui import get_tts
            for target_lang in self.targets:
                language_config = self.voices.get(target_lang, {})
                model_name = language_config.get("model")
                if model_name and model_name not in self.tts_models:
                    console.print(f"[dim]Loading TTS model for {target_lang}: {model_name}[/dim]")
                    self.tts_models[model_name] = get_tts(model_name)
                    console.print(f"[green]✓ TTS model loaded for {target_lang}[/green]")
            
            console.print("[green]All models preloaded successfully![/green]")
            return True
            
        except Exception as e:
            console.print(f"[red]Error preloading models: {e}[/red]")
            return False
    
    def _detect_utterance_boundaries_realtime(self, current_timestamp: float):
        """
        Detect utterance boundaries in real-time using adaptive silence detection.
        
        This function analyzes audio energy in real-time to identify natural speech segments.
        It uses adaptive thresholds based on recent audio history to handle varying noise levels
        and implements multiple strategies for utterance boundary detection:
        
        1. Silence-based detection: Ends utterances after sufficient silence
        2. Duration-based detection: Forces breaks for overly long utterances
        3. Adaptive thresholds: Adjusts sensitivity based on ambient audio levels
        
        Args:
            current_timestamp: Current time in the audio stream (seconds)
        """
        if len(self.audio_buffer) < self.buffer_samples:
            return
        
        # Calculate RMS energy for recent audio (last 500ms)
        recent_audio = self.audio_buffer[-int(0.5 * self.sample_rate):]
        rms_energy = np.sqrt(np.mean(recent_audio ** 2))
        
        # Maintain rolling energy history for adaptive threshold calculation
        self.energy_history.append(rms_energy)
        if len(self.energy_history) > self.max_energy_history:
            self.energy_history.pop(0)
        
        # Calculate adaptive threshold based on recent energy history
        # This helps handle varying background noise levels
        if len(self.energy_history) >= 10:  # Need sufficient history
            avg_energy = np.mean(self.energy_history[-10:])  # Last 10 measurements
            adaptive_threshold = avg_energy * 0.3  # 30% of average energy
        else:
            adaptive_threshold = 0.01  # Conservative fallback threshold
        
        # Utterance boundary detection parameters
        min_silence_duration = 0.2  # Minimum silence to end utterance (reduced for responsiveness)
        min_utterance_duration = 0.5  # Minimum utterance length to avoid fragments
        max_utterance_duration = 8.0   # Maximum utterance length - force break for efficiency
        
        # Debug logging every 2 seconds
        if int(current_timestamp) % 2 == 0 and current_timestamp - int(current_timestamp) < 0.1:
            console.print(f"[dim]RMS: {rms_energy:.4f}, Adaptive threshold: {adaptive_threshold:.4f}, In silence: {self.in_silence}[/dim]")
        
        # Check if current utterance is too long and force a break
        if self.current_utterance_start is not None:
            current_utterance_duration = current_timestamp - self.current_utterance_start
            if current_utterance_duration >= max_utterance_duration:
                # Force utterance break due to length
                console.print(f"[yellow]Forcing utterance break at {current_timestamp:.1f}s (duration: {current_utterance_duration:.1f}s)[/yellow]")
                self._add_completed_utterance(self.current_utterance_start, current_timestamp)
                self.current_utterance_start = None
        
        # Detect silence/speech transitions
        if rms_energy < adaptive_threshold:
            if not self.in_silence:
                # Transition to silence
                self.in_silence = True
                self.silence_start_time = current_timestamp
                console.print(f"[dim]Silence started at {current_timestamp:.1f}s (RMS: {rms_energy:.4f} < {adaptive_threshold:.4f})[/dim]")
        else:
            if self.in_silence:
                # Transition from silence to speech
                self.in_silence = False
                silence_duration = current_timestamp - self.silence_start_time
                console.print(f"[dim]Speech resumed at {current_timestamp:.1f}s after {silence_duration:.1f}s silence[/dim]")
                
                # If we had a long enough silence, end the current utterance
                if silence_duration >= min_silence_duration and self.current_utterance_start is not None:
                    utterance_duration = self.silence_start_time - self.current_utterance_start
                    if utterance_duration >= min_utterance_duration:
                        # Complete utterance detected
                        console.print(f"[green]Complete utterance: {self.current_utterance_start:.1f}s - {self.silence_start_time:.1f}s ({utterance_duration:.1f}s)[/green]")
                        self._add_completed_utterance(self.current_utterance_start, self.silence_start_time)
                    
                    self.current_utterance_start = None
                
                # Start new utterance
                if self.current_utterance_start is None:
                    self.current_utterance_start = current_timestamp
                    console.print(f"[green]New utterance started at {current_timestamp:.1f}s[/green]")
            elif self.current_utterance_start is None and rms_energy > adaptive_threshold * 1.5:
                # Start utterance if we're not in silence and no current utterance
                self.current_utterance_start = current_timestamp
                console.print(f"[green]Initial utterance started at {current_timestamp:.1f}s[/green]")
    
    def _add_completed_utterance(self, start_time: float, end_time: float):
        """Add a completed utterance to the processing queue"""
        utterance_audio = self.original_audio[int(start_time * self.sample_rate):int(end_time * self.sample_rate)]
        self.transcription_queue.put((start_time, end_time, utterance_audio))
    
    def _process_completed_utterances(self):
        """Process any completed utterances from the queue"""
        while not self.transcription_queue.empty():
            try:
                start_time, end_time, utterance_audio = self.transcription_queue.get_nowait()
                
                console.print(f"[dim]Processing utterance at {start_time:.1f}s - {end_time:.1f}s[/dim]")
                
                # Transcribe this utterance
                segments = self._transcribe_chunk(utterance_audio, start_time)
                
                for start_time_seg, end_time_seg, text, confidence in segments:
                    if not self.running:
                        break
                        
                    # Color-code confidence levels
                    if confidence >= 0.8:
                        conf_color = "green"
                    elif confidence >= 0.6:
                        conf_color = "yellow"
                    else:
                        conf_color = "red"
                    
                    console.print(f"[bold]Transcribed:[/bold] {text}")
                    console.print(f"[dim]Time: {start_time_seg:.1f}s - {end_time_seg:.1f}s, Confidence: [{conf_color}]{confidence:.2f}[/{conf_color}][/dim]")
                    
                    # Add to translation queue
                    self.translation_queue.put((start_time_seg, end_time_seg, text))
                    
            except queue.Empty:
                break
    
    def _start_transcription(self):
        """Start transcription process with real-time utterance detection"""
        console.print("[green]Starting real-time utterance detection...[/green]")
        
        # Update buffer size with actual sample rate
        self.buffer_samples = int(self.buffer_duration * self.sample_rate)
        
        # Process audio in real-time chunks for utterance detection
        chunk_duration = 0.5  # Process 500ms chunks for real-time detection
        chunk_samples = int(chunk_duration * self.sample_rate)
        
        # Start processing from the beginning and follow the audio timeline
        start_time = time.time()
        
        for chunk_start in range(0, len(self.original_audio), chunk_samples):
            if not self.running:
                break
            
            # Calculate when this chunk should be processed based on audio timeline
            chunk_timestamp = chunk_start / self.sample_rate
            current_time = time.time()
            elapsed_time = current_time - start_time
            
            # Wait until it's time to process this chunk (real-time streaming)
            if chunk_timestamp > elapsed_time:
                wait_time = chunk_timestamp - elapsed_time
                console.print(f"[dim]Waiting {wait_time:.1f}s to process chunk at {chunk_timestamp:.1f}s...[/dim]")
                time.sleep(wait_time)
            
            # Extract chunk
            chunk_end = min(chunk_start + chunk_samples, len(self.original_audio))
            audio_chunk = self.original_audio[chunk_start:chunk_end]
            
            # Add chunk to buffer
            self.audio_buffer = np.concatenate([self.audio_buffer, audio_chunk])
            
            # Keep only recent audio in buffer
            if len(self.audio_buffer) > self.buffer_samples:
                self.audio_buffer = self.audio_buffer[-self.buffer_samples:]
            
            # Detect utterance boundaries in real-time
            self._detect_utterance_boundaries_realtime(chunk_timestamp)
            
            # Process completed utterances
            self._process_completed_utterances()
        
        # Process any remaining utterance at the end
        if self.current_utterance_start is not None:
            final_end_time = len(self.original_audio) / self.sample_rate
            utterance_duration = final_end_time - self.current_utterance_start
            if utterance_duration >= 0.3:  # Minimum utterance duration
                console.print(f"[green]Final utterance: {self.current_utterance_start:.1f}s - {final_end_time:.1f}s ({utterance_duration:.1f}s)[/green]")
                self._add_completed_utterance(self.current_utterance_start, final_end_time)
                self._process_completed_utterances()
        
        console.print("[green]Real-time transcription complete[/green]")
    
    def _save_mixed_audio(self):
        """Save the mixed audio to a temporary file for video overlay"""
        try:
            import soundfile as sf
            sf.write("temp_mixed_audio.wav", self.mixed_audio, self.sample_rate)
            console.print("[green]Saved mixed audio to temp_mixed_audio.wav[/green]")
        except Exception as e:
            console.print(f"[red]Error saving mixed audio: {e}[/red]")
    
    def _transcribe_chunk(self, audio_chunk: np.ndarray, chunk_timestamp: float) -> List[Tuple[float, float, str, float]]:
        """Transcribe a single audio chunk using preloaded model"""
        try:
            from utils.transcription import transcribe_audio_chunk
            
            if self.whisper_model is None:
                console.print("[red]Whisper model not loaded[/red]")
                return []
            
            segments = transcribe_audio_chunk(audio_chunk, self.sample_rate, self.whisper_model, domain="sports")
            
            # Adjust timestamps to absolute time
            adjusted_segments = []
            for seg_start, seg_end, text, confidence in segments:
                abs_start = chunk_timestamp + seg_start
                abs_end = chunk_timestamp + seg_end
                adjusted_segments.append((abs_start, abs_end, text, confidence))
            
            return adjusted_segments
            
        except Exception as e:
            console.print(f"[red]Chunk transcription error: {e}[/red]")
            return []
    
    def _translation_worker(self):
        """Worker thread for translation and TTS"""
        while self.running:
            try:
                start_time, end_time, text = self.translation_queue.get(timeout=1.0)
                
                # Detect speaker
                speaker = detect_speaker(text)
                clean_text = clean_speaker_prefix(text, speaker)
                
                console.print(f"[bold]Processing segment:[/bold] {clean_text}")
                console.print(f"[dim]Speaker: {speaker}[/dim]")
                
                # Process each target language
                for target_lang in self.targets:
                    # Get voice configuration
                    model_name, tts_speaker, voice_sample = get_speaker_voice(self.voices, target_lang, speaker)
                    
                    # Translate text using preloaded model
                    t0 = time.time()
                    preprocessed_text = preprocess_text_for_translation(clean_text)
                    
                    # Use cache if available
                    mt_key = sha1("MT", preprocessed_text, target_lang)
                    mt_path = CACHE_DIR / f"{mt_key}.json"
                    
                    if self.args.no_cache or not mt_path.exists():
                        # Use preloaded MT model
                        mt_res = translate(preprocessed_text, target_lang)
                        if not self.args.no_cache:
                            mt_path.write_text(
                                json.dumps(mt_res, ensure_ascii=False), 
                                encoding="utf-8"
                            )
                    else:
                        import json
                        mt_res = json.loads(mt_path.read_text("utf-8"))
                    
                    t1 = time.time()
                    console.print(f"[bold]{target_lang}[/bold]: {mt_res['out']}  [dim](MT {t1-t0:.2f}s)[/dim]")
                    
                    # Synthesize audio using preloaded TTS model
                    tts_key = sha1("TTS", mt_res["out"], target_lang, model_name, str(tts_speaker))
                    wav_path = CACHE_DIR / f"{tts_key}.wav"
                    
                    if self.args.no_cache or not wav_path.exists():
                        # Use preloaded TTS model
                        wav_path = synth_to_wav(mt_res["out"], model_name, speaker=tts_speaker, target_language=target_lang, voice_sample_path=voice_sample)
                        
                        if not self.args.no_cache:
                            tmp = wav_path
                            wav_path = CACHE_DIR / f"{tts_key}.wav"
                            Path(tmp).rename(wav_path)
                    
                    t2 = time.time()
                    console.print(f"[dim]TTS {t2-t1:.2f}s → adding to audio queue[/dim]")
                    
                    # Add to audio queue for mixing
                    self.audio_queue.put((start_time, end_time, wav_path, target_lang))
                
                console.print()  # Empty line between segments
                
            except queue.Empty:
                continue
            except Exception as e:
                console.print(f"[red]Translation worker error: {e}[/red]")
    
    def _audio_worker(self):
        """Worker thread for audio mixing and playback"""
        while self.running:
            try:
                start_time, end_time, wav_path, target_lang = self.audio_queue.get(timeout=1.0)
                
                # Load synthesized audio
                import soundfile as sf
                translated_audio, tts_sample_rate = sf.read(str(wav_path), dtype="float32")
                
                # Resample to match our target sample rate if needed
                if tts_sample_rate != self.sample_rate:
                    import librosa
                    translated_audio = librosa.resample(translated_audio, orig_sr=tts_sample_rate, target_sr=self.sample_rate)
                
                # Use natural duration of translated audio instead of forcing original duration
                # This prevents Spanish lines from being cut off
                translated_duration = len(translated_audio) / self.sample_rate
                console.print(f"[dim]Translated audio duration: {translated_duration:.2f}s (original: {end_time-start_time:.2f}s)[/dim]")
                
                # Sequential audio placement to prevent overlaps
                # Place translated audio after the last translated audio ended
                sequential_start_time = max(start_time, self.last_audio_end_time)
                sequential_end_time = sequential_start_time + translated_duration
                
                # Update the last audio end time for next segment
                self.last_audio_end_time = sequential_end_time
                
                # Mix translated audio into the main track with sequential placement
                start_sample = int(sequential_start_time * self.sample_rate)
                end_sample = start_sample + len(translated_audio)
                
                # Extend mixed audio track if translated audio extends beyond current length
                if end_sample > len(self.mixed_audio):
                    # Extend the mixed audio track to accommodate longer translated audio
                    extension_samples = end_sample - len(self.mixed_audio)
                    extension_audio = np.zeros(extension_samples, dtype=np.float32)
                    self.mixed_audio = np.concatenate([self.mixed_audio, extension_audio])
                    console.print(f"[dim]Extended mixed audio track by {extension_samples/self.sample_rate:.2f}s[/dim]")
                
                # Mix with original audio (reduce original volume)
                original_volume = 1.0 - self.mix_volume
                translated_volume = self.mix_volume
                
                # Apply volume levels
                self.mixed_audio[start_sample:end_sample] = (
                    self.mixed_audio[start_sample:end_sample] * original_volume +
                    translated_audio * translated_volume
                )
                
                console.print(f"[dim]Mixed {target_lang} audio at {sequential_start_time:.1f}s for {translated_duration:.2f}s (vol: {translated_volume:.1f})[/dim]")
                
            except queue.Empty:
                continue
            except Exception as e:
                console.print(f"[red]Audio worker error: {e}[/red]")
    
    def _playback_worker(self):
        """Worker thread for real-time audio playback"""
        console.print("[green]Starting real-time audio playback...[/green]")
        
        try:
            import sounddevice as sd
            
            # Wait for some translation to complete before starting playback
            time.sleep(self.delay)
            
            # Play the mixed audio track (original + translated)
            console.print("[green]Playing mixed audio track...[/green]")
            sd.play(self.mixed_audio, self.sample_rate)
            sd.wait()  # Wait for entire audio to finish
            
            console.print("[green]Mixed audio playback completed[/green]")
            
        except Exception as e:
            console.print(f"[red]Playback worker error: {e}[/red]")
    
    def _wait_for_completion(self):
        """Wait for processing to complete"""
        # Wait for transcription to complete
        while not self.transcription_queue.empty():
            time.sleep(0.1)
        
        # Wait for translation to complete
        while not self.translation_queue.empty():
            time.sleep(0.1)
        
        # Wait for audio processing to complete
        while not self.audio_queue.empty():
            time.sleep(0.1)
        
        console.print("\n[bold]Processing complete![/bold]")
    
    def _cleanup(self):
        """Clean up resources"""
        self.running = False
        
        if self.translation_thread:
            self.translation_thread.join()
        if self.audio_thread:
            self.audio_thread.join()
        if self.playback_thread:
            self.playback_thread.join()
        # Note: No delayed player cleanup needed
        
        console.print("[green]Cleanup complete[/green]")

def main():
    """Main entry point"""
    ap = argparse.ArgumentParser(description="Real-time audio streaming transcription and translation")
    ap.add_argument("--audio", "-a", required=True, help="Path to audio/video file")
    ap.add_argument("--targets", "-t", default="es", help="Comma-separated target languages: es,fr,de,…")
    ap.add_argument("--config", "-c", default="coqui-voices.yaml", help="YAML mapping langs->Coqui model")
    ap.add_argument("--no-cache", action="store_true", default=True, help="Disable translation/audio cache")
    ap.add_argument("--delay", "-d", type=float, default=8.0, help="Playback delay in seconds (default: 8.0)")
    ap.add_argument("--mix-volume", "-v", type=float, default=0.8, help="Volume level for translated audio (0.0-1.0)")
    ap.add_argument("--whisper-model", default="base", help="Whisper model size (tiny,base,small,medium,large)")
    ap.add_argument("--device", default="cpu", help="Device for Whisper (cpu,cuda,mps)")
    ap.add_argument("--output", "-o", help="Output video file path (optional)")
    
    args = ap.parse_args()
    
    # Load configuration
    cfg = load_cfg(args.config)
    voices = cfg.get("languages", {})
    targets = [t.strip() for t in args.targets.split(",") if t.strip()]
    
    # Set up voice samples directory and validate existing samples
    voices = setup_voice_samples(voices, cfg.get("voice_samples", {}).get("directory", "./voice_samples"))
    
    # Validate targets
    missing = [t for t in targets if t not in voices]
    if missing:
        console.print(f"[red]No Coqui voice configured for: {', '.join(missing)}[/red]")
        console.print(f"Add them under 'languages:' in {args.config}.")
        sys.exit(2)
    
    # Validate audio file
    if not Path(args.audio).exists():
        console.print(f"[red]Audio file not found: {args.audio}[/red]")
        sys.exit(1)
    
    # Check Whisper model availability
    if get_whisper_model(args.whisper_model, args.device) is None:
        console.print("[red]Failed to load Whisper model. Check installation.[/red]")
        sys.exit(1)
    
    # Process audio file
    processor = AudioStreamProcessor(targets, voices, args)
    processor.process_audio_file(args.audio)
    
    # Create output video if requested
    if args.output:
        console.print(f"[green]Creating output video: {args.output}[/green]")
        try:
            overlay_audio_on_video(args.audio, "temp_mixed_audio.wav", args.output, args.mix_volume)
        except Exception as e:
            console.print(f"[red]Error creating output video: {e}[/red]")

if __name__ == "__main__":
    main()
