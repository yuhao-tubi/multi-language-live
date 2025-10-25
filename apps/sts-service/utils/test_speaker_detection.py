#!/usr/bin/env python3
"""
Test Speaker Detection Utility

This script tests the speaker detection functionality with audio samples,
providing accuracy metrics and performance benchmarks.

Author: Philip Baillargeon (Assistance by Cursor/GPT)
"""

import sys
import time
import numpy as np
import librosa
from pathlib import Path
from typing import List, Dict, Tuple
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, TaskID
import argparse

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from utils.speaker_detection import SpeakerDetector, create_speaker_detector

console = Console()

def load_audio_samples(sample_dir: str) -> Dict[str, List[Tuple[np.ndarray, int]]]:
    """
    Load audio samples from directory, organized by speaker.
    
    Expected directory structure:
    sample_dir/
    ├── speaker1/
    │   ├── sample1.wav
    │   └── sample2.wav
    ├── speaker2/
    │   ├── sample1.wav
    │   └── sample2.wav
    └── ...
    
    Args:
        sample_dir: Directory containing speaker subdirectories
        
    Returns:
        Dictionary mapping speaker names to lists of (audio_data, sample_rate) tuples
    """
    sample_path = Path(sample_dir)
    if not sample_path.exists():
        console.print(f"[red]Sample directory not found: {sample_dir}[/red]")
        return {}
    
    samples = {}
    
    for speaker_dir in sample_path.iterdir():
        if speaker_dir.is_dir():
            speaker_name = speaker_dir.name
            samples[speaker_name] = []
            
            for audio_file in speaker_dir.glob("*.wav"):
                try:
                    audio_data, sample_rate = librosa.load(str(audio_file), sr=None)
                    samples[speaker_name].append((audio_data, sample_rate))
                    console.print(f"[dim]Loaded {speaker_name}: {audio_file.name}[/dim]")
                except Exception as e:
                    console.print(f"[red]Error loading {audio_file}: {e}[/red]")
    
    return samples

def test_speaker_detection(samples: Dict[str, List[Tuple[np.ndarray, int]]], 
                          similarity_threshold: float = 0.75) -> Dict:
    """
    Test speaker detection accuracy and performance.
    
    Args:
        samples: Dictionary of speaker samples
        similarity_threshold: Threshold for speaker matching
        
    Returns:
        Dictionary with test results
    """
    detector = create_speaker_detector(similarity_threshold=similarity_threshold)
    
    results = {
        'total_samples': 0,
        'correct_predictions': 0,
        'incorrect_predictions': 0,
        'new_speakers': 0,
        'extraction_times': [],
        'identification_times': [],
        'speaker_mapping': {},
        'confusion_matrix': {},
        'detailed_results': []
    }
    
    # First pass: Register speakers with first sample
    console.print("[bold]Phase 1: Registering speakers...[/bold]")
    for speaker_name, speaker_samples in samples.items():
        if speaker_samples:
            audio_data, sample_rate = speaker_samples[0]
            detected_id, confidence = detector.identify_speaker(audio_data, sample_rate)
            results['speaker_mapping'][detected_id] = speaker_name
            results['new_speakers'] += 1
            console.print(f"[green]Registered {speaker_name} as {detected_id}[/green]")
    
    # Second pass: Test all samples
    console.print("[bold]Phase 2: Testing speaker detection...[/bold]")
    
    with Progress() as progress:
        task = progress.add_task("Testing samples...", total=sum(len(samples) for samples in samples.values()))
        
        for speaker_name, speaker_samples in samples.items():
            for i, (audio_data, sample_rate) in enumerate(speaker_samples):
                start_time = time.time()
                detected_id, confidence = detector.identify_speaker(audio_data, sample_rate)
                identification_time = time.time() - start_time
                
                # Determine if prediction is correct
                expected_speaker = speaker_name
                predicted_speaker = results['speaker_mapping'].get(detected_id, 'unknown')
                
                is_correct = predicted_speaker == expected_speaker
                
                if is_correct:
                    results['correct_predictions'] += 1
                else:
                    results['incorrect_predictions'] += 1
                
                results['total_samples'] += 1
                results['identification_times'].append(identification_time)
                
                # Store detailed result
                result = {
                    'speaker_name': speaker_name,
                    'sample_index': i,
                    'detected_id': detected_id,
                    'predicted_speaker': predicted_speaker,
                    'confidence': confidence,
                    'is_correct': is_correct,
                    'identification_time': identification_time
                }
                results['detailed_results'].append(result)
                
                # Update confusion matrix
                if expected_speaker not in results['confusion_matrix']:
                    results['confusion_matrix'][expected_speaker] = {}
                if predicted_speaker not in results['confusion_matrix'][expected_speaker]:
                    results['confusion_matrix'][expected_speaker][predicted_speaker] = 0
                results['confusion_matrix'][expected_speaker][predicted_speaker] += 1
                
                progress.update(task, advance=1)
    
    # Get performance stats
    stats = detector.get_speaker_stats()
    results['extraction_times'] = stats['extraction_times']
    
    return results

def print_results(results: Dict):
    """Print test results in a formatted table."""
    
    # Overall accuracy
    accuracy = results['correct_predictions'] / results['total_samples'] if results['total_samples'] > 0 else 0
    
    console.print(f"\n[bold]Speaker Detection Test Results[/bold]")
    console.print(f"Total samples: {results['total_samples']}")
    console.print(f"Correct predictions: {results['correct_predictions']}")
    console.print(f"Incorrect predictions: {results['incorrect_predictions']}")
    console.print(f"Accuracy: {accuracy:.2%}")
    console.print(f"New speakers detected: {results['new_speakers']}")
    
    # Performance metrics
    avg_extraction_time = np.mean(results['extraction_times']) * 1000 if results['extraction_times'] else 0
    avg_identification_time = np.mean(results['identification_times']) * 1000 if results['identification_times'] else 0
    
    console.print(f"\n[bold]Performance Metrics[/bold]")
    console.print(f"Average extraction time: {avg_extraction_time:.1f}ms")
    console.print(f"Average identification time: {avg_identification_time:.1f}ms")
    
    # Speaker mapping
    console.print(f"\n[bold]Speaker Mapping[/bold]")
    for detected_id, speaker_name in results['speaker_mapping'].items():
        console.print(f"  {detected_id} → {speaker_name}")
    
    # Confusion matrix
    if results['confusion_matrix']:
        console.print(f"\n[bold]Confusion Matrix[/bold]")
        table = Table()
        table.add_column("Actual Speaker", style="cyan")
        table.add_column("Predicted Speaker", style="magenta")
        table.add_column("Count", style="green")
        
        for actual_speaker, predictions in results['confusion_matrix'].items():
            for predicted_speaker, count in predictions.items():
                table.add_row(actual_speaker, predicted_speaker, str(count))
        
        console.print(table)
    
    # Detailed results
    console.print(f"\n[bold]Detailed Results[/bold]")
    table = Table()
    table.add_column("Speaker", style="cyan")
    table.add_column("Sample", style="yellow")
    table.add_column("Detected ID", style="magenta")
    table.add_column("Confidence", style="green")
    table.add_column("Correct", style="red")
    table.add_column("Time (ms)", style="blue")
    
    for result in results['detailed_results']:
        correct_symbol = "✓" if result['is_correct'] else "✗"
        table.add_row(
            result['speaker_name'],
            str(result['sample_index']),
            result['detected_id'],
            f"{result['confidence']:.3f}",
            correct_symbol,
            f"{result['identification_time']*1000:.1f}"
        )
    
    console.print(table)

def create_test_samples(output_dir: str = "./test_samples"):
    """
    Create test audio samples for speaker detection testing.
    
    Args:
        output_dir: Directory to create test samples
    """
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    console.print(f"[green]Creating test samples in {output_dir}[/green]")
    
    # Create speaker directories
    speakers = ["speaker1", "speaker2", "speaker3"]
    sample_rate = 16000
    duration = 3.0
    
    for speaker in speakers:
        speaker_dir = output_path / speaker
        speaker_dir.mkdir(exist_ok=True)
        
        # Create 3 samples per speaker with different characteristics
        for i in range(3):
            # Different frequency for each speaker
            base_freq = 200 + (speakers.index(speaker) * 100) + (i * 50)
            
            # Generate sine wave with some variation
            t = np.linspace(0, duration, int(sample_rate * duration))
            audio = np.sin(2 * np.pi * base_freq * t).astype(np.float32)
            
            # Add some noise for realism
            noise = np.random.normal(0, 0.1, len(audio)).astype(np.float32)
            audio = audio + noise
            
            # Normalize
            audio = audio / np.max(np.abs(audio))
            
            # Save as WAV file
            output_file = speaker_dir / f"sample_{i+1}.wav"
            import soundfile as sf
            sf.write(str(output_file), audio, sample_rate)
            
            console.print(f"[dim]Created {speaker}/sample_{i+1}.wav (freq: {base_freq}Hz)[/dim]")
    
    console.print(f"[green]Test samples created successfully![/green]")
    console.print(f"Run: python test_speaker_detection.py test {output_dir}")

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Test Speaker Detection Utility")
    parser.add_argument("command", choices=["test", "create-samples"], 
                       help="Command to run")
    parser.add_argument("--samples-dir", default="./test_samples",
                       help="Directory containing test samples")
    parser.add_argument("--threshold", type=float, default=0.75,
                       help="Similarity threshold for speaker matching")
    parser.add_argument("--output-dir", default="./test_samples",
                       help="Output directory for created samples")
    
    args = parser.parse_args()
    
    if args.command == "create-samples":
        create_test_samples(args.output_dir)
    
    elif args.command == "test":
        if not Path(args.samples_dir).exists():
            console.print(f"[red]Samples directory not found: {args.samples_dir}[/red]")
            console.print("[yellow]Run 'python test_speaker_detection.py create-samples' first[/yellow]")
            return
        
        console.print(f"[bold]Testing speaker detection with samples from: {args.samples_dir}[/bold]")
        console.print(f"Similarity threshold: {args.threshold}")
        
        # Load samples
        samples = load_audio_samples(args.samples_dir)
        if not samples:
            console.print("[red]No samples found[/red]")
            return
        
        console.print(f"Found {len(samples)} speakers with {sum(len(s) for s in samples.values())} total samples")
        
        # Run tests
        results = test_speaker_detection(samples, args.threshold)
        
        # Print results
        print_results(results)

if __name__ == "__main__":
    main()
