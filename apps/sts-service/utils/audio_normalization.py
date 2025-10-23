#!/usr/bin/env python3
"""
Audio Duration Normalization Utilities

This module provides audio time-stretching and duration normalization
using Rubber Band (via system calls) or librosa as fallback.

Author: Philip Baillargeon (Assistance by Cursor/GPT)
"""

import numpy as np
import soundfile as sf
import librosa
import subprocess
import tempfile
import os
from typing import Tuple, Optional

def check_rubberband_available() -> bool:
    """Check if Rubber Band command-line tool is available."""
    try:
        result = subprocess.run(['rubberband', '--version'], 
                              capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

RUBBERBAND_AVAILABLE = check_rubberband_available()

def normalize_audio_duration_rubberband(
    audio_data: np.ndarray, 
    sample_rate: int, 
    target_duration: float = 15.0
) -> Tuple[np.ndarray, int]:
    """
    Normalize audio duration using Rubber Band command-line tool.
    
    Args:
        audio_data: Input audio as numpy array (float32, range -1.0 to 1.0)
        sample_rate: Sample rate of input audio
        target_duration: Target duration in seconds (default: 15.0)
    
    Returns:
        Tuple of (normalized_audio, sample_rate)
    """
    current_duration = len(audio_data) / sample_rate
    stretch_ratio = target_duration / current_duration
    
    print(f"Using Rubber Band: {current_duration:.2f}s → {target_duration:.2f}s (ratio: {stretch_ratio:.3f})")
    print(f"  Input: {len(audio_data)} samples at {sample_rate}Hz")
    
    # Create temporary files
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as input_file:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as output_file:
            try:
                # Write input audio to temporary file
                sf.write(input_file.name, audio_data, sample_rate)
                print(f"  Written to temp file: {input_file.name}")
                
                # Run Rubber Band
                cmd = [
                    'rubberband',
                    '-t', str(stretch_ratio),
                    '-F',  # Preserve formants
                    '-c', '5',  # Crisp transients
                    input_file.name,
                    output_file.name
                ]
                
                print(f"  Running command: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                if result.returncode != 0:
                    print(f"  Rubber Band stderr: {result.stderr}")
                    raise RuntimeError(f"Rubber Band failed: {result.stderr}")
                
                # Read processed audio
                processed_audio, sr = sf.read(output_file.name, dtype='float32')
                
                # Verify duration
                final_duration = len(processed_audio) / sr
                print(f"  Rubber Band result: {len(processed_audio)} samples, {final_duration:.2f}s at {sr}Hz")
                
                return processed_audio, sr
                
            finally:
                # Clean up temporary files
                try:
                    os.unlink(input_file.name)
                    os.unlink(output_file.name)
                except:
                    pass

def normalize_audio_duration_librosa(
    audio_data: np.ndarray, 
    sample_rate: int, 
    target_duration: float = 15.0
) -> Tuple[np.ndarray, int]:
    """
    Normalize audio duration using librosa time-stretching.
    
    Args:
        audio_data: Input audio as numpy array (float32, range -1.0 to 1.0)
        sample_rate: Sample rate of input audio
        target_duration: Target duration in seconds (default: 15.0)
    
    Returns:
        Tuple of (normalized_audio, sample_rate)
    """
    current_duration = len(audio_data) / sample_rate
    stretch_ratio = target_duration / current_duration
    
    print(f"Using librosa: {current_duration:.2f}s → {target_duration:.2f}s (ratio: {stretch_ratio:.3f})")
    print(f"  Input: {len(audio_data)} samples at {sample_rate}Hz")
    
    # Use librosa's time-stretching
    stretched_audio = librosa.effects.time_stretch(audio_data, rate=stretch_ratio)
    
    # Verify duration
    final_duration = len(stretched_audio) / sample_rate
    print(f"  Librosa result: {len(stretched_audio)} samples, {final_duration:.2f}s at {sample_rate}Hz")
    
    return stretched_audio, sample_rate

def normalize_audio_duration(
    audio_data: np.ndarray, 
    sample_rate: int, 
    target_duration: float = 15.0,
    preserve_pitch: bool = True
) -> Tuple[np.ndarray, int]:
    """
    Normalize audio duration to exactly target_duration seconds.
    
    Strategy:
    - If audio is longer than target: compress using Rubber Band/librosa
    - If audio is shorter than target: pad with silence
    - If audio is close to target: return as-is
    
    Args:
        audio_data: Input audio as numpy array (float32, range -1.0 to 1.0)
        sample_rate: Sample rate of input audio
        target_duration: Target duration in seconds (default: 15.0)
        preserve_pitch: Whether to preserve pitch during compression (default: True)
    
    Returns:
        Tuple of (normalized_audio, sample_rate)
    
    Raises:
        ValueError: If audio data is invalid
    """
    if len(audio_data) == 0:
        raise ValueError("Audio data cannot be empty")
    
    # Calculate current duration
    current_duration = len(audio_data) / sample_rate
    target_samples = int(target_duration * sample_rate)
    
    # If already at target duration (within 0.1s tolerance), return as-is
    if abs(current_duration - target_duration) < 0.1:
        print(f"Audio duration is already close to target ({current_duration:.2f}s), returning as-is")
        return audio_data, sample_rate
    
    print(f"Normalizing audio duration: {current_duration:.2f}s → {target_duration:.2f}s")
    
    # Strategy: Only compress if longer than target, otherwise pad with silence
    if current_duration > target_duration:
        # Audio is too long - compress it
        print(f"Audio is longer than target ({current_duration:.2f}s > {target_duration:.2f}s), compressing...")
        
        try:
            # Try Rubber Band first if available
            if RUBBERBAND_AVAILABLE:
                return normalize_audio_duration_rubberband(audio_data, sample_rate, target_duration)
            else:
                # Fallback to librosa
                return normalize_audio_duration_librosa(audio_data, sample_rate, target_duration)
                
        except Exception as e:
            print(f"ERROR: Audio compression failed: {e}")
            print("Falling back to simple trimming...")
            
            # Fallback: simple trim to target length
            return audio_data[:target_samples], sample_rate
            
    else:
        # Audio is too short - pad with silence
        print(f"Audio is shorter than target ({current_duration:.2f}s < {target_duration:.2f}s), padding with silence...")
        
        padding_samples = target_samples - len(audio_data)
        padding = np.zeros(padding_samples, dtype=np.float32)
        padded_audio = np.concatenate([audio_data, padding])
        
        final_duration = len(padded_audio) / sample_rate
        print(f"Padded audio duration: {final_duration:.2f}s")
        
        return padded_audio, sample_rate

def normalize_audio_duration_from_bytes(
    audio_bytes: bytes, 
    sample_rate: int, 
    target_duration: float = 15.0,
    preserve_pitch: bool = True
) -> Tuple[bytes, int]:
    """
    Normalize audio duration from raw bytes.
    
    Args:
        audio_bytes: Raw audio data as bytes
        sample_rate: Sample rate of input audio
        target_duration: Target duration in seconds (default: 15.0)
        preserve_pitch: Whether to preserve pitch during time-stretching (default: True)
    
    Returns:
        Tuple of (normalized_audio_bytes, sample_rate)
    """
    try:
        # Convert bytes to numpy array
        audio_data = np.frombuffer(audio_bytes, dtype=np.float32)
        
        # Normalize duration
        normalized_audio, sr = normalize_audio_duration(
            audio_data, sample_rate, target_duration, preserve_pitch
        )
        
        # Convert back to bytes
        normalized_bytes = normalized_audio.astype(np.float32).tobytes()
        
        return normalized_bytes, sr
        
    except Exception as e:
        print(f"ERROR: Failed to normalize audio from bytes: {e}")
        # Return original bytes as fallback
        return audio_bytes, sample_rate

def get_audio_duration(audio_data: np.ndarray, sample_rate: int) -> float:
    """Get duration of audio data in seconds."""
    return len(audio_data) / sample_rate

def get_audio_duration_from_bytes(audio_bytes: bytes, sample_rate: int) -> float:
    """Get duration of audio data from bytes in seconds."""
    audio_data = np.frombuffer(audio_bytes, dtype=np.float32)
    return get_audio_duration(audio_data, sample_rate)

# Test function
def test_audio_normalization():
    """Test audio normalization functionality."""
    print("Testing audio normalization...")
    print(f"Rubber Band available: {RUBBERBAND_AVAILABLE}")
    
    sample_rate = 44100
    
    # Test 1: Audio longer than target (should compress)
    print("\n--- Test 1: Compressing long audio (20s → 15s) ---")
    duration_long = 20.0
    frequency = 440.0
    
    t = np.linspace(0, duration_long, int(sample_rate * duration_long), False)
    long_audio = 0.3 * np.sin(2 * np.pi * frequency * t).astype(np.float32)
    
    print(f"Original: {len(long_audio)} samples, {get_audio_duration(long_audio, sample_rate):.2f}s")
    
    compressed_audio, sr = normalize_audio_duration(long_audio, sample_rate, 15.0)
    print(f"Compressed: {len(compressed_audio)} samples, {get_audio_duration(compressed_audio, sr):.2f}s")
    
    # Test 2: Audio shorter than target (should pad)
    print("\n--- Test 2: Padding short audio (8s → 15s) ---")
    duration_short = 8.0
    
    t = np.linspace(0, duration_short, int(sample_rate * duration_short), False)
    short_audio = 0.3 * np.sin(2 * np.pi * frequency * t).astype(np.float32)
    
    print(f"Original: {len(short_audio)} samples, {get_audio_duration(short_audio, sample_rate):.2f}s")
    
    padded_audio, sr = normalize_audio_duration(short_audio, sample_rate, 15.0)
    print(f"Padded: {len(padded_audio)} samples, {get_audio_duration(padded_audio, sr):.2f}s")
    
    # Test 3: Audio close to target (should return as-is)
    print("\n--- Test 3: Audio close to target (15.05s → 15s) ---")
    duration_close = 15.05
    
    t = np.linspace(0, duration_close, int(sample_rate * duration_close), False)
    close_audio = 0.3 * np.sin(2 * np.pi * frequency * t).astype(np.float32)
    
    print(f"Original: {len(close_audio)} samples, {get_audio_duration(close_audio, sample_rate):.2f}s")
    
    unchanged_audio, sr = normalize_audio_duration(close_audio, sample_rate, 15.0)
    print(f"Unchanged: {len(unchanged_audio)} samples, {get_audio_duration(unchanged_audio, sr):.2f}s")
    
    print("\n✅ Audio normalization test completed")

if __name__ == "__main__":
    test_audio_normalization()
