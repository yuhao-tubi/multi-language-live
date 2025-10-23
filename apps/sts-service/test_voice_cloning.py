#!/usr/bin/env python3
"""
Test script for XTTS-v2 Voice Cloning Optimization

This script demonstrates the optimized workflow using XTTS-v2 for all languages
with voice cloning capabilities.

Author: Philip Baillargeon (Assistance by Cursor/GPT)
"""

import sys
import argparse
from pathlib import Path
from rich.console import Console
import yaml

from talk_multi_coqui import (
    load_cfg, translate, synth_to_wav, get_speaker_voice, 
    preprocess_text_for_tts, clean_speaker_prefix, detect_speaker, play_wav
)
from utils.voice_management import (
    validate_voice_sample, preprocess_voice_sample, setup_voice_samples,
    list_available_voice_samples, update_voice_config_with_samples
)

console = Console()

def test_voice_cloning(text: str, language: str, speaker: str, voices: dict, play_audio: bool = True):
    """
    Test voice cloning for a specific speaker and language
    
    Args:
        text: Text to synthesize
        language: Target language
        speaker: Speaker name
        voices: Voice configuration
        play_audio: Whether to play the generated audio
    """
    console.print(f"\n[bold]Testing voice cloning for {speaker} in {language}[/bold]")
    console.print(f"Text: {text}")
    
    # Get voice configuration
    model_name, tts_speaker, voice_sample = get_speaker_voice(voices, language, speaker)
    
    console.print(f"Model: {model_name}")
    console.print(f"Speaker: {tts_speaker}")
    console.print(f"Voice sample: {voice_sample}")
    
    # Validate voice sample if provided
    if voice_sample and Path(voice_sample).exists():
        is_valid, message = validate_voice_sample(voice_sample)
        console.print(f"Voice sample validation: {message}")
        
        if not is_valid:
            console.print("[yellow]Voice sample is invalid, using fallback speaker[/yellow]")
            voice_sample = None
    
    # Synthesize audio
    try:
        wav_path = synth_to_wav(text, model_name, speaker=tts_speaker, target_language=language, voice_sample_path=voice_sample)
        console.print(f"[green]✓ Audio synthesized: {wav_path}[/green]")
        
        # Play the audio if requested
        if play_audio:
            console.print(f"[dim]Playing audio...[/dim]")
            play_wav(wav_path)
            console.print(f"[green]✓ Audio playback complete[/green]")
        
        return wav_path
    except Exception as e:
        console.print(f"[red]✗ Failed to synthesize audio: {e}[/red]")
        return None

def test_all_languages(text: str, speaker: str, voices: dict, play_audio: bool = True):
    """
    Test voice cloning across all configured languages
    
    Args:
        text: Text to synthesize
        speaker: Speaker name
        voices: Voice configuration
        play_audio: Whether to play the generated audio
    """
    console.print(f"\n[bold]Testing voice cloning for '{speaker}' across all languages[/bold]")
    
    results = {}
    for language in voices.keys():
        console.print(f"\n[cyan]Testing {language}[/cyan]")
        wav_path = test_voice_cloning(text, language, speaker, voices, play_audio)
        results[language] = wav_path
    
    return results

def main():
    """Main test function"""
    parser = argparse.ArgumentParser(description="Test XTTS-v2 voice cloning optimization")
    parser.add_argument("--config", "-c", default="coqui-voices.yaml", help="Voice configuration file")
    parser.add_argument("--text", "-t", default="Hello, this is a test of voice cloning.", help="Text to synthesize")
    parser.add_argument("--speaker", "-s", default="JOE", help="Speaker name to test")
    parser.add_argument("--language", "-l", help="Specific language to test (if not provided, tests all)")
    parser.add_argument("--list-samples", action="store_true", help="List available voice samples")
    parser.add_argument("--setup-samples", action="store_true", help="Set up voice samples directory")
    parser.add_argument("--no-play", action="store_true", help="Don't play audio, just generate files")
    
    args = parser.parse_args()
    
    # Load configuration
    cfg = load_cfg(args.config)
    voices = cfg.get("languages", {})
    
    # Set up voice samples if requested
    if args.setup_samples:
        console.print("[green]Setting up voice samples directory...[/green]")
        voices = setup_voice_samples(voices, cfg.get("voice_samples", {}).get("directory", "./voice_samples"))
        console.print("[green]Voice samples directory setup complete![/green]")
        console.print("\n[yellow]Next steps:[/yellow]")
        console.print("1. Place voice sample files in ./voice_samples/")
        console.print("2. Update coqui-voices.yaml to reference your voice samples")
        console.print("3. Run this script again to test voice cloning")
        return
    
    # List available voice samples if requested
    if args.list_samples:
        console.print("[green]Available voice samples:[/green]")
        voice_samples = list_available_voice_samples()
        if voice_samples:
            for sample in voice_samples:
                status = "✓" if sample["valid"] else "✗"
                console.print(f"  {status} {sample['speaker']}: {sample['path']} - {sample['message']}")
        else:
            console.print("[yellow]No voice samples found[/yellow]")
        return
    
    # Test voice cloning
    if args.language:
        # Test specific language
        if args.language not in voices:
            console.print(f"[red]Language '{args.language}' not configured[/red]")
            return
        
        wav_path = test_voice_cloning(args.text, args.language, args.speaker, voices, not args.no_play)
        if wav_path:
            console.print(f"\n[green]Test completed successfully![/green]")
            console.print(f"Generated audio: {wav_path}")
    else:
        # Test all languages
        results = test_all_languages(args.text, args.speaker, voices, not args.no_play)
        
        successful = sum(1 for path in results.values() if path is not None)
        total = len(results)
        
        console.print(f"\n[bold]Test Results: {successful}/{total} languages successful[/bold]")
        
        for language, wav_path in results.items():
            status = "✓" if wav_path else "✗"
            console.print(f"  {status} {language}: {'Success' if wav_path else 'Failed'}")

if __name__ == "__main__":
    main()
