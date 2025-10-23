#!/usr/bin/env python3
"""
Multilingual Text-to-Speech with Speaker Detection and Adaptive Speed Control

This module provides real-time multilingual translation and TTS synthesis with:
- Speaker detection from VTT files (detects names in CAPS)
- Adaptive speed control to match VTT timing
- High-quality audio processing with rubberband
- Text preprocessing for better TTS pronunciation
- Caching for improved performance

Author: Philip Baillargeon (Assistance by Cursor/GPT)
"""

# Set environment variables BEFORE any imports
import os
os.environ['TORCH_LOAD_WEIGHTS_ONLY'] = 'False'
os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'

# =============================================================================
# IMPORTS AND CONFIGURATION
# =============================================================================

import sys, re, json, time, tempfile, hashlib, threading
from pathlib import Path
from typing import Dict, List, Tuple
import sounddevice as sd, soundfile as sf
from rich.console import Console
import yaml
import inflect

# Offline MT (multilingual translation)
import torch
from langdetect import detect
from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

# Monkey patch torch.load to handle Coqui TTS compatibility
original_torch_load = torch.load

def patched_torch_load(*args, **kwargs):
    # Force weights_only=False for Coqui TTS compatibility
    kwargs['weights_only'] = False
    return original_torch_load(*args, **kwargs)

torch.load = patched_torch_load

# Coqui TTS
from TTS.api import TTS as CoquiTTS

# Initialize console and cache directory
console = Console()
CACHE_DIR = Path(".cache_coqui")
CACHE_DIR.mkdir(exist_ok=True)
# Force CPU for XTTS v2 to avoid MPS channel limit issues
DEVICE = "cpu"

# Import text processing functions from utils module
from utils.text_processing import (
    preprocess_text_for_tts,
    preprocess_text_for_translation,
    clean_speaker_prefix,
    detect_speaker,
)


# =============================================================================
# VTT PARSING FUNCTIONS
# =============================================================================

def parse_vtt_timestamp(timestamp: str) -> float:
    """
    Parse VTT timestamp (HH:MM:SS.mmm) to seconds
    
    Args:
        timestamp: VTT timestamp string
        
    Returns:
        Time in seconds as float
    """
    parts = timestamp.split(':')
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds_parts = parts[2].split('.')
    seconds = int(seconds_parts[0])
    milliseconds = int(seconds_parts[1]) if len(seconds_parts) > 1 else 0
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0

def parse_vtt_file(vtt_path: str) -> List[Tuple[float, float, str, str]]:
    """
    Parse VTT file and return list of (start_time, end_time, text, speaker) tuples
    
    Args:
        vtt_path: Path to VTT file
        
    Returns:
        List of segments with timing and speaker information
    """
    segments = []
    with open(vtt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split by double newlines to get segments
    segments_raw = content.split('\n\n')
    
    for segment in segments_raw:
        lines = segment.strip().split('\n')
        if len(lines) >= 2 and '-->' in lines[0]:
            # Parse timing line (first line after WEBVTT)
            timing_line = lines[0]
            start_str, end_str = timing_line.split(' --> ')
            start_time = parse_vtt_timestamp(start_str.strip())
            end_time = parse_vtt_timestamp(end_str.strip())
            
            # Combine text lines (skip timing line)
            text_lines = lines[1:]
            text = ' '.join(text_lines).strip()
            
            if text:  # Only add non-empty segments
                # Detect speaker from text
                speaker = detect_speaker(text)
                segments.append((start_time, end_time, text, speaker))
        elif len(lines) >= 3 and '-->' in lines[1]:
            # Handle segments with segment numbers
            timing_line = lines[1]
            start_str, end_str = timing_line.split(' --> ')
            start_time = parse_vtt_timestamp(start_str.strip())
            end_time = parse_vtt_timestamp(end_str.strip())
            
            # Combine text lines (skip segment number and timing)
            text_lines = lines[2:]
            text = ' '.join(text_lines).strip()
            
            if text:  # Only add non-empty segments
                # Detect speaker from text
                speaker = detect_speaker(text)
                segments.append((start_time, end_time, text, speaker))
    
    return segments

# =============================================================================
# AUDIO PROCESSING FUNCTIONS
# =============================================================================

def get_audio_duration(path: Path) -> float:
    """
    Get the actual duration of an audio file in seconds
    
    Args:
        path: Path to audio file
        
    Returns:
        Duration in seconds
    """
    data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    return len(data) / sr

def adjust_audio_speed(input_path: Path, output_path: Path, speed_factor: float) -> Path:
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
        raise RuntimeError(f"rubberband failed: {result.stderr}")
    
    return output_path

def play_wav(path: Path):
    """Play WAV file and wait for completion"""
    data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    sd.play(data, sr)
    sd.wait()

def play_wav_with_timing(path: Path, duration: float):
    """
    Play WAV file for specified duration
    
    Args:
        path: Path to WAV file
        duration: Duration to play in seconds
    """
    data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    sd.play(data, sr)
    sd.wait()

# =============================================================================
# TRANSLATION AND TTS FUNCTIONS
# =============================================================================

def sha1(*parts: str) -> str:
    """Generate SHA1 hash from multiple string parts"""
    h = hashlib.sha1()
    for p in parts: 
        h.update(p.encode("utf-8"))
    return h.hexdigest()

def load_cfg(path: str) -> dict:
    """Load YAML configuration file"""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

# Global caches for models
_mt_cache = {}
_tts_cache = {}

def get_mt() -> Tuple[M2M100ForConditionalGeneration, M2M100Tokenizer]:
    """Get or load multilingual translation model"""
    if "mt" not in _mt_cache:
        console.print("Loading multilingual MT (M2M100 418M)…")
        model = M2M100ForConditionalGeneration.from_pretrained("facebook/m2m100_418M")
        tokenizer = M2M100Tokenizer.from_pretrained("facebook/m2m100_418M")
        _mt_cache["mt"] = (model, tokenizer)
    return _mt_cache["mt"]

def translate(text: str, tgt: str) -> Dict[str, str]:
    """
    Translate text to target language
    
    Args:
        text: Text to translate
        tgt: Target language code
        
    Returns:
        Dictionary with translation result and source language
    """
    model, tokenizer = get_mt()
    
    # Assume source language is always English
    src = "en"
    
    # Set source and target languages
    tokenizer.src_lang = src
    inputs = tokenizer(text, return_tensors="pt")
    
    # Generate translation with TTS-friendly parameters
    with torch.no_grad():
        generated_tokens = model.generate(
            **inputs, 
            forced_bos_token_id=tokenizer.get_lang_id(tgt),
            num_beams=4,  # Use beam search for more accurate translation
            early_stopping=True,  # Stop when EOS token is generated
            repetition_penalty=1.1,  # Slight penalty to avoid repetition
            max_length=100,  # Reasonable max length for TTS
            do_sample=False  # Use deterministic generation
        )
    
    result = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]
    return {"out": result, "src": src}

def get_speaker_voice(voices: Dict, language: str, speaker: str) -> Tuple[str, str, str]:
    """
    Get the appropriate voice configuration for a speaker and language
    
    Args:
        voices: Voice configuration dictionary
        language: Target language code
        speaker: Detected speaker name
        
    Returns:
        Tuple of (model_name, speaker_id, voice_sample_path)
    """
    language_config = voices.get(language, {})
    model_name = language_config.get("model")
    is_multi_speaker = language_config.get("multi_speaker", False)
    
    # Check if speaker-specific configuration exists
    speakers_config = language_config.get("speakers", {})
    if speaker in speakers_config:
        speaker_config = speakers_config[speaker]
        speaker_id = speaker_config.get("speaker")
        voice_sample = speaker_config.get("voice_sample")
    else:
        # Fallback to default speaker
        default_config = speakers_config.get("default", {})
        speaker_id = default_config.get("speaker", "Andrew Chipper")
        voice_sample = default_config.get("voice_sample")
    
    # For XTTS v2, use the configured speaker name
    if is_multi_speaker and "xtts" in model_name.lower():
        # Keep the speaker_id as configured (it should be a valid speaker name)
        pass
    
    # For single-speaker models, return None as speaker_id
    if not is_multi_speaker:
        speaker_id = None
    
    return model_name, speaker_id, voice_sample

def get_tts(model_name: str) -> CoquiTTS:
    if model_name not in _tts_cache:
        console.print(f"Loading Coqui TTS model: {model_name}")
        console.print(f"[dim]Using device: {DEVICE}[/dim]")
        try:
            _tts_cache[model_name] = CoquiTTS(model_name=model_name, progress_bar=False).to(DEVICE)
        except Exception as e:
            console.print(f"[red]Failed to load TTS model {model_name}: {e}[/red]")
            if "CUDA" in str(e):
                console.print("[yellow]Try: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu[/yellow]")
                sys.exit(1)
            else:
                raise e
    return _tts_cache[model_name]

def synth_to_wav(text: str, model_name: str, speaker=None, target_language: str = 'es', voice_sample_path: str = None) -> Path:
    """
    Synthesize text to WAV file with optional voice cloning
    
    Args:
        text: Text to synthesize
        model_name: TTS model name
        speaker: Speaker ID (optional)
        target_language: Target language code
        voice_sample_path: Path to voice sample for cloning (optional)
        
    Returns:
        Path to generated WAV file
    """
    wav = Path(tempfile.mkstemp(suffix=".wav")[1])
    tts = get_tts(model_name)
    
    # Preprocess text for better TTS quality
    processed_text = preprocess_text_for_tts(text, convert_numbers=False)
    
    # Synthesize audio - handle single-speaker vs multi-speaker models
    if speaker is not None:
        # For multilingual models like XTTS v2, pass language parameter
        if "xtts" in model_name.lower():
            # Use voice cloning if voice sample is provided
            if voice_sample_path and Path(voice_sample_path).exists():
                console.print(f"[dim]Using voice cloning with sample: {voice_sample_path}[/dim]")
                tts.tts_to_file(
                    text=processed_text, 
                    file_path=str(wav), 
                    speaker_wav=voice_sample_path,
                    language=target_language
                )
            else:
                # Use default speaker voice
                tts.tts_to_file(text=processed_text, file_path=str(wav), speaker=speaker, language=target_language)
        else:
            tts.tts_to_file(text=processed_text, file_path=str(wav), speaker=speaker)
    else:
        # For multilingual models like XTTS v2, pass language parameter
        if "xtts" in model_name.lower():
            # Use voice cloning if voice sample is provided
            if voice_sample_path and Path(voice_sample_path).exists():
                console.print(f"[dim]Using voice cloning with sample: {voice_sample_path}[/dim]")
                tts.tts_to_file(
                    text=processed_text, 
                    file_path=str(wav), 
                    speaker_wav=voice_sample_path,
                    language=target_language
                )
            else:
                tts.tts_to_file(text=processed_text, file_path=str(wav), language=target_language)
        else:
            tts.tts_to_file(text=processed_text, file_path=str(wav))
    return wav

# =============================================================================
# VTT PROCESSING FUNCTIONS
# =============================================================================

def process_vtt_file(vtt_path: str, targets: List[str], voices: Dict, args):
    """
    Process VTT file with real-time timing alignment and speaker detection
    
    Args:
        vtt_path: Path to VTT file
        targets: List of target languages
        voices: Voice configuration dictionary
        args: Command line arguments
    """
    segments = parse_vtt_file(vtt_path)
    console.print(f"[green]Processing {len(segments)} segments from VTT file...[/green]")
    
    # Track detected speakers
    detected_speakers = set()
    speaker_counts = {}
    
    # First pass: detect all speakers
    for start_time_vtt, end_time_vtt, text, speaker in segments:
        detected_speakers.add(speaker)
        speaker_counts[speaker] = speaker_counts.get(speaker, 0) + 1
    
    console.print(f"[green]Detected speakers:[/green] {', '.join(sorted(detected_speakers))}")
    for speaker, count in sorted(speaker_counts.items()):
        console.print(f"  [dim]{speaker}: {count} segments[/dim]")
    console.print()
    
    start_time = time.time()
    audio_start_times = {}  # Track when each language audio starts
    
    for i, (start_time_vtt, end_time_vtt, text, speaker) in enumerate(segments):
        # Calculate when this segment should start playing
        segment_start_time = start_time + start_time_vtt
        current_time = time.time()
        
        # Wait until it's time to play this segment
        wait_time = segment_start_time - current_time
        if wait_time > 0:
            console.print(f"[dim]Waiting {wait_time:.2f}s for segment {i+1}/{len(segments)}...[/dim]")
            time.sleep(wait_time)
        
        console.print(f"[bold]Segment {i+1}/{len(segments)}:[/bold] {text}")
        console.print(f"[dim]Speaker: {speaker}[/dim]")
        
        # Clean speaker prefix from text for TTS
        clean_text = clean_speaker_prefix(text, speaker)
        for tgt in targets:
            # Get speaker-specific voice configuration
            model_name, tts_speaker = get_speaker_voice(voices, tgt, speaker)
            
            # --- MT (with cache) ---
            t0 = time.time()
            # Use preprocessed text for cache key to ensure consistency
            preprocessed_text = preprocess_text_for_translation(clean_text)
            mt_key = sha1("MT", preprocessed_text, tgt)
            mt_path = CACHE_DIR / f"{mt_key}.json"
            if args.no_cache or not mt_path.exists():
                mt_res = translate(preprocessed_text, tgt)
                if not args.no_cache:
                    mt_path.write_text(json.dumps(mt_res, ensure_ascii=False), encoding="utf-8")
            else:
                mt_res = json.loads(mt_path.read_text("utf-8"))
            t1 = time.time()
            
            console.print(f"[bold]{tgt}[/bold]: {mt_res['out']}  [dim](MT {t1-t0:.2f}s; src={mt_res['src']})[/dim]")
            if tts_speaker is not None:
                console.print(f"[dim]Using voice: {model_name} (speaker {tts_speaker}) for {speaker}[/dim]")
            else:
                console.print(f"[dim]Using voice: {model_name} (single-speaker) for {speaker}[/dim]")
            
            # Calculate speed adjustment for VTT timing
            segment_duration = end_time_vtt - start_time_vtt
            
            # --- TTS (with adaptive speed via post-processing) ---
            if args.adaptive_speed:
                # Always synthesize fresh audio and apply speed adjustment via post-processing
                # First synthesize at normal speed
                temp_wav = synth_to_wav(mt_res["out"], model_name, speaker=tts_speaker, target_language=tgt)
                baseline_duration = get_audio_duration(temp_wav)
                
                # Calculate required speed to match VTT timing
                required_speed = baseline_duration / segment_duration
                # Clamp speed to reasonable range (0.5x to 2.0x)
                required_speed = max(0.5, min(2.0, required_speed))
                
                console.print(f"[dim]Adaptive speed: {required_speed:.2f}x (baseline: {baseline_duration:.2f}s → target: {segment_duration:.2f}s)[/dim]")
                
                # Apply speed adjustment via post-processing
                wav_path = Path(tempfile.mkstemp(suffix=".wav")[1])
                wav_path = adjust_audio_speed(temp_wav, wav_path, required_speed)
                
                # Clean up temp file
                Path(temp_wav).unlink()
            else:
                # When adaptive speed is disabled, use cache
                tts_key = sha1("TTS", mt_res["out"], tgt, model_name, str(tts_speaker))
            wav_path = CACHE_DIR / f"{tts_key}.wav"
            
            if args.no_cache or not wav_path.exists():
                # Synthesize audio at normal speed
                wav_path = synth_to_wav(mt_res["out"], model_name, speaker=tts_speaker, target_language=tgt)
                
                if not args.no_cache:
                    # move temp to cache filename
                    tmp = wav_path
                    wav_path = CACHE_DIR / f"{tts_key}.wav"
                    Path(tmp).rename(wav_path)
            
            t2 = time.time()
            console.print(f"[dim]TTS {t2-t1:.2f}s → playing {tgt}…[/dim]")
            
            # Play audio for the exact VTT duration
            play_wav_with_timing(wav_path, segment_duration)
        
        console.print()  # Empty line between segments

# =============================================================================
# INTERACTIVE MODE FUNCTIONS
# =============================================================================

def interactive_mode(targets: List[str], voices: Dict, args):
    """
    Run interactive translation and TTS mode
    
    Args:
        targets: List of target languages
        voices: Voice configuration dictionary
        args: Command line arguments
    """
    console.print("[green]Type text; I'll translate & speak locally in:[/green] " +
                  ", ".join(f"[bold]{t}[/bold]" for t in targets))
    console.print("Type 'quit' to exit.\n")

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line: 
            continue
        if line.lower() in ("q", "quit", "exit"): 
            break

        for tgt in targets:
            model_name = voices[tgt]["model"]
            speaker = voices[tgt].get("speaker")

            # --- MT (with cache) ---
            t0 = time.time()
            mt_key = sha1("MT", line, tgt)
            mt_path = CACHE_DIR / f"{mt_key}.json"
            if args.no_cache or not mt_path.exists():
                mt_res = translate(line, tgt)
                if not args.no_cache:
                    mt_path.write_text(json.dumps(mt_res, ensure_ascii=False), encoding="utf-8")
            else:
                mt_res = json.loads(mt_path.read_text("utf-8"))
            t1 = time.time()

            console.print(f"[bold]{tgt}[/bold]: {mt_res['out']}  [dim](MT {t1-t0:.2f}s; src={mt_res['src']})[/dim]")

            # --- TTS (with cache) ---
            tts_key = sha1("TTS", mt_res["out"], tgt, model_name, str(speaker))
            wav_path = CACHE_DIR / f"{tts_key}.wav"
            if args.no_cache or not wav_path.exists():
                # Use normal speed for interactive mode
                wav_path = synth_to_wav(mt_res["out"], model_name, speaker=speaker, target_language=tgt)
                if not args.no_cache:
                    # move temp to cache filename
                    tmp = wav_path
                    wav_path = CACHE_DIR / f"{tts_key}.wav"
                    Path(tmp).rename(wav_path)

            t2 = time.time()
            console.print(f"[dim]TTS {t2-t1:.2f}s → playing {tgt}…[/dim]")
            play_wav(wav_path)

    console.print("\n[bold]Bye![/bold]")

# =============================================================================
# MAIN FUNCTION
# =============================================================================

def main():
    """Main entry point"""
    import argparse
    
    ap = argparse.ArgumentParser(description="Local multilingual translate + TTS (Coqui)")
    ap.add_argument("--targets", "-t", default="es", help="Comma-separated target langs: es,fr,de,…")
    ap.add_argument("--config", "-c", default="coqui-voices.yaml", help="YAML mapping langs->Coqui model")
    ap.add_argument("--no-cache", action="store_true", default=True, help="Disable translation/audio cache (default: True for testing)")
    ap.add_argument("--vtt", "-v", help="Process VTT file with real-time timing alignment")
    ap.add_argument("--adaptive-speed", action="store_true", default=False, help="Use adaptive speed control for VTT timing (default: False)")
    args = ap.parse_args()

    cfg = load_cfg(args.config)
    voices = cfg.get("languages", {})
    targets = [t.strip() for t in args.targets.split(",") if t.strip()]

    missing = [t for t in targets if t not in voices]
    if missing:
        console.print(f"[red]No Coqui voice configured for: {', '.join(missing)}[/red]")
        console.print(f"Add them under 'languages:' in {args.config}.")
        sys.exit(2)

    # Handle VTT file processing
    if args.vtt:
        if not Path(args.vtt).exists():
            console.print(f"[red]VTT file not found: {args.vtt}[/red]")
            sys.exit(1)
        
        console.print(f"[green]Processing VTT file: {args.vtt}[/green]")
        console.print(f"[green]Target languages:[/green] " + ", ".join(f"[bold]{t}[/bold]" for t in targets))
        console.print("[yellow]Press Ctrl+C to stop playback[/yellow]\n")
        
        try:
            process_vtt_file(args.vtt, targets, voices, args)
        except KeyboardInterrupt:
            console.print("\n[yellow]Playback interrupted by user[/yellow]")
        
        console.print("\n[bold]VTT processing complete![/bold]")
        return

    # Interactive mode
    interactive_mode(targets, voices, args)

if __name__ == "__main__":
    main()