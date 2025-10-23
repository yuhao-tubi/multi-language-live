#!/usr/bin/env python3
"""
Voice Sample Management Utilities for XTTS-v2 Voice Cloning

This module provides utilities for managing voice samples and voice cloning
with XTTS-v2 models.

Author: Philip Baillargeon (Assistance by Cursor/GPT)
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import soundfile as sf
import librosa
from rich.console import Console

console = Console()

def validate_voice_sample(audio_path: str, min_duration: float = 3.0, max_duration: float = 30.0) -> Tuple[bool, str]:
    """
    Validate a voice sample for XTTS-v2 voice cloning
    
    Args:
        audio_path: Path to the audio file
        min_duration: Minimum duration in seconds (default: 3.0)
        max_duration: Maximum duration in seconds (default: 30.0)
        
    Returns:
        Tuple of (is_valid, message)
    """
    try:
        if not Path(audio_path).exists():
            return False, f"File does not exist: {audio_path}"
        
        # Load audio file
        audio_data, sample_rate = sf.read(audio_path)
        duration = len(audio_data) / sample_rate
        
        if duration < min_duration:
            return False, f"Audio too short: {duration:.2f}s (minimum: {min_duration}s)"
        
        if duration > max_duration:
            return False, f"Audio too long: {duration:.2f}s (maximum: {max_duration}s)"
        
        # Check if audio is mono (XTTS-v2 prefers mono)
        if len(audio_data.shape) > 1 and audio_data.shape[1] > 1:
            console.print(f"[yellow]Warning: Audio is stereo, XTTS-v2 works better with mono audio[/yellow]")
        
        # Check sample rate (prefer 22050 Hz)
        if sample_rate != 22050:
            console.print(f"[yellow]Warning: Sample rate is {sample_rate} Hz, XTTS-v2 prefers 22050 Hz[/yellow]")
        
        return True, f"Valid voice sample: {duration:.2f}s, {sample_rate} Hz"
        
    except Exception as e:
        return False, f"Error validating audio file: {e}"

def preprocess_voice_sample(input_path: str, output_path: str, target_sample_rate: int = 22050) -> bool:
    """
    Preprocess a voice sample for optimal XTTS-v2 performance
    
    Args:
        input_path: Path to input audio file
        output_path: Path to save processed audio file
        target_sample_rate: Target sample rate (default: 22050)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Load audio
        audio_data, sample_rate = sf.read(input_path)
        
        # Convert to mono if stereo
        if len(audio_data.shape) > 1 and audio_data.shape[1] > 1:
            audio_data = librosa.to_mono(audio_data.T)
        
        # Resample if needed
        if sample_rate != target_sample_rate:
            audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=target_sample_rate)
        
        # Normalize audio
        audio_data = librosa.util.normalize(audio_data)
        
        # Save processed audio
        sf.write(output_path, audio_data, target_sample_rate)
        
        console.print(f"[green]Processed voice sample: {output_path}[/green]")
        return True
        
    except Exception as e:
        console.print(f"[red]Error preprocessing voice sample: {e}[/red]")
        return False

def setup_voice_samples(voices_config: Dict, voice_samples_dir: str = "./voice_samples") -> Dict:
    """
    Set up voice samples directory and validate existing samples
    
    Args:
        voices_config: Voice configuration dictionary
        voice_samples_dir: Directory for voice samples
        
    Returns:
        Updated voice configuration with validated voice samples
    """
    voice_samples_path = Path(voice_samples_dir)
    voice_samples_path.mkdir(exist_ok=True)
    
    console.print(f"[green]Setting up voice samples directory: {voice_samples_path}[/green]")
    
    # Create example voice sample files
    example_files = {
        "joe_sample.wav": "Place a 3-30 second audio sample of JOE's voice here",
        "referee_sample.wav": "Place a 3-30 second audio sample of REFEREE's voice here",
        "README.md": """# Voice Samples Directory

This directory contains voice samples for XTTS-v2 voice cloning.

## Requirements:
- Audio files should be 3-30 seconds long
- Mono audio is preferred (will be converted automatically)
- Sample rate of 22050 Hz is optimal
- Supported formats: WAV, MP3, FLAC, M4A

## Usage:
1. Place voice samples in this directory
2. Update coqui-voices.yaml to reference the voice samples:
   ```yaml
   speakers:
     JOE:
       speaker: "Andrew Chipper"  # Fallback voice
       voice_sample: "./voice_samples/joe_sample.wav"
   ```

## File naming convention:
- joe_sample.wav - Voice sample for JOE speaker
- referee_sample.wav - Voice sample for REFEREE speaker
- [speaker_name]_sample.wav - Voice sample for [speaker_name] speaker
"""
    }
    
    for filename, content in example_files.items():
        file_path = voice_samples_path / filename
        if not file_path.exists():
            if filename.endswith('.md'):
                file_path.write_text(content)
            else:
                file_path.write_text(content)
            console.print(f"[dim]Created example file: {file_path}[/dim]")
    
    # Validate existing voice samples
    for lang_code, lang_config in voices_config.get("languages", {}).items():
        speakers_config = lang_config.get("speakers", {})
        for speaker_name, speaker_config in speakers_config.items():
            voice_sample_path = speaker_config.get("voice_sample")
            if voice_sample_path and Path(voice_sample_path).exists():
                is_valid, message = validate_voice_sample(voice_sample_path)
                if is_valid:
                    console.print(f"[green]✓ {speaker_name} voice sample: {message}[/green]")
                else:
                    console.print(f"[red]✗ {speaker_name} voice sample: {message}[/red]")
    
    return voices_config

def create_voice_sample_config(speaker_name: str, voice_sample_path: str, fallback_speaker: str = "Andrew Chipper") -> Dict:
    """
    Create a voice sample configuration for a speaker
    
    Args:
        speaker_name: Name of the speaker
        voice_sample_path: Path to the voice sample file
        fallback_speaker: Fallback speaker name if voice sample fails
        
    Returns:
        Speaker configuration dictionary
    """
    return {
        "speaker": fallback_speaker,
        "voice_sample": voice_sample_path
    }

def update_voice_config_with_samples(config_path: str, voice_samples_dir: str = "./voice_samples") -> None:
    """
    Update voice configuration file with voice samples
    
    Args:
        config_path: Path to the voice configuration file
        voice_samples_dir: Directory containing voice samples
    """
    import yaml
    
    # Load existing configuration
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    voice_samples_path = Path(voice_samples_dir)
    
    # Find voice sample files
    voice_sample_files = {}
    if voice_samples_path.exists():
        for audio_file in voice_samples_path.glob("*.wav"):
            speaker_name = audio_file.stem.replace("_sample", "").upper()
            voice_sample_files[speaker_name] = str(audio_file)
    
    # Update configuration with found voice samples
    for lang_code, lang_config in config.get("languages", {}).items():
        speakers_config = lang_config.get("speakers", {})
        for speaker_name in speakers_config:
            if speaker_name in voice_sample_files:
                speakers_config[speaker_name]["voice_sample"] = voice_sample_files[speaker_name]
                console.print(f"[green]Updated {speaker_name} voice sample: {voice_sample_files[speaker_name]}[/green]")
    
    # Save updated configuration
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    
    console.print(f"[green]Updated voice configuration: {config_path}[/green]")

def list_available_voice_samples(voice_samples_dir: str = "./voice_samples") -> List[str]:
    """
    List available voice sample files
    
    Args:
        voice_samples_dir: Directory containing voice samples
        
    Returns:
        List of available voice sample file paths
    """
    voice_samples_path = Path(voice_samples_dir)
    if not voice_samples_path.exists():
        return []
    
    voice_samples = []
    for audio_file in voice_samples_path.glob("*.wav"):
        is_valid, message = validate_voice_sample(str(audio_file))
        voice_samples.append({
            "path": str(audio_file),
            "speaker": audio_file.stem.replace("_sample", "").upper(),
            "valid": is_valid,
            "message": message
        })
    
    return voice_samples

if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "validate":
            if len(sys.argv) > 2:
                audio_path = sys.argv[2]
                is_valid, message = validate_voice_sample(audio_path)
                console.print(f"[{'green' if is_valid else 'red'}]{message}[/{'green' if is_valid else 'red'}]")
            else:
                console.print("[red]Usage: python voice_management.py validate <audio_file>[/red]")
        
        elif command == "preprocess":
            if len(sys.argv) > 3:
                input_path = sys.argv[2]
                output_path = sys.argv[3]
                success = preprocess_voice_sample(input_path, output_path)
                if success:
                    console.print("[green]Voice sample preprocessed successfully[/green]")
                else:
                    console.print("[red]Failed to preprocess voice sample[/red]")
            else:
                console.print("[red]Usage: python voice_management.py preprocess <input_file> <output_file>[/red]")
        
        elif command == "list":
            voice_samples = list_available_voice_samples()
            if voice_samples:
                console.print("[green]Available voice samples:[/green]")
                for sample in voice_samples:
                    status = "✓" if sample["valid"] else "✗"
                    console.print(f"  {status} {sample['speaker']}: {sample['path']} - {sample['message']}")
            else:
                console.print("[yellow]No voice samples found[/yellow]")
        
        else:
            console.print("[red]Unknown command. Available commands: validate, preprocess, list[/red]")
    else:
        console.print("Voice Sample Management Utilities")
        console.print("Available commands:")
        console.print("  validate <audio_file>  - Validate a voice sample")
        console.print("  preprocess <input> <output> - Preprocess a voice sample")
        console.print("  list - List available voice samples")
