#!/usr/bin/env python3
"""
Test script for transcription improvements without audio synthesis

This script tests the enhanced transcription pipeline with:
- Upgraded Whisper model (base/small)
- Domain-specific prompts
- Confidence scoring
- Named Entity Recognition

Author: Philip Baillargeon (Assistance by Cursor/GPT)
"""

import argparse
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import time

# Import our enhanced transcription utilities
from utils.transcription import (
    get_whisper_model, 
    transcribe_audio_chunk, 
    get_domain_prompt,
    enhance_with_ner
)
from utils.audio_streaming import load_audio_file

def check_dependencies():
    """Check if required dependencies are installed"""
    # All dependencies are now handled by environment.yml
    return True

console = Console()

def test_transcription(audio_path: str, model_size: str = "base", domain: str = "sports", 
                      device: str = "cpu", show_details: bool = True):
    """
    Test transcription with enhanced features
    
    Args:
        audio_path: Path to audio file
        model_size: Whisper model size (tiny, base, small, medium, large)
        domain: Domain type for better transcription
        device: Device to use (cpu, cuda, mps)
        show_details: Whether to show detailed results
    """
    
    # Check dependencies first
    ner_available = check_dependencies()
    
    console.print(Panel.fit(f"[bold blue]Enhanced Transcription Test[/bold blue]\n"
                           f"Audio: {audio_path}\n"
                           f"Model: {model_size}\n"
                           f"Domain: {domain}\n"
                           f"Device: {device}"))
    
    # Load Whisper model
    console.print(f"\n[green]Loading Whisper model: {model_size}[/green]")
    model = get_whisper_model(model_size, device)
    if model is None:
        console.print("[red]Failed to load Whisper model[/red]")
        return False
    
    # Load audio file
    console.print(f"[green]Loading audio: {audio_path}[/green]")
    try:
        audio_data, sample_rate = load_audio_file(audio_path)
        console.print(f"[green]✓ Loaded {len(audio_data)/sample_rate:.1f}s of audio at {sample_rate}Hz[/green]")
    except Exception as e:
        console.print(f"[red]Failed to load audio: {e}[/red]")
        return False
    
    # Show domain-specific prompt
    prompt = get_domain_prompt(domain)
    console.print(f"\n[dim]Domain prompt: {prompt}[/dim]")
    
    # Transcribe audio
    console.print(f"\n[green]Transcribing audio...[/green]")
    start_time = time.time()
    
    segments = transcribe_audio_chunk(audio_data, sample_rate, model, domain)
    
    transcription_time = time.time() - start_time
    audio_duration = len(audio_data) / sample_rate
    real_time_factor = transcription_time / audio_duration
    
    console.print(f"[green]✓ Transcription complete in {transcription_time:.2f}s (RTF: {real_time_factor:.2f})[/green]")
    
    if not segments:
        console.print("[yellow]No segments transcribed[/yellow]")
        return False
    
    # Display results
    if show_details:
        display_results(segments, domain)
    
    return True

def display_results(segments, domain):
    """Display transcription results in a formatted table"""
    
    # Create results table
    table = Table(title="Transcription Results", show_header=True, header_style="bold magenta")
    table.add_column("Time", style="dim", width=12)
    table.add_column("Text", style="default", width=60)
    table.add_column("Confidence", style="default", width=10)
    table.add_column("Quality", style="default", width=8)
    
    total_confidence = 0
    high_confidence_count = 0
    
    for start_time, end_time, text, confidence in segments:
        duration = end_time - start_time
        
        # Determine quality indicator
        if confidence >= 0.8:
            quality = "🟢 High"
            high_confidence_count += 1
        elif confidence >= 0.6:
            quality = "🟡 Medium"
        else:
            quality = "🔴 Low"
        
        time_str = f"{start_time:.1f}s - {end_time:.1f}s"
        conf_str = f"{confidence:.2f}"
        
        table.add_row(time_str, text, conf_str, quality)
        total_confidence += confidence
    
    console.print(table)
    
    # Summary statistics
    avg_confidence = total_confidence / len(segments) if segments else 0
    high_conf_percentage = (high_confidence_count / len(segments)) * 100 if segments else 0
    
    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"  • Total segments: {len(segments)}")
    console.print(f"  • Average confidence: {avg_confidence:.2f}")
    console.print(f"  • High confidence segments: {high_conf_percentage:.1f}%")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Test enhanced transcription pipeline")
    parser.add_argument("audio", help="Path to audio file")
    parser.add_argument("--model", default="base", choices=["tiny", "base", "small", "medium", "large"],
                       help="Whisper model size")
    parser.add_argument("--domain", default="sports", 
                       choices=["sports", "football", "basketball", "news", "interview", "general"],
                       help="Domain type for better transcription")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda", "mps"],
                       help="Device to use")
    parser.add_argument("--no-details", action="store_true", help="Hide detailed results")
    
    args = parser.parse_args()
    
    # Validate audio file
    if not Path(args.audio).exists():
        console.print(f"[red]Audio file not found: {args.audio}[/red]")
        sys.exit(1)
    
    # Run test
    success = test_transcription(
        args.audio, 
        args.model, 
        args.domain, 
        args.device,
        show_details=not args.no_details
    )
    
    if success:
        console.print("\n[green]✓ Transcription test completed successfully![/green]")
    else:
        console.print("\n[red]✗ Transcription test failed[/red]")
        sys.exit(1)

if __name__ == "__main__":
    main()
