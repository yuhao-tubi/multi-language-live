#!/usr/bin/env python3
"""
Audio Transcription Utilities using Faster-Whisper

This module provides streaming audio transcription capabilities using faster-whisper
for real-time processing of audio/video files with improved utterance detection.

Author: Philip Baillargeon (Assistance by Cursor/GPT)
"""

import numpy as np
import threading
import queue
import time
from typing import Iterator, Tuple, Optional, List
from pathlib import Path
from rich.console import Console
import librosa
import scipy.signal

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

console = Console()

def preprocess_audio_for_transcription(audio_data: np.ndarray, sample_rate: int) -> np.ndarray:
    """
    Preprocess audio data to improve transcription quality
    
    Args:
        audio_data: Raw audio data
        sample_rate: Sample rate of the audio
        
    Returns:
        Preprocessed audio data
    """
    # Ensure audio data is float32 for Whisper compatibility
    audio_data = audio_data.astype(np.float32)
    
    # Normalize audio (keep as float32)
    audio_data = librosa.util.normalize(audio_data).astype(np.float32)
    
    # Apply high-pass filter to remove low-frequency noise
    # This helps with speech clarity
    nyquist = sample_rate // 2
    high_cutoff = 80  # Hz
    sos = scipy.signal.butter(4, high_cutoff / nyquist, btype='high', output='sos')
    audio_data = scipy.signal.sosfilt(sos, audio_data).astype(np.float32)
    
    # Apply gentle noise reduction using spectral gating
    # This helps reduce background noise
    audio_data = librosa.effects.preemphasis(audio_data, coef=0.97).astype(np.float32)
    
    # Normalize again after processing (keep as float32)
    audio_data = librosa.util.normalize(audio_data).astype(np.float32)
    
    return audio_data

def split_long_segments(segments: List[Tuple[float, float, str, float]], 
                       max_duration: float = 6.0) -> List[Tuple[float, float, str, float]]:
    """
    Split segments that are too long for efficient processing.
    
    Long segments can cause delays in translation and TTS processing. This function
    intelligently splits them at natural boundaries (sentences, punctuation) to
    maintain semantic coherence while improving processing efficiency.
    
    Args:
        segments: List of (start_time, end_time, text, confidence) tuples
        max_duration: Maximum duration for a single segment (seconds)
        
    Returns:
        List of segments with long ones split at natural boundaries
        
    Strategy:
        1. Keep segments under max_duration as-is
        2. Split by sentence boundaries (periods) if available
        3. Split by punctuation (commas, semicolons) as fallback
        4. Force split at midpoint if no natural boundaries exist
    """
    split_segments = []
    
    for start_time, end_time, text, confidence in segments:
        duration = end_time - start_time
        
        if duration <= max_duration:
            # Segment is short enough, keep as is
            split_segments.append((start_time, end_time, text, confidence))
        else:
            # Segment is too long, try to split it
            console.print(f"[yellow]Splitting long segment: {duration:.1f}s - '{text[:50]}...'[/yellow]")
            
            # Split by sentences first
            sentences = text.split('. ')
            if len(sentences) > 1:
                # Split by sentences
                time_per_sentence = duration / len(sentences)
                for i, sentence in enumerate(sentences):
                    if i < len(sentences) - 1:
                        sentence += '.'
                    
                    seg_start = start_time + (i * time_per_sentence)
                    seg_end = start_time + ((i + 1) * time_per_sentence)
                    
                    if sentence.strip():
                        split_segments.append((seg_start, seg_end, sentence.strip(), confidence))
            else:
                # No sentence boundaries, split by commas or conjunctions
                split_points = []
                for i, char in enumerate(text):
                    if char in [',', ';', ' and ', ' but ', ' so ']:
                        split_points.append(i)
                
                if split_points:
                    # Split at punctuation
                    prev_pos = 0
                    time_per_char = duration / len(text)
                    
                    for pos in split_points:
                        seg_start = start_time + (prev_pos * time_per_char)
                        seg_end = start_time + (pos * time_per_char)
                        segment_text = text[prev_pos:pos].strip()
                        
                        if segment_text:
                            split_segments.append((seg_start, seg_end, segment_text, confidence))
                        prev_pos = pos + 1
                    
                    # Add remaining text
                    if prev_pos < len(text):
                        seg_start = start_time + (prev_pos * time_per_char)
                        seg_end = end_time
                        segment_text = text[prev_pos:].strip()
                        if segment_text:
                            split_segments.append((seg_start, seg_end, segment_text, confidence))
                else:
                    # No natural split points, force split at midpoint
                    mid_time = start_time + (duration / 2)
                    mid_text_pos = len(text) // 2
                    
                    # Find nearest space to avoid splitting words
                    for i in range(mid_text_pos, len(text)):
                        if text[i] == ' ':
                            mid_text_pos = i
                            break
                    
                    first_half = text[:mid_text_pos].strip()
                    second_half = text[mid_text_pos:].strip()
                    
                    if first_half:
                        split_segments.append((start_time, mid_time, first_half, confidence))
                    if second_half:
                        split_segments.append((mid_time, end_time, second_half, confidence))
    
    return split_segments

def improve_sentence_boundaries(segments: List[Tuple[float, float, str, float]]) -> List[Tuple[float, float, str, float]]:
    """
    Improve sentence boundary detection by merging short segments and splitting long ones
    
    Args:
        segments: List of (start_time, end_time, text, confidence) tuples
        
    Returns:
        Improved segments with better sentence boundaries
    """
    if not segments:
        return segments
    
    improved_segments = []
    current_segment = None
    
    for start_time, end_time, text, confidence in segments:
        text = text.strip()
        if not text:
            continue
            
        # If this is a very short segment (< 1 second), try to merge with previous
        if current_segment and (end_time - start_time) < 1.0:
            # Check if it makes sense to merge (no sentence ending punctuation)
            prev_text = current_segment[2]
            if not prev_text.endswith(('.', '!', '?')):
                # Merge with previous segment (average confidence)
                prev_confidence = current_segment[3]
                avg_confidence = (prev_confidence + confidence) / 2
                current_segment = (
                    current_segment[0],  # Keep original start time
                    end_time,           # Update end time
                    f"{prev_text} {text}",  # Combine text
                    avg_confidence      # Average confidence
                )
                continue
        
        # If we have a current segment, finalize it
        if current_segment:
            improved_segments.append(current_segment)
        
        # Start new segment
        current_segment = (start_time, end_time, text, confidence)
    
    # Add the last segment
    if current_segment:
        improved_segments.append(current_segment)
    
    return improved_segments

# Global cache for Whisper model
_whisper_cache = {}

def get_whisper_model(model_size: str = "base", device: str = "cpu") -> Optional[WhisperModel]:
    """
    Get or load Whisper model with caching and MPS fallback
    
    Args:
        model_size: Whisper model size (tiny, base, small, medium, large)
        device: Device to run on (cpu, cuda, mps)
        
    Returns:
        WhisperModel instance or None if faster-whisper not available
    """
    if WhisperModel is None:
        console.print("[red]faster-whisper not installed. Run: pip install faster-whisper[/red]")
        return None
    
    # Handle MPS fallback for faster-whisper compatibility
    if device == "mps":
        console.print("[yellow]Whisper doesn't support MPS, falling back to CPU[/yellow]")
        device = "cpu"
    
    cache_key = f"{model_size}_{device}"
    if cache_key not in _whisper_cache:
        console.print(f"Loading Whisper model: {model_size} on {device}")
        try:
            _whisper_cache[cache_key] = WhisperModel(
                model_size, 
                device=device,
                compute_type="float16" if device != "cpu" else "int8"
            )
        except Exception as e:
            console.print(f"[red]Failed to load Whisper model: {e}[/red]")
            return None
    
    return _whisper_cache[cache_key]

def get_domain_prompt(domain: str = "sports") -> str:
    """
    Generate domain-specific initial prompt for better transcription accuracy
    
    Args:
        domain: Domain type (sports, news, interview, etc.)
        
    Returns:
        Domain-specific prompt string
    """
    # Base prompt structure
    base_prompt = "This is a {domain_type} broadcast with {key_elements}."
    
    # Domain-specific configurations
    domain_configs = {
        "sports": {
            "domain_type": "sports commentary",
            "key_elements": "team names, player names, game statistics, play-by-play analysis, and sports terminology"
        },
        "football": {
            "domain_type": "American football commentary", 
            "key_elements": "team names, player names, yard lines, penalties, touchdowns, field goals, and detailed play descriptions"
        },
        "basketball": {
            "domain_type": "basketball commentary",
            "key_elements": "team names, player names, scores, fouls, timeouts, and game strategy analysis"
        },
        "news": {
            "domain_type": "news broadcast",
            "key_elements": "proper names, locations, dates, and formal speech patterns"
        },
        "interview": {
            "domain_type": "interview",
            "key_elements": "conversational speech, questions and answers, and natural pauses"
        },
        "general": {
            "domain_type": "general speech",
            "key_elements": "proper names, locations, and natural conversation patterns"
        }
    }
    
    config = domain_configs.get(domain, domain_configs["general"])
    return base_prompt.format(**config)

def enhance_with_ner(text: str, domain: str = "sports") -> str:
    """
    Simple text enhancement without external dependencies
    
    Args:
        text: Input text
        domain: Domain type for context-specific processing
        
    Returns:
        Enhanced text with basic capitalization improvements
    """
    # Simple capitalization for common patterns
    import re
    
    # Capitalize words after periods, exclamation marks, and question marks
    text = re.sub(r'(\.|!|\?)\s*([a-z])', lambda m: m.group(1) + ' ' + m.group(2).upper(), text)
    
    # Capitalize first letter of the text
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    
    # Domain-specific enhancements
    if domain == "sports":
        text = _enhance_sports_entities(text)
    
    return text

def _enhance_sports_entities(text: str) -> str:
    """
    Apply sports-specific entity enhancement rules
    
    Args:
        text: Input text
        
    Returns:
        Enhanced text with sports-specific corrections
    """
    import re
    
    # Capitalize common sports terms
    sports_patterns = [
        (r'\b(nfl|nba|mlb|nhl)\b', lambda m: m.group(1).upper()),
        (r'\b(touchdown|field goal|penalty|yard|yards|first down|second down|third down|fourth down)\b', 
         lambda m: m.group(1).title()),
        (r'\b(quarterback|running back|wide receiver|tight end|defensive back|linebacker)\b', 
         lambda m: m.group(1).title()),
        (r'\b(playoff|super bowl|championship|conference)\b', 
         lambda m: m.group(1).title()),
    ]
    
    enhanced_text = text
    for pattern, replacement in sports_patterns:
        enhanced_text = re.sub(pattern, replacement, enhanced_text, flags=re.IGNORECASE)
    
    return enhanced_text

def transcribe_audio_chunk(audio_data: np.ndarray, sample_rate: int, model: WhisperModel, 
                          domain: str = "sports") -> List[Tuple[float, float, str, float]]:
    """
    Transcribe a single audio chunk with confidence scoring and enhanced processing
    
    Args:
        audio_data: Audio data as numpy array
        sample_rate: Sample rate of audio
        model: WhisperModel instance
        domain: Domain type for better transcription accuracy
        
    Returns:
        List of (start_time, end_time, text, confidence) tuples
    """
    try:
        # Preprocess audio for better transcription quality
        audio_data = preprocess_audio_for_transcription(audio_data, sample_rate)
        
        # Get domain-specific prompt
        initial_prompt = get_domain_prompt(domain)
        
        segments, info = model.transcribe(
            audio_data,
            language="en",  # Assume English input
            word_timestamps=True,
            vad_filter=True,  # Voice activity detection
            vad_parameters=dict(min_silence_duration_ms=300),  # Reduced for more sensitive detection
            # Enhanced parameters for better accuracy
            beam_size=8,  # Increased beam search for better accuracy
            best_of=8,    # Generate more candidates and pick best
            temperature=[0.0, 0.2, 0.4],  # Temperature ensemble for better results
            compression_ratio_threshold=2.4,  # Detect repetition
            log_prob_threshold=-1.0,  # Filter low-confidence segments
            no_speech_threshold=0.6,  # Better silence detection
            condition_on_previous_text=True,  # Use context from previous segments
            initial_prompt=initial_prompt
        )
        
        results = []
        for segment in segments:
            if segment.text.strip():
                # Calculate confidence from log probability
                confidence = min(1.0, max(0.0, (segment.avg_logprob + 1.0) / 1.0))
                # Apply text enhancement
                enhanced_text = enhance_with_ner(segment.text.strip(), domain)
                results.append((segment.start, segment.end, enhanced_text, confidence))
        
        # Improve sentence boundaries
        results = improve_sentence_boundaries(results)
        
        # Split overly long segments for better processing
        results = split_long_segments(results)
        
        return results
    except Exception as e:
        console.print(f"[red]Transcription error: {e}[/red]")
        return []

class StreamingTranscriber:
    """
    Streaming transcriber for real-time audio processing
    
    This class provides a threaded interface for continuous audio transcription
    with buffering and result queuing for real-time applications.
    """
    
    def __init__(self, model_size: str = "base", device: str = "cpu"):
        self.model_size = model_size
        self.device = device
        self.model = None
        self.running = False
        self.transcription_thread = None
        self.audio_buffer = queue.Queue()
        self.result_queue = queue.Queue()
    
    def start(self) -> bool:
        """Start the streaming transcriber"""
        self.model = get_whisper_model(self.model_size, self.device)
        if self.model is None:
            return False
        
        self.running = True
        self.transcription_thread = threading.Thread(target=self._transcription_worker)
        self.transcription_thread.start()
        return True
    
    def stop(self):
        """Stop the streaming transcriber"""
        self.running = False
        if self.transcription_thread:
            self.transcription_thread.join()
    
    def add_audio_chunk(self, audio_data: np.ndarray, sample_rate: int, timestamp: float):
        """
        Add audio chunk to transcription buffer
        
        Args:
            audio_data: Audio data chunk
            sample_rate: Sample rate
            timestamp: Absolute timestamp of chunk start
        """
        self.audio_buffer.put((audio_data, sample_rate, timestamp))
    
    def get_transcription_results(self) -> Iterator[Tuple[float, float, str]]:
        """Get transcription results as they become available"""
        while self.running or not self.result_queue.empty():
            try:
                result = self.result_queue.get(timeout=0.1)
                yield result
            except queue.Empty:
                continue
    
    def _transcription_worker(self):
        """Worker thread for processing audio chunks"""
        while self.running:
            try:
                audio_data, sample_rate, timestamp = self.audio_buffer.get(timeout=1.0)
                
                # Transcribe chunk
                segments = transcribe_audio_chunk(audio_data, sample_rate, self.model)
                
                # Add results to queue with absolute timestamps
                for seg_start, seg_end, text, _ in segments:
                    abs_start = timestamp + seg_start
                    abs_end = timestamp + seg_end
                    self.result_queue.put((abs_start, abs_end, text))
                    
            except queue.Empty:
                continue
            except Exception as e:
                console.print(f"[red]Streaming transcription error: {e}[/red]")