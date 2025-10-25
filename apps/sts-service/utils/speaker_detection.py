#!/usr/bin/env python3
"""
Speaker Detection Utility for Real-time Audio Processing

This module provides fast speaker detection capabilities using librosa and scikit-learn
for extracting speaker embeddings and identifying different voices in audio streams.

Key Features:
- Fast embedding extraction using MFCCs and spectral features (~50-100ms per fragment)
- Online speaker clustering and tracking
- Support for pre-registered speakers and dynamic speaker discovery
- Integration with voice model assignment from coqui-voices.yaml

Author: Philip Baillargeon (Assistance by Cursor/GPT)
"""

import numpy as np
import librosa
import json
import pickle
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict
from rich.console import Console
import time
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import AgglomerativeClustering
import warnings

# Suppress sklearn warnings for cleaner output
warnings.filterwarnings('ignore', category=UserWarning, module='sklearn')

console = Console()

class SpeakerDetector:
    """
    Real-time speaker detection using audio embeddings and clustering.
    
    This class extracts speaker embeddings from audio and uses similarity-based
    clustering to identify different speakers across audio fragments.
    """
    
    def __init__(self, similarity_threshold: float = 0.75, device: str = "cpu", 
                 max_speakers: int = 10, embedding_dim: int = 60):
        """
        Initialize the speaker detector.
        
        Args:
            similarity_threshold: Threshold for speaker matching (0.0-1.0)
            device: Device for processing (cpu/mps/cuda)
            max_speakers: Maximum number of speakers to track
            embedding_dim: Dimension of speaker embeddings
        """
        self.similarity_threshold = similarity_threshold
        self.device = device
        self.max_speakers = max_speakers
        self.embedding_dim = embedding_dim
        
        # Speaker storage
        self.speaker_embeddings: Dict[str, np.ndarray] = {}
        self.speaker_metadata: Dict[str, Dict] = {}
        self.speaker_counts: Dict[str, int] = defaultdict(int)
        self.next_speaker_id = 0
        
        # Performance tracking
        self.extraction_times = []
        self.identification_times = []
        
        # Feature extraction parameters (optimized for speed)
        self.mfcc_params = {
            'n_mfcc': 13,  # Reduced from 40 for speed
            'n_fft': 1024,  # Reduced from 2048 for speed
            'hop_length': 256,  # Reduced from 512 for speed
            'n_mels': 64  # Reduced from 128 for speed
        }
        
        console.print(f"[green]SpeakerDetector initialized[/green]")
        console.print(f"  Similarity threshold: {similarity_threshold}")
        console.print(f"  Max speakers: {max_speakers}")
        console.print(f"  Embedding dimension: {embedding_dim}")
    
    def extract_embedding(self, audio_data: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        Extract speaker embedding from audio data.
        
        Uses a combination of MFCCs, spectral features, and pitch features
        optimized for speed while maintaining speaker discrimination.
        
        Args:
            audio_data: Audio data as numpy array
            sample_rate: Sample rate of audio
            
        Returns:
            Speaker embedding vector (embedding_dim dimensions)
        """
        start_time = time.time()
        
        try:
            # Ensure audio is float32 and normalized
            audio_data = audio_data.astype(np.float32)
            audio_data = librosa.util.normalize(audio_data)
            
            # Extract MFCCs (primary speaker feature)
            mfccs = librosa.feature.mfcc(
                y=audio_data, 
                sr=sample_rate,
                **self.mfcc_params
            )
            
            # Extract only essential spectral features for speed
            spectral_centroids = librosa.feature.spectral_centroid(y=audio_data, sr=sample_rate)
            zero_crossing_rate = librosa.feature.zero_crossing_rate(audio_data)
            
            # Skip expensive pitch extraction for speed
            # f0, voiced_flag, voiced_probs = librosa.pyin(...)
            
            # Aggregate features across time (mean + std)
            features = []
            
            # MFCCs: mean + std of each coefficient
            for i in range(mfccs.shape[0]):
                features.extend([
                    np.mean(mfccs[i]),
                    np.std(mfccs[i])
                ])
            
            # Essential spectral features: mean + std
            features.extend([
                np.mean(spectral_centroids),
                np.std(spectral_centroids)
            ])
            
            # Zero crossing rate: mean + std
            features.extend([
                np.mean(zero_crossing_rate),
                np.std(zero_crossing_rate)
            ])
            
            # Convert to numpy array and pad/truncate to embedding_dim
            embedding = np.array(features, dtype=np.float32)
            
            if len(embedding) > self.embedding_dim:
                embedding = embedding[:self.embedding_dim]
            elif len(embedding) < self.embedding_dim:
                # Pad with zeros
                padding = np.zeros(self.embedding_dim - len(embedding), dtype=np.float32)
                embedding = np.concatenate([embedding, padding])
            
            # Normalize embedding
            embedding = embedding / (np.linalg.norm(embedding) + 1e-8)
            
            # Track performance
            extraction_time = time.time() - start_time
            self.extraction_times.append(extraction_time)
            
            return embedding
            
        except Exception as e:
            console.print(f"[red]Error extracting embedding: {e}[/red]")
            # Return zero embedding on error
            return np.zeros(self.embedding_dim, dtype=np.float32)
    
    def identify_speaker(self, audio_data: np.ndarray, sample_rate: int) -> Tuple[str, float]:
        """
        Identify speaker from audio data using fast similarity-based approach.
        
        Args:
            audio_data: Audio data as numpy array
            sample_rate: Sample rate of audio
            
        Returns:
            Tuple of (speaker_id, confidence)
        """
        start_time = time.time()
        
        try:
            # Extract embedding
            embedding = self.extract_embedding(audio_data, sample_rate)
            
            if len(self.speaker_embeddings) == 0:
                # First speaker
                speaker_id = f"speaker_{self.next_speaker_id}"
                self.speaker_embeddings[speaker_id] = embedding
                self.speaker_metadata[speaker_id] = {
                    'created_at': time.time(),
                    'sample_count': 1,
                    'voice_sample_path': None
                }
                self.speaker_counts[speaker_id] = 1
                self.next_speaker_id += 1
                
                confidence = 1.0
                console.print(f"[green]New speaker detected: {speaker_id}[/green]")
                
            else:
                # Compare with existing speakers
                similarities = []
                speaker_ids = list(self.speaker_embeddings.keys())
                
                for speaker_id in speaker_ids:
                    similarity = cosine_similarity(
                        embedding.reshape(1, -1),
                        self.speaker_embeddings[speaker_id].reshape(1, -1)
                    )[0][0]
                    similarities.append(similarity)
                
                max_similarity = max(similarities)
                best_speaker_idx = similarities.index(max_similarity)
                best_speaker_id = speaker_ids[best_speaker_idx]
                
                if max_similarity >= self.similarity_threshold:
                    # Match found
                    speaker_id = best_speaker_id
                    confidence = max_similarity
                    
                    # Update speaker embedding with exponential moving average
                    alpha = 0.1  # Learning rate
                    self.speaker_embeddings[speaker_id] = (
                        (1 - alpha) * self.speaker_embeddings[speaker_id] + 
                        alpha * embedding
                    )
                    self.speaker_counts[speaker_id] += 1
                    
                    console.print(f"[blue]Speaker matched: {speaker_id} (confidence: {confidence:.3f})[/blue]")
                    
                else:
                    # New speaker
                    if len(self.speaker_embeddings) < self.max_speakers:
                        speaker_id = f"speaker_{self.next_speaker_id}"
                        self.speaker_embeddings[speaker_id] = embedding
                        self.speaker_metadata[speaker_id] = {
                            'created_at': time.time(),
                            'sample_count': 1,
                            'voice_sample_path': None
                        }
                        self.speaker_counts[speaker_id] = 1
                        self.next_speaker_id += 1
                        
                        confidence = 1.0
                        console.print(f"[green]New speaker detected: {speaker_id} (similarity: {max_similarity:.3f})[/green]")
                    else:
                        # Use closest existing speaker
                        speaker_id = best_speaker_id
                        confidence = max_similarity
                        console.print(f"[yellow]Max speakers reached, using closest: {speaker_id} (confidence: {confidence:.3f})[/yellow]")
            
            # Track performance
            identification_time = time.time() - start_time
            self.identification_times.append(identification_time)
            
            return speaker_id, confidence
            
        except Exception as e:
            console.print(f"[red]Error identifying speaker: {e}[/red]")
            return "default", 0.0
    
    def register_speaker(self, speaker_id: str, audio_data: np.ndarray, sample_rate: int, 
                        voice_sample_path: Optional[str] = None) -> bool:
        """
        Manually register a speaker with reference audio.
        
        Args:
            speaker_id: Unique identifier for the speaker
            audio_data: Reference audio data
            sample_rate: Sample rate of audio
            voice_sample_path: Optional path to voice sample file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            embedding = self.extract_embedding(audio_data, sample_rate)
            
            self.speaker_embeddings[speaker_id] = embedding
            self.speaker_metadata[speaker_id] = {
                'created_at': time.time(),
                'sample_count': 1,
                'voice_sample_path': voice_sample_path
            }
            self.speaker_counts[speaker_id] = 1
            
            console.print(f"[green]Registered speaker: {speaker_id}[/green]")
            return True
            
        except Exception as e:
            console.print(f"[red]Error registering speaker {speaker_id}: {e}[/red]")
            return False
    
    def update_speaker_embedding(self, speaker_id: str, audio_data: np.ndarray, sample_rate: int) -> bool:
        """
        Update existing speaker embedding with new audio.
        
        Args:
            speaker_id: Speaker identifier
            audio_data: New audio data
            sample_rate: Sample rate of audio
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if speaker_id not in self.speaker_embeddings:
                console.print(f"[red]Speaker {speaker_id} not found[/red]")
                return False
            
            new_embedding = self.extract_embedding(audio_data, sample_rate)
            
            # Exponential moving average update
            alpha = 0.1
            self.speaker_embeddings[speaker_id] = (
                (1 - alpha) * self.speaker_embeddings[speaker_id] + 
                alpha * new_embedding
            )
            
            self.speaker_counts[speaker_id] += 1
            self.speaker_metadata[speaker_id]['sample_count'] += 1
            
            return True
            
        except Exception as e:
            console.print(f"[red]Error updating speaker {speaker_id}: {e}[/red]")
            return False
    
    def get_speaker_voice_config(self, speaker_id: str, target_lang: str, 
                                voices_config: Optional[Dict] = None,
                                vits_config: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Get voice configuration for a speaker from VITS voices config.
        
        Args:
            speaker_id: Speaker identifier
            target_lang: Target language code
            voices_config: Voice configuration dictionary (legacy)
            vits_config: VITS voice configuration dictionary
            
        Returns:
            Voice configuration dictionary
        """
        # Try VITS config first (preferred)
        if vits_config:
            vits_models = vits_config.get('vits_models', {})
            if target_lang in vits_models:
                lang_config = vits_models[target_lang]
                
                # Check if speaker has specific VITS configuration
                if speaker_id in lang_config:
                    config = lang_config[speaker_id].copy()
                    config['config_type'] = 'vits'
                    return config
                
                # Fall back to default
                if 'default' in lang_config:
                    config = lang_config['default'].copy()
                    config['config_type'] = 'vits'
                    return config
        
        # Fall back to legacy voices config
        if voices_config:
            # Check speaker mapping first
            speaker_mapping = voices_config.get('speaker_mapping', {})
            if speaker_id in speaker_mapping:
                config = speaker_mapping[speaker_id].copy()
                config['config_type'] = 'legacy'
                return config
            
            # Check if speaker_id matches a configured speaker name
            languages = voices_config.get('languages', {})
            if target_lang in languages:
                speakers = languages[target_lang].get('speakers', {})
                if speaker_id in speakers:
                    config = speakers[speaker_id].copy()
                    config['config_type'] = 'legacy'
                    return config
            
            # Fall back to default
            default_config = speaker_mapping.get('default', {})
            if default_config:
                config = default_config.copy()
                config['config_type'] = 'legacy'
                return config
        
        # Ultimate fallback
        return {
            'model': f'tts_models/{target_lang}/css10/vits',
            'speaker_id': 0,
            'fallback_model': f'tts_models/{target_lang}/css10/vits',
            'config_type': 'fallback'
        }
    
    def get_speaker_stats(self) -> Dict[str, Any]:
        """
        Get statistics about detected speakers.
        
        Returns:
            Dictionary with speaker statistics
        """
        stats = {
            'total_speakers': len(self.speaker_embeddings),
            'speaker_counts': dict(self.speaker_counts),
            'avg_extraction_time': np.mean(self.extraction_times) if self.extraction_times else 0,
            'avg_identification_time': np.mean(self.identification_times) if self.identification_times else 0,
            'speakers': {}
        }
        
        for speaker_id, metadata in self.speaker_metadata.items():
            stats['speakers'][speaker_id] = {
                'sample_count': self.speaker_counts[speaker_id],
                'created_at': metadata['created_at'],
                'voice_sample_path': metadata.get('voice_sample_path')
            }
        
        return stats
    
    def save_speaker_database(self, file_path: str) -> bool:
        """
        Save speaker database to file.
        
        Args:
            file_path: Path to save the database
            
        Returns:
            True if successful, False otherwise
        """
        try:
            database = {
                'speaker_embeddings': self.speaker_embeddings,
                'speaker_metadata': self.speaker_metadata,
                'speaker_counts': dict(self.speaker_counts),
                'next_speaker_id': self.next_speaker_id,
                'similarity_threshold': self.similarity_threshold,
                'embedding_dim': self.embedding_dim
            }
            
            with open(file_path, 'wb') as f:
                pickle.dump(database, f)
            
            console.print(f"[green]Speaker database saved: {file_path}[/green]")
            return True
            
        except Exception as e:
            console.print(f"[red]Error saving speaker database: {e}[/red]")
            return False
    
    def load_speaker_database(self, file_path: str) -> bool:
        """
        Load speaker database from file.
        
        Args:
            file_path: Path to load the database from
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not Path(file_path).exists():
                console.print(f"[yellow]Speaker database not found: {file_path}[/yellow]")
                return False
            
            with open(file_path, 'rb') as f:
                database = pickle.load(f)
            
            self.speaker_embeddings = database['speaker_embeddings']
            self.speaker_metadata = database['speaker_metadata']
            self.speaker_counts = defaultdict(int, database['speaker_counts'])
            self.next_speaker_id = database['next_speaker_id']
            self.similarity_threshold = database.get('similarity_threshold', 0.75)
            self.embedding_dim = database.get('embedding_dim', 60)
            
            console.print(f"[green]Speaker database loaded: {file_path}[/green]")
            console.print(f"  Loaded {len(self.speaker_embeddings)} speakers")
            return True
            
        except Exception as e:
            console.print(f"[red]Error loading speaker database: {e}[/red]")
            return False
    
    def reset(self):
        """Reset the speaker detector to initial state."""
        self.speaker_embeddings.clear()
        self.speaker_metadata.clear()
        self.speaker_counts.clear()
        self.next_speaker_id = 0
        self.extraction_times.clear()
        self.identification_times.clear()
        
        console.print("[yellow]Speaker detector reset[/yellow]")


def create_speaker_detector(similarity_threshold: float = 0.75, device: str = "cpu") -> SpeakerDetector:
    """
    Create a new SpeakerDetector instance.
    
    Args:
        similarity_threshold: Threshold for speaker matching
        device: Device for processing
        
    Returns:
        SpeakerDetector instance
    """
    return SpeakerDetector(similarity_threshold=similarity_threshold, device=device)


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "test":
            # Test speaker detection with sample audio
            detector = SpeakerDetector()
            
            # Create some test audio (sine waves at different frequencies)
            sample_rate = 16000
            duration = 2.0
            
            # Speaker 1: 440 Hz tone
            t = np.linspace(0, duration, int(sample_rate * duration))
            audio1 = np.sin(2 * np.pi * 440 * t).astype(np.float32)
            
            # Speaker 2: 880 Hz tone  
            audio2 = np.sin(2 * np.pi * 880 * t).astype(np.float32)
            
            # Test identification
            speaker1, conf1 = detector.identify_speaker(audio1, sample_rate)
            speaker2, conf2 = detector.identify_speaker(audio2, sample_rate)
            speaker1_again, conf1_again = detector.identify_speaker(audio1, sample_rate)
            
            console.print(f"Speaker 1: {speaker1} (confidence: {conf1:.3f})")
            console.print(f"Speaker 2: {speaker2} (confidence: {conf2:.3f})")
            console.print(f"Speaker 1 again: {speaker1_again} (confidence: {conf1_again:.3f})")
            
            # Print stats
            stats = detector.get_speaker_stats()
            console.print(f"Total speakers: {stats['total_speakers']}")
            console.print(f"Avg extraction time: {stats['avg_extraction_time']*1000:.1f}ms")
            console.print(f"Avg identification time: {stats['avg_identification_time']*1000:.1f}ms")
        
        else:
            console.print("[red]Unknown command. Available commands: test[/red]")
    else:
        console.print("Speaker Detection Utility")
        console.print("Available commands:")
        console.print("  test - Test speaker detection with sample audio")
