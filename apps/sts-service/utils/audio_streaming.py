#!/usr/bin/env python3
"""
Audio Streaming and Mixing Utilities

This module provides audio loading, mixing, and playback capabilities for
real-time audio processing with delayed playback and audio overlay.

Author: Philip Baillargeon (Assistance by Cursor/GPT)
"""

import numpy as np
import threading
import queue
import time
import tempfile
from pathlib import Path
from typing import Tuple, Optional, List, Callable
from rich.console import Console

try:
    import ffmpeg
    import sounddevice as sd
    import soundfile as sf
    from pydub import AudioSegment
    from pydub.playback import play
except ImportError as e:
    console = Console()
    console.print(f"[red]Missing audio dependencies: {e}[/red]")
    console.print("[yellow]Install with: pip install ffmpeg-python sounddevice soundfile pydub[/yellow]")

console = Console()

def load_audio_file(file_path: str, target_sample_rate: int = 16000) -> Tuple[np.ndarray, int]:
    """
    Load audio from file (supports video files via ffmpeg)
    
    Args:
        file_path: Path to audio/video file
        target_sample_rate: Target sample rate for output
        
    Returns:
        Tuple of (audio_data, sample_rate)
    """
    try:
        # Check if file exists
        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Extract audio from file (supports video files)
        probe = ffmpeg.probe(file_path)
        audio_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'audio'), None)
        
        if audio_stream is None:
            raise ValueError(f"No audio stream found in {file_path}")
        
        # Extract audio as numpy array
        out, _ = (
            ffmpeg
            .input(file_path)
            .output('pipe:', format='wav', acodec='pcm_s16le', ac=1, ar=target_sample_rate)
            .run(capture_stdout=True, quiet=True)
        )
        
        audio_data = np.frombuffer(out, np.int16).astype(np.float32) / 32768.0
        
        console.print(f"[green]Loaded audio: {len(audio_data)/target_sample_rate:.1f}s at {target_sample_rate}Hz[/green]")
        return audio_data, target_sample_rate
        
    except Exception as e:
        console.print(f"[red]Error loading audio file {file_path}: {e}[/red]")
        raise

def create_audio_mixer(sample_rate: int = 16000, channels: int = 1) -> 'AudioMixer':
    """
    Create an audio mixer for real-time audio mixing
    
    Args:
        sample_rate: Sample rate for audio processing
        channels: Number of audio channels
        
    Returns:
        AudioMixer instance
    """
    return AudioMixer(sample_rate, channels)

class AudioMixer:
    """
    Real-time audio mixer for combining multiple audio streams
    """
    
    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.audio_tracks = {}  # Track name -> audio data
        self.volume_levels = {}  # Track name -> volume (0.0-1.0)
        self.running = False
        self.playback_thread = None
        self.audio_queue = queue.Queue()
        
    def add_track(self, name: str, audio_data: np.ndarray, volume: float = 1.0):
        """
        Add audio track to mixer
        
        Args:
            name: Track name/identifier
            audio_data: Audio data as numpy array
            volume: Volume level (0.0-1.0)
        """
        self.audio_tracks[name] = audio_data
        self.volume_levels[name] = volume
        console.print(f"[green]Added track '{name}' with volume {volume:.2f}[/green]")
    
    def update_track_volume(self, name: str, volume: float):
        """Update volume level for a track"""
        if name in self.volume_levels:
            self.volume_levels[name] = volume
            console.print(f"[dim]Updated track '{name}' volume to {volume:.2f}[/dim]")
    
    def mix_audio(self, duration: float) -> np.ndarray:
        """
        Mix all tracks for specified duration
        
        Args:
            duration: Duration in seconds
            
        Returns:
            Mixed audio data
        """
        samples = int(duration * self.sample_rate)
        mixed = np.zeros(samples, dtype=np.float32)
        
        for name, audio_data in self.audio_tracks.items():
            volume = self.volume_levels.get(name, 1.0)
            
            # Take the required number of samples
            track_samples = min(samples, len(audio_data))
            track_audio = audio_data[:track_samples] * volume
            
            # Mix into output
            mixed[:track_samples] += track_audio
        
        # Normalize to prevent clipping
        max_val = np.max(np.abs(mixed))
        if max_val > 1.0:
            mixed = mixed / max_val
        
        return mixed
    
    def start_playback(self, callback: Optional[Callable] = None):
        """Start audio playback"""
        if self.running:
            return
        
        self.running = True
        self.playback_thread = threading.Thread(target=self._playback_worker, args=(callback,))
        self.playback_thread.start()
        console.print("[green]Started audio playback[/green]")
    
    def stop_playback(self):
        """Stop audio playback"""
        self.running = False
        if self.playback_thread:
            self.playback_thread.join()
        console.print("[yellow]Stopped audio playback[/yellow]")
    
    def _playback_worker(self, callback: Optional[Callable] = None):
        """Worker thread for audio playback"""
        try:
            def audio_callback(outdata, frames, time, status):
                if status:
                    console.print(f"[yellow]Audio callback status: {status}[/yellow]")
                
                # Get mixed audio for this chunk
                chunk_duration = frames / self.sample_rate
                mixed_audio = self.mix_audio(chunk_duration)
                
                # Reshape for output
                if self.channels == 1:
                    outdata[:, 0] = mixed_audio
                else:
                    outdata[:, :] = mixed_audio.reshape(-1, self.channels)
                
                # Call user callback if provided
                if callback:
                    callback(mixed_audio, chunk_duration)
            
            # Start audio stream
            with sd.OutputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                callback=audio_callback,
                blocksize=1024
            ):
                while self.running:
                    time.sleep(0.1)
                    
        except Exception as e:
            console.print(f"[red]Audio playback error: {e}[/red]")

class DelayedAudioPlayer:
    """
    Audio player with configurable delay for synchronized playback
    """
    
    def __init__(self, delay: float = 8.0, sample_rate: int = 16000):
        self.delay = delay
        self.sample_rate = sample_rate
        self.audio_buffer = queue.Queue()
        self.running = False
        self.playback_thread = None
        self.start_time = None
        
    def start(self):
        """Start delayed playback"""
        if self.running:
            return
        
        self.running = True
        self.start_time = time.time()
        self.playback_thread = threading.Thread(target=self._playback_worker)
        self.playback_thread.start()
        console.print(f"[green]Started delayed playback with {self.delay}s delay[/green]")
    
    def stop(self):
        """Stop delayed playback"""
        self.running = False
        if self.playback_thread:
            self.playback_thread.join()
        console.print("[yellow]Stopped delayed playback[/yellow]")
    
    def add_audio_segment(self, audio_data: np.ndarray, timestamp: float):
        """
        Add audio segment for delayed playback
        
        Args:
            audio_data: Audio data
            timestamp: Absolute timestamp when this audio should play
        """
        self.audio_buffer.put((audio_data, timestamp))
    
    def _playback_worker(self):
        """Worker thread for delayed playback"""
        while self.running:
            try:
                audio_data, target_timestamp = self.audio_buffer.get(timeout=1.0)
                
                # Calculate when this audio should play
                play_time = self.start_time + target_timestamp
                current_time = time.time()
                
                # Wait until it's time to play
                wait_time = play_time - current_time
                if wait_time > 0:
                    time.sleep(wait_time)
                
                # Play the audio
                sd.play(audio_data, self.sample_rate)
                sd.wait()
                
            except queue.Empty:
                continue
            except Exception as e:
                console.print(f"[red]Delayed playback error: {e}[/red]")

def overlay_audio_on_video(video_path: str, audio_path: str, output_path: str, 
                          audio_volume: float = 0.8, original_volume: float = 0.2):
    """
    Overlay audio on video file using ffmpeg
    
    Args:
        video_path: Path to video file
        audio_path: Path to audio file to overlay
        output_path: Path for output video
        audio_volume: Volume level for overlay audio (0.0-1.0)
        original_volume: Volume level for original audio (0.0-1.0)
    """
    try:
        # Create ffmpeg inputs
        video_input = ffmpeg.input(video_path)
        audio_input = ffmpeg.input(audio_path)
        
        # Create audio filters
        original_audio = video_input.audio.filter('volume', original_volume)
        overlay_audio = audio_input.audio.filter('volume', audio_volume)
        
        # Mix the audio streams
        mixed_audio = ffmpeg.filter([original_audio, overlay_audio], 'amix', inputs=2)
        
        # Output with video and mixed audio
        output = ffmpeg.output(
            video_input.video,
            mixed_audio,
            output_path,
            vcodec='copy',  # Copy video without re-encoding
            acodec='aac',
            audio_bitrate='128k'
        )
        
        # Run the conversion
        ffmpeg.run(output, overwrite_output=True, quiet=True)
        
        console.print(f"[green]Created mixed video: {output_path}[/green]")
        
    except Exception as e:
        console.print(f"[red]Error creating mixed video: {e}[/red]")
        raise

def save_audio_segment(audio_data: np.ndarray, sample_rate: int, 
                      start_time: float, end_time: float, output_path: str):
    """
    Save audio segment to file
    
    Args:
        audio_data: Full audio data
        sample_rate: Sample rate
        start_time: Start time in seconds
        end_time: End time in seconds
        output_path: Output file path
    """
    start_sample = int(start_time * sample_rate)
    end_sample = int(end_time * sample_rate)
    
    segment = audio_data[start_sample:end_sample]
    
    sf.write(output_path, segment, sample_rate)
    console.print(f"[dim]Saved audio segment: {output_path} ({end_time-start_time:.2f}s)[/dim]")

def create_silence(duration: float, sample_rate: int = 16000) -> np.ndarray:
    """
    Create silence audio data
    
    Args:
        duration: Duration in seconds
        sample_rate: Sample rate
        
    Returns:
        Silence audio data
    """
    samples = int(duration * sample_rate)
    return np.zeros(samples, dtype=np.float32)
