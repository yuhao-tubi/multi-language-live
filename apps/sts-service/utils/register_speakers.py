#!/usr/bin/env python3
"""
Register Speakers Utility

This script provides a CLI tool to pre-register speakers with voice samples,
creating a speaker database for use with the speaker detection system.

Author: Philip Baillargeon (Assistance by Cursor/GPT)
"""

import sys
import argparse
from pathlib import Path
from typing import Dict, List, Optional
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, TaskID
import yaml

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from utils.speaker_detection import SpeakerDetector, create_speaker_detector
from utils.voice_management import validate_voice_sample, preprocess_voice_sample

console = Console()

def register_speaker_from_file(detector: SpeakerDetector, speaker_id: str, 
                              audio_file: str, voice_sample_path: Optional[str] = None) -> bool:
    """
    Register a speaker from an audio file.
    
    Args:
        detector: SpeakerDetector instance
        speaker_id: Unique identifier for the speaker
        audio_file: Path to audio file
        voice_sample_path: Optional path to voice sample for TTS
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Validate audio file
        is_valid, message = validate_voice_sample(audio_file)
        if not is_valid:
            console.print(f"[red]Invalid audio file: {message}[/red]")
            return False
        
        # Load audio
        import librosa
        audio_data, sample_rate = librosa.load(audio_file, sr=None)
        
        # Register speaker
        success = detector.register_speaker(speaker_id, audio_data, sample_rate, voice_sample_path)
        
        if success:
            console.print(f"[green]✓ Registered speaker: {speaker_id}[/green]")
            console.print(f"  Audio file: {audio_file}")
            if voice_sample_path:
                console.print(f"  Voice sample: {voice_sample_path}")
        else:
            console.print(f"[red]✗ Failed to register speaker: {speaker_id}[/red]")
        
        return success
        
    except Exception as e:
        console.print(f"[red]Error registering speaker {speaker_id}: {e}[/red]")
        return False

def register_speakers_from_config(detector: SpeakerDetector, config_file: str) -> Dict[str, bool]:
    """
    Register speakers from a configuration file.
    
    Expected config format:
    speakers:
      speaker1:
        audio_file: "./samples/speaker1_sample.wav"
        voice_sample: "./voice_samples/speaker1_voice.wav"
      speaker2:
        audio_file: "./samples/speaker2_sample.wav"
        voice_sample: "./voice_samples/speaker2_voice.wav"
    
    Args:
        detector: SpeakerDetector instance
        config_file: Path to configuration file
        
    Returns:
        Dictionary mapping speaker IDs to success status
    """
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        speakers_config = config.get('speakers', {})
        if not speakers_config:
            console.print("[red]No speakers found in configuration file[/red]")
            return {}
        
        results = {}
        
        with Progress() as progress:
            task = progress.add_task("Registering speakers...", total=len(speakers_config))
            
            for speaker_id, speaker_config in speakers_config.items():
                audio_file = speaker_config.get('audio_file')
                voice_sample = speaker_config.get('voice_sample')
                
                if not audio_file:
                    console.print(f"[red]No audio_file specified for speaker: {speaker_id}[/red]")
                    results[speaker_id] = False
                    progress.update(task, advance=1)
                    continue
                
                if not Path(audio_file).exists():
                    console.print(f"[red]Audio file not found: {audio_file}[/red]")
                    results[speaker_id] = False
                    progress.update(task, advance=1)
                    continue
                
                success = register_speaker_from_file(detector, speaker_id, audio_file, voice_sample)
                results[speaker_id] = success
                progress.update(task, advance=1)
        
        return results
        
    except Exception as e:
        console.print(f"[red]Error loading configuration file: {e}[/red]")
        return {}

def update_voice_config(detector: SpeakerDetector, config_file: str, target_lang: str = "es"):
    """
    Update voice configuration file with registered speakers.
    
    Args:
        detector: SpeakerDetector instance
        config_file: Path to voice configuration file
        target_lang: Target language code
    """
    try:
        # Load existing configuration
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        # Get speaker mapping
        speaker_mapping = config.get('speaker_mapping', {})
        
        # Update with registered speakers
        stats = detector.get_speaker_stats()
        for speaker_id, metadata in stats['speakers'].items():
            if speaker_id not in speaker_mapping:
                speaker_mapping[speaker_id] = {
                    'fallback_speaker': 'Andrew Chipper',
                    'voice_sample': metadata.get('voice_sample_path')
                }
        
        config['speaker_mapping'] = speaker_mapping
        
        # Save updated configuration
        with open(config_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        
        console.print(f"[green]Updated voice configuration: {config_file}[/green]")
        
    except Exception as e:
        console.print(f"[red]Error updating voice configuration: {e}[/red]")

def list_registered_speakers(detector: SpeakerDetector):
    """List all registered speakers."""
    stats = detector.get_speaker_stats()
    
    if not stats['speakers']:
        console.print("[yellow]No speakers registered[/yellow]")
        return
    
    console.print(f"[bold]Registered Speakers ({stats['total_speakers']})[/bold]")
    
    table = Table()
    table.add_column("Speaker ID", style="cyan")
    table.add_column("Sample Count", style="green")
    table.add_column("Voice Sample", style="magenta")
    table.add_column("Created", style="yellow")
    
    for speaker_id, metadata in stats['speakers'].items():
        voice_sample = metadata.get('voice_sample_path', 'None')
        created_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(metadata['created_at']))
        
        table.add_row(
            speaker_id,
            str(metadata['sample_count']),
            voice_sample,
            created_at
        )
    
    console.print(table)

def create_sample_config(output_file: str = "speaker_registration.yaml"):
    """
    Create a sample configuration file for speaker registration.
    
    Args:
        output_file: Path to output configuration file
    """
    sample_config = {
        'speakers': {
            'joe_buck': {
                'audio_file': './voice_samples/joe_buck_voice_sample.wav',
                'voice_sample': './voice_samples/joe_buck_voice_sample.wav'
            },
            'color_commentator': {
                'audio_file': './voice_samples/color_commentator.wav',
                'voice_sample': './voice_samples/color_commentator.wav'
            },
            'referee': {
                'audio_file': './voice_samples/referee_sample.wav',
                'voice_sample': './voice_samples/referee_sample.wav'
            }
        }
    }
    
    with open(output_file, 'w') as f:
        yaml.dump(sample_config, f, default_flow_style=False, sort_keys=False)
    
    console.print(f"[green]Created sample configuration: {output_file}[/green]")
    console.print("[yellow]Edit the file to specify your audio files and run:[/yellow]")
    console.print(f"python register_speakers.py register --config {output_file}")

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Register Speakers Utility")
    parser.add_argument("command", choices=["register", "list", "create-config", "update-config"],
                       help="Command to run")
    parser.add_argument("--speaker-id", help="Speaker ID for single registration")
    parser.add_argument("--audio-file", help="Audio file for single registration")
    parser.add_argument("--voice-sample", help="Voice sample file for single registration")
    parser.add_argument("--config", help="Configuration file for batch registration")
    parser.add_argument("--database", default="./speaker_database.pkl",
                       help="Speaker database file")
    parser.add_argument("--voice-config", default="coqui-voices.yaml",
                       help="Voice configuration file to update")
    parser.add_argument("--target-lang", default="es",
                       help="Target language for voice configuration")
    parser.add_argument("--threshold", type=float, default=0.75,
                       help="Similarity threshold for speaker matching")
    
    args = parser.parse_args()
    
    # Create speaker detector
    detector = create_speaker_detector(similarity_threshold=args.threshold)
    
    # Load existing database if it exists
    if Path(args.database).exists():
        detector.load_speaker_database(args.database)
        console.print(f"[green]Loaded existing speaker database: {args.database}[/green]")
    
    if args.command == "register":
        if args.config:
            # Batch registration from config file
            console.print(f"[bold]Registering speakers from config: {args.config}[/bold]")
            results = register_speakers_from_config(detector, args.config)
            
            # Print results
            successful = sum(1 for success in results.values() if success)
            total = len(results)
            console.print(f"\n[bold]Registration Results[/bold]")
            console.print(f"Successful: {successful}/{total}")
            
            for speaker_id, success in results.items():
                status = "✓" if success else "✗"
                console.print(f"  {status} {speaker_id}")
        
        elif args.speaker_id and args.audio_file:
            # Single speaker registration
            console.print(f"[bold]Registering speaker: {args.speaker_id}[/bold]")
            success = register_speaker_from_file(
                detector, 
                args.speaker_id, 
                args.audio_file, 
                args.voice_sample
            )
            
            if success:
                console.print(f"[green]Speaker {args.speaker_id} registered successfully[/green]")
            else:
                console.print(f"[red]Failed to register speaker {args.speaker_id}[/red]")
        
        else:
            console.print("[red]Either --config or --speaker-id + --audio-file required[/red]")
            return
        
        # Save database
        detector.save_speaker_database(args.database)
    
    elif args.command == "list":
        list_registered_speakers(detector)
    
    elif args.command == "create-config":
        create_sample_config()
    
    elif args.command == "update-config":
        console.print(f"[bold]Updating voice configuration: {args.voice_config}[/bold]")
        update_voice_config(detector, args.voice_config, args.target_lang)
    
    else:
        console.print("[red]Unknown command[/red]")

if __name__ == "__main__":
    import time
    main()
